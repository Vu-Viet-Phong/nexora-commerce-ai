"""Source reconciliation uses bounded Parquet batches and row fingerprints.

Only hashes/keys are retained internally, and only aggregate counts reach the
report. Source order is the loader's retained-row ordinal per source_sheet.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
import hashlib
import json
from pathlib import Path
from time import perf_counter

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import text

from src.data.ingest import ORIGINAL_COLUMNS
from src.data.load import LINE_COLUMNS, SOURCE_SYSTEM
from .contracts import TABLE_COLUMNS, qualified
from .frame import line_business_rules, missing_values
from .results import ValidationResult, compare, skipped

FLAGS = tuple(c for c in LINE_COLUMNS if c.startswith(("is_", "has_")))
REQUIRED_SOURCE = (*ORIGINAL_COLUMNS, "source_sheet", *FLAGS)
PAYLOAD = LINE_COLUMNS
CENT = Decimal("0.01")
RECONCILIATION_NAMES = (
    "source.row_counts", "source.dimension_keys", "source.flag_counts",
    "source.monetary_aggregates", "source.records", "source.provenance",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def copy_money(value) -> Decimal:
    """Match loader pandas.round(2) followed by COPY float_format='%.2f'."""
    return Decimal(format(float(value), ".2f"))


def fingerprint(row: dict) -> bytes:
    """Canonical payload: no identity line_id, no raw customer values in output."""
    values = []
    for column in PAYLOAD:
        value = row[column]
        if value is None or pd.isna(value):
            values.append(None)
        elif column == "invoice_date":
            values.append(pd.Timestamp(value).to_pydatetime(warn=False).isoformat())
        elif column == "unit_price":
            money = Decimal(str(value)).quantize(CENT)
            # PostgreSQL NUMERIC normalizes signed zero; fingerprints must too.
            values.append(format(abs(money) if money == 0 else money, ".2f"))
        elif column in ("customer_id", "quantity", "source_row_number"):
            values.append(int(value))
        elif column in FLAGS:
            values.append(bool(value))
        else:
            values.append(str(value))
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode("utf-8")).digest()


def source_expectations(path: Path, *, batch_size: int = 50_000) -> dict:
    """Reusable offline extraction; malformed input raises without logging rows."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    parquet = pq.ParquetFile(path)
    missing = sorted(set(REQUIRED_SOURCE) - set(parquet.schema_arrow.names))
    if missing:
        raise ValueError("Parquet is missing required contract columns: " + ", ".join(missing))
    sha = file_sha256(path)
    positions: dict[str, int] = defaultdict(int)
    record_hashes: dict[tuple[str, int], bytes] = {}
    keys = {"customers": set(), "products": set(), "invoices": set()}
    flag_counts = dict.fromkeys(FLAGS, 0)
    money = {name: Decimal("0.00") for name in ("ledger", "gross_sales", "merchandise_returns")}
    guest_lines = 0
    for batch in parquet.iter_batches(batch_size=batch_size, columns=list(REQUIRED_SOURCE)):
        frame = batch.to_pandas()
        required_values = [c for c in REQUIRED_SOURCE if c not in ("Customer ID", "Description")]
        if missing_values(frame, tuple(required_values)).status == "FAIL":
            raise ValueError("Parquet contains NULL values in required fields")
        source_lines = frame.rename(columns={
            "Invoice": "invoice_number", "StockCode": "stock_code",
            "Customer ID": "customer_id", "Description": "description",
            "Quantity": "quantity", "Price": "unit_price",
        })
        if line_business_rules(source_lines, prices_are_rounded=False).status == "FAIL":
            raise ValueError("Parquet business flags do not match Stage 1 contracts")
        frame["Price"] = frame["Price"].round(2)
        for raw in frame.to_dict("records"):
            sheet = str(raw["source_sheet"])
            positions[sheet] += 1
            position = positions[sheet]
            customer = None if pd.isna(raw["Customer ID"]) else int(raw["Customer ID"])
            if customer is not None and raw["Customer ID"] != customer:
                raise ValueError("Customer ID must match the loader integer contract")
            if float(raw["Quantity"]) != int(raw["Quantity"]):
                raise ValueError("Quantity must match the loader integer contract")
            quantity = int(raw["Quantity"])
            price = copy_money(raw["Price"])
            if not price.is_finite():
                raise ValueError("Price must be finite")
            row = {
                "source_system": SOURCE_SYSTEM, "source_sheet": sheet,
                "source_row_number": position,
                "source_line_key": f"{SOURCE_SYSTEM}:{sheet}:{position}",
                "source_file_sha256": sha,
                "invoice_number": str(raw["Invoice"]), "stock_code": str(raw["StockCode"]),
                "customer_id": customer,
                "description": None if pd.isna(raw["Description"]) else str(raw["Description"]),
                "invoice_date": raw["InvoiceDate"], "quantity": quantity, "unit_price": price,
                **{flag: bool(raw[flag]) for flag in FLAGS},
            }
            record_hashes[(sheet, position)] = fingerprint(row)
            # Keep only hashed entity identifiers, including customer IDs.
            for table, value in (("invoices", row["invoice_number"]),
                                 ("products", row["stock_code"]), ("customers", customer)):
                if value is not None:
                    keys[table].add(hashlib.sha256(str(value).encode()).digest())
            guest_lines += customer is None
            total = (price * quantity).quantize(CENT)
            money["ledger"] += total
            if row["is_valid_sale"]:
                money["gross_sales"] += total
            if row["is_cancellation"] and not row["is_non_product"]:
                money["merchandise_returns"] += total
            for flag in FLAGS:
                flag_counts[flag] += row[flag]
    money["net_merchandise"] = money["gross_sales"] + money["merchandise_returns"]
    if file_sha256(path) != sha:
        raise ValueError("Parquet changed while source expectations were built")
    return {
        "row_counts": {**{t: len(v) for t, v in keys.items()}, "invoice_lines": len(record_hashes)},
        "dimension_keys": keys, "record_hashes": record_hashes,
        "flag_counts": {**flag_counts, "guest_lines": guest_lines},
        "money": money, "sha256": sha,
    }


def record_differences(expected: dict, rows, *, consume: bool = False) -> dict[str, int]:
    """Detect missing/extra records and same-key payload changes, not just counts."""
    # The runner uses this index once; avoid a second million-key dictionary.
    # Standalone callers retain the existing non-mutating default.
    remaining = expected if consume else expected.copy()
    extra = changed = 0
    for row in rows:
        key = (str(row["source_sheet"]), int(row["source_row_number"]))
        expected_hash = remaining.pop(key, None)
        if expected_hash is None:
            extra += 1
        elif fingerprint(dict(row)) != expected_hash:
            changed += 1
    return {"missing": len(remaining), "extra": extra, "changed": changed}


def reconcile_source(connection, source_path: Path, schema: str) -> list[ValidationResult]:
    """Reconcile inside the caller's read-only snapshot; never load source data."""
    started = perf_counter()
    try:
        path = Path(source_path)
        expected = source_expectations(path)
    except Exception:
        return [
            ValidationResult("source.parquet", "Readable Parquet matching the loader contract",
                             None, "FAIL", (perf_counter() - started) * 1000,
                             "Cannot read or validate Parquet; verify path, columns, values and permissions."),
            *(skipped(name, "Parquet contract validation failed.") for name in RECONCILIATION_NAMES),
        ]
    results = [ValidationResult(
        "source.parquet", "Readable Parquet matching the loader contract",
        {"rows": expected["row_counts"]["invoice_lines"], "sha256": expected["sha256"]},
        "PASS", (perf_counter() - started) * 1000,
    )]

    def check(name, wanted, query):
        tick = perf_counter()
        try:
            with connection.begin_nested():
                actual = query()
            results.append(compare(name, wanted, actual, execution_ms=(perf_counter() - tick) * 1000))
        except Exception:
            results.append(ValidationResult(
                name, wanted, None, "FAIL", (perf_counter() - tick) * 1000,
                "Source reconciliation query failed; check PostgreSQL schema and permissions.",
            ))

    params = {"source": SOURCE_SYSTEM, "sha": expected["sha256"]}
    tables = {t: qualified(schema, t) for t in TABLE_COLUMNS}
    lines = tables["invoice_lines"]
    check("source.row_counts", expected["row_counts"], lambda: {
        table: connection.execute(text(f"SELECT COUNT(*) FROM {table_sql} "
                                        "WHERE source_system = :source"), params).scalar_one()
        for table, table_sql in tables.items()
    })

    def dimension_differences():
        differences = {}
        for table, column in (("customers", "customer_id"), ("products", "stock_code"),
                              ("invoices", "invoice_number")):
            actual = {
                hashlib.sha256(str(value).encode()).digest()
                for value in connection.execute(text(
                    f"SELECT {column} FROM {tables[table]} WHERE source_system = :source"
                ), params).scalars()
            }
            wanted = expected["dimension_keys"][table]
            differences[table] = {"missing": len(wanted - actual), "extra": len(actual - wanted)}
        return differences

    check("source.dimension_keys", {t: {"missing": 0, "extra": 0} for t in expected["dimension_keys"]},
          dimension_differences)
    flag_sql = ", ".join(f'COUNT(*) FILTER (WHERE "{f}") AS "{f}"' for f in FLAGS)
    check("source.flag_counts", expected["flag_counts"], lambda: dict(
        connection.execute(text(
            f"SELECT {flag_sql}, COUNT(*) FILTER (WHERE customer_id IS NULL) guest_lines "
            f"FROM {lines} WHERE source_system = :source"
        ), params).mappings().one()
    ))
    check("source.monetary_aggregates", expected["money"], lambda: dict(
        connection.execute(text(
            "SELECT COALESCE(SUM(line_total), 0) ledger, "
            "COALESCE(SUM(line_total) FILTER (WHERE is_valid_sale), 0) gross_sales, "
            "COALESCE(SUM(line_total) FILTER (WHERE is_cancellation AND NOT is_non_product), 0) merchandise_returns, "
            "COALESCE(SUM(line_total) FILTER (WHERE is_valid_sale), 0) + "
            "COALESCE(SUM(line_total) FILTER (WHERE is_cancellation AND NOT is_non_product), 0) net_merchandise "
            f"FROM {lines} WHERE source_system = :source"
        ), params).mappings().one()
    ))

    def records():
        columns = ", ".join(f'"{c}"' for c in PAYLOAD)
        with connection.execute(text(
            f"SELECT {columns} FROM {lines} WHERE source_system = :source"
        ), params, execution_options={"yield_per": 50_000}).mappings() as rows:
            return record_differences(expected["record_hashes"], rows, consume=True)

    check("source.records", {"missing": 0, "extra": 0, "changed": 0}, records)
    check("source.provenance", {t: 0 for t in tables}, lambda: {
        table: connection.execute(text(
            f"SELECT COUNT(*) FROM {table_sql} WHERE source_system = :source "
            "AND source_file_sha256 IS DISTINCT FROM :sha"
        ), params).scalar_one() for table, table_sql in tables.items()
    })
    return results

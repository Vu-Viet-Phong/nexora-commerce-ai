"""Load the Stage 1 parquet output into the approved PostgreSQL schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import pandas as pd
from sqlalchemy import create_engine, text

SOURCE_SYSTEM = "UCI"
DEFAULT_SOURCE = Path("data/processed/transactions_clean.parquet")
NON_PRODUCT_TYPES = {
    "POST": "POSTAGE",
    "DOT": "DISCOUNT",
    "M": "MANUAL_FEE",
    "C2": "CARRIAGE",
    "D": "DISCOUNT",
    "S": "SAMPLE",
    "BANK CHARGES": "BANK_CHARGE",
    "ADJUST": "INVENTORY_ADJUSTMENT",
    "ADJUST2": "INVENTORY_ADJUSTMENT",
    "AMAZONFEE": "AMAZON_FEE",
    "CRUK": "SERVICE",
    "TEST001": "TEST",
    "TEST002": "TEST",
}
LINE_COLUMNS = (
    "source_system",
    "source_line_key",
    "source_sheet",
    "source_row_number",
    "source_file_sha256",
    "invoice_number",
    "stock_code",
    "customer_id",
    "description",
    "invoice_date",
    "quantity",
    "unit_price",
    "is_duplicate_within_sheet",
    "is_duplicate_cross_sheet",
    "is_cancellation",
    "is_bad_debt_adjustment",
    "is_negative_quantity",
    "is_return",
    "is_inventory_adjustment",
    "has_customer_id",
    "has_description",
    "has_valid_price",
    "is_price_zero",
    "is_price_negative",
    "is_non_product",
    "is_unknown_special_code",
    "is_valid_sale",
)


def load_local_env() -> None:
    """Load ignored local configuration without replacing process variables."""
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def normalize_database_url(url: str) -> str:
    """Make an unescaped local password safe for SQLAlchemy parsing."""
    marker = "@localhost:5432/"
    if marker not in url:
        return url
    prefix, suffix = url.rsplit(marker, 1)
    scheme, credentials = prefix.split("://", 1)
    username, password = credentials.split(":", 1)
    return f"{scheme}://{username}:{quote(unquote(password), safe='')}{marker}{suffix}"


def source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mode_latest(values: pd.Series) -> str:
    counts = values.dropna().astype(str).value_counts()
    if counts.empty:
        return ""
    candidates = set(counts[counts == counts.max()].index)
    for value in reversed(values.dropna().astype(str).tolist()):
        if value in candidates:
            return value
    return str(counts.index[0])


def _first_customer(values: pd.Series) -> int | None:
    non_null = values.dropna()
    return int(non_null.iloc[0]) if not non_null.empty else None


def _invoice_type(frame: pd.DataFrame) -> str:
    if frame["is_cancellation"].any():
        return "CANCELLATION"
    if frame["is_bad_debt_adjustment"].any():
        return "BAD_DEBT_ADJUSTMENT"
    if frame["is_inventory_adjustment"].any():
        return "INVENTORY_ADJUSTMENT"
    return "SALE"


def prepare_frames(source_path: Path) -> tuple[pd.DataFrame, ...]:
    """Build dimension, header, and line frames from the immutable parquet."""
    frame = pd.read_parquet(source_path).copy()
    frame["source_row_number"] = frame.groupby("source_sheet", sort=False).cumcount() + 1
    frame["source_line_key"] = (
        SOURCE_SYSTEM
        + ":"
        + frame["source_sheet"].astype(str)
        + ":"
        + frame["source_row_number"].astype(str)
    )
    frame["invoice_date"] = pd.to_datetime(frame["InvoiceDate"])
    frame["unit_price"] = frame["Price"].round(2)
    frame["customer_id"] = frame["Customer ID"].astype("Int64")
    frame["invoice_number"] = frame["Invoice"].astype(str)
    frame["stock_code"] = frame["StockCode"].astype(str)
    sha = source_sha256(source_path)

    customer_rows: list[dict[str, Any]] = []
    for customer_id, group in frame.dropna(subset=["customer_id"]).groupby(
        "customer_id", sort=True
    ):
        valid = group["is_valid_sale"]
        returns = group["is_cancellation"] & ~group["is_non_product"]
        customer_rows.append(
            {
                "source_system": SOURCE_SYSTEM,
                "customer_id": int(customer_id),
                "primary_country": _mode_latest(group["Country"]),
                "first_invoice_date": group["invoice_date"].min(),
                "last_invoice_date": group["invoice_date"].max(),
                "total_orders_lifetime": int(group.loc[valid, "invoice_number"].nunique()),
                "total_merchandise_spend": round(
                    group.loc[valid, "line_total"].sum()
                    + group.loc[returns, "line_total"].sum(),
                    2,
                ),
                "source_file_sha256": sha,
            }
        )
    customers = pd.DataFrame(customer_rows)

    product_rows: list[dict[str, Any]] = []
    for stock_code, group in frame.groupby("stock_code", sort=True):
        product_type = NON_PRODUCT_TYPES.get(stock_code, "PHYSICAL_MERCHANDISE")
        valid_prices = group.loc[group["has_valid_price"], "unit_price"]
        product_rows.append(
            {
                "source_system": SOURCE_SYSTEM,
                "stock_code": stock_code,
                "primary_description": _mode_latest(group["Description"]) or None,
                "product_type": product_type,
                "is_physical_merchandise": product_type == "PHYSICAL_MERCHANDISE",
                "median_unit_price": valid_prices.median() if not valid_prices.empty else None,
                "first_seen_date": group["invoice_date"].min(),
                "last_seen_date": group["invoice_date"].max(),
                "source_file_sha256": sha,
            }
        )
    products = pd.DataFrame(product_rows)

    invoice_rows: list[dict[str, Any]] = []
    for invoice_number, group in frame.groupby("invoice_number", sort=True):
        invoice_rows.append(
            {
                "source_system": SOURCE_SYSTEM,
                "invoice_number": invoice_number,
                "customer_id": _first_customer(group["customer_id"]),
                "invoice_date": group["invoice_date"].min(),
                "country": str(group["Country"].iloc[0]),
                "invoice_type": _invoice_type(group),
                "total_line_count": len(group),
                "total_quantity": int(group["Quantity"].sum()),
                "total_invoice_amount": round(group["line_total"].sum(), 2),
                "source_file_sha256": sha,
            }
        )
    invoices = pd.DataFrame(invoice_rows)

    lines = pd.DataFrame(
        {
            "source_system": SOURCE_SYSTEM,
            "source_line_key": frame["source_line_key"],
            "source_sheet": frame["source_sheet"],
            "source_row_number": frame["source_row_number"],
            "source_file_sha256": sha,
            "invoice_number": frame["invoice_number"],
            "stock_code": frame["stock_code"],
            "customer_id": frame["customer_id"],
            "description": frame["Description"],
            "invoice_date": frame["invoice_date"],
            "quantity": frame["Quantity"],
            "unit_price": frame["unit_price"],
            **{
                column: frame[column]
                for column in LINE_COLUMNS
                if column.startswith(("is_", "has_"))
            },
        }
    )
    return customers, products, invoices, lines


def copy_frame(connection: Any, table: str, frame: pd.DataFrame, columns: tuple[str, ...]) -> int:
    """Bulk insert rows with PostgreSQL COPY on the active transaction."""
    dbapi = connection.connection.driver_connection
    output = frame.loc[:, list(columns)].copy()
    integer_columns = {
        "customer_id",
        "source_row_number",
        "quantity",
        "total_line_count",
        "total_quantity",
    }
    for column in integer_columns.intersection(output.columns):
        output[column] = output[column].astype("Int64")
    buffer = output.to_csv(
        index=False,
        header=False,
        na_rep="\\N",
        lineterminator="\n",
        float_format="%.2f",
    )
    column_sql = ", ".join(columns)
    with dbapi.cursor().copy(
        f"COPY {table} ({column_sql}) FROM STDIN WITH (FORMAT CSV, NULL '\\N')"
    ) as copy:
        copy.write(buffer)
    return len(output)


def load_source(
    database_url: str,
    source_path: Path = DEFAULT_SOURCE,
    *,
    fail_after: str | None = None,
    schema: str | None = None,
) -> dict[str, Any]:
    """Atomically replace this source namespace and return load metrics."""
    customers, products, invoices, lines = prepare_frames(source_path)
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    with engine.begin() as connection:
        if schema is not None:
            if not schema.isidentifier():
                raise ValueError("schema must be a valid SQL identifier")
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
        actual_database = connection.execute(text("SELECT current_database()")).scalar_one()
        for table in ("invoice_lines", "invoices", "products", "customers"):
            connection.execute(
                text(f"DELETE FROM {table} WHERE source_system = :source_system"),
                {"source_system": SOURCE_SYSTEM},
            )
        if fail_after == "delete":
            raise RuntimeError("intentional loader failure after source delete")
        copy_frame(connection, "customers", customers, tuple(customers.columns))
        copy_frame(connection, "products", products, tuple(products.columns))
        copy_frame(connection, "invoices", invoices, tuple(invoices.columns))
        copy_frame(connection, "invoice_lines", lines, LINE_COLUMNS)
        if fail_after == "copy":
            raise RuntimeError("intentional loader failure after bulk copy")
    engine.dispose()
    return {
        "database": actual_database,
        "customers": len(customers),
        "products": len(products),
        "invoices": len(invoices),
        "invoice_lines": len(lines),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()
    load_local_env()
    database_url = args.database_url or os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    print(json.dumps(load_source(database_url, args.source), sort_keys=True))


if __name__ == "__main__":
    main()

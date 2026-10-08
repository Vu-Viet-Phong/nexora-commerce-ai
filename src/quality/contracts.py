"""Contracts copied from schema.sql and existing Stage 1/2 implementation.

No marts are queried here. Duplicate business-looking lines and guest customers
are retained by the approved source contract.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from src.data.load import LINE_COLUMNS
from src.data.clean import KNOWN_NON_PRODUCT_CODES, KNOWN_NON_PRODUCT_PREFIXES

TABLE_COLUMNS = {
    "customers": (
        "source_system", "customer_id", "primary_country", "first_invoice_date",
        "last_invoice_date", "total_orders_lifetime", "total_merchandise_spend",
        "source_file_sha256",
    ),
    "products": (
        "source_system", "stock_code", "primary_description", "product_type",
        "is_physical_merchandise", "median_unit_price", "first_seen_date",
        "last_seen_date", "source_file_sha256",
    ),
    "invoices": (
        "source_system", "invoice_number", "customer_id", "invoice_date", "country",
        "invoice_type", "total_line_count", "total_quantity",
        "total_invoice_amount", "source_file_sha256",
    ),
    "invoice_lines": ("line_id", *LINE_COLUMNS, "line_total"),
}
NULLABLE = {
    "products": {"primary_description", "median_unit_price"},
    "invoices": {"customer_id"},
    "invoice_lines": {"customer_id", "description"},
    "customers": set(),
}
MONEY_COLUMNS = {
    ("customers", "total_merchandise_spend"): 14,
    ("products", "median_unit_price"): 12,
    ("invoices", "total_invoice_amount"): 14,
    ("invoice_lines", "unit_price"): 12,
    ("invoice_lines", "line_total"): 14,
}
GRAINS = {
    "customers": ("source_system", "customer_id"),
    "products": ("source_system", "stock_code"),
    "invoices": ("source_system", "invoice_number"),
    "invoice_lines": ("source_system", "source_line_key"),
}
MARTS = ("mart_daily_sales", "mart_customer_daily", "mart_customer_snapshot")


def qualified(schema: str, table: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("schema must be a simple SQL identifier")
    if table not in TABLE_COLUMNS:
        raise ValueError("table is outside the relational-core contract")
    return f'"{schema}"."{table}"'


@dataclass(frozen=True)
class Check:
    name: str
    sql: str
    expected: int = 0


def core_checks(schema: str) -> list[Check]:
    """Build fixed SELECTs; all source values are bound parameters."""
    tables = {table: qualified(schema, table) for table in TABLE_COLUMNS}
    l, i, p, c = (tables[t] for t in ("invoice_lines", "invoices", "products", "customers"))
    checks: list[Check] = []
    for table, columns in TABLE_COLUMNS.items():
        missing = " OR ".join(f'"{column}" IS NULL' for column in columns
                              if column not in NULLABLE[table])
        checks.append(Check(
            f"completeness.{table}",
            f"SELECT COUNT(*) FROM {tables[table]} WHERE source_system = :source AND ({missing})",
        ))
        grain = ", ".join(f'"{column}"' for column in GRAINS[table])
        checks.append(Check(
            f"uniqueness.{table}.grain",
            f"SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) n "
            f"FROM {tables[table]} WHERE source_system = :source "
            f"GROUP BY {grain} HAVING COUNT(*) > 1) d",
        ))
    for name, columns in (
        ("line_id", "line_id"), ("source_position", "source_system, source_sheet, source_row_number"),
    ):
        checks.append(Check(
            f"uniqueness.invoice_lines.{name}",
            f"SELECT COALESCE(SUM(n - 1), 0) FROM (SELECT COUNT(*) n FROM {l} "
            f"WHERE source_system = :source GROUP BY {columns} HAVING COUNT(*) > 1) d",
        ))
    for child, parent, key in (
        ("invoices", "customers", "customer_id"),
        ("invoice_lines", "customers", "customer_id"),
        ("invoice_lines", "products", "stock_code"),
        ("invoice_lines", "invoices", "invoice_number"),
    ):
        checks.append(Check(
            f"integrity.{child}.{parent}",
            f"SELECT COUNT(*) FROM {tables[child]} child WHERE child.source_system = :source "
            f"AND child.{key} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {tables[parent]} parent "
            f"WHERE parent.source_system = child.source_system AND parent.{key} = child.{key})",
        ))
    predicates = {
        "source_line_key": "source_row_number <= 0 OR source_line_key IS DISTINCT FROM "
                           "(source_system || ':' || source_sheet || ':' || source_row_number::text)",
        "identifiers": "invoice_number = '' OR stock_code = '' OR source_sheet = ''",
        "customer_presence": "has_customer_id IS DISTINCT FROM (customer_id IS NOT NULL)",
        "description_presence": "has_description IS DISTINCT FROM (description IS NOT NULL)",
        "cancellation": "is_cancellation IS DISTINCT FROM (UPPER(invoice_number) LIKE 'C%')",
        "bad_debt": "is_bad_debt_adjustment IS DISTINCT FROM (UPPER(invoice_number) LIKE 'A%')",
        "return": "is_return IS DISTINCT FROM is_cancellation",
        "negative_quantity": "is_negative_quantity IS DISTINCT FROM (quantity < 0)",
        "price_flags": "is_price_zero IS DISTINCT FROM (unit_price = 0) OR "
                       "is_price_negative IS DISTINCT FROM (unit_price < 0) OR "
                       "has_valid_price IS DISTINCT FROM (unit_price > 0)",
        "inventory_adjustment": "is_inventory_adjustment IS DISTINCT FROM "
                                "(quantity < 0 AND NOT is_cancellation AND is_price_zero AND customer_id IS NULL)",
        "valid_sale": "is_valid_sale IS DISTINCT FROM (NOT is_cancellation AND NOT "
                      "is_bad_debt_adjustment AND quantity > 0 AND has_valid_price AND NOT is_non_product)",
        "non_product": "is_non_product IS DISTINCT FROM (stock_code = ANY(:non_product_codes) OR "
                       + " OR ".join(
                           f"LEFT(stock_code, {len(prefix)}) = :prefix_{index}"
                           for index, prefix in enumerate(KNOWN_NON_PRODUCT_PREFIXES)
                       ) + ")",
    }
    for name, predicate in predicates.items():
        checks.append(Check(f"business.{name}",
                            f"SELECT COUNT(*) FROM {l} WHERE source_system = :source AND ({predicate})"))
    checks.extend([
        Check("integrity.line_header_customer",
              f"SELECT COUNT(*) FROM {l} l JOIN {i} i USING (source_system, invoice_number) "
              "WHERE l.source_system = :source AND l.customer_id IS NOT NULL "
              "AND l.customer_id IS DISTINCT FROM i.customer_id"),
        Check("financial.line_arithmetic",
              f"SELECT COUNT(*) FROM {l} WHERE source_system = :source "
              "AND line_total IS DISTINCT FROM ROUND(quantity::numeric * unit_price, 2)"),
        Check("financial.invoice_ledger",
              f"SELECT COUNT(*) FROM {i} i LEFT JOIN (SELECT source_system, invoice_number, "
              f"COUNT(*) n, SUM(quantity) q, SUM(line_total) amount, MIN(invoice_date) first_date "
              f"FROM {l} WHERE source_system = :source GROUP BY source_system, invoice_number) l "
              "USING (source_system, invoice_number) WHERE i.source_system = :source AND "
              "(i.total_line_count IS DISTINCT FROM l.n OR i.total_quantity IS DISTINCT FROM l.q "
              "OR i.total_invoice_amount IS DISTINCT FROM l.amount OR i.invoice_date IS DISTINCT FROM l.first_date)"),
        Check("business.invoice_type",
              f"SELECT COUNT(*) FROM {i} i LEFT JOIN (SELECT source_system, invoice_number, "
              "CASE WHEN BOOL_OR(is_cancellation) THEN 'CANCELLATION' "
              "WHEN BOOL_OR(is_bad_debt_adjustment) THEN 'BAD_DEBT_ADJUSTMENT' "
              "WHEN BOOL_OR(is_inventory_adjustment) THEN 'INVENTORY_ADJUSTMENT' ELSE 'SALE' END kind "
              f"FROM {l} WHERE source_system = :source GROUP BY source_system, invoice_number) l "
              "USING (source_system, invoice_number) WHERE i.source_system = :source "
              "AND i.invoice_type IS DISTINCT FROM l.kind"),
        Check("financial.customer_merchandise",
              f"SELECT COUNT(*) FROM {c} c LEFT JOIN (SELECT source_system, customer_id, "
              "COUNT(DISTINCT invoice_number) FILTER (WHERE is_valid_sale) orders, "
              "COALESCE(SUM(line_total) FILTER (WHERE is_valid_sale), 0) + "
              "COALESCE(SUM(line_total) FILTER (WHERE is_cancellation AND NOT is_non_product), 0) spend "
              f"FROM {l} WHERE source_system = :source AND customer_id IS NOT NULL "
              "GROUP BY source_system, customer_id) l USING (source_system, customer_id) "
              "WHERE c.source_system = :source AND (c.total_orders_lifetime IS DISTINCT FROM l.orders "
              "OR c.total_merchandise_spend IS DISTINCT FROM l.spend)"),
        Check("integrity.join_fanout",
              f"SELECT ABS((SELECT COUNT(*) FROM {l} WHERE source_system = :source) - "
              f"(SELECT COUNT(*) FROM {l} l JOIN {p} p USING (source_system, stock_code) "
              f"JOIN {i} i USING (source_system, invoice_number) LEFT JOIN {c} c "
              "ON c.source_system = l.source_system AND c.customer_id = l.customer_id "
              "WHERE l.source_system = :source))"),
    ])
    return checks


def parameters(source_system: str) -> dict:
    return {"source": source_system, "non_product_codes": sorted(KNOWN_NON_PRODUCT_CODES),
            **{f"prefix_{i}": prefix for i, prefix in enumerate(KNOWN_NON_PRODUCT_PREFIXES)}}

"""Read-only PostgreSQL enforcement metadata from the accepted schema.sql."""
from __future__ import annotations

from time import perf_counter
from sqlalchemy import text
from .results import ValidationResult, compare

PRIMARY_KEYS = {
    "customers": ("source_system", "customer_id"),
    "products": ("source_system", "stock_code"),
    "invoices": ("source_system", "invoice_number"),
    "invoice_lines": ("line_id",),
}
UNIQUE_KEYS = {"invoice_lines": (
    ("source_system", "source_line_key"),
    ("source_system", "source_sheet", "source_row_number"),
)}
FOREIGN_KEYS = (
    ("invoices", ("source_system", "customer_id"), "customers", ("source_system", "customer_id")),
    ("invoice_lines", ("source_system", "customer_id"), "customers", ("source_system", "customer_id")),
    ("invoice_lines", ("source_system", "stock_code"), "products", ("source_system", "stock_code")),
    ("invoice_lines", ("source_system", "invoice_number"), "invoices", ("source_system", "invoice_number")),
)
INDEXES = {
    ("invoices", "idx_invoices_customer"): ("source_system", "customer_id"),
    ("invoices", "idx_invoices_date"): ("source_system", "invoice_date"),
    ("invoice_lines", "idx_invoice_lines_invoice"): ("source_system", "invoice_number"),
    ("invoice_lines", "idx_invoice_lines_product"): ("source_system", "stock_code"),
    ("invoice_lines", "idx_invoice_lines_customer"): ("source_system", "customer_id"),
    ("invoice_lines", "idx_invoice_lines_date"): ("source_system", "invoice_date"),
}
NAMES = ("schema.primary_keys", "schema.foreign_keys", "schema.unique_constraints", "schema.indexes")

CONSTRAINT_SQL = """
SELECT t.relname table_name, c.contype::text kind,
    ARRAY(SELECT a.attname::text FROM unnest(c.conkey) WITH ORDINALITY AS k(num, ord)
          JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.num ORDER BY k.ord) columns,
    pn.nspname referenced_schema, p.relname referenced_table,
    ARRAY(SELECT a.attname::text FROM unnest(c.confkey) WITH ORDINALITY AS k(num, ord)
          JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.num ORDER BY k.ord) referenced_columns,
    c.confdeltype::text delete_action, c.confupdtype::text update_action,
    c.convalidated validated, ix.indisvalid index_valid, ix.indisready index_ready
FROM pg_constraint c JOIN pg_class t ON t.oid = c.conrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
LEFT JOIN pg_class p ON p.oid = c.confrelid
LEFT JOIN pg_namespace pn ON pn.oid = p.relnamespace
LEFT JOIN pg_index ix ON ix.indexrelid = c.conindid
WHERE n.nspname = :schema AND t.relname IN ('customers', 'products', 'invoices', 'invoice_lines')
AND c.contype IN ('p', 'u', 'f')
"""

INDEX_SQL = """
SELECT t.relname table_name, i.relname index_name,
    ARRAY(SELECT a.attname::text FROM unnest(ix.indkey) WITH ORDINALITY AS k(num, ord)
          JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.num
          WHERE k.ord <= ix.indnkeyatts ORDER BY k.ord) columns,
    am.amname method, ix.indisunique is_unique, ix.indisvalid valid, ix.indisready ready,
    (ix.indpred IS NULL AND ix.indexprs IS NULL) unconditional_simple
FROM pg_index ix JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_am am ON am.oid = i.relam
WHERE n.nspname = :schema AND t.relname IN ('customers', 'products', 'invoices', 'invoice_lines')
"""


def metadata_results(constraints: list[dict], indexes: list[dict], schema: str) -> list[ValidationResult]:
    """Compare definitions, not just names or current duplicate/orphan counts."""
    results = []
    groups = {
        "schema.primary_keys": [(t, cols, "p", None, None) for t, cols in PRIMARY_KEYS.items()],
        "schema.foreign_keys": [(t, cols, "f", parent, parent_cols)
                                for t, cols, parent, parent_cols in FOREIGN_KEYS],
        "schema.unique_constraints": [(t, cols, "u", None, None)
                                      for t, keys in UNIQUE_KEYS.items() for cols in keys],
    }
    for name, definitions in groups.items():
        tick = perf_counter()
        missing = invalid = 0
        for table, columns, kind, parent, parent_cols in definitions:
            candidates = [r for r in constraints if r["table_name"] == table
                          and r["kind"] == kind and tuple(r["columns"]) == columns]
            if not candidates:
                missing += 1
                continue
            def valid(row):
                backing_index = row["index_valid"] and row["index_ready"]
                if kind == "f":
                    return (row["validated"] and backing_index
                            and row["referenced_schema"] == schema
                            and row["referenced_table"] == parent
                            and tuple(row["referenced_columns"]) == parent_cols
                            and row["delete_action"] == "r" and row["update_action"] == "a")
                return row["validated"] and backing_index
            invalid += not any(valid(row) for row in candidates)
        results.append(compare(name, {"missing": 0, "invalid": 0},
                               {"missing": missing, "invalid": invalid},
                               execution_ms=(perf_counter() - tick) * 1000))
    tick = perf_counter()
    missing = invalid = 0
    for (table, name), columns in INDEXES.items():
        candidates = [r for r in indexes if r["table_name"] == table and r["index_name"] == name]
        if not candidates:
            missing += 1
        elif not any(tuple(r["columns"]) == columns and r["method"] == "btree"
                     and not r["is_unique"] and r["valid"] and r["ready"]
                     and r["unconditional_simple"] for r in candidates):
            invalid += 1
    results.append(compare("schema.indexes", {"missing": 0, "invalid": 0},
                           {"missing": missing, "invalid": invalid},
                           execution_ms=(perf_counter() - tick) * 1000))
    return results


def validate_metadata(connection, schema: str) -> list[ValidationResult]:
    tick = perf_counter()
    try:
        with connection.begin_nested():
            constraints = connection.execute(text(CONSTRAINT_SQL), {"schema": schema}).mappings().all()
            indexes = connection.execute(text(INDEX_SQL), {"schema": schema}).mappings().all()
        results = metadata_results(constraints, indexes, schema)
        # The first result includes shared catalog retrieval time.
        results[0] = ValidationResult(**{**results[0].__dict__,
                                        "execution_ms": (perf_counter() - tick) * 1000})
        return results
    except Exception:
        return [ValidationResult(name, "Accepted enforcement metadata", None, "FAIL",
                (perf_counter() - tick) * 1000,
                "Cannot inspect enforcement metadata; check PostgreSQL schema and catalog permissions.")
                for name in NAMES]

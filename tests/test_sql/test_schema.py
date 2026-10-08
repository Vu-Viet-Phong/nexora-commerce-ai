from pathlib import Path
import re


SCHEMA = Path(__file__).parents[2] / "sql" / "schema.sql"


def schema_text() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def test_required_tables_exist() -> None:
    sql = schema_text()
    for table in ("customers", "products", "invoices", "invoice_lines"):
        assert re.search(rf"CREATE TABLE {table}\s*\(", sql)


def test_expected_primary_keys_exist() -> None:
    sql = schema_text()
    assert "PRIMARY KEY (source_system, customer_id)" in sql
    assert "PRIMARY KEY (source_system, stock_code)" in sql
    assert "PRIMARY KEY (source_system, invoice_number)" in sql
    assert "line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY" in sql


def test_expected_foreign_keys_exist() -> None:
    sql = schema_text()
    assert "REFERENCES customers (source_system, customer_id)" in sql
    assert "REFERENCES invoices (source_system, invoice_number)" in sql
    assert "REFERENCES products (source_system, stock_code)" in sql


def test_customer_id_is_nullable_in_facts() -> None:
    sql = schema_text()
    invoices = sql.split("CREATE TABLE invoices", 1)[1].split(
        "CREATE TABLE invoice_lines", 1
    )[0]
    lines = sql.split("CREATE TABLE invoice_lines", 1)[1].split(
        "CREATE INDEX", 1
    )[0]
    assert re.search(r"\bcustomer_id BIGINT,\s*\n", invoices)
    assert re.search(r"\bcustomer_id BIGINT,\s*\n", lines)


def test_money_columns_use_numeric_not_float() -> None:
    sql = schema_text()
    assert "NUMERIC(12, 2)" in sql
    assert "NUMERIC(14, 2)" in sql
    assert "FLOAT" not in sql.upper()
    assert "DOUBLE PRECISION" not in sql.upper()
    assert "REAL" not in sql.upper()


def test_stable_invoice_line_identifier_and_indexes_exist() -> None:
    sql = schema_text()
    assert "source_line_key VARCHAR(128) NOT NULL" in sql
    assert "UNIQUE (source_system, source_line_key)" in sql
    assert "UNIQUE (source_system, source_sheet, source_row_number)" in sql
    for index_name in (
        "idx_invoices_customer",
        "idx_invoices_date",
        "idx_invoice_lines_invoice",
        "idx_invoice_lines_product",
        "idx_invoice_lines_customer",
        "idx_invoice_lines_date",
    ):
        assert f"CREATE INDEX {index_name}" in sql

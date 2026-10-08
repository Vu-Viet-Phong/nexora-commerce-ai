"""All writes here are to the explicitly opted-in Codex-owned sandbox."""
from decimal import Decimal
import json
import os
import subprocess
import sys

import pytest
from sqlalchemy import event, text

from src.data.load import LINE_COLUMNS
from src.quality.contracts import Check, qualified
from src.quality.engine import run_query, validate_database

pytestmark = pytest.mark.quality_postgres


def results(sandbox, **kwargs):
    report = validate_database(sandbox.engine, schema=sandbox.schema,
                               source_path=sandbox.source_path, **kwargs)
    return report, {r.name: r for r in report.results}


def mutate(sandbox, sql):
    with sandbox.engine.begin() as connection:
        connection.execute(text(sql))


def test_correct_fixture_all_core_and_source_checks_pass(quality_sandbox):
    report, checks = results(quality_sandbox)
    assert report.summary["FAIL"] == 0, report.to_json()
    assert checks["source.records"].status == "PASS"
    assert checks["source.monetary_aggregates"].actual["ledger"] == Decimal("8.00")
    assert checks["profile.allowed_missing_and_special_lines"].actual["guest_lines"] == 2
    assert checks["profile.allowed_missing_and_special_lines"].actual["retained_duplicate_lines"] == 2
    assert report.summary["SKIP"] == 3  # Marts are deferred.


@pytest.mark.parametrize("assignment,check", [
    ("is_cancellation = TRUE", "business.cancellation"),
    ("is_valid_sale = FALSE", "business.valid_sale"),
    ("is_inventory_adjustment = TRUE", "business.inventory_adjustment"),
    ("is_return = TRUE", "business.return"),
    ("is_non_product = TRUE", "business.non_product"),
    ("has_customer_id = FALSE", "business.customer_presence"),
    ("unit_price = -1", "business.price_flags"),
    ("quantity = 0", "business.valid_sale"),
])
def test_business_rule_violations_in_actual_sql(quality_sandbox, assignment, check):
    table = qualified(quality_sandbox.schema, "invoice_lines")
    mutate(quality_sandbox, f"UPDATE {table} SET {assignment} WHERE source_row_number = 1")
    report, checks = results(quality_sandbox)
    assert checks[check].status == "FAIL", report.to_json()
    assert checks["source.records"].actual["changed"] == 1


def test_invoice_and_customer_monetary_mismatch(quality_sandbox):
    invoices = qualified(quality_sandbox.schema, "invoices")
    customers = qualified(quality_sandbox.schema, "customers")
    mutate(quality_sandbox, f"UPDATE {invoices} SET total_invoice_amount = total_invoice_amount + 0.01")
    mutate(quality_sandbox, f"UPDATE {customers} SET total_merchandise_spend = total_merchandise_spend + 0.01")
    _, checks = results(quality_sandbox)
    assert checks["financial.invoice_ledger"].status == "FAIL"
    assert checks["financial.customer_merchandise"].status == "FAIL"


def test_same_count_replacement_detects_missing_extra_lines(quality_sandbox):
    table = qualified(quality_sandbox.schema, "invoice_lines")
    mutate(quality_sandbox, f"UPDATE {table} SET source_row_number = 99, "
                           "source_line_key = 'UCI:fixture:99' WHERE source_row_number = 1")
    _, checks = results(quality_sandbox)
    assert checks["source.row_counts"].status == "PASS"
    assert checks["source.records"].actual == {"missing": 1, "extra": 1, "changed": 0}


def test_missing_line_and_header_total_detected(quality_sandbox):
    table = qualified(quality_sandbox.schema, "invoice_lines")
    mutate(quality_sandbox, f"DELETE FROM {table} WHERE source_row_number = 1")
    _, checks = results(quality_sandbox)
    assert checks["source.row_counts"].status == "FAIL"
    assert checks["source.records"].actual["missing"] == 1
    assert checks["financial.invoice_ledger"].status == "FAIL"


def drop_constraints(sandbox, kind):
    table = qualified(sandbox.schema, "invoice_lines")
    with sandbox.engine.begin() as connection:
        names = connection.execute(text(
            "SELECT conname FROM pg_constraint WHERE conrelid = to_regclass(:table) AND contype = :kind"
        ), {"table": table, "kind": kind}).scalars().all()
        for name in names:
            quoted = connection.dialect.identifier_preparer.quote(name)
            connection.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {quoted}"))


def test_duplicate_invoice_line_and_position_detected(quality_sandbox):
    drop_constraints(quality_sandbox, "u")
    table = qualified(quality_sandbox.schema, "invoice_lines")
    columns = ", ".join(LINE_COLUMNS)
    mutate(quality_sandbox, f"INSERT INTO {table} ({columns}) "
                           f"SELECT {columns} FROM {table} WHERE source_row_number = 1")
    _, checks = results(quality_sandbox)
    assert checks["uniqueness.invoice_lines.grain"].actual == 1
    assert checks["uniqueness.invoice_lines.source_position"].actual == 1
    assert checks["source.records"].actual["extra"] == 1


def test_orphan_product_detected(quality_sandbox):
    drop_constraints(quality_sandbox, "f")
    table = qualified(quality_sandbox.schema, "invoice_lines")
    mutate(quality_sandbox, f"UPDATE {table} SET stock_code = 'MISSING' WHERE source_row_number = 1")
    _, checks = results(quality_sandbox)
    assert checks["integrity.invoice_lines.products"].actual == 1
    assert checks["integrity.join_fanout"].status == "FAIL"


def test_numeric_storage_drift_detected(quality_sandbox):
    table = qualified(quality_sandbox.schema, "customers")
    mutate(quality_sandbox, f"ALTER TABLE {table} ALTER COLUMN total_merchandise_spend TYPE double precision")
    _, checks = results(quality_sandbox)
    assert checks["financial.decimal_storage"].status == "FAIL"


def test_missing_schema_column_skips_business_queries(quality_sandbox):
    table = qualified(quality_sandbox.schema, "invoice_lines")
    mutate(quality_sandbox, f"ALTER TABLE {table} DROP COLUMN has_customer_id")
    _, checks = results(quality_sandbox)
    assert checks["schema.required_columns"].status == "FAIL"
    assert checks["business.customer_presence"].status == "SKIP"


def test_snapshot_queries_are_read_only_and_do_not_install_marts(quality_sandbox):
    statements = []

    def collect(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(quality_sandbox.engine, "before_cursor_execute", collect)
    try:
        report, _ = results(quality_sandbox)
    finally:
        event.remove(quality_sandbox.engine, "before_cursor_execute", collect)
    assert report.summary["FAIL"] == 0
    assert "SET TRANSACTION READ ONLY" in statements
    assert all(s.split()[0].upper() in ("SELECT", "SET", "SAVEPOINT", "RELEASE")
               for s in statements)
    assert not any("mart_daily_sales" in s for s in statements)


def test_bad_query_recovers_in_savepoint_and_sanitizes_errors(quality_sandbox):
    with quality_sandbox.engine.begin() as connection:
        connection.execute(text("SET TRANSACTION READ ONLY"))
        failed = run_query(connection, Check("missing", "SELECT unknown_private_column"), {})
        passed = run_query(connection, Check("next", "SELECT 0"), {})
    assert failed.status == "FAIL"
    assert passed.status == "PASS"
    assert "unknown_private_column" not in failed.failure_reason


def test_other_source_namespace_is_excluded(quality_sandbox):
    schema = quality_sandbox.schema
    # Clone parents before facts, using only deterministic fixture data.
    for table in ("customers", "products", "invoices", "invoice_lines"):
        from src.quality.contracts import TABLE_COLUMNS
        columns = [c for c in TABLE_COLUMNS[table] if c not in ("line_id", "line_total")]
        names = ", ".join(columns)
        expressions = ", ".join("'OTHER'" if c == "source_system" else c for c in columns)
        target = qualified(schema, table)
        mutate(quality_sandbox, f"INSERT INTO {target} ({names}) SELECT {expressions} FROM {target}")
    report, checks = results(quality_sandbox)
    assert report.summary["FAIL"] == 0, report.to_json()
    assert checks["source.row_counts"].actual["invoice_lines"] == 8


def test_unreadable_source_is_fail_not_silent_skip(quality_sandbox, tmp_path):
    report = validate_database(quality_sandbox.engine, schema=quality_sandbox.schema,
                               source_path=tmp_path / "not-present.parquet")
    checks = {r.name: r for r in report.results}
    assert checks["source.parquet"].status == "FAIL"
    assert checks["source.records"].status == "SKIP"
    assert "not-present.parquet" not in report.to_json()


@pytest.mark.quality_full_data
def test_opt_in_full_data_source_reconciliation(quality_sandbox):
    report, checks = results(quality_sandbox)
    source_results = [r for r in report.results if r.name.startswith("source.")]
    assert all(r.status == "PASS" for r in source_results), report.to_json()
    assert checks["source.row_counts"].actual["invoice_lines"] > 0


@pytest.mark.parametrize("corrupt", [False, True])
def test_cli_end_to_end_reports_and_exit_codes(quality_sandbox, tmp_path, corrupt):
    if corrupt:
        table = qualified(quality_sandbox.schema, "invoice_lines")
        mutate(quality_sandbox, f"UPDATE {table} SET is_valid_sale = FALSE WHERE source_row_number = 1")
    env = {**os.environ, "DATABASE_URL": os.environ["NEXORA_QUALITY_TEST_DATABASE_URL"]}
    completed = subprocess.run(
        [sys.executable, "-m", "src.quality", "--schema", quality_sandbox.schema,
         "--source", str(quality_sandbox.source_path),
         "--json-out", str(tmp_path / "quality.json"),
         "--markdown-out", str(tmp_path / "quality.md")],
        env=env, capture_output=True, text=True, check=False, timeout=30,
    )
    assert completed.returncode == (1 if corrupt else 0), completed.stdout
    report = json.loads(completed.stdout)
    assert report == json.loads((tmp_path / "quality.json").read_text(encoding="utf-8"))
    assert report["gate_summary"]["status"] == ("FAIL" if corrupt else "PASS")
    assert report["summary"]["SKIP"] == 3
    assert report["execution_ms"] > 0
    assert '"customer_id":' not in json.dumps([r["actual"] for r in report["results"]])
    assert "Relational core/source gate:" in (tmp_path / "quality.md").read_text(encoding="utf-8")


def test_raw_price_flags_survive_rounding_and_negative_zero(quality_sandbox, tmp_path):
    from src.data.load import load_source
    from .test_source import make_source, raw_row
    path = make_source(tmp_path, [raw_row("1", price=0.001), raw_row("2", price=-0.001)])
    load_source(os.environ["NEXORA_QUALITY_TEST_DATABASE_URL"], path, schema=quality_sandbox.schema)
    report, checks = results(quality_sandbox)
    assert checks["business.price_flags"].status == "PASS"
    assert checks["source.records"].status == "PASS", report.to_json()
    assert report.gate_summary["status"] == "PASS", report.to_json()

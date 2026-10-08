from contextlib import nullcontext
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from src.quality.contracts import (
    Check, MONEY_COLUMNS, NULLABLE, TABLE_COLUMNS, core_checks, qualified,
)
from src.quality.engine import run_query, schema_results, validate_database
from src.quality.results import QualityReport, ValidationResult, compare, skipped


def catalog():
    return [
        dict(table_name=table, column_name=col,
             is_nullable="YES" if col in NULLABLE[table] else "NO",
             data_type="numeric" if (table, col) in MONEY_COLUMNS else "text",
             numeric_precision=MONEY_COLUMNS.get((table, col)),
             numeric_scale=2 if (table, col) in MONEY_COLUMNS else None)
        for table, cols in TABLE_COLUMNS.items() for col in cols
    ]


def fake_engine(rows=None, failing=False):
    connection = MagicMock()
    connection.begin.return_value = nullcontext()
    connection.begin_nested.return_value = nullcontext()
    executed = []

    def execute(statement, params=None):
        sql = str(statement)
        executed.append((sql, params))
        result = MagicMock()
        result.scalar_one.return_value = 0
        if "information_schema.columns" in sql:
            result.mappings.return_value.all.return_value = catalog() if rows is None else rows
        if "guest_lines" in sql:
            result.mappings.return_value.one.return_value = {"guest_lines": 2}
        if failing and "COUNT(*)" in sql and "guest_lines" not in sql:
            raise RuntimeError("postgresql://secret:password@private/secret customer")
        return result

    connection.execute.side_effect = execute
    engine = MagicMock()
    engine.connect.return_value.execution_options.return_value.__enter__.return_value = connection
    return engine, executed


def test_comparison_pass_fail_and_decimal_tolerance():
    assert compare("count", 0, 0).status == "PASS"
    assert compare("count", 0, 2).status == "FAIL"
    assert compare("money", Decimal("0.30"), Decimal("0.31"),
                   tolerance=Decimal("0.01")).status == "PASS"
    assert compare("money", Decimal("0.30"), Decimal("0.32"),
                   tolerance=Decimal("0.01")).status == "FAIL"
    with pytest.raises(ValueError):
        compare("money", 0, 0, tolerance=Decimal("-1"))


def test_catalog_missing_columns_and_nullable_customer_contract():
    assert all(r.status == "PASS" for r in schema_results(catalog()))
    rows = [r for r in catalog() if not (r["table_name"] == "invoice_lines"
                                        and r["column_name"] == "stock_code")]
    assert schema_results(rows)[0].status == "FAIL"
    # NULL guests are allowed; turning the column into NOT NULL is contract drift.
    rows = catalog()
    next(r for r in rows if r["table_name"] == "invoices"
         and r["column_name"] == "customer_id")["is_nullable"] = "NO"
    assert schema_results(rows)[1].status == "FAIL"


@pytest.mark.parametrize("change,value", [
    ("data_type", "double precision"), ("numeric_scale", 3), ("numeric_precision", 10),
])
def test_numeric_contract_rejects_drift(change, value):
    rows = catalog()
    next(r for r in rows if r["table_name"] == "invoice_lines"
         and r["column_name"] == "unit_price")[change] = value
    assert schema_results(rows)[2].status == "FAIL"


@pytest.mark.parametrize("schema", ['public; DROP TABLE customers', 'a"b', "", "a.b"])
def test_schema_injection_is_rejected(schema):
    with pytest.raises(ValueError):
        qualified(schema, "invoice_lines")


def test_queries_cover_core_contract_and_bind_namespace():
    checks = core_checks("quality_test")
    assert len({c.name for c in checks}) == len(checks)
    names = {c.name for c in checks}
    assert {"uniqueness.invoice_lines.source_position", "business.valid_sale",
            "integrity.invoice_lines.products", "financial.invoice_ledger",
            "financial.customer_merchandise"} <= names
    for check in checks:
        assert check.sql.startswith("SELECT ")
        assert ":source" in check.sql
        assert "mart_" not in check.sql


def test_query_errors_are_safe_and_savepoint_is_used():
    connection = MagicMock()
    connection.begin_nested.return_value = nullcontext()
    connection.execute.side_effect = RuntimeError("DATABASE_URL=secret customer 12345")
    result = run_query(connection, Check("broken", "SELECT 1"), {})
    assert result.status == "FAIL"
    assert result.execution_ms >= 0
    assert "secret" not in result.failure_reason
    assert "12345" not in result.failure_reason
    connection.begin_nested.assert_called_once()


def test_runner_uses_read_only_snapshot_and_never_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "this must never be used")
    engine, executed = fake_engine()
    report = validate_database(engine, source_system="OTHER")
    assert executed[0][0] == "SET TRANSACTION READ ONLY"
    assert report.summary["FAIL"] == 0
    assert len([r for r in report.results if r.name.startswith("marts.")]) == 3
    assert all(r.status == "SKIP" for r in report.results if r.name.startswith("marts."))
    assert report.summary["status"] == "SKIP"
    engine.connect.return_value.execution_options.assert_called_once_with(
        isolation_level="REPEATABLE READ"
    )
    for sql, params in executed:
        if ":source" in sql:
            assert params["source"] == "OTHER"
            assert "OTHER" not in sql


def test_missing_core_schema_skips_dependent_checks():
    engine, executed = fake_engine(rows=[])
    report = validate_database(engine)
    assert report.summary["FAIL"] >= 1
    assert not any('FROM "public"."invoice_lines"' in sql for sql, _ in executed)
    assert any(r.status == "SKIP" for r in report.results if r.name.startswith("business."))


def test_runner_continues_after_individual_query_failure():
    engine, _ = fake_engine(failing=True)
    report = validate_database(engine)
    assert len([r for r in report.results if r.name.startswith("business.")]) >= 10
    assert report.summary["FAIL"] >= 10
    assert "password" not in report.to_json()


def test_report_decimals_and_skip_are_not_false_pass(tmp_path):
    report = QualityReport("UCI", "public", [
        compare("ledger", Decimal("1.00"), Decimal("1.01")),
        skipped("marts.test", "Pending 2.4"),
    ])
    assert report.summary["status"] == "FAIL"
    assert '"1.01"' in report.to_json()
    report.write(tmp_path / "report.json")
    report.write(tmp_path / "report.md", markdown=True)
    assert "FAIL" in (tmp_path / "report.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        ValidationResult("x", None, None, "UNKNOWN")


@pytest.mark.parametrize("kwargs", [
    {"source_system": ""}, {"source_system": "x" * 33}, {"statement_timeout_ms": 0},
])
def test_invalid_options_fail_before_connection(kwargs):
    engine = MagicMock()
    with pytest.raises(ValueError):
        validate_database(engine, **kwargs)
    engine.connect.assert_not_called()

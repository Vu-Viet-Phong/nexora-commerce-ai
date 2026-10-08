"""Run core checks in one PostgreSQL read-only, repeatable-read snapshot."""
from __future__ import annotations

from time import perf_counter

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .contracts import (
    MONEY_COLUMNS, NULLABLE, TABLE_COLUMNS, MARTS, core_checks, parameters, qualified,
)
from .results import QualityReport, ValidationResult, compare, skipped


def schema_results(rows: list[dict]) -> list[ValidationResult]:
    """Inspect catalog aggregates without exposing database records."""
    indexed = {(r["table_name"], r["column_name"]): r for r in rows}
    missing = [f"{t}.{c}" for t, cols in TABLE_COLUMNS.items() for c in cols
               if (t, c) not in indexed]
    nullability_errors = sum(
        r["is_nullable"] != ("YES" if col in NULLABLE[table] else "NO")
        for (table, col), r in indexed.items()
        if table in TABLE_COLUMNS and col in TABLE_COLUMNS[table]
    )
    money_errors = sum(
        key not in indexed or indexed[key]["data_type"] != "numeric"
        or indexed[key]["numeric_precision"] != precision
        or indexed[key]["numeric_scale"] != 2
        for key, precision in MONEY_COLUMNS.items()
    )
    return [
        compare("schema.required_columns", [], missing),
        compare("schema.nullability", 0, nullability_errors),
        compare("financial.decimal_storage", 0, money_errors),
    ]


def run_query(connection, check, params: dict) -> ValidationResult:
    """Savepoint recovery keeps a failed SELECT from aborting later checks."""
    started = perf_counter()
    try:
        with connection.begin_nested():
            actual = connection.execute(text(check.sql), params).scalar_one()
        return compare(check.name, check.expected, actual,
                       execution_ms=(perf_counter() - started) * 1000)
    except Exception:
        # SQLAlchemy errors can embed URLs, parameters and source values.
        return ValidationResult(
            check.name, check.expected, None, "FAIL",
            (perf_counter() - started) * 1000,
            "Read-only query failed; check schema, permissions and PostgreSQL availability.",
        )


def validate_database(
    engine: Engine, *, source_system: str = "UCI", schema: str = "public",
    source_path=None, statement_timeout_ms: int = 120_000,
) -> QualityReport:
    """No DDL, DML, loader invocation or .env access; caller owns the engine."""
    qualified(schema, "invoice_lines")
    if not source_system or len(source_system) > 32:
        raise ValueError("source_system must contain 1–32 characters")
    if statement_timeout_ms <= 0:
        raise ValueError("statement_timeout_ms must be positive")
    started = perf_counter()
    report = QualityReport(source_system, schema)
    checks = core_checks(schema)
    try:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": str(statement_timeout_ms)},
                )
                tick = perf_counter()
                rows = connection.execute(text(
                    "SELECT table_name, column_name, is_nullable, data_type, "
                    "numeric_precision, numeric_scale FROM information_schema.columns "
                    "WHERE table_schema = :schema AND table_name IN "
                    "('customers', 'products', 'invoices', 'invoice_lines')"
                ), {"schema": schema}).mappings().all()
                catalog = schema_results(rows)
                catalog[0] = ValidationResult(
                    **{**catalog[0].__dict__, "execution_ms": (perf_counter() - tick) * 1000}
                )
                report.results.extend(catalog)
                if catalog[0].status == "FAIL":
                    report.results.extend(skipped(check.name, "Required core columns are missing.")
                                          for check in checks)
                    report.results.append(skipped("source.reconciliation", "Core schema is incomplete."))
                else:
                    params = parameters(source_system)
                    report.results.append(run_query(connection, type(checks[0])(
                        "completeness.source_population",
                        f"SELECT CASE WHEN COUNT(*) > 0 THEN 0 ELSE 1 END FROM "
                        f"{qualified(schema, 'invoice_lines')} WHERE source_system = :source",
                    ), params))
                    report.results.extend(run_query(connection, check, params) for check in checks)
                    # Informational profiles are PASS because NULL guests and flagged
                    # special transactions are allowed; flags are checked separately.
                    tick = perf_counter()
                    with connection.begin_nested():
                        profile = dict(connection.execute(text(
                            "SELECT COUNT(*) FILTER (WHERE customer_id IS NULL) guest_lines, "
                            "COUNT(*) FILTER (WHERE description IS NULL) missing_descriptions, "
                            "COUNT(*) FILTER (WHERE is_duplicate_within_sheet) retained_duplicate_lines, "
                            "COUNT(*) FILTER (WHERE quantity = 0) zero_quantity_lines, "
                            "COUNT(*) FILTER (WHERE is_price_zero) zero_price_lines, "
                            "COUNT(*) FILTER (WHERE is_price_negative) negative_price_lines "
                            f"FROM {qualified(schema, 'invoice_lines')} WHERE source_system = :source"
                        ), params).mappings().one())
                    report.results.append(ValidationResult(
                        "profile.allowed_missing_and_special_lines",
                        "Informational counts; no invented rejection threshold.",
                        profile, "PASS", (perf_counter() - tick) * 1000,
                    ))
                    if source_path is None:
                        report.results.append(skipped("source.reconciliation", "No Parquet source supplied."))
                    elif source_system != "UCI":
                        report.results.append(skipped(
                            "source.reconciliation", "Existing Parquet loader contract supports UCI only."
                        ))
                    else:
                        from .source import reconcile_source
                        report.results.extend(reconcile_source(connection, source_path, schema))
    except Exception:
        report.results.append(ValidationResult(
            "database.execution", "Read-only snapshot completed", None, "FAIL",
            failure_reason="Database validation could not complete; check connection, schema and permissions.",
        ))
    report.results.extend(skipped(
        f"marts.{mart}", "Deferred until Milestone 2.4 integration and approval."
    ) for mart in MARTS)
    report.execution_ms = (perf_counter() - started) * 1000
    return report

"""CLI: python -m src.quality; configuration comes only from process environment."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from .contracts import qualified
from .engine import validate_database
from .results import QualityReport, ValidationResult


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only PostgreSQL data quality validation")
    parser.add_argument("--schema", default="public")
    parser.add_argument("--source-system", default="UCI")
    parser.add_argument("--source", type=Path, default=None,
                        help="Optional immutable processed Parquet; enables exact source reconciliation.")
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--markdown-out", type=Path, default=None)
    parser.add_argument("--statement-timeout-ms", type=int, default=120_000)
    args = parser.parse_args(argv)
    try:
        qualified(args.schema, "invoice_lines")
        if not args.source_system or len(args.source_system) > 32:
            raise ValueError("source_system must contain 1–32 characters")
        if args.statement_timeout_ms <= 0:
            raise ValueError("statement-timeout-ms must be positive")
        if args.json_out and args.markdown_out and args.json_out.resolve() == args.markdown_out.resolve():
            raise ValueError("JSON and Markdown output paths must differ")
    except ValueError as error:
        parser.error(str(error))
    report = QualityReport(args.source_system, args.schema)
    engine = None
    try:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            report.results.append(ValidationResult(
                "database.configuration", "DATABASE_URL supplied in process environment", None, "FAIL",
                failure_reason="DATABASE_URL is not configured. Supply it through your secret manager.",
            ))
        else:
            url = make_url(database_url)
            if url.get_backend_name() != "postgresql":
                raise ValueError("PostgreSQL is required")
            url = url.set(drivername="postgresql+psycopg")
            engine = create_engine(url, hide_parameters=True, pool_pre_ping=True,
                                   connect_args={"connect_timeout": 10})
            report = validate_database(
                engine, source_system=args.source_system, schema=args.schema,
                source_path=args.source, statement_timeout_ms=args.statement_timeout_ms,
            )
    except Exception:
        report.results.append(ValidationResult(
            "database.connection", "Valid PostgreSQL process configuration", None, "FAIL",
            failure_reason="Cannot configure PostgreSQL connection; verify DATABASE_URL and installed dependencies.",
        ))
    finally:
        if engine is not None:
            engine.dispose()
    try:
        if args.json_out:
            report.write(args.json_out)
        if args.markdown_out:
            report.write(args.markdown_out, markdown=True)
    except OSError:
        report.results.append(ValidationResult(
            "report.output", "Report files written", None, "FAIL",
            failure_reason="Cannot write report files; verify destination and filesystem permissions.",
        ))
        # If JSON succeeded before Markdown failed, update its gate state.
        if args.json_out:
            try:
                report.write(args.json_out)
            except OSError:
                pass
    print(report.to_json())
    return {"PASS": 0, "FAIL": 1, "SKIP": 2}[report.gate_summary["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

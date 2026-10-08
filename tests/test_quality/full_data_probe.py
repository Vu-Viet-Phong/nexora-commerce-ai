"""Opt-in full-data experiment in a Codex-owned PostgreSQL sandbox.

Run this module explicitly; pytest does not collect it. No .env access and no
credentials/raw rows in outputs. Windows native counters measure this Python
process's lifetime peak working set/commit, not PostgreSQL server memory.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from decimal import Decimal
import json
import os
from pathlib import Path
from time import perf_counter

import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.data.load import load_source
from src.quality.contracts import qualified
from src.quality.engine import validate_database
from src.quality.source import file_sha256


def peak_memory() -> dict:
    if os.name != "nt":
        return {"method": "unavailable", "peak_working_set_bytes": None,
                "peak_commit_bytes": None}

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
            )
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    ctypes.windll.kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get_memory.restype = wintypes.BOOL
    if not get_memory(ctypes.windll.kernel32.GetCurrentProcess(),
                      ctypes.byref(counters), counters.cb):
        raise RuntimeError("Native memory measurement unavailable")
    return {"method": "Windows GetProcessMemoryInfo lifetime high-water marks",
            "peak_working_set_bytes": counters.PeakWorkingSetSize,
            "peak_commit_bytes": counters.PeakPagefileUsage}


def financial_diagnostics(engine, schema: str, source: Path) -> dict:
    lines, invoices, customers = (qualified(schema, table)
                                   for table in ("invoice_lines", "invoices", "customers"))
    with engine.connect() as connection:
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            result = {}
            for label, sql in {
                "invoices": f"""SELECT COUNT(*) FILTER (WHERE delta <> 0) mismatched_groups,
                    COALESCE(SUM(delta), 0) signed_delta, COALESCE(SUM(ABS(delta)), 0) absolute_delta,
                    COALESCE(MAX(ABS(delta)), 0) maximum_absolute_delta
                    FROM (SELECT i.total_invoice_amount - SUM(l.line_total) delta
                    FROM {invoices} i JOIN {lines} l USING (source_system, invoice_number)
                    WHERE i.source_system = :source GROUP BY i.invoice_number, i.total_invoice_amount) d""",
                "customers": f"""SELECT COUNT(*) FILTER (WHERE delta <> 0) mismatched_groups,
                    COALESCE(SUM(delta), 0) signed_delta, COALESCE(SUM(ABS(delta)), 0) absolute_delta,
                    COALESCE(MAX(ABS(delta)), 0) maximum_absolute_delta
                    FROM (SELECT c.total_merchandise_spend -
                    (COALESCE(SUM(l.line_total) FILTER (WHERE l.is_valid_sale), 0) +
                    COALESCE(SUM(l.line_total) FILTER (WHERE l.is_cancellation AND NOT l.is_non_product), 0)) delta
                    FROM {customers} c JOIN {lines} l USING (source_system, customer_id)
                    WHERE c.source_system = :source GROUP BY c.customer_id, c.total_merchandise_spend) d""",
            }.items():
                result[label] = dict(connection.execute(text(sql), {"source": "UCI"}).mappings().one())
            result["database_ledger"] = connection.execute(text(
                f"SELECT SUM(line_total) FROM {lines} WHERE source_system = :source"
            ), {"source": "UCI"}).scalar_one()
    raw_total = round(pd.read_parquet(source, columns=["line_total"])["line_total"].sum(), 2)
    result["parquet_pre_rounding_ledger"] = Decimal(str(raw_total))
    result["database_minus_pre_rounding_source"] = (
        result["database_ledger"] - result["parquet_pre_rounding_ledger"]
    )
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("load", "validate"), required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    qualified(args.schema, "invoice_lines")
    if not args.schema.startswith("codex_quality_full_"):
        parser.error("schema must use the codex_quality_full_ ownership prefix")
    url = make_url(os.environ["NEXORA_QUALITY_TEST_DATABASE_URL"])
    if url.get_backend_name() != "postgresql" or url.database != "nexora_quality_codex_test":
        parser.error("requires the dedicated nexora_quality_codex_test database")
    url = url.set(drivername="postgresql+psycopg")
    parquet = pq.ParquetFile(args.source)
    if parquet.metadata.num_rows != 1_044_848:
        parser.error("full-data experiment requires exactly 1,044,848 source rows")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    before = file_sha256(args.source)
    started = perf_counter()
    engine = create_engine(url, hide_parameters=True)
    metrics = {"phase": args.phase, "source_rows": parquet.metadata.num_rows,
               "source_sha256": before, "schema": args.schema}
    exit_code = 0
    try:
        if args.phase == "load":
            with engine.begin() as connection:
                assert connection.execute(text("SELECT current_database()")).scalar_one() == url.database
                # CREATE without IF NOT EXISTS refuses to overwrite an existing schema.
                connection.execute(text(f'CREATE SCHEMA "{args.schema}"'))
                connection.execute(text(f'SET LOCAL search_path TO "{args.schema}"'))
                ddl = (Path(__file__).parents[2] / "sql/schema.sql").read_text(encoding="utf-8")
                connection.exec_driver_sql(ddl.replace("BEGIN;", "").replace("COMMIT;", ""))
            print("Loading full source into the private sandbox.", flush=True)
            metrics["loaded"] = load_source(url.render_as_string(hide_password=False),
                                            args.source, schema=args.schema)
        else:
            print("Validating full source in a read-only snapshot.", flush=True)
            report = validate_database(engine, schema=args.schema, source_path=args.source)
            report.write(args.output_dir / "full-data-report.json")
            report.write(args.output_dir / "full-data-report.md", markdown=True)
            metrics["summary"] = report.summary
            metrics["gate_summary"] = report.gate_summary
            metrics["validation_ms"] = report.execution_ms
            metrics["financial_diagnostics"] = financial_diagnostics(engine, args.schema, args.source)
            exit_code = {"PASS": 0, "FAIL": 1, "SKIP": 2}[report.gate_summary["status"]]
        metrics["source_unchanged"] = before == file_sha256(args.source)
        if not metrics["source_unchanged"]:
            exit_code = 1
    except Exception:
        metrics["execution_error"] = "Experiment failed; no raw exception/parameters are logged."
        exit_code = 1
    finally:
        engine.dispose()
    metrics["phase_wall_seconds"] = perf_counter() - started
    metrics["memory"] = peak_memory()
    metrics["exit_code"] = exit_code
    output = json.dumps(metrics, indent=2,
                        default=lambda value: format(value, "f") if isinstance(value, Decimal) else str(value))
    (args.output_dir / f"{args.phase}-metrics.json").write_text(output, encoding="utf-8")
    print(output)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

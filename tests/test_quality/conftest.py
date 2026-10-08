"""Dedicated quality fixtures: no .env loading and no shared test database."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.data.load import load_source
from .test_source import make_source


def pytest_addoption(parser):
    parser.addoption("--quality-postgres", action="store_true", default=False,
                     help="Run quality tests on an explicitly configured Codex-owned database.")
    parser.addoption("--quality-full-data", action="store_true", default=False,
                     help="Also run full-data quality checks; requires --quality-postgres.")


def pytest_configure(config):
    config.addinivalue_line("markers", "quality_postgres: isolated PostgreSQL integration")
    config.addinivalue_line("markers", "quality_full_data: opt-in complete Parquet reconciliation")
    if config.getoption("--quality-full-data") and not config.getoption("--quality-postgres"):
        raise pytest.UsageError("--quality-full-data requires --quality-postgres")


def pytest_collection_modifyitems(config, items):
    for item in items:
        if "quality_full_data" in item.keywords and not config.getoption("--quality-full-data"):
            item.add_marker(pytest.mark.skip(reason="requires --quality-full-data"))
        elif "quality_postgres" in item.keywords and not config.getoption("--quality-postgres"):
            item.add_marker(pytest.mark.skip(reason="requires --quality-postgres"))


@dataclass
class QualitySandbox:
    engine: object
    schema: str
    source_path: Path


@pytest.fixture
def quality_sandbox(tmp_path, request):
    url = os.getenv("NEXORA_QUALITY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NEXORA_QUALITY_TEST_DATABASE_URL is not configured")
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql" or parsed.database != "nexora_quality_codex_test":
        raise pytest.UsageError("Quality integration requires dedicated database nexora_quality_codex_test")
    if request.node.get_closest_marker("quality_full_data"):
        source = os.getenv("NEXORA_QUALITY_SOURCE")
        if not source:
            pytest.skip("NEXORA_QUALITY_SOURCE is not configured")
        source_path = Path(source)
    else:
        source_path = make_source(tmp_path)
    engine = create_engine(url, hide_parameters=True)
    schema = f"codex_quality_{uuid.uuid4().hex}"
    created = False
    try:
        with engine.begin() as connection:
            if connection.execute(text("SELECT current_database()")).scalar_one() != parsed.database:
                raise pytest.UsageError("Connected database identity does not match the quality sandbox")
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            ddl = (Path(__file__).parents[2] / "sql/schema.sql").read_text(encoding="utf-8")
            # Keep atomic ownership in engine.begin(), stripping only DDL transaction wrappers.
            ddl = ddl.replace("BEGIN;", "").replace("COMMIT;", "")
            connection.exec_driver_sql(ddl)
        load_source(url, source_path, schema=schema)
        yield QualitySandbox(engine, schema, source_path)
    finally:
        if created:
            with engine.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()

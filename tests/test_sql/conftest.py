import os
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import create_engine, text

from src.data.load import load_local_env, normalize_database_url


load_local_env()
DATABASE_URL = os.getenv("NEXORA_TEST_DATABASE_URL")


def pytest_addoption(parser) -> None:
    parser.addoption(
        "--run-full-data",
        action="store_true",
        default=False,
        help="Run tests that load and reconcile the complete processed dataset.",
    )


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "full_data: loads the complete processed dataset and is opt-in",
    )


def pytest_collection_modifyitems(config, items) -> None:
    if config.getoption("--run-full-data"):
        return
    skip = pytest.mark.skip(reason="requires --run-full-data")
    for item in items:
        if "full_data" in item.keywords:
            item.add_marker(skip)


@dataclass
class DatabaseSandbox:
    engine: object
    schema: str
    database_url: str

    def set_search_path(self, connection) -> None:
        connection.execute(text(f'SET search_path TO "{self.schema}"'))


@pytest.fixture
def database_sandbox():
    if not DATABASE_URL:
        pytest.skip("NEXORA_TEST_DATABASE_URL is not configured")
    engine = create_engine(normalize_database_url(DATABASE_URL), pool_pre_ping=True)
    schema = f"test_{uuid.uuid4().hex}"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    sandbox = DatabaseSandbox(
        engine=engine,
        schema=schema,
        database_url=normalize_database_url(DATABASE_URL),
    )
    try:
        yield sandbox
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        engine.dispose()

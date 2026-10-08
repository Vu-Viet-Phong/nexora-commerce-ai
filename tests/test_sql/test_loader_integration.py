from decimal import Decimal
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from src.data.load import load_local_env, load_source, normalize_database_url


load_local_env()
DATABASE_URL = os.getenv("NEXORA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="NEXORA_TEST_DATABASE_URL is not configured",
)

ROOT = Path(__file__).parents[2]
SCHEMA = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")


def apply_clean_schema(connection) -> None:
    connection.execute(
        text(
            "DROP TABLE IF EXISTS invoice_lines, invoices, products, "
            "customers CASCADE"
        )
    )
    for statement in SCHEMA.split(";"):
        if statement.strip():
            connection.execute(text(statement))


def table_counts(connection) -> tuple[int, ...]:
    return tuple(
        connection.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE source_system = 'UCI'")
        ).scalar_one()
        for table in ("customers", "products", "invoices", "invoice_lines")
    )


def test_loader_reconciles_and_is_idempotent() -> None:
    engine = create_engine(normalize_database_url(DATABASE_URL))
    with engine.begin() as connection:
        apply_clean_schema(connection)

    first = load_source(DATABASE_URL)
    assert first["customers"] == 5_942
    assert first["products"] == 5_131
    assert first["invoices"] == 53_628
    assert first["invoice_lines"] == 1_044_848

    with engine.connect() as connection:
        counts_after_first = table_counts(connection)
        assert counts_after_first == (5_942, 5_131, 53_628, 1_044_848)
        assert connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM invoice_lines
                WHERE source_system = 'UCI' AND customer_id IS NULL
                """
            )
        ).scalar_one() == 235_287
        assert connection.execute(
            text(
                """
                SELECT SUM(line_total)
                FROM invoice_lines
                WHERE source_system = 'UCI' AND is_valid_sale
                """
            )
        ).scalar_one() == Decimal("19700954.44")
        assert connection.execute(
            text(
                """
                SELECT SUM(line_total)
                FROM invoice_lines
                WHERE source_system = 'UCI'
                  AND is_cancellation AND NOT is_non_product
                """
            )
        ).scalar_one() == Decimal("-719692.94")

    second = load_source(DATABASE_URL)
    assert second == first
    with engine.connect() as connection:
        assert table_counts(connection) == counts_after_first

        with pytest.raises(RuntimeError, match="intentional loader failure"):
            load_source(DATABASE_URL, fail_after="copy")
        assert table_counts(connection) == counts_after_first

    engine.dispose()

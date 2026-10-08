from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from src.data.load import load_source

ROOT = Path(__file__).parents[2]
SCHEMA = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")


def table_counts(connection) -> tuple[int, ...]:
    return tuple(
        connection.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE source_system = 'UCI'")
        ).scalar_one()
        for table in ("customers", "products", "invoices", "invoice_lines")
    )


@pytest.mark.full_data
def test_loader_reconciles_and_is_idempotent(database_sandbox) -> None:
    engine = database_sandbox.engine
    with engine.begin() as connection:
        database_sandbox.set_search_path(connection)
        for statement in SCHEMA.split(";"):
            if statement.strip():
                connection.execute(text(statement))

    first = load_source(
        database_sandbox.database_url,
        schema=database_sandbox.schema,
    )
    assert first["customers"] == 5_942
    assert first["products"] == 5_131
    assert first["invoices"] == 53_628
    assert first["invoice_lines"] == 1_044_848

    with engine.connect() as connection:
        database_sandbox.set_search_path(connection)
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

    second = load_source(
        database_sandbox.database_url,
        schema=database_sandbox.schema,
    )
    assert second == first
    with engine.connect() as connection:
        database_sandbox.set_search_path(connection)
        assert table_counts(connection) == counts_after_first

        with pytest.raises(RuntimeError, match="intentional loader failure"):
            load_source(
                database_sandbox.database_url,
                fail_after="copy",
                schema=database_sandbox.schema,
            )
        assert table_counts(connection) == counts_after_first

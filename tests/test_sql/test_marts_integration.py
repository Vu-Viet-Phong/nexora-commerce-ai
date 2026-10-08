from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from src.data.load import load_source

ROOT = Path(__file__).parents[2]
MART_FILES = (
    ROOT / "sql" / "marts" / "mart_daily_sales.sql",
    ROOT / "sql" / "marts" / "mart_customer_daily.sql",
    ROOT / "sql" / "marts" / "mart_customer_snapshot.sql",
)


def install_marts(connection) -> None:
    for path in MART_FILES:
        connection.execute(text(path.read_text(encoding="utf-8")))


@pytest.mark.full_data
def test_marts_reconcile_grain_and_rfm(database_sandbox) -> None:
    engine = database_sandbox.engine
    with engine.begin() as connection:
        database_sandbox.set_search_path(connection)
        schema = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
        for statement in schema.split(";"):
            if statement.strip():
                connection.execute(text(statement))
    load_source(
        database_sandbox.database_url,
        schema=database_sandbox.schema,
    )
    with engine.begin() as connection:
        database_sandbox.set_search_path(connection)
        install_marts(connection)

    with engine.connect() as connection:
        database_sandbox.set_search_path(connection)
        assert connection.execute(
            text("SELECT COUNT(*) FROM mart_customer_snapshot")
        ).scalar_one() == 5_942

        duplicate_daily_sales = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT calendar_day, country, is_physical_merchandise
                    FROM mart_daily_sales
                    GROUP BY calendar_day, country, is_physical_merchandise
                    HAVING COUNT(*) > 1
                ) AS duplicates
                """
            )
        ).scalar_one()
        assert duplicate_daily_sales == 0

        duplicate_customer_daily = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT customer_id, calendar_day
                    FROM mart_customer_daily
                    GROUP BY customer_id, calendar_day
                    HAVING COUNT(*) > 1
                ) AS duplicates
                """
            )
        ).scalar_one()
        assert duplicate_customer_daily == 0

        joined_fact_totals = connection.execute(
            text(
                """
                SELECT COUNT(*), SUM(l.line_total)
                FROM invoice_lines AS l
                JOIN invoices AS i
                  ON i.source_system = l.source_system
                 AND i.invoice_number = l.invoice_number
                JOIN products AS p
                  ON p.source_system = l.source_system
                 AND p.stock_code = l.stock_code
                WHERE l.source_system = 'UCI'
                """
            )
        ).one()
        assert joined_fact_totals[0] == 1_044_848
        assert joined_fact_totals[1] == Decimal("18909762.10")

        daily_totals = connection.execute(
            text(
                """
                SELECT
                    SUM(gross_sales),
                    SUM(valid_sales_revenue),
                    SUM(return_value),
                    SUM(net_sales),
                    SUM(distinct_invoices),
                    SUM(units_sold),
                    SUM(units_returned)
                FROM mart_daily_sales
                """
            )
        ).one()
        assert daily_totals[0] == Decimal("19700954.44")
        assert daily_totals[1] == Decimal("19700954.44")
        assert daily_totals[2] == Decimal("-719692.94")
        assert daily_totals[3] == Decimal("18981261.50")
        assert daily_totals[4] == 39_516
        assert daily_totals[5] == 11_221_957
        assert daily_totals[6] == 469_882

        assert connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM mart_daily_sales
                WHERE net_sales <> gross_sales + return_value
                """
            )
        ).scalar_one() == 0

        customer_totals = connection.execute(
            text(
                """
                SELECT SUM(gross_spend), SUM(return_value), SUM(net_spend)
                FROM mart_customer_daily
                """
            )
        ).one()
        assert customer_totals[0] == Decimal("17124940.98")
        assert customer_totals[1] == Decimal("-713046.25")
        assert customer_totals[2] == Decimal("16411894.73")
        assert connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM mart_customer_daily
                WHERE net_spend <> gross_spend + return_value
                """
            )
        ).scalar_one() == 0

        snapshot = connection.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE frequency > 0),
                    COUNT(*) FILTER (WHERE frequency = 0),
                    SUM(monetary),
                    MIN(recency_days),
                    MAX(recency_days),
                    AVG(average_order_value)
                FROM mart_customer_snapshot
                """
            )
        ).one()
        assert snapshot[0] == 5_852
        assert snapshot[1] == 90
        assert snapshot[2] == Decimal("16411894.73")
        assert snapshot[3] >= 0
        assert snapshot[4] >= snapshot[3]
        assert snapshot[5] > 0
        assert connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM mart_customer_snapshot
                WHERE frequency = 0
                  AND average_order_value IS NOT NULL
                """
            )
        ).scalar_one() == 0

        view_numeric_types = connection.execute(
            text(
                """
                SELECT
                    pg_typeof(gross_sales)::text,
                    pg_typeof(return_value)::text,
                    pg_typeof(net_sales)::text
                FROM mart_daily_sales
                LIMIT 1
                """
            )
        ).one()
        assert view_numeric_types == ("numeric", "numeric", "numeric")

    engine.dispose()

import os
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from src.data.load import load_local_env, normalize_database_url


load_local_env()
DATABASE_URL = os.getenv("NEXORA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="NEXORA_TEST_DATABASE_URL is not configured",
)

ROOT = Path(__file__).parents[2]
MART_FILES = (
    ROOT / "sql" / "marts" / "mart_daily_sales.sql",
    ROOT / "sql" / "marts" / "mart_customer_daily.sql",
    ROOT / "sql" / "marts" / "mart_customer_snapshot.sql",
)


def install_marts(connection) -> None:
    for path in MART_FILES:
        connection.execute(text(path.read_text(encoding="utf-8")))


def test_marts_reconcile_grain_and_rfm() -> None:
    engine = create_engine(normalize_database_url(DATABASE_URL))
    with engine.begin() as connection:
        install_marts(connection)

    with engine.connect() as connection:
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

    engine.dispose()

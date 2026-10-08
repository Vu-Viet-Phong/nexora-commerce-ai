"""Unit and contract tests for Analytics Dashboard query layer and logic.

Tests execute fast in-memory using SQLite and mocks to avoid
interfering with shared databases or external services.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from app.queries import (
    DatabaseQueryError,
    calculate_country_shares,
    compute_customer_distributions,
    compute_rfm_segments,
    get_available_countries,
    get_customer_daily_trend,
    get_customer_kpis,
    get_date_range,
    get_daily_sales_trend,
    get_engine,
    get_merchandise_breakdown,
    get_rfm_snapshot,
    get_sales_by_country,
    get_sales_kpis,
    get_top_customers,
    load_env_config,
    normalize_db_url,
    resample_sales_trend,
    summarize_rfm_segments,
)


# ============================================================================
# CONFIGURATION & UTILITY TESTS
# ============================================================================

def test_normalize_db_url_encodes_special_password():
    raw_url = "postgresql+psycopg://nexora_app:p@ss#word!@localhost:5432/nexora_commerce"
    normalized = normalize_db_url(raw_url)
    assert "@localhost:5432/nexora_commerce" in normalized
    assert "p%40ss%23word%21" in normalized


def test_normalize_db_url_leaves_standard_url_untouched():
    raw_url = "postgresql+psycopg://user:simplepass@remotehost:5432/db"
    assert normalize_db_url(raw_url) == raw_url


def test_load_env_config_reads_custom_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("TEST_NEXORA_VAR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_NEXORA_VAR=active_secret\n# Comment\nINVALID_LINE", encoding="utf-8")

    load_env_config(env_file)
    import os
    assert os.getenv("TEST_NEXORA_VAR") == "active_secret"


def test_get_engine_missing_url_raises(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("NEXORA_DATABASE_URL", raising=False)
    with pytest.raises(DatabaseQueryError, match="Database URL not configured"):
        get_engine(database_url=None, load_env=False)


# ============================================================================
# IN-MEMORY SQLITE FIXTURE FOR QUERY LAYER
# ============================================================================

@pytest.fixture
def sqlite_engine():
    """Create in-memory SQLite engine mimicking PostgreSQL Mart views."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE mart_daily_sales (
                    calendar_day DATE,
                    country TEXT,
                    is_physical_merchandise BOOLEAN,
                    gross_sales NUMERIC(14, 2),
                    valid_sales_revenue NUMERIC(14, 2),
                    return_value NUMERIC(14, 2),
                    net_sales NUMERIC(14, 2),
                    distinct_invoices BIGINT,
                    units_sold BIGINT,
                    units_returned BIGINT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE mart_customer_daily (
                    customer_id BIGINT,
                    calendar_day DATE,
                    order_frequency BIGINT,
                    gross_spend NUMERIC(14, 2),
                    return_value NUMERIC(14, 2),
                    net_spend NUMERIC(14, 2),
                    valid_transaction_count BIGINT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE mart_customer_snapshot (
                    customer_id BIGINT,
                    primary_country TEXT,
                    recency_days BIGINT,
                    frequency BIGINT,
                    monetary NUMERIC(14, 2),
                    average_order_value NUMERIC(14, 2),
                    tenure_days BIGINT,
                    first_purchase_date DATE,
                    last_purchase_date DATE
                )
                """
            )
        )

        # Seed sample rows
        conn.execute(
            text(
                """
                INSERT INTO mart_daily_sales VALUES
                ('2010-01-01', 'United Kingdom', 1, 1000.0, 1000.0, -100.0, 900.0, 10, 100, 10),
                ('2010-01-01', 'United Kingdom', 0, 50.0, 50.0, 0.0, 50.0, 2, 2, 0),
                ('2010-01-02', 'Germany', 1, 500.0, 500.0, -50.0, 450.0, 5, 50, 5),
                ('2010-01-03', 'France', 1, 200.0, 200.0, 0.0, 200.0, 2, 20, 0)
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO mart_customer_daily VALUES
                (1001, '2010-01-01', 2, 400.0, -40.0, 360.0, 2),
                (1002, '2010-01-01', 1, 600.0, -60.0, 540.0, 1),
                (1003, '2010-01-02', 1, 500.0, -50.0, 450.0, 1)
                """
            )
        )

        conn.execute(
            text(
                """
                INSERT INTO mart_customer_snapshot VALUES
                (1001, 'United Kingdom', 10, 5, 1200.0, 240.0, 300, '2010-01-01', '2010-10-01'),
                (1002, 'Germany', 45, 2, 600.0, 300.0, 150, '2010-01-01', '2010-08-15'),
                (1003, 'France', 120, 1, 200.0, 200.0, 50, '2010-01-03', '2010-01-03'),
                (1004, 'United Kingdom', NULL, 0, -50.0, NULL, NULL, NULL, NULL)
                """
            )
        )

    return engine


# ============================================================================
# SALES QUERY TESTS
# ============================================================================

def test_get_date_range_and_countries(sqlite_engine):
    min_date, max_date = get_date_range(sqlite_engine)
    assert min_date is not None
    assert max_date is not None

    countries = get_available_countries(sqlite_engine)
    assert countries == ["France", "Germany", "United Kingdom"]


def test_get_sales_kpis_all_filters(sqlite_engine):
    kpis = get_sales_kpis(sqlite_engine)
    assert kpis["gross_sales"] == 1750.0
    assert kpis["return_value"] == -150.0
    assert kpis["net_sales"] == 1600.0
    assert kpis["invoice_segments"] == 19
    assert kpis["units_sold"] == 172
    assert kpis["units_returned"] == 15
    assert kpis["net_aov"] == round(1600.0 / 19, 2)
    assert kpis["gross_aov"] == round(1750.0 / 19, 2)
    assert kpis["return_rate_pct"] == round(150.0 / 1750.0 * 100, 2)


def test_get_sales_kpis_filtered_by_country_and_date(sqlite_engine):
    start = datetime.date(2010, 1, 1)
    end = datetime.date(2010, 1, 1)
    kpis = get_sales_kpis(sqlite_engine, start_date=start, end_date=end, country="United Kingdom")
    assert kpis["gross_sales"] == 1050.0
    assert kpis["net_sales"] == 950.0
    assert kpis["invoice_segments"] == 12


def test_get_daily_sales_trend(sqlite_engine):
    trend_df = get_daily_sales_trend(sqlite_engine)
    assert len(trend_df) == 3
    assert "gross_sales" in trend_df.columns
    assert "net_sales" in trend_df.columns


def test_get_sales_by_country(sqlite_engine):
    country_df = get_sales_by_country(sqlite_engine, limit=2)
    assert len(country_df) == 2
    assert country_df.iloc[0]["country"] == "United Kingdom"
    assert country_df.iloc[0]["net_sales"] == 950.0


def test_get_merchandise_breakdown(sqlite_engine):
    breakdown_df = get_merchandise_breakdown(sqlite_engine)
    assert len(breakdown_df) == 2
    labels = breakdown_df["product_classification"].tolist()
    assert "Physical Merchandise" in labels
    assert "Special & Service" in labels


def test_resample_sales_trend_weekly_and_monthly(sqlite_engine):
    daily = get_daily_sales_trend(sqlite_engine)
    assert len(daily) == 3
    daily_net_sum = daily["net_sales"].sum()

    weekly = resample_sales_trend(daily, frequency="Weekly")
    assert not weekly.empty
    assert round(weekly["net_sales"].sum(), 2) == round(daily_net_sum, 2)

    monthly = resample_sales_trend(daily, frequency="Monthly")
    assert len(monthly) == 1  # all 3 days are in Jan 2010
    assert round(monthly["net_sales"].sum(), 2) == round(daily_net_sum, 2)
    assert monthly.iloc[0]["invoice_segments"] == daily["invoice_segments"].sum()


def test_calculate_country_shares(sqlite_engine):
    country_df = get_sales_by_country(sqlite_engine, limit=10)
    shares_df = calculate_country_shares(country_df, total_net_sales=1600.0)
    assert "market_share_pct" in shares_df.columns
    # Total net sales across all 3 countries is 1600.0 (UK: 950 -> ~59.38%)
    uk_share = shares_df.loc[shares_df["country"] == "United Kingdom", "market_share_pct"].iloc[0]
    assert uk_share == pytest.approx(59.38, abs=0.1)


def test_resample_sales_trend_empty():
    empty_df = pd.DataFrame()
    assert resample_sales_trend(empty_df, "Weekly").empty
    assert calculate_country_shares(empty_df).empty


# ============================================================================
# CUSTOMER QUERY TESTS
# ============================================================================

def test_get_customer_kpis(sqlite_engine):
    cust_kpis = get_customer_kpis(sqlite_engine)
    assert cust_kpis["total_customers"] == 4
    assert cust_kpis["repeat_customers"] == 2
    assert cust_kpis["repeat_rate_pct"] == 50.0
    assert cust_kpis["one_time_buyers"] == 1
    assert cust_kpis["total_customer_spend"] == 1950.0


def test_get_customer_daily_trend(sqlite_engine):
    trend = get_customer_daily_trend(sqlite_engine)
    assert len(trend) == 2
    assert "active_customers" in trend.columns


def test_get_top_customers(sqlite_engine):
    top = get_top_customers(sqlite_engine, limit=2)
    assert len(top) == 2
    assert top.iloc[0]["customer_id"] == 1001
    assert top.iloc[0]["monetary"] == 1200.0


def test_compute_customer_distributions(sqlite_engine):
    snapshot = get_rfm_snapshot(sqlite_engine)
    freq_tiers, mon_brackets = compute_customer_distributions(snapshot)
    assert len(freq_tiers) == 5
    assert len(mon_brackets) == 6
    assert freq_tiers["Customer Count"].sum() == 4
    assert mon_brackets["Customer Count"].sum() == 4
    assert freq_tiers["Percentage"].sum() == pytest.approx(100.0, abs=0.1)


def test_compute_customer_distributions_empty():
    empty_df = pd.DataFrame(columns=["frequency", "monetary"])
    f_df, m_df = compute_customer_distributions(empty_df)
    assert f_df.empty
    assert m_df.empty


# ============================================================================
# RFM SEGMENTATION TESTS
# ============================================================================

def test_compute_rfm_segments_empty_dataframe():
    empty_df = pd.DataFrame(columns=["customer_id", "recency_days", "frequency", "monetary"])
    res = compute_rfm_segments(empty_df)
    assert "rfm_segment" in res.columns
    assert len(res) == 0


def test_compute_rfm_segments_handles_null_recency_and_assigns_segments():
    df = pd.DataFrame({
        "customer_id": [1, 2, 3, 4, 5],
        "recency_days": [2.0, 15.0, 120.0, 300.0, np.nan],
        "frequency": [20, 8, 2, 1, 0],
        "monetary": [5000.0, 1500.0, 300.0, 80.0, -20.0],
    })
    segmented = compute_rfm_segments(df)

    assert set(segmented.columns).issuperset({"r_score", "f_score", "m_score", "rfm_score", "rfm_segment"})
    # Customer 1 (recent, high frequency, high spend) should have top scores
    assert segmented.loc[segmented["customer_id"] == 1, "r_score"].iloc[0] == 5
    assert segmented.loc[segmented["customer_id"] == 1, "f_score"].iloc[0] == 5
    assert segmented.loc[segmented["customer_id"] == 1, "m_score"].iloc[0] == 5
    assert segmented.loc[segmented["customer_id"] == 1, "rfm_segment"].iloc[0] == "Champions"

    # Customer 5 with NaN recency should not crash and receive lowest r_score
    assert segmented.loc[segmented["customer_id"] == 5, "r_score"].iloc[0] == 1


def test_summarize_rfm_segments(sqlite_engine):
    raw_df = get_rfm_snapshot(sqlite_engine)
    segmented = compute_rfm_segments(raw_df)
    summary = summarize_rfm_segments(segmented)

    assert "Segment" in summary.columns
    assert "Revenue Share (%)" in summary.columns
    assert summary["Customer Count"].sum() == len(raw_df)
    assert round(summary["Revenue Share (%)"].sum(), 1) == pytest.approx(100.0, abs=0.5)


def test_summarize_rfm_segments_empty():
    empty_df = pd.DataFrame()
    res = summarize_rfm_segments(empty_df)
    assert res.empty
    assert "Segment" in res.columns


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

def test_missing_table_raises_database_query_error():
    engine = create_engine("sqlite:///:memory:")
    with pytest.raises(DatabaseQueryError):
        get_sales_kpis(engine)

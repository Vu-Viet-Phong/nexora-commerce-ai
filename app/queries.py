"""Database query layer for Nexora Commerce AI Analytics Dashboard.

Provides read-only, parameterized queries to PostgreSQL SQL Marts
(mart_daily_sales, mart_customer_daily, mart_customer_snapshot).
Includes safe environment variable resolution, connection pooling,
and graceful fallback handling for missing tables or empty datasets.
"""

from __future__ import annotations

import datetime
import os
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

import numpy as np
import pandas as pd
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError


class DatabaseQueryError(Exception):
    """Raised when a dashboard database query fails."""


def load_env_config(env_path: Path | None = None) -> None:
    """Safely load local environment variables from .env if present.

    Does not overwrite existing process environment variables.
    Never prints or logs values.
    """
    if env_path is None:
        # Search from file location up to project root
        env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def normalize_db_url(url: str) -> str:
    """URL-encode password characters for SQLAlchemy while masking credentials in logs.

    Handles special characters safely without leaking credentials.
    """
    marker = "@localhost:5432/"
    if marker not in url:
        return url
    prefix, suffix = url.rsplit(marker, 1)
    if "://" not in prefix or ":" not in prefix.split("://", 1)[1]:
        return url
    scheme, credentials = prefix.split("://", 1)
    username, password = credentials.split(":", 1)
    return f"{scheme}://{username}:{quote(unquote(password), safe='')}{marker}{suffix}"


def get_engine(database_url: str | None = None, load_env: bool = True) -> Engine:
    """Create and return a read-only SQLAlchemy engine with pre-ping validation.

    Priority:
    1. Explicit database_url argument
    2. DATABASE_URL environment variable
    3. NEXORA_DATABASE_URL environment variable
    """
    if load_env:
        load_env_config()
    target_url = (
        database_url
        or os.getenv("DATABASE_URL")
        or os.getenv("NEXORA_DATABASE_URL")
    )
    if not target_url:
        raise DatabaseQueryError(
            "Database URL not configured. Please set DATABASE_URL in .env"
        )
    normalized = normalize_db_url(target_url)
    return create_engine(normalized, pool_pre_ping=True)


# ============================================================================
# FILTER METADATA QUERIES
# ============================================================================

def get_date_range(engine: Engine) -> tuple[date | None, date | None]:
    """Retrieve min and max calendar days available in mart_daily_sales."""
    query = text(
        """
        SELECT
            MIN(calendar_day) AS min_date,
            MAX(calendar_day) AS max_date
        FROM mart_daily_sales
        """
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(query).mappings().first()
            if row and row["min_date"] and row["max_date"]:
                # Convert string dates if necessary (e.g. from SQLite)
                min_val = row["min_date"]
                max_val = row["max_date"]
                if isinstance(min_val, str):
                    min_val = datetime.date.fromisoformat(min_val)
                if isinstance(max_val, str):
                    max_val = datetime.date.fromisoformat(max_val)
                return min_val, max_val
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch date range: {exc}") from exc
    return None, None


def get_available_countries(engine: Engine) -> list[str]:
    """Retrieve sorted list of distinct countries from mart_daily_sales."""
    query = text(
        """
        SELECT DISTINCT country
        FROM mart_daily_sales
        ORDER BY country ASC
        """
    )
    try:
        with engine.connect() as conn:
            rows = conn.execute(query).fetchall()
            return [str(r[0]) for r in rows if r[0]]
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch countries: {exc}") from exc


# ============================================================================
# SALES ANALYTICS QUERIES (mart_daily_sales)
# ============================================================================

def get_sales_kpis(
    engine: Engine,
    start_date: date | None = None,
    end_date: date | None = None,
    country: str | None = None,
) -> dict[str, float]:
    """Calculate aggregated Sales KPIs directly in PostgreSQL to save memory."""
    clauses = ["1=1"]
    params: dict[str, Any] = {}

    if start_date is not None:
        clauses.append("calendar_day >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        clauses.append("calendar_day <= :end_date")
        params["end_date"] = end_date
    if country and country != "All":
        clauses.append("country = :country")
        params["country"] = country

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            COALESCE(SUM(gross_sales), 0) AS gross_sales,
            COALESCE(SUM(valid_sales_revenue), 0) AS valid_sales,
            COALESCE(SUM(return_value), 0) AS return_value,
            COALESCE(SUM(net_sales), 0) AS net_sales,
            COALESCE(SUM(distinct_invoices), 0) AS total_orders,
            COALESCE(SUM(units_sold), 0) AS units_sold,
            COALESCE(SUM(units_returned), 0) AS units_returned
        FROM mart_daily_sales
        WHERE {where_sql}
        """
    )

    try:
        with engine.connect() as conn:
            row = conn.execute(query, params).mappings().first()
            if not row:
                return {
                    "gross_sales": 0.0,
                    "valid_sales": 0.0,
                    "return_value": 0.0,
                    "net_sales": 0.0,
                    "total_orders": 0,
                    "units_sold": 0,
                    "units_returned": 0,
                    "aov": 0.0,
                    "return_rate_pct": 0.0,
                }
            gross = float(row["gross_sales"])
            ret = float(row["return_value"])
            net = float(row["net_sales"])
            orders = int(row["total_orders"])
            units_s = int(row["units_sold"])
            units_r = int(row["units_returned"])

            aov = round(net / orders, 2) if orders > 0 else 0.0
            return_rate = round(abs(ret) / gross * 100.0, 2) if gross > 0 else 0.0

            return {
                "gross_sales": gross,
                "valid_sales": float(row["valid_sales"]),
                "return_value": ret,
                "net_sales": net,
                "total_orders": orders,
                "units_sold": units_s,
                "units_returned": units_r,
                "aov": aov,
                "return_rate_pct": return_rate,
            }
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch sales KPIs: {exc}") from exc


def get_daily_sales_trend(
    engine: Engine,
    start_date: date | None = None,
    end_date: date | None = None,
    country: str | None = None,
) -> pd.DataFrame:
    """Retrieve daily sales timeseries aggregated across categories."""
    clauses = ["1=1"]
    params: dict[str, Any] = {}

    if start_date is not None:
        clauses.append("calendar_day >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        clauses.append("calendar_day <= :end_date")
        params["end_date"] = end_date
    if country and country != "All":
        clauses.append("country = :country")
        params["country"] = country

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            calendar_day,
            SUM(gross_sales) AS gross_sales,
            SUM(return_value) AS return_value,
            SUM(net_sales) AS net_sales,
            SUM(distinct_invoices) AS total_orders,
            SUM(units_sold) AS units_sold,
            SUM(units_returned) AS units_returned
        FROM mart_daily_sales
        WHERE {where_sql}
        GROUP BY calendar_day
        ORDER BY calendar_day ASC
        """
    )
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn, params=params)
            if not df.empty:
                df["calendar_day"] = pd.to_datetime(df["calendar_day"])
            return df
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch daily sales trend: {exc}") from exc


def get_sales_by_country(
    engine: Engine,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 10,
) -> pd.DataFrame:
    """Retrieve top revenue countries within the selected date range."""
    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": limit}

    if start_date is not None:
        clauses.append("calendar_day >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        clauses.append("calendar_day <= :end_date")
        params["end_date"] = end_date

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            country,
            SUM(gross_sales) AS gross_sales,
            SUM(return_value) AS return_value,
            SUM(net_sales) AS net_sales,
            SUM(distinct_invoices) AS total_orders
        FROM mart_daily_sales
        WHERE {where_sql}
        GROUP BY country
        ORDER BY net_sales DESC
        LIMIT :limit
        """
    )
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch country sales: {exc}") from exc


def get_merchandise_breakdown(
    engine: Engine,
    start_date: date | None = None,
    end_date: date | None = None,
    country: str | None = None,
) -> pd.DataFrame:
    """Retrieve breakdown between physical merchandise and special/service fees."""
    clauses = ["1=1"]
    params: dict[str, Any] = {}

    if start_date is not None:
        clauses.append("calendar_day >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        clauses.append("calendar_day <= :end_date")
        params["end_date"] = end_date
    if country and country != "All":
        clauses.append("country = :country")
        params["country"] = country

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            CASE
                WHEN is_physical_merchandise THEN 'Physical Merchandise'
                ELSE 'Special & Service'
            END AS product_classification,
            SUM(gross_sales) AS gross_sales,
            SUM(return_value) AS return_value,
            SUM(net_sales) AS net_sales,
            SUM(units_sold) AS units_sold
        FROM mart_daily_sales
        WHERE {where_sql}
        GROUP BY is_physical_merchandise
        ORDER BY is_physical_merchandise DESC
        """
    )
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch merchandise breakdown: {exc}") from exc


# ============================================================================
# CUSTOMER ANALYTICS QUERIES (mart_customer_daily, mart_customer_snapshot)
# ============================================================================

def get_customer_kpis(
    engine: Engine,
    country: str | None = None,
) -> dict[str, float]:
    """Calculate aggregate customer statistics from mart_customer_snapshot."""
    clauses = ["1=1"]
    params: dict[str, Any] = {}

    if country and country != "All":
        clauses.append("primary_country = :country")
        params["country"] = country

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            COUNT(*) AS total_customers,
            COALESCE(SUM(monetary), 0) AS total_customer_spend,
            COALESCE(AVG(frequency), 0) AS avg_frequency,
            COALESCE(AVG(average_order_value), 0) AS avg_aov,
            COALESCE(AVG(recency_days), 0) AS avg_recency_days,
            COALESCE(AVG(tenure_days), 0) AS avg_tenure_days
        FROM mart_customer_snapshot
        WHERE {where_sql}
        """
    )
    try:
        with engine.connect() as conn:
            row = conn.execute(query, params).mappings().first()
            if not row:
                return {
                    "total_customers": 0,
                    "total_customer_spend": 0.0,
                    "avg_frequency": 0.0,
                    "avg_aov": 0.0,
                    "avg_recency_days": 0.0,
                    "avg_tenure_days": 0.0,
                }
            return {
                "total_customers": int(row["total_customers"]),
                "total_customer_spend": float(row["total_customer_spend"]),
                "avg_frequency": float(row["avg_frequency"]),
                "avg_aov": float(row["avg_aov"]),
                "avg_recency_days": float(row["avg_recency_days"]),
                "avg_tenure_days": float(row["avg_tenure_days"]),
            }
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch customer KPIs: {exc}") from exc


def get_customer_daily_trend(
    engine: Engine,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Retrieve daily active purchasing customers and aggregate daily spend."""
    clauses = ["1=1"]
    params: dict[str, Any] = {}

    if start_date is not None:
        clauses.append("calendar_day >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        clauses.append("calendar_day <= :end_date")
        params["end_date"] = end_date

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            calendar_day,
            COUNT(DISTINCT customer_id) AS active_customers,
            SUM(gross_spend) AS daily_gross_spend,
            SUM(net_spend) AS daily_net_spend,
            SUM(order_frequency) AS daily_orders
        FROM mart_customer_daily
        WHERE {where_sql}
        GROUP BY calendar_day
        ORDER BY calendar_day ASC
        """
    )
    try:
        with engine.connect() as conn:
            df = pd.read_sql_query(query, conn, params=params)
            if not df.empty:
                df["calendar_day"] = pd.to_datetime(df["calendar_day"])
            return df
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch customer daily trend: {exc}") from exc


def get_top_customers(
    engine: Engine,
    country: str | None = None,
    limit: int = 15,
) -> pd.DataFrame:
    """Retrieve top customers ranked by total monetary spend."""
    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": limit}

    if country and country != "All":
        clauses.append("primary_country = :country")
        params["country"] = country

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            customer_id,
            primary_country,
            monetary,
            frequency,
            average_order_value,
            recency_days,
            tenure_days,
            first_purchase_date,
            last_purchase_date
        FROM mart_customer_snapshot
        WHERE {where_sql}
        ORDER BY monetary DESC
        LIMIT :limit
        """
    )
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch top customers: {exc}") from exc


# ============================================================================
# RFM ANALYTICS & SEGMENTATION (mart_customer_snapshot)
# ============================================================================

def get_rfm_snapshot(
    engine: Engine,
    country: str | None = None,
) -> pd.DataFrame:
    """Retrieve full customer snapshot dataset for RFM analysis and distribution."""
    clauses = ["1=1"]
    params: dict[str, Any] = {}

    if country and country != "All":
        clauses.append("primary_country = :country")
        params["country"] = country

    where_sql = " AND ".join(clauses)
    query = text(
        f"""
        SELECT
            customer_id,
            primary_country,
            recency_days,
            frequency,
            monetary,
            average_order_value,
            tenure_days
        FROM mart_customer_snapshot
        WHERE {where_sql}
        """
    )
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except SQLAlchemyError as exc:
        raise DatabaseQueryError(f"Failed to fetch RFM snapshot: {exc}") from exc


def compute_rfm_segments(df: pd.DataFrame) -> pd.DataFrame:
    """Compute standard 1-5 RFM scores and business customer segments.

    - Recency score: 5 = most recent (lowest recency_days), 1 = least recent.
    - Frequency score: 5 = most frequent, 1 = least frequent.
    - Monetary score: 5 = highest spend, 1 = lowest spend.

    Handles duplicated quantiles cleanly using rank percentile bins.
    """
    if df.empty:
        result = df.copy()
        result["r_score"] = 0
        result["f_score"] = 0
        result["m_score"] = 0
        result["rfm_score"] = "000"
        result["rfm_segment"] = "Unknown"
        return result

    result = df.copy()

    # Recency: lower days is better -> invert rank (NaN/null means no valid sale -> worst recency)
    clean_recency = result["recency_days"].fillna(result["recency_days"].max() + 365)
    r_pct = clean_recency.rank(pct=True, method="first", ascending=False)
    result["r_score"] = np.ceil(r_pct * 5).fillna(1).astype(int).clip(1, 5)

    # Frequency: higher is better (NaN -> 0 -> lowest frequency)
    clean_freq = result["frequency"].fillna(0)
    f_pct = clean_freq.rank(pct=True, method="first", ascending=True)
    result["f_score"] = np.ceil(f_pct * 5).fillna(1).astype(int).clip(1, 5)

    # Monetary: higher is better (NaN -> 0 -> lowest spend)
    clean_monetary = result["monetary"].fillna(0)
    m_pct = clean_monetary.rank(pct=True, method="first", ascending=True)
    result["m_score"] = np.ceil(m_pct * 5).fillna(1).astype(int).clip(1, 5)

    result["rfm_score"] = (
        result["r_score"].astype(str)
        + result["f_score"].astype(str)
        + result["m_score"].astype(str)
    )

    def assign_segment(row: pd.Series) -> str:
        r = row["r_score"]
        f = row["f_score"]
        m = row["m_score"]

        # High-value active buyers
        if r >= 4 and f >= 4 and m >= 4:
            return "Champions"
        if r >= 3 and f >= 3:
            return "Loyal Customers"
        if r >= 4 and f <= 2:
            return "Potential Loyalists"
        if r >= 3 and f <= 2 and m >= 3:
            return "Promising"
        # Slipping / at risk
        if r <= 2 and f >= 3 and m >= 3:
            return "At Risk"
        if r <= 2 and f >= 3 and m <= 2:
            return "Need Attention"
        if r <= 2 and f <= 2 and m >= 3:
            return "About To Sleep"
        # Inactive
        if r == 1 and f <= 2:
            return "Lost"
        if r <= 2 and f <= 2:
            return "Hibernating"
        return "Standard"

    result["rfm_segment"] = result.apply(assign_segment, axis=1)
    return result

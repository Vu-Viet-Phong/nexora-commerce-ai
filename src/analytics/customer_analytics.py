"""Read-only customer feature generation and EDA over approved SQL marts."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
from sqlalchemy import text

CUSTOMER_FEATURE_COLUMNS = (
    "customer_id",
    "primary_country",
    "reference_date",
    "recency_days",
    "frequency",
    "monetary",
    "average_order_value",
    "tenure_days",
)

CUSTOMER_FEATURES_SQL = """
WITH bounded_daily AS (
    SELECT
        customer_id,
        calendar_day,
        order_frequency,
        gross_spend,
        return_value,
        net_spend
    FROM mart_customer_daily
    WHERE calendar_day <= CAST(:as_of_date AS DATE)
),
aggregated AS (
    SELECT
        customer_id,
        MIN(calendar_day) FILTER (WHERE order_frequency > 0)
            AS first_purchase_date,
        MAX(calendar_day) FILTER (WHERE order_frequency > 0)
            AS last_purchase_date,
        COALESCE(SUM(order_frequency), 0)::INTEGER AS frequency,
        COALESCE(SUM(gross_spend), 0)::NUMERIC(14, 2) AS gross_monetary,
        COALESCE(SUM(return_value), 0)::NUMERIC(14, 2) AS return_value,
        COALESCE(SUM(net_spend), 0)::NUMERIC(14, 2) AS monetary
    FROM bounded_daily
    GROUP BY customer_id
)
SELECT
    c.customer_id,
    c.primary_country,
    CAST(:as_of_date AS DATE) AS reference_date,
    CASE
        WHEN a.last_purchase_date IS NOT NULL
            THEN CAST(:as_of_date AS DATE) - a.last_purchase_date
        ELSE NULL
    END AS recency_days,
    COALESCE(a.frequency, 0)::INTEGER AS frequency,
    COALESCE(a.monetary, 0)::NUMERIC(14, 2) AS monetary,
    CASE
        WHEN COALESCE(a.frequency, 0) > 0
            THEN ROUND(a.gross_monetary / a.frequency, 2)
        ELSE NULL
    END::NUMERIC(14, 2) AS average_order_value,
    CASE
        WHEN a.first_purchase_date IS NOT NULL
            THEN CAST(:as_of_date AS DATE) - a.first_purchase_date
        ELSE NULL
    END AS tenure_days
FROM customers AS c
LEFT JOIN aggregated AS a
  ON a.customer_id = c.customer_id
WHERE c.source_system = 'UCI'
ORDER BY c.customer_id
"""

EDA_QUERIES = {
    "sales_distribution": """
        SELECT
            COUNT(*) AS day_count,
            MIN(net_sales) AS min_net_sales,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY net_sales)
                AS median_net_sales,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY net_sales)
                AS p95_net_sales,
            MAX(net_sales) AS max_net_sales
        FROM mart_daily_sales
    """,
    "customer_transaction_behavior": """
        SELECT
            COUNT(*) AS customer_count,
            AVG(frequency) AS average_frequency,
            AVG(recency_days) FILTER (WHERE frequency > 0) AS average_recency,
            AVG(tenure_days) FILTER (WHERE frequency > 0) AS average_tenure
        FROM mart_customer_snapshot
    """,
    "order_frequency": """
        SELECT frequency, COUNT(*) AS customer_count
        FROM mart_customer_snapshot
        GROUP BY frequency
        ORDER BY frequency
    """,
    "spending_distribution": """
        SELECT
            percentile_cont(0.50) WITHIN GROUP (ORDER BY monetary) AS p50,
            percentile_cont(0.90) WITHIN GROUP (ORDER BY monetary) AS p90,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY monetary) AS p99,
            MAX(monetary) AS max_monetary
        FROM mart_customer_snapshot
    """,
    "product_popularity": """
        SELECT
            l.stock_code,
            p.primary_description,
            SUM(l.quantity) FILTER (WHERE l.is_valid_sale) AS units_sold,
            SUM(l.line_total) FILTER (WHERE l.is_valid_sale)::NUMERIC(14, 2)
                AS gross_sales
        FROM invoice_lines AS l
        JOIN products AS p
          ON p.source_system = l.source_system
         AND p.stock_code = l.stock_code
        WHERE l.source_system = 'UCI'
        GROUP BY l.stock_code, p.primary_description
        ORDER BY units_sold DESC NULLS LAST
        LIMIT 100
    """,
    "country_distribution": """
        SELECT country, SUM(net_sales)::NUMERIC(14, 2) AS net_sales
        FROM mart_daily_sales
        GROUP BY country
        ORDER BY net_sales DESC
    """,
    "returns_and_cancellations": """
        SELECT
            SUM(return_value)::NUMERIC(14, 2) AS return_value,
            SUM(units_returned) AS units_returned,
            COUNT(*) FILTER (WHERE return_value < 0) AS groups_with_returns
        FROM mart_daily_sales
    """,
    "missing_customer_id": """
        SELECT
            COUNT(*) AS line_count,
            COUNT(*) FILTER (WHERE customer_id IS NULL) AS missing_customer_lines,
            SUM(line_total) FILTER (WHERE customer_id IS NULL)::NUMERIC(14, 2)
                AS missing_customer_ledger
        FROM invoice_lines
        WHERE source_system = 'UCI'
    """,
    "temporal_transaction_patterns": """
        SELECT calendar_day, SUM(net_sales)::NUMERIC(14, 2) AS net_sales,
               SUM(distinct_invoices) AS invoice_count
        FROM mart_daily_sales
        GROUP BY calendar_day
        ORDER BY calendar_day
    """,
    "sparsity_and_long_tail": """
        WITH ranked AS (
            SELECT
                customer_id,
                monetary,
                frequency,
                SUM(monetary) OVER () AS population_monetary,
                ROW_NUMBER() OVER (ORDER BY monetary DESC) AS customer_rank
            FROM mart_customer_snapshot
            WHERE monetary > 0
        )
        SELECT
            COUNT(*) AS positive_customers,
            COUNT(*) FILTER (WHERE frequency = 0) AS zero_frequency_customers,
            MAX(monetary) AS top_customer_monetary,
            SUM(monetary) FILTER (WHERE customer_rank <= 100)
                / NULLIF(MAX(population_monetary), 0) AS top_100_share
        FROM ranked
    """,
}


def build_customer_features_query() -> str:
    """Return the deterministic as-of feature query without executing it."""
    return CUSTOMER_FEATURES_SQL


def validate_customer_features(frame: pd.DataFrame) -> None:
    """Validate the one-row-per-customer contract for an ML-ready frame."""
    missing = set(CUSTOMER_FEATURE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"missing customer feature columns: {sorted(missing)}")
    if frame["customer_id"].duplicated().any():
        raise ValueError("customer_id must be unique")
    if frame["customer_id"].isna().any():
        raise ValueError("customer_id must not be NULL in customer features")
        
    if not frame.empty and frame["frequency"].isna().all():
        raise ValueError("frequency cannot be entirely NULL")
    if not frame.empty and frame["monetary"].isna().all():
        raise ValueError("monetary cannot be entirely NULL")

    numeric_columns = (
        "recency_days",
        "frequency",
        "monetary",
        "average_order_value",
        "tenure_days",
    )
    for column in numeric_columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].notna().any() and (values.isna() & frame[column].notna()).any():
            raise ValueError(f"{column} contains non-numeric values")
        if np.isinf(values.astype(float)).any():
            raise ValueError(f"{column} contains non-finite values")

    freq = pd.to_numeric(frame["frequency"], errors="coerce")
    rec = pd.to_numeric(frame["recency_days"], errors="coerce")
    tenure = pd.to_numeric(frame["tenure_days"], errors="coerce")

    if (freq < 0).any():
        raise ValueError("frequency must be non-negative")
    if (rec < 0).any():
        raise ValueError("recency_days must be non-negative")
    if (tenure < 0).any():
        raise ValueError("tenure_days must be non-negative")
        
    if ((freq > 0) & rec.isna()).any():
        raise ValueError("recency_days must not be NULL when frequency > 0")
    if ((freq == 0) & rec.notna()).any():
        raise ValueError("recency_days must be NULL when frequency == 0")


def fetch_customer_features(
    engine: Any,
    *,
    as_of_date: date = date(2011, 12, 10),
) -> pd.DataFrame:
    """Fetch bounded customer features; only the customer-level result enters RAM."""
    frame = pd.read_sql(
        text(CUSTOMER_FEATURES_SQL),
        engine,
        params={"as_of_date": as_of_date},
    )
    validate_customer_features(frame)
    return frame


def write_customer_features(
    engine: Any,
    output_path: Path,
    *,
    as_of_date: date = date(2011, 12, 10),
) -> pd.DataFrame:
    """Write only the small customer-level feature dataset, never raw facts."""
    frame = fetch_customer_features(engine, as_of_date=as_of_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(output_path, index=False)
    return frame


def run_eda(engine: Any) -> dict[str, pd.DataFrame]:
    """Run the approved read-only EDA queries and return bounded summaries."""
    return {
        name: pd.read_sql(text(query), engine)
        for name, query in EDA_QUERIES.items()
    }

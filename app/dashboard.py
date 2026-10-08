"""Nexora Commerce AI - Executive Analytics Dashboard.

Streamlit-based analytical dashboard consuming PostgreSQL SQL Marts:
- mart_daily_sales
- mart_customer_daily
- mart_customer_snapshot
"""

from __future__ import annotations

import datetime
from typing import Any

import pandas as pd
import streamlit as st

from app.queries import (
    DatabaseQueryError,
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
)

# ============================================================================
# PAGE CONFIGURATION & STYLING
# ============================================================================

st.set_page_config(
    page_title="Nexora Commerce AI | Executive Dashboard",
    page_icon="🛍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for clean enterprise aesthetics
st.markdown(
    """
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        border-left: 4px solid #1E88E5;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        margin-bottom: 12px;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #616161;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .metric-value {
        font-size: 1.6rem;
        font-weight: 700;
        color: #212121;
        margin-top: 4px;
    }
    .metric-delta {
        font-size: 0.8rem;
        color: #43A047;
        margin-top: 2px;
    }
    .badge-connected {
        background-color: #E8F5E9;
        color: #2E7D32;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-disconnected {
        background-color: #FFEBEE;
        color: #C62828;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================================
# CACHED DATA FETCHERS
# ============================================================================

@st.cache_resource
def init_engine():
    """Cache the database engine instance."""
    try:
        return get_engine()
    except Exception as exc:
        return None


@st.cache_data(ttl=600)
def fetch_metadata(_engine) -> tuple[datetime.date, datetime.date, list[str]]:
    """Retrieve date range and available countries."""
    min_date, max_date = get_date_range(_engine)
    countries = get_available_countries(_engine)
    # Default fallbacks if empty
    min_d = min_date or datetime.date(2009, 12, 1)
    max_d = max_date or datetime.date(2011, 12, 9)
    return min_d, max_d, countries


@st.cache_data(ttl=300)
def fetch_sales_data(_engine, start_date, end_date, country):
    """Retrieve sales KPIs, daily trend, country distribution, and product breakdown."""
    kpis = get_sales_kpis(_engine, start_date=start_date, end_date=end_date, country=country)
    trend = get_daily_sales_trend(_engine, start_date=start_date, end_date=end_date, country=country)
    countries = get_sales_by_country(_engine, start_date=start_date, end_date=end_date, limit=10)
    merch = get_merchandise_breakdown(_engine, start_date=start_date, end_date=end_date, country=country)
    return kpis, trend, countries, merch


@st.cache_data(ttl=300)
def fetch_customer_data(_engine, start_date, end_date, country):
    """Retrieve customer KPIs, daily active spend trend, and top customers."""
    kpis = get_customer_kpis(_engine, country=country)
    trend = get_customer_daily_trend(_engine, start_date=start_date, end_date=end_date)
    top_cust = get_top_customers(_engine, country=country, limit=15)
    return kpis, trend, top_cust


@st.cache_data(ttl=300)
def fetch_rfm_data(_engine, country):
    """Retrieve customer RFM snapshot and calculated segments."""
    rfm_df = get_rfm_snapshot(_engine, country=country)
    segmented_df = compute_rfm_segments(rfm_df)
    return segmented_df


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    engine = init_engine()

    # --- SIDEBAR ---
    with st.sidebar:
        st.title("Nexora Commerce AI")
        st.caption("E-Commerce Intelligence Dashboard MVP")

        if engine is not None:
            st.markdown('<span class="badge-connected">● PostgreSQL Live Connected</span>', unsafe_allow_html=True)
        else:
            st.markdown('<span class="badge-disconnected">● Database Not Connected</span>', unsafe_allow_html=True)
            st.error("Cannot connect to PostgreSQL. Check `.env` configuration.")
            st.stop()

        st.divider()
        st.subheader("Filter Controls")

        try:
            min_date, max_date, country_options = fetch_metadata(engine)
        except Exception as exc:
            st.error(f"Error loading metadata: {exc}")
            st.stop()

        # Date range picker
        date_selection = st.date_input(
            "Select Date Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            help="Filter sales and customer metrics by invoice date.",
        )
        if isinstance(date_selection, (tuple, list)) and len(date_selection) == 2:
            start_date, end_date = date_selection
        else:
            start_date, end_date = min_date, max_date

        # Country filter
        country_choice = st.selectbox(
            "Country",
            options=["All"] + country_options,
            index=0,
            help="Filter analytics for a specific geographic market.",
        )

        st.divider()
        if st.button("🔄 Refresh Data Cache", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.caption("Data Source: `UCI Online Retail II` via SQL Marts")
        st.caption("Marts: `mart_daily_sales`, `mart_customer_daily`, `mart_customer_snapshot`")

    # --- HEADER ---
    st.title("🛒 Executive Analytics Dashboard")
    st.markdown(
        f"**Active Window:** `{start_date}` to `{end_date}` | "
        f"**Market:** `{country_choice}` | "
        f"**Grain:** Daily Sales & Customer Marts"
    )

    # --- TABS NAVIGATION ---
    tab_sales, tab_customers, tab_rfm = st.tabs([
        "💰 Sales Overview",
        "👥 Customer Analytics",
        "🎯 RFM Segmentation",
    ])

    # ========================================================================
    # TAB 1: SALES OVERVIEW (Skeleton preview for Checkpoint A)
    # ========================================================================
    with tab_sales:
        try:
            kpis, trend_df, country_df, merch_df = fetch_sales_data(
                engine, start_date=start_date, end_date=end_date, country=country_choice
            )
            # KPI Metric Row
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Gross Sales", f"£{kpis['gross_sales']:,.2f}")
            with col2:
                st.metric("Returns / Cancel", f"£{abs(kpis['return_value']):,.2f}", delta=f"-{kpis['return_rate_pct']:.2f}%", delta_color="inverse")
            with col3:
                st.metric("Net Sales", f"£{kpis['net_sales']:,.2f}")
            with col4:
                st.metric("Total Orders", f"{kpis['total_orders']:,}")
            with col5:
                st.metric("Average Order Value", f"£{kpis['aov']:,.2f}")

            st.divider()

            # Sales charts row
            col_chart_main, col_chart_side = st.columns([2, 1])
            with col_chart_main:
                st.subheader("Daily Net Sales Trend")
                if not trend_df.empty:
                    chart_data = trend_df.set_index("calendar_day")[["net_sales", "gross_sales"]]
                    st.line_chart(chart_data)
                else:
                    st.info("No sales transactions found for the selected filter.")

            with col_chart_side:
                st.subheader("Top Markets by Net Sales")
                if not country_df.empty:
                    top_bar_data = country_df.set_index("country")["net_sales"].head(7)
                    st.bar_chart(top_bar_data)
                else:
                    st.info("No country sales data available.")

        except DatabaseQueryError as err:
            st.error(f"Query error in Sales Overview: {err}")

    # ========================================================================
    # TAB 2: CUSTOMER ANALYTICS (Skeleton preview for Checkpoint A)
    # ========================================================================
    with tab_customers:
        try:
            cust_kpis, cust_trend, top_cust = fetch_customer_data(
                engine, start_date=start_date, end_date=end_date, country=country_choice
            )
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Identified Customers", f"{cust_kpis['total_customers']:,}")
            with col2:
                st.metric("Total Customer Spend", f"£{cust_kpis['total_customer_spend']:,.2f}")
            with col3:
                st.metric("Avg Frequency", f"{cust_kpis['avg_frequency']:.1f} orders")
            with col4:
                st.metric("Avg Customer AOV", f"£{cust_kpis['avg_aov']:,.2f}")

            st.divider()
            st.subheader("Daily Active Customer Purchasing Trend")
            if not cust_trend.empty:
                st.line_chart(cust_trend.set_index("calendar_day")["active_customers"])
            else:
                st.info("No active purchasing activity found.")

        except DatabaseQueryError as err:
            st.error(f"Query error in Customer Analytics: {err}")

    # ========================================================================
    # TAB 3: RFM SEGMENTATION (Skeleton preview for Checkpoint A)
    # ========================================================================
    with tab_rfm:
        try:
            rfm_data = fetch_rfm_data(engine, country=country_choice)
            st.subheader("Customer RFM Distribution & Segments")
            if not rfm_data.empty:
                segment_counts = rfm_data["rfm_segment"].value_counts().reset_index()
                segment_counts.columns = ["Segment", "Customer Count"]
                col_rfm_chart, col_rfm_table = st.columns([1, 1])
                with col_rfm_chart:
                    st.bar_chart(segment_counts.set_index("Segment")["Customer Count"])
                with col_rfm_table:
                    st.dataframe(segment_counts, use_container_width=True)
            else:
                st.info("No RFM data available.")

        except DatabaseQueryError as err:
            st.error(f"Query error in RFM Segmentation: {err}")


if __name__ == "__main__":
    main()

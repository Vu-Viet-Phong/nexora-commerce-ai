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
    calculate_country_shares,
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
    resample_sales_trend,
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
    # TAB 1: SALES OVERVIEW (Checkpoint B Implementation)
    # ========================================================================
    with tab_sales:
        try:
            kpis, trend_df, country_df, merch_df = fetch_sales_data(
                engine, start_date=start_date, end_date=end_date, country=country_choice
            )

            # 1. Executive KPI Cards Row
            st.markdown("### 📊 Key Performance Indicators (Sales)")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric(
                    label="Gross Sales",
                    value=f"£{kpis['gross_sales']:,.2f}",
                    help="Total revenue from all valid positive sales transactions.",
                )
                st.caption(f"Valid: £{kpis['valid_sales']:,.2f}")
            with col2:
                st.metric(
                    label="Returns & Refunds",
                    value=f"-£{abs(kpis['return_value']):,.2f}",
                    delta=f"{kpis['return_rate_pct']:.2f}% return rate",
                    delta_color="inverse",
                    help="Total value lost to cancellations and returns.",
                )
                st.caption(f"Units returned: {kpis['units_returned']:,}")
            with col3:
                st.metric(
                    label="Net Sales",
                    value=f"£{kpis['net_sales']:,.2f}",
                    help="Net revenue realized = Gross Sales - Returns.",
                )
                net_rate = (kpis['net_sales'] / kpis['gross_sales'] * 100.0) if kpis['gross_sales'] > 0 else 0.0
                st.caption(f"Net realization: {net_rate:.1f}%")
            with col4:
                st.metric(
                    label="Total Orders",
                    value=f"{kpis['total_orders']:,}",
                    help="Count of unique valid sales invoices.",
                )
                st.caption(f"Units sold: {kpis['units_sold']:,}")
            with col5:
                st.metric(
                    label="Average Order Value",
                    value=f"£{kpis['aov']:,.2f}",
                    help="Average net revenue per order invoice.",
                )
                items_per_order = (kpis['units_sold'] / kpis['total_orders']) if kpis['total_orders'] > 0 else 0.0
                st.caption(f"Avg items/order: {items_per_order:.1f}")

            st.divider()

            # 2. Sales Trend & Volume Over Time
            st.markdown("### 📈 Revenue & Order Volume Trends")
            col_freq, col_metric = st.columns([1, 2])
            with col_freq:
                freq_choice = st.radio(
                    "Trend Granularity",
                    options=["Daily", "Weekly", "Monthly"],
                    horizontal=True,
                    index=1,
                    help="Aggregate sales curve into Daily, Weekly, or Monthly buckets.",
                )
            with col_metric:
                view_metric = st.selectbox(
                    "Trend Focus",
                    options=["Net & Gross Sales", "Units Sold & Returned", "Cumulative Net Sales"],
                    index=0,
                )

            if not trend_df.empty:
                resampled_trend = resample_sales_trend(trend_df, frequency=freq_choice)
                if view_metric == "Net & Gross Sales":
                    chart_data = resampled_trend.set_index("calendar_day")[["net_sales", "gross_sales"]]
                    st.line_chart(chart_data, color=["#1E88E5", "#43A047"])
                elif view_metric == "Units Sold & Returned":
                    unit_chart = resampled_trend.set_index("calendar_day")[["units_sold", "units_returned"]]
                    st.bar_chart(unit_chart, color=["#1E88E5", "#E53935"])
                else:
                    cumulative = resampled_trend.copy()
                    cumulative["cumulative_net_sales"] = cumulative["net_sales"].cumsum()
                    st.area_chart(
                        cumulative.set_index("calendar_day")["cumulative_net_sales"],
                        color="#1E88E5",
                    )
            else:
                st.info("No sales transactions found for the selected time window and country.")

            st.divider()

            # 3. Geographic Performance & Market Share
            st.markdown("### 🌍 Geographic Performance & Market Distribution")
            col_geo_chart, col_geo_table = st.columns([1, 1])

            country_with_shares = calculate_country_shares(country_df, total_net_sales=kpis["net_sales"])

            with col_geo_chart:
                st.subheader("Top 10 Markets by Net Revenue")
                if not country_with_shares.empty:
                    bar_data = country_with_shares.head(10).set_index("country")["net_sales"]
                    st.bar_chart(bar_data, color="#1E88E5")
                else:
                    st.info("No country sales data available.")

            with col_geo_table:
                st.subheader("Market Revenue Breakdown")
                if not country_with_shares.empty:
                    display_geo = country_with_shares.copy()
                    display_geo.columns = [
                        "Country", "Gross Sales (£)", "Returns (£)", "Net Sales (£)", "Orders", "Market Share (%)"
                    ]
                    st.dataframe(
                        display_geo.style.format({
                            "Gross Sales (£)": "£{:,.2f}",
                            "Returns (£)": "£{:,.2f}",
                            "Net Sales (£)": "£{:,.2f}",
                            "Orders": "{:,.0f}",
                            "Market Share (%)": "{:.2f}%",
                        }),
                        use_container_width=True,
                        height=350,
                    )
                else:
                    st.info("No country records to display.")

            st.divider()

            # 4. Product Classification & Data Governance
            st.markdown("### 🏷️ Product Classification & Governance Contract")
            col_merch_info, col_merch_table = st.columns([1, 1])

            with col_merch_info:
                st.info(
                    "**Data Governance & Mart Contract:**\n\n"
                    "- All sales lines in `mart_daily_sales` represent verified **Physical Merchandise**.\n"
                    "- Non-merchandise activities (Postal fees `POST`, Manual adjustments `M`, Bank charges `BANK CHARGES`, Bad Debt) "
                    "are partitioned per Stage 1 & Stage 2 data cleansing contracts.\n"
                    "- Inventory adjustments (`ADJUST`, `ADJUST2`) are excluded from sales revenue calculations."
                )

            with col_merch_table:
                if not merch_df.empty:
                    display_merch = merch_df.copy()
                    display_merch.columns = [
                        "Classification", "Gross Sales (£)", "Returns (£)", "Net Sales (£)", "Units Sold"
                    ]
                    st.dataframe(
                        display_merch.style.format({
                            "Gross Sales (£)": "£{:,.2f}",
                            "Returns (£)": "£{:,.2f}",
                            "Net Sales (£)": "£{:,.2f}",
                            "Units Sold": "{:,.0f}",
                        }),
                        use_container_width=True,
                    )

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

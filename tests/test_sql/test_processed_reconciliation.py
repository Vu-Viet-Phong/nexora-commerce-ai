from pathlib import Path

import pandas as pd


DATASET = (
    Path(__file__).parents[2]
    / "data"
    / "processed"
    / "transactions_clean.parquet"
)


def load_processed() -> pd.DataFrame:
    return pd.read_parquet(DATASET)


def test_processed_source_counts_match_schema_targets() -> None:
    frame = load_processed()
    assert len(frame) == 1_044_848
    assert frame["Invoice"].nunique() == 53_628
    assert frame["StockCode"].nunique() == 5_131
    assert frame["Customer ID"].nunique() == 5_942
    assert frame["Customer ID"].isna().sum() == 235_287


def test_special_transaction_flags_are_retained() -> None:
    frame = load_processed()
    assert frame["is_cancellation"].sum() == 19_165
    assert frame["is_return"].sum() == 19_165
    assert frame["is_inventory_adjustment"].sum() == 3_393
    assert frame["is_bad_debt_adjustment"].sum() == 6
    assert frame["is_non_product"].sum() == 5_805
    assert frame["is_duplicate_within_sheet"].sum() == 22_813


def test_processed_revenue_ground_truth_is_decimal_rounded() -> None:
    frame = load_processed()
    assert round(frame["line_total"].sum(), 2) == 18_909_762.12
    assert round(frame.loc[frame["is_valid_sale"], "line_total"].sum(), 2) == (
        19_700_954.46
    )
    assert round(
        frame.loc[
            frame["is_cancellation"] & ~frame["is_non_product"], "line_total"
        ].sum(),
        2,
    ) == -719_692.94


def test_invoice_header_grain_has_single_customer_and_country() -> None:
    frame = load_processed()
    assert frame.groupby("Invoice")["Customer ID"].nunique(dropna=True).max() == 1
    assert frame.groupby("Invoice")["Country"].nunique(dropna=True).max() == 1
    assert frame.groupby("Invoice")["InvoiceDate"].nunique(dropna=False).gt(1).sum() == 83

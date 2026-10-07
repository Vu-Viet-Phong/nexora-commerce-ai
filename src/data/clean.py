"""Type normalization and explainable quality flags for Stage 1."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from .ingest import ORIGINAL_COLUMNS

KNOWN_NON_PRODUCT_CODES = {
    "POST", "DOT", "M", "C2", "D", "S", "BANK CHARGES", "ADJUST",
    "AMAZONFEE", "GIFT VOUCHER", "TEST001", "TEST002", "CRUK", "ADJUST2",
}
KNOWN_NON_PRODUCT_PREFIXES = ("GIFT_0001_",)


def _as_frame(data: Mapping[str, pd.DataFrame] | pd.DataFrame) -> pd.DataFrame:
    if isinstance(data, pd.DataFrame):
        return data.copy(deep=True)
    frames = [frame.copy(deep=True).assign(source_sheet=name) for name, frame in data.items()]
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame(columns=[*ORIGINAL_COLUMNS, "source_sheet"])


def clean_data(data: Mapping[str, pd.DataFrame] | pd.DataFrame) -> pd.DataFrame:
    frame = _as_frame(data)
    missing = [column for column in ORIGINAL_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing original columns: {missing}")
    if "source_sheet" not in frame:
        frame["source_sheet"] = "unknown"

    frame["Invoice"] = frame["Invoice"].astype("string").str.strip()
    # Chuẩn hóa nhưng vẫn giữ missing StockCode là <NA>, không thành "NAN".
    frame["StockCode"] = frame["StockCode"].astype("string").str.strip().str.upper()
    frame["Description"] = frame["Description"].astype("string").str.strip()
    frame["Country"] = frame["Country"].astype("string").str.strip()
    frame["Quantity"] = pd.to_numeric(frame["Quantity"], errors="coerce")
    frame["Price"] = pd.to_numeric(frame["Price"], errors="coerce")
    frame["Customer ID"] = pd.to_numeric(frame["Customer ID"], errors="coerce").astype("Int64")
    frame["InvoiceDate"] = pd.to_datetime(frame["InvoiceDate"], errors="coerce")

    key = list(ORIGINAL_COLUMNS)
    exact = frame.duplicated(key, keep=False)
    within = frame.duplicated(key + ["source_sheet"], keep=False)
    sheet_count = frame.groupby(key, dropna=False, sort=False)["source_sheet"].transform("nunique")
    cross = exact & sheet_count.gt(1)
    first_sheet = frame.groupby(key, dropna=False, sort=False)["source_sheet"].transform("first")
    cross_removed = cross & frame["source_sheet"].ne(first_sheet)
    frame["is_duplicate_within_sheet"] = within
    frame["is_duplicate_cross_sheet"] = cross
    frame = frame.loc[~cross_removed].copy()
    frame.attrs["cross_sheet_duplicates_removed"] = int(cross_removed.sum())
    frame.attrs["within_sheet_duplicates_detected"] = int(within.sum())

    invoice_upper = frame["Invoice"].str.upper()
    stock_upper = frame["StockCode"].str.upper()
    frame["is_cancellation"] = invoice_upper.str.startswith("C", na=False)
    frame["is_bad_debt_adjustment"] = invoice_upper.str.startswith("A", na=False)
    frame["is_negative_quantity"] = frame["Quantity"].lt(0).fillna(False)
    frame["is_return"] = frame["is_cancellation"]
    frame["is_inventory_adjustment"] = (
        frame["is_negative_quantity"]
        & ~frame["is_cancellation"]
        & frame["Price"].eq(0)
        & frame["Customer ID"].isna()
    )
    frame["has_customer_id"] = frame["Customer ID"].notna()
    frame["has_description"] = frame["Description"].notna()
    frame["has_valid_price"] = frame["Price"].gt(0).fillna(False)
    frame["is_price_zero"] = frame["Price"].eq(0)
    frame["is_price_negative"] = frame["Price"].lt(0).fillna(False)
    frame["is_non_product"] = stock_upper.isin(KNOWN_NON_PRODUCT_CODES) | stock_upper.str.startswith(
        KNOWN_NON_PRODUCT_PREFIXES, na=False
    )
    frame["is_unknown_special_code"] = False
    frame["is_valid_sale"] = (
        ~frame["is_cancellation"] & ~frame["is_bad_debt_adjustment"]
        & frame["Quantity"].gt(0) & frame["has_valid_price"]
        & ~frame["is_non_product"]
    )
    frame["line_total"] = frame["Quantity"] * frame["Price"]
    return frame.reset_index(drop=True)


def clean_sheets(sheets: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    return clean_data(sheets)

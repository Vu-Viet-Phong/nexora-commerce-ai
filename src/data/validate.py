"""Explicit structural and reconciliation validation for Stage 1."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .ingest import ORIGINAL_COLUMNS

EXPECTED_FLAGS = (
    "is_cancellation", "is_bad_debt_adjustment", "is_negative_quantity",
    "is_inventory_adjustment", "has_customer_id", "has_description",
    "has_valid_price", "is_non_product", "is_valid_sale",
    "is_duplicate_within_sheet", "is_duplicate_cross_sheet",
)


def validate_data(
    frame: pd.DataFrame,
    *,
    raw_rows: int | None = None,
    cross_sheet_duplicates_removed: int | None = None,
    require_flags: bool = False,
    expected_date_min: pd.Timestamp | None = None,
    expected_date_max: pd.Timestamp | None = None,
    raise_on_error: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    missing = [column for column in ORIGINAL_COLUMNS if column not in frame.columns]
    missing_flags = [column for column in EXPECTED_FLAGS if column not in frame.columns] if require_flags else []
    if missing:
        errors.append(f"missing_columns:{','.join(missing)}")
    if missing_flags:
        errors.append(f"missing_flags:{','.join(missing_flags)}")
    if require_flags and "source_sheet" not in frame.columns:
        errors.append("missing_columns:source_sheet")
    date_values = pd.to_datetime(frame["InvoiceDate"], errors="coerce") if "InvoiceDate" in frame else pd.Series(dtype="datetime64[ns]")
    quantity_numeric = pd.to_numeric(frame["Quantity"], errors="coerce") if "Quantity" in frame else pd.Series(dtype="float64")
    price_numeric = pd.to_numeric(frame["Price"], errors="coerce") if "Price" in frame else pd.Series(dtype="float64")
    if len(frame) and date_values.isna().any():
        errors.append(f"invalid_datetime:{int(date_values.isna().sum())}")
    if len(frame) and quantity_numeric.isna().any():
        errors.append(f"non_numeric_quantity:{int(quantity_numeric.isna().sum())}")
    if len(frame) and price_numeric.isna().any():
        errors.append(f"non_numeric_price:{int(price_numeric.isna().sum())}")
    if raw_rows is not None and cross_sheet_duplicates_removed is not None:
        expected_rows = raw_rows - cross_sheet_duplicates_removed
        if len(frame) != expected_rows:
            errors.append(f"row_reconciliation:{len(frame)}!={expected_rows}")
    actual_min = date_values.min() if date_values.notna().any() else None
    actual_max = date_values.max() if date_values.notna().any() else None
    if expected_date_min is not None and actual_min != expected_date_min:
        errors.append(f"date_min_changed:{actual_min}!={expected_date_min}")
    if expected_date_max is not None and actual_max != expected_date_max:
        errors.append(f"date_max_changed:{actual_max}!={expected_date_max}")
    result: dict[str, Any] = {
        "is_valid": not errors,
        "errors": errors,
        "row_count": int(len(frame)),
        "raw_rows": raw_rows,
        "cross_sheet_duplicates_removed": cross_sheet_duplicates_removed,
        "date_min": actual_min.isoformat() if actual_min is not None else None,
        "date_max": actual_max.isoformat() if actual_max is not None else None,
    }
    if raise_on_error and errors:
        raise ValueError("Data validation failed: " + "; ".join(errors))
    return result


def validation_summary(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame([validate_data(frame)])

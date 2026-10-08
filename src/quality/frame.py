"""Small offline validation functions for deterministic fixtures and callers.

These helpers return aggregates only. Relational-core SQL uses the same approved
grains and Stage 1 flag rules; NULL fact customers remain valid.
"""
from __future__ import annotations

from decimal import Decimal
import pandas as pd

from src.data.clean import KNOWN_NON_PRODUCT_CODES, KNOWN_NON_PRODUCT_PREFIXES
from .results import ValidationResult, compare


def required_columns(frame: pd.DataFrame, required: tuple[str, ...]) -> ValidationResult:
    return compare("completeness.required_columns", [], sorted(set(required) - set(frame.columns)))


def missing_values(frame: pd.DataFrame, required: tuple[str, ...]) -> ValidationResult:
    columns = required_columns(frame, required)
    if columns.status == "FAIL":
        return columns
    return compare("completeness.missing_values", 0, int(frame[list(required)].isna().any(axis=1).sum()))


def unique_grain(frame: pd.DataFrame, grain: tuple[str, ...]) -> ValidationResult:
    columns = required_columns(frame, grain)
    if columns.status == "FAIL":
        return columns
    return compare("uniqueness.grain", 0, int(frame.duplicated(list(grain)).sum()))


def foreign_keys(
    child: pd.DataFrame, parent: pd.DataFrame, keys: tuple[str, ...], *,
    nullable_key: str | None = None,
) -> ValidationResult:
    for frame in (child, parent):
        columns = required_columns(frame, keys)
        if columns.status == "FAIL":
            return columns
    eligible = child if nullable_key is None else child.loc[child[nullable_key].notna()]
    parents = set(parent.loc[:, list(keys)].itertuples(index=False, name=None))
    orphans = sum(key not in parents for key in eligible.loc[:, list(keys)].itertuples(index=False, name=None))
    return compare("integrity.foreign_keys", 0, orphans)


def line_business_rules(lines: pd.DataFrame) -> ValidationResult:
    required = (
        "invoice_number", "stock_code", "customer_id", "description", "quantity", "unit_price",
        "is_cancellation", "is_bad_debt_adjustment", "is_negative_quantity", "is_return",
        "is_inventory_adjustment", "has_customer_id", "has_description", "has_valid_price",
        "is_price_zero", "is_price_negative", "is_non_product", "is_valid_sale",
    )
    columns = required_columns(lines, required)
    if columns.status == "FAIL":
        return columns
    invoice = lines["invoice_number"].astype("string").str.upper()
    stock = lines["stock_code"].astype("string")
    expected = {
        "is_cancellation": invoice.str.startswith("C", na=False),
        "is_bad_debt_adjustment": invoice.str.startswith("A", na=False),
        "is_negative_quantity": lines["quantity"].lt(0),
        "has_customer_id": lines["customer_id"].notna(),
        "has_description": lines["description"].notna(),
        "has_valid_price": lines["unit_price"].gt(0),
        "is_price_zero": lines["unit_price"].eq(0),
        "is_price_negative": lines["unit_price"].lt(0),
        "is_non_product": stock.isin(KNOWN_NON_PRODUCT_CODES) |
                          stock.str.startswith(KNOWN_NON_PRODUCT_PREFIXES, na=False),
    }
    expected["is_return"] = expected["is_cancellation"]
    expected["is_inventory_adjustment"] = (
        expected["is_negative_quantity"] & ~expected["is_cancellation"] &
        expected["is_price_zero"] & ~expected["has_customer_id"]
    )
    expected["is_valid_sale"] = (
        ~expected["is_cancellation"] & ~expected["is_bad_debt_adjustment"] &
        lines["quantity"].gt(0) & expected["has_valid_price"] & ~expected["is_non_product"]
    )
    violations = {
        flag: int((lines[flag].isna() | lines[flag].ne(values)).fillna(True).sum())
        for flag, values in expected.items()
    }
    return compare("business.line_flags", dict.fromkeys(expected, 0), violations)


def monetary_total(values) -> Decimal:
    """Never aggregate money via a binary-float accumulator."""
    return sum((Decimal(str(value)) for value in values), Decimal("0.00"))

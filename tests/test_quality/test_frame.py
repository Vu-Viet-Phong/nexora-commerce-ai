from decimal import Decimal

import pandas as pd
import pytest

from src.data.load import prepare_frames
from src.quality.frame import (
    foreign_keys, line_business_rules, missing_values, monetary_total, unique_grain,
)
from src.quality.results import compare
from .test_source import make_source


def test_missing_required_values_and_missing_columns_are_failures():
    frame = pd.DataFrame({"source_system": ["UCI", "UCI"], "quantity": [1, None]})
    assert missing_values(frame, ("source_system", "quantity")).actual == 1
    assert missing_values(frame, ("source_system", "absent")).status == "FAIL"


def test_duplicate_detection_uses_approved_grain_not_invoice_product(tmp_path):
    *_, lines = prepare_frames(make_source(tmp_path))
    assert unique_grain(lines, ("source_system", "source_line_key")).status == "PASS"
    lines.loc[1, "source_line_key"] = lines.loc[0, "source_line_key"]
    assert unique_grain(lines, ("source_system", "source_line_key")).actual == 1
    assert unique_grain(lines, ("source_system", "source_sheet", "source_row_number")).status == "PASS"


def test_invalid_foreign_keys_are_source_scoped_and_null_guests_are_allowed():
    children = pd.DataFrame({
        "source_system": ["UCI", "OTHER", "UCI"], "customer_id": [123, 123, None],
    })
    parents = pd.DataFrame({"source_system": ["UCI"], "customer_id": [123]})
    result = foreign_keys(children, parents, ("source_system", "customer_id"),
                          nullable_key="customer_id")
    assert result.status == "FAIL"
    assert result.actual == 1
    assert foreign_keys(children.iloc[[0, 2]], parents, ("source_system", "customer_id"),
                        nullable_key="customer_id").status == "PASS"


def test_money_mismatch_and_decimal_aggregation():
    assert monetary_total(["0.1", "0.2"]) == Decimal("0.3")
    assert compare("ledger", monetary_total(["0.10", "0.20"]), Decimal("0.31")).status == "FAIL"


def test_correct_flags_preserve_returns_adjustments_zero_negative_prices(tmp_path):
    *_, lines = prepare_frames(make_source(tmp_path))
    assert line_business_rules(lines).status == "PASS"


@pytest.mark.parametrize("flag", [
    "is_cancellation", "is_bad_debt_adjustment", "is_negative_quantity", "is_return",
    "is_inventory_adjustment", "has_customer_id", "has_description", "has_valid_price",
    "is_price_zero", "is_price_negative", "is_non_product", "is_valid_sale",
])
def test_business_rule_violations_detected_offline(tmp_path, flag):
    *_, lines = prepare_frames(make_source(tmp_path))
    lines.loc[0, flag] = not bool(lines.loc[0, flag])
    result = line_business_rules(lines)
    assert result.status == "FAIL"
    assert result.actual[flag] == 1


def test_raw_price_flags_are_preserved_at_rounded_zero(tmp_path):
    from .test_source import raw_row
    *_, lines = prepare_frames(make_source(tmp_path, [raw_row("1", price=0.001)]))
    assert lines.iloc[0]["unit_price"] == 0
    assert line_business_rules(lines).status == "PASS"
    assert line_business_rules(lines, prices_are_rounded=False).status == "FAIL"

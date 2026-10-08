from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from src.data.clean import clean_data
from src.data.ingest import ORIGINAL_COLUMNS
from src.data.load import prepare_frames
from src.quality.source import (
    FLAGS, copy_money, fingerprint, record_differences, source_expectations,
)


def raw_row(invoice="100", quantity=1, price=2.0, customer=123, code="100"):
    return dict(zip(ORIGINAL_COLUMNS, [
        invoice, code, "Widget", quantity, "2011-01-01", price, customer, "UK",
    ]))


def make_source(tmp_path: Path, rows=None):
    rows = rows if rows is not None else [
        raw_row(), raw_row(), raw_row("C100", -1),
        raw_row("200", -1, 0, None), raw_row("300", 1, 5, None, "POST"),
        raw_row("400", 0), raw_row("500", 1, -1), raw_row("A100", 1),
    ]
    frame = clean_data({"fixture": pd.DataFrame(rows)})
    path = tmp_path / "source.parquet"
    frame.to_parquet(path, index=False)
    return path


def test_source_counts_preserve_guests_duplicates_and_specials(tmp_path):
    expected = source_expectations(make_source(tmp_path), batch_size=2)
    assert expected["row_counts"] == {
        "customers": 1, "products": 2, "invoices": 7, "invoice_lines": 8,
    }
    assert expected["flag_counts"]["guest_lines"] == 2
    assert expected["flag_counts"]["is_duplicate_within_sheet"] == 2
    assert expected["flag_counts"]["is_cancellation"] == 1
    assert expected["flag_counts"]["is_inventory_adjustment"] == 1
    assert expected["flag_counts"]["is_bad_debt_adjustment"] == 1
    assert expected["flag_counts"]["is_price_negative"] == 1
    assert expected["money"]["gross_sales"] == Decimal("4.00")
    assert expected["money"]["merchandise_returns"] == Decimal("-2.00")
    assert expected["money"]["ledger"] == Decimal("8.00")


def test_source_fingerprints_match_existing_loader_and_batch_boundaries(tmp_path):
    path = make_source(tmp_path)
    expected = source_expectations(path, batch_size=1)
    *_, lines = prepare_frames(path)
    # COPY converts price to two-decimal values; database returns Decimal.
    records = lines.to_dict("records")
    for row in records:
        row["unit_price"] = copy_money(row["unit_price"])
    assert record_differences(expected["record_hashes"], records) == {
        "missing": 0, "extra": 0, "changed": 0,
    }
    assert source_expectations(path, batch_size=3)["record_hashes"] == expected["record_hashes"]


def test_missing_extra_same_count_and_changed_record_detection(tmp_path):
    path = make_source(tmp_path, [raw_row("1"), raw_row("2")])
    expected = source_expectations(path)
    *_, lines = prepare_frames(path)
    rows = lines.to_dict("records")
    assert record_differences(expected["record_hashes"], rows[:1])["missing"] == 1
    replaced = [dict(rows[0]), dict(rows[1], source_row_number=3)]
    assert record_differences(expected["record_hashes"], replaced) == {
        "missing": 1, "extra": 1, "changed": 0,
    }
    changed = [dict(rows[0], quantity=5), rows[1]]
    assert record_differences(expected["record_hashes"], changed)["changed"] == 1


@pytest.mark.parametrize("column", ["Invoice", "StockCode", "Quantity", "Price", "source_sheet",
                                  "is_valid_sale"])
def test_missing_required_columns_are_rejected(tmp_path, column):
    path = make_source(tmp_path)
    frame = pd.read_parquet(path).drop(columns=[column])
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing required"):
        source_expectations(path)


@pytest.mark.parametrize("column", ["Invoice", "Quantity", "Price", "is_valid_sale"])
def test_missing_required_values_are_rejected(tmp_path, column):
    path = make_source(tmp_path)
    frame = pd.read_parquet(path)
    frame.loc[0, column] = None
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="NULL values"):
        source_expectations(path)


def test_source_price_rounding_matches_loader_copy_not_binary_float(tmp_path):
    path = make_source(tmp_path, [raw_row("1", 3, 0.105)])
    expected = source_expectations(path)
    *_, lines = prepare_frames(path)
    wanted = copy_money(lines.iloc[0]["unit_price"]) * 3
    assert expected["money"]["ledger"] == wanted == Decimal("0.30")


def test_zero_batch_and_unreadable_source_errors(tmp_path):
    with pytest.raises(ValueError, match="batch_size"):
        source_expectations(make_source(tmp_path), batch_size=0)
    with pytest.raises((FileNotFoundError, OSError)):
        source_expectations(tmp_path / "missing.parquet")


def test_source_rejects_inconsistent_business_flags(tmp_path):
    path = make_source(tmp_path)
    frame = pd.read_parquet(path)
    frame.loc[0, "is_valid_sale"] = False
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="business flags"):
        source_expectations(path)


def test_source_handles_raw_nonzero_prices_rounding_to_zero(tmp_path):
    path = make_source(tmp_path, [raw_row("1", 1, 0.001), raw_row("2", 1, -0.001)])
    expected = source_expectations(path)
    assert expected["money"]["ledger"] == Decimal("0.00")
    assert expected["flag_counts"]["has_valid_price"] == 1
    assert expected["flag_counts"]["is_price_negative"] == 1

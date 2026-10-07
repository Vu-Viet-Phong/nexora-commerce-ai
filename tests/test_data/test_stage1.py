from pathlib import Path

import pandas as pd

from src.data.clean import clean_data
from src.data.ingest import ORIGINAL_COLUMNS, file_checksum, load_excel_cached
from src.data.validate import validate_data


def _row(invoice: str, quantity: int = 1) -> dict:
    return dict(
        zip(
            ORIGINAL_COLUMNS,
            [invoice, "100", "Widget", quantity, "2011-01-01", 2.0, 12345, "UK"],
        )
    )


def test_cross_sheet_duplicates_are_deduplicated_but_within_sheet_are_flagged():
    duplicate = _row("1")
    sheets = {
        "a": pd.DataFrame([duplicate, duplicate]),
        "b": pd.DataFrame([duplicate, _row("2", -1)]),
    }
    cleaned = clean_data(sheets)
    assert len(cleaned) == 3
    assert cleaned["is_duplicate_within_sheet"].sum() == 2
    assert cleaned["is_duplicate_cross_sheet"].sum() == 2
    assert cleaned["is_return"].sum() == 1


def test_validation_reports_required_fields():
    frame = pd.DataFrame([_row("1")])
    assert validate_data(frame)["is_valid"]
    broken = frame.drop(columns=["Invoice"])
    assert not validate_data(broken)["is_valid"]


def test_excel_cache_reuses_checksum_manifest(tmp_path: Path):
    source = tmp_path / "source.xlsx"
    pd.DataFrame([_row("1")]).to_excel(source, index=False, sheet_name="Year 2009-2010")
    cache = tmp_path / "cache"
    first = load_excel_cached(source, cache)
    second = load_excel_cached(source, cache)
    assert list(first) == list(second) == ["Year 2009-2010"]
    assert file_checksum(source)
    assert (cache / "manifest.json").exists()


def test_business_flags_cover_audit_cases():
    frame = pd.DataFrame(
        [
            _row("C100", -1),
            _row("2", -1),
            _row("A100", 1),
            dict(zip(ORIGINAL_COLUMNS, ["3", "POST", None, -1, "2011-01-01", 0.0, None, "UK"])),
            dict(zip(ORIGINAL_COLUMNS, ["4", "100", "Widget", 1, "2011-01-01", -1.0, 12345, "UK"])),
        ]
    )
    cleaned = clean_data({"sheet": frame})
    assert cleaned.loc[0, "is_cancellation"]
    assert cleaned.loc[1, "is_negative_quantity"]
    assert cleaned.loc[2, "is_bad_debt_adjustment"]
    assert cleaned.loc[3, "is_inventory_adjustment"]
    assert cleaned.loc[3, "is_non_product"]
    assert cleaned.loc[4, "is_price_negative"]


def test_missing_customer_and_description_are_retained_and_flagged():
    row = _row("1")
    row["Customer ID"] = None
    row["Description"] = None
    cleaned = clean_data({"sheet": pd.DataFrame([row])})
    assert len(cleaned) == 1
    assert not cleaned.loc[0, "has_customer_id"]
    assert not cleaned.loc[0, "has_description"]


def test_validation_rejects_invalid_datetime_and_missing_flag():
    frame = clean_data({"sheet": pd.DataFrame([_row("1")])})
    frame["InvoiceDate"] = pd.Series(["not-a-date"])
    result = validate_data(frame, require_flags=True)
    assert not result["is_valid"]
    assert any(error.startswith("invalid_datetime") for error in result["errors"])
    assert not validate_data(frame.drop(columns=["is_valid_sale"]), require_flags=True)["is_valid"]

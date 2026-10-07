"""Stage 1 pipeline: ingest, clean, validate, and persist explainable outputs."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from .clean import clean_data
from .ingest import load_excel_cached
from .validate import validate_data


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def run_stage1(
    raw_path: str | Path,
    *,
    interim_dir: str | Path = "data/interim",
    output_dir: str | Path = "data/processed",
    force_reload: bool = False,
) -> dict[str, Any]:
    """Run one pipeline pass and return metrics plus the processed frame."""
    started = time.perf_counter()
    interim = Path(interim_dir)
    output = Path(output_dir)
    interim.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    load_started = time.perf_counter()
    sheets = load_excel_cached(
        raw_path,
        interim / "cache",
        manifest_path=interim / "raw_manifest.json",
        force=force_reload,
    )
    excel_or_cache_seconds = time.perf_counter() - load_started
    raw_rows = sum(len(frame) for frame in sheets.values())
    raw_dates = pd.concat(
        [pd.to_datetime(frame["InvoiceDate"], errors="coerce") for frame in sheets.values()],
        ignore_index=True,
    )
    expected_date_min = raw_dates.min()
    expected_date_max = raw_dates.max()
    raw_interim = pd.concat(
        [frame.assign(source_sheet=name) for name, frame in sheets.items()],
        ignore_index=True,
        sort=False,
    )
    # Excel identifiers are mixed numeric/text; string dtype keeps all values
    # representable in the intermediate Parquet without changing source frames.
    for column in raw_interim.columns:
        if raw_interim[column].dtype != "object":
            continue
        raw_interim[column] = raw_interim[column].astype("string")
    raw_interim.to_parquet(interim / "transactions_raw.parquet", index=False)
    cleaned = clean_data(sheets)
    cross_removed = int(cleaned.attrs.get("cross_sheet_duplicates_removed", 0))
    within_detected = int(cleaned.attrs.get("within_sheet_duplicates_detected", 0))
    validation = validate_data(
        cleaned,
        raw_rows=raw_rows,
        cross_sheet_duplicates_removed=cross_removed,
        require_flags=True,
        expected_date_min=expected_date_min,
        expected_date_max=expected_date_max,
    )
    if not validation["is_valid"]:
        raise ValueError("Data validation failed: " + "; ".join(validation["errors"]))

    processed_path = output / "transactions_clean.parquet"
    cleaned.to_parquet(processed_path, index=False)
    reloaded = pd.read_parquet(processed_path)
    reloaded_validation = validate_data(
        reloaded,
        raw_rows=raw_rows,
        cross_sheet_duplicates_removed=cross_removed,
        require_flags=True,
        expected_date_min=expected_date_min,
        expected_date_max=expected_date_max,
    )
    if not reloaded_validation["is_valid"]:
        raise ValueError("Processed parquet validation failed: " + "; ".join(reloaded_validation["errors"]))

    summary = {
        "raw_rows": int(raw_rows),
        "cross_sheet_duplicates_removed": cross_removed,
        "rows_retained": int(len(cleaned)),
        "rows_removed": int(raw_rows - len(cleaned)),
        "removal_reasons": {"cross_sheet_exact_duplicate": cross_removed},
        "rows_retained_flagged": int((~cleaned["is_valid_sale"]).sum()),
        "cancellations": int(cleaned["is_cancellation"].sum()),
        "inventory_adjustments": int(cleaned["is_inventory_adjustment"].sum()),
        "bad_debt_adjustments": int(cleaned["is_bad_debt_adjustment"].sum()),
        "missing_customer_id": int((~cleaned["has_customer_id"]).sum()),
        "missing_description": int((~cleaned["has_description"]).sum()),
        "price_zero": int(cleaned["is_price_zero"].sum()),
        "price_negative": int(cleaned["is_price_negative"].sum()),
        "duplicate_within_sheet_detected": within_detected,
        "duplicate_cross_sheet_flagged": int(cleaned["is_duplicate_cross_sheet"].sum()),
        "validation": reloaded_validation,
        "excel_or_cache_load_seconds": round(excel_or_cache_seconds, 3),
        "total_pipeline_seconds": round(time.perf_counter() - started, 3),
    }
    (output / "cleaning_summary.json").write_text(
        json.dumps(summary, indent=2, default=_json_default),
        encoding="utf-8",
    )
    return {
        "sheets": sheets,
        "cleaned": reloaded,
        "validation": reloaded_validation,
        "summary": summary,
        "processed_path": processed_path,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    result = run_stage1(
        root / "data" / "raw" / "uci" / "online_retail_II.xlsx",
        interim_dir=root / "data" / "interim",
        output_dir=root / "data" / "processed",
    )
    print(json.dumps(result["summary"], indent=2, default=_json_default))


if __name__ == "__main__":
    main()

"""Immutable ingestion and checksum-aware caching for Online Retail II."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ORIGINAL_COLUMNS = (
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
)


def file_checksum(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_manifest_path(cache_dir: Path) -> Path:
    return cache_dir / "manifest.json"


def _load_cache_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _relative_source(source: Path) -> str:
    return source.as_posix().split("data/raw/", 1)[-1] if "data/raw/" in source.as_posix() else source.name


def write_raw_manifest(
    source: str | Path,
    sheets: dict[str, pd.DataFrame],
    destination: str | Path,
    *,
    checksum: str | None = None,
) -> dict[str, Any]:
    """Write a portable manifest describing the immutable source workbook."""
    source_path = Path(source)
    frames = list(sheets.values())
    date_values = pd.concat(
        [pd.to_datetime(frame["InvoiceDate"], errors="coerce") for frame in frames],
        ignore_index=True,
    ) if frames and all("InvoiceDate" in frame for frame in frames) else pd.Series(dtype="datetime64[ns]")
    manifest = {
        "source": "data/raw/uci/online_retail_II.xlsx",
        "filename": source_path.name,
        "sha256": checksum or file_checksum(source_path),
        "file_size_bytes": source_path.stat().st_size,
        "sheet_names": list(sheets),
        "rows_per_sheet": {name: int(len(frame)) for name, frame in sheets.items()},
        "total_rows": int(sum(len(frame) for frame in frames)),
        "columns": list(frames[0].columns) if frames else [],
        "date_min": date_values.min().isoformat() if date_values.notna().any() else None,
        "date_max": date_values.max().isoformat() if date_values.notna().any() else None,
        "manifest_timestamp": datetime.now(timezone.utc).isoformat(),
    }
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    destination_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_excel_cached(
    path: str | Path,
    cache_dir: str | Path | None = None,
    *,
    manifest_path: str | Path | None = None,
    force: bool = False,
) -> dict[str, pd.DataFrame]:
    """Read all sheets once, or reuse a cache only when the SHA-256 matches."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Raw workbook not found: {source}")
    cache = Path(cache_dir) if cache_dir else source.parent / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    checksum = file_checksum(source)
    cache_manifest_path = _cache_manifest_path(cache)
    cached_manifest = _load_cache_manifest(cache_manifest_path)
    if not force and cached_manifest.get("sha256") == checksum:
        cached = {
            name: cache / filename
            for name, filename in cached_manifest.get("sheets", {}).items()
        }
        if cached and all(file.is_file() for file in cached.values()):
            sheets = {name: pd.read_pickle(file) for name, file in cached.items()}
            if manifest_path is not None:
                write_raw_manifest(source, sheets, manifest_path, checksum=checksum)
            return sheets

    # One pandas read for the complete workbook; no per-sheet Excel reads.
    sheets = pd.read_excel(source, sheet_name=None)
    cache_files: dict[str, str] = {}
    for index, (name, frame) in enumerate(sheets.items()):
        filename = f"{checksum[:16]}_{index}.pkl"
        frame.to_pickle(cache / filename)
        cache_files[name] = filename
    cache_manifest_path.write_text(
        json.dumps(
            {
                "sha256": checksum,
                "sheets": cache_files,
                "shapes": {name: list(frame.shape) for name, frame in sheets.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if manifest_path is not None:
        write_raw_manifest(source, sheets, manifest_path, checksum=checksum)
    return sheets


def ingest_excel(path: str | Path, cache_dir: str | Path | None = None) -> dict[str, pd.DataFrame]:
    return load_excel_cached(path, cache_dir)

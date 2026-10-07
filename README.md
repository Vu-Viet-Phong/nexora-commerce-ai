# Nexora-Commerce-AI

## Project overview

Nexora-Commerce-AI is an end-to-end E-Commerce Intelligence project covering data engineering, analytics, machine learning, and future AI capabilities.

## Current development stage

Stage 1 complete: ingestion, checksum-aware interim cache, cleaning flags,
validation, processed Parquet, manifest, summaries, tests, and initial audit.

## Project structure

- `configs/`: project configuration
- `data/`: raw, interim, and processed data
- `notebooks/`: exploratory and audit notebooks
- `src/data/`: data ingestion, cleaning, and validation modules
- `tests/`: testing foundation
- `docs/`: project and data documentation

## Stage 1 pipeline

The raw workbook is never modified. The loader computes a SHA-256 checksum and
reuses sheet-level caches with a manifest. Cleaning preserves within-sheet
duplicates as quality flags, removes only exact cross-sheet repeats, and keeps
returns/cancellations and missing values visible. Run the pipeline from the
repository root:

```python
python -m src.data.pipeline
```

The first run reads the workbook once and creates a checksum-keyed cache.
Later runs reuse the cache when the raw checksum is unchanged. Outputs are
`data/interim/transactions_raw.parquet`,
`data/interim/raw_manifest.json`,
`data/processed/transactions_clean.parquet`, and
`data/processed/cleaning_summary.json`. See `docs/data_audit.md` for observed
facts and cleaning decisions.

Project Development & Learning Log:
[docs/PROJECT_LEARNING_LOG.md](docs/PROJECT_LEARNING_LOG.md)

## Data source placeholder

The `Online Retail II` dataset will be placed manually in `data/raw/uci/`.

## Roadmap placeholder

Future stages will add analytics, machine learning, recommendation, multimodal search, LLM, API, and MLOps capabilities.

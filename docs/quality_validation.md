# Milestone 2.5 — relational-core quality validation

Implementation branch: `feat/stage2-data-quality`, based on pushed
`origin/main` at `a9710c2829d00b28b7cd69c2a00130fc94193780`.
Milestone 2.5 is implemented in checkpoints, **not marked APPROVED**.
Milestone 2.4 remains an explicit integration dependency even though mart files
are present in the base commit.

Checkpoint A provides reusable aggregate result comparison, schema contracts,
32 core SQL checks and a read-only runner. Queries use a repeatable-read snapshot,
bound source parameters and per-check savepoints. Missing schema skips dependent
checks. No code reads `.env`; callers supply an engine created from their
process configuration. Reports contain counts/aggregates, not source rows.

Run the independent offline suite from the isolated worktree:

```powershell
python -m pytest tests/test_quality/test_core.py -q
```

The runner checks schema presence/nullability, NUMERIC precision and scale,
required values, four source-scoped grains, line identity and position, four
foreign keys, deterministic source keys, source quality flags, invoice type,
line arithmetic, invoice ledger, customer merchandise spend and join fanout.
Guest customer IDs and source-flagged special/duplicate lines are retained;
their presence is informational. A quantity of zero is profiled rather than
rejected using a business rule that the project has never approved.

The financial checks deliberately surface disagreements between stored header/
customer totals and exact line NUMERIC aggregates. They do not silently widen
tolerances or modify the existing loader. Source reconciliation and CLI follow
in the next checkpoints. All three marts currently emit SKIP.

## Checkpoint B — offline and isolated PostgreSQL tests

Source reconciliation now compares row counts, source-scoped dimension keys,
15 flag counts plus guest count, exact monetary aggregates, line payload
fingerprints and all four tables' Parquet provenance. A replacement record with
the same total row count fails the missing/extra check. Parquet is processed in
50,000-row batches; fingerprints/entity hashes remain in memory, so memory
still scales with source cardinality. No source rows are written to reports.

Offline DataFrame helpers cover required fields, approved grains, nullable
source-scoped foreign keys, the existing line-flag rules and Decimal sums.

```powershell
python -m pytest tests/test_quality -q
# Only use a dedicated Codex-owned database named nexora_quality_codex_test:
# Set NEXORA_QUALITY_TEST_DATABASE_URL in this process using your secret manager.
python -m pytest tests/test_quality --quality-postgres -q
# Full data is separately opt-in; set NEXORA_QUALITY_SOURCE to the Parquet path.
python -m pytest tests/test_quality --quality-postgres --quality-full-data -q
```

Validated on Python 3.11.16 and private PostgreSQL 16.15: 50 offline tests
passed (21 integration/full-data tests skipped); with --quality-postgres,
70 tests passed and the one full-data test remained skipped. The private
instance used loopback port 59165 and never connected to the shared test DB.

These counts describe checkpoint B fixtures, not the real million-row dataset.
The full-data test checks source reconciliation; review the complete report
separately for core financial discrepancies caused by loader rounding.

# Milestone 2.5 — relational-core quality validation

Implementation branch: `feat/stage2-data-quality`, based on pushed
`origin/main` at `a9710c2829d00b28b7cd69c2a00130fc94193780`.
Core, Parquet reconciliation, offline/SQL tests and CLI reporting are implemented.
Milestone 2.5 is **not marked APPROVED**.
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
in the next checkpoints (now implemented below). All three marts currently emit SKIP.

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

## Checkpoint C — CLI, reporting and quality gate

Run with the project's Python environment active. Supply an already URL-encoded
`DATABASE_URL` through process configuration/your secret manager. The CLI never
loads `.env` and does not accept credentials on the command line.

```powershell
python -m src.quality --help
# DATABASE_URL must already exist in the process environment.
python -m src.quality --source-system UCI --schema public --source "D:/data science/nexora-commerce-ai/nexora-commerce-ai/data/processed/transactions_clean.parquet" --json-out "quality-report.json" --markdown-out "quality-report.md"
$LASTEXITCODE
```

Choose report destinations outside Git or leave them untracked; generated reports
are not part of this branch. They contain aggregates, statuses, expected/actual
values, per-check runtime, failure reasons, UTC generation time and a summary.
Decimal money is serialized as exact strings, not converted back to float.

| Exit code | Meaning |
|---|---|
| 0 | Every relational-core/source gate check passed. Deferred marts do not participate in this gate. |
| 1 | A validation, database configuration/query, source contract or report-write check failed. |
| 2 | Gate coverage is incomplete, for example no Parquet source was supplied; invalid CLI arguments also use argparse exit 2. |

`summary` includes **all** checks, so it remains SKIP while marts are deferred.
`gate_summary` explicitly covers relational core and source; it can be PASS
without claiming complete mart coverage. An empty result set never passes.

The runner uses only SELECT and read-only transaction/savepoint control, with
a per-statement timeout (default 120,000 ms) and 10-second connection timeout
in the CLI. Existing indexes are reused. This timeout is not a whole-run budget.
Query text/parameters/driver exception strings are not written to reports.

Raw Stage 1 price flags are preserved through the loader's rounding. A raw price
of 0.001 can legitimately have `has_valid_price=True` while stored price is
0.00. Nonzero stored prices must agree with their sign flags; at zero, exactly
one original price category must be set. Parquet raw flags are validated before
rounding. Fingerprints normalize negative zero to PostgreSQL NUMERIC zero.

Final checkpoint C validation on Python 3.11.16 / PostgreSQL 16.15:

| Suite | Result | Runtime |
|---|---|---:|
| Quality + Stage 1, offline | 72 passed, 24 skipped | 3.23 s |
| Quality with private PostgreSQL, including CLI subprocesses | 88 passed, 1 skipped | 11.53 s |
| Existing static schema, --noconftest | 8 passed | 0.06 s |
| Persisted PASS/FAIL CLI evidence fixtures | 2 passed | 4.49 s |

The one opt-in full-data test remains unrun. Fixture evidence is **not** a
certification of the 1,044,848-row development warehouse. Source reconciliation
currently supports UCI, as the loader does. It validates exact line payloads,
dimension key sets and provenance; it does not compare every descriptive
dimension attribute with its source-derived mode/median.

## Merge preparation

See [Vietnamese learning notes](learning/stage_02_data_quality.md),
[learning-log integration text](learning/stage_02_data_quality_log_update.md)
and [deferred mart contracts](quality_marts_integration.md).
No existing SQL mart, Copilot test, loader, project learning log or milestone
approval document is changed by this feature. After Milestone 2.4 approval,
revalidate the feature against the integrated mart contracts before approval.

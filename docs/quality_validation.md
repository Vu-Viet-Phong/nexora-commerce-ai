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

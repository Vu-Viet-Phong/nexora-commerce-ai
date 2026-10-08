# Full-data experiment — Milestone 2.5

This is Codex's experiment log, not a replacement for independent review or
acceptance documents. Milestone 2.5 remains unapproved.

## Evidence and isolation

Run on Python 3.11.16 / private PostgreSQL 16.15, loopback port 59165,
database `nexora_quality_codex_test`, schema `codex_quality_full_20261008_review`.
The input is the existing immutable `transactions_clean.parquet`, 1,044,848 rows,
SHA-256 `69bd19f7e29712ade31d9927b516411a599b32afdb7e2f983de5ee4539d1292a`.
No .env is read. Setup calls the existing loader API, not its .env-loading CLI.
Only the private sandbox is written; validation is read-only.

## First full-data run: enforcement metadata added

| Phase | Wall seconds | Validation seconds | Python peak working set bytes | Python peak commit bytes |
|---|---:|---:|---:|---:|
| Existing loader + private schema setup | 181.722055 | — | 1,254,895,616 | 1,776,988,160 |
| Validation + financial diagnostics | 161.389804 | 159.932525 | 613,076,992 | 976,654,336 |

Memory uses Windows GetProcessMemoryInfo lifetime high-water counters in separate
Python processes for load and validation. Working set is resident process memory;
peak commit uses PeakPagefileUsage. Imports and phase orchestration are included.
These figures exclude PostgreSQL server processes, the OS cache and other apps;
they are not whole-system peak memory or Python-only heap measurements.

The validation report contains **51 checks: 48 PASS, 0 FAIL, 3 SKIP**.
The core/source gate is PASS; overall coverage is SKIP because marts are deferred.

Executed: required columns/nullability/NUMERIC; four enforcement metadata
checks; source population; all 32 core SELECT checks; special/missing profile;
all seven source checks. In particular, all 1,044,848 line payloads were compared:
missing=0, extra=0, changed=0. Four-table counts are customers=5,942,
products=5,131, invoices=53,628, invoice_lines=1,044,848. Dimension key sets,
15 flag counts, guest count, exact normalized monetary aggregates and provenance
all pass. The source checksum remains unchanged.

Financial diagnostics: invoice mismatched groups=0 and customer mismatched
groups=0; signed/absolute/max deltas are all 0.00. Stored NUMERIC ledger is
18,909,762.10; pre-rounding Parquet ledger is 18,909,762.12; delta is -0.02.
This is the documented loader normalization difference, not a failed source
comparison. Normalized Parquet expectations match the database exactly.
No tolerance was increased to turn a failure into a pass.

The generated JSON/Markdown reports and load/validation metrics are kept outside
Git under this chat's `quality_full_review` evidence directory. Only the
aggregate findings are documented here.

## Why metadata checks were required

Acceptance requires actual enforced primary/foreign/unique constraints and
indexes, not just duplicate/orphan-free contents. The minimal metadata module
queries pg_constraint/pg_index in the caller's read-only snapshot. It checks:

- Four PK definitions, including global invoice_lines(line_id).
- Four source-composite FKs: correct parent/schema/key order, validated state,
  ON DELETE RESTRICT, default NO ACTION on update and valid/ready backing index.
- Two invoice_lines UNIQUE constraints in the accepted order.
- Six named DDL indexes: table/key order, btree, nonunique, valid/ready, no
  partial predicate or expression replacing the required plain index.

It intentionally follows actual schema.sql, not proposed indexes on historical
fact/dim names. Metadata failures do not suppress independent data-content checks.

Tests: offline quality suite 84 passed/29 skipped in 4.76 s; private PostgreSQL
quality suite 112 passed/1 skipped in 18.93 s. The separate full-data probe ran
all core/source checks; the pytest full-data case is still opt-in.

## Milestone 2.4 approval audit

Remote main is `b2d16ed05b40af98935eba796075345be0d33e6e`.
The live main checklist marks mart QA matrix rows 13/14 PASSED, but its header
and sign-off history still stop at Milestone 2.3 APPROVED. The data-model review
also says Milestone 2.3 APPROVED and authorizes proceeding to 2.4.
There is no official 2.4 APPROVED sign-off in the accessible repository.

Therefore all three mart checks remain SKIP. No mart objects are installed or
queried by this experiment. Approval is the blocker for activating those checks;
the existing preparation contracts must be reconfirmed after formal sign-off.

## Reproduce the opt-in experiment

Activate the existing Python environment and inject the URL of your own dedicated
test database in NEXORA_QUALITY_TEST_DATABASE_URL. Do not pass passwords in argv.
Use a fresh codex_quality_full_ schema; load refuses to overwrite an existing one.

```powershell
python -m tests.test_quality.full_data_probe --phase load --source "D:/data science/nexora-commerce-ai/nexora-commerce-ai/data/processed/transactions_clean.parquet" --schema codex_quality_full_fresh --output-dir "C:/your-evidence/full-load"
python -m tests.test_quality.full_data_probe --phase validate --source "D:/data science/nexora-commerce-ai/nexora-commerce-ai/data/processed/transactions_clean.parquet" --schema codex_quality_full_fresh --output-dir "C:/your-evidence/full-validation"
```

The dataset must contain exactly 1,044,848 rows. The probe requires the dedicated
database identity and a Codex-owned schema prefix. It never modifies main or
other assistants' review documents.

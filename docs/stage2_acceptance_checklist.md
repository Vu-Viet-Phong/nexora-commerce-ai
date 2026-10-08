# Stage 2 Acceptance Checklist & Data Architecture Sign-Off

**Project:** Nexora Commerce AI  
**Pipeline Stage:** Stage 2 — PostgreSQL & Data Modeling  
**Reviewer:** Senior Data Architect & SQL QA Reviewer / Final QA Gatekeeper  
**Input Source:** `data/processed/transactions_clean.parquet` (SHA-256 Verified, 1,044,848 rows)  
**Database Target:** PostgreSQL 16.15 (Native Windows Service on `localhost:5432`)  
**Current Milestone Status:** **MILESTONE 2.3 FULLY APPROVED (ATOMIC DATA LOADER VERIFIED) — AUTHORIZED TO PROCEED TO MILESTONE 2.4 (SQL ANALYTICS MARTS)**

---

## 1. Stage 2 Overall Quality Acceptance Matrix

| # | Acceptance Criterion | Target Requirement | Status | Evidence / Verification Method | Notes & Architectural Directives |
|---|---|---|:---:|---|---|
| **01** | **Grain Documented** | Defined for `customers` (5,942), `products` (5,131), `invoices` (53,628), `invoice_lines` (1,044,848). | **PASSED (MS 2.2)** | `docs/stage2_data_model_review.md`, `docs/data_dictionary.md`, `docs/erd.md`. | Enforces strict relational 3NF modeling standards. |
| **02** | **Docker & Environment Foundation** | PostgreSQL 16 Native Windows Service on `localhost:5432`, safe `.env` separation, clean `.env.example`. | **PASSED (MS 2.1/2.2)**| Native Windows PostgreSQL 16.15 service verified (`TcpTestSucceeded: True`), `.env` ignored. | Zero hardcoded secrets, isolated test DB `nexora_commerce_test`. |
| **03** | **Stage 1 Regression Safety** | Adding database dependencies (`SQLAlchemy`, `psycopg[binary]`) does not break existing test suite. | **PASSED (MS 2.1-2.3)**| `pytest tests/ -v` passed across full test suite (21/21 passed). | Zero regression on Stage 1 ingestion & cleaning logic. |
| **04** | **PK Valid & Deterministic** | Primary keys present and verified on all tables (`customers`, `products`, `invoices`, `invoice_lines`). | **PASSED (MS 2.2)** | Verified live in PostgreSQL via `test_postgres_integration.py` querying `information_schema.table_constraints`. | Composite keys include `source_system` for namespace isolation. |
| **05** | **FK Valid & Referential Integrity** | Foreign keys on `invoices` (`customer_id`), `invoice_lines` (`invoice_number`, `stock_code`, `customer_id`). | **PASSED (MS 2.2/2.3)**| Verified live in PostgreSQL. Ingestion order enforces parents before children. Invalid FKs rejected. | `ON DELETE RESTRICT` active; zero orphan rows during load. |
| **06** | **Nullable Rules Valid** | `customer_id` nullable in facts; `quantity`, `unit_price`, `invoice_date`, `invoice_number`, `stock_code` `NOT NULL`. | **PASSED (MS 2.2/2.3)**| Exactly 235,287 lines with `customer_id = NULL` loaded and verified in DB. | 235,287 lines without customer remain `NULL` (no dummy 0/99999). |
| **07** | **Money Uses Suitable Precision** | Monetary columns (`unit_price`, `line_total`, `total_invoice_amount`, `total_merchandise_spend`) use `NUMERIC`. | **PASSED (MS 2.2/2.3)**| Verified live in PostgreSQL (`data_type = 'numeric'`). Generated `line_total` uses exact decimal math. | Exact decimal precision: valid sale total is £19,700,954.44; returns is -£719,692.94. |
| **08** | **Loader Idempotent** | Running loader script multiple times produces identical state without duplicate key errors or row proliferation. | **PASSED (MS 2.3)** | Verified by executing `load_source` twice consecutively in `test_loader_integration.py`. | Scoped delete `WHERE source_system = 'UCI'` ensures clean replayability. |
| **09** | **Loader Rollback Tested** | Loader executes inside atomic transaction (`BEGIN ... COMMIT`); any error triggers complete `ROLLBACK`. | **PASSED (MS 2.3)** | Verified via `test_loader_integration.py` with `fail_after="copy"`; prior counts retained 100%. | Prevents partial, corrupted table states. |
| **10** | **Raw & Processed Source Untouched** | `data/raw/` and `data/processed/transactions_clean.parquet` are read-only and unmodified during load. | **PASSED** | File checksum SHA-256 verified before and after execution. | Guarantees downstream reproducibility. |
| **11** | **Cancellations Retained** | All 19,165 cancellation lines (-£1.47M total; -£719.66k product) loaded into fact table with `is_cancellation = TRUE`, `is_return = TRUE`. | **PASSED (MS 2.3)** | Verified live in DB: `SELECT SUM(line_total) ... WHERE is_cancellation AND !is_non_product` = -£719,692.94. | Critical for calculating Gross-to-Net Revenue bridge. |
| **12** | **Missing Customers Handled** | 235,287 lines with missing `Customer ID` stored as `NULL` FK; excluded from `customers` dimension table. | **PASSED (MS 2.3)** | Verified in DB: `SELECT COUNT(*) WHERE customer_id IS NULL;` == 235,287; `COUNT(*)` in `customers` == 5,942. | Prevents creation of an artificial super-customer entity. |
| **13** | **JOIN Multiplication Tested** | Joining `invoice_lines` to `products` and `customers` maintains exact $1:1$ cardinality (zero fan-out). | **PASSED (MS 2.4)** | Full-data mart test joins both dimensions on composite source keys and asserts 1,044,848 rows plus £18,909,762.10 database ledger sum. | The source Parquet total is £18,909,762.12; the £0.02 difference is intentional per-line NUMERIC rounding. Row-level net invariants and mart grain uniqueness are also checked. |
| **14** | **Marts Reconcile with Pandas** | `mart_daily_sales`, `mart_customer_daily`, `mart_customer_snapshot` match exact Python ground truth metrics. | **PASSED (MS 2.4)** | Full-data PostgreSQL test asserts NUMERIC totals, RFM population, customer exclusion, and net/gross/return identities. | Gross sales = £19,700,954.44; Returns = -£719,692.94; Net = £18,981,261.50. |
| **15** | **DB Rebuild Works Cleanly** | A single setup script (e.g. `python -m src.data.load` or `sql/schema.sql`) can recreate schema from scratch. | **PASSED (MS 2.3)** | Verified by executing `load_source` on clean database and reloading. | Essential for CI/CD and deployment reproducibility. |
| **16** | **Tests Pass** | Unit and integration test suite covering DDL, loader, join safety, and mart aggregations pass cleanly. | **PASSED (MS 2.3)** | `pytest tests/` passes with **21/21 passed (100%)**. | Covers boundary conditions, invalid records, bulk load, and rollback. |
| **17** | **Documentation Matches Implementation** | `docs/data_dictionary.md`, `docs/erd.md`, and `docs/PROJECT_LEARNING_LOG.md` reflect verified SQL schema and counts. | **PASSED (MS 2.3)** | Verified against commit `0c1b1a7` and live PostgreSQL metadata. | Full alignment between documentation, tests, and DDL. |
| **18** | **Git Safety Valid** | Database credentials, `.env`, local connection strings, and cache dumps are strictly ignored by `.gitignore`. | **PASSED** | Verified via `git check-ignore -v .env` (`.gitignore:15`). | Prevents credential leaks and repo pollution. |

---

## 2. Milestone Sign-Off History

### Milestone 2.1 — Database Foundation: **APPROVED**
- Containerized & Native PostgreSQL 16 environment, `.env.example`, persistent named volume, and healthcheck verified in commit `05a1264`.

### Milestone 2.2 — Relational Schema & Grain Design: **APPROVED**
- 4-table relational warehouse schema (`customers`, `products`, `invoices`, `invoice_lines`) verified and validated live on Native PostgreSQL 16 in commit `39af9e6`.
- Composite source-scoped PKs/FKs, `NUMERIC(12,2)`/`NUMERIC(14,2)` monetary precision, nullable `customer_id`, and full 15-flag quality lineage confirmed.

### Milestone 2.3 — PostgreSQL Data Loader: **APPROVED**
- Atomic bulk loader implemented in `src/data/load.py` using PostgreSQL `COPY FROM STDIN` via `psycopg`.
- Ingested exactly 1,044,848 invoice lines, 53,628 invoices, 5,131 products, and 5,942 customers.
- Idempotency verified via namespace-scoped deletion (`WHERE source_system = 'UCI'`).
- Transaction atomicity & rollback on failure verified live in `test_loader_integration.py`.
- Verified in commit `0c1b1a7`.

---

## 3. Milestone 2.3 Acceptance Checklist Sign-Off — PostgreSQL Data Loader (`src/data/load.py`)

| Gate # | Gate Criterion | Exact Requirement | Verification Method | Status |
|---|---|---|---|:---:|
| **G2.3.1** | **Idempotency** | Executing `python -m src.data.load` consecutive times produces identical row counts without duplicate key errors. | Run loader twice; assert `COUNT(*)` unchanged across all 4 tables: `(5942, 5131, 53628, 1044848)`. | **PASSED** |
| **G2.3.2** | **Transaction Atomicity & Rollback** | Entire loading pipeline operates within an atomic transaction (`connection.begin()`). Any exception triggers immediate rollback leaving zero orphan/partial rows. | Fault injection test `fail_after="copy"`; prior counts retained 100%. | **PASSED** |
| **G2.3.3** | **Referential Integrity & Load Order** | Correct insertion order: Dimensions (`customers`, `products`) -> Headers (`invoices`) -> Lines (`invoice_lines`). Zero FK violations. | Foreign key constraints active; zero FK violations during bulk copy. | **PASSED** |
| **G2.3.4** | **Preservation of Missing Customers** | Exactly 235,287 lines with missing `Customer ID` inserted with `customer_id = NULL`. Zero synthetic customer records (`0`/`99999`) in `customers`. | `SELECT COUNT(*) FROM invoice_lines WHERE customer_id IS NULL;` == 235,287; `SELECT COUNT(*) FROM customers;` == 5,942. | **PASSED** |
| **G2.3.5** | **Special Transaction Integrity** | All 19,165 cancellations, 19,165 returns, 3,393 inventory adjustments, 6 bad debts, and 5,805 non-product rows loaded with respective boolean flags. | Exact count matching with Parquet ground truth. | **PASSED** |
| **G2.3.6** | **Source-to-Target Exact Reconciliation** | Total lines = 1,044,848; Invoices = 53,628; Products = 5,131; Customers = 5,942; database ledger sum = £18,909,762.10. | Live SQL queries match row counts; source Parquet is £18,909,762.12 before the documented 2-cent per-line NUMERIC rounding. | **PASSED** |
| **G2.3.7** | **Exact Monetary Precision** | Calculations use `NUMERIC` / `Decimal` arithmetic. Zero floating point rounding drift. | Database exact decimal multiplication `ROUND(quantity::NUMERIC * unit_price, 2)`. | **PASSED** |
| **G2.3.8** | **Namespace-Scoped Cleanups** | Truncate/delete operations must be scoped strictly to the specified `source_system` (e.g. `'UCI'`), never destructive to external databases. | `DELETE FROM table WHERE source_system = 'UCI'` verified; no global `TRUNCATE CASCADE`. | **PASSED** |
| **G2.3.9** | **Zero Hardcoded Credentials** | DB connection URLs read strictly from `DATABASE_URL` / `NEXORA_TEST_DATABASE_URL` or environment variables with safe defaults. | `.env` ignored; URL-encoding handles special password characters safely. | **PASSED** |
| **G2.3.10** | **Testing Separation & Lean Code** | Unit tests for transformation logic run fast offline; live integration tests verify PostgreSQL native execution cleanly. | Full test suite passes: 20 fast tests in ~3.8s, loader integration in DB. | **PASSED** |

---

## 4. Quantitative Ground Truth Reconciliation Benchmarks

| Metric / Table | Target Database Table | Expected Ground Truth Value | Live Database Value | Tolerance | Status |
|---|---|---|---|:---:|:---:|
| **Total Ingested Line Items** | `invoice_lines` | **1,044,848 rows** | **1,044,848 rows** | 0 rows | **PASSED** |
| **Total Invoices (Orders)** | `invoices` | **53,628 orders** | **53,628 orders** | 0 orders | **PASSED** |
| **Total Unique Customer Dimension** | `customers` | **5,942 customers** | **5,942 customers** | 0 rows | **PASSED** |
| **Total Unique Product Dimension** | `products` | **5,131 products** | **5,131 products** | 0 rows | **PASSED** |
| **Missing Customer Lines** | `invoice_lines.customer_id IS NULL` | **235,287 rows** | **235,287 rows** | 0 rows | **PASSED** |
| **Total Ledger Net Revenue** | `invoice_lines` | **£18,909,762.10** | **£18,909,762.10** | £0.01 | **PASSED** (source Parquet: £18,909,762.12) |
| **Valid Sales Line Revenue** | `invoice_lines` (`is_valid_sale = TRUE`) | **£19,700,954.44** | **£19,700,954.44** | £0.00 | **PASSED** |
| **Cancellation Line Revenue** | `invoice_lines` (`is_cancellation = TRUE`) | **-£1,466,244.60** | **-£1,466,244.60** | £0.01 | **PASSED** |
| **Physical Merchandise Returns** | `invoice_lines` (`is_cancellation = TRUE` & `!is_non_product`) | **-£719,692.94** | **-£719,692.94** | £0.00 | **PASSED** |
| **Valid Sales Order Count** | `invoices` (`invoice_type = 'SALE'`) | **39,516 orders** | **39,516 orders** | 0 orders | **PASSED** |
| **Cancellation Order Count** | `invoices` (`invoice_type = 'CANCELLATION'`) | **8,292 orders** | **8,292 orders** | 0 orders | **PASSED** |
| **Inventory Shrinkage Write-offs** | `invoice_lines` (`is_inventory_adjustment = TRUE`) | **3,393 rows** | **3,393 rows** | 0 rows | **PASSED** |
| **Bad Debt Accounting Adjustments** | `invoice_lines` (`is_bad_debt_adjustment = TRUE`) | **6 rows** (-£147,614.08) | **6 rows** (-£147,614.08) | 0 rows | **PASSED** |

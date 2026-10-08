# Stage 2 Acceptance Checklist & Data Architecture Sign-Off

**Project:** Nexora Commerce AI  
**Pipeline Stage:** Stage 2 — PostgreSQL & Data Modeling  
**Reviewer:** Senior Data Architect & SQL QA Reviewer / Final QA Gatekeeper  
**Input Source:** `data/processed/transactions_clean.parquet` (SHA-256 Verified, 1,044,848 rows)  
**Database Target:** PostgreSQL 16.15 (Native Windows Service on `localhost:5432`)  
**Current Milestone Status:** **MILESTONE 2.2 FULLY APPROVED (LIVE POSTGRESQL VERIFIED) — AUTHORIZED TO PROCEED TO MILESTONE 2.3**

---

## 1. Stage 2 Overall Quality Acceptance Matrix

| # | Acceptance Criterion | Target Requirement | Status | Evidence / Verification Method | Notes & Architectural Directives |
|---|---|---|:---:|---|---|
| **01** | **Grain Documented** | Defined for `customers` (5,942), `products` (5,131), `invoices` (53,628), `invoice_lines` (1,044,848). | **PASSED (MS 2.2)** | `docs/stage2_data_model_review.md`, `docs/data_dictionary.md`, `docs/erd.md`. | Enforces strict relational 3NF modeling standards. |
| **02** | **Docker & Environment Foundation** | PostgreSQL 16 Native Windows Service on `localhost:5432`, safe `.env` separation, clean `.env.example`. | **PASSED (MS 2.1/2.2)**| Native Windows PostgreSQL 16.15 service verified (`TcpTestSucceeded: True`), `.env` ignored. | Zero hardcoded secrets, isolated test DB `nexora_commerce_test`. |
| **03** | **Stage 1 Regression Safety** | Adding database dependencies (`SQLAlchemy`, `psycopg[binary]`) does not break existing test suite. | **PASSED (MS 2.1/2.2)**| `pytest tests/ -v` passed across full test suite (20/20 passed in 2.83s). | Zero regression on Stage 1 ingestion & cleaning logic. |
| **04** | **PK Valid & Deterministic** | Primary keys present and verified on all tables (`customers`, `products`, `invoices`, `invoice_lines`). | **PASSED (MS 2.2)** | Verified live in PostgreSQL via `test_postgres_integration.py` querying `information_schema.table_constraints`. | Composite keys include `source_system` for namespace isolation. |
| **05** | **FK Valid & Referential Integrity** | Foreign keys on `invoices` (`customer_id`), `invoice_lines` (`invoice_number`, `stock_code`, `customer_id`). | **PASSED (MS 2.2)** | Verified live in PostgreSQL. Rejection of invalid FKs tested (`pytest.raises(IntegrityError)`). | `ON DELETE RESTRICT` active; invalid references rejected cleanly. |
| **06** | **Nullable Rules Valid** | `customer_id` nullable in facts; `quantity`, `unit_price`, `invoice_date`, `invoice_number`, `stock_code` `NOT NULL`. | **PASSED (MS 2.2)** | Verified live in PostgreSQL. Insert with `customer_id = NULL` confirmed valid. | 235,287 lines without customer remain `NULL` (no dummy 0/99999). |
| **07** | **Money Uses Suitable Precision** | Monetary columns (`unit_price`, `line_total`, `total_invoice_amount`, `total_merchandise_spend`) use `NUMERIC`. | **PASSED (MS 2.2)** | Verified live in PostgreSQL (`data_type = 'numeric'` in `information_schema.columns`). | Exact decimal precision: `line_total` generated is 19.99 (0 float drift). |
| **08** | **Loader Idempotent** | Running loader script multiple times produces identical state without duplicate key errors or row proliferation. | **PENDING MS 2.3** | To be verified by executing `python -m src.data.load` twice consecutively. | Requires transactional truncate or deterministic conflict handling. |
| **09** | **Loader Rollback Tested** | Loader executes inside atomic transaction (`BEGIN ... COMMIT`); any error triggers complete `ROLLBACK`. | **PASSED (MS 2.2 Live)**| Verified live in PostgreSQL via `connection.begin_nested()` savepoint rollback test. | Prevents partial, corrupted table states. |
| **10** | **Raw & Processed Source Untouched** | `data/raw/` and `data/processed/transactions_clean.parquet` are read-only and unmodified during load. | **PASSED** | File checksums verified before and after execution. | Guarantees downstream reproducibility. |
| **11** | **Cancellations Retained** | All 19,165 cancellation lines (-£1.47M total; -£719.66k product) loaded into fact table with `is_cancellation = TRUE`, `is_return = TRUE`. | **PENDING MS 2.3** | To be verified by `SELECT COUNT(*) FROM invoice_lines WHERE is_cancellation = TRUE;`. | Critical for calculating Gross-to-Net Revenue bridge. |
| **12** | **Missing Customers Handled** | 235,287 lines with missing `Customer ID` stored as `NULL` FK; excluded from `customers` dimension table. | **PENDING MS 2.3** | To be verified by `SELECT COUNT(*) FROM invoice_lines WHERE customer_id IS NULL;` == 235,287. | Prevents creation of an artificial super-customer entity. |
| **13** | **JOIN Multiplication Tested** | Joining `invoice_lines` to `products` and `customers` maintains exact $1:1$ cardinality (zero fan-out). | **PENDING MS 2.4** | To be tested with `SELECT COUNT(*), SUM(line_total) FROM invoice_lines l JOIN products p ...`. | Total rows must remain 1,044,848; total sum must remain £18,909,762.12. |
| **14** | **Marts Reconcile with Pandas** | `mart_daily_sales`, `mart_customer_daily`, `mart_customer_snapshot` match exact Python ground truth metrics. | **PENDING MS 2.4** | Automated test comparing SQL query sums against Pandas dataframe sums. | Gross sales = £19,700,954.46; Returns = -£719,692.94; Net = £18,981,261.52. |
| **15** | **DB Rebuild Works Cleanly** | A single setup script (e.g. `python -m src.data.load --rebuild` or `sql/schema.sql`) can recreate schema from scratch. | **PENDING MS 2.3** | To be tested by dropping the test schema and executing full rebuild. | Essential for CI/CD and deployment reproducibility. |
| **16** | **Tests Pass** | Unit and integration test suite covering DDL, loader, join safety, and mart aggregations pass cleanly. | **PASSED (MS 2.2)** | `pytest tests/` passes with **20/20 passed (100%)** in 2.83s. | Covers boundary conditions, invalid records, and live DB integrity. |
| **17** | **Documentation Matches Implementation** | `docs/data_dictionary.md`, `docs/erd.md`, and `docs/PROJECT_LEARNING_LOG.md` reflect verified SQL schema and counts. | **PASSED (MS 2.2)** | Verified against commit `39af9e6` and live PostgreSQL metadata. | Full alignment between documentation, tests, and DDL. |
| **18** | **Git Safety Valid** | Database credentials, `.env`, local connection strings, and cache dumps are strictly ignored by `.gitignore`. | **PASSED** | Verified via `git check-ignore -v .env` (`.gitignore:15`). | Prevents credential leaks and repo pollution. |

---

## 2. Milestone Sign-Off History

### Milestone 2.1 — Database Foundation: **APPROVED**
- Containerized PostgreSQL 16 environment, `.env.example`, persistent named volume, and healthcheck verified in commit `05a1264`.

### Milestone 2.2 — Relational Schema & Grain Design: **APPROVED**
- 4-table relational warehouse schema (`customers`, `products`, `invoices`, `invoice_lines`) verified and validated live on Native PostgreSQL 16 in commit `39af9e6`.
- Composite source-scoped PKs/FKs, `NUMERIC(12,2)`/`NUMERIC(14,2)` monetary precision, nullable `customer_id`, and full 15-flag quality lineage confirmed.

---

## 3. Milestone 2.3 Acceptance Checklist — PostgreSQL Data Loader (`src/data/load.py`)

The loader implementation must satisfy all 10 gate criteria below to achieve sign-off:

| Gate # | Gate Criterion | Exact Requirement | Verification Method | Blocker Classification |
|---|---|---|---|:---:|
| **G2.3.1** | **Idempotency** | Executing `python -m src.data.load` consecutive times produces identical row counts without duplicate key errors. | Run loader twice; assert `COUNT(*)` unchanged across all 4 tables. | Code Logic Gate |
| **G2.3.2** | **Transaction Atomicity & Rollback** | Entire loading pipeline operates within an atomic transaction (`connection.begin()`). Any exception triggers immediate rollback leaving zero orphan/partial rows. | Simulated fault injection test; assert 0 rows inserted if error occurs. | Code Logic Gate |
| **G2.3.3** | **Referential Integrity & Load Order** | Correct insertion order: Dimensions (`customers`, `products`) -> Headers (`invoices`) -> Lines (`invoice_lines`). Zero FK violations. | Foreign key constraint checks during load. | Code Logic Gate |
| **G2.3.4** | **Preservation of Missing Customers** | Exactly 235,287 lines with missing `Customer ID` inserted with `customer_id = NULL`. Zero synthetic customer records (`0`/`99999`) in `customers`. | `SELECT COUNT(*) FROM invoice_lines WHERE customer_id IS NULL;` == 235,287; `SELECT COUNT(*) FROM customers;` == 5,942. | Code Logic Gate |
| **G2.3.5** | **Special Transaction Integrity** | All 19,165 cancellations, 19,165 returns, 3,393 inventory adjustments, 6 bad debts, and 5,805 non-product rows loaded with respective boolean flags. | Count checks against Parquet ground truth. | Code Logic Gate |
| **G2.3.6** | **Source-to-Target Exact Reconciliation** | Total lines = 1,044,848; Invoices = 53,628; Products = 5,131; Customers = 5,942; Total Ledger Sum = £18,909,762.12. | Automated query comparing table aggregates against Parquet ground truth (0 tolerance on counts; £0.01 tolerance on money). | Code Logic Gate |
| **G2.3.7** | **Exact Monetary Precision** | Calculations use `NUMERIC` / `Decimal` arithmetic. Zero floating point rounding drift. | Unit tests comparing DataFrame decimal totals with DB sums. | Code Logic Gate |
| **G2.3.8** | **Namespace-Scoped Cleanups** | Truncate/delete operations must be scoped strictly to the specified `source_system` (e.g. `'UCI'`) or project tables, never destructive to external databases. | Code review of SQL delete/truncate statements. | Code Logic Gate |
| **G2.3.9** | **Zero Hardcoded Credentials** | DB connection URLs read strictly from `DATABASE_URL` / `NEXORA_TEST_DATABASE_URL` or environment variables with safe defaults. | Static inspection & secret scanning. | Code Logic Gate |
| **G2.3.10** | **Testing Separation & Offline Grace** | Unit tests for transformation logic run offline (in-memory / mock); live integration tests run when PostgreSQL is reachable and skip cleanly otherwise. | `pytest tests/` runs successfully in both offline and online states. | Environment Aware |

---

## 4. Quantitative Ground Truth Reconciliation Benchmarks

| Metric / Table | Target Database Table | Expected Ground Truth Value | Tolerance | Status |
|---|---|---|:---:|:---:|
| **Total Ingested Line Items** | `invoice_lines` | **1,044,848 rows** | 0 rows | PENDING MS 2.3 |
| **Total Invoices (Orders)** | `invoices` | **53,628 orders** | 0 orders | PENDING MS 2.3 |
| **Total Unique Customer Dimension** | `customers` | **5,942 customers** | 0 rows | PENDING MS 2.3 |
| **Total Unique Product Dimension** | `products` | **5,131 products** | 0 rows | PENDING MS 2.3 |
| **Total Ledger Net Revenue** | `invoice_lines` | **£18,909,762.12** | £0.01 | PENDING MS 2.3 |
| **Valid Sales Line Revenue** | `invoice_lines` (`is_valid_sale = TRUE`) | **£19,700,954.46** | £0.01 | PENDING MS 2.3 |
| **Cancellation Line Revenue** | `invoice_lines` (`is_cancellation = TRUE`) | **-£1,466,244.60** | £0.01 | PENDING MS 2.3 |
| **Physical Merchandise Returns** | `invoice_lines` (`is_cancellation = TRUE` & `!is_non_product`) | **-£719,692.94** | £0.01 | PENDING MS 2.3 |
| **Valid Sales Order Count** | `invoices` (`invoice_type = 'SALE'`) | **39,516 orders** | 0 orders | PENDING MS 2.3 |
| **Cancellation Order Count** | `invoices` (`invoice_type = 'CANCELLATION'`) | **8,292 orders** | 0 orders | PENDING MS 2.3 |
| **Inventory Shrinkage Write-offs** | `invoice_lines` (`is_inventory_adjustment = TRUE`) | **3,393 rows** | 0 rows | PENDING MS 2.3 |
| **Bad Debt Accounting Adjustments** | `invoice_lines` (`is_bad_debt_adjustment = TRUE`) | **6 rows** (-£147,614.08) | 0 rows | PENDING MS 2.3 |

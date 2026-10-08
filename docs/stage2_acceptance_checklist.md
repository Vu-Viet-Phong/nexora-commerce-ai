# Stage 2 Acceptance Checklist & Data Architecture Sign-Off

**Project:** Nexora Commerce AI  
**Pipeline Stage:** Stage 2 — PostgreSQL & Data Modeling  
**Reviewer:** Senior Data Architect & SQL QA Reviewer / Final QA Gatekeeper  
**Input Source:** `data/processed/transactions_clean.parquet` (SHA-256 Verified, 1,044,848 rows)  
**Database Target:** PostgreSQL (Relational Warehouse & Dimensional Data Marts)  
**Current Milestone Status:** **MILESTONE 2.1 APPROVED (PROCEED TO MILESTONE 2.2)**

---

## 1. Stage 2 Quality Acceptance Matrix

| # | Acceptance Criterion | Target Requirement | Status | Evidence / Verification Method | Notes & Architectural Directives |
|---|---|---|:---:|---|---|
| **01** | **Grain Documented** | Exactly defined for `dim_customers` (5,942 rows), `dim_products` (5,131 rows), `dim_dates` (739 days), `fact_invoices` (53,628 rows), `fact_invoice_lines` (1,044,848 rows). | **PASSED** | Documented in `docs/stage2_data_model_review.md` and `docs/stage2_metric_contract_review.md`. | Enforces strict dimensional modeling standards. |
| **02** | **Docker & Environment Foundation** | PostgreSQL 16 container, safe environment variable interpolation, persistent volume, healthcheck, clean `.env.example`. | **PASSED (MS 2.1)** | `deployment/docker-compose.yml`, `.env.example`, `pyproject.toml` verified. | Zero hardcoded secrets, healthcheck with `pg_isready`. |
| **03** | **Stage 1 Regression Safety** | Adding database dependencies (`SQLAlchemy`, `psycopg[binary]`) does not break existing test suite. | **PASSED (MS 2.1)** | `pytest tests/ -v` passed 7/7 tests in 2.21s. | Zero regression on Stage 1 ingestion & cleaning logic. |
| **04** | **PK Valid & Deterministic** | Primary keys present on all tables (`customer_id`, `stock_code`, `date_id`, `invoice_number`, `line_id`). | **PENDING MS 2.2** | To be verified against `sql/schema.sql` once created. | Ensures entity integrity and fast indexed lookups. |
| **05** | **FK Valid & Referential Integrity** | Foreign keys on `fact_invoices` (`customer_id`), `fact_invoice_lines` (`invoice_number`, `stock_code`, `customer_id`). | **PENDING MS 2.2** | To be verified against DDL constraints and foreign key validation queries. | `ON DELETE RESTRICT` recommended; cascades prohibited on core facts. |
| **06** | **Nullable Rules Valid** | `customer_id` nullable in facts; `quantity`, `unit_price`, `invoice_date`, `invoice_number`, `stock_code` `NOT NULL`. | **PENDING MS 2.2** | To be verified against table column nullability constraints. | 235,287 lines without customer must remain `NULL` (no dummy 0/99999). |
| **07** | **Money Uses Suitable Precision** | Monetary columns (`unit_price`, `line_total`, `invoice_amount`) must use `NUMERIC(12, 2)` or `NUMERIC(14, 2)`. | **PENDING MS 2.2** | To be verified against SQL data types (Zero `FLOAT` / `DOUBLE PRECISION` allowed). | Eliminates IEEE-754 floating point arithmetic rounding discrepancies. |
| **08** | **Loader Idempotent** | Running loader script multiple times produces identical state without duplicate key errors or row proliferation. | **PENDING MS 2.3** | To be verified by executing `python src/data/load.py` twice consecutively. | Requires transactional truncate or deterministic conflict handling. |
| **09** | **Loader Rollback Tested** | Loader executes inside atomic transaction (`BEGIN ... COMMIT`); any error triggers complete `ROLLBACK`. | **PENDING MS 2.3** | To be tested by injecting a simulated error (e.g. invalid type) during bulk load. | Prevents partial, corrupted table states. |
| **10** | **Raw & Processed Source Untouched** | `data/raw/` and `data/processed/transactions_clean.parquet` are read-only and unmodified during load. | **PASSED** | File checksums verified before and after execution. | Guarantees downstream reproducibility. |
| **11** | **Cancellations Retained** | All 19,165 cancellation lines (-£1.47M total; -£719.66k product) loaded into fact table with `is_cancellation = TRUE`, `is_return = TRUE`. | **PENDING MS 2.3** | To be verified by `SELECT COUNT(*) FROM fact_invoice_lines WHERE is_cancellation = TRUE;`. | Critical for calculating Gross-to-Net Revenue bridge. |
| **12** | **Missing Customers Handled** | 235,287 lines with missing `Customer ID` stored as `NULL` FK; excluded from `dim_customers` and customer snapshot mart. | **PENDING MS 2.3** | To be verified by `SELECT COUNT(*) FROM fact_invoice_lines WHERE customer_id IS NULL;` == 235,287. | Prevents creation of an artificial super-customer entity. |
| **13** | **JOIN Multiplication Tested** | Joining `fact_invoice_lines` to `dim_products` and `dim_customers` must maintain exact $1:1$ cardinality (zero fan-out). | **PENDING MS 2.4** | To be tested with `SELECT COUNT(*), SUM(line_total) FROM fact_invoice_lines l JOIN dim_products p ...`. | Total rows must remain 1,044,848; total sum must remain £18,909,762.12. |
| **14** | **Marts Reconcile with Pandas** | `mart_daily_sales`, `mart_customer_daily`, `mart_customer_snapshot` match exact Python ground truth metrics. | **PENDING MS 2.4** | Automated test comparing SQL query sums against Pandas dataframe sums. | Gross sales = £19,700,939.69; Returns = -£719,656.34; Net = £18,981,283.35. |
| **15** | **DB Rebuild Works Cleanly** | A single setup script (e.g. `python -m src.data.load --rebuild` or `sql/schema.sql`) can recreate schema from scratch. | **PENDING MS 2.3** | To be tested by dropping the test schema and executing full rebuild. | Essential for CI/CD and deployment reproducibility. |
| **16** | **Tests Pass** | Unit and integration test suite covering DDL, loader, join safety, and mart aggregations pass cleanly. | **PENDING MS 2.5** | `pytest tests/test_sql/` (or equivalent) passes with 100% success. | Covers boundary conditions, invalid records, and idempotency. |
| **17** | **Documentation Matches Implementation** | `docs/data_dictionary.md`, `docs/erd.md`, and `docs/PROJECT_LEARNING_LOG.md` reflect verified SQL schema and counts. | **PENDING MS 2.5** | Review documentation against live database metadata. | Zero discrepancies between docs and actual DDL. |
| **18** | **Git Safety Valid** | Database credentials, `.env`, local connection strings, and cache dumps are strictly ignored by `.gitignore`. | **PASSED** | Verified via `git check-ignore` (`.gitignore:15` ignores `.env`). | Prevents credential leaks and repo pollution. |

---

## 2. Quantitative Ground Truth Reconciliation Benchmarks

| Metric / Table | Target Database Table / Mart | Expected Ground Truth Value | Tolerance | Status |
|---|---|---|:---:|:---:|
| **Total Ingested Line Items** | `fact_invoice_lines` | **1,044,848 rows** | 0 rows | PENDING MS 2.3 |
| **Total Invoices (Orders)** | `fact_invoices` | **53,628 orders** | 0 orders | PENDING MS 2.3 |
| **Total Unique Customer Dimension** | `dim_customers` | **5,942 customers** | 0 rows | PENDING MS 2.3 |
| **Total Unique Product Dimension** | `dim_products` | **5,131 products** | 0 rows | PENDING MS 2.3 |
| **Gross Merchandise Sales** | `mart_daily_sales` | **£19,700,939.69** | £0.01 | PENDING MS 2.4 |
| **Physical Merchandise Returns** | `mart_daily_sales` | **-£719,656.34** | £0.01 | PENDING MS 2.4 |
| **Net Physical Merchandise Revenue**| `mart_daily_sales` | **£18,981,283.35** | £0.01 | PENDING MS 2.4 |
| **Service & Freight Net Revenue** | `fact_invoice_lines` | **+£75,092.85** | £0.01 | PENDING MS 2.3 |
| **Bad Debt Accounting Adjustments** | `fact_invoice_lines` | **-£147,614.08** | £0.01 | PENDING MS 2.3 |
| **Total Ledger Net Revenue** | `fact_invoice_lines` | **£18,909,762.12** | £0.01 | PENDING MS 2.3 |
| **Valid Sales Order Count** | `fact_invoices` | **39,516 orders** | 0 orders | PENDING MS 2.3 |
| **Cancellation Order Count** | `fact_invoices` | **8,292 orders** | 0 orders | PENDING MS 2.3 |
| **Inventory Shrinkage Write-offs** | `fact_invoice_lines` | **3,393 rows** | 0 rows | PENDING MS 2.3 |

---

## 3. Milestone 2.1 Sign-Off

**MILESTONE 2.1 VERDICT:** **READY (APPROVED)**  
The PostgreSQL 16 containerization, environment variable separation, `.env.example`, persistent named volume, and healthcheck configurations pass architectural review. Stage 1 test regression is 0. Copilot is approved to proceed to **Milestone 2.2 — Schema Design & DDL Implementation**.

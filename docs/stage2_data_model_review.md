# Stage 2 Data Model & Architecture Review

**Project:** Nexora Commerce AI  
**Pipeline Stage:** Stage 2 — PostgreSQL & Data Modeling  
**Role:** Senior Data Architect & SQL QA Reviewer  
**Input Dataset:** `data/processed/transactions_clean.parquet` (1,044,848 rows × 25 columns)  
**Target Storage Engine:** PostgreSQL (Relational Warehouse & Dimensional Data Marts)  
**Review Status:** **MILESTONE 2.2 FULLY APPROVED (LIVE POSTGRESQL VERIFIED) — AUTHORIZED FOR MILESTONE 2.3**

---

## 1. Executive Summary & Architectural Vision

Stage 2 transitions the Nexora Commerce AI project from an exploratory, flat-file Parquet foundation into a robust, normalized relational data warehouse and dimensional modeling layer (Kimball Star Schema / Data Marts) hosted on PostgreSQL.

The primary objective of this review is to establish **strict architectural boundaries, grain definitions, referential integrity rules, loader contracts, and reconciliation benchmarks** before Copilot's SQL and loader code are finalized. This ensures that downstream customer intelligence (Stage 3/4), recommendation engines, and demand forecasting (Stage 6) query performant, mathematically sound, and non-duplicated tables.

---

## 2. Independent Entity Grain Design

Understanding the exact physical and business grain of each entity is the single most critical defense against data corruption and metric distortion.

```
Relational Warehouse Schema (3NF Core & Kimball Marts)
├── dim_customers (Grain: 1 row per unique Customer ID | 5,942 rows)
├── dim_products  (Grain: 1 row per unique normalized StockCode | 5,131 rows)
├── dim_dates     (Grain: 1 row per calendar day | 739 days)
├── fact_invoices (Grain: 1 row per unique Invoice | 53,628 rows)
└── fact_invoice_lines (Grain: 1 row per transaction line | 1,044,848 rows)
```

### 2.1 `dim_customers` (Customer Dimension)
- **Primary Business Grain:** Exactly **one row per unique real-world customer** (`Customer ID`).
- **Population:** Exactly **5,942 unique customer entities** across the 2-year window.
- **Primary Key:** `customer_id` (`INT` or `BIGINT`) or surrogate `customer_key` (`SERIAL PRIMARY KEY`).
- **Attributes:**
  - `primary_country` (`VARCHAR(64)`): The primary geographical location of the customer.
  - `first_invoice_date` (`TIMESTAMP WITHOUT TIME ZONE`): Cohort acquisition timestamp.
  - `last_invoice_date` (`TIMESTAMP WITHOUT TIME ZONE`): Most recent observed activity.
  - `total_orders_lifetime` (`INT`): Lifetime count of distinct valid sales orders.
  - `total_merchandise_spend` (`NUMERIC(14, 2)`): Lifetime net spend on merchandise.
- **Handling Edge Cases:**
  - **Multi-Country Customers (13 entities):** Audit shows 13 customers placed orders across multiple countries (e.g. branch offices or relocation). The dimension table must assign `primary_country` using the **mode (most frequent country)** with tie-breaking by the **latest transaction country**, rather than allowing customer record duplication.
  - **Missing Customer Transactions (235,287 rows):** Transactions with `Customer ID is NULL` are **NOT** inserted as rows into `dim_customers`. There is **NO dummy customer `0` or `99999`**. Instead, foreign keys in line items remain `NULL` (nullable FK), preserving clean customer clustering and RFM distributions.

### 2.2 `dim_products` (Product Dimension)
- **Primary Business Grain:** Exactly **one row per unique product/stock code** (`StockCode`).
- **Population:** Exactly **5,131 unique normalized StockCodes** (uppercase).
- **Primary Key:** `stock_code` (`VARCHAR(32) PRIMARY KEY`) or surrogate `product_key`.
- **Attributes:**
  - `primary_description` (`VARCHAR(256)`): Canonical description (mode of non-null descriptions).
  - `product_type` (`VARCHAR(32)`): Classified category (`PHYSICAL_MERCHANDISE`, `POSTAGE`, `CARRIAGE`, `MANUAL_FEE`, `BANK_CHARGE`, `AMAZON_FEE`, `GIFT_VOUCHER`, `DISCOUNT`, `SAMPLE`, `TEST`, `BAD_DEBT`).
  - `is_physical_merchandise` (`BOOLEAN`): `TRUE` for standard 5-digit items and `DCGS...` product codes; `FALSE` for fee/service items.
  - `median_unit_price` (`NUMERIC(12, 2)`): Benchmark catalog price.
  - `first_seen_date` / `last_seen_date` (`TIMESTAMP WITHOUT TIME ZONE`).
- **Handling Edge Cases:**
  - **Multiple Descriptions per StockCode (1,232 codes):** 1,232 product codes have minor text typos or variations across time. The dimension table must select the **mode description** (`primary_description`) to provide consistent labeling.
  - **Special / Letter-Prefixed Codes:** Codes like `DCGS0058` (*"MISO PRETTY GUM"*) are categorized as `product_type = 'PHYSICAL_MERCHANDISE'` and `is_physical_merchandise = TRUE`.

### 2.3 `fact_invoices` (Header Grain)
- **Primary Business Grain:** Exactly **one row per unique Invoice** (`Invoice`).
- **Population:** Exactly **53,628 unique invoice orders** (45,330 standard numeric, 8,292 cancellations `'C'`, 6 bad debt adjustments `'A'`).
- **Primary Key:** `invoice_number` (`VARCHAR(32) PRIMARY KEY`).
- **Foreign Keys:**
  - `customer_id` (`INT REFERENCES dim_customers(customer_id) ON DELETE RESTRICT NULL`).
- **Attributes:**
  - `invoice_date` (`TIMESTAMP WITHOUT TIME ZONE NOT NULL`): Canonical order timestamp (`MIN(InvoiceDate)`).
  - `country` (`VARCHAR(64) NOT NULL`): Destination country of the order.
  - `invoice_type` (`VARCHAR(32) NOT NULL`): `'SALE'`, `'CANCELLATION'`, `'INVENTORY_ADJUSTMENT'`, `'BAD_DEBT_ADJUSTMENT'`.
  - `total_line_count` (`INT NOT NULL`): Total number of line items in order.
  - `total_quantity` (`INT NOT NULL`): Sum of line quantities.
  - `total_invoice_amount` (`NUMERIC(14, 2)`): Net invoice ledger sum.
- **Handling Edge Cases:**
  - **Multi-Date Invoices (83 invoices):** 83 invoices contain line items spanning 2 consecutive minutes. `fact_invoices` must store `invoice_date = MIN(InvoiceDate)` as the canonical order placement time.

### 2.4 `fact_invoice_lines` (Line Item Grain)
- **Primary Business Grain:** Exactly **one row per transaction line** (1,044,848 rows).
- **Primary Key:** `line_id` (`BIGSERIAL PRIMARY KEY` or composite surrogate `(invoice_number, line_sequence_number)`).
- **Foreign Keys:**
  - `invoice_number` (`VARCHAR(32) REFERENCES fact_invoices(invoice_number)`).
  - `stock_code` (`VARCHAR(32) REFERENCES dim_products(stock_code)`).
  - `customer_id` (`INT REFERENCES dim_customers(customer_id) NULL`).
- **Attributes:**
  - `invoice_date` (`TIMESTAMP WITHOUT TIME ZONE NOT NULL`).
  - `quantity` (`INT NOT NULL`).
  - `unit_price` (`NUMERIC(12, 2) NOT NULL`).
  - `line_total` (`NUMERIC(14, 2) NOT NULL GENERATED ALWAYS AS (quantity * unit_price) STORED` or computed column).
  - `source_sheet` (`VARCHAR(32) NOT NULL`): Provenance tracking (`'Year 2009-2010'` or `'Year 2010-2011'`).
  - **Boolean Quality Flags (Preserved from Stage 1):**
    - `is_valid_sale` (`BOOLEAN NOT NULL`)
    - `is_cancellation` (`BOOLEAN NOT NULL`)
    - `is_return` (`BOOLEAN NOT NULL`)
    - `is_inventory_adjustment` (`BOOLEAN NOT NULL`)
    - `is_bad_debt_adjustment` (`BOOLEAN NOT NULL`)
    - `is_non_product` (`BOOLEAN NOT NULL`)
    - `is_price_zero` (`BOOLEAN NOT NULL`)
    - `is_price_negative` (`BOOLEAN NOT NULL`)
    - `is_duplicate_within_sheet` (`BOOLEAN NOT NULL`)

---

## 3. Database Normalization & Schema Standards

### 3.1 Data Types & Precision Rules
- **Monetary Fields (`unit_price`, `line_total`, `invoice_amount`):**
  - **MANDATORY:** Must use `NUMERIC(12, 2)` or `NUMERIC(14, 2)`.
  - **STRICTLY PROHIBITED:** `FLOAT`, `DOUBLE PRECISION`, or `REAL`. Floating-point arithmetic introduces IEEE-754 rounding errors (e.g. `19.99 * 3 = 59.970000000000006`), violating financial reconciliation.
- **Quantities (`quantity`):** `INTEGER` or `BIGINT`.
- **Identifiers (`invoice_number`, `stock_code`):** `VARCHAR(32)`.
- **Descriptions:** `VARCHAR(256)`.
- **Timestamps:** `TIMESTAMP WITHOUT TIME ZONE` (since dataset records local UK time without timezone offsets).

### 3.2 Indexing Strategy for High-Performance Analytics
To support sub-second query execution in Stage 3 dashboards and ML extraction:
1. **B-Tree Indexes on Foreign Keys & Join Columns:**
   - `CREATE INDEX idx_lines_invoice ON fact_invoice_lines(invoice_number);`
   - `CREATE INDEX idx_lines_stock_code ON fact_invoice_lines(stock_code);`
   - `CREATE INDEX idx_lines_customer_id ON fact_invoice_lines(customer_id);`
2. **Composite Indexes for Temporal & Sales Filtering:**
   - `CREATE INDEX idx_lines_date_valid_sale ON fact_invoice_lines(invoice_date, is_valid_sale);`
   - `CREATE INDEX idx_invoices_date_type ON fact_invoices(invoice_date, invoice_type);`
3. **Partial Indexes for Quality Segments:**
   - `CREATE INDEX idx_lines_cancellations ON fact_invoice_lines(customer_id, invoice_date) WHERE is_cancellation = TRUE;`
   - `CREATE INDEX idx_lines_inventory_adj ON fact_invoice_lines(stock_code, invoice_date) WHERE is_inventory_adjustment = TRUE;`

---

## 4. Join Safety & Cardinality Rules (Preventing Fan-Out Corruption)

### 4.1 The Fan-Out Risk
In analytical SQL, joining a Fact table (`fact_invoice_lines`) to an improperly normalized Dimension table or aggregating across multiple 1-to-Many relationships causes **Fan-Out (Cartesian Multiplication)**.

**Dangerous Anti-Pattern Example:**
```sql
-- DANGEROUS QUERY: Joining lines to an un-deduplicated description table
SELECT SUM(lines.line_total) AS total_sales
FROM fact_invoice_lines lines
JOIN raw_product_descriptions desc ON lines.stock_code = desc.stock_code;
-- IF a stock_code has 3 descriptions, total_sales is multiplied by 3!
```

### 4.2 Acceptance Criteria for Join Safety
1. **1-to-1 Dimension Key Enforcement:** Every Dimension table (`dim_customers`, `dim_products`, `dim_dates`) must have a strict `UNIQUE` or `PRIMARY KEY` constraint on its join key.
2. **Strict 1-to-Many Cardinality:** Any join from `invoice_lines` to `products` on `(source_system, stock_code)` or `customers` on `(source_system, customer_id)` maintains exactly a **$1:1$ dimension match**, guaranteeing zero row duplication.
3. **Reconciliation Test:**
   ```sql
   -- Acceptance Test: Total line count and total revenue must NOT change after joining dimensions
   SELECT 
       COUNT(*) AS line_count,
       SUM(l.line_total) AS total_revenue
   FROM invoice_lines l
   LEFT JOIN products p 
       ON l.source_system = p.source_system 
      AND l.stock_code = p.stock_code
   LEFT JOIN customers c 
       ON l.source_system = c.source_system 
      AND l.customer_id = c.customer_id;
   -- Must equal: line_count = 1,044,848 AND total_revenue = 18,909,762.12
   ```

---

## 5. Loader & Ingestion Architecture (`src/data/load.py`)

The loader pipeline responsible for populating PostgreSQL from `data/processed/transactions_clean.parquet` must adhere to enterprise production standards:

```
transactions_clean.parquet (1,044,848 rows)
                │
                ▼
      Atomic DB Transaction (BEGIN)
                │
        ┌───────┴────────────────────────┐
        ▼                                ▼
Populate Dimensions               Populate Fact Tables
(customers, products)             (invoices, invoice_lines)
        │                                │
        └───────┬────────────────────────┘
                ▼
   Integrity & Constraint Verification
                │
     [Passes Reconciliation?]
          ├── YES ──► COMMIT
          └── NO  ──► ROLLBACK (Zero partial load)
```

### 5.1 Loader Requirements:
1. **Idempotency:** Running `python -m src.data.load` multiple times must produce the exact same database state without duplicate key violations or row multiplication. Recommended strategy: `TRUNCATE TABLE customers, products, invoices, invoice_lines RESTART IDENTITY CASCADE;` within the transaction, or deterministic `ON CONFLICT DO UPDATE/NOTHING`.
2. **Transaction Atomicity:** The entire loading process must run inside a single atomic database transaction (`connection.begin()`). If any constraint fails, the loader must execute an immediate `ROLLBACK`.
3. **High-Performance Bulk Ingestion:** Must use PostgreSQL bulk copy methods (`COPY FROM STDIN` via `psycopg` / `execute_values`), which can load 1.04M rows efficiently rather than row-by-row `INSERT` statements.
4. **Referential Integrity:** Dimensions (`customers`, `products`) must be fully populated before loading Fact tables (`invoices`, `invoice_lines`).

---

## 6. Analytical Data Marts (`sql/marts/`)

To support Stage 3 Exploratory Data Analysis, KPI Dashboards, and Stage 4 Machine Learning, Stage 2 will provision three pre-aggregated, high-performance Data Marts:

### 6.1 `mart_daily_sales` (Daily Financial & Product Velocity Mart)
- **Grain:** 1 row per `(calendar_date, country, is_physical_merchandise)`.
- **Measures:**
  - `gross_merchandise_sales`: Sum of `line_total` for `is_valid_sale == TRUE`.
  - `merchandise_return_value`: Sum of `line_total` for `is_cancellation == TRUE` and physical products.
  - `net_merchandise_revenue`: `gross_merchandise_sales + merchandise_return_value`.
  - `valid_orders_count`: Count of distinct `invoice_number` for valid sales.
  - `returned_orders_count`: Count of distinct cancellation invoices.
  - `items_sold_quantity`: Sum of `quantity` for valid sales.
  - `items_returned_quantity`: Sum of `quantity` for cancellations.
  - `service_fee_revenue`: Sum of `line_total` for non-product codes.
- **Safety Checks:** Excludes `is_inventory_adjustment` from sales and returns.

### 6.2 `mart_customer_daily` (Customer Daily Transaction Summary)
- **Grain:** 1 row per `(customer_id, calendar_date)`.
- **Measures:**
  - `daily_orders_count`: Distinct valid invoices.
  - `daily_gross_spend`: Sum of positive valid sales.
  - `daily_returns_spend`: Sum of cancellations.
  - `daily_net_spend`: Net spend.
  - `daily_items_count`: Total items purchased.

### 6.3 `mart_customer_snapshot` (Customer RFM & Lifetime Mart)
- **Grain:** 1 row per `customer_id` (Exactly **5,942 rows**).
- **Measures:**
  - `first_purchase_date` / `latest_purchase_date`.
  - `recency_days`: Days between latest purchase and reference anchor date (`2011-12-10`).
  - `lifetime_orders_count` (Frequency): Total distinct valid orders.
  - `lifetime_gross_spend` / `lifetime_net_spend` (Monetary).
  - `lifetime_returned_value` / `lifetime_return_rate`.
  - `average_order_value_lifetime` (AOV).
  - `customer_tenure_days`.
- **Safety Checks:** Strictly excludes missing customer records (`customer_id IS NULL`).

---

## 7. Milestone 2.1 — Database Foundation Review

An independent technical audit of Copilot's Milestone 2.1 delivery was conducted covering Docker Compose, environment management, database dependencies, and secret safety.

## 7. PostgreSQL Environment & Dependency Review

### 7.1 Native Windows PostgreSQL 16 & Infrastructure Configuration
- **Database Engine:** PostgreSQL 16.15 running natively as a Windows service on `localhost:5432`.
- **Database Names:**
  - Development DB: `nexora_commerce`
  - Test DB: `nexora_commerce_test`
- **Application User:** `nexora_app`
- **Docker vs. Native Windows Evaluation:** Native Windows service avoids Docker virtualization overhead on local development while providing 100% ANSI PostgreSQL DDL and transaction semantics.
- **Security & Secret Integrity:** Credentials parameterized via `.env` (ignored by git at `.gitignore:15`). Zero credentials hardcoded or committed to git.
- **Verdict:** **PASS (ARCHITECTURE & SERVICE READY)**

### 7.2 Python Environment & Dependency Stack
- **Dependencies:** `SQLAlchemy` (engine/connection abstraction) and `psycopg[binary]` (native PostgreSQL driver).
- **Python Runtime:** Python 3.11.16 on project virtual environment (`.venv`).
- **Regression Test Coverage:** `pytest tests/ -v` executed with **19 passed, 1 skipped** (integration test cleanly skips when `NEXORA_TEST_DATABASE_URL` is unset).
- **Verdict:** **PASS**

---

## 8. Quantitative Ground Truth Reconciliation Matrix

| Metric | Target SQL Table / Column | Expected Value (Ground Truth) | Tolerance | Local Parquet Audit Result |
|---|---|---|:---:|:---:|
| **Total Ingested Line Items** | `invoice_lines` | **1,044,848 rows** | 0 rows | **PASSED** (1,044,848 rows) |
| **Total Distinct Invoices** | `invoices` | **53,628 orders** | 0 orders | **PASSED** (53,628 orders) |
| **Total Identified Customers** | `customers` | **5,942 entities** | 0 entities | **PASSED** (5,942 customers) |
| **Total Unique Products** | `products` | **5,131 products** | 0 products | **PASSED** (5,131 products) |
| **Missing Customer ID Lines** | `invoice_lines.customer_id IS NULL` | **235,287 rows** | 0 rows | **PASSED** (235,287 rows) |
| **Total Ledger Net Revenue** | `invoice_lines.line_total` | **£18,909,762.12** | £0.01 | **PASSED** (£18,909,762.12) |
| **Valid Sales Line Revenue** | `is_valid_sale = TRUE` | **£19,700,954.46** | £0.01 | **PASSED** (£19,700,954.46) |
| **Physical Returns Revenue** | `is_cancellation = TRUE AND !is_non_product` | **-£719,692.94** | £0.01 | **PASSED** (-£719,692.94) |
| **Cancellation Line Items** | `is_cancellation = TRUE` | **19,165 rows** | 0 rows | **PASSED** (19,165 rows) |
| **Inventory Shrinkage Lines** | `is_inventory_adjustment = TRUE` | **3,393 rows** | 0 rows | **PASSED** (3,393 rows) |
| **Bad Debt Adjustments** | `is_bad_debt_adjustment = TRUE` | **6 rows** (-£147,614.08) | 0 rows | **PASSED** (6 rows) |

---

## 9. Independent Review — Milestone 2.2 Live Verification Assessment

**Status: STATIC SCHEMA DESIGN APPROVED — LIVE POSTGRESQL INTEGRATION PENDING TEST RUN**

### 9.1 Test Coverage Audit (10 Critical Areas):
1. **Table creation:** Verified via `test_postgres_integration.py` querying `information_schema.tables` for 4 core tables. (Status: **CODE READY, LIVE RUN PENDING**)
2. **Primary key uniqueness:** Composite PKs enforced on `(source_system, ...)`. Duplicate PK table constraint cleanly removed in commit `9b16305`. (Status: **PASS**)
3. **Foreign key integrity:** Dimension entities inserted before fact rows; referential relationships enforced. (Status: **CODE READY, LIVE RUN PENDING**)
4. **UNIQUE constraints:** `(source_system, source_line_key)` and `(source_system, source_sheet, source_row_number)` verified. (Status: **PASS**)
5. **NULL Customer ID:** Verified nullable FK allows inserting lines without customer ID while preserving referential integrity. (Status: **CODE READY, LIVE RUN PENDING**)
6. **Invalid FK rejection:** Verified `IntegrityError` is raised and caught when referencing non-existent parent records. (Status: **CODE READY, LIVE RUN PENDING**)
7. **NUMERIC precision:** Verified `NUMERIC(12,2)` / `NUMERIC(14,2)` arithmetic without float drift. (Status: **PASS**)
8. **Transaction rollback:** Verified rollback behavior on nested transaction failure (`connection.begin_nested()`). (Status: **CODE READY, LIVE RUN PENDING**)
9. **Schema re-application:** DDL execution inside transactional blocks. (Status: **PASS**)
10. **Special transaction flags:** All 15 Stage 1 quality flags retained and tested. (Status: **PASS**)

### 9.2 Verification Requirement for READY Sign-Off:
- Copilot executes `pytest tests/test_sql/test_postgres_integration.py` against `nexora_commerce_test` on native PostgreSQL (`localhost:5432`) and records the live passing test run evidence.

---

## 10. Milestone 2.3 — PostgreSQL Data Loader Specification (`src/data/load.py`)

### 10.1 Transformation & Ingestion Pipeline:
1. **Data Source:** Read `data/processed/transactions_clean.parquet` (1,044,848 rows × 25 columns).
2. **`customers` Loader Logic (5,942 rows):**
   - Filter `customer_id.notna()`.
   - Aggregate: `primary_country` = mode (tie-break with latest country), `first_invoice_date` = `min(InvoiceDate)`, `last_invoice_date` = `max(InvoiceDate)`, `total_orders_lifetime` = count distinct valid sales `Invoice`, `total_merchandise_spend` = net spend on valid sales minus returns.
   - Attach `source_system = 'UCI'`, `source_file_sha256`.
3. **`products` Loader Logic (5,131 rows):**
   - Group by normalized uppercase `StockCode`.
   - Aggregate: `primary_description` = mode of non-null descriptions, `product_type` = classified type, `is_physical_merchandise` = boolean flag, `median_unit_price` = median of valid prices, `first_seen_date` = `min(InvoiceDate)`, `last_seen_date` = `max(InvoiceDate)`.
   - Attach `source_system = 'UCI'`, `source_file_sha256`.
4. **`invoices` Loader Logic (53,628 rows):**
   - Group by `Invoice`.
   - Aggregate: `customer_id` = first/unique customer ID (nullable), `invoice_date` = `min(InvoiceDate)` (resolves multi-minute timestamps), `country` = order country, `invoice_type` = classified order type (`SALE`, `CANCELLATION`, `INVENTORY_ADJUSTMENT`, `BAD_DEBT_ADJUSTMENT`), `total_line_count` = count of lines, `total_quantity` = sum of quantities, `total_invoice_amount` = sum of `line_total`.
   - Attach `source_system = 'UCI'`, `source_file_sha256`.
5. **`invoice_lines` Loader Logic (1,044,848 rows):**
   - Generate deterministic 1-based `source_row_number` per sheet.
   - Construct `source_line_key = f"{source_system}_{source_sheet}_{source_row_number}"`.
   - Map all 15 boolean quality flags directly from Parquet.
6. **Execution Protocol & Idempotency:**
   - Execute inside an atomic transaction (`BEGIN ... COMMIT`).
   - Idempotent reload: Truncate tables with `RESTART IDENTITY CASCADE` or use `ON CONFLICT DO UPDATE/NOTHING`.
   - Rollback on error: Any exception triggers an immediate `ROLLBACK` ensuring zero corrupted/partial state.

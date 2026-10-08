# Stage 2 Data Model & Architecture Review

**Project:** Nexora Commerce AI  
**Pipeline Stage:** Stage 2 — PostgreSQL & Data Modeling  
**Role:** Senior Data Architect & SQL QA Reviewer  
**Input Dataset:** `data/processed/transactions_clean.parquet` (1,044,848 rows × 25 columns)  
**Target Storage Engine:** PostgreSQL (Relational Warehouse & Dimensional Data Marts)  
**Review Status:** **MILESTONE 2.1 APPROVED (ARCHITECTURE & DB FOUNDATION READY)**

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
2. **Strict 1-to-Many Cardinality:** Any join from `fact_invoice_lines` to `dim_products` on `stock_code` or `dim_customers` on `customer_id` must maintain exactly a **$1:1$ dimension match**, guaranteeing zero row duplication.
3. **Reconciliation Test:**
   ```sql
   -- Acceptance Test: Total line count and total revenue must NOT change after joining dimensions
   SELECT 
       COUNT(*) AS line_count,
       SUM(line_total) AS total_revenue
   FROM fact_invoice_lines l
   LEFT JOIN dim_products p ON l.stock_code = p.stock_code
   LEFT JOIN dim_customers c ON l.customer_id = c.customer_id;
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
(dim_customers, dim_products)     (fact_invoices, fact_invoice_lines)
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
1. **Idempotency:** Running `python src/data/load.py` multiple times must produce the exact same database state without duplicate key violations or row multiplication. Recommended strategy: `TRUNCATE ... RESTART IDENTITY CASCADE` within a transaction, or deterministic `ON CONFLICT DO UPDATE`.
2. **Transaction Atomicity:** The entire loading process must run inside a single atomic database transaction (`BEGIN ... COMMIT`). If any constraint fails, the loader must execute an immediate `ROLLBACK`.
3. **High-Performance Bulk Ingestion:** Must use PostgreSQL bulk copy methods (`COPY FROM STDIN` via `psycopg2.copy_expert` or `cursor.copy_from`), which can load 1.04M rows in under 5 seconds, rather than individual `INSERT` statements.
4. **Referential Integrity:** Dimensions (`dim_customers`, `dim_products`) must be fully populated before loading Fact tables (`fact_invoices`, `fact_invoice_lines`).

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

### 7.1 Docker Compose & Service Configuration
- **File Evaluated:** `deployment/docker-compose.yml`
- **Base Image:** `postgres:16` (Official PostgreSQL 16 image — robust and standard).
- **Environment Parameterization:** Uses parameter expansion with safe fallback defaults:
  - `POSTGRES_DB: ${POSTGRES_DB:-nexora}`
  - `POSTGRES_USER: ${POSTGRES_USER:-nexora}`
  - `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-nexora_local_only}`
- **Port Mapping:** `"${POSTGRES_PORT:-5432}:5432"` (Configurable host port).
- **Persistent Volume:** `postgres_data:/var/lib/postgresql/data` (Docker-managed named volume; keeps DB state across container restarts without committing raw DB files).
- **Healthcheck:** Implements shell-evaluated `pg_isready` check with escaped `$$` interpolation:
  `test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]`
  (Interval: 5s, Timeout: 5s, Retries: 10).
- **Security & Secret Integrity:** Zero real production credentials committed. Volume and local `.env` files are strictly isolated from git tracking.
- **Verdict:** **PASS**

### 7.2 Python Environment & Dependency Stack
- **File Evaluated:** `pyproject.toml`
- **Dependencies Added:** `SQLAlchemy` (database engine / connection abstraction) and `psycopg[binary]` (PostgreSQL native adapter).
- **Python Runtime:** Python 3.11.16 on Conda `vbpr_env`.
- **Stage 1 Regression Test:** `pytest tests/ -v` executed: **7/7 unit tests PASSED** in 2.21s. Zero regression observed.
- **Verdict:** **PASS**

### 7.3 Secret Safety & Git Status
- `.env.example` contains only clean placeholders (`POSTGRES_DB=`, `POSTGRES_USER=`, `POSTGRES_PASSWORD=`, `POSTGRES_PORT=5432`, `DATABASE_URL=`).
- `.env` and `.env.*` are verified as ignored by `.gitignore` lines 15–16 (`git check-ignore -v .env`).
- Git history remains clean with zero exposed secrets.
- **Verdict:** **PASS**

---

## 8. Automated Pandas vs PostgreSQL Reconciliation Matrix

Stage 2 acceptance requires automated, exact numeric parity between the source Parquet dataset (`transactions_clean.parquet`) and the PostgreSQL tables.

| Metric | Target SQL Table / Mart | Expected Value (Ground Truth) | Tolerance | QA Result |
|---|---|---|:---:|:---:|
| **Total Lines Ingested** | `fact_invoice_lines` | **1,044,848** | 0 rows | PENDING MILESTONE 2.3 |
| **Total Invoices Ingested** | `fact_invoices` | **53,628** | 0 orders | PENDING MILESTONE 2.3 |
| **Total Unique Customers** | `dim_customers` | **5,942** | 0 entities | PENDING MILESTONE 2.3 |
| **Total Unique Products** | `dim_products` | **5,131** | 0 products | PENDING MILESTONE 2.3 |
| **Gross Merchandise Sales** | `mart_daily_sales` | **£19,700,939.69** | £0.01 | PENDING MILESTONE 2.4 |
| **Merchandise Returns** | `mart_daily_sales` | **-£719,656.34** | £0.01 | PENDING MILESTONE 2.4 |
| **Net Merchandise Revenue** | `mart_daily_sales` | **£18,981,283.35** | £0.01 | PENDING MILESTONE 2.4 |
| **Total Ledger Net Revenue** | `fact_invoice_lines` | **£18,909,762.12** | £0.01 | PENDING MILESTONE 2.3 |
| **Valid Sales Order Count** | `fact_invoices` | **39,516** | 0 orders | PENDING MILESTONE 2.3 |
| **Cancellations Order Count** | `fact_invoices` | **8,292** | 0 orders | PENDING MILESTONE 2.3 |
| **Inventory Adjustments Count**| `fact_invoice_lines` | **3,393** | 0 rows | PENDING MILESTONE 2.3 |

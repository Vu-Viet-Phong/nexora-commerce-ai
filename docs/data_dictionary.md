# Data Dictionary

The dictionary describes the PostgreSQL DDL in [`sql/schema.sql`](../sql/schema.sql).
All source-derived timestamps use `TIMESTAMP WITHOUT TIME ZONE` because the
source contains local timestamps without timezone offsets. `source_system`
is currently `UCI` and is mandatory for future source isolation.

## customers

**Grain:** One row per identified customer within one source system.  
**Primary key:** `(source_system, customer_id)`  
**Foreign keys:** None.

| Column | PostgreSQL Type | Nullable | Source | Meaning | Transformation | Notes |
|---|---|---:|---|---|---|---|
| source_system | VARCHAR(32) | No | loader constant | Source namespace | Set to `UCI` for this dataset | Part of identity |
| customer_id | BIGINT | No | `Customer ID` | Identified customer | Normalize numeric identifier | Missing source IDs are not dimension rows |
| primary_country | VARCHAR(64) | No | `Country` | Representative customer country | Mode; latest-country tie break | 13 customers span multiple countries |
| first_invoice_date | TIMESTAMP WITHOUT TIME ZONE | No | `InvoiceDate` | First observed invoice timestamp | Minimum by customer | Source local time |
| last_invoice_date | TIMESTAMP WITHOUT TIME ZONE | No | `InvoiceDate` | Last observed invoice timestamp | Maximum by customer | Source local time |
| total_orders_lifetime | INTEGER | No | `Invoice` and flags | Valid order count | Distinct invoice count for valid sales | Non-negative |
| total_merchandise_spend | NUMERIC(14,2) | No | `line_total` and flags | Customer net merchandise spend | Aggregate according to metric contract | Money is exact decimal |
| source_file_sha256 | CHAR(64) | No | ingestion manifest | Input file identity | Copy verified SHA-256 | Provenance |

## products

**Grain:** One row per source-scoped normalized stock code.  
**Primary key:** `(source_system, stock_code)`  
**Foreign keys:** None.

| Column | PostgreSQL Type | Nullable | Source | Meaning | Transformation | Notes |
|---|---|---:|---|---|---|---|
| source_system | VARCHAR(32) | No | loader constant | Source namespace | Set to `UCI` | Part of identity |
| stock_code | VARCHAR(32) | No | `StockCode` | Product or service code | Normalize text without collapsing codes | Special codes remain represented |
| primary_description | VARCHAR(256) | Yes | `Description` | Canonical description | Mode of non-null descriptions | 1,192 codes have multiple descriptions |
| product_type | VARCHAR(32) | No | Stage 1 flags/classification | Product/service classification | Use explicit classification rules | Includes non-product and adjustments |
| is_physical_merchandise | BOOLEAN | No | Stage 1 classification | Physical product indicator | Preserve classification | Not inferred only from prefix |
| median_unit_price | NUMERIC(12,2) | Yes | `Price` | Typical observed unit price | Median of valid observations | Nullable if no valid price |
| first_seen_date | TIMESTAMP WITHOUT TIME ZONE | No | `InvoiceDate` | First observed code timestamp | Minimum by stock code | Source local time |
| last_seen_date | TIMESTAMP WITHOUT TIME ZONE | No | `InvoiceDate` | Last observed code timestamp | Maximum by stock code | Source local time |
| source_file_sha256 | CHAR(64) | No | ingestion manifest | Input file identity | Copy verified SHA-256 | Provenance |

## invoices

**Grain:** One row per source-scoped invoice header.  
**Primary key:** `(source_system, invoice_number)`  
**Foreign keys:** `(source_system, customer_id)` references `customers`.

| Column | PostgreSQL Type | Nullable | Source | Meaning | Transformation | Notes |
|---|---|---:|---|---|---|---|
| source_system | VARCHAR(32) | No | loader constant | Source namespace | Set to `UCI` | Part of identity |
| invoice_number | VARCHAR(32) | No | `Invoice` | Invoice/business identifier | Normalize as text | Prefixes `C` and `A` are retained |
| customer_id | BIGINT | Yes | `Customer ID` | Invoice customer | Normalize numeric ID | NULL is preserved for guest lines |
| invoice_date | TIMESTAMP WITHOUT TIME ZONE | No | `InvoiceDate` | Canonical invoice timestamp | Minimum line timestamp | 83 invoices have timestamp conflicts |
| country | VARCHAR(64) | No | `Country` | Invoice country | Use source value | Header representation must be deterministic |
| invoice_type | VARCHAR(32) | No | invoice/quality flags | Invoice business type | Classify sale/cancellation/adjustment | Controlled by DDL check |
| total_line_count | INTEGER | No | line rows | Number of lines | Count lines per invoice | Positive |
| total_quantity | BIGINT | No | `Quantity` | Invoice quantity total | Sum without dropping negatives | Includes returns/adjustments |
| total_invoice_amount | NUMERIC(14,2) | No | line values | Invoice ledger amount | Sum line totals | Exact decimal |
| source_file_sha256 | CHAR(64) | No | ingestion manifest | Input file identity | Copy verified SHA-256 | Provenance |

## invoice_lines

**Grain:** One row per retained transaction line from the processed source,
including duplicate flags, cancellations, returns, inventory adjustments,
bad-debt adjustments, and non-product records.  
**Primary key:** `line_id` (internal identity); stable source key is
`(source_system, source_line_key)`.  
**Foreign keys:** `(source_system, invoice_number)` to `invoices`;
`(source_system, stock_code)` to `products`; nullable
`(source_system, customer_id)` to `customers`.

| Column | PostgreSQL Type | Nullable | Source | Meaning | Transformation | Notes |
|---|---|---:|---|---|---|---|
| line_id | BIGINT IDENTITY | No | database | Internal line identity | Generated by PostgreSQL | Not a StockCode key |
| source_system | VARCHAR(32) | No | loader constant | Source namespace | Set to `UCI` | Prevents cross-source joins |
| source_line_key | VARCHAR(128) | No | source provenance | Stable source line identifier | Deterministic from source row identity | Unique within source |
| source_sheet | VARCHAR(64) | No | workbook sheet | Original sheet | Preserve source sheet | Provenance |
| source_row_number | BIGINT | No | deterministic loader ordinal | Original/loader row position | Assign before load | Disambiguates within-sheet duplicates |
| source_file_sha256 | CHAR(64) | No | ingestion manifest | Input file identity | Copy verified SHA-256 | Provenance |
| invoice_number | VARCHAR(32) | No | `Invoice` | Parent invoice | Normalize as text | FK to invoice header |
| stock_code | VARCHAR(32) | No | `StockCode` | Product/service code | Normalize text | FK to product |
| customer_id | BIGINT | Yes | `Customer ID` | Line customer | Preserve missingness | Nullable FK |
| description | VARCHAR(256) | Yes | `Description` | Source description | Preserve null | Does not define product identity |
| invoice_date | TIMESTAMP WITHOUT TIME ZONE | No | `InvoiceDate` | Line event timestamp | Preserve source timestamp | May differ slightly from header |
| quantity | INTEGER | No | `Quantity` | Line quantity | Preserve signs | Returns/cancellations remain |
| unit_price | NUMERIC(12,2) | No | `Price` | Line unit price | Convert from source float to decimal | No FLOAT storage |
| line_total | NUMERIC(14,2) generated | Yes | quantity and unit_price | Line ledger amount | Generated exact decimal product | Nullable metadata reflects generated SQL |
| is_duplicate_within_sheet | BOOLEAN | No | Stage 1 flag | Within-sheet ambiguity flag | Preserve flag | Not silently dropped |
| is_duplicate_cross_sheet | BOOLEAN | No | Stage 1 flag | Cross-sheet duplicate flag | Preserve flag | Stage 1 handles exact overlap |
| is_cancellation | BOOLEAN | No | Stage 1 flag | Cancellation indicator | Preserve flag | Prefix `C` behavior |
| is_bad_debt_adjustment | BOOLEAN | No | Stage 1 flag | Bad-debt adjustment | Preserve flag | Prefix `A` behavior |
| is_negative_quantity | BOOLEAN | No | Stage 1 flag | Negative quantity indicator | Preserve flag | Not equivalent to cancellation |
| is_return | BOOLEAN | No | Stage 1 flag | Return indicator | Preserve flag | Business return classification |
| is_inventory_adjustment | BOOLEAN | No | Stage 1 flag | Inventory adjustment | Preserve flag | No silent drop |
| has_customer_id | BOOLEAN | No | Stage 1 flag | Customer ID presence | Preserve flag | Must agree with nullable ID |
| has_description | BOOLEAN | No | Stage 1 flag | Description presence | Preserve flag | Source quality indicator |
| has_valid_price | BOOLEAN | No | Stage 1 flag | Price validity | Preserve flag | Stage 1 definition |
| is_price_zero | BOOLEAN | No | Stage 1 flag | Zero-price indicator | Preserve flag | Samples/gifts may be retained |
| is_price_negative | BOOLEAN | No | Stage 1 flag | Negative-price indicator | Preserve flag | Accounting edge case |
| is_non_product | BOOLEAN | No | Stage 1 flag | Service/special code indicator | Preserve explicit classification | Excluded by metric contract where required |
| is_unknown_special_code | BOOLEAN | No | Stage 1 flag | Unclassified special-code indicator | Preserve flag | Currently observed as zero |
| is_valid_sale | BOOLEAN | No | Stage 1 flag | Valid merchandise sale | Preserve metric-contract flag | Does not delete other rows |

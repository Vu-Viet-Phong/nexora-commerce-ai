# Stage 2 — PostgreSQL SQL and Relational Modeling

## Scope and verification status

This note explains the four-table core schema implemented for Nexora Commerce
AI:

- `customers`
- `products`
- `invoices`
- `invoice_lines`

The source is `data/processed/transactions_clean.parquet`. The processed
source is read-only. Static schema and source reconciliation tests run locally.
Live PostgreSQL execution is still pending because Docker, Docker Compose and
`psql` are not available in the current environment. The optional integration
test is skipped unless `NEXORA_TEST_DATABASE_URL` points to a dedicated test
database.

## Grain

Grain states what one row means. It must be decided before SQL is written,
because aggregating at the wrong grain can multiply revenue.

| Table | Grain |
|---|---|
| `customers` | One identified `Customer ID` within one `source_system` |
| `products` | One normalized `StockCode` within one `source_system` |
| `invoices` | One `Invoice` header within one `source_system` |
| `invoice_lines` | One retained processed transaction line |

Nexora has 1,044,848 processed lines, 53,628 invoices, 5,131 products and
5,942 identified customers. A missing Customer ID is not a customer entity:
235,287 line rows retain a nullable customer foreign key instead of using a
fake customer.

## Facts and dimensions

`customers` and `products` are descriptive dimensions. `invoices` and
`invoice_lines` are transaction facts at header and line grain. The schema
does not add `dim_dates`, marts, or alternate `fact_*` names merely to match
an earlier proposal. The deployed DDL and documentation use the same four
table names.

## Keys and referential integrity

A primary key uniquely identifies a row. `customers`, `products`, and
`invoices` use composite business keys containing `source_system`:

```sql
PRIMARY KEY (source_system, customer_id)
PRIMARY KEY (source_system, stock_code)
PRIMARY KEY (source_system, invoice_number)
```

This is a composite key: `UCI` and a future `Amazon` invoice with the same
textual number remain different entities.

`invoice_lines.line_id` is a PostgreSQL identity key. It is an internal
surrogate key, not a business key and not a StockCode. The source-level
identity is carried by `source_line_key`, `source_sheet`,
`source_row_number`, and `source_file_sha256`, with unique constraints on
source namespace plus line provenance.

Foreign keys enforce referential integrity:

- an invoice customer must exist in `customers`, unless it is NULL;
- a line invoice must exist in `invoices`;
- a line product must exist in `products`;
- a non-null line customer must exist in `customers`.

`ON DELETE RESTRICT` prevents deleting a referenced dimension or invoice
while transaction rows still depend on it.

## NULL Customer ID

The processed data has 235,287 missing Customer IDs. NULL means the source
did not identify a customer; it does not mean a synthetic customer. PostgreSQL
allows a nullable foreign key without requiring a dummy dimension row. This
preserves guest transactions and avoids concentrating unrelated activity into
one fake entity.

## NUMERIC versus FLOAT

`unit_price` uses `NUMERIC(12,2)`, while line, invoice and customer money
measures use `NUMERIC(14,2)`. PostgreSQL `NUMERIC` stores decimal arithmetic
appropriate for financial reconciliation. FLOAT is binary floating point and
can represent values such as 19.99 approximately. The generated `line_total`
uses:

```sql
ROUND(quantity::NUMERIC * unit_price, 2)
```

The quantity and price inputs are non-null, so `line_total` is declared
`NOT NULL`.

## Schema application

`sql/schema.sql` is a PostgreSQL DDL transaction. It creates tables,
constraints and indexes, then commits. If a statement fails, PostgreSQL
rolls the transaction back. The schema is intended for a clean test database;
loader rebuild/idempotency behavior belongs to Milestone 2.3.

The current environment cannot execute this file because Docker, Docker
Compose and `psql` are unavailable. No live DDL result is reported as PASS.
When a dedicated test database is available, set
`NEXORA_TEST_DATABASE_URL` and run the optional integration tests. Do not point
that variable at a database containing real user data.

## Integration testing

Static tests verify DDL declarations and processed-source ground truth. They
cover table names, keys, nullable customer fields, money types, quality flags,
source identity and source counts.

The optional PostgreSQL test applies the schema and checks the four public
tables. Further runtime checks required before Loader acceptance include
foreign-key rejection, duplicate source identity rejection, NULL customer
insertion, generated line total precision, and transaction rollback.

## Join cardinality and fan-out

The safe joins use the complete source-scoped keys:

```sql
l.source_system = p.source_system
AND l.stock_code = p.stock_code
```

and equivalent invoice/customer joins. Each dimension key is unique, so a
line-to-dimension join remains 1:1 from the line's perspective. Joining an
invoice amount to its lines and then summing the header amount would repeat
that amount once per line. Revenue must be aggregated from `invoice_lines`,
or header measures must be aggregated at invoice grain before joining.

## Source-to-target reconciliation

The local source tests confirm:

- 1,044,848 processed lines
- 53,628 invoices
- 5,131 products
- 5,942 customers
- 235,287 NULL customer references
- 19,165 cancellation/return lines
- 3,393 inventory-adjustment lines
- 6 bad-debt lines
- total processed line amount: 18,909,762.12

The current Parquet ground truth also gives 19,700,954.46 for rows flagged
`is_valid_sale` and -719,692.94 for cancellation rows that are not
`is_non_product`. These values differ from older review benchmarks, so they
must be reconciled explicitly during loader work rather than silently copied
from documentation.

Database-level reconciliation is pending until a loader inserts rows into a
dedicated PostgreSQL test database. No database row count or revenue total is
claimed yet.

## Technical decisions and errors found

- Keep four core tables; do not add `dim_dates` before a business requirement.
- Keep source namespace in every business identity and foreign key.
- Keep quality flags and special transactions instead of filtering them out.
- Use an identity line key plus deterministic source provenance.
- Corrected the DDL's duplicate declaration of the `invoice_lines` primary key.
- Made generated `line_total` explicitly `NOT NULL` and aligned the data
  dictionary.
- Expanded the ERD to show every line-level quality flag and documented
  provenance uniqueness.

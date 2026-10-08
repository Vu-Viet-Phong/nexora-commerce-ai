# Stage 2 — PostgreSQL SQL and Relational Modeling

## Scope and verification status

This note explains the four-table core schema implemented for Nexora Commerce
AI:

- `customers`
- `products`
- `invoices`
- `invoice_lines`

The source is `data/processed/transactions_clean.parquet`. The processed
source is read-only. Static schema, loader and source reconciliation tests run
locally.
Live PostgreSQL verification uses the native PostgreSQL 16 service on Windows;
Docker is intentionally out of scope for this milestone.

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

## Native Windows configuration and schema application

`sql/schema.sql` is a PostgreSQL DDL transaction. It creates tables,
constraints and indexes, then commits. If a statement fails, PostgreSQL
rolls the transaction back. The schema is intended for a clean test database;
loader rebuild/idempotency behavior belongs to Milestone 2.3.

The local configuration is stored in a Git-ignored `.env` at the project root:

```text
DATABASE_URL=postgresql+psycopg://nexora_app:<url-encoded-password>@localhost:5432/nexora_commerce
NEXORA_TEST_DATABASE_URL=postgresql+psycopg://nexora_app:<url-encoded-password>@localhost:5432/nexora_commerce_test
```

The password is never committed or printed. The integration test loads `.env`
inside the Python process, rather than relying on inheritance from another
terminal. It also normalizes a local password containing `@` before creating
the SQLAlchemy URL; URL-encoding the password in `.env` remains preferred.

The concrete command was:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_sql\test_postgres_integration.py -vv
```

The test drops only the four target tables in the dedicated
`nexora_commerce_test` database, applies `sql/schema.sql` in one transaction,
and verifies runtime metadata and behavior. This is safe for the test
database because it is explicitly separate from the main database.

## Integration testing

Static tests verify DDL declarations and processed-source ground truth. They
cover table names, keys, nullable customer fields, money types, quality flags,
source identity and source counts.

The live PostgreSQL test passed (`1 passed`). It verifies SQLAlchemy/psycopg
connectivity, all four tables, primary keys, foreign keys, UNIQUE constraints,
indexes, NUMERIC money columns, nullable customer IDs, generated
`line_total = 19.99`, invalid FK rejection, duplicate source identity
rejection, and savepoint rollback.

PostgreSQL marks a transaction as failed after a constraint error. Each test
case therefore rolls back its savepoint before issuing the next assertion;
otherwise PostgreSQL returns `InFailedSqlTransaction`.

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

The loader now performs database-level reconciliation in the dedicated test
database. Full Parquet loading is intentionally a Milestone 2.3 operation;
analytics marts and downstream reconciliation remain out of scope.

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
- Native Windows PostgreSQL was used instead of Docker because Docker was
  unavailable; Docker troubleshooting was deliberately not continued.
- The first connection attempt exposed a malformed local URL caused by an
  unescaped `@` in the password. The test loader normalizes that value
  without logging it; future `.env` values should percent-encode special
  characters.

## Milestone 2.3 loader

The loader is implemented in
[`src/data/load.py`](../../src/data/load.py). It follows an ETL shape: read
the immutable processed Parquet, transform it into the four approved grains,
then load PostgreSQL. The database is the system of record after the load,
which makes the execution an ELT-compatible boundary for later SQL marts.

The main functions are deliberately small:

- `load_local_env()` reads only the ignored local `.env` and never overwrites
  process variables.
- `normalize_database_url()` protects SQLAlchemy parsing when a local
  password contains an unescaped `@`; percent-encoding in `.env` is preferred.
- `prepare_frames()` creates customer, product, invoice and line frames,
  including the deterministic source row key and all 15 quality flags.
- `copy_frame()` uses PostgreSQL `COPY FROM STDIN` for bulk loading.
- `load_source()` deletes only the `UCI` namespace from each table, inserts
  parent tables before facts inside one SQLAlchemy transaction, and lets any
  exception roll the whole transaction back.

The delete-and-reload strategy is idempotent without using
`TRUNCATE ... CASCADE`: it cannot remove another source namespace and can be
used only against the configured loader database. A second run produced the
same `(customers, products, invoices, invoice_lines)` counts:
`(5,942, 5,131, 53,628, 1,044,848)`.

The loader preserves 235,287 NULL customer IDs, 19,165 cancellations, 3,393
inventory adjustments, 6 bad-debt adjustments and the source sheet/row
lineage. PostgreSQL generates `line_total` from the two-decimal NUMERIC
`unit_price`; therefore SQL totals use the database's exact rounded metric.
The valid-sale total in PostgreSQL is **19,700,954.44**, while the Parquet
float aggregate is **19,700,954.46** before conversion to the schema's
two-decimal unit-price contract. The return total is **-719,692.94** in both
contracts.

The integration test intentionally raises an exception after bulk copy. The
transaction is rolled back and the prior complete counts remain unchanged.
This demonstrates atomicity and rollback rather than merely testing a nested
savepoint.

Run the complete loader again with:

```powershell
.\.venv\Scripts\python.exe -m src.data.load
```

The command reads `DATABASE_URL` from the process or ignored `.env`, prints
only row counts and database name, and never prints credentials.

## Reproducible commands and outcome

```powershell
git check-ignore --verbose .env
.\.venv\Scripts\python.exe -m pytest tests\test_sql\test_postgres_integration.py -vv
.\.venv\Scripts\python.exe -m pytest tests -q
```

Observed results:

- `.env` matched `.gitignore` and was never staged.
- PostgreSQL test connection succeeded through SQLAlchemy/psycopg.
- Schema apply and runtime integration test: **1 passed**.
- Full suite before loader: **20 passed in 2.60s**.
- Loader integration: **1 passed in 606.08s**; the run covered bulk load,
  reconciliation, idempotent reload and rollback.
- Full suite after loader: **21 passed in 621.09s**.
- Main database loader run: **188.25s**, returning 5,942 customers, 5,131
  products, 53,628 invoices and 1,044,848 invoice lines.
- The main database safety check confirmed `nexora_commerce`, zero existing
  target tables and no rows to overwrite. The schema was then applied and
  verified as four created tables. No destructive statement was run against
  existing main data.

## Milestone 2.4: SQL analytics marts

### OLTP core and OLAP marts

The four loader tables are the relational core (an OLTP-shaped model): each
table has a clear write grain, foreign keys protect relationships, and
generated `line_total` keeps monetary arithmetic deterministic. Analytics
marts are an OLAP-shaped read layer. They aggregate facts for questions such
as "sales by day" or "customer RFM" without changing the source facts.

The three views are intentionally lean and reproducible:

- `mart_daily_sales`: one row per `(calendar_day, country,
  is_physical_merchandise)`.
- `mart_customer_daily`: one row per `(customer_id, calendar_day)`.
- `mart_customer_snapshot`: one row per identified customer.

The first two are fact-like aggregates. `customers` and `products` behave as
dimensions, while `invoice_lines` is the transaction fact and `invoices` is
the canonical header/date dimension. The SQL uses `invoices.invoice_date`,
not a line timestamp, so one invoice cannot be split across calendar days.

### Contract decisions

The marts use only the `UCI` source namespace. A test sentinel row from a
previous schema test initially leaked into a mart query and inflated gross
sales by `19.99`; the explicit source predicate fixed the producer rather
than masking the downstream total. Valid sale lines provide gross sales,
units sold and invoice frequency. Physical merchandise cancellation lines
provide negative return value and positive `units_returned`. Inventory
adjustments and non-product cancellation lines are excluded. NULL customer
lines remain in the daily company mart but are excluded from both
customer-level views.

Snapshot `frequency` is the count of distinct valid-sale invoice numbers.
`monetary` is valid-sale gross plus physical return value (net monetary
value), and AOV is gross monetary divided by that frequency. All 5,942
identified customers remain in the snapshot; 90 customers have no valid sale
and therefore receive frequency zero and NULL purchase dates/recency rather
than fabricated values. The reference date is `2011-12-10`.

### SQL concepts in the actual views

`JOIN` combines a line with its invoice header and product dimension. The
join is composite (`source_system` plus business key), which prevents
cross-source matches. A fan-out join would multiply `line_total`; the
integration test checks grain uniqueness and the reconciliation totals.

`WITH eligible_lines AS (...)` is a CTE. It gives the daily views one
readable filtered input before `GROUP BY` performs aggregation. `SUM` adds
NUMERIC monetary values and quantities, while `COUNT(DISTINCT invoice_number)`
counts orders rather than lines. `CASE` separates valid sales from returns.
The snapshot uses PostgreSQL aggregate `FILTER` clauses for the same
separation, then a `LEFT JOIN` retains customers with no qualifying sale.
No window function is needed: the requested RFM metrics are customer-level
aggregates, not rankings over an ordered partition.

Example input/output for one daily group:

```sql
SELECT calendar_day, country, gross_sales, return_value, net_sales
FROM mart_daily_sales
ORDER BY calendar_day, country
LIMIT 1;
```

Input is the retained line fact plus canonical invoice date and product
classification. Output is one row at the declared grain. `net_sales` is
gross plus the negative return value. A common error is grouping by line
date, counting lines as orders, or joining on `stock_code` without the source
namespace; each can create duplicate revenue.

### Reconciliation and RFM results

The test database was reloaded with the approved loader before mart
validation. The live PostgreSQL NUMERIC results were:

| Check | Result |
|---|---:|
| identified snapshot customers | 5,942 |
| customers with valid-sale frequency | 5,852 |
| customers with frequency zero | 90 |
| daily gross / valid revenue | 19,700,954.44 |
| daily return value | -719,692.94 |
| daily net sales | 18,981,261.50 |
| daily distinct invoices summed by grain | 39,516 |
| daily units sold / returned | 11,221,957 / 469,882 |
| customer gross / return / net | 17,124,940.98 / -713,046.25 / 16,411,894.73 |

The customer totals are lower than company totals because NULL customer
activity is deliberately not attributed to an identified customer. The
integration test also verifies zero duplicate keys, snapshot count, return
handling, customer exclusion, and positive AOV for customers with purchases.
Monetary comparisons use the schema's two-decimal generated `NUMERIC`
contract, not binary floating-point source sums. The reconciliation also
checks the complete fact join (`invoice_lines` to `invoices` and `products`)
remains exactly 1,044,848 rows with ledger sum £18,909,762.10. The source
Parquet audit reports £18,909,762.12; the two-penny difference is the
intentional per-line `NUMERIC(12,2)` rounding performed by the generated
database column. This is a
direct fan-out/orphan guard, not only a check on final aggregates. Row-level
invariants assert `net_sales = gross_sales + return_value` and
`net_spend = gross_spend + return_value`. PostgreSQL `pg_typeof` checks confirm
the mart money measures remain `numeric`; the snapshot invariant confirms
zero-purchase customers have no fabricated AOV. Their monetary value may be
negative when the source contains return-only activity.

### Performance evidence

`EXPLAIN (ANALYZE, BUFFERS)` was run on the test database without changing
data. PostgreSQL used parallel sequential scans and hash joins for the large
line fact, followed by external merge sort/group aggregation. Observed
execution times were approximately 1.57s for daily sales, 1.29s for customer
daily, and 1.60s for the snapshot. Sorts spilled to temporary disk (about
20--36 MB per worker/query), which is the current bottleneck. No index was
added speculatively; future optimization should be driven by production
workload and a fresh query plan.

### Reproducible validation

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_sql\test_marts_integration.py -q
.\.venv\Scripts\python.exe -m pytest tests -q
```

The full-data mart integration test passed (`1 passed in 224.67s`) and the
final regression suite passed (`16 passed, 6 skipped in 1.55s`). The test
creates a UUID schema and loads the source only inside that schema; the
full-data loader/idempotency test was not rerun for this mart checkpoint.

# Nexora Commerce AI ERD

## Grain and relationships

```mermaid
erDiagram
    customers {
        varchar source_system PK
        bigint customer_id PK
        varchar primary_country
        timestamp first_invoice_date
        timestamp last_invoice_date
        int total_orders_lifetime
        numeric total_merchandise_spend
        char source_file_sha256
    }

    products {
        varchar source_system PK
        varchar stock_code PK
        varchar primary_description
        varchar product_type
        boolean is_physical_merchandise
        numeric median_unit_price
        timestamp first_seen_date
        timestamp last_seen_date
        char source_file_sha256
    }

    invoices {
        varchar source_system PK
        varchar invoice_number PK
        bigint customer_id FK
        timestamp invoice_date
        varchar country
        varchar invoice_type
        int total_line_count
        bigint total_quantity
        numeric total_invoice_amount
        char source_file_sha256
    }

    invoice_lines {
        bigint line_id PK
        varchar source_system
        varchar source_line_key UK
        varchar source_sheet
        bigint source_row_number
        char source_file_sha256
        varchar invoice_number FK
        varchar stock_code FK
        bigint customer_id FK
        varchar description
        timestamp invoice_date
        int quantity
        numeric unit_price
        numeric line_total
        boolean is_duplicate_within_sheet
        boolean is_duplicate_cross_sheet
        boolean is_cancellation
        boolean is_bad_debt_adjustment
        boolean is_negative_quantity
        boolean is_return
        boolean is_inventory_adjustment
        boolean has_customer_id
        boolean has_description
        boolean has_valid_price
        boolean is_price_zero
        boolean is_price_negative
        boolean is_non_product
        boolean is_unknown_special_code
        boolean is_valid_sale
    }

    customers ||--o{ invoices : "customer_id"
    customers ||--o{ invoice_lines : "customer_id"
    invoices ||--|{ invoice_lines : "invoice_number"
    products ||--o{ invoice_lines : "stock_code"
```

## Cardinality

- `customers` to `invoices`: **1:N**. One identified customer can have many
  invoice headers; an invoice has zero or one customer because guest lines
  retain a nullable `customer_id`.
- `customers` to `invoice_lines`: **1:N**. One identified customer can have
  many lines; a line may have no customer.
- `invoices` to `invoice_lines`: **1:N**. Each invoice header has one or more
  source transaction lines.
- `products` to `invoice_lines`: **1:N**. One source-scoped stock code can
  occur on many lines; each line references one product.

The source namespace is part of every entity identity. This prevents an
invoice or stock code from UCI being accidentally joined to an identically
named key from MMRec or Amazon.

`invoice_lines` also enforces uniqueness for
`(source_system, source_line_key)` and
`(source_system, source_sheet, source_row_number)`. These are source
provenance constraints rather than additional business grains.

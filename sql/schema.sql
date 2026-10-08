-- Nexora Commerce AI relational foundation.
-- Loaders must populate source_line_key from source_system, source_sheet, and
-- a deterministic source row ordinal. Raw and processed files are read-only.

BEGIN;

CREATE TABLE customers (
    source_system VARCHAR(32) NOT NULL,
    customer_id BIGINT NOT NULL,
    primary_country VARCHAR(64) NOT NULL,
    first_invoice_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    last_invoice_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    total_orders_lifetime INTEGER NOT NULL CHECK (total_orders_lifetime >= 0),
    total_merchandise_spend NUMERIC(14, 2) NOT NULL,
    source_file_sha256 CHAR(64) NOT NULL,
    PRIMARY KEY (source_system, customer_id)
);

CREATE TABLE products (
    source_system VARCHAR(32) NOT NULL,
    stock_code VARCHAR(32) NOT NULL,
    primary_description VARCHAR(256),
    product_type VARCHAR(32) NOT NULL,
    is_physical_merchandise BOOLEAN NOT NULL,
    median_unit_price NUMERIC(12, 2),
    first_seen_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    last_seen_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    source_file_sha256 CHAR(64) NOT NULL,
    PRIMARY KEY (source_system, stock_code),
    CHECK (stock_code <> ''),
    CHECK (median_unit_price IS NULL OR median_unit_price >= 0)
);

CREATE TABLE invoices (
    source_system VARCHAR(32) NOT NULL,
    invoice_number VARCHAR(32) NOT NULL,
    customer_id BIGINT,
    invoice_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    country VARCHAR(64) NOT NULL,
    invoice_type VARCHAR(32) NOT NULL,
    total_line_count INTEGER NOT NULL CHECK (total_line_count > 0),
    total_quantity BIGINT NOT NULL,
    total_invoice_amount NUMERIC(14, 2) NOT NULL,
    source_file_sha256 CHAR(64) NOT NULL,
    PRIMARY KEY (source_system, invoice_number),
    CHECK (invoice_number <> ''),
    CHECK (
        invoice_type IN (
            'SALE',
            'CANCELLATION',
            'INVENTORY_ADJUSTMENT',
            'BAD_DEBT_ADJUSTMENT'
        )
    ),
    FOREIGN KEY (source_system, customer_id)
        REFERENCES customers (source_system, customer_id)
        ON DELETE RESTRICT
);

CREATE TABLE invoice_lines (
    line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_system VARCHAR(32) NOT NULL,
    source_line_key VARCHAR(128) NOT NULL,
    source_sheet VARCHAR(64) NOT NULL,
    source_row_number BIGINT NOT NULL CHECK (source_row_number > 0),
    source_file_sha256 CHAR(64) NOT NULL,
    invoice_number VARCHAR(32) NOT NULL,
    stock_code VARCHAR(32) NOT NULL,
    customer_id BIGINT,
    description VARCHAR(256),
    invoice_date TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    line_total NUMERIC(14, 2) NOT NULL
        GENERATED ALWAYS AS (
            ROUND(quantity::NUMERIC * unit_price, 2)
        ) STORED,
    is_duplicate_within_sheet BOOLEAN NOT NULL,
    is_duplicate_cross_sheet BOOLEAN NOT NULL,
    is_cancellation BOOLEAN NOT NULL,
    is_bad_debt_adjustment BOOLEAN NOT NULL,
    is_negative_quantity BOOLEAN NOT NULL,
    is_return BOOLEAN NOT NULL,
    is_inventory_adjustment BOOLEAN NOT NULL,
    has_customer_id BOOLEAN NOT NULL,
    has_description BOOLEAN NOT NULL,
    has_valid_price BOOLEAN NOT NULL,
    is_price_zero BOOLEAN NOT NULL,
    is_price_negative BOOLEAN NOT NULL,
    is_non_product BOOLEAN NOT NULL,
    is_unknown_special_code BOOLEAN NOT NULL,
    is_valid_sale BOOLEAN NOT NULL,
    UNIQUE (source_system, source_line_key),
    UNIQUE (source_system, source_sheet, source_row_number),
    CHECK (invoice_number <> ''),
    CHECK (stock_code <> ''),
    FOREIGN KEY (source_system, invoice_number)
        REFERENCES invoices (source_system, invoice_number)
        ON DELETE RESTRICT,
    FOREIGN KEY (source_system, stock_code)
        REFERENCES products (source_system, stock_code)
        ON DELETE RESTRICT,
    FOREIGN KEY (source_system, customer_id)
        REFERENCES customers (source_system, customer_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_invoices_customer
    ON invoices (source_system, customer_id);

CREATE INDEX idx_invoices_date
    ON invoices (source_system, invoice_date);

CREATE INDEX idx_invoice_lines_invoice
    ON invoice_lines (source_system, invoice_number);

CREATE INDEX idx_invoice_lines_product
    ON invoice_lines (source_system, stock_code);

CREATE INDEX idx_invoice_lines_customer
    ON invoice_lines (source_system, customer_id);

CREATE INDEX idx_invoice_lines_date
    ON invoice_lines (source_system, invoice_date);

COMMIT;

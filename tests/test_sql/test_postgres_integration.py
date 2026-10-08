import os
from pathlib import Path

import pytest


DATABASE_URL = os.getenv("NEXORA_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="NEXORA_TEST_DATABASE_URL is not configured",
)


def test_schema_applies_and_enforces_referential_integrity() -> None:
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    engine = sqlalchemy.create_engine(DATABASE_URL)
    schema = (
        Path(__file__).parents[2] / "sql" / "schema.sql"
    ).read_text(encoding="utf-8")
    with engine.begin() as connection:
        for statement in schema.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        tables = connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                      'customers', 'products', 'invoices', 'invoice_lines'
                  )
                """
            )
        ).scalars().all()
        assert set(tables) == {
            "customers",
            "products",
            "invoices",
            "invoice_lines",
        }

        connection.execute(
            text(
                """
                INSERT INTO customers (
                    source_system, customer_id, primary_country,
                    first_invoice_date, last_invoice_date,
                    total_orders_lifetime, total_merchandise_spend,
                    source_file_sha256
                ) VALUES (
                    'TEST', 1, 'United Kingdom',
                    '2010-01-01 00:00:00', '2010-01-01 00:00:00',
                    1, 19.99, :sha
                )
                """
            ),
            {"sha": "0" * 64},
        )
        connection.execute(
            text(
                """
                INSERT INTO products (
                    source_system, stock_code, primary_description,
                    product_type, is_physical_merchandise,
                    median_unit_price, first_seen_date, last_seen_date,
                    source_file_sha256
                ) VALUES (
                    'TEST', 'SPECIAL', 'Special item',
                    'PHYSICAL_MERCHANDISE', TRUE, 19.99,
                    '2010-01-01 00:00:00', '2010-01-01 00:00:00', :sha
                )
                """
            ),
            {"sha": "0" * 64},
        )
        connection.execute(
            text(
                """
                INSERT INTO invoices (
                    source_system, invoice_number, customer_id,
                    invoice_date, country, invoice_type,
                    total_line_count, total_quantity,
                    total_invoice_amount, source_file_sha256
                ) VALUES (
                    'TEST', '100001', 1, '2010-01-01 00:00:00',
                    'United Kingdom', 'SALE', 1, 1, 19.99, :sha
                )
                """
            ),
            {"sha": "0" * 64},
        )
        connection.execute(
            text(
                """
                INSERT INTO invoice_lines (
                    source_system, source_line_key, source_sheet,
                    source_row_number, source_file_sha256,
                    invoice_number, stock_code, customer_id, description,
                    invoice_date, quantity, unit_price,
                    is_duplicate_within_sheet, is_duplicate_cross_sheet,
                    is_cancellation, is_bad_debt_adjustment,
                    is_negative_quantity, is_return,
                    is_inventory_adjustment, has_customer_id,
                    has_description, has_valid_price, is_price_zero,
                    is_price_negative, is_non_product,
                    is_unknown_special_code, is_valid_sale
                ) VALUES (
                    'TEST', 'TEST:sheet:1', 'sheet', 1, :sha,
                    '100001', 'SPECIAL', NULL, 'Special item',
                    '2010-01-01 00:00:00', 1, 19.99,
                    FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE,
                    FALSE, TRUE, TRUE, FALSE, FALSE, FALSE, FALSE, TRUE
                )
                """
            ),
            {"sha": "0" * 64},
        )
        row = connection.execute(
            text(
                """
                SELECT customer_id, line_total
                FROM invoice_lines
                WHERE source_system = 'TEST'
                  AND source_line_key = 'TEST:sheet:1'
                """
            )
        ).one()
        assert row.customer_id is None
        assert str(row.line_total) == "19.99"

        with connection.begin_nested():
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO invoice_lines (
                            source_system, source_line_key, source_sheet,
                            source_row_number, source_file_sha256,
                            invoice_number, stock_code, invoice_date,
                            quantity, unit_price,
                            is_duplicate_within_sheet,
                            is_duplicate_cross_sheet,
                            is_cancellation, is_bad_debt_adjustment,
                            is_negative_quantity, is_return,
                            is_inventory_adjustment, has_customer_id,
                            has_description, has_valid_price, is_price_zero,
                            is_price_negative, is_non_product,
                            is_unknown_special_code, is_valid_sale
                        ) VALUES (
                            'TEST', 'TEST:invalid:1', 'sheet', 2, :sha,
                            'missing-invoice', 'SPECIAL',
                            '2010-01-01 00:00:00', 1, 1.00,
                            FALSE, FALSE, FALSE, FALSE, FALSE, FALSE,
                            FALSE, FALSE, FALSE, TRUE, FALSE, FALSE,
                            FALSE, FALSE, TRUE
                        )
                        """
                    ),
                    {"sha": "0" * 64},
                )

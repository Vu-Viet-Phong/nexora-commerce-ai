from pathlib import Path

import pytest
from sqlalchemy import text


def test_schema_applies_and_enforces_referential_integrity(database_sandbox) -> None:
    sqlalchemy = pytest.importorskip("sqlalchemy")
    from sqlalchemy.exc import IntegrityError

    schema = (Path(__file__).parents[2] / "sql" / "schema.sql").read_text(
        encoding="utf-8"
    )
    with database_sandbox.engine.begin() as connection:
        database_sandbox.set_search_path(connection)
        for statement in schema.split(";"):
            if statement.strip():
                connection.execute(text(statement))
        tables = connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
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
        constraints = connection.execute(
            text(
                """
                SELECT table_name, constraint_type
                FROM information_schema.table_constraints
                WHERE table_schema = current_schema()
                  AND table_name IN (
                      'customers', 'products', 'invoices', 'invoice_lines'
                  )
                """
            )
        ).all()
        constraint_types = {(row[0], row[1]) for row in constraints}
        assert ("customers", "PRIMARY KEY") in constraint_types
        assert ("products", "PRIMARY KEY") in constraint_types
        assert ("invoices", "PRIMARY KEY") in constraint_types
        assert ("invoice_lines", "PRIMARY KEY") in constraint_types
        assert ("invoices", "FOREIGN KEY") in constraint_types
        assert ("invoice_lines", "FOREIGN KEY") in constraint_types
        assert ("invoice_lines", "UNIQUE") in constraint_types

        numeric_columns = connection.execute(
            text(
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND data_type = 'numeric'
                """
            )
        ).all()
        assert {
            (row[0], row[1]) for row in numeric_columns
        } >= {
            ("customers", "total_merchandise_spend"),
            ("products", "median_unit_price"),
            ("invoices", "total_invoice_amount"),
            ("invoice_lines", "unit_price"),
            ("invoice_lines", "line_total"),
        }

        indexes = connection.execute(
            text(
                """
                SELECT indexname
                FROM pg_indexes
                WHERE schemaname = current_schema()
                """
            )
        ).scalars().all()
        assert {
            "idx_invoices_customer",
            "idx_invoices_date",
            "idx_invoice_lines_invoice",
            "idx_invoice_lines_product",
            "idx_invoice_lines_customer",
            "idx_invoice_lines_date",
        } <= set(indexes)

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

        with connection.begin_nested() as savepoint:
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
            savepoint.rollback()

        with pytest.raises(RuntimeError):
            with connection.begin_nested() as savepoint:
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
                            'TEST', 'TEST:rollback:1', 'sheet', 4, :sha,
                            '100001', 'SPECIAL',
                            '2010-01-01 00:00:00', 1, 1.00,
                            FALSE, FALSE, FALSE, FALSE, FALSE, FALSE,
                            FALSE, FALSE, FALSE, TRUE, FALSE, FALSE,
                            FALSE, FALSE, TRUE
                        )
                        """
                    ),
                    {"sha": "0" * 64},
                )
                raise RuntimeError("intentional savepoint rollback")

        with connection.begin_nested() as savepoint:
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
                            'TEST', 'TEST:sheet:1', 'sheet', 3, :sha,
                            '100001', 'SPECIAL',
                            '2010-01-01 00:00:00', 1, 19.99,
                            FALSE, FALSE, FALSE, FALSE, FALSE, FALSE,
                            FALSE, FALSE, TRUE, TRUE, FALSE, FALSE,
                            FALSE, FALSE, TRUE
                        )
                        """
                    ),
                    {"sha": "0" * 64},
                )
            savepoint.rollback()

        with connection.begin_nested() as savepoint:
            with pytest.raises(IntegrityError):
                connection.execute(
                    text(
                        """
                        INSERT INTO invoices (
                            source_system, invoice_number, customer_id,
                            invoice_date, country, invoice_type,
                            total_line_count, total_quantity,
                            total_invoice_amount, source_file_sha256
                        ) VALUES (
                            'TEST', '100002', 999,
                            '2010-01-01 00:00:00', 'United Kingdom',
                            'SALE', 1, 1, 1.00, :sha
                        )
                        """
                    ),
                    {"sha": "0" * 64},
                )
            savepoint.rollback()

        assert connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM invoice_lines
                WHERE source_system = 'TEST'
                """
            )
        ).scalar_one() == 1

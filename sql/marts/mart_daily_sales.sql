CREATE OR REPLACE VIEW mart_daily_sales AS
WITH eligible_lines AS (
    SELECT
        i.invoice_date::date AS calendar_day,
        i.country,
        p.is_physical_merchandise,
        l.invoice_number,
        l.quantity,
        l.line_total,
        l.is_valid_sale,
        l.is_cancellation,
        l.is_non_product
    FROM invoice_lines AS l
    JOIN invoices AS i
      ON i.source_system = l.source_system
     AND i.invoice_number = l.invoice_number
    JOIN products AS p
      ON p.source_system = l.source_system
     AND p.stock_code = l.stock_code
    WHERE l.source_system = 'UCI'
      AND l.is_inventory_adjustment = FALSE
      AND (
          l.is_valid_sale = TRUE
          OR (l.is_cancellation = TRUE AND l.is_non_product = FALSE)
      )
)
SELECT
    calendar_day,
    country,
    is_physical_merchandise,
    SUM(CASE WHEN is_valid_sale THEN line_total ELSE 0 END)::NUMERIC(14, 2)
        AS gross_sales,
    SUM(CASE WHEN is_valid_sale THEN line_total ELSE 0 END)::NUMERIC(14, 2)
        AS valid_sales_revenue,
    SUM(
        CASE
            WHEN is_cancellation AND NOT is_non_product THEN line_total
            ELSE 0
        END
    )::NUMERIC(14, 2) AS return_value,
    SUM(
        CASE
            WHEN is_valid_sale OR (is_cancellation AND NOT is_non_product)
                THEN line_total
            ELSE 0
        END
    )::NUMERIC(14, 2) AS net_sales,
    COUNT(DISTINCT CASE WHEN is_valid_sale THEN invoice_number END)
        AS distinct_invoices,
    COALESCE(SUM(CASE WHEN is_valid_sale THEN quantity ELSE 0 END), 0)
        AS units_sold,
    COALESCE(
        -SUM(
            CASE
                WHEN is_cancellation AND NOT is_non_product THEN quantity
                ELSE 0
            END
        ),
        0
    ) AS units_returned
FROM eligible_lines
GROUP BY calendar_day, country, is_physical_merchandise;

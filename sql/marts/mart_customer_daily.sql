CREATE OR REPLACE VIEW mart_customer_daily AS
WITH eligible_lines AS (
    SELECT
        l.customer_id,
        i.invoice_date::date AS calendar_day,
        l.invoice_number,
        l.line_total,
        l.is_valid_sale,
        l.is_cancellation,
        l.is_non_product
    FROM invoice_lines AS l
    JOIN invoices AS i
      ON i.source_system = l.source_system
     AND i.invoice_number = l.invoice_number
    WHERE l.source_system = 'UCI'
      AND l.customer_id IS NOT NULL
      AND l.is_inventory_adjustment = FALSE
      AND (
          l.is_valid_sale = TRUE
          OR (l.is_cancellation = TRUE AND l.is_non_product = FALSE)
      )
)
SELECT
    customer_id,
    calendar_day,
    COUNT(DISTINCT CASE WHEN is_valid_sale THEN invoice_number END)
        AS order_frequency,
    SUM(CASE WHEN is_valid_sale THEN line_total ELSE 0 END)::NUMERIC(14, 2)
        AS gross_spend,
    SUM(
        CASE
            WHEN is_cancellation AND NOT is_non_product THEN line_total
            ELSE 0
        END
    )::NUMERIC(14, 2) AS return_value,
    SUM(line_total)::NUMERIC(14, 2) AS net_spend,
    COUNT(*) FILTER (WHERE is_valid_sale) AS valid_transaction_count
FROM eligible_lines
GROUP BY customer_id, calendar_day;

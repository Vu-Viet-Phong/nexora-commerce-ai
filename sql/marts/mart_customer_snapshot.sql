CREATE OR REPLACE VIEW mart_customer_snapshot AS
WITH customer_activity AS (
    SELECT
        l.customer_id,
        MIN(i.invoice_date::date) FILTER (WHERE l.is_valid_sale)
            AS first_purchase_date,
        MAX(i.invoice_date::date) FILTER (WHERE l.is_valid_sale)
            AS last_purchase_date,
        COUNT(DISTINCT l.invoice_number)
            FILTER (WHERE l.is_valid_sale) AS frequency,
        SUM(l.line_total)
            FILTER (WHERE l.is_valid_sale)::NUMERIC(14, 2) AS gross_monetary,
        SUM(l.line_total)
            FILTER (
                WHERE l.is_cancellation
                  AND NOT l.is_non_product
            )::NUMERIC(14, 2) AS return_value
    FROM invoice_lines AS l
    JOIN invoices AS i
      ON i.source_system = l.source_system
     AND i.invoice_number = l.invoice_number
    WHERE l.source_system = 'UCI'
      AND l.customer_id IS NOT NULL
      AND l.is_inventory_adjustment = FALSE
    GROUP BY l.customer_id
),
metrics AS (
    SELECT
        c.customer_id,
        c.primary_country,
        DATE '2011-12-10' - a.last_purchase_date AS recency_days,
        COALESCE(a.frequency, 0)::INTEGER AS frequency,
        COALESCE(a.gross_monetary, 0)::NUMERIC(14, 2) AS gross_monetary,
        COALESCE(a.return_value, 0)::NUMERIC(14, 2) AS return_value,
        (
            COALESCE(a.gross_monetary, 0) + COALESCE(a.return_value, 0)
        )::NUMERIC(14, 2) AS monetary,
        a.first_purchase_date,
        a.last_purchase_date
    FROM customers AS c
    LEFT JOIN customer_activity AS a
      ON a.customer_id = c.customer_id
     AND c.source_system = 'UCI'
    WHERE c.source_system = 'UCI'
)
SELECT
    customer_id,
    primary_country,
    recency_days,
    frequency,
    monetary,
    CASE
        WHEN frequency > 0
            THEN ROUND(gross_monetary / frequency, 2)
        ELSE NULL
    END::NUMERIC(14, 2) AS average_order_value,
    CASE
        WHEN first_purchase_date IS NOT NULL
            THEN DATE '2011-12-10' - first_purchase_date
        ELSE NULL
    END AS tenure_days,
    first_purchase_date,
    last_purchase_date
FROM metrics;

# Stage 2 Business Metric Contract & QA Guidelines

**Project:** Nexora Commerce AI  
**Pipeline Stage:** Stage 2 — PostgreSQL & Data Modeling / Stage 3 — Analytics & EDA  
**Role:** Senior Data Architect & SQL QA Reviewer  
**Status:** **OFFICIAL METRIC CONTRACT**

---

## 1. Purpose of the Metric Contract

In enterprise data platforms, metric divergence across dashboards, reports, and machine learning features is a primary source of business confusion. 

This document defines the **canonical mathematical formulas, operational SQL filters, dimensional grains, and boundary conditions** for all core e-commerce metrics in Nexora Commerce AI. Any SQL view, data mart, dashboard, or ML pipeline must strictly adhere to these definitions.

---

## 2. Core Business Metric Contract

### 2.1 Gross Merchandise Sales (GMS)
- **Business Definition:** The total top-line monetary value of all valid physical merchandise transactions before deducting returns, discounts, or cancellations.
- **Mathematical Formula:**
  $$\text{Gross Merchandise Sales} = \sum (\text{Quantity} \times \text{UnitPrice}) \quad \forall \text{ records where } \texttt{is\_valid\_sale} = \text{TRUE}$$
- **SQL Implementation:**
  ```sql
  SELECT SUM(line_total) AS gross_merchandise_sales
  FROM fact_invoice_lines
  WHERE is_valid_sale = TRUE;
  ```
- **Dimensional Grain:** Evaluated at Line Item level (`fact_invoice_lines`); aggregateable by Date, Country, Customer, Product.
- **Baseline Benchmark Value:** **£19,700,954.44** in PostgreSQL `NUMERIC`
  arithmetic (the source float audit remains £19,700,939.69).
- **Mandatory Inclusions:**
  - Standard physical products with `Quantity > 0` and `Price > 0`.
  - Guest checkout transactions (`customer_id IS NULL` is included, contributing £2,576,013.46).
  - Multi-line POS duplicate lines (`is_duplicate_within_sheet = TRUE` is included by default).
- **Mandatory Exclusions:**
  - Cancellations (`is_cancellation = TRUE`).
  - Inventory shrinkage / write-offs (`is_inventory_adjustment = TRUE`).
  - Bad debt accounting adjustments (`is_bad_debt_adjustment = TRUE`).
  - Non-product service codes (`is_non_product = TRUE`, e.g. `POST`, `DOT`, `M`, `BANK CHARGES`, `AMAZONFEE`).
  - Zero-price samples / gifts (`is_price_zero = TRUE`).

---

### 2.2 Merchandise Return Value
- **Business Definition:** The total monetary value of customer-initiated cancellations and returns of physical merchandise reversing prior sales.
- **Mathematical Formula:**
  $$\text{Merchandise Return Value} = \sum (\text{Quantity} \times \text{UnitPrice}) \quad \forall \text{ records where } \texttt{is\_cancellation} = \text{TRUE} \text{ and } \texttt{is\_non\_product} = \text{FALSE}$$
- **SQL Implementation:**
  ```sql
  SELECT SUM(line_total) AS merchandise_return_value
  FROM fact_invoice_lines
  WHERE is_cancellation = TRUE AND is_non_product = FALSE;
  ```
- **Dimensional Grain:** Evaluated at Line Item level; aggregateable by Date, Country, Customer, Product.
- **Baseline Benchmark Value:** **-£719,692.94** in PostgreSQL `NUMERIC`
  arithmetic (the source float audit remains -£719,656.34).
- **Mandatory Inclusions:** Physical merchandise items under invoice prefix `'C'`.
- **Mandatory Exclusions:**
  - Non-product fee reversals (`is_non_product = TRUE`, e.g. reversed Amazon fees, manual fee refunds totaling -£745,647.32).
  - Warehouse inventory shrinkage write-offs (`is_inventory_adjustment = TRUE`).

---

### 2.3 Net Merchandise Revenue
- **Business Definition:** The net realized top-line revenue generated from physical product commerce after subtracting customer returns.
- **Mathematical Formula:**
  $$\text{Net Merchandise Revenue} = \text{Gross Merchandise Sales} + \text{Merchandise Return Value}$$
- **SQL Implementation:**
  ```sql
  SELECT 
      SUM(CASE WHEN is_valid_sale = TRUE THEN line_total ELSE 0 END) +
      SUM(CASE WHEN is_cancellation = TRUE AND is_non_product = FALSE THEN line_total ELSE 0 END) AS net_merchandise_revenue
  FROM fact_invoice_lines;
  ```
- **Dimensional Grain:** Order, Customer, Product, Date.
- **Baseline Benchmark Value:** **£18,981,261.50**
- **Business Impact:** This is the primary target variable for company-level merchandise financial reporting.

---

### 2.4 Valid Order Count
- **Business Definition:** The total number of distinct, successful sales orders placed by customers.
- **Mathematical Formula:**
  $$\text{Order Count} = \text{COUNT}(\text{DISTINCT } \text{Invoice}) \quad \forall \text{ records where } \texttt{is\_valid\_sale} = \text{TRUE}$$
- **SQL Implementation:**
  ```sql
  SELECT COUNT(DISTINCT invoice_number) AS valid_order_count
  FROM fact_invoice_lines
  WHERE is_valid_sale = TRUE;
  ```
- **Dimensional Grain:** Header / Invoice Grain (`fact_invoices`).
- **Baseline Benchmark Value:** **39,516 orders** (out of 53,628 total invoices).
- **Mandatory Exclusions:** Cancellation invoices (8,292 orders), bad debt adjustments (6 invoices), pure inventory write-off invoices (3,393 single-line invoices).

---

### 2.5 Average Order Value (AOV)
- **Business Definition:** The average gross revenue generated per valid sales transaction.
- **Mathematical Formula:**
  $$\text{Average Order Value (AOV)} = \frac{\text{Gross Merchandise Sales}}{\text{Valid Order Count}} = \frac{£19,700,954.44}{39,516}$$
- **SQL Implementation:**
  ```sql
  SELECT 
      SUM(line_total) / COUNT(DISTINCT invoice_number) AS average_order_value
  FROM fact_invoice_lines
  WHERE is_valid_sale = TRUE;
  ```
- **Dimensional Grain:** Customer, Segment, Temporal Cohort.
- **Baseline Benchmark Value:** **£498.56** per order (reflecting the mixed B2B wholesale and direct retail nature of the dataset).

---

### 2.6 Active Customer Count & Population
- **Business Definition:** The total count of unique identified individuals or companies who engaged in commercial transactions.
- **Mathematical Formula:**
  $$\text{Customer Population} = \text{COUNT}(\text{DISTINCT } \text{Customer ID}) \quad \forall \text{ records where } \texttt{has\_customer\_id} = \text{TRUE}$$
- **SQL Implementation:**
  ```sql
  SELECT COUNT(DISTINCT customer_id) AS total_customer_count
  FROM dim_customers;
  ```
- **Baseline Benchmark Value:** Exactly **5,942 unique customers**.
- **Active Customers (in given period $T$):** Distinct `customer_id` with $\ge 1$ valid sale in window $T$.

---

### 2.7 Repeat Purchase Rate
- **Business Definition:** The proportion of identified customers who have placed two or more separate valid sales orders over their lifecycle.
- **Mathematical Formula:**
  $$\text{Repeat Purchase Rate} = \frac{\text{Count of Customers with } \ge 2 \text{ Valid Orders}}{\text{Total Identified Customers with } \ge 1 \text{ Valid Order}}$$
- **SQL Implementation:**
  ```sql
  WITH customer_orders AS (
      SELECT 
          customer_id,
          COUNT(DISTINCT invoice_number) AS order_count
      FROM fact_invoice_lines
      WHERE is_valid_sale = TRUE AND customer_id IS NOT NULL
      GROUP BY customer_id
  )
  SELECT 
      COUNT(CASE WHEN order_count >= 2 THEN 1 END)::NUMERIC / COUNT(*) AS repeat_purchase_rate
  FROM customer_orders;
  ```
- **Dimensional Grain:** Customer Population level.

---

## 3. STRICTLY FORBIDDEN / DEFERRED METRICS

To prevent fabricated analytics and pseudo-scientific modeling, the following metrics are **STRICTLY FORBIDDEN** from being computed, presented in dashboards, or used in Stage 2/3/4 models:

| Metric | Why It Is Strictly Forbidden | Missing Ground Truth Data |
|---|---|---|
| **Conversion Rate (CR)** | **PROHIBITED.** The dataset contains only completed sales transaction receipts. There is zero telemetry on web sessions, page views, impressions, unique visitors, or abandoned carts. Calculating $\frac{\text{Orders}}{\text{Visitors}}$ without visitor data is impossible. | Web traffic logs, Google Analytics, Clickstream sessions. |
| **Gross Margin / Net Profit** | **PROHIBITED.** The dataset contains only selling price (`Price`), not unit wholesale cost or Cost of Goods Sold (COGS). Computing profit as $\text{Price} \times \text{Quantity}$ conflates Revenue with Profit. | Supplier purchase price, bill of materials, COGS. |
| **Return on Ad Spend (ROAS) / ROI** | **PROHIBITED.** There is zero data on marketing campaign expenditure, PPC ad spend, SEO costs, or influencer budgets. | Ad spend, marketing channel attribution logs. |
| **Customer Acquisition Cost (CAC)** | **PROHIBITED.** Marketing spend by channel/cohort is completely absent. | Sales & Marketing OPEX data. |
| **Inventory Turnover Ratio** | **DEFERRED.** While sales quantity is known, beginning/ending warehouse balance snapshot tables are absent. | Daily balance stock snapshot tables. |

---

## 4. Financial Reconciliation Summary

```
Total Ledger Gross Lines (£20,770,293.94)
  ├── Physical Valid Merchandise Sales ........... £19,700,954.44  (is_valid_sale = TRUE)
  ├── Non-Product Services & Freight ............ +£821,740.17  (POST, DOT, M, C2, D, S, BANK CHARGES)
  ├── Gift Vouchers & Tested Services ..........   +£1,686.52  (GIFT_0001_*, CRUK, TEST*)
  ├── Promotional / Zero-Price Items ............        £0.00  (is_price_zero = TRUE)
  └── Accounting Bad Debt Credit ................  +£11,062.06  (Invoice A563185)

Total Ledger Deductions (-£1,860,531.82)
  ├── Physical Merchandise Returns .............   -£719,692.94  (is_cancellation = TRUE & physical)
  ├── Service & Fee Reversals ..................   -£745,647.32  (Manual, Amazon fee, Bank charge refunds)
  ├── Bad Debt Accounting Write-offs ...........   -£158,676.14  (Invoices A506401, A516228, A528059, A563186, A563187)
  ├── Negative Non-C Inventory Shrinkage .......        £0.00  (Price = 0.0)
  └── Net Reversal Adjustments .................  -£236,552.02

========================================================================================
TOTAL LEDGER NET CASH FLOW ..................... £18,909,762.10  (1,044,848 rows exact sum after NUMERIC rounding)
TOTAL NET MERCHANDISE REVENUE .................. £18,981,261.50  (Gross Sales + Merchandise Returns)
========================================================================================
```

---

## 5. QA Verification Protocol

Every SQL Data Mart query in `sql/marts/` must be validated against the Python Pandas benchmark before acceptance:
1. `SUM(line_total)` across all valid sales in `mart_daily_sales` must equal **£19,700,954.44** ($\pm £0.01$) after PostgreSQL `NUMERIC(12,2)` line rounding.
2. `SUM(line_total)` across all returns in `mart_daily_sales` must equal **-£719,692.94** ($\pm £0.01$).
3. Total unique customers in `mart_customer_snapshot` must equal **5,942**.
4. Sum of lifetime spend across all 5,942 customers in `mart_customer_snapshot` must equal **£16,411,894.73** (reflecting net spend of identified customers).

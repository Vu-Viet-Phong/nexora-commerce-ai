# Nexora Commerce AI - Cleaning Decision Matrix (Stage 1)

> **Document Version:** 1.1.0 (Post-Review Final Sign-Off)  
> **Author:** Senior Data Quality Engineer & Data Science Reviewer / Final QA Gatekeeper  
> **Scope:** Stage 1 Data Cleaning & Preparation Rules for UCI Online Retail II  
> **Source File:** `data/raw/uci/online_retail_II.xlsx` (SHA-256: `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`)  
> **Baseline Cleaned Count:** 1,044,848 rows (from 1,067,371 raw rows after resolving 22,523 cross-sheet duplicate overlap records)  
> **Stage 1 Approval Status:** **APPROVED (READY FOR STAGE 2)**

---

## 1. Executive Summary & Core Principles

1. **Non-Destructive Cleaning:** Raw data is immutable. No row is permanently dropped except verified physical workbook duplicate overlap between Excel sheets. All anomalies, cancellations, and missing fields are retained and classified with boolean quality flags.
2. **Explainable Quality Flags:** Downstream analytics (Merchandise Revenue, Customer RFM, Churn, Demand Forecasting) filter records explicitly using boolean flags rather than relying on an opaque, destructive pipeline.
3. **Strict Separation of Business Concepts:**
   - Customer Returns ($\text{Invoice starts with } \texttt{'C'}$, $\text{is\_return = True}$) $\ne$ Warehouse Inventory Adjustments ($\text{Quantity} < 0, \text{Price} = 0, \text{Customer ID is NaN}$, $\text{is\_inventory\_adjustment = True}$).
   - Missing Customer ID $\ne$ Invalid Transaction. (Cash / guest checkouts are valid sales for revenue & inventory, but excluded from customer-level RFM).
   - Non-Product / Service Charges ($\texttt{POST}, \texttt{M}, \texttt{BANK CHARGES}, \texttt{AMAZONFEE}, \texttt{GIFT\_0001\_*}, \texttt{TEST*}, \texttt{CRUK}$) $\ne$ Physical Merchandise.
4. **Normalized Identifiers:** `StockCode` is standardized to uppercase string with trimmed whitespace while preserving missing values as `<NA>`.

---

## 2. Comprehensive Cleaning Decision Matrix

| Issue / Category | Detection Rule | Observed Count (Raw / Base) | Pipeline Action | Retain Raw Info? | Valid for Sales / Revenue? | Valid for Customer / RFM? | Valid for Demand Forecast? | Business Rationale | Edge Cases & Residual Risks |
|---|---|---|---|---|---|---|---|---|---|
| **Cross-Sheet Overlap Duplicates** | Exact 8-column match between `Year 2009-2010` and `Year 2010-2011` within window `2010-12-01` to `2010-12-09` | 22,523 rows (22,202 distinct keys) | **Remove duplicate instance from 2nd sheet (`Year 2010-2011`)**; retain 1st instance | Yes (Flagged as `is_duplicate_cross_sheet` in interim) | Yes (1 instance only) | Yes (1 instance only) | Yes (1 instance only) | The two annual sheets overlap by 9 days (multisets are 100% identical). Retaining both double-counts £377,488.45 in revenue. | None. Multisets within window are 100% identical across all 8 fields. 0 cross-sheet duplicates exist outside this window. |
| **Within-Sheet Duplicates** | Identical 8 original columns occurring within the same sheet | 12,133 extra copies (23,430 rows in raw groups; 11,812 extra copies / 22,813 rows in base) | **RETAIN ALL; Flag with `is_duplicate_within_sheet = True`** | Yes | Yes (Unless strict deduplication policy applied) | Yes | Yes | Dataset has no line-item unique identifier. Customers ordering multiple units in separate lines on the same invoice is common in wholesale/retail POS. Blindly dropping causes £54,228.42 undercount. | Some rows might be true accidental double-clicks at checkout. A parameter flag `drop_within_sheet_duplicates` can be exposed for sensitivity analysis. |
| **Cancellations / Customer Returns** | `Invoice` string starts with `'C'` or `'c'` (case-insensitive) | 19,494 raw rows / 19,165 base rows (8,292 unique invoices) | **RETAIN ALL; Flag with `is_cancellation = True`, `is_return = True`, `is_valid_sale = False`** | Yes | Yes (As negative offset to calculate Net Revenue: -£1,465,303.66 total; -£719,656.34 product only) | Yes (For Net Monetary & Return Behavior modeling) | Separate target (Model gross demand & return rate separately) | Cancellations represent legitimate return transactions that reverse previous sales. Must not be deleted. | 1 row (`C496350`) has `Quantity = +1, Price = 373.57` (Manual correction). 719 cancellation rows have missing `Customer ID`. |
| **Negative Quantity (Non-C)** | `Quantity < 0` AND `Invoice` does NOT start with `'C'` | 3,457 raw rows / 3,393 base rows (3,393 unique invoices) | **RETAIN ALL; Flag with `is_inventory_adjustment = True`, `is_negative_quantity = True`, `is_return = False`, `is_valid_sale = False`** | Yes | **NO (Revenue = £0.00)** | **NO (No Customer ID)** | **NO (Internal write-off, not customer demand)** | 100% of these records have `Price == 0.0` and `Customer ID is NaN`. 77.6% have missing Description; remaining have descriptions like *"damaged"*, *"lost"*, *"thrown away"*, *"check"*. These are warehouse stock adjustments, NOT customer returns. | Conflating these with customer returns would artificially inflate return rates and distort product demand forecasting. |
| **Zero Price (Price == 0.0)** | `Price == 0.0` | 6,207 raw rows / 6,024 base rows (2,631 positive qty, 3,393 negative qty) | **RETAIN ALL; Flag with `is_price_zero = True`** | Yes | **NO (Revenue = £0.00)** | **NO for RFM Monetary (can be included in Frequency if promotional sample)** | Quantity can be tracked as sample/giveaway volume | Price = 0 produces £0.00 revenue. Positive qty lines include promotional samples, gifts, or inventory found; negative qty lines are inventory adjustments. | 70 positive qty rows have a valid `Customer ID` (e.g. door mats, fairy lights given to customers). Tracked separately from merchandise sales. |
| **Negative Price (Price < 0.0)** | `Price < 0.0` | 5 raw rows / 5 base rows (Invoices `A506401`, `A516228`, `A528059`, `A563186`, `A563187`) | **RETAIN ALL; Flag with `is_price_negative = True`, `is_bad_debt_adjustment = True`, `is_valid_sale = False`** | Yes | **NO (Accounting adjustment, not merchandise)** | **NO (Customer ID is NaN)** | **NO** | All 5 rows have Description *"Adjust bad debt"*, StockCode `B`, Customer ID `NaN`, Invoice prefix `A`. Total value is -£158,676.14 (reversing uncollectible debt). | `A563185` has `Price = +11,062.06` (positive bad debt offset). Total prefix A rows = 6 rows (Net: -£147,614.08). |
| **Missing Customer ID** | `Customer ID` is `NaN` / `<NA>` | 243,007 raw rows (22.77%) / 235,287 base rows (22.52%) | **RETAIN ALL; Convert to nullable integer `Int64`; Flag with `has_customer_id = False`** | Yes | **YES (Valid for aggregate revenue, store sales, product velocity: £2,576,013.46 gross sales)** | **NO (Exclude from Customer-level RFM / Churn / Lifetime Value)** | **YES (Contributes to overall product demand)** | Represents guest checkout / walk-in POS transactions without loyalty card. Dropping would destroy 13.08% of gross merchandise revenue and 22.52% of transaction volume. | **DO NOT impute or fill with dummy ID (e.g. 99999)** as it creates a colossal "super-customer" that completely breaks RFM clustering and ML models. |
| **Missing Description** | `Description` is `NaN` / `<NA>` | 4,382 raw rows (0.411%) / 4,275 base rows (0.409%) | **RETAIN ALL; Convert to nullable string `string`; Flag with `has_description = False`** | Yes | **NO (All have `Price == 0.0` and `Customer ID is NaN`)** | **NO** | **NO** | 100% of missing description rows have `Price == 0.0` and missing `Customer ID`. They consist of 2,633 inventory adjustments and 1,642 zero-priced unallocated inventory counts. | None. Zero revenue impact. |
| **Service & Non-Product StockCodes** | StockCodes matching known service/overhead codes (`POST`, `DOT`, `M`, `C2`, `D`, `S`, `BANK CHARGES`, `ADJUST`, `ADJUST2`, `AMAZONFEE`, `B`, `CRUK`, `PADS`, `TEST001`, `TEST002`, `GIFT_0001_*`) | 5,805 base rows (4,755 positive lines, 1,050 cancellation lines) | **RETAIN ALL; Flag with `is_non_product = True`, `is_valid_sale = False` (or separate fee flag)** | Yes | Separate from Merchandise Revenue (Track as Fee/Postage/Discount line items) | Exclude from Product Recommenders; include in Customer Lifetime Value if fee was charged to customer | **NO (Exclude from merchandise demand forecasting)** | Charges like postage (£448k), manual adjustments (£340k), amazon fees (-£242k), bank charges (-£36k) are financial line items, not physical inventory demand. | `M` (Manual) can represent custom products or fee adjustments. `DCGS...` codes (e.g. `DCGS0058`) are legitimate products and are preserved as physical merchandise (`is_non_product = False`). |
| **Extreme Outlier Quantities** | $\| \text{Quantity} \| \ge 10,000$ or $> p_{99.9}$ (600 units) | 13 rows $\ge 10,000$; 927 rows $> 600$ | **RETAIN ALL; Expose raw values; Flag with `is_extreme_quantity` for modeling sensitivity** | Yes | Yes (Reflects actual B2B wholesale order volume) | Yes (With robust scaling / winsorization in Stage 3) | Winsorize or flag for separate B2B bulk forecasting model | Highest values are matched purchase-cancellation pairs (e.g. `581483` / `C581484` for 80,995 units; `541431` / `C541433` for 74,215 units) or legitimate wholesale orders (`502269` for 40,000 packs of tissues). | Automated deletion breaks financial reconciliation. Models must handle heavy-tailed B2B distributions via log-transform or separate segmentation. |
| **Extreme Outlier Prices** | $\text{Price} > p_{99.9}$ (£214.59) | 1,045 base rows $> p_{99.9}$ (£214.59) | **RETAIN ALL; Flag with `is_extreme_price`** | Yes | Yes | Yes | Yes | 94.6% (989 of 1,045) of extreme prices belong to non-product service codes (`Manual`, `AMAZONFEE`, `BANK CHARGES`, `POSTAGE`). High product prices reflect luxury giftware (e.g. `PICNIC BASKET WICKER 60 PIECES` at £649.50). | Filtering non-product codes automatically eliminates 95% of extreme price outliers. |
| **Incomplete Final Month (2011-12)** | `InvoiceDate` between `2011-12-01` and `2011-12-09` | 25,526 base rows (8 active trading days) | **RETAIN ALL; Add metadata note in temporal splits** | Yes | Yes | Yes | Truncate or weight when calculating monthly aggregates | Data collection ended mid-month on Dec 9, 2011. Monthly aggregation will show an artificial 70% drop compared to Nov 2011 unless normalized. | In Stage 6 forecasting, evaluate models on rolling daily/weekly windows or complete months rather than raw monthly sums. |

---

## 3. Decision Rules for Downstream Modules

### A. Stage 2: Exploratory Data Analysis & Business Intelligence
- **Gross Merchandise Revenue:** Filter `is_valid_sale == True`. Total: **£19,700,939.69**.
- **Customer Return Value (Merchandise):** Filter `is_cancellation == True & is_non_product == False`. Total: **-£719,656.34**.
- **Net Merchandise Revenue:** $\text{Gross} + \text{Return Value} = \mathbf{£18,981,283.35}$.
- **Service & Fee Net Total:** Filter `is_non_product == True | is_bad_debt_adjustment == True`. Total: **-£71,521.23**.
- **Total Ledger Net Total:** **£18,909,762.12**.

### B. Stage 3 & 4: Customer Analytics (RFM, Churn, LTV, Recommenders)
- **Population Definition:** Filter `has_customer_id == True` (809,561 rows across 5,942 unique customers).
- **Recency:** Maximum `InvoiceDate` per customer relative to dataset reference date (`2011-12-10 00:00:00`).
- **Frequency:** Count of unique `Invoice` orders where `is_valid_sale == True`.
- **Monetary:** Sum of `line_total` for `is_valid_sale == True` plus `is_cancellation == True` (reflecting net customer spend).

### C. Stage 6: Demand Forecasting & Inventory Management
- **Target Variable (Sales Demand):** Aggregate `Quantity` where `is_valid_sale == True` grouped by `StockCode` and daily/weekly frequency.
- **Exclusions:** Exclude `is_inventory_adjustment == True` (warehouse shrinkage/breakage is not customer demand).
- **Return Forecasting:** Model return probability / return quantity as a secondary output using `is_cancellation == True` (`is_return == True`).

---

## 4. Verification & Audit Trail Sign-Off

- **Raw SHA-256 Verified:** `bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980`
- **Total Raw Ingestion:** 1,067,371 rows across 2 sheets.
- **Cross-Sheet Overlap Deduplication:** 22,523 duplicate instances removed from Sheet 2.
- **Cleaned Dataset Preservation:** 1,044,848 rows retained with 100% data audit reconciliation.
- **QA Gatekeeper Sign-Off:** **STAGE 1 APPROVED**.

# Milestone 2.5 — contracts for integration after Milestone 2.4 approval

Status: **PREPARATION ONLY; MART CHECKS NOT EXECUTED OR ACTIVATED.**
The current quality runner emits three named SKIPs and never installs or queries
the marts. This document records contracts visible in the base commit
`a9710c2829d00b28b7cd69c2a00130fc94193780`; recheck the accepted Milestone 2.4
implementation before turning them into executable quality checks.

## Prerequisites

1. Milestone 2.4 has an explicit approval and its code is integrated.
2. The owner confirms final mart grains, columns, scope and date semantics.
3. Core/source checks are run on the same read-only snapshot.
4. Any tests that install mart views use only a separate Codex-owned schema/database.
5. Integration results are reviewed before Milestone 2.5 acceptance; this feature does not approve itself.

No SQL mart, Copilot test or current approval/learning-log file is edited here.

## Contracts from existing SQL

| Mart | Grain currently in SQL | Required checks to implement after approval |
|---|---|---|
| `mart_daily_sales` | `calendar_day, country, is_physical_merchandise` | Grain unique; gross_sales = valid_sales_revenue; return_value matches cancellation/non-product filter; net_sales = gross_sales + return_value; sums reconcile to eligible core lines; quantity aggregates and per-group distinct_invoices match core. |
| `mart_customer_daily` | `customer_id, calendar_day` | Grain unique; no NULL customers; order_frequency counts distinct valid invoices; gross_spend/return_value/net_spend and valid_transaction_count reconcile per group and globally for identified customers. |
| `mart_customer_snapshot` | `customer_id` | One row per UCI customer dimension, including customers without valid sales; frequency = distinct valid invoices; monetary = gross valid sales + physical returns; first/last purchase dates, recency, tenure and AOV match current accepted formulas. |

The current SQL filters the UCI namespace and uses `invoices.invoice_date::date`
as `calendar_day`, rather than each line timestamp. Source contains invoice
timestamp conflicts, so test expectations must mirror that explicit header date.

Daily sales eligibility currently requires:
`l.source_system='UCI'`, `NOT l.is_inventory_adjustment`, and
`l.is_valid_sale OR (l.is_cancellation AND NOT l.is_non_product)`.
Customer daily uses the same eligibility plus `customer_id IS NOT NULL`.
Guest sales remain in company daily totals and are excluded from customer marts.

Current snapshot SQL uses the fixed reference date `DATE '2011-12-10'`.
For valid-sale frequency > 0, AOV is rounded gross monetary / frequency;
otherwise AOV is NULL. Recency and tenure are NULL without valid purchase dates.
This records current SQL behavior; it does not introduce a new as-of-date policy.

Distinct invoice counts are not assumed additive across arbitrary groups.
Compare distinct counts at the same grain, and compute global distinct counts
directly from core lines. Financial expectations use stored NUMERIC line_total
and accepted filters; do not copy outdated float-based money benchmarks.

## Proposed small fixture scenarios

- Two valid merchandise lines of one invoice: gross sums both, order count remains one.
- A guest sale: included in company sales, absent from customer aggregates.
- A physical cancellation: signed return_value retained; net = gross + return.
- A non-product fee/reversal and inventory adjustment: excluded as current SQL specifies.
- Retained within-sheet duplicate lines: counted by the source contract, not dropped.
- An identified customer without valid sales: snapshot retained, frequency zero, purchase-based dates/AOV NULL.
- Two source namespaces sharing business IDs: accepted mart scope must prevent cross-source leakage.
- Line timestamps that differ from the canonical header timestamp: calendar grain follows accepted SQL.

Reuse the existing quality fixture infrastructure; do not run Copilot's integration
fixtures on its shared database. Full-data reconciliation stays separately opt-in.

## Activation checklist

Implement a dedicated mart-check module only after the prerequisites hold; replace
the current explicit SKIPs with checks of approved grains and aggregates. Add
unit/isolated PostgreSQL tests for the scenarios above. Decide whether mart checks
become required in gate_summary, document this scope change, and test exit codes.
The current CLI has no switch that silently enables unfinished marts.

# Supply Chain / S&OP SQL Portfolio Project

> **All data in this project is fully synthetic and fictional.**
> No real company, site, vendor, person, or product names are used.
> This project was built for portfolio and demonstration purposes only.

---

## Business Context

Sales & Operations Planning (S&OP) is the monthly cross-functional process where supply chain, commercial, and finance teams align on demand forecasts, production capacity, and inventory health.

This project models the supply chain exception management layer of S&OP for a fictional pharma/FMCG manufacturing company. The focus is on:

- **Production attainment** — are plants hitting their monthly plans?
- **Shortfall risk** — which SKUs are at risk of stocking out?
- **Excess inventory** — where is working capital locked up in slow-moving stock?
- **Supply issues** — what disruptions are impacting sales, and what is the financial cost?
- **Order fulfilment** — which sites are struggling to ship on time?

The dataset covers **12 months (Jan–Dec 2024)** across **5 manufacturing sites** and **20 products**.

---

## Schema

### Tables and Relationships

```
sites ──────────────────────────────────────────────────────────┐
 site_id PK                                                     │
 site_name, site_type [In-house|Loan-Licensee|Third-Party]      │
 region                                                         │
                                                                │
products ───────────────────────────────────────────────────────┤
 product_id PK                                                  │
 sku_code UNIQUE, sku_description                               │
 category [Tablets|Capsules|Injectables|Topicals|Liquids]       │
 unit_value (INR per unit)                                      │
                                                                │
inventory_movements ────────────────── material_id → products   │
 movement_id PK                          plant_id  → sites ─────┘
 batch_no, posting_date
 quantity  (positive = in, negative = out)
 movement_type [Receipt|Issue|Transfer|Return]
 purchase_order

production_plan ──────────────────────── site_id    → sites
 plan_id PK                              product_id → products
 plan_month (YYYY-MM)
 planned_qty, actual_qty

sales_orders ─────────────────────────── site_id    → sites
 order_id PK                             product_id → products
 order_date, qty
 status [Fulfilled|Backordered|Pending|Cancelled]

stock_build_up ───────────────────────── site_id    → sites
 id PK                                   sku_code   → products.sku_code
 reason_for_buildup
 current_doh (days of holding)
 planned_coverage_months, current_coverage_months
 get_well_month

supply_issues ────────────────────────── product_id → products
 id PK
 affected_production_month, affected_sale_month (YYYY-MM)
 challenge_description, support_required
 reason_category [RMPM|Quality|Site Backlog|Commercial|Demand Variation]
 monthly_sales_impact_inr_cr
 get_well_date, months_impacted
```

### Intentional Data Patterns

| Pattern | Products / SKUs |
|---|---|
| Chronic production under-performers (avg attainment < 85%) | SKU-003, SKU-007 |
| Escalating supply issues with rising monthly financial impact | SKU-004 (Jan→Jun), SKU-009 (Apr→Sep) |
| Rising backorder rate in H2 vs H1 | SKU-005, SKU-011 |
| Excess inventory / high days-of-holding | SKU-015 (245 DOH), SKU-018 (210 DOH) |

---

## Queries

### Q1 — Stock Cover & Stockout Risk by Site-Product
**Business question:** Which site-product combinations are at risk of a stockout?

Calculates net stock (sum of all movements) and average monthly demand (average of monthly issue quantities), then derives stock cover in days. Flags SKUs below 15 days as CRITICAL and below 30 days as LOW.

---

### Q2 — Production Attainment by Product & Month
**Business question:** Which products are chronically missing their production plan?

Uses a window function to compute each product's average attainment across 12 months alongside its monthly attainment. Products with an average below 85% are flagged as CHRONIC UNDER-PERFORMER — the two planted products (SKU-003, SKU-007) surface clearly.

---

### Q3 — Top SKUs by Current Inventory Value
**Business question:** Where is the company's working capital locked in stock?

Ranks SKUs by total INR Cr. value currently held in inventory. High-value Injectables (unit values INR 350–480) typically dominate. Used in month-end S&OP reviews to prioritise excess-inventory reduction.

---

### Q4 — Order Fill Rate by Site and Month
**Business question:** Which sites are failing to fulfil orders, and is it getting worse?

Computes the percentage of orders with status = 'Fulfilled' per site per month. Sites tied to the chronic under-performing products show a visible drop in fill rate coinciding with production shortfalls.

---

### Q5 — Backorder Trend: H1 vs H2 by Product
**Business question:** Which products show a deteriorating backorder rate in H2?

Pivots H1 (Jan–Jun) vs H2 (Jul–Dec) backorder rates per product and computes the change in percentage points. SKU-005 and SKU-011 show a jump of 40+ points — the planted pattern is clearly visible.

---

### Q6 — Excess Inventory: High DOH SKUs
**Business question:** Which SKUs are carrying far more stock than planned?

Pulls the stock_build_up tracker and calculates excess DOH (current minus planned coverage × 30). SKU-015 (245 days) and SKU-018 (210 days) are the outliers; the reason column explains the root cause for each.

---

### Q7 — Financial Impact of Supply Issues by Month and Category
**Business question:** How much revenue is at risk each month, and what is causing it?

Aggregates monthly_sales_impact_inr_cr from supply_issues by month and reason_category. The escalating months for SKU-004 and SKU-009 are visible as the highest-impact rows.

---

### Q8 — Top Supply Issues by Cumulative Financial Impact
**Business question:** Which individual disruptions have caused the most total damage?

Ranks each supply issue by total_impact = monthly_impact × months_impacted. Chronic issues with long durations outrank one-off shocks even if the monthly impact looks smaller — this reframes how teams prioritise CAPA.

---

### Q9 — Production Volume by Category and Site
**Business question:** How is production volume distributed, and who is over/under-delivering?

Aggregates planned and actual production by site and product category, showing overall attainment per combination. Highlights whether under-performance is site-wide or category-specific.

---

### Q10 — Inventory Value Trend: Monthly Net Movement by Category
**Business question:** Is total inventory investment growing or shrinking, and in which category?

Calculates net movement value (units × unit price) per category per month, with a running cumulative total using a window function. A rising cumulative in Injectables alongside backorders signals stock that is being held but not dispatched.

---

### Q11 — Month-by-Month Backorder Ramp for Worsening Products
**Business question:** For the products identified in Q5, how does the backorder count evolve each month?

Shows total orders, backorder count, backordered quantity, and backorder rate % per month for SKU-005 and SKU-011. The ramp from ~5% in H1 to 60%+ in Dec is a clean demonstration of a supply-demand mismatch trajectory.

---

### Q12 — Escalating Supply Issues: Running Impact Trend
**Business question:** What does the compounding cost of an unresolved supply issue look like?

Uses a window function (SUM OVER ORDER BY month) to build a running total of financial impact for SKU-004 and SKU-009. The curve makes the business case for early intervention obvious and is a typical S&OP escalation deck chart.

---

## How to Run

```bash
# 1. Generate the database
python generate_data.py

# 2. Run all queries interactively
sqlite3 supply_chain.db < queries.sql

# Or open in DB Browser for SQLite / DBeaver and run queries one by one
```

**Requirements:** Python 3.7+ (stdlib only — no pip installs needed), SQLite 3.

---

## Notes

- All company names, product names, site names, person names, and financial figures are **entirely fictional**.
- The data was generated with a fixed random seed (`random.seed(42)`) so results are fully reproducible.
- Monetary values are in **INR Crore (Cr.)** as is standard in Indian pharma/FMCG S&OP reporting.
- The schema mirrors common patterns in SAP MM/PP/SD environments but is simplified for analytical clarity.

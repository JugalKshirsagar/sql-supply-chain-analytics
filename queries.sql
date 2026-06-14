-- =============================================================================
-- Supply Chain / S&OP Portfolio — SQL Query Bank
-- Database : supply_chain.db (SQLite)
-- All data is synthetic, generated for portfolio/demo purposes.
-- =============================================================================


-- =============================================================================
-- Q1: STOCK COVER & STOCKOUT RISK BY SITE-PRODUCT
-- Business question: Which site-product combinations are at risk of a stockout
--   based on current net stock vs average monthly demand?
-- Insight: Highlights SKUs where cover < 30 days for proactive replenishment
--   escalation before the next S&OP cycle.
-- =============================================================================
WITH net_stock AS (
    SELECT
        plant_id    AS site_id,
        material_id AS product_id,
        SUM(quantity) AS stock_units
    FROM inventory_movements
    GROUP BY plant_id, material_id
    HAVING SUM(quantity) > 0
),
avg_monthly_issue AS (
    SELECT
        plant_id    AS site_id,
        material_id AS product_id,
        AVG(monthly_qty) AS avg_monthly_demand
    FROM (
        SELECT plant_id, material_id,
               strftime('%Y-%m', posting_date) AS mo,
               SUM(ABS(quantity))              AS monthly_qty
        FROM inventory_movements
        WHERE movement_type = 'Issue'
        GROUP BY plant_id, material_id, mo
    )
    GROUP BY plant_id, material_id
)
SELECT
    s.site_name,
    p.sku_code,
    p.sku_description,
    p.category,
    ROUND(ns.stock_units, 0)                                        AS net_stock_units,
    ROUND(ami.avg_monthly_demand, 0)                                AS avg_monthly_demand,
    ROUND(ns.stock_units / (ami.avg_monthly_demand / 30.0), 1)     AS stock_cover_days,
    CASE
        WHEN ns.stock_units / (ami.avg_monthly_demand / 30.0) < 15 THEN 'CRITICAL'
        WHEN ns.stock_units / (ami.avg_monthly_demand / 30.0) < 30 THEN 'LOW'
        ELSE 'ADEQUATE'
    END AS risk_flag
FROM net_stock ns
JOIN avg_monthly_issue ami
    ON ns.site_id = ami.site_id AND ns.product_id = ami.product_id
JOIN sites   s ON ns.site_id   = s.site_id
JOIN products p ON ns.product_id = p.product_id
ORDER BY stock_cover_days ASC
LIMIT 15;


-- =============================================================================
-- Q2: PRODUCTION ATTAINMENT BY PRODUCT & MONTH — CHRONIC UNDER-PERFORMERS
-- Business question: Which products consistently miss their production plan,
--   and which months are worst?
-- Insight: Products with avg attainment < 85% across 12 months are flagged
--   as chronic under-performers requiring a site-level corrective action plan.
-- =============================================================================
SELECT
    p.sku_code,
    p.sku_description,
    pp.plan_month,
    pp.planned_qty,
    pp.actual_qty,
    ROUND(pp.actual_qty * 100.0 / pp.planned_qty, 1)               AS monthly_attainment_pct,
    ROUND(AVG(pp.actual_qty * 100.0 / pp.planned_qty)
          OVER (PARTITION BY pp.product_id), 1)                     AS avg_attainment_pct,
    CASE
        WHEN AVG(pp.actual_qty * 100.0 / pp.planned_qty)
             OVER (PARTITION BY pp.product_id) < 85 THEN 'CHRONIC UNDER-PERFORMER'
        ELSE 'NORMAL'
    END AS performance_flag
FROM production_plan pp
JOIN products p ON pp.product_id = p.product_id
ORDER BY avg_attainment_pct ASC, pp.plan_month;


-- =============================================================================
-- Q3: TOP SKUs BY CURRENT INVENTORY VALUE
-- Business question: Where is the company's working capital locked up in stock?
-- Insight: Ranks SKUs by total INR value in the warehouse, useful for
--   prioritising slow-mover reviews and excess-inventory write-off decisions.
-- =============================================================================
WITH net_stock AS (
    SELECT
        material_id AS product_id,
        SUM(quantity) AS stock_units
    FROM inventory_movements
    GROUP BY material_id
)
SELECT
    p.sku_code,
    p.sku_description,
    p.category,
    ROUND(ns.stock_units, 0)                             AS net_stock_units,
    p.unit_value                                          AS unit_value_inr,
    ROUND(ns.stock_units * p.unit_value / 1e7, 2)        AS inventory_value_inr_cr
FROM net_stock ns
JOIN products p ON ns.product_id = p.product_id
WHERE ns.stock_units > 0
ORDER BY inventory_value_inr_cr DESC
LIMIT 10;


-- =============================================================================
-- Q4: ORDER FILL RATE BY SITE AND MONTH
-- Business question: Which manufacturing sites are consistently failing to
--   fulfil customer orders on time, and is performance deteriorating?
-- Insight: Sites with fill rate < 80% in consecutive months signal a structural
--   supply constraint rather than a one-off event.
-- =============================================================================
SELECT
    s.site_name,
    strftime('%Y-%m', so.order_date)                                    AS month,
    COUNT(*)                                                            AS total_orders,
    SUM(CASE WHEN so.status = 'Fulfilled'   THEN 1 ELSE 0 END)         AS fulfilled,
    SUM(CASE WHEN so.status = 'Backordered' THEN 1 ELSE 0 END)         AS backordered,
    SUM(CASE WHEN so.status = 'Cancelled'   THEN 1 ELSE 0 END)         AS cancelled,
    ROUND(
        SUM(CASE WHEN so.status = 'Fulfilled' THEN 1.0 ELSE 0 END)
        / COUNT(*) * 100, 1
    )                                                                   AS fill_rate_pct
FROM sales_orders so
JOIN sites s ON so.site_id = s.site_id
GROUP BY s.site_name, month
ORDER BY s.site_name, month;


-- =============================================================================
-- Q5: BACKORDER TREND — H1 vs H2 COMPARISON BY PRODUCT
-- Business question: Which products show a deteriorating backorder rate in the
--   second half of the year versus the first half?
-- Insight: A jump of > 10 percentage points in backorder rate signals a
--   structural demand-supply mismatch that needs an S&OP intervention.
-- =============================================================================
WITH half_year AS (
    SELECT
        product_id,
        CASE WHEN strftime('%m', order_date) <= '06' THEN 'H1' ELSE 'H2' END AS half,
        COUNT(*) AS total_orders,
        SUM(CASE WHEN status = 'Backordered' THEN 1 ELSE 0 END)              AS backorders
    FROM sales_orders
    GROUP BY product_id, half
),
pivoted AS (
    SELECT
        product_id,
        MAX(CASE WHEN half = 'H1' THEN ROUND(backorders * 100.0 / total_orders, 1) END) AS h1_bo_pct,
        MAX(CASE WHEN half = 'H2' THEN ROUND(backorders * 100.0 / total_orders, 1) END) AS h2_bo_pct
    FROM half_year
    GROUP BY product_id
)
SELECT
    p.sku_code,
    p.sku_description,
    COALESCE(pv.h1_bo_pct, 0)                                         AS h1_backorder_pct,
    COALESCE(pv.h2_bo_pct, 0)                                         AS h2_backorder_pct,
    ROUND(COALESCE(pv.h2_bo_pct,0) - COALESCE(pv.h1_bo_pct,0), 1)   AS change_pct_pts,
    CASE
        WHEN COALESCE(pv.h2_bo_pct,0) - COALESCE(pv.h1_bo_pct,0) > 10  THEN 'WORSENING'
        WHEN COALESCE(pv.h2_bo_pct,0) - COALESCE(pv.h1_bo_pct,0) < -5  THEN 'IMPROVING'
        ELSE 'STABLE'
    END AS trend
FROM pivoted pv
JOIN products p ON pv.product_id = p.product_id
ORDER BY change_pct_pts DESC;


-- =============================================================================
-- Q6: EXCESS INVENTORY — HIGH DOH SKUs FROM STOCK BUILD-UP TRACKER
-- Business question: Which SKUs are carrying significantly more stock than
--   planned coverage, and what is the root cause?
-- Insight: The excess DOH days quantify how far each SKU is from its target;
--   get_well_month shows when the situation is expected to normalise.
-- =============================================================================
SELECT
    sb.sku_code,
    p.sku_description,
    p.category,
    s.site_name,
    sb.reason_for_buildup,
    sb.current_doh                                                  AS current_doh_days,
    ROUND(sb.planned_coverage_months * 30, 0)                      AS planned_doh_days,
    ROUND(sb.current_doh - sb.planned_coverage_months * 30, 0)    AS excess_doh_days,
    sb.current_coverage_months,
    sb.planned_coverage_months,
    sb.get_well_month
FROM stock_build_up sb
JOIN products p ON sb.sku_code    = p.sku_code
JOIN sites    s ON sb.site_id     = s.site_id
ORDER BY sb.current_doh DESC;


-- =============================================================================
-- Q7: FINANCIAL IMPACT OF SUPPLY ISSUES BY MONTH AND REASON CATEGORY
-- Business question: How much revenue is at risk each month from supply
--   disruptions, and which root-cause category is driving the most loss?
-- Insight: Monthly totals show whether the total impact is growing (escalation)
--   or reducing (recovery); category breakdown guides where to focus CAPA.
-- =============================================================================
SELECT
    affected_sale_month                              AS month,
    reason_category,
    COUNT(*)                                         AS issue_count,
    ROUND(SUM(monthly_sales_impact_inr_cr), 2)       AS total_impact_inr_cr
FROM supply_issues
GROUP BY affected_sale_month, reason_category
ORDER BY affected_sale_month, total_impact_inr_cr DESC;


-- =============================================================================
-- Q8: TOP SUPPLY ISSUES BY CUMULATIVE FINANCIAL IMPACT
-- Business question: Which individual supply issues have caused the most total
--   revenue damage when extended over the months they were active?
-- Insight: total_impact = monthly_impact × months_impacted; used to prioritise
--   escalations and estimate business case for corrective investments.
-- =============================================================================
SELECT
    si.id                                                          AS issue_id,
    p.sku_code,
    p.sku_description,
    si.affected_sale_month,
    si.reason_category,
    si.challenge_description,
    si.monthly_sales_impact_inr_cr,
    si.months_impacted,
    ROUND(si.monthly_sales_impact_inr_cr * si.months_impacted, 2) AS total_impact_inr_cr,
    si.get_well_date
FROM supply_issues si
JOIN products p ON si.product_id = p.product_id
ORDER BY total_impact_inr_cr DESC
LIMIT 10;


-- =============================================================================
-- Q9: PRODUCTION VOLUME BY CATEGORY AND SITE
-- Business question: How is manufacturing volume (planned vs actual) distributed
--   across product categories and sites?
-- Insight: Reveals which site-category combinations are consistently
--   over- or under-delivering, informing capacity rebalancing decisions.
-- =============================================================================
SELECT
    s.site_name,
    s.site_type,
    p.category,
    ROUND(SUM(pp.planned_qty), 0)                                  AS total_planned_units,
    ROUND(SUM(pp.actual_qty), 0)                                   AS total_actual_units,
    ROUND(SUM(pp.actual_qty) * 100.0 / SUM(pp.planned_qty), 1)    AS overall_attainment_pct
FROM production_plan pp
JOIN sites    s ON pp.site_id   = s.site_id
JOIN products p ON pp.product_id = p.product_id
GROUP BY s.site_name, s.site_type, p.category
ORDER BY s.site_name, p.category;


-- =============================================================================
-- Q10: INVENTORY VALUE TREND — MONTHLY NET MOVEMENT BY CATEGORY
-- Business question: Is the company's total inventory investment growing or
--   shrinking month by month, and which category is driving the change?
-- Insight: A rising cumulative value in Injectables alongside backorder
--   escalation signals stock is being held but not dispatched — a service risk.
-- =============================================================================
WITH monthly_net AS (
    SELECT
        strftime('%Y-%m', posting_date) AS month,
        material_id,
        SUM(quantity)                   AS net_movement_units
    FROM inventory_movements
    GROUP BY month, material_id
)
SELECT
    mn.month,
    p.category,
    ROUND(SUM(mn.net_movement_units * p.unit_value) / 1e7, 2)     AS net_movement_value_inr_cr,
    ROUND(
        SUM(SUM(mn.net_movement_units * p.unit_value))
        OVER (PARTITION BY p.category ORDER BY mn.month) / 1e7, 2
    )                                                              AS cumulative_value_inr_cr
FROM monthly_net mn
JOIN products p ON mn.material_id = p.product_id
GROUP BY mn.month, p.category
ORDER BY mn.month, p.category;


-- =============================================================================
-- Q11: MONTH-BY-MONTH BACKORDER COUNT FOR WORSENING PRODUCTS
-- Business question: For the products flagged as "WORSENING" in Q5, how does
--   the backorder count and quantity evolve month by month through the year?
-- Insight: Shows the ramp-up pattern clearly — useful for presenting the
--   supply risk trajectory to commercial and supply planning teams.
-- =============================================================================
SELECT
    strftime('%Y-%m', so.order_date)                               AS month,
    p.sku_code,
    p.sku_description,
    COUNT(*)                                                       AS total_orders,
    SUM(CASE WHEN so.status = 'Backordered' THEN 1 ELSE 0 END)    AS backorder_count,
    ROUND(
        SUM(CASE WHEN so.status = 'Backordered' THEN so.qty ELSE 0 END), 0
    )                                                              AS backordered_qty,
    ROUND(
        SUM(CASE WHEN so.status = 'Backordered' THEN 1.0 ELSE 0 END)
        / COUNT(*) * 100, 1
    )                                                              AS backorder_rate_pct
FROM sales_orders so
JOIN products p ON so.product_id = p.product_id
WHERE so.product_id IN (5, 11)
GROUP BY month, p.sku_code
ORDER BY p.sku_code, month;


-- =============================================================================
-- Q12: ESCALATING SUPPLY ISSUES — RUNNING IMPACT TREND (Products 4 & 9)
-- Business question: For products with a known escalating supply problem, what
--   does the cumulative financial damage look like as each month passes?
-- Insight: The running total makes the compounding cost of inaction visible —
--   a powerful input for escalation decks and get-well date accountability.
-- =============================================================================
SELECT
    p.sku_code,
    p.sku_description,
    si.affected_sale_month,
    si.reason_category,
    si.challenge_description,
    si.monthly_sales_impact_inr_cr,
    ROUND(
        SUM(si.monthly_sales_impact_inr_cr)
        OVER (PARTITION BY si.product_id ORDER BY si.affected_sale_month), 2
    )                                                              AS running_total_inr_cr
FROM supply_issues si
JOIN products p ON si.product_id = p.product_id
WHERE si.product_id IN (4, 9)
ORDER BY si.product_id, si.affected_sale_month;

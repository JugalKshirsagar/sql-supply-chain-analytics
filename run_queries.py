"""Runs all 12 portfolio queries and prints formatted output."""
import sqlite3, textwrap

conn = sqlite3.connect("supply_chain.db")
conn.row_factory = sqlite3.Row

QUERIES = [
    ("Q1  — Stock Cover & Stockout Risk (top 10 lowest cover)",
     """
     WITH net_stock AS (
         SELECT plant_id AS site_id, material_id AS product_id, SUM(quantity) AS stock_units
         FROM inventory_movements GROUP BY plant_id, material_id HAVING SUM(quantity) > 0
     ),
     avg_monthly_issue AS (
         SELECT plant_id AS site_id, material_id AS product_id, AVG(monthly_qty) AS avg_monthly_demand
         FROM (SELECT plant_id, material_id, strftime('%Y-%m', posting_date) AS mo,
                      SUM(ABS(quantity)) AS monthly_qty
               FROM inventory_movements WHERE movement_type = 'Issue'
               GROUP BY plant_id, material_id, mo)
         GROUP BY plant_id, material_id
     )
     SELECT s.site_name, p.sku_code,
            ROUND(ns.stock_units,0)                                      AS net_stock_units,
            ROUND(ami.avg_monthly_demand,0)                              AS avg_monthly_demand,
            ROUND(ns.stock_units/(ami.avg_monthly_demand/30.0),1)       AS stock_cover_days,
            CASE WHEN ns.stock_units/(ami.avg_monthly_demand/30.0)<15 THEN 'CRITICAL'
                 WHEN ns.stock_units/(ami.avg_monthly_demand/30.0)<30 THEN 'LOW'
                 ELSE 'ADEQUATE' END                                     AS risk_flag
     FROM net_stock ns
     JOIN avg_monthly_issue ami ON ns.site_id=ami.site_id AND ns.product_id=ami.product_id
     JOIN sites    s ON ns.site_id   =s.site_id
     JOIN products p ON ns.product_id=p.product_id
     ORDER BY stock_cover_days ASC LIMIT 10
     """),

    ("Q2  — Production Attainment: Chronic Under-Performers (all products ranked)",
     """
     SELECT p.sku_code, p.sku_description,
            ROUND(AVG(pp.actual_qty*100.0/pp.planned_qty),1) AS avg_attainment_pct,
            CASE WHEN AVG(pp.actual_qty*100.0/pp.planned_qty)<85
                 THEN 'CHRONIC UNDER-PERFORMER' ELSE 'NORMAL' END AS performance_flag
     FROM production_plan pp JOIN products p ON pp.product_id=p.product_id
     GROUP BY pp.product_id ORDER BY avg_attainment_pct ASC LIMIT 8
     """),

    ("Q3  — Top SKUs by Current Inventory Value (INR Cr.)",
     """
     WITH net_stock AS (
         SELECT material_id AS product_id, SUM(quantity) AS stock_units
         FROM inventory_movements GROUP BY material_id
     )
     SELECT p.sku_code, p.sku_description, p.category,
            ROUND(ns.stock_units,0)                       AS net_stock_units,
            p.unit_value                                  AS unit_value_inr,
            ROUND(ns.stock_units*p.unit_value/1e7,2)      AS inventory_value_inr_cr
     FROM net_stock ns JOIN products p ON ns.product_id=p.product_id
     WHERE ns.stock_units > 0
     ORDER BY inventory_value_inr_cr DESC LIMIT 8
     """),

    ("Q4  — Order Fill Rate by Site (Sep–Dec 2024)",
     """
     SELECT s.site_name, strftime('%Y-%m',so.order_date) AS month,
            COUNT(*) AS total_orders,
            SUM(CASE WHEN so.status='Fulfilled'   THEN 1 ELSE 0 END) AS fulfilled,
            SUM(CASE WHEN so.status='Backordered' THEN 1 ELSE 0 END) AS backordered,
            ROUND(SUM(CASE WHEN so.status='Fulfilled' THEN 1.0 ELSE 0 END)/COUNT(*)*100,1) AS fill_rate_pct
     FROM sales_orders so JOIN sites s ON so.site_id=s.site_id
     WHERE strftime('%Y-%m',so.order_date) >= '2024-09'
     GROUP BY s.site_name, month ORDER BY s.site_name, month
     """),

    ("Q5  — Backorder Trend: H1 vs H2 (products ranked by worsening)",
     """
     WITH hy AS (
         SELECT product_id,
                CASE WHEN strftime('%m',order_date)<='06' THEN 'H1' ELSE 'H2' END AS half,
                COUNT(*) AS tot,
                SUM(CASE WHEN status='Backordered' THEN 1 ELSE 0 END) AS bo
         FROM sales_orders GROUP BY product_id, half
     ),
     pv AS (
         SELECT product_id,
                MAX(CASE WHEN half='H1' THEN ROUND(bo*100.0/tot,1) END) AS h1,
                MAX(CASE WHEN half='H2' THEN ROUND(bo*100.0/tot,1) END) AS h2
         FROM hy GROUP BY product_id
     )
     SELECT p.sku_code, p.sku_description,
            COALESCE(pv.h1,0) AS h1_bo_pct, COALESCE(pv.h2,0) AS h2_bo_pct,
            ROUND(COALESCE(pv.h2,0)-COALESCE(pv.h1,0),1) AS change_pct_pts,
            CASE WHEN COALESCE(pv.h2,0)-COALESCE(pv.h1,0)>10  THEN 'WORSENING'
                 WHEN COALESCE(pv.h2,0)-COALESCE(pv.h1,0)<-5  THEN 'IMPROVING'
                 ELSE 'STABLE' END AS trend
     FROM pv JOIN products p ON pv.product_id=p.product_id
     ORDER BY change_pct_pts DESC LIMIT 8
     """),

    ("Q6  — Excess Inventory: High DOH SKUs",
     """
     SELECT sb.sku_code, p.sku_description, s.site_name,
            sb.current_doh AS current_doh_days,
            ROUND(sb.planned_coverage_months*30,0)                AS planned_doh_days,
            ROUND(sb.current_doh-sb.planned_coverage_months*30,0) AS excess_doh_days,
            sb.current_coverage_months, sb.planned_coverage_months, sb.get_well_month
     FROM stock_build_up sb
     JOIN products p ON sb.sku_code=p.sku_code
     JOIN sites    s ON sb.site_id =s.site_id
     ORDER BY sb.current_doh DESC
     """),

    ("Q7  — Financial Impact of Supply Issues by Month & Category",
     """
     SELECT affected_sale_month AS month, reason_category,
            COUNT(*) AS issue_count,
            ROUND(SUM(monthly_sales_impact_inr_cr),2) AS total_impact_inr_cr
     FROM supply_issues
     GROUP BY affected_sale_month, reason_category
     ORDER BY affected_sale_month, total_impact_inr_cr DESC
     """),

    ("Q8  — Top Supply Issues by Cumulative Financial Impact",
     """
     SELECT p.sku_code, si.affected_sale_month, si.reason_category,
            si.monthly_sales_impact_inr_cr AS monthly_impact_cr,
            si.months_impacted,
            ROUND(si.monthly_sales_impact_inr_cr*si.months_impacted,2) AS total_impact_inr_cr,
            si.get_well_date
     FROM supply_issues si JOIN products p ON si.product_id=p.product_id
     ORDER BY total_impact_inr_cr DESC LIMIT 8
     """),

    ("Q9  — Production Volume by Category & Site",
     """
     SELECT s.site_name, s.site_type, p.category,
            ROUND(SUM(pp.planned_qty),0) AS total_planned,
            ROUND(SUM(pp.actual_qty),0)  AS total_actual,
            ROUND(SUM(pp.actual_qty)*100.0/SUM(pp.planned_qty),1) AS overall_attainment_pct
     FROM production_plan pp
     JOIN sites    s ON pp.site_id   =s.site_id
     JOIN products p ON pp.product_id=p.product_id
     GROUP BY s.site_name, s.site_type, p.category ORDER BY s.site_name, p.category
     """),

    ("Q10 — Inventory Value Trend by Category (first 20 rows)",
     """
     WITH mn AS (
         SELECT strftime('%Y-%m',posting_date) AS month, material_id,
                SUM(quantity) AS net_units
         FROM inventory_movements GROUP BY month, material_id
     )
     SELECT mn.month, p.category,
            ROUND(SUM(mn.net_units*p.unit_value)/1e7,2) AS net_movement_inr_cr,
            ROUND(SUM(SUM(mn.net_units*p.unit_value))
                  OVER (PARTITION BY p.category ORDER BY mn.month)/1e7,2) AS cumulative_inr_cr
     FROM mn JOIN products p ON mn.material_id=p.product_id
     GROUP BY mn.month, p.category
     ORDER BY mn.month, p.category LIMIT 20
     """),

    ("Q11 — Monthly Backorder Ramp for SKU-005 & SKU-011",
     """
     SELECT strftime('%Y-%m',so.order_date) AS month, p.sku_code,
            COUNT(*) AS total_orders,
            SUM(CASE WHEN so.status='Backordered' THEN 1 ELSE 0 END) AS backorder_count,
            ROUND(SUM(CASE WHEN so.status='Backordered' THEN 1.0 ELSE 0 END)/COUNT(*)*100,1) AS backorder_rate_pct
     FROM sales_orders so JOIN products p ON so.product_id=p.product_id
     WHERE so.product_id IN (5,11)
     GROUP BY month, p.sku_code ORDER BY p.sku_code, month
     """),

    ("Q12 — Running Supply Issue Impact for SKU-004 & SKU-009",
     """
     SELECT p.sku_code, si.affected_sale_month, si.reason_category,
            si.monthly_sales_impact_inr_cr,
            ROUND(SUM(si.monthly_sales_impact_inr_cr)
                  OVER (PARTITION BY si.product_id ORDER BY si.affected_sale_month),2) AS running_total_inr_cr
     FROM supply_issues si JOIN products p ON si.product_id=p.product_id
     WHERE si.product_id IN (4,9)
     ORDER BY si.product_id, si.affected_sale_month
     """),
]


def print_table(rows):
    if not rows:
        print("  (no rows)")
        return
    keys = rows[0].keys()
    widths = {k: max(len(k), max(len(str(r[k])) for r in rows)) for k in keys}
    header = "  " + "  ".join(k.ljust(widths[k]) for k in keys)
    sep    = "  " + "  ".join("-" * widths[k] for k in keys)
    print(header); print(sep)
    for row in rows:
        print("  " + "  ".join(str(row[k]).ljust(widths[k]) for k in keys))


for title, sql in QUERIES:
    print(f"\n{'='*74}")
    print(f"  {title}")
    print(f"{'='*74}")
    rows = conn.execute(textwrap.dedent(sql)).fetchall()
    print_table(rows)

conn.close()
print("\n\nAll queries executed successfully.")

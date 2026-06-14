"""
Supply Chain / S&OP Portfolio Project — SQLite Data Generator
All data is fully synthetic; generated for portfolio/demo purposes only.
"""

import sqlite3
import random
import os
import calendar
from datetime import date

random.seed(42)

DB_PATH = "supply_chain.db"
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# ── SCHEMA ───────────────────────────────────────────────────────────────────
cur.executescript("""
CREATE TABLE sites (
    site_id   INTEGER PRIMARY KEY,
    site_name TEXT NOT NULL,
    site_type TEXT NOT NULL CHECK(site_type IN ('In-house','Loan-Licensee','Third-Party')),
    region    TEXT NOT NULL
);

CREATE TABLE products (
    product_id      INTEGER PRIMARY KEY,
    sku_code        TEXT NOT NULL UNIQUE,
    sku_description TEXT NOT NULL,
    category        TEXT NOT NULL,
    unit_value      REAL NOT NULL
);

CREATE TABLE inventory_movements (
    movement_id    INTEGER PRIMARY KEY,
    material_id    INTEGER NOT NULL REFERENCES products(product_id),
    batch_no       TEXT NOT NULL,
    posting_date   TEXT NOT NULL,
    quantity       REAL NOT NULL,          -- positive = stock in, negative = stock out
    movement_type  TEXT NOT NULL CHECK(movement_type IN ('Receipt','Issue','Transfer','Return')),
    plant_id       INTEGER NOT NULL REFERENCES sites(site_id),
    purchase_order TEXT
);

CREATE TABLE production_plan (
    plan_id     INTEGER PRIMARY KEY,
    site_id     INTEGER NOT NULL REFERENCES sites(site_id),
    product_id  INTEGER NOT NULL REFERENCES products(product_id),
    plan_month  TEXT NOT NULL,
    planned_qty REAL NOT NULL,
    actual_qty  REAL NOT NULL
);

CREATE TABLE sales_orders (
    order_id   INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(product_id),
    site_id    INTEGER NOT NULL REFERENCES sites(site_id),
    order_date TEXT NOT NULL,
    qty        REAL NOT NULL,
    status     TEXT NOT NULL CHECK(status IN ('Fulfilled','Backordered','Pending','Cancelled'))
);

CREATE TABLE stock_build_up (
    id                      INTEGER PRIMARY KEY,
    sku_code                TEXT NOT NULL,
    site_id                 INTEGER NOT NULL REFERENCES sites(site_id),
    reason_for_buildup      TEXT NOT NULL,
    current_doh             REAL NOT NULL,
    planned_coverage_months REAL NOT NULL,
    current_coverage_months REAL NOT NULL,
    get_well_month          TEXT NOT NULL
);

CREATE TABLE supply_issues (
    id                          INTEGER PRIMARY KEY,
    product_id                  INTEGER NOT NULL REFERENCES products(product_id),
    affected_production_month   TEXT NOT NULL,
    affected_sale_month         TEXT NOT NULL,
    challenge_description       TEXT NOT NULL,
    support_required            TEXT NOT NULL,
    reason_category             TEXT NOT NULL CHECK(reason_category IN
                                    ('RMPM','Quality','Site Backlog','Commercial','Demand Variation')),
    monthly_sales_impact_inr_cr REAL NOT NULL,
    get_well_date               TEXT NOT NULL,
    months_impacted             INTEGER NOT NULL
);
""")

# ── MASTER DATA ──────────────────────────────────────────────────────────────
SITES = [
    (1, "Site Alpha",    "In-house",      "North"),
    (2, "Site Beta",     "In-house",      "West"),
    (3, "Plant Gamma",   "In-house",      "South"),
    (4, "Plant Delta",   "Loan-Licensee", "East"),
    (5, "Vendor Unit 1", "Third-Party",   "West"),
]
cur.executemany("INSERT INTO sites VALUES (?,?,?,?)", SITES)

# Intentional flags noted inline:
#   product_id 3, 7  → chronic production under-performers
#   product_id 4, 9  → escalating supply issues (rising monthly impact)
#   product_id 5, 11 → rising backorders in H2 (Jul-Dec)
#   SKU-015, SKU-018 → high days-of-holding in stock_build_up
PRODUCTS = [
    (1,  "SKU-001", "Amoxillin Tab 500mg",      "Tablets",      45.0),
    (2,  "SKU-002", "Ciprozan Tab 250mg",        "Tablets",      62.0),
    (3,  "SKU-003", "Metrozole Tab 400mg",       "Tablets",      38.0),
    (4,  "SKU-004", "Pantazone Tab 40mg",        "Tablets",      55.0),
    (5,  "SKU-005", "Atorvex Tab 10mg",          "Tablets",      80.0),
    (6,  "SKU-006", "Doxycine Cap 100mg",        "Capsules",     72.0),
    (7,  "SKU-007", "Omeprazex Cap 20mg",        "Capsules",     90.0),
    (8,  "SKU-008", "Azithrozin Cap 250mg",      "Capsules",    110.0),
    (9,  "SKU-009", "Cefspan Inj 1g",            "Injectables", 350.0),
    (10, "SKU-010", "Merozan Inj 500mg",         "Injectables", 420.0),
    (11, "SKU-011", "Vancozan Inj 500mg",        "Injectables", 480.0),
    (12, "SKU-012", "Piperacin Inj 4g",          "Injectables", 390.0),
    (13, "SKU-013", "Betadex Cream 30g",         "Topicals",     95.0),
    (14, "SKU-014", "Clotrix Cream 15g",         "Topicals",     85.0),
    (15, "SKU-015", "Syrupex Liquid 200ml",      "Liquids",      48.0),
    (16, "SKU-016", "Cofliq Liquid 100ml",       "Liquids",      35.0),
    (17, "SKU-017", "Glucovex Tab 500mg",        "Tablets",      42.0),
    (18, "SKU-018", "Levozex Tab 500mg",         "Tablets",      68.0),
    (19, "SKU-019", "Ranitex Cap 150mg",         "Capsules",     55.0),
    (20, "SKU-020", "Paracetam Tab 500mg",       "Tablets",      30.0),
]
cur.executemany("INSERT INTO products VALUES (?,?,?,?,?)", PRODUCTS)

UNIT_VALUE = {pid: uv for pid, _, __, ___, uv in PRODUCTS}

# Which site manufactures which products (multi-source for 3, 5, 6, 16)
SITE_PRODS = {
    1: [1, 2, 3, 4, 5, 6],
    2: [7, 8, 9, 10, 11, 12],
    3: [13, 14, 15, 16],
    4: [3, 5, 17, 18],
    5: [19, 20, 6, 16],
}
# Primary (first) site per product — used for sales orders
PRIMARY_SITE = {}
for sid, pids in SITE_PRODS.items():
    for pid in pids:
        if pid not in PRIMARY_SITE:
            PRIMARY_SITE[pid] = sid

CHRONIC      = {3, 7}    # chronic under-performers: avg attainment 68-83%
BACKORDER_H2 = {5, 11}  # backorder rate ramps up Jul-Dec

MONTHS = [f"2024-{m:02d}" for m in range(1, 13)]


def rdate(year, month):
    last = calendar.monthrange(year, month)[1]
    return date(year, month, random.randint(1, last)).isoformat()


# ── PRODUCTION PLAN ───────────────────────────────────────────────────────────
plan_rows = []
plan_id = 1
for sid, pids in SITE_PRODS.items():
    for pid in pids:
        for mo in MONTHS:
            yr, mn = map(int, mo.split("-"))
            planned = round(random.uniform(6000, 20000))
            if pid in CHRONIC:
                actual = round(planned * random.uniform(0.68, 0.83))
            else:
                actual = round(planned * random.uniform(0.88, 1.05))
            plan_rows.append((plan_id, sid, pid, mo, planned, actual))
            plan_id += 1

cur.executemany("INSERT INTO production_plan VALUES (?,?,?,?,?,?)", plan_rows)


# ── INVENTORY MOVEMENTS ──────────────────────────────────────────────────────
# Generated from each production plan row: Receipt → Issue → optional Transfer/Return.
# Issues are stored as negative quantities so SUM(quantity) per plant+product = net stock.
movements = []
mov_id    = 1
batch_ctr = 10000

for _, sid, pid, mo, _, actual_qty in plan_rows:
    yr, mn = map(int, mo.split("-"))
    pdate  = rdate(yr, mn)

    # Receipt (GR from production)
    po = f"PO-{sid:02d}{pid:03d}{mn:02d}-{random.randint(1000,9999)}"
    movements.append((mov_id, pid, f"BT{batch_ctr}", pdate,  actual_qty, "Receipt",  sid, po))
    mov_id += 1; batch_ctr += 1

    # Issue (dispatch to market) — 88-98% of received qty
    iss = round(actual_qty * random.uniform(0.88, 0.98))
    movements.append((mov_id, pid, f"BT{batch_ctr}", pdate, -iss, "Issue", sid, None))
    mov_id += 1; batch_ctr += 1

    # Inter-plant Transfer (25% probability)
    if random.random() < 0.25:
        tqty = round(actual_qty * random.uniform(0.04, 0.12))
        dest = random.choice([s for s in SITE_PRODS if s != sid])
        movements.append((mov_id, pid, f"BT{batch_ctr}", pdate, tqty, "Transfer", dest, None))
        mov_id += 1; batch_ctr += 1

    # Return (15% probability)
    if random.random() < 0.15:
        rqty = round(actual_qty * random.uniform(0.01, 0.04))
        movements.append((mov_id, pid, f"BT{batch_ctr}", pdate, rqty, "Return", sid, None))
        mov_id += 1; batch_ctr += 1

cur.executemany("INSERT INTO inventory_movements VALUES (?,?,?,?,?,?,?,?)", movements)


# ── SALES ORDERS ──────────────────────────────────────────────────────────────
# Products 5 and 11: backorder probability ramps from 40% (Jul) to 65% (Dec).
# All other products: ~5-7% backorder rate throughout the year.
orders = []
oid = 1
for pid, *_ in PRODUCTS:
    sid = PRIMARY_SITE[pid]
    for mo in MONTHS:
        yr, mn = map(int, mo.split("-"))
        for _ in range(random.randint(3, 6)):
            odate = rdate(yr, mn)
            qty   = round(random.uniform(200, 2000))

            if pid in BACKORDER_H2 and mn >= 7:
                bo_prob = 0.40 + (mn - 7) * 0.05   # 40% Jul → 65% Dec
                r = random.random()
                if r < bo_prob:
                    status = "Backordered"
                elif r < bo_prob + 0.15:
                    status = "Pending"
                elif r < bo_prob + 0.18:
                    status = "Cancelled"
                else:
                    status = "Fulfilled"
            else:
                r = random.random()
                if r < 0.78:
                    status = "Fulfilled"
                elif r < 0.88:
                    status = "Pending"
                elif r < 0.93:
                    status = "Backordered"
                else:
                    status = "Cancelled"

            orders.append((oid, pid, sid, odate, qty, status))
            oid += 1

cur.executemany("INSERT INTO sales_orders VALUES (?,?,?,?,?,?)", orders)


# ── STOCK BUILD-UP ────────────────────────────────────────────────────────────
# SKU-015 (DOH 245) and SKU-018 (DOH 210) are the high-excess outliers.
buildup = [
    (1, "SKU-015", 3, "Demand forecast miss — market uptake significantly lower than plan",       245.0, 2.0, 8.2, "2024-09"),
    (2, "SKU-018", 4, "Export deal cancelled post-manufacture — stock redirected to domestic",    210.0, 1.5, 7.0, "2024-10"),
    (3, "SKU-016", 3, "Planned institutional order cancelled; excess FG held at plant",           130.0, 1.5, 4.3, "2024-09"),
    (4, "SKU-006", 1, "Safety stock over-build post prior-quarter supply disruption",              95.0, 2.0, 3.2, "2024-07"),
    (5, "SKU-020", 5, "Seasonal demand lower than Q1 forecast; correction in progress",            88.0, 2.0, 2.9, "2024-07"),
    (6, "SKU-002", 1, "New channel launch delayed — pre-built inventory now idle",                110.0, 1.5, 3.7, "2024-08"),
    (7, "SKU-010", 2, "API vendor over-delivered; excess WIP converted to finished goods",         78.0, 2.0, 2.6, "2024-08"),
    (8, "SKU-017", 4, "Market access approval delayed in target region",                           72.0, 2.0, 2.4, "2024-07"),
]
cur.executemany("INSERT INTO stock_build_up VALUES (?,?,?,?,?,?,?,?)", buildup)


# ── SUPPLY ISSUES ─────────────────────────────────────────────────────────────
# Product 4 (Pantazone): escalating impact Jan→Jun (RMPM → Quality → Site Backlog cascade)
# Product 9 (Cefspan):   escalating impact Apr→Sep (CMO + Quality cascade)
issues = [
    (1,  4,"2024-01","2024-01","API sourcing delay from single qualified vendor",         "Alternate vendor qualification",          "RMPM",             0.12,"2024-04-30",4),
    (2,  4,"2024-02","2024-02","API batch rejected at incoming QC",                       "Expedite re-test with vendor support",    "Quality",          0.18,"2024-04-30",3),
    (3,  4,"2024-03","2024-03","Continued API shortage — vendor at full capacity",        "Import API; airfreight approval",         "RMPM",             0.25,"2024-05-31",3),
    (4,  4,"2024-04","2024-04","Production schedule slipped 3 weeks due to input gap",   "Weekend batches; overtime approval",      "Site Backlog",     0.34,"2024-06-30",2),
    (5,  4,"2024-05","2024-05","Batch failure during process validation",                 "QA review; concession batch approval",    "Quality",          0.41,"2024-07-31",2),
    (6,  4,"2024-06","2024-06","Accumulated backlog from prior 5 months uncleared",      "Priority scheduling block",               "Site Backlog",     0.52,"2024-08-31",2),
    (7,  9,"2024-04","2024-04","CMO capacity constrained — shared filling line",          "Request dedicated line from CMO",         "Site Backlog",     0.20,"2024-07-31",3),
    (8,  9,"2024-05","2024-05","Raw material under regulatory hold at customs",           "EXIM cell customs clearance support",     "RMPM",             0.31,"2024-08-31",4),
    (9,  9,"2024-06","2024-06","Yield loss on fermentation step — 2 batches failed",     "Process review; batch correction plan",   "Quality",          0.38,"2024-09-30",3),
    (10, 9,"2024-07","2024-07","CMO maintenance shutdown reduced July schedule",          "Reschedule + alternate site evaluation",  "Site Backlog",     0.47,"2024-10-31",3),
    (11, 9,"2024-08","2024-08","Two consecutive fill-finish batch failures",              "Root cause analysis; rework approval",    "Quality",          0.58,"2024-11-30",3),
    (12, 9,"2024-09","2024-09","Demand spike + constrained supply — compounded shortfall","Emergency import + customer allocation", "Demand Variation", 0.71,"2024-12-31",3),
    (13, 3,"2024-03","2024-03","Coating excipient rejected — artwork change pending",     "Change control board fast-track",         "Quality",          0.15,"2024-05-31",2),
    (14,11,"2024-07","2024-07","Cold-chain logistics failure — product quarantined",      "CAPA; logistics vendor replacement",      "Quality",          0.60,"2024-09-30",2),
    (15, 5,"2024-08","2024-08","Demand surge from tender win; safety stock insufficient","Emergency production run authorisation",  "Demand Variation", 0.28,"2024-10-31",2),
    (16, 7,"2024-05","2024-05","Primary packing line breakdown — extended downtime",      "Machine repair + rental backup unit",     "Site Backlog",     0.22,"2024-07-31",2),
    (17,12,"2024-09","2024-09","API import constrained by FOREX availability",            "Pre-payment approval; FOREX desk",        "RMPM",             0.19,"2024-11-30",2),
    (18, 2,"2024-06","2024-06","Commercial deal structure caused channel oversale",       "Demand revision; customer allocation",    "Commercial",       0.09,"2024-08-31",1),
]
cur.executemany("INSERT INTO supply_issues VALUES (?,?,?,?,?,?,?,?,?,?)", issues)

conn.commit()
conn.close()

print("supply_chain.db created successfully.")
print(f"  sites               : {len(SITES)} rows")
print(f"  products            : {len(PRODUCTS)} rows")
print(f"  production_plan     : {len(plan_rows)} rows")
print(f"  inventory_movements : {len(movements)} rows")
print(f"  sales_orders        : {len(orders)} rows")
print(f"  stock_build_up      : {len(buildup)} rows")
print(f"  supply_issues       : {len(issues)} rows")

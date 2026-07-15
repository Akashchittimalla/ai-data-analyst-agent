"""
seed_data.py
Generates realistic 2-year (2023-2024) business dataset for DuckDB.
Includes deliberate Q3 2023 Electronics dip to power the demo scenario.
Run standalone: python seed_data.py
"""

import random
from datetime import date, timedelta

import duckdb

random.seed(42)

REGIONS = ["North", "South", "East", "West"]
CATEGORIES = ["Electronics", "Apparel", "Home", "Sports"]
SEGMENTS = ["Enterprise", "SMB", "Consumer"]

PRODUCTS = {
    "Electronics": ["Laptop Pro", "Wireless Earbuds", "Smart Watch", "4K Monitor", "Tablet X"],
    "Apparel": ["Winter Jacket", "Running Shoes", "Yoga Pants", "Casual Tee", "Dress Shirt"],
    "Home": ["Coffee Maker", "Air Purifier", "LED Desk Lamp", "Blender", "Throw Blanket"],
    "Sports": ["Yoga Mat", "Resistance Bands", "Foam Roller", "Jump Rope", "Water Bottle"],
}

BASE_PRICES = {
    "Laptop Pro": 1299,
    "Wireless Earbuds": 149,
    "Smart Watch": 349,
    "4K Monitor": 499,
    "Tablet X": 599,
    "Winter Jacket": 189,
    "Running Shoes": 129,
    "Yoga Pants": 79,
    "Casual Tee": 29,
    "Dress Shirt": 59,
    "Coffee Maker": 89,
    "Air Purifier": 199,
    "LED Desk Lamp": 49,
    "Blender": 69,
    "Throw Blanket": 39,
    "Yoga Mat": 45,
    "Resistance Bands": 25,
    "Foam Roller": 35,
    "Jump Rope": 19,
    "Water Bottle": 29,
}


def seed_all(con: duckdb.DuckDBPyConnection):
    _seed_products(con)
    _seed_customers(con)
    _seed_sales(con)
    sales_count = con.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    cust_count = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    print(f"  -> {sales_count:,} sales rows")
    print(f"  -> {cust_count:,} customers")


def _seed_products(con):
    rows = []
    for cat, prods in PRODUCTS.items():
        for name in prods:
            pid = name.lower().replace(" ", "_")
            price = BASE_PRICES[name]
            cost = round(price * random.uniform(0.35, 0.55), 2)
            launch = date(2020, random.randint(1, 12), random.randint(1, 28))
            rows.append((pid, name, cat, price, cost, launch))
    con.executemany("INSERT INTO products VALUES (?,?,?,?,?,?)", rows)


def _seed_customers(con):
    rows = []
    for i in range(1, 3001):
        cid = f"C{i:05d}"
        name = f"Customer {i}"
        seg = random.choice(SEGMENTS)
        region = random.choice(REGIONS)
        acq = date(2022, 1, 1) + timedelta(days=random.randint(0, 730))
        ltv = round(random.uniform(100, 8000), 2)
        rows.append((cid, name, seg, region, acq, ltv))
    con.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?)", rows)


def _seed_sales(con):
    """
    ~14,000 transactions across 2023-2024.
    Q3 2023: Electronics volume drops 45% (supply chain shock).
    Nov-Dec: +40% seasonal uplift.
    """
    rows = []
    current = date(2023, 1, 1)
    end = date(2024, 12, 31)

    while current <= end:
        in_q3_2023 = current.year == 2023 and current.month in [7, 8, 9]
        in_holiday = current.month in [11, 12]

        base = 20 if in_holiday else 14
        if in_q3_2023:
            base = max(5, int(base * 0.55))

        n = random.randint(base - 2, base + 4)

        for _ in range(n):
            cat = random.choice(CATEGORIES)

            # During Q3 shock, Electronics is 60% less likely.
            if in_q3_2023 and cat == "Electronics" and random.random() < 0.60:
                cat = random.choice(["Apparel", "Home", "Sports"])

            product = random.choice(PRODUCTS[cat])
            region = random.choices(REGIONS, weights=[30, 25, 28, 17])[0]
            price = BASE_PRICES[product]
            units = random.randint(1, 4)
            revenue = round(price * units * random.uniform(0.92, 1.08), 2)
            cost = round(revenue * random.uniform(0.35, 0.55), 2)
            product_id = product.lower().replace(" ", "_")
            customer_id = f"C{random.randint(1, 3000):05d}"
            rows.append((current, customer_id, product_id, product, cat, region, revenue, units, cost))

        current += timedelta(days=1)

    con.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?,?)", rows)


if __name__ == "__main__":
    import os

    os.makedirs("data", exist_ok=True)
    con = duckdb.connect("data/analytics.duckdb")
    for tbl in [
        "CREATE TABLE IF NOT EXISTS sales(date DATE, customer_id VARCHAR, product_id VARCHAR, product VARCHAR, category VARCHAR, region VARCHAR, revenue DECIMAL(12,2), units INTEGER, cost DECIMAL(12,2))",
        "CREATE TABLE IF NOT EXISTS customers(customer_id VARCHAR, name VARCHAR, segment VARCHAR, region VARCHAR, acq_date DATE, lifetime_val DECIMAL(12,2))",
        "CREATE TABLE IF NOT EXISTS products(product_id VARCHAR, name VARCHAR, category VARCHAR, price DECIMAL(10,2), cost DECIMAL(10,2), launch_date DATE)",
    ]:
        con.execute(tbl)
    seed_all(con)
    con.close()
    print("Done.")

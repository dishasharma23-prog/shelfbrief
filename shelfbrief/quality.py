"""Data-quality rules for the product table, written as SQL so they can run straight on shelf.sqlite.

Each rule is a query that returns the rows breaking it. A clean table returns nothing for every rule.

    python -m shelfbrief quality            # check data/shelf.sqlite (or data/products.csv)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

RULES = {
    "missing title, url or brand":
        "SELECT product_id FROM products WHERE COALESCE(title, '') = '' OR COALESCE(url, '') = '' OR COALESCE(brand, '') = ''",
    "price missing or not positive":
        "SELECT product_id FROM products WHERE price_inr IS NULL OR price_inr <= 0",
    "price above MRP":
        "SELECT product_id FROM products WHERE mrp_inr IS NOT NULL AND price_inr > mrp_inr + 0.01",
    "discount does not match price and MRP":
        """SELECT product_id FROM products
           WHERE mrp_inr > 0 AND discount_pct IS NOT NULL
             AND ABS(discount_pct - 100.0 * (mrp_inr - price_inr) / mrp_inr) > 0.6""",
    "duplicate product in a brand":
        "SELECT brand_slug, product_id FROM products GROUP BY brand_slug, product_id HAVING COUNT(*) > 1",
    "duplicate URL":
        "SELECT url FROM products GROUP BY url HAVING COUNT(*) > 1",
    "rating outside 0-5":
        "SELECT product_id FROM products WHERE rating IS NOT NULL AND (rating < 0 OR rating > 5)",
    "negative review count":
        "SELECT product_id FROM products WHERE review_count < 0",
    "rating without reviews behind it":
        "SELECT product_id FROM products WHERE rating IS NOT NULL AND review_count = 0",
    "size given without a unit":
        "SELECT product_id FROM products WHERE size IS NOT NULL AND size > 0 AND COALESCE(size_unit, '') = ''",
    "price per 100 ml/g does not match price and size":
        """SELECT product_id FROM products
           WHERE size > 0 AND price_per_100 IS NOT NULL
             AND ABS(price_per_100 - 100.0 * price_inr / size) > 0.05 * price_per_100 + 0.5""",
}


def check(db: sqlite3.Connection) -> dict[str, int]:
    """Run every rule and return how many rows break each one (0 = clean)."""
    return {name: len(db.execute(sql).fetchall()) for name, sql in RULES.items()}


def check_frame(df: pd.DataFrame) -> dict[str, int]:
    """Same rules on a DataFrame, loaded into an in-memory SQLite database."""
    with sqlite3.connect(":memory:") as db:
        df.to_sql("products", db, index=False)
        return check(db)


def check_files(data_dir: Path) -> dict[str, int]:
    db_path = data_dir / "shelf.sqlite"
    if db_path.exists():
        with sqlite3.connect(db_path) as db:
            return check(db)
    return check_frame(pd.read_csv(data_dir / "products.csv"))


def report(results: dict[str, int]) -> bool:
    for name, bad in results.items():
        print(f"  {'ok  ' if bad == 0 else 'FAIL'}  {name}" + (f": {bad} row(s)" if bad else ""))
    return all(bad == 0 for bad in results.values())

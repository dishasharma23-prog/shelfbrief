import pandas as pd
import pytest

from shelfbrief.quality import RULES, check_frame

GOOD = {
    "brand": "TestCo", "brand_slug": "t", "product_id": 1, "title": "Glow Serum", "url": "https://t.test/products/glow",
    "price_inr": 450.0, "mrp_inr": 500.0, "discount_pct": 10.0, "size": 30.0, "size_unit": "ml",
    "price_per_100": 1500.0, "rating": 4.4, "review_count": 120,
}


def table(*changes):
    rows = []
    for i, change in enumerate(changes or [{}]):
        row = {**GOOD, "product_id": i + 1, "url": f"https://t.test/products/{i}"}
        row.update(change)
        rows.append(row)
    return pd.DataFrame(rows)


def test_clean_table_passes_every_rule():
    results = check_frame(table({}, {"mrp_inr": None, "discount_pct": None}, {"size": None, "price_per_100": None}))
    assert results == {name: 0 for name in RULES}


@pytest.mark.parametrize("rule, change", [
    ("missing title, url or brand", {"title": ""}),
    ("price missing or not positive", {"price_inr": 0}),
    ("price above MRP", {"price_inr": 650.0, "discount_pct": None}),
    ("discount does not match price and MRP", {"discount_pct": 25.0}),
    ("rating outside 0-5", {"rating": 7}),
    ("negative review count", {"review_count": -3}),
    ("rating without reviews behind it", {"rating": 0.0, "review_count": 0}),
    ("size given without a unit", {"size_unit": ""}),
    ("price per 100 ml/g does not match price and size", {"price_per_100": 300.0}),
])
def test_each_rule_catches_its_problem(rule, change):
    results = check_frame(table({}, change))
    assert results[rule] == 1, results


def test_duplicates_are_caught():
    df = table({}, {})
    df.loc[1, ["product_id", "url"]] = df.loc[0, ["product_id", "url"]].values
    results = check_frame(df)
    assert results["duplicate product in a brand"] == 1
    assert results["duplicate URL"] == 1

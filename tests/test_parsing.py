from shelfbrief import claims
from shelfbrief.clean import build_table, parse_size, product_row
from shelfbrief.pages import parse_product_page

BRAND = {"slug": "t", "name": "TestCo", "url": "https://t.test"}


def test_jsonld_rating_offer_and_breadcrumbs():
    html = """<html><head>
    <script type="application/ld+json">{"@context":"https://schema.org","@graph":[
      {"@type":"Product","name":"Glow Serum","sku":"GS1","offers":[{"@type":"Offer","price":"499.00","priceCurrency":"INR",
       "availability":"https://schema.org/InStock"}],"aggregateRating":{"ratingValue":"4.4","reviewCount":"1,203"}},
      {"@type":"BreadcrumbList","itemListElement":[{"position":2,"name":"Serums"},{"position":1,"name":"Home"}]}]}</script>
    </head></html>"""
    p = parse_product_page(html)
    assert p["name"] == "Glow Serum" and p["price"] == 499.0 and p["currency"] == "INR"
    assert p["rating"] == 4.4 and p["review_count"] == 1203 and p["rating_source"] == "json-ld"
    assert p["availability"] == "InStock" and p["breadcrumbs"] == ["Home", "Serums"]


def test_repairs_trailing_comma_jsonld():
    html = '<script type="application/ld+json">{"@type":"Product","name":"X","aggregateRating":{"ratingValue":4.1,"reviewCount":9},}</script>'
    assert parse_product_page(html)["rating"] == 4.1


def test_judgeme_badge_fallback_and_og_tags():
    html = """<head><meta property="og:title" content="Hair Oil"><meta property="product:price:amount" content="399.00"></head>
    <div class="jdgm-prev-badge" data-average-rating="4.30" data-number-of-reviews="2890"></div>"""
    p = parse_product_page(html)
    assert p["name"] == "Hair Oil" and p["price"] == 399.0
    assert (p["rating"], p["review_count"], p["rating_source"]) == (4.3, 2890, "judge.me")


def test_sizes_normalise():
    assert parse_size("Shampoo 1 L") == (1000, "ml")
    assert parse_size("Face Pack 50gm") == (50, "g")
    assert parse_size("no size here") == (None, None)


def test_claims_vocabulary():
    text = "Vitamin C 15% serum with 1% hyaluronic acid. Fragrance-free, vegan. Get 20% off today!"
    assert claims.strengths(text) == ["15% Vitamin C", "1% Hyaluronic Acid"]
    assert "Fragrance-Free" in claims.find(claims.FREE_FROM, text)
    assert claims.categorise("Fragrance-free Face Cream") == "Moisturiser"
    assert claims.categorise("Rosemary Hair Growth Serum") == "Hair Oil & Serum"
    assert claims.categorise("Maleic Bond Repair Hair Shampoo", "hair growth kit") == "Shampoo & Conditioner"  # title wins
    assert claims.categorise("Barrier Balm", "Moisturizer") == "Moisturiser"   # falls back to type and tags
    assert claims.spf("Sun gel SPF 50 PA++++") == 50
    assert claims.hours("up to 8 hours, 24-hour hydration") == [24, 8]


def raw(title, variants, **kw):
    return {"id": 1, "title": title, "handle": title.lower().replace(" ", "-"), "body_html": kw.get("body", ""),
            "product_type": kw.get("ptype", ""), "tags": kw.get("tags", []), "variants": variants,
            "created_at": "2026-09-01T10:00:00+05:30"}


def test_product_row_uses_one_variant_for_price_mrp_and_size():
    r = product_row(BRAND, raw("Oud EDP", [
        {"title": "100 ml", "price": "1299.00", "compare_at_price": "1599.00", "available": True},
        {"title": "50 ml", "price": "799.00", "compare_at_price": "999.00", "available": True}]))
    assert (r["price_inr"], r["mrp_inr"], r["size"], r["discount_pct"]) == (799, 999, 50, 20.0)
    assert r["price_per_100"] == 1598.0


def test_junk_products_are_dropped():
    assert product_row(BRAND, raw("Gift Card", [{"price": "500"}])) is None
    assert product_row(BRAND, raw("Sample: Gel 5 g", [{"price": "1"}])) is None
    assert product_row(BRAND, raw("Free thing", [{"price": "0.00"}])) is None
    assert product_row(BRAND, raw("Rs 150 off BookMyShow voucher", [{"price": "150"}])) is None
    assert product_row(BRAND, raw("Toner 10ml | Mini", [{"price": "1.00"}])) is None   # Rs 1 gift-with-purchase
    r = product_row(BRAND, raw("Toner Duo", [{"title": "Promo 10 ml", "price": "1"}, {"title": "100 ml", "price": "399"}]))
    assert (r["price_inr"], r["size"]) == (399, 100)


def test_table_dedupes_and_positions_prices():
    rows = [product_row(BRAND, raw(f"Serum {i}", [{"title": "30 ml", "price": str(p)}])) for i, p in
            enumerate([300, 600, 600, 1200])]
    rows.append(dict(rows[1]))  # duplicate
    df = build_table(rows)
    assert len(df) == 4
    pos = dict(zip(df["title"], df["price_position"]))
    assert pos["Serum 0"] == "Value" and pos["Serum 1"] == "Mid" and pos["Serum 3"] == "Premium"

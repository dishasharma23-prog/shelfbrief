"""Builds tests/fixtures/web.json: a small fake web of FICTIONAL brands used by the tests and `shelfbrief demo`.

Covers the cases the real scraper meets: a well-behaved store with JSON-LD ratings and a crawl-delay,
a store whose ratings live in a Judge.me badge, a store that allows its catalog but not product pages,
a site that disallows everything, and a site that isn't on Shopify at all.
Run: python tests/fixtures/build_fixtures.py
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

NOW = datetime(2026, 10, 26, tzinfo=timezone.utc)
web = {}


def put(url, body, status=200, ctype="text/html"):
    web[url] = {"status": status, "content_type": ctype, "body": body if isinstance(body, str) else json.dumps(body)}


def product(pid, title, ptype, price, mrp, size, body, tags, days_old, extra_variants=()):
    variants = [{"id": pid * 10, "title": size, "price": f"{price:.2f}",
                 "compare_at_price": f"{mrp:.2f}" if mrp and mrp > price else None, "available": True}]
    for i, (vtitle, vprice, vmrp) in enumerate(extra_variants, 1):
        variants.append({"id": pid * 10 + i, "title": vtitle, "price": f"{vprice:.2f}",
                         "compare_at_price": f"{vmrp:.2f}" if vmrp else None, "available": True})
    created = (NOW - timedelta(days=days_old)).isoformat()
    handle = title.lower().replace("%", "").replace("&", "and").replace("+", "").replace(":", "")
    handle = "-".join(w for w in handle.replace("(", "").replace(")", "").split())
    return {"id": pid, "title": title, "handle": handle, "body_html": f"<p>{body}</p>", "product_type": ptype,
            "vendor": "", "tags": tags, "created_at": created, "published_at": created,
            "updated_at": (NOW - timedelta(days=min(days_old, 5))).isoformat(), "variants": variants, "images": []}


def page_html(name, desc, price, jsonld_rating=None, judgeme=None, breadcrumb=None, broken=False, no_jsonld=False):
    blocks = []
    if not no_jsonld:
        ld = {"@context": "https://schema.org", "@type": "Product", "name": name, "description": desc,
              "offers": {"@type": "Offer", "price": f"{price:.2f}", "priceCurrency": "INR",
                         "availability": "https://schema.org/InStock"}}
        if jsonld_rating:
            ld["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": jsonld_rating[0], "reviewCount": jsonld_rating[1]}
        text = json.dumps(ld, indent=1)
        if broken:  # a trailing comma, as some themes ship
            text = text[:-2] + ",\n}"
        blocks.append(f'<script type="application/ld+json">{text}</script>')
    if breadcrumb:
        bc = {"@context": "https://schema.org", "@type": "BreadcrumbList",
              "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n} for i, n in enumerate(breadcrumb)]}
        blocks.append(f'<script type="application/ld+json">{json.dumps(bc)}</script>')
    badge = ""
    if judgeme:
        badge = (f'<div class="jdgm-widget jdgm-preview-badge"><div class="jdgm-prev-badge" '
                 f'data-average-rating="{judgeme[0]}" data-number-of-reviews="{judgeme[1]}">'
                 f'<span class="jdgm-prev-badge__text">{judgeme[1]} reviews</span></div></div>')
    return f"""<!doctype html><html><head><title>{name}</title>
<meta property="og:title" content="{name}"><meta property="og:description" content="{desc[:150]}">
<meta property="product:price:amount" content="{price:.2f}"><meta property="product:price:currency" content="INR">
{''.join(blocks)}</head><body><main><h1 class="product__title">{name}</h1>{badge}
<div class="price">Rs. {price:,.0f}</div><div class="product__description rte">{desc}</div></main></body></html>"""


def store(host, robots, products, pages, crawl=True):
    base = f"https://{host}"
    put(base + "/robots.txt", robots, ctype="text/plain")
    put(base + "/products.json?limit=1&page=1", {"products": products[:1]}, ctype="application/json")
    put(base + "/products.json?limit=250&page=1", {"products": products}, ctype="application/json")
    put(base + "/products.json?limit=250&page=2", {"products": []}, ctype="application/json")
    for p in products:
        if p["handle"] in pages:
            put(f"{base}/products/{p['handle']}", pages[p["handle"]])


# ---------- Dewleaf: skincare, JSON-LD ratings, crawl-delay ----------
D = [
    (101, "10% Niacinamide + 1% Zinc Serum", "Serum", 549, 599, "30 ml", "Oil control serum for acne-prone skin. Helps reduce blemishes and visible pores. Fragrance-free, vegan and non-comedogenic.", ["serum", "oily skin"], 400, (4.5, 2310)),
    (102, "Vitamin C 15% Brightening Serum", "Serum", 699, 799, "30 ml", "15% ethyl ascorbic acid for a brighter glow and fading dark spots. Dermatologically tested.", ["serum", "glow"], 300, (4.3, 1180)),
    (103, "SPF 50 PA++++ Hybrid Sunscreen Gel", "Sunscreen", 449, 499, "50 g", "Lightweight sun gel with broad UVA/UVB protection. Paraben-free and non-comedogenic.", ["sunscreen"], 260, (4.4, 3105)),
    (104, "Ceramide Barrier Repair Moisturiser", "Moisturiser", 499, 0, "50 g", "Five ceramides with hyaluronic acid to repair the skin barrier and calm redness. Fragrance-free, for sensitive skin.", ["moisturiser"], 210, (4.6, 870)),
    (105, "2% Salicylic Acid Face Wash", "Face Wash", 299, 349, "100 ml", "BHA cleanser for oily, acne-prone skin. Sulphate-free.", ["cleanser"], 500, (4.2, 1640)),
    (106, "Hyaluronic Acid Hydrating Toner", "Toner", 399, 0, "100 ml", "Hydrating toner that leaves skin plump and soft.", ["toner"], 180, (4.1, 320)),
    (107, "Retinol 0.3% Night Cream", "Moisturiser", 799, 999, "30 g", "Encapsulated retinol night cream for fine lines. Start twice a week.", ["night cream", "anti-ageing"], 40, (4.0, 210)),
    (108, "Alpha Arbutin 2% Spot Serum", "Serum", 599, 0, "30 ml", "2% alpha arbutin for pigmentation and dark spots.", ["serum", "new"], 20, (4.4, 58)),
    (109, "Glow Starter Kit", "Kit", 1299, 1597, "Default Title", "Our three bestsellers in one kit.", ["kit"], 90, None),
    (110, "Peptide Under Eye Cream", "Eye Cream", 549, 0, "15 g", "Peptides and caffeine for fine lines and puffiness.", ["eye care"], 150, (3.9, 140)),
    (111, "Gift Card", "Gift Card", 500, 0, "Default Title", "A Dewleaf gift card.", [], 600, None),
    (112, "Sample: Sunscreen Gel 5 g", "Sample", 1, 0, "5 g", "Free sample.", [], 30, None),
    (113, "Centella Calming Gel Cream", "Moisturiser", 449, 0, "50 g", "Centella asiatica gel cream that soothes sensitive, irritated skin.", ["cica"], 75, (4.5, 96)),
]
dew_products, dew_pages = [], {}
for i, (pid, t, ty, pr, mrp, sz, body, tags, age, rating) in enumerate(D):
    p = product(pid, t, ty, pr, mrp, sz, body, tags, age)
    dew_products.append(p)
    if rating:
        dew_pages[p["handle"]] = page_html(t, body, pr, jsonld_rating=rating, breadcrumb=["Home", ty, t],
                                           broken=(pid == 104), no_jsonld=False)
store("dewleaf.example", "User-agent: *\nDisallow: /cart\nDisallow: /checkout\nCrawl-delay: 2\n", dew_products, dew_pages)

# ---------- Kesari Botanicals: hair & ayurveda, Judge.me badges ----------
K = [
    (201, "Rosemary & Onion Hair Growth Oil", "Hair Oil", 399, 499, "200 ml", "Ayurvedic oil with rosemary and onion to reduce hair fall. Sulphate-free formula.", ["hair"], 420, (4.3, 2890)),
    (202, "Rice Water Shampoo", "Shampoo", 349, 0, "250 ml", "Strengthening rice water shampoo for hair fall. Sulphate-free and paraben-free.", ["hair"], 360, (4.1, 1220)),
    (203, "Rice Water Conditioner", "Conditioner", 349, 0, "250 ml", "Hydrating rice water conditioner for soft, smooth lengths.", ["hair"], 360, (4.0, 610)),
    (204, "Kumkumadi Brightening Face Oil", "Face Oil", 899, 1099, "30 ml", "Ayurvedic kumkumadi tailam with saffron for a radiant glow.", ["face"], 500, (4.6, 740)),
    (205, "Anti-Dandruff Tea Tree Shampoo", "Shampoo", 399, 0, "250 ml", "Tea tree and zinc to control dandruff and itchy, flaky scalp.", ["hair"], 280, (4.2, 530)),
    (206, "Kesar Ubtan De-Tan Face Pack", "Face Pack", 299, 399, "100 g", "Saffron ubtan face pack for tan removal and brightening.", ["face"], 330, (4.3, 980)),
    (207, "Bhringraj Scalp Serum", "Hair Serum", 649, 0, "50 ml", "Lightweight scalp serum with bhringraj and rosemary for hair fall. Ayurvedic.", ["hair", "new"], 30, (4.5, 45)),
    (208, "Aloe Vera Gel", "Gel", 199, 0, "300 ml", "Pure aloe vera gel to hydrate and soothe skin and hair.", ["multi-use"], 700, (4.4, 1500)),
    (209, "Hair Care Ritual Combo", "Combo", 999, 1197, "Default Title", "Oil, shampoo and conditioner together.", ["combo"], 200, None),
    (210, "Coconut Milk Body Lotion", "Body Lotion", 299, 0, "400 ml", "Body lotion with coconut milk for 24-hour hydration.", ["body"], 240, (4.2, 300)),
    (211, "Sandalwood Soap (Pack of 3)", "Soap", 249, 0, "375 g", "Handmade ayurvedic sandalwood soap.", ["body"], 650, (4.1, 410)),
]
kes_products, kes_pages = [], {}
for pid, t, ty, pr, mrp, sz, body, tags, age, rating in K:
    p = product(pid, t, ty, pr, mrp, sz, body, tags, age)
    kes_products.append(p)
    if rating:
        kes_pages[p["handle"]] = page_html(t, body, pr, judgeme=rating, no_jsonld=(pid == 208))
store("kesaribotanicals.example", "User-agent: *\nDisallow: /account\n", kes_products, kes_pages)

# ---------- Monsoon Men: grooming; catalog allowed, product pages disallowed ----------
M = [
    (301, "Charcoal Oil Control Face Wash", "Face Wash", 249, 299, "100 ml", "Activated charcoal face wash for oily skin and oil control.", ["men"], 380),
    (302, "Beard Growth Oil with Rosemary", "Beard Oil", 399, 499, "30 ml", "Rosemary and argan beard oil for a fuller-looking beard.", ["beard"], 300),
    (303, "Matte Finish Sunscreen SPF 50", "Sunscreen", 399, 0, "50 g", "Matte sunscreen with SPF 50 for oily skin. Non-comedogenic.", ["men", "sun"], 160),
    (304, "Caffeine Under Eye Gel", "Eye Care", 349, 0, "15 g", "Caffeine gel for dark circles and puffiness.", ["men"], 220),
    (305, "Sandalwood Beard Wash", "Beard Wash", 299, 0, "100 ml", "Gentle sulphate-free beard wash.", ["beard"], 260),
    (306, "Precision Razor Kit", "Kit", 999, 1299, "Default Title", "Razor, two cartridges and a travel case.", ["shaving"], 450),
    (307, "Oud Noir Eau de Parfum", "Perfume", 1299, 1599, "100 ml", "Long-lasting woody oud fragrance, up to 8 hours.", ["fragrance"], 110, (("50 ml", 799, 999),)),
    (308, "Aqua Deodorant Body Spray", "Deodorant", 249, 0, "150 ml", "Fresh aquatic deodorant with long-lasting freshness.", ["body"], 340),
    (309, "4% Niacinamide Oil-Free Moisturiser", "Moisturiser", 399, 0, "50 g", "4% niacinamide, oil-free gel for oily skin. Non-comedogenic.", ["men", "new"], 25),
    (310, "Hair Wax Strong Hold", "Styling", 349, 0, "75 g", "Matte strong-hold hair wax.", ["hair"], 410),
]
mon_products = []
for row in M:
    pid, t, ty, pr, mrp, sz, body, tags, age, *extra = row
    mon_products.append(product(pid, t, ty, pr, mrp, sz, body, tags, age, extra[0] if extra else ()))
store("monsoonmen.example", "User-agent: *\nDisallow: /products/\nDisallow: /cart\n", mon_products, {})

# ---------- GlowCart: disallows everything ----------
put("https://glowcart.example/robots.txt", "User-agent: *\nDisallow: /\n", ctype="text/plain")
# ---------- HerbHouse: not Shopify ----------
put("https://herbhouse.example/robots.txt", "", status=404, ctype="text/plain")
put("https://herbhouse.example/products.json?limit=1&page=1", "<html>Not found</html>", status=404)

out = Path(__file__).with_name("web.json")
out.write_text(json.dumps(web, indent=1), encoding="utf-8")
print(f"wrote {len(web)} URLs to {out}")

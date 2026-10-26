import json

import pytest

import httpx

from shelfbrief import briefs, pipeline
from shelfbrief.demo import FIXTURES, fake_web_transport
from shelfbrief.fetcher import Fetcher


def run_demo(tmp_path):
    brands = pipeline.load_brands(FIXTURES / "brands.yaml")
    fetcher = Fetcher(transport=fake_web_transport(), sleep=lambda s: None)
    status = pipeline.scrape(fetcher, brands, tmp_path)
    df = pipeline.clean(brands, tmp_path)
    items = pipeline.brief(df, tmp_path, use_llm=False)
    run = pipeline.export_site(df, items, status, tmp_path, tmp_path / "site.json", fetcher.stats, sample=True)
    return status, df, items, run


def test_end_to_end_on_fixture_web(tmp_path):
    status, df, items, run = run_demo(tmp_path)
    by = {s["slug"]: s for s in status}
    assert by["glowcart"]["status"] == "skipped" and "robots" in by["glowcart"]["reason"]
    assert by["herbhouse"]["status"] == "skipped" and "Shopify" in by["herbhouse"]["reason"]
    assert by["monsoonmen"]["pages_parsed"] == 0          # product pages are disallowed there
    assert by["dewleaf"]["pages_parsed"] > 0
    # gift card and sample are filtered out of 34 raw products
    assert run["catalog_products"] == 34 and len(df) == 32
    assert df.loc[df["brand_slug"] == "monsoonmen", "rating"].isna().all()
    assert df.loc[df["brand_slug"] == "kesari", "rating_source"].dropna().eq("judge.me").all()
    for f in ("products.csv", "products.json", "shelf.sqlite", "briefs.json", "run.json", "site.json"):
        assert (tmp_path / f).exists()
    site = json.loads((tmp_path / "site.json").read_text(), parse_constant=pytest.fail)  # browsers reject NaN
    assert site["run"]["sample"] is True and len(site["products"]) == 32
    raw = site["raw_example"]                               # one untouched catalog record for the raw -> clean demo
    assert raw["url"] == items[0]["product"]["url"] and raw["variants"] and "price" in raw["variants"][0]


def test_briefs_are_grounded_and_skip_kits(tmp_path):
    _, df, items, _ = run_demo(tmp_path)
    assert items and all(b["product"]["category"] != "Kits & Combos" for b in items)
    for b in items:
        p = df[df["url"] == b["product"]["url"]].iloc[0]
        page_claims = set(p["strengths"]) | set(p["ingredients"]) | set(p["free_from"])
        for point in b["proof_points"]:
            assert (point in page_claims or point.startswith(("Rated ", "SPF "))
                    or point.endswith("-hour claim on the product page")), point
        assert any("ASCI" in g for g in b["guardrails"])


def test_llm_output_with_invented_numbers_is_rejected():
    f = {"strengths": ["10% Niacinamide"], "spf": None}
    assert briefs._grounded("10% Niacinamide for clearer skin", f)
    assert not briefs._grounded("Packed with 20% Niacinamide", f)
    assert not briefs._grounded("SPF 50 daily", f)


def test_llm_brief_falls_back_on_bad_response():
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    f = {"strengths": [], "spf": None}
    assert briefs.llm_brief(f, "key", "model", client) is None


def test_stops_asking_a_store_that_keeps_rate_limiting(tmp_path):
    products = [{"id": i, "handle": f"p{i}", "title": f"Serum {i}", "updated_at": f"2026-01-{i + 1:02d}",
                 "variants": [{"price": "499.00", "title": "30ml"}]} for i in range(6)]
    page_hits = []

    def handler(req):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if req.url.path == "/products.json":
            return httpx.Response(200, json={"products": products if req.url.params.get("page") in ("1", None) else []})
        page_hits.append(req.url.path)
        return httpx.Response(429, headers={"Retry-After": "1"})

    brand = {"slug": "busy", "name": "Busy Store", "url": "https://busy.test"}
    fetcher = Fetcher(transport=httpx.MockTransport(handler), sleep=lambda s: None, max_retries=1)
    status = pipeline.scrape(fetcher, [brand], tmp_path, enrich=6)
    assert status[0]["rate_limited"] and status[0]["pages_parsed"] == 0
    assert len(set(page_hits)) == pipeline.RATE_LIMIT_STOP     # gave up after two pages, not all six

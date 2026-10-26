"""The five stages: check -> crawl -> parse -> clean -> brief, plus exports for analysis and the website."""
from __future__ import annotations

import json
import logging
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

from . import briefs as briefs_mod
from . import shopify
from .clean import _JUNK, build_table, product_row
from .fetcher import Disallowed, FetchError, Fetcher
from .pages import parse_product_page

log = logging.getLogger("shelfbrief")
RATE_LIMIT_STOP = 2   # product pages in a row that still get HTTP 429 after all retries before we stop asking a store


def load_brands(path: Path, only: list[str] | None = None) -> list[dict]:
    brands = yaml.safe_load(Path(path).read_text(encoding="utf-8"))["brands"]
    brands = [b for b in brands if b.get("enabled", True)]
    if only:
        brands = [b for b in brands if b["slug"] in only]
    return brands


def _no_nan(x):
    # pandas leaves NaN in dicts built from rows; NaN isn't valid JSON, so browsers refuse the whole file
    if isinstance(x, float) and x != x:
        return None
    if isinstance(x, dict):
        return {k: _no_nan(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_no_nan(v) for v in x]
    return x


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_no_nan(data), ensure_ascii=False, indent=1, default=str, allow_nan=False),
                    encoding="utf-8")


def _read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


# ---------------- 1. check ----------------
def check(fetcher: Fetcher, brands: list[dict]) -> list[dict]:
    results = []
    for b in brands:
        cat = shopify.catalog_url(b["url"], 1)
        page = shopify.product_url(b["url"], "example")
        r = {"slug": b["slug"], "name": b["name"], "url": b["url"],
             "robots_catalog": fetcher.allowed(cat), "robots_pages": fetcher.allowed(page),
             "crawl_delay": fetcher.crawl_delay(cat), "shopify": False, "status": "ok", "reason": ""}
        if not r["robots_catalog"]:
            r.update(status="skipped", reason="robots.txt disallows the product catalog")
        elif not shopify.looks_like_shopify(fetcher, b["url"]):
            r.update(status="skipped", reason="no public Shopify catalog (/products.json)")
        else:
            r["shopify"] = True
        log.info("%-24s %s %s", b["name"], r["status"].upper(), r["reason"])
        results.append(r)
    return results


# ---------------- 2+3. crawl and parse ----------------
def scrape(fetcher: Fetcher, brands: list[dict], data_dir: Path, max_pages: int = 20, enrich: int = 40) -> list[dict]:
    status = check(fetcher, brands)
    for b, s in zip(brands, status):
        if s["status"] != "ok":
            continue
        raw_dir = data_dir / "raw" / b["slug"]
        try:
            products = list(shopify.iter_products(fetcher, b["url"], max_pages=max_pages))
        except (Disallowed, FetchError) as e:
            s.update(status="failed", reason=str(e))
            continue
        _write_json(raw_dir / "catalog.json", products)
        s["catalog_products"] = len(products)

        pages, parsed, blocked, limited = {}, 0, 0, 0
        if s["robots_pages"] and enrich:
            sellable = [p for p in products if not _JUNK.search(p.get("title") or "")]  # don't fetch gift cards
            newest = sorted(sellable, key=lambda p: p.get("updated_at") or "", reverse=True)[:enrich]
            for p in newest:
                url = shopify.product_url(b["url"], p.get("handle", ""))
                try:
                    pages[url] = parse_product_page(fetcher.get_text(url))
                    parsed += 1
                    limited = 0
                except Disallowed:
                    blocked += 1
                except FetchError as e:
                    log.warning("page failed: %s", e)
                    limited = limited + 1 if "HTTP 429" in str(e) else 0
                    if limited >= RATE_LIMIT_STOP:   # the store keeps saying "slow down": stop asking this run
                        log.warning("%s keeps rate-limiting; skipping its remaining product pages", b["name"])
                        s["rate_limited"] = True
                        break
        _write_json(raw_dir / "pages.json", pages)
        s.update(pages_parsed=parsed, pages_blocked=blocked)
        log.info("%-24s %d products, %d pages parsed", b["name"], len(products), parsed)
    _write_json(data_dir / "raw" / "check.json", status)
    return status


# ---------------- 4. clean ----------------
def clean(brands: list[dict], data_dir: Path) -> pd.DataFrame:
    rows = []
    for b in brands:
        raw_dir = data_dir / "raw" / b["slug"]
        catalog = _read_json(raw_dir / "catalog.json", [])
        pages = _read_json(raw_dir / "pages.json", {})
        for raw in catalog:
            url = shopify.product_url(b["url"], raw.get("handle", ""))
            rows.append(product_row(b, raw, pages.get(url)))
    df = build_table(rows)
    out = data_dir / "products"
    if not df.empty:
        df.to_json(out.with_suffix(".json"), orient="records", force_ascii=False, indent=1)
        flat = df.copy()
        for col in ("ingredients", "benefits", "free_from", "strengths", "tags", "hours"):
            flat[col] = flat[col].map(lambda v: "; ".join(map(str, v)) if isinstance(v, list) else "")
        flat.to_csv(out.with_suffix(".csv"), index=False)
        with sqlite3.connect(data_dir / "shelf.sqlite") as db:
            flat.to_sql("products", db, if_exists="replace", index=False)
    log.info("clean table: %d products", len(df))
    return df


# ---------------- 5. brief ----------------
def brief(df: pd.DataFrame, data_dir: Path, per_brand: int = 4, use_llm: bool | None = None) -> list[dict]:
    items = briefs_mod.write_briefs(df, per_brand=per_brand, use_llm=use_llm) if not df.empty else []
    _write_json(data_dir / "briefs.json", items)
    log.info("briefs: %d", len(items))
    return items


# ---------------- exports ----------------
def _top_category(cats: pd.Series) -> str:
    # D2C stores list a combo for nearly every product, so "mostly kits" says nothing about the range
    real = cats[~cats.isin(["Kits & Combos", "Other"])]
    return (real if not real.empty else cats).value_counts().index[0]


def insights(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    by_brand = []
    for slug, g in df.groupby("brand_slug"):
        by_brand.append({
            "slug": slug, "brand": g["brand"].iloc[0], "products": int(len(g)),
            "median_price": float(g["price_inr"].median()), "avg_discount": round(float(g["discount_pct"].mean()), 1),
            "on_discount_pct": round(float((g["discount_pct"] > 0).mean() * 100), 1),
            "top_category": _top_category(g["category"]),
            "rated": int(g["rating"].notna().sum()),
            "avg_rating": round(float(g["rating"].mean()), 2) if g["rating"].notna().any() else None,
            "new_90d": int((g["days_since_launch"] <= 90).sum()),
        })

    def top(col, n=10):
        c = Counter(x for lst in df[col] for x in lst)
        out = []
        for name, count in c.most_common(n):
            brands = Counter(df.loc[df[col].map(lambda l: name in l), "brand"])
            out.append({"name": name, "count": count, "brands": dict(brands)})
        return out

    cat = (df.dropna(subset=["price_per_100"]).groupby(["category", "size_unit"])["price_per_100"]
           .agg(["median", "min", "max", "count"]).reset_index().sort_values("count", ascending=False))
    return {
        "totals": {"brands": int(df["brand_slug"].nunique()), "products": int(len(df)),
                   "categories": int(df["category"].nunique()),
                   "median_price": float(df["price_inr"].median()),
                   "avg_discount": round(float(df["discount_pct"].mean()), 1),
                   "with_ratings": int(df["rating"].notna().sum()),
                   "with_claims": int((df["ingredients"].map(len) + df["benefits"].map(len) > 0).sum())},
        "by_brand": sorted(by_brand, key=lambda r: -r["products"]),
        "top_ingredients": top("ingredients"),
        "top_benefits": top("benefits"),
        "top_free_from": top("free_from", 6),
        "category_price": [{"category": r.category, "unit": r.size_unit, "median": round(r["median"], 1),
                            "min": round(r["min"], 1), "max": round(r["max"], 1), "count": int(r["count"])}
                           for _, r in cat.head(10).iterrows()],
        "category_mix": [{"brand": b, **{k: int(v) for k, v in g["category"].value_counts().items()}}
                         for b, g in df.groupby("brand")],
    }


def raw_example(df: pd.DataFrame, items: list[dict], data_dir: Path) -> dict | None:
    """The first briefed product exactly as the catalog served it (trimmed), so the site can show raw next to clean."""
    if df.empty or not items:
        return None
    url = items[0]["product"]["url"]
    slug = df.loc[df["url"] == url, "brand_slug"].iloc[0]
    handle = url.rstrip("/").rsplit("/", 1)[-1]
    for raw in _read_json(data_dir / "raw" / slug / "catalog.json", []):
        if raw.get("handle") == handle:
            return {
                "source": url.rsplit("/products/", 1)[0] + "/products.json",
                "url": url,
                "title": raw.get("title"), "product_type": raw.get("product_type"),
                "tags": (raw.get("tags") or [])[:8] if isinstance(raw.get("tags"), list) else raw.get("tags"),
                "body_html": (raw.get("body_html") or "")[:700],
                "variants": [{k: v.get(k) for k in ("title", "price", "compare_at_price", "grams", "available")}
                             for v in (raw.get("variants") or [])[:3]],
            }
    return None


def export_site(df: pd.DataFrame, items: list[dict], status: list[dict], data_dir: Path, site_path: Path,
                stats: dict, sample: bool = False):
    keep = ["brand", "brand_slug", "title", "url", "category", "price_inr", "mrp_inr", "discount_pct", "size",
            "size_unit", "price_per_100", "price_position", "ingredients", "benefits", "free_from", "strengths",
            "spf", "hours", "rating", "review_count", "image", "in_stock", "days_since_launch"]
    products = json.loads(df[keep].to_json(orient="records")) if not df.empty else []
    run = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sample": sample,
        "sites_checked": len(status),
        "sites_ok": sum(s["status"] == "ok" for s in status),
        "sites_skipped": [{"name": s["name"], "reason": s["reason"]} for s in status if s["status"] != "ok"],
        "rate_limited": [s["name"] for s in status if s.get("rate_limited")],
        "catalog_products": sum(s.get("catalog_products", 0) for s in status),
        "pages_parsed": sum(s.get("pages_parsed", 0) for s in status),
        "clean_products": len(products),
        "briefs": len(items),
        "requests": stats.get("requests", 0),
        "cache_hits": stats.get("cache_hits", 0),
        "retries": stats.get("retries", 0),
    }
    _write_json(data_dir / "run.json", run)
    _write_json(site_path, {"run": run, "insights": insights(df), "products": products, "briefs": items,
                            "raw_example": raw_example(df, items, data_dir)})
    log.info("site data -> %s", site_path)
    return run

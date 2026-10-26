"""Turns raw catalog products + parsed product pages into one clean, analysis-ready table."""
from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd
from bs4 import BeautifulSoup

from . import claims

_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s?(ml|l|ltr|litre|g|gm|gms|grams?|kg|mg)\b", re.I)
_JUNK = re.compile(r"gift ?card|free gift|sample|tester|e-?gift|shipping protection|insurance|donation|voucher|coupon", re.I)
MIN_PRICE = 20   # stores list gift-with-purchase minis at Rs 1; no real D2C beauty product sells this low


def html_to_text(html: str | None) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def parse_size(*texts: str) -> tuple[float | None, str | None]:
    """First pack size found, normalised to ml or g. '1 L' -> (1000, 'ml'), '50gm' -> (50, 'g')."""
    for text in texts:
        m = _SIZE.search(text or "")
        if m:
            qty, unit = float(m.group(1)), m.group(2).lower()
            if unit in ("l", "ltr", "litre"):
                return qty * 1000, "ml"
            if unit == "kg":
                return qty * 1000, "g"
            if unit == "mg":
                return qty / 1000, "g"
            return qty, "ml" if unit == "ml" else "g"
    return None, None


def _price(value) -> float | None:
    try:
        v = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return v if v >= MIN_PRICE else None


def _ts(value) -> str | None:
    if not value:
        return None
    try:
        return pd.to_datetime(value, utc=True).isoformat()
    except (ValueError, TypeError):
        return None


def product_row(brand: dict, raw: dict, page: dict | None = None) -> dict | None:
    """One raw Shopify product -> one clean row (or None if it isn't a real sellable product)."""
    title = (raw.get("title") or "").strip()
    variants = raw.get("variants") or []
    prices = [p for p in (_price(v.get("price")) for v in variants) if p]
    if not title or not prices or _JUNK.search(title) or _JUNK.search(raw.get("product_type") or ""):
        return None

    # Price, MRP and pack size all come from the same variant: the cheapest one on sale.
    priced = [(v, _price(v.get("price"))) for v in variants]
    priced = [(v, p) for v, p in priced if p]
    in_stock = [(v, p) for v, p in priced if v.get("available", True)] or priced
    base, price = min(in_stock, key=lambda vp: vp[1])
    compare = _price(base.get("compare_at_price"))
    mrp = compare if compare and compare > price else price
    description = html_to_text(raw.get("body_html"))
    tags = raw.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    vtitle = base.get("title") if base.get("title") not in (None, "Default Title") else ""
    size, unit = parse_size(vtitle, title) if len(priced) > 1 else parse_size(vtitle, title, description)
    copy = " ".join([title, raw.get("product_type") or "", " ".join(tags), description])
    handle = raw.get("handle") or ""
    images = raw.get("images") or []
    page = page or {}

    return {
        "brand": brand["name"],
        "brand_slug": brand["slug"],
        "product_id": str(raw.get("id") or handle),
        "title": title,
        "url": f"{brand['url'].rstrip('/')}/products/{handle}",
        "category": claims.categorise(title, " ".join([raw.get("product_type") or "", " ".join(tags)])),
        "product_type": (raw.get("product_type") or "").strip() or None,
        "price_inr": round(price, 2),
        "mrp_inr": round(mrp, 2),
        "discount_pct": round((mrp - price) / mrp * 100, 1) if mrp > price else 0.0,
        "size": size,
        "size_unit": unit,
        "price_per_100": round(price / size * 100, 2) if size else None,
        "in_stock": any(bool(v.get("available", True)) for v in variants),
        "variant_count": len(variants),
        "ingredients": claims.find(claims.INGREDIENTS, copy),
        # Benefits named in the title or tags lead; then the rest found in the description.
        "benefits": list(dict.fromkeys(claims.find(claims.BENEFITS, title + " " + " ".join(tags))
                                       + claims.find(claims.BENEFITS, copy))),
        "free_from": claims.find(claims.FREE_FROM, copy),
        "strengths": claims.strengths(" ".join([title, description])),
        "spf": claims.spf(copy),
        "hours": claims.hours(copy),
        "rating": page.get("rating"),
        "review_count": page.get("review_count"),
        "rating_source": page.get("rating_source"),
        "image": (images[0].get("src") if images and isinstance(images[0], dict) else None) or page.get("image"),
        "description": description[:600],
        "tags": tags[:12],
        "created_at": _ts(raw.get("created_at") or raw.get("published_at")),
        "updated_at": _ts(raw.get("updated_at")),
    }


def build_table(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame([r for r in rows if r])
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["brand_slug", "url"]).reset_index(drop=True)
    now = datetime.now(timezone.utc)
    created = pd.to_datetime(df["created_at"], utc=True, errors="coerce")
    df["days_since_launch"] = (now - created).dt.days
    # Position each product against its category's median price per 100 ml/g across all brands.
    med = df.groupby("category")["price_per_100"].transform("median")
    ratio = df["price_per_100"] / med
    df["price_position"] = pd.cut(ratio, [0, 0.8, 1.25, float("inf")], labels=["Value", "Mid", "Premium"]).astype(str)
    df.loc[df["price_per_100"].isna(), "price_position"] = None
    return df.sort_values(["brand", "category", "title"]).reset_index(drop=True)

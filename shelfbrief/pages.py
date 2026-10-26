"""Extracts structured facts from a product page's HTML.

Order of trust: schema.org JSON-LD (what the store publishes for search engines), then review-widget
markup (Judge.me / Yotpo badges, common on Indian Shopify stores), then Open Graph meta tags.
"""
from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup


def _num(value):
    if value is None:
        return None
    m = re.search(r"\d+(?:[.,]\d+)?", str(value).replace(",", ""))
    return float(m.group()) if m else None


def _iter_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        raw = (tag.string or tag.get_text() or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Stores often ship trailing commas or raw newlines in strings; try a light repair once.
            try:
                data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw.replace("\n", " ")))
            except json.JSONDecodeError:
                continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, dict):
                if "@graph" in node:
                    stack.extend(node["@graph"] if isinstance(node["@graph"], list) else [node["@graph"]])
                yield node


def _is_product(node: dict) -> bool:
    t = node.get("@type")
    return t == "Product" or (isinstance(t, list) and "Product" in t)


def parse_product_page(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    out = {"name": None, "rating": None, "review_count": None, "price": None, "currency": None,
           "availability": None, "sku": None, "description": None, "image": None, "breadcrumbs": [],
           "rating_source": None}

    for node in _iter_jsonld(soup):
        if _is_product(node):
            out["name"] = out["name"] or node.get("name")
            out["sku"] = out["sku"] or node.get("sku")
            out["description"] = out["description"] or node.get("description")
            img = node.get("image")
            out["image"] = out["image"] or (img[0] if isinstance(img, list) and img else img if isinstance(img, str) else None)
            agg = node.get("aggregateRating") or {}
            if agg and out["rating"] is None:
                out["rating"] = _num(agg.get("ratingValue"))
                out["review_count"] = _num(agg.get("reviewCount") or agg.get("ratingCount"))
                out["rating_source"] = "json-ld"
            offers = node.get("offers")
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict) and out["price"] is None:
                out["price"] = _num(offers.get("price") or offers.get("lowPrice"))
                out["currency"] = offers.get("priceCurrency")
                av = str(offers.get("availability") or "")
                out["availability"] = av.rsplit("/", 1)[-1] or None
        elif node.get("@type") == "BreadcrumbList":
            items = sorted(node.get("itemListElement") or [], key=lambda i: i.get("position", 0))
            out["breadcrumbs"] = [i.get("name") or (i.get("item") or {}).get("name") for i in items if isinstance(i, dict)]

    if out["rating"] is None:
        badge = soup.select_one(".jdgm-prev-badge[data-average-rating]")
        if badge:
            out["rating"] = _num(badge.get("data-average-rating"))
            out["review_count"] = _num(badge.get("data-number-of-reviews"))
            out["rating_source"] = "judge.me"
    if out["rating"] is None:
        yotpo = soup.select_one(".yotpo-bottomline, .yotpo-sr-bottom-line-summary")
        if yotpo:
            text = yotpo.get_text(" ", strip=True)
            m_r = re.search(r"(\d(?:\.\d)?)\s*(?:out of 5|/ ?5|stars?)", text, re.I)
            m_n = re.search(r"([\d,]+)\s*reviews?", text, re.I)
            if m_r:
                out["rating"] = float(m_r.group(1))
                out["review_count"] = _num(m_n.group(1)) if m_n else None
                out["rating_source"] = "yotpo"

    def meta(prop):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        return tag.get("content") if tag else None

    out["name"] = out["name"] or meta("og:title") or (soup.title.get_text(strip=True) if soup.title else None)
    out["description"] = out["description"] or meta("og:description") or meta("description")
    out["image"] = out["image"] or meta("og:image")
    if out["price"] is None:
        out["price"] = _num(meta("product:price:amount") or meta("og:price:amount"))
        out["currency"] = out["currency"] or meta("product:price:currency") or meta("og:price:currency")
    if out["review_count"] is not None:
        out["review_count"] = int(out["review_count"])
    return out

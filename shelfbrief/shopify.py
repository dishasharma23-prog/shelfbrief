"""Reads a Shopify store's public product catalog (/products.json), page by page."""
from __future__ import annotations

from typing import Iterator

from .fetcher import Fetcher

PAGE_SIZE = 250  # Shopify's maximum for this endpoint


def catalog_url(base_url: str, page: int) -> str:
    return f"{base_url.rstrip('/')}/products.json?limit={PAGE_SIZE}&page={page}"


def iter_products(fetcher: Fetcher, base_url: str, max_pages: int = 20) -> Iterator[dict]:
    """Yields raw product dicts until a page comes back empty (or max_pages is reached)."""
    for page in range(1, max_pages + 1):
        data = fetcher.get_json(catalog_url(base_url, page))
        products = data.get("products") if isinstance(data, dict) else None
        if not products:
            return
        yield from products
        if len(products) < PAGE_SIZE:
            return


def product_url(base_url: str, handle: str) -> str:
    return f"{base_url.rstrip('/')}/products/{handle}"


def looks_like_shopify(fetcher: Fetcher, base_url: str) -> bool:
    """True if the store answers /products.json with a products list."""
    try:
        data = fetcher.get_json(f"{base_url.rstrip('/')}/products.json?limit=1&page=1")
    except Exception:
        return False
    return isinstance(data, dict) and isinstance(data.get("products"), list)

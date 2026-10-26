"""Command line: python -m shelfbrief {check,scrape,clean,brief,run,demo}"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import pipeline
from .fetcher import Fetcher

ROOT = Path(__file__).resolve().parent.parent
SITE_DATA = ROOT / "web" / "data" / "site.json"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="shelfbrief", description="Scrape the shelf. Write the brief.")
    ap.add_argument("command", choices=["check", "scrape", "clean", "brief", "run", "demo"])
    ap.add_argument("--config", default=str(ROOT / "brands.yaml"), help="brands file (default: brands.yaml)")
    ap.add_argument("--data-dir", default=str(ROOT / "data"))
    ap.add_argument("--brands", help="comma-separated slugs to limit the run to")
    ap.add_argument("--max-pages", type=int, default=20, help="catalog pages per brand (250 products each)")
    ap.add_argument("--enrich", type=int, default=40, help="product pages to parse per brand for ratings")
    ap.add_argument("--per-brand", type=int, default=4, help="campaign briefs per brand")
    ap.add_argument("--delay", type=float, default=1.5, help="minimum seconds between requests to one site")
    ap.add_argument("--no-llm", action="store_true", help="write briefs from rules even if GEMINI_API_KEY is set")
    ap.add_argument("--site-data", default=str(SITE_DATA), help="where to write the website's data file")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.DEBUG if a.verbose else logging.WARNING)
    data_dir = Path(a.data_dir)
    only = a.brands.split(",") if a.brands else None
    use_llm = False if a.no_llm else None

    if a.command == "demo":
        from .demo import FIXTURES, fake_web_transport
        brands = pipeline.load_brands(FIXTURES / "brands.yaml", only)
        data_dir = ROOT / "data" / "demo"
        fetcher = Fetcher(transport=fake_web_transport(), sleep=lambda s: None, delay=a.delay)
        status = pipeline.scrape(fetcher, brands, data_dir, a.max_pages, a.enrich)
        df = pipeline.clean(brands, data_dir)
        items = pipeline.brief(df, data_dir, a.per_brand, use_llm=False)
        run = pipeline.export_site(df, items, status, data_dir, Path(a.site_data), fetcher.stats, sample=True)
        print(f"\nDemo (fictional brands): {run['clean_products']} products, {run['briefs']} briefs -> {a.site_data}")
        return 0

    brands = pipeline.load_brands(Path(a.config), only)
    fetcher = Fetcher(delay=a.delay, cache_dir=data_dir / "cache")
    try:
        if a.command == "check":
            for r in pipeline.check(fetcher, brands):
                print(f"{r['name']:<26} {r['status'].upper():<8} crawl-delay {r['crawl_delay']:.1f}s  {r['reason']}")
            return 0
        if a.command in ("scrape", "run"):
            status = pipeline.scrape(fetcher, brands, data_dir, a.max_pages, a.enrich)
        else:
            status = pipeline._read_json(data_dir / "raw" / "check.json", [])
        if a.command == "scrape":
            return 0
        df = pipeline.clean(brands, data_dir)
        if a.command == "clean":
            return 0
        items = pipeline.brief(df, data_dir, a.per_brand, use_llm)
        run = pipeline.export_site(df, items, status, data_dir, Path(a.site_data), fetcher.stats)
        print(f"\n{run['sites_ok']}/{run['sites_checked']} sites scraped, {run['clean_products']} products, "
              f"{run['briefs']} briefs, {run['requests']} requests -> {a.site_data}")
        return 0
    finally:
        fetcher.close()


if __name__ == "__main__":
    sys.exit(main())

# ShelfBrief

**Live site: [dishasharma23-prog.github.io/shelfbrief](https://dishasharma23-prog.github.io/shelfbrief/)**

**Scrape the shelf. Write the brief.**

ShelfBrief is a Python pipeline that collects the public product catalogs of Indian D2C beauty and personal-care brands, parses their product pages, cleans everything into one dataset, and turns each brand's strongest products into influencer campaign briefs. A static website (three.js, GSAP, Lenis) tells the story: a curved, draggable carousel of the scraped products (each rendered once in 3D), the polite request log, one real record going from raw to clean, the price-per-100 insights and the briefs, ready to copy.

```
check  ->  crawl  ->  parse  ->  clean  ->  brief
robots.txt   /products.json   product HTML   pandas   grounded briefs
```

| Stage | What it does | Code |
|---|---|---|
| **Check** | Reads each site's `robots.txt` and tests for a public Shopify catalog. Sites that fail either check are skipped with a logged reason. | `fetcher.py`, `pipeline.check` |
| **Crawl** | Pages through `/products.json` (250 products per page). | `shopify.py` |
| **Parse** | Reads product-page HTML with BeautifulSoup: schema.org JSON-LD (rating, review count, offer), Judge.me and Yotpo review badges, Open Graph tags. Repairs common broken JSON-LD. | `pages.py` |
| **Clean** | Takes price, MRP and pack size from the same variant, so discounts and price per 100 ml/g are real. Normalises sizes (1 L -> 1000 ml), strips HTML, drops gift cards and samples, de-duplicates, extracts claims (hero ingredients with strength, benefits, free-from labels, SPF, wear hours), and positions each product against its category median. | `clean.py`, `claims.py` |
| **Brief** | Picks each brand's best-reviewed, newest and most claim-rich products and writes a campaign brief: positioning, audience, creator niches, three opening hooks, formats, proof points and ASCI-aware guardrails. Proof points are only claims found on the brand's own page. | `briefs.py` |

Outputs land in `data/`: `products.csv`, `products.json`, `shelf.sqlite`, `briefs.json`, `run.json`, plus `web/data/site.json` for the website.

## Quick start (Windows PowerShell)

```powershell
cd shelfbrief
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python -m pytest -q              # 21 tests, all offline
python -m shelfbrief demo        # full pipeline on fictional test stores, no internet needed
python -m shelfbrief check       # which real brands allow it (robots.txt + public catalog)
python -m shelfbrief run         # scrape, clean and brief the real brands in brands.yaml
```

On macOS or Linux, activate with `source .venv/bin/activate`.

View the site:

```powershell
cd web
python -m http.server 8000
```

Then open http://localhost:8000.

### Useful options

```powershell
python -m shelfbrief run --brands minimalist,plum   # only some brands
python -m shelfbrief run --enrich 20                # parse 20 product pages per brand (default 40)
python -m shelfbrief run --delay 3                  # slower: 3 s between requests to one site
python -m shelfbrief run --no-llm                   # rule-based briefs even if a key is set
```

### Optional: AI-written briefs

Set `GEMINI_API_KEY` and the creative parts of each brief (positioning, audience, niches, hooks, formats) are written by Gemini from the same scraped facts. Its output is checked: a hook that mentions a percentage or SPF value that isn't on the product page is thrown away, and the brief falls back to the rule-based version.

```powershell
$env:GEMINI_API_KEY = "your-key"
python -m shelfbrief run
```

## Built to be a good guest

- Every URL is checked against `robots.txt` before it is requested, with a parser that follows RFC 9309 (wildcards, `$` anchors, most-specific rule wins). Python's built-in parser ignores wildcards, and Shopify's default robots.txt is full of them.
- At least 1.5 s between requests to one site, longer if the site sets `Crawl-delay`.
- Retries only on 429 and 5xx, with exponential backoff, honouring `Retry-After`. Never retries a 404.
- Stops asking: if a store still answers `429` on two product pages in a row after all retries, the rest of its product pages are skipped for that run.
- Identifies itself as `ShelfBriefBot/1.0` with a link to this repo.
- Caches responses for six hours, so re-runs during development don't hit the store again.
- Reads only public catalog and product pages: no logins, no checkout, no customer reviews or personal data.

`brands.yaml` is a list of candidates. Run `check` first and respect what it reports; set `enabled: false` for any brand you don't want to crawl, and read a site's terms before you publish data from it.

## Automation

`.github/workflows/pages.yml` runs the tests and publishes `web/` to GitHub Pages on every push to `main`.

`.github/workflows/scrape.yml` runs every Monday at 08:47 IST: it runs the tests, scrapes, cleans, writes briefs and commits the new data, which then triggers a fresh publish. If a run comes back thin (stores often rate-limit cloud IPs), it keeps last week's data rather than replacing it. You can also start it from the **Actions** tab.

To turn it on after pushing the repo:
1. **Settings -> Pages -> Source:** GitHub Actions.
2. Optional: **Settings -> Secrets and variables -> Actions -> New secret** named `GEMINI_API_KEY`.

## Project layout

```
shelfbrief/
  fetcher.py     polite HTTP client: rate limit, retries, cache
  robots.py      robots.txt rules per RFC 9309
  shopify.py     catalog pagination
  pages.py       product-page HTML parsing (JSON-LD, review badges, Open Graph)
  claims.py      category, ingredient, benefit and free-from vocabulary
  clean.py       raw products -> one clean pandas table
  briefs.py      campaign briefs (rules, or Gemini with grounding checks)
  pipeline.py    the five stages and the exports
  demo.py        serves the fixture web for offline runs
tests/           pytest suite + fixtures/ (a small fake web of fictional brands)
web/             the static site: index.html, style.css, app.js (sections, charts, scroll story), scene.js (renders each product once in 3D for the carousel), data/site.json
brands.yaml      the brands to scrape
```

`python web/build_single.py` bundles the site, data included, into one HTML file in `dist/`.

---

Built by Disha Sharma.

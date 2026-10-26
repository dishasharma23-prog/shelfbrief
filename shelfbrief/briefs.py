"""Writes influencer campaign briefs from the cleaned product table.

Every brief is grounded: proof points are only claims found on the brand's own product page.
Without an API key the briefs come from rules below; with GEMINI_API_KEY set, Gemini rewrites the
creative parts (positioning, audience, niches, hooks, formats) from the same facts, and its output is
checked so it cannot add strength or SPF numbers that aren't on the page.
"""
from __future__ import annotations

import json
import math
import os
import re

import httpx
import pandas as pd

AUDIENCE_BY_BENEFIT = {
    "Acne & Blemishes": "Teens and 20-somethings with oily, acne-prone skin",
    "Oil Control": "Oily-skin users in humid cities",
    "Brightening": "Skincare beginners after an even, glowing look",
    "Pigmentation & Dark Spots": "People dealing with tanning, dark spots or uneven tone",
    "Hydration": "Dry or dehydrated skin, long hours in air-conditioning",
    "Anti-Ageing": "25-40s starting a preventive routine",
    "Sun Protection": "Daily commuters and outdoor-heavy routines",
    "Hair Fall": "People worried about hair fall and thinning",
    "Dandruff": "People with flaky, itchy scalps",
    "Barrier Repair": "Sensitive or over-exfoliated skin",
}

AUDIENCE_BY_CATEGORY = {
    "Fragrance": ["Young professionals building a signature scent", "Festive and gifting shoppers"],
    "Beard & Shaving": ["Men building a first grooming routine", "Bearded men who want a neater look"],
    "Hair Styling": ["Men and women who style daily", "College students"],
    "Lip Makeup": ["Everyday makeup wearers", "Shoppers who love trying new shades"],
    "Face Makeup": ["Makeup wearers who need all-day wear", "Bridal and occasion shoppers"],
    "Kits & Combos": ["Gifting shoppers", "Beginners who want a ready routine"],
}

BENEFIT_PHRASE = {
    "Acne & Blemishes": "acne-prone skin", "Oil Control": "oily skin", "Brightening": "a brighter glow",
    "Hydration": "hydration", "Anti-Ageing": "early signs of ageing", "Sun Protection": "daily sun protection",
    "Pigmentation & Dark Spots": "dark spots and uneven tone", "Hair Fall": "hair fall", "Dandruff": "dandruff",
    "Barrier Repair": "sensitive skin", "Long-Lasting": "all-day wear",
}

PRODUCT_NOUNS = ["eau de parfum", "face wash", "face oil", "face pack", "face mask", "hair oil", "beard oil", "beard wash",
                 "scalp serum", "night cream", "eye cream", "gel cream", "body lotion", "body spray", "lip balm",
                 "sunscreen", "serum", "toner", "moisturiser", "moisturizer", "cleanser", "shampoo", "conditioner",
                 "perfume", "lotion", "soap", "gel", "cream", "oil", "kit", "wax", "balm", "mist", "spray"]


def product_noun(title: str, category: str) -> str:
    low = title.lower()
    for n in PRODUCT_NOUNS:
        if re.search(r"\b" + n + r"\b", low):
            if n == "oil" and category == "Beard & Shaving":
                return "beard oil"
            if n == "oil" and category.startswith("Hair"):
                return "hair oil"
            return "fragrance" if n == "eau de parfum" else n
    return category.lower()


def possessive(name: str) -> str:
    return name + ("'" if name.endswith("s") else "'s")


NICHES_BY_CATEGORY = {
    "Serum & Face Oil": ["Ingredient-explainer skinfluencers", "Dermatologist creators", "Routine-diary creators"],
    "Sunscreen": ["Skincare educators", "Travel & outdoor creators", "Fitness creators"],
    "Face Wash": ["Skincare educators", "College & hostel-life creators", "Men's grooming creators"],
    "Moisturiser": ["Skincare educators", "Minimal-routine creators", "Makeup artists (prep step)"],
    "Toner & Mist": ["Skincare educators", "Travel creators", "Self-care creators"],
    "Face Makeup": ["Makeup artists", "GRWM creators", "Bridal & occasion creators"],
    "Lip Makeup": ["Makeup & swatch creators", "GRWM creators", "Fashion creators"],
    "Eye & Lip Care": ["Skincare educators", "Work-from-home lifestyle creators"],
    "Shampoo & Conditioner": ["Haircare creators", "Curly-hair community", "Wash-day vloggers"],
    "Hair Oil & Serum": ["Haircare creators", "Ayurveda & wellness creators", "Routine-diary creators"],
    "Beard & Shaving": ["Men's grooming creators", "Fitness creators", "Office-wear creators"],
    "Body Care": ["Lifestyle vloggers", "Self-care creators", "ASMR creators"],
    "Fragrance": ["Fragrance reviewers", "Fashion & lifestyle creators"],
    "Face Mask & Scrub": ["Self-care Sunday creators", "Skincare educators"],
    "Kits & Combos": ["Gifting & festive-haul creators", "Routine-builder creators"],
}

FORMATS_BY_CATEGORY = {
    "Serum & Face Oil": ["28-day routine diary, same light and angle each week", "30-second ingredient explainer", "Where it goes in an AM/PM layering routine"],
    "Sunscreen": ["White-cast and finish test across skin tones", "Midday reapplication over makeup", "Full commute-day wear test"],
    "Face Wash": ["Texture close-up and after-wash skin feel", "Double-cleanse routine", "Oily-skin check-ins through the day"],
    "Moisturiser": ["Texture swatch with an absorption timer", "Under-makeup wear test", "Night routine reel"],
    "Toner & Mist": ["Morning routine POV", "Desk refresh mid-workday", "Travel kit packing"],
    "Face Makeup": ["9-to-9 wear test", "Shade match across skin tones", "GRWM"],
    "Lip Makeup": ["All-shade lip swatches", "Transfer test (mask, cup, kiss-off)", "GRWM"],
    "Eye & Lip Care": ["Night routine close-up", "Week-long check-in"],
    "Shampoo & Conditioner": ["Wash-day routine", "Ingredient explainer", "Week-long hair-feel check-ins"],
    "Hair Oil & Serum": ["8-week scalp diary", "Champi routine reel", "Myth vs fact on hair growth"],
    "Beard & Shaving": ["Grooming routine POV", "Office-ready in 5 minutes", "Before/after trim"],
    "Body Care": ["Shower routine ASMR", "Texture and scent first impressions", "Weekly self-care reset"],
    "Fragrance": ["Describe the scent before showing the bottle", "Longevity check across a day", "Occasion pairing"],
    "Face Mask & Scrub": ["Self-care Sunday routine", "Texture and after-feel close-ups"],
    "Kits & Combos": ["Unboxing and gifting idea", "Full routine using only the kit", "Festive haul"],
}
DEFAULT_NICHES = ["Lifestyle creators", "Honest-review creators"]
DEFAULT_FORMATS = ["Honest first impressions", "Routine integration", "Day-in-the-life"]
ACTIVES = {"Retinol", "Salicylic Acid", "Glycolic Acid", "Lactic Acid", "AHA", "Azelaic Acid", "Kojic Acid"}


def _clean_list(value) -> list:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    return list(value)


def _num(value):
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else value


def facts(p: dict) -> dict:
    """The only facts a brief may lean on, all taken from the product page."""
    return {
        "brand": p["brand"], "title": p["title"], "category": p["category"], "url": p["url"],
        "price_inr": p["price_inr"], "mrp_inr": p["mrp_inr"], "discount_pct": p["discount_pct"],
        "size": _num(p.get("size")), "size_unit": p.get("size_unit"),
        "price_position": p.get("price_position"),
        "ingredients": _clean_list(p.get("ingredients")), "benefits": _clean_list(p.get("benefits")),
        "free_from": _clean_list(p.get("free_from")), "strengths": _clean_list(p.get("strengths")),
        "spf": _num(p.get("spf")), "hours": _clean_list(p.get("hours")), "rating": _num(p.get("rating")), "review_count": _num(p.get("review_count")),
    }


def proof_points(f: dict) -> list[str]:
    pts = list(f["strengths"])
    if f["spf"]:
        pts.append(f"SPF {int(f['spf'])}")
    pts += [i for i in f["ingredients"] if not any(i.lower() in s.lower() for s in f["strengths"])][:3]
    pts += f["free_from"][:3]
    pts += [f"{h}-hour claim on the product page" for h in f.get("hours", [])[:1]]
    if f["rating"] and f["review_count"]:
        pts.append(f"Rated {f['rating']:.1f}/5 from {int(f['review_count']):,} reviews on the brand site")
    return pts[:7]


def guardrails(f: dict) -> list[str]:
    g = ["Disclose the paid partnership upfront (#ad / #collab), as ASCI's influencer guidelines require.",
         "Only use the proof points listed here; they are the claims printed on the product page."]
    if {"Acne & Blemishes", "Hair Fall", "Pigmentation & Dark Spots", "Dandruff"} & set(f["benefits"]):
        g.append("No treatment language ('cures acne', 'stops hair fall'); present results as personal experience.")
    if f["category"] == "Sunscreen" or f["spf"]:
        g.append("Show a realistic amount and mention reapplying through the day.")
    if ACTIVES & set(f["ingredients"]):
        g.append("Mention a patch test and gradual introduction, since this contains an active acid or retinoid.")
    return g


def rule_brief(f: dict) -> dict:
    hooks = []
    if f["strengths"]:
        hooks.append(f"{f['strengths'][0]}, every day for four weeks. Here's my honest diary.")
    if f["spf"]:
        hooks.append(f"Does this SPF {int(f['spf'])} pass the white-cast test? Let's find out outdoors.")
    if f["ingredients"] and len(hooks) < 3:
        hooks.append(f"What {f['ingredients'][0]} actually does, in 30 seconds.")
    if f["rating"] and f["review_count"] and f["review_count"] >= 50 and len(hooks) < 3:
        hooks.append(f"{int(f['review_count']):,} people rated this {f['rating']:.1f}/5. I tried it to see why.")
    if f["discount_pct"] >= 20 and len(hooks) < 3:
        hooks.append(f"₹{f['price_inr']:,.0f} instead of ₹{f['mrp_inr']:,.0f}: worth it?")
    if f["free_from"] and len(hooks) < 3:
        hooks.append(f"{f['free_from'][0]} and still effective? My honest take.")
    if len(hooks) < 2:
        hooks.append(f"The {f['category'].lower()} I'd hand a friend who's just starting out.")

    audience = (AUDIENCE_BY_CATEGORY.get(f["category"])
                or [AUDIENCE_BY_BENEFIT[b] for b in f["benefits"] if b in AUDIENCE_BY_BENEFIT][:3]
                or ["Broad beauty and personal-care shoppers"])
    size = f" ({f['size']:g} {f['size_unit']})" if f["size"] else ""
    lead = f["strengths"][0] if f["strengths"] else (f["ingredients"][0] if f["ingredients"] else None)
    noun = product_noun(f["title"], f["category"])
    what = f"{lead} {noun}" if lead and lead.lower() not in noun else noun
    focus = f" for {BENEFIT_PHRASE[f['benefits'][0]]}" if f["benefits"] and f["benefits"][0] in BENEFIT_PHRASE else ""
    pos = f", {f['price_position'].lower()}-priced for its category" if f["price_position"] in ("Value", "Mid", "Premium") else ""
    return {
        "one_liner": f"{possessive(f['brand'])} ₹{f['price_inr']:,.0f}{size} {what}{focus}{pos}.",
        "audience": audience,
        "creator_niches": NICHES_BY_CATEGORY.get(f["category"], DEFAULT_NICHES),
        "hooks": hooks[:3],
        "formats": FORMATS_BY_CATEGORY.get(f["category"], DEFAULT_FORMATS),
    }


GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PROMPT = """You write influencer campaign briefs for an Indian creator-marketing agency.
Use ONLY the facts in this JSON. Never invent percentages, SPF values, ratings, awards or results.
Return JSON with keys: one_liner (string, max 25 words), audience (2-3 strings), creator_niches (3 strings),
hooks (3 short spoken opening lines for a Reel, max 16 words each), formats (3 content format ideas).

FACTS:
{facts}"""


def _grounded(text: str, f: dict) -> bool:
    """Rejects LLM text that mentions a % or SPF number not present in the facts."""
    allowed = " ".join(f["strengths"]) + f" SPF {f['spf']}" if f["spf"] else " ".join(f["strengths"])
    for num in re.findall(r"(\d+(?:\.\d+)?)\s*%", text):
        if f"{num}%" not in allowed.replace(" %", "%"):
            return False
    for num in re.findall(r"spf\s*(\d+)", text, re.I):
        if not f["spf"] or int(num) != int(f["spf"]):
            return False
    return True


def llm_brief(f: dict, api_key: str, model: str, client: httpx.Client | None = None) -> dict | None:
    client = client or httpx.Client(timeout=40)
    body = {"contents": [{"parts": [{"text": PROMPT.format(facts=json.dumps(f, ensure_ascii=False))}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.7}}
    try:
        r = client.post(GEMINI_URL.format(model=model), params={"key": api_key}, json=body)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
    except (httpx.HTTPError, KeyError, IndexError, json.JSONDecodeError):
        return None
    need = {"one_liner": str, "audience": list, "creator_niches": list, "hooks": list, "formats": list}
    if not all(isinstance(out.get(k), t) for k, t in need.items()):
        return None
    out["hooks"] = [h for h in out["hooks"] if isinstance(h, str) and _grounded(h, f)][:3]
    if not _grounded(out["one_liner"], f) or not out["hooks"]:
        return None
    return {k: out[k] if k == "one_liner" else [str(x) for x in out[k]][:3] for k in need}


def pick_products(df: pd.DataFrame, per_brand: int = 4) -> pd.DataFrame:
    """Best candidates per brand: well-reviewed, recently launched, with concrete claims; no kits."""
    d = df[(df["category"] != "Kits & Combos") & df["in_stock"]].copy()
    if d.empty:
        return d
    reviews = d["review_count"].fillna(0).astype(float)
    rating = d["rating"].fillna(0).astype(float)
    fresh = (d["days_since_launch"].fillna(9999) < 120).astype(float)
    claims_n = d["strengths"].map(len) + d["ingredients"].map(len) + d["benefits"].map(len)
    d["_score"] = reviews.map(lambda n: math.log1p(n)) * (rating / 5) + fresh * 2 + claims_n.clip(upper=5) * 0.4
    d = d.sort_values("_score", ascending=False)
    picked = d.groupby("brand_slug", sort=False).head(per_brand)
    # Prefer variety: at most two per category within a brand.
    picked = picked.groupby(["brand_slug", "category"], sort=False).head(2)
    return picked.drop(columns="_score")


def write_briefs(df: pd.DataFrame, per_brand: int = 4, use_llm: bool | None = None) -> list[dict]:
    api_key = os.environ.get("GEMINI_API_KEY")
    model = os.environ.get("SHELFBRIEF_MODEL", "gemini-2.0-flash")
    use_llm = bool(api_key) if use_llm is None else (use_llm and bool(api_key))
    client = httpx.Client(timeout=40) if use_llm else None
    briefs = []
    for p in pick_products(df, per_brand).to_dict("records"):
        f = facts(p)
        creative = (llm_brief(f, api_key, model, client) if use_llm else None)
        source = "gemini" if creative else "rules"
        creative = creative or rule_brief(f)
        briefs.append({"product": f, **creative, "proof_points": proof_points(f),
                       "guardrails": guardrails(f), "written_by": source})
    return briefs

"""Vocabulary for turning product copy into structured facts: category, hero ingredients, benefits, free-from claims."""
from __future__ import annotations

import re

# Ordered: the first matching category wins, so specific ones come before generic ones.
CATEGORIES = [
    ("Kits & Combos", r"\b(kit|combo|bundle|regime|gift set|duo|trio)\b|\bset of\b"),
    ("Hair Oil & Serum", r"\b(hair oil|hair serum|hair growth|scalp)\b"),
    ("Shampoo & Conditioner", r"\b(shampoo|conditioner|hair mask)\b"),
    ("Beard & Shaving", r"\b(beard|shaving|shave|razor|trimmer|after ?shave)\b"),
    ("Lip Makeup", r"\b(lipstick|lip ?gloss|lip tint|lip crayon|lip liner)\b"),
    ("Eye & Lip Care", r"\b(eye cream|under ?eye|lip balm|lip mask|lip scrub)\b"),
    ("Fragrance", r"\b(perfume|eau de|edp|edt|fragrance|body mist)\b"),
    ("Sunscreen", r"\b(sunscreen|sun screen|spf ?\d+|sunblock|sun gel|sun stick)\b"),
    ("Hair Styling", r"\b(hair wax|pomade|hair gel|hair spray|styling)\b"),
    ("Serum & Face Oil", r"\b(serum|ampoule|essence|booster|face oil)\b"),
    ("Face Wash", r"\b(face ?wash|cleanser|cleansing gel|foaming wash)\b"),
    ("Toner & Mist", r"\b(toner|mist)\b"),
    ("Moisturiser", r"\b(moisturi[sz]er|moisturi[sz]ing cream|face cream|gel cream|night cream|day cream)\b"),
    ("Face Makeup", r"\b(foundation|concealer|compact|primer|blush|highlighter|bb cream|cc cream|kajal|eyeliner|mascara)\b"),
    ("Body Care", r"\b(body lotion|body wash|shower gel|body butter|body scrub|soap|deodorant|deo)\b"),
    ("Face Mask & Scrub", r"\b(face mask|face pack|sheet mask|clay mask|face scrub|exfoliat\w*|peel)\b"),
]

INGREDIENTS = {
    "Niacinamide": r"niacinamide",
    "Vitamin C": r"vitamin ?c\b|ascorbic|ethyl ascorbic",
    "Hyaluronic Acid": r"hyaluronic|sodium hyaluronate",
    "Salicylic Acid": r"salicylic|\bbha\b",
    "Glycolic Acid": r"glycolic",
    "Lactic Acid": r"lactic acid",
    "AHA": r"\baha\b",
    "Retinol": r"retinol|retinal\b|retinoid",
    "Bakuchiol": r"bakuchiol",
    "Ceramides": r"ceramide",
    "Peptides": r"peptide",
    "Alpha Arbutin": r"alpha ?arbutin",
    "Kojic Acid": r"kojic",
    "Azelaic Acid": r"azelaic",
    "Centella / Cica": r"centella|\bcica\b",
    "Tea Tree": r"tea ?tree",
    "Rosemary": r"rosemary",
    "Onion": r"\bonion\b",
    "Rice Water": r"rice water",
    "Kumkumadi": r"kumkumadi",
    "Saffron": r"saffron|kesar",
    "Aloe Vera": r"aloe",
    "Squalane": r"squalane",
    "Caffeine": r"caffeine|coffee",
    "Zinc": r"\bzinc\b",
}

BENEFITS = {
    "Brightening": r"brighten|glow|radian|luminous|dull",
    "Acne & Blemishes": r"\bacne\b|breakout|blemish|pimple",
    "Oil Control": r"oil control|oily skin|sebum|mattif",
    "Hydration": r"hydrat|moistur|dryness|plump",
    "Anti-Ageing": r"anti[- ]?ag|fine lines|wrinkle|firm",
    "Sun Protection": r"\bspf\b|uva|uvb|sun protection|pa\+",
    "Pigmentation & Dark Spots": r"pigment|dark spot|\btan\b|de-?tan|uneven tone",
    "Hair Fall": r"hair ?fall|hair loss|thinning",
    "Dandruff": r"dandruff|flak",
    "Barrier Repair": r"barrier|repair|sooth|calm|redness|sensitive",
    "Long-Lasting": r"long[- ]?lasting|\d+ ?h(ou)?rs?\b|transfer[- ]?proof|smudge[- ]?proof",
}

FREE_FROM = {
    "Fragrance-Free": r"fragrance[- ]free|no fragrance|unscented",
    "Paraben-Free": r"paraben[- ]free|no parabens?",
    "Sulphate-Free": r"sulph?ate[- ]free|no sulph?ates?",
    "Silicone-Free": r"silicone[- ]free",
    "Vegan": r"\bvegan\b",
    "Cruelty-Free": r"cruelty[- ]free|not tested on animals",
    "Dermatologically Tested": r"dermatolog(ist|ically) (tested|approved)",
    "Non-Comedogenic": r"non[- ]comedogenic",
    "Ayurvedic": r"ayurved",
}

_SPF = re.compile(r"\bspf ?(\d{2,3})\b", re.I)


_NOT_A_TYPE = re.compile(r"(fragrance|paraben|sulph?ate|silicone|alcohol|oil)[- ]free", re.I)


def categorise(*texts: str) -> str:
    """First category matched, trying each text in order: the title beats product type and tags,
    which stores fill with whole-catalog labels (a shampoo tagged 'hair growth', a cream tagged 'kit')."""
    for text in texts:
        low = _NOT_A_TYPE.sub(" ", (text or "").lower())
        for name, pattern in CATEGORIES:
            if re.search(pattern, low):
                return name
    return "Other"


def find(vocab: dict, text: str) -> list[str]:
    low = text.lower()
    return [name for name, pattern in vocab.items() if re.search(pattern, low)]


def spf(text: str) -> int | None:
    m = _SPF.search(text)
    return int(m.group(1)) if m else None


def strengths(text: str) -> list[str]:
    """Percent strengths tied to a known ingredient, e.g. '10% Niacinamide' or 'Retinol 0.3%' -> '0.3% Retinol'."""
    found = []
    for name, pattern in INGREDIENTS.items():
        before = re.compile(r"(\d{1,2}(?:\.\d+)?)\s?%\s?(?:(?!(?:off|on|upto|up|to|discount|cashback|flat|extra|sale)\b)[a-z\-]+\s){0,2}?(?:" + pattern + ")", re.I)
        after = re.compile(r"(?:" + pattern + r")\s?(\d{1,2}(?:\.\d+)?)\s?%", re.I)
        for rx in (before, after):
            for m in rx.finditer(text):
                found.append((m.start(), f"{m.group(1)}% {name}"))
    found.sort()
    return list(dict.fromkeys(s for _, s in found))[:4]


_HOURS = re.compile(r"\b(\d{1,2})[- ]?(?:hours?|hrs?)\b", re.I)


def hours(text: str) -> list[int]:
    """Wear or effect durations written on the product, e.g. 'up to 8 hours', '24-hour hydration'."""
    return sorted({int(h) for h in _HOURS.findall(text) if 1 < int(h) <= 72}, reverse=True)

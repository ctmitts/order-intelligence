"""
Single source of truth for the demo's (fictional) branding and product catalog.

The underlying project was built for a real client. For this public-facing
demo we do two things to protect the client:

1. Genericize the organization name (ORG_NAME below).
2. Map every order line into a clean, fictional product catalog and *generate*
   the product description from that catalog — we never copy the real
   descriptions through, so no product/ingredient signal can leak, no matter
   how messy the source OCR was.

Change ORG_NAME / the catalog here and it propagates to the UI, the data
pipeline, and the docs.
"""

import os
import re

# --- Fictional organization -------------------------------------------------
ORG_NAME = "Wandering Roots Collective"
ORG_SHORT = "Wandering Roots"
TAGLINE = "Small-batch botanical wellness, shipped to members"

# Real-client tokens to scrub from a raw export are supplied privately via the
# ANON_SCRUB_TOKENS env var (comma-separated) — never hard-coded in the repo.
ORG_SCRUB_TOKENS = [t.strip() for t in os.environ.get("ANON_SCRUB_TOKENS", "").split(",") if t.strip()]

# --- Canonical (fictional) product catalog ----------------------------------
# Every order line is classified into one of these categories; the description
# is generated, never carried over from the source data.
CATALOG = {
    "CARM": {"category": "Caramels", "name": "Signature Caramels"},
    "GUMM": {"category": "Gummies", "name": "Botanical Gummies"},
    "CHOC": {"category": "Chocolate", "name": "Dark Chocolate Bar"},
    "SAMP": {"category": "Sampler", "name": "Sampler Pack"},
    "ASST": {"category": "Assorted", "name": "Assorted Selection"},
}
TIER_LABEL = {"1": "1-Pack", "3": "3-Pack", "5": "5-Pack"}


def _classify(raw_code: str, raw_desc: str) -> str:
    """Bucket a (possibly garbled OCR) code/description into a catalog key.

    Checked in priority order; keyword membership is deliberately loose so it
    absorbs the long tail of OCR variants (CARA, GUMMIE, CHOCH, HBAR, ...).
    """
    s = f"{raw_code} {raw_desc}".upper()
    if "SAMP" in s or "SAMPLE" in s or "SMPL" in s or "SIMPLER" in s:
        return "SAMP"
    if "CAR" in s or "CRAV" in s:
        return "CARM"
    if "GUM" in s or "GALACTIC" in s or "GLM" in s or s.startswith("MG"):
        return "GUMM"
    if any(k in s for k in ("CHO", "BAR", "HERO", "HERB", "HBAR", "MUSH", "MMB", "MMC")):
        return "CHOC"
    return "ASST"


def _tier(raw_code: str) -> str:
    """Extract a 1/3/5 pack tier from the code, defaulting to 1."""
    m = re.search(r"-(\d)(?:\D|$)", raw_code or "")
    if m and m.group(1) in "135":
        return m.group(1)
    m2 = re.search(r"(\d)\s*$", raw_code or "")
    if m2 and m2.group(1) in "135":
        return m2.group(1)
    return "1"


def canonical_product(raw_code: str, raw_desc: str) -> tuple:
    """Return (clean_code, generated_description, category) for one line."""
    cat = _classify(raw_code or "", raw_desc or "")
    if cat == "SAMP":
        return "SAMP", CATALOG["SAMP"]["name"], CATALOG["SAMP"]["category"]
    if cat == "ASST":
        return "ASST", CATALOG["ASST"]["name"], CATALOG["ASST"]["category"]
    tier = _tier(raw_code)
    code = f"{cat}-{tier}"
    desc = f"{CATALOG[cat]['name']} — {TIER_LABEL[tier]}"
    return code, desc, CATALOG[cat]["category"]


def category_of(code: str) -> str:
    """Map a (already-canonical) product code back to its category label."""
    prefix = (code or "").split("-")[0]
    return CATALOG.get(prefix, {}).get("category", "Other")

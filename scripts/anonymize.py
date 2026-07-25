#!/usr/bin/env python3
"""
Anonymize the order export for public/demo use.

Design goals, in priority order:

1. NON-REVERSIBLE. Fake identities are assigned by random draw, not derived
   from the real name via a public hash. There is deliberately no function
   fake = f(real_name) that anyone can recompute. This defeats membership
   inference: for a membership organization, *membership itself* can be the sensitive fact,
   so no one with this script should be able to test "does <real person>
   appear in the data?".

2. CONSISTENT PER CUSTOMER. Each real customer maps to exactly one fake
   identity, so repeat-buyer counts, lifetime value, and product-loyalty
   analytics are identical on the anonymized data.

3. NO SILENT MERGES. Fake names are guaranteed unique across customers. The
   app groups analytics by Customer_Name, so two real customers sharing a
   fake name would corrupt the very patterns we preserve.

What is replaced : Customer_Name, Email, street address (Line1), Line2 dropped.
What is coarsened: Zip truncated to 3-digit prefix (HIPAA safe-harbor style).
What is preserved: products, prices, dates, city, state, order structure.

The real->fake mapping is written to a PRIVATE file (gitignored) so you can
audit it or honor a deletion request. It must never be committed.

Usage:
    python3 anonymize.py [input.csv] [output.csv]
"""

import csv
import os
import secrets
import sys

# Import shared branding/genericization config from the app package.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app"))
from branding import ORG_SCRUB_TOKENS, canonical_product  # noqa: E402

# The public schema: the 22 order columns. Any extra columns in the source
# (standardization audit fields, etc.) are dropped.
CANONICAL_COLUMNS = [
    "Order_Number", "Date", "Customer_Name", "Email", "Ship_Date",
    "Shipping_Address_Line1", "Shipping_Address_Line2", "Shipping_City",
    "Shipping_State", "Shipping_Zip", "Product_Code", "Product_Description",
    "Unit_Price", "Quantity", "Extended_Price", "Service_Fee", "Total_Discount",
    "Sub_Total", "Shipping", "Total_Amount", "Source_File", "Source_Page",
]

FIRST_NAMES = [
    "Avery", "Blake", "Cameron", "Dakota", "Elliot", "Finley", "Gray", "Harper",
    "Indigo", "Jordan", "Kai", "Logan", "Marlowe", "Nova", "Oakley", "Parker",
    "Quinn", "Reese", "Sage", "Tatum", "Umi", "Val", "Wren", "Xen", "Yael", "Zion",
    "Amara", "Bennett", "Colette", "Dominic", "Esme", "Felix", "Greta", "Hugo",
    "Isla", "Julian", "Keira", "Leon", "Mira", "Nolan", "Odette", "Priya",
    "Rafael", "Simone", "Theo", "Uma", "Vince", "Willa", "Xavier", "Yara", "Zara",
]
LAST_NAMES = [
    "Ainsworth", "Barlow", "Castellano", "Delgado", "Emerson", "Fontaine",
    "Guerrero", "Hollis", "Iverson", "Jennings", "Kowalski", "Larkin", "Mercer",
    "Nakamura", "Okafor", "Pruitt", "Quintero", "Ramsey", "Sinclair", "Thorne",
    "Underwood", "Vasquez", "Whitfield", "Xu", "Yates", "Zimmerman", "Abbott",
    "Bianchi", "Cho", "Donovan", "Escobar", "Farrell", "Ghosh", "Haddad",
]
STREET_NAMES = [
    "Maple", "Cedar", "Birch", "Willow", "Chestnut", "Sycamore", "Aspen",
    "Juniper", "Magnolia", "Laurel", "Poplar", "Hawthorn", "Linden", "Cypress",
    "Sequoia", "Redwood", "Alder", "Hemlock", "Dogwood", "Spruce",
]
STREET_TYPES = ["St", "Ave", "Rd", "Ln", "Dr", "Way", "Ct", "Pl", "Ter", "Blvd"]
MIDDLE_INITIALS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "proton.me"]

# Cryptographically-seeded RNG. A fresh, unrecorded seed each run means the
# assignment cannot be reproduced from the committed script — that is the point.
_rng = secrets.SystemRandom()


def genericize_row(row: dict) -> None:
    """De-identify the *organization*: normalize product codes/names and scrub
    any real-org tokens from every cell. This protects the client, separate
    from the customer-PII anonymization above."""
    # Map to the canonical catalog and GENERATE the description from scratch —
    # the real code/description are never carried through, so no product or
    # ingredient signal can leak regardless of how garbled the OCR was.
    code, desc, _category = canonical_product(
        row.get("Product_Code"), row.get("Product_Description")
    )
    row["Product_Code"] = code
    row["Product_Description"] = desc

    # Blanket scrub of real-org tokens across all string cells (catches
    # provenance filenames like "<Company> - Adobe Scan ...").
    for k, v in row.items():
        if isinstance(v, str):
            for token in ORG_SCRUB_TOKENS:
                if token in v:
                    v = v.replace(token, "sample-scan")
            row[k] = v


def truncate_zip(zip_value: str) -> str:
    """Keep the 3-digit geographic prefix; drop the pinpoint digits."""
    digits = "".join(ch for ch in (zip_value or "") if ch.isdigit())
    return digits[:3]


def make_unique_identity(used_names: set, used_emails: set) -> dict:
    """Draw a synthetic identity, guaranteeing a globally-unique display name."""
    first = _rng.choice(FIRST_NAMES)
    last = _rng.choice(LAST_NAMES)

    # Guarantee a unique full name: bare, then add a middle initial, then a
    # numeric suffix as a last resort. The app groups by Customer_Name, so a
    # duplicate name would silently merge two real customers.
    name = f"{first} {last}"
    if name in used_names:
        for mid in _rng.sample(MIDDLE_INITIALS, len(MIDDLE_INITIALS)):
            candidate = f"{first} {mid}. {last}"
            if candidate not in used_names:
                name = candidate
                break
        else:
            suffix = 2
            while f"{first} {last} ({suffix})" in used_names:
                suffix += 1
            name = f"{first} {last} ({suffix})"
    used_names.add(name)

    # Unique email, independent of the display name's collision handling.
    while True:
        num = _rng.randint(10, 9999)
        email = f"{first.lower()}.{last.lower()}{num}@{_rng.choice(EMAIL_DOMAINS)}"
        if email not in used_emails:
            used_emails.add(email)
            break

    house = _rng.randint(100, 9899)
    line1 = f"{house} {_rng.choice(STREET_NAMES)} {_rng.choice(STREET_TYPES)}"
    return {"name": name, "email": email, "line1": line1}


def anonymize(in_path: str, out_path: str) -> None:
    with open(in_path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    mapping: dict[str, dict] = {}  # real_name (lower) -> identity
    used_names: set[str] = set()
    used_emails: set[str] = set()

    for row in rows:
        key = (row.get("Customer_Name") or "").strip().lower()
        if key not in mapping:
            mapping[key] = make_unique_identity(used_names, used_emails)
        ident = mapping[key]

        if "Customer_Name" in row:
            row["Customer_Name"] = ident["name"]
        if "Email" in row and (row.get("Email") or "").strip():
            row["Email"] = ident["email"]
        if "Shipping_Address_Line1" in row and (row.get("Shipping_Address_Line1") or "").strip():
            row["Shipping_Address_Line1"] = ident["line1"]
        if "Shipping_Address_Line2" in row:
            row["Shipping_Address_Line2"] = ""  # apt/unit is identifying — drop
        if "Shipping_Zip" in row:
            row["Shipping_Zip"] = truncate_zip(row.get("Shipping_Zip"))

        # De-identify the organization (products + real-org tokens).
        genericize_row(row)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CANONICAL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    # Private mapping — for audit / deletion requests only. NEVER commit.
    map_path = os.path.join(os.path.dirname(out_path), "anon_mapping_private.csv")
    with open(map_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["real_name", "fake_name", "fake_email"])
        # Re-read the original file to record true names alongside the fakes
        # (rows in memory are already anonymized).
        seen = {}
        with open(in_path, newline="", encoding="utf-8") as orig:
            for r in csv.DictReader(orig):
                k = (r.get("Customer_Name") or "").strip().lower()
                if k in mapping and k not in seen:
                    seen[k] = True
                    w.writerow([r.get("Customer_Name", ""), mapping[k]["name"], mapping[k]["email"]])

    print(f"Anonymized {len(rows)} rows across {len(mapping)} unique customers.")
    print(f"  Replaced : Customer_Name, Email, street address (Line2 dropped)")
    print(f"  Coarsened: Zip -> 3-digit prefix")
    print(f"  Preserved: products, prices, dates, city, state, order structure")
    print(f"  Public   : {out_path}")
    print(f"  PRIVATE  : {map_path}  (gitignored — never commit)")


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    default_in = os.path.join(here, "..", "data", "orders_raw.csv")
    default_out = os.path.join(here, "..", "data", "orders.csv")
    in_path = sys.argv[1] if len(sys.argv) > 1 else default_in
    out_path = sys.argv[2] if len(sys.argv) > 2 else default_out
    anonymize(in_path, out_path)

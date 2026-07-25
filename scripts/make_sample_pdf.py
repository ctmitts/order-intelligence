#!/usr/bin/env python3
"""
Generate a synthetic order-form / packing-slip PDF for testing the live
extraction flow. All names, addresses, and products are fictional (Wandering
Roots Collective branding). Output: samples/sample_order_form.pdf

Usage:
    python3 make_sample_pdf.py [out.pdf]
"""

import os
import sys

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))
from branding import ORG_NAME, TAGLINE  # noqa: E402

INK = (0.12, 0.16, 0.15)
MUTE = (0.42, 0.45, 0.44)
GREEN = (0.18, 0.42, 0.37)
LINE = (0.85, 0.87, 0.86)

# Two fully-synthetic orders.
ORDERS = [
    {
        "number": "4821", "date": "06/12/2024", "ship_date": "06/14/2024",
        "name": "Nova Sinclair", "email": "nova.sinclair482@gmail.com",
        "addr1": "1420 Cedar Ave", "city": "Portland", "state": "OR", "zip": "97214",
        "lines": [
            ("GUMM-3", "Botanical Gummies — 3-Pack", 1, 64.99),
            ("CHOC-1", "Dark Chocolate Bar — 1-Pack", 2, 28.00),
        ],
        "service_fee": 7.26, "shipping": 12.00,
    },
    {
        "number": "4907", "date": "06/13/2024", "ship_date": "06/15/2024",
        "name": "Julian Okafor", "email": "julian.okafor137@proton.me",
        "addr1": "88 Marlowe St", "city": "Austin", "state": "TX", "zip": "78702",
        "lines": [
            ("CARM-5", "Signature Caramels — 5-Pack", 1, 149.99),
            ("SAMP", "Sampler Pack", 1, 39.00),
        ],
        "service_fee": 10.94, "shipping": 12.00,
    },
]


def draw_order(page, o):
    W = page.rect.width
    x0, x1 = 54, W - 54

    def text(x, y, s, size=10, color=INK, bold=False):
        s = s.replace("—", "-")  # base-14 fonts don't carry the em dash
        page.insert_text((x, y), s, fontsize=size,
                         fontname="hebo" if bold else "helv", color=color)

    # Header
    text(x0, 70, ORG_NAME.upper(), size=17, color=GREEN, bold=True)
    text(x0, 88, TAGLINE, size=9, color=MUTE)
    text(x1 - 120, 70, "PACKING SLIP", size=13, color=INK, bold=True)
    page.draw_line((x0, 104), (x1, 104), color=LINE, width=1)

    # Order meta (right) + Ship To (left)
    text(x0, 140, "SHIP TO", size=8, color=MUTE, bold=True)
    text(x0, 158, o["name"], size=11, bold=True)
    text(x0, 174, o["addr1"], size=10)
    text(x0, 190, f'{o["city"]}, {o["state"]} {o["zip"]}', size=10)
    text(x0, 206, o["email"], size=10, color=MUTE)

    mx = x1 - 210
    for i, (label, val) in enumerate([
        ("Order #", o["number"]), ("Order Date", o["date"]), ("Ship Date", o["ship_date"]),
    ]):
        y = 140 + i * 18
        text(mx, y, label, size=9, color=MUTE)
        text(mx + 90, y, val, size=9, bold=True)

    # Table
    ty = 250
    text(x0, ty, "CODE", size=8, color=MUTE, bold=True)
    text(x0 + 78, ty, "DESCRIPTION", size=8, color=MUTE, bold=True)
    text(x1 - 168, ty, "QTY", size=8, color=MUTE, bold=True)
    text(x1 - 118, ty, "UNIT", size=8, color=MUTE, bold=True)
    text(x1 - 52, ty, "AMOUNT", size=8, color=MUTE, bold=True)
    page.draw_line((x0, ty + 8), (x1, ty + 8), color=LINE, width=1)

    subtotal = 0.0
    ry = ty + 30
    for code, desc, qty, unit in o["lines"]:
        amount = qty * unit
        subtotal += amount
        text(x0, ry, code, size=10, bold=True)
        text(x0 + 78, ry, desc, size=10)
        text(x1 - 168, ry, str(qty), size=10)
        text(x1 - 118, ry, f"${unit:,.2f}", size=10)
        text(x1 - 58, ry, f"${amount:,.2f}", size=10)
        ry += 22

    # Totals
    page.draw_line((x1 - 220, ry + 4), (x1, ry + 4), color=LINE, width=1)
    total = subtotal + o["service_fee"] + o["shipping"]
    rows = [
        ("Subtotal", subtotal, False), ("Service Fee", o["service_fee"], False),
        ("Shipping", o["shipping"], False), ("Total", total, True),
    ]
    yy = ry + 24
    for label, val, bold in rows:
        text(x1 - 220, yy, label, size=10, color=INK if bold else MUTE, bold=bold)
        text(x1 - 70, yy, f"${val:,.2f}", size=10, bold=bold)
        yy += 20

    text(x0, page.rect.height - 60, "Fictional data — for demo/testing only.",
         size=8, color=MUTE)


def main(out_path):
    doc = fitz.open()
    for o in ORDERS:
        page = doc.new_page(width=612, height=792)
        draw_order(page, o)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    doc.save(out_path)
    doc.close()
    print(f"Wrote {len(ORDERS)}-page sample: {out_path}")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "samples", "sample_order_form.pdf")
    main(out)

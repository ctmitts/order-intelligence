#!/usr/bin/env python3
"""
Rebuild the ChromaDB vector store from the anonymized order CSV.

Idempotent: wipes any existing collection and re-imports every row from
data/orders.csv. Run this after cloning the repo or after re-anonymizing.

Usage:
    python3 build_db.py [orders.csv] [chroma_db_dir]
"""

import os
import sys

import pandas as pd

# Make the app package importable when run from scripts/.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "app"))

from database_manager import OrderDatabaseManager  # noqa: E402


def build(csv_path: str, db_path: str) -> None:
    if not os.path.exists(csv_path):
        raise SystemExit(f"CSV not found: {csv_path}\nRun scripts/anonymize.py first.")

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {csv_path}")

    # Fresh start: remove any existing store so re-runs don't duplicate.
    import shutil
    if os.path.isdir(db_path):
        shutil.rmtree(db_path)
    os.makedirs(db_path, exist_ok=True)

    db = OrderDatabaseManager(db_path=db_path)

    records = df.to_dict(orient="records")
    # ChromaDB caps a single add() at ~5461 records; insert in chunks.
    CHUNK = 2000
    total = 0
    for i in range(0, len(records), CHUNK):
        batch = records[i : i + CHUNK]
        db.add_records(batch)
        total += len(batch)
        print(f"  imported {total}/{len(records)}")
    print(f"Imported {total} records into ChromaDB at {db_path}")

    stats = db.get_summary_stats()
    print(f"  Unique orders   : {stats.get('unique_orders')}")
    print(f"  Unique customers: {stats.get('unique_customers')}")
    print(f"  Date range      : {stats.get('date_range')}")


if __name__ == "__main__":
    csv_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "data", "orders.csv")
    db_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "app", "chroma_db")
    build(csv_path, db_path)

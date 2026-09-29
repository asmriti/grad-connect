"""Ingest professors from the CSV into PostgreSQL.

Usage:
    python scripts/ingest.py [--csv path/to/data.csv]
"""

import _bootstrap  # noqa: F401

import argparse

from app.config import get_settings
from app.db.session import get_sessionmaker
from app.services.ingest import read_csv, upsert_professors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None, help="CSV path (default: settings)")
    args = parser.parse_args()

    csv_path = args.csv or get_settings().professors_csv
    records, errors = read_csv(csv_path)
    for error in errors:
        print(f"  warning: {error}")
    print(f"Read {len(records)} valid professor records from {csv_path}")

    with get_sessionmaker()() as session:
        inserted, updated = upsert_professors(session, records)
    print(f"Inserted {inserted}, updated {updated}, unchanged {len(records) - inserted - updated}.")


if __name__ == "__main__":
    main()

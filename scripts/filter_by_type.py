#!/usr/bin/env python3
"""
Remove places whose maps_type_label is not in the allowed list.

Usage:
    python scripts/filter_by_type.py <database.db> <Label1> <Label2> ...

Example:
    python scripts/filter_by_type.py dentist_london.db Dentist "Dental Clinic"
"""
import argparse
import sqlite3
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Keep only places matching the given maps_type_label values."
    )
    parser.add_argument("database", help="Path to the SQLite database")
    parser.add_argument("labels", nargs="+", metavar="LABEL",
                        help="maps_type_label values to keep")
    args = parser.parse_args()

    conn = sqlite3.connect(args.database)
    conn.row_factory = sqlite3.Row

    before = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]

    print("Labels found before filtering:")
    rows = conn.execute(
        "SELECT COALESCE(maps_type_label, '(none)') as label, COUNT(*) as n "
        "FROM places GROUP BY maps_type_label ORDER BY n DESC"
    ).fetchall()
    for r in rows:
        marker = "✓" if r["label"] in args.labels else "✗"
        print(f"  {marker} {r['label']:<40} {r['n']}")

    # Delete
    placeholders = ",".join("?" * len(args.labels))
    conn.execute(
        f"DELETE FROM places WHERE maps_type_label NOT IN ({placeholders}) OR maps_type_label IS NULL",
        args.labels,
    )
    conn.commit()

    after = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]

    print(f"\nRemoved: {before - after} entries")
    print(f"Remaining: {after}")

    conn.close()


if __name__ == "__main__":
    main()

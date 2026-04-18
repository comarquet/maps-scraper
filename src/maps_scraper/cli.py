from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from . import db, export
from .db import db_path_for_search
from .geocoder import geocode_to_bbox
from .grid import GridSearcher
from .models import bbox_from_center_radius, haversine_km


def _get_api_key() -> str:
    load_dotenv()
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not key:
        print("Error: GOOGLE_MAPS_API_KEY not set. "
              "Set it in .env or as an environment variable.", file=sys.stderr)
        sys.exit(1)
    return key


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(message)s",
        level=level,
        stream=sys.stderr,
    )


def cmd_search(args: argparse.Namespace) -> None:
    api_key = _get_api_key()
    _setup_logging(args.verbose)

    # Resolve bounding box — either from a named location or from center+radius
    if args.center:
        try:
            lat, lng = map(float, args.center.split(","))
        except ValueError:
            print("Error: --center must be in format LAT,LNG (e.g. 48.72,2.08)", file=sys.stderr)
            sys.exit(1)
        if args.radius is None:
            print("Error: --radius is required when using --center", file=sys.stderr)
            sys.exit(1)
        location_label = f"{lat},{lng} r={args.radius}km"
        bbox = bbox_from_center_radius(lat, lng, args.radius)
        print(f"Searching within {args.radius} km of ({lat}, {lng})", file=sys.stderr)
    else:
        if not args.location:
            print("Error: provide either --location or --center + --radius", file=sys.stderr)
            sys.exit(1)
        location_label = args.location
        print(f"Geocoding '{args.location}'...", file=sys.stderr)
        bbox = geocode_to_bbox(args.location, api_key)

    print(f"Bounding box: ({bbox.sw.latitude:.4f}, {bbox.sw.longitude:.4f}) → "
          f"({bbox.ne.latitude:.4f}, {bbox.ne.longitude:.4f})", file=sys.stderr)

    if not args.query and not args.type:
        print("Error: provide a query and/or --type", file=sys.stderr)
        sys.exit(1)

    query = args.query or args.type
    query_label = args.query or args.type

    db_path = db_path_for_search(query_label, location_label)
    print(f"Database: {db_path}", file=sys.stderr)
    conn = db.get_connection(db_path)
    db.init_db(conn)

    # Create search record
    search_id = db.create_search(conn, query_label, location_label)

    # Run exhaustive grid search
    searcher = GridSearcher(query, bbox, api_key, included_type=args.type)
    places = searcher.run()

    # Filter to radius if --center/--radius was used
    if args.center and args.radius:
        center_lat, center_lng = map(float, args.center.split(","))
        before = len(places)
        places = [
            p for p in places
            if p.latitude is not None and p.longitude is not None
            and haversine_km(center_lat, center_lng, p.latitude, p.longitude) <= args.radius
        ]
        print(f"  Radius filter: {before} → {len(places)} places within {args.radius} km", file=sys.stderr)

    # Store results
    inserted = db.upsert_places(conn, places, search_id)
    db.update_search_stats(conn, search_id, len(places), searcher.cells_searched)

    # Summary of maps_type_label found
    from collections import Counter
    label_counts = Counter(p.maps_type_label for p in places if p.maps_type_label)
    if label_counts:
        print(f"\nGoogle Maps type labels found:", file=sys.stderr)
        for label, n in label_counts.most_common():
            print(f"  {label:<40} {n}", file=sys.stderr)

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"Search complete!", file=sys.stderr)
    print(f"  Query:          {query_label}", file=sys.stderr)
    print(f"  Location:       {location_label}", file=sys.stderr)
    print(f"  Unique places:  {len(places)}", file=sys.stderr)
    print(f"  New places:     {inserted}", file=sys.stderr)
    print(f"  Cells searched: {searcher.cells_searched}", file=sys.stderr)
    print(f"  Search ID:      {search_id}", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)
    print(f"\nExport with: maps-scraper export --search-id {search_id}", file=sys.stderr)

    conn.close()


def _resolve_db(args: argparse.Namespace) -> Path:
    """Return the database path: explicit --db, or latest .db file in cwd."""
    if args.db:
        p = Path(args.db)
        if not p.exists():
            print(f"Error: database '{p}' not found.", file=sys.stderr)
            sys.exit(1)
        return p
    db_files = sorted(Path(".").glob("*.db"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not db_files:
        print("No database found. Run a search first.", file=sys.stderr)
        sys.exit(1)
    return db_files[0]


def cmd_export(args: argparse.Namespace) -> None:
    db_path = _resolve_db(args)
    print(f"Using database: {db_path}", file=sys.stderr)
    conn = db.get_connection(db_path)
    db.init_db(conn)

    # Determine search_id
    search_id = args.search_id
    if search_id is None:
        latest = db.get_latest_search(conn)
        if latest is None:
            print("No searches found. Run a search first.", file=sys.stderr)
            sys.exit(1)
        search_id = latest["id"]
        print(f"Exporting latest search (ID {search_id})...", file=sys.stderr)

    output = Path(args.output) if args.output else None
    near = None
    open_at = None
    if args.near:
        try:
            lat, lng = map(float, args.near.split(","))
            near = (lat, lng)
        except ValueError:
            print("Error: --near must be in format LAT,LNG (e.g. 45.43,4.39)", file=sys.stderr)
            sys.exit(1)
    if args.open_at:
        try:
            open_at = export.parse_open_at(args.open_at)
        except ValueError as exc:
            print(f"Error: --open-at {exc}", file=sys.stderr)
            sys.exit(1)

    if args.format == "json":
        content = export.export_json(conn, search_id, output, near=near,
                                     max_distance_km=args.max_distance,
                                     type_labels=args.type,
                                     min_rating=args.min_rating,
                                     min_reviews=args.min_reviews,
                                     open_at=open_at)
    else:
        content = export.export_csv(conn, search_id, output, near=near,
                                    max_distance_km=args.max_distance,
                                    type_labels=args.type,
                                    min_rating=args.min_rating,
                                    min_reviews=args.min_reviews,
                                    open_at=open_at)

    if output:
        print(f"Exported to {output}", file=sys.stderr)
    else:
        print(content)

    conn.close()


def cmd_history(args: argparse.Namespace) -> None:
    db_path = _resolve_db(args)
    print(f"Using database: {db_path}", file=sys.stderr)
    conn = db.get_connection(db_path)
    db.init_db(conn)

    searches = db.get_all_searches(conn)
    if not searches:
        print("No searches yet.")
        return

    print(f"{'ID':>4}  {'Date':<20} {'Results':>8} {'Cells':>6}  Query")
    print(f"{'—'*4}  {'—'*20} {'—'*8} {'—'*6}  {'—'*30}")
    for s in searches:
        print(f"{s['id']:>4}  {s['searched_at']:<20} {s['total_found']:>8} "
              f"{s['cells_searched']:>6}  {s['query']} @ {s['location']}")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="maps-scraper",
        description="Exhaustive Google Maps Places scraper",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # search
    p_search = subparsers.add_parser("search", help="Search for places in an area")
    p_search.add_argument("query", nargs="?", default=None,
                          help="Search query (e.g., 'italian restaurant'). Optional if --type is set.")
    p_search.add_argument("--location", "-l",
                          help="Location name to geocode (e.g., 'Paris')")
    p_search.add_argument("--center", metavar="LAT,LNG",
                          help="Center point for radius search (e.g. 48.72,2.08)")
    p_search.add_argument("--radius", "-r", type=float, metavar="KM",
                          help="Search radius in km around --center (e.g. 15)")
    p_search.add_argument("--type", "-t", metavar="TYPE",
                          help="Filter by primary type (e.g. restaurant, dentist, cafe)")
    p_search.add_argument("--verbose", "-v", action="store_true",
                          help="Show detailed progress")
    p_search.set_defaults(func=cmd_search)

    # export
    p_export = subparsers.add_parser("export", help="Export search results")
    p_export.add_argument("--format", "-f", choices=["csv", "json"], default="csv",
                          help="Export format (default: csv)")
    p_export.add_argument("--output", "-o", help="Output file (default: stdout)")
    p_export.add_argument("--search-id", type=int,
                          help="Search ID to export (default: latest)")
    p_export.add_argument("--near", metavar="LAT,LNG",
                          help="Sort by distance to this point (e.g. 45.43,4.39)")
    p_export.add_argument("--max-distance", type=float, metavar="KM",
                          help="Only export places within this distance from --near (requires --near)")
    p_export.add_argument("--type", "-t", metavar="TYPE", action="append",
                          help="Only export places with this Google Maps type label (repeatable, e.g. -t Restaurant -t Cafe)")
    p_export.add_argument("--min-rating", type=float, metavar="RATING",
                          help="Only export places with rating >= RATING (e.g. 4.0)")
    p_export.add_argument("--min-reviews", type=int, metavar="N",
                          help="Only export places with review_count >= N (e.g. 5)")
    p_export.add_argument("--open-at", metavar='"DAY HH:MM"',
                          help="Only export places open on the given day and time (e.g. 'Thursday 23:00')")
    p_export.add_argument("--db", metavar="FILE",
                          help="Database file to use (default: most recent .db in current directory)")
    p_export.set_defaults(func=cmd_export)

    # history
    p_history = subparsers.add_parser("history", help="Show past searches")
    p_history.add_argument("--db", metavar="FILE",
                           help="Database file to use (default: most recent .db in current directory)")
    p_history.set_defaults(func=cmd_history)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

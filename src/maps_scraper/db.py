from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .models import Place

DB_PATH = Path("maps_scraper.db")


def db_path_for_search(query: str, location_label: str) -> Path:
    """Generate a meaningful database filename from query and location."""
    def slugify(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[°'\"\s]+", "_", s)   # spaces and special chars → _
        s = re.sub(r"[^a-z0-9_.,+-]", "", s)  # keep only safe chars
        s = re.sub(r"_+", "_", s).strip("_")
        return s[:40]

    return Path(f"{slugify(query)}__{slugify(location_label)}.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query           TEXT NOT NULL,
    location        TEXT NOT NULL,
    total_found     INTEGER DEFAULT 0,
    cells_searched  INTEGER DEFAULT 0,
    searched_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS places (
    place_id        TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    address         TEXT,
    rating          REAL,
    review_count    INTEGER,
    price_level     INTEGER,
    maps_type_label TEXT,
    latitude        REAL,
    longitude       REAL,
    maps_url        TEXT,
    opening_hours   TEXT,
    search_id       INTEGER REFERENCES searches(id)
);

CREATE INDEX IF NOT EXISTS idx_places_rating ON places(rating DESC);
CREATE INDEX IF NOT EXISTS idx_places_review_count ON places(review_count DESC);
CREATE INDEX IF NOT EXISTS idx_places_search ON places(search_id);
"""


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    # Migration: add opening_hours column if missing (existing databases)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(places)")}
    if "opening_hours" not in cols:
        conn.execute("ALTER TABLE places ADD COLUMN opening_hours TEXT")
    if "maps_type_label" not in cols:
        conn.execute("ALTER TABLE places ADD COLUMN maps_type_label TEXT")
    conn.commit()


def create_search(conn: sqlite3.Connection, query: str, location: str) -> int:
    cur = conn.execute(
        "INSERT INTO searches (query, location) VALUES (?, ?)",
        (query, location),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def upsert_places(conn: sqlite3.Connection, places: list[Place], search_id: int) -> int:
    """Upsert places, updating all fields including search_id on conflict.
    Returns the number of truly new places (not previously in DB)."""
    if not places:
        return 0

    unique_place_ids = {p.place_id for p in places}
    existing_ids = {
        row[0] for row in conn.execute(
            f"SELECT place_id FROM places WHERE place_id IN ({','.join('?' * len(unique_place_ids))})",
            list(unique_place_ids),
        )
    }

    for p in places:
        conn.execute(
            """INSERT INTO places
               (place_id, name, address, rating, review_count, price_level,
                maps_type_label, latitude, longitude, maps_url, opening_hours, search_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(place_id) DO UPDATE SET
                   name=excluded.name, address=excluded.address, rating=excluded.rating,
                   review_count=excluded.review_count, price_level=excluded.price_level,
                   maps_type_label=excluded.maps_type_label,
                   latitude=excluded.latitude, longitude=excluded.longitude,
                   maps_url=excluded.maps_url, opening_hours=excluded.opening_hours,
                   search_id=excluded.search_id""",
            (
                p.place_id, p.name, p.address, p.rating, p.review_count,
                p.price_level, p.maps_type_label, p.latitude, p.longitude,
                p.maps_url, p.opening_hours_json, search_id,
            ),
        )
    conn.commit()
    return len(unique_place_ids - existing_ids)


def update_search_stats(conn: sqlite3.Connection, search_id: int,
                        total_found: int, cells_searched: int) -> None:
    conn.execute(
        "UPDATE searches SET total_found = ?, cells_searched = ? WHERE id = ?",
        (total_found, cells_searched, search_id),
    )
    conn.commit()


def get_places_by_search(conn: sqlite3.Connection, search_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM places WHERE search_id = ? ORDER BY rating DESC, review_count DESC",
        (search_id,),
    ).fetchall()


def get_places_near(
    conn: sqlite3.Connection, search_id: int, lat: float, lng: float
) -> list[sqlite3.Row]:
    """Return places sorted by distance to (lat, lng), closest first."""
    return conn.execute(
        """SELECT *,
               ((latitude - ?) * (latitude - ?) + (longitude - ?) * (longitude - ?)) AS dist_sq
           FROM places
           WHERE search_id = ? AND latitude IS NOT NULL
           ORDER BY dist_sq""",
        (lat, lat, lng, lng, search_id),
    ).fetchall()


def get_all_searches(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM searches ORDER BY searched_at DESC",
    ).fetchall()


def get_latest_search(conn: sqlite3.Connection) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM searches ORDER BY id DESC LIMIT 1",
    ).fetchone()

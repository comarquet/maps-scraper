"""Tests for database layer."""
import sqlite3

from maps_scraper import db
from maps_scraper.models import Place


def _in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    return conn


def test_create_search():
    conn = _in_memory_db()
    sid = db.create_search(conn, "pizza", "Rome")
    assert sid == 1
    sid2 = db.create_search(conn, "sushi", "Tokyo")
    assert sid2 == 2


def test_upsert_places_dedup():
    conn = _in_memory_db()
    sid = db.create_search(conn, "test", "here")
    places = [
        Place(place_id="a", name="A", rating=4.0, review_count=100),
        Place(place_id="b", name="B", rating=3.5, review_count=50),
        Place(place_id="a", name="A duplicate", rating=4.0, review_count=100),
    ]
    inserted = db.upsert_places(conn, places, sid)
    assert inserted == 2

    rows = db.get_places_by_search(conn, sid)
    assert len(rows) == 2
    names = {r["name"] for r in rows}
    assert "A duplicate" in names  # last write wins on conflict
    assert "B" in names


def test_update_search_stats():
    conn = _in_memory_db()
    sid = db.create_search(conn, "test", "here")
    db.update_search_stats(conn, sid, total_found=42, cells_searched=9)
    searches = db.get_all_searches(conn)
    assert searches[0]["total_found"] == 42
    assert searches[0]["cells_searched"] == 9


def test_get_latest_search():
    conn = _in_memory_db()
    assert db.get_latest_search(conn) is None
    db.create_search(conn, "first", "A")
    db.create_search(conn, "second", "B")
    latest = db.get_latest_search(conn)
    assert latest["query"] == "second"


def test_places_ordered_by_rating():
    conn = _in_memory_db()
    sid = db.create_search(conn, "test", "here")
    places = [
        Place(place_id="low", name="Low", rating=2.0, review_count=10),
        Place(place_id="high", name="High", rating=4.8, review_count=500),
        Place(place_id="mid", name="Mid", rating=4.0, review_count=200),
    ]
    db.upsert_places(conn, places, sid)
    rows = db.get_places_by_search(conn, sid)
    ratings = [r["rating"] for r in rows]
    assert ratings == sorted(ratings, reverse=True)

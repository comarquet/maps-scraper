"""Tests for export module."""
import csv
import io
import json
import sqlite3

from maps_scraper import db
from maps_scraper.export import export_csv, export_json, parse_open_at
from maps_scraper.models import Place


def _setup() -> tuple[sqlite3.Connection, int]:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    sid = db.create_search(conn, "test", "here")
    places = [
        Place(place_id="a", name="Place A", rating=4.5, review_count=200,
              address="1 Main St", latitude=48.8, longitude=2.3),
        Place(place_id="b", name="Place B", rating=3.8, review_count=50,
              address="2 High St", latitude=48.9, longitude=2.4),
    ]
    db.upsert_places(conn, places, sid)
    return conn, sid


def _setup_with_opening_hours() -> tuple[sqlite3.Connection, int]:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    sid = db.create_search(conn, "test", "here")
    places = [
        Place(
            place_id="late",
            name="Late Bar",
            rating=4.5,
            review_count=200,
            address="1 Main St",
            latitude=48.8,
            longitude=2.3,
            opening_hours=[
                "Thursday: 6:00 PM - 11:30 PM",
                "Friday: 6:00 PM - 1:00 AM",
            ],
        ),
        Place(
            place_id="day",
            name="Day Cafe",
            rating=4.6,
            review_count=80,
            address="2 High St",
            latitude=48.81,
            longitude=2.31,
            opening_hours=[
                "Thursday: 8:00 AM - 6:00 PM",
                "Friday: 8:00 AM - 6:00 PM",
            ],
        ),
        Place(
            place_id="all_day",
            name="All Day Diner",
            rating=4.3,
            review_count=120,
            address="3 Park Ave",
            latitude=48.82,
            longitude=2.32,
            opening_hours=[
                "Thursday: Open 24 hours",
            ],
        ),
    ]
    db.upsert_places(conn, places, sid)
    return conn, sid


def test_export_csv_format():
    conn, sid = _setup()
    content = export_csv(conn, sid)
    reader = csv.DictReader(io.StringIO(content))
    rows = list(reader)
    assert len(rows) == 2
    assert reader.fieldnames == ["name", "rating", "review_count", "maps_url"]
    assert rows[0]["name"] == "Place A"
    assert rows[0]["rating"] == "4.5"
    assert rows[0]["review_count"] == "200"


def test_export_json_format():
    conn, sid = _setup()
    content = export_json(conn, sid)
    data = json.loads(content)
    assert len(data) == 2
    assert list(data[0].keys()) == ["name", "rating", "review_count", "maps_url"]
    assert data[0]["name"] == "Place A"
    assert data[0]["rating"] == 4.5
    assert data[0]["review_count"] == 200


def test_export_csv_to_file(tmp_path):
    conn, sid = _setup()
    out = tmp_path / "output.csv"
    export_csv(conn, sid, out)
    assert out.exists()
    content = out.read_text()
    assert "Place A" in content
    assert "Place B" in content


def test_export_json_to_file(tmp_path):
    conn, sid = _setup()
    out = tmp_path / "output.json"
    export_json(conn, sid, out)
    data = json.loads(out.read_text())
    assert len(data) == 2


def test_parse_open_at():
    assert parse_open_at("Thursday 23:00") == ("Thursday", 23 * 60)


def test_export_csv_filters_open_at():
    conn, sid = _setup_with_opening_hours()
    content = export_csv(conn, sid, near=(48.8, 2.3), open_at=("Thursday", 23 * 60))
    rows = list(csv.DictReader(io.StringIO(content)))
    assert "distance_km" in rows[0]
    assert [row["name"] for row in rows] == ["Late Bar", "All Day Diner"]


def test_export_json_filters_open_at_overnight():
    conn, sid = _setup_with_opening_hours()
    content = export_json(conn, sid, open_at=("Friday", 0))
    data = json.loads(content)
    assert [row["name"] for row in data] == ["Late Bar"]

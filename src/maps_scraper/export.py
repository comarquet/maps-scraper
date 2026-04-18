from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
from pathlib import Path

from .db import get_places_by_search, get_places_near
from .models import haversine_km

EXPORT_COLUMNS = [
    "place_id", "name", "address", "rating", "review_count",
    "price_level", "maps_type_label", "latitude", "longitude",
    "maps_url", "opening_hours",
]
DEFAULT_EXPORT_COLUMNS = ["name", "rating", "review_count", "maps_url"]

_SPACE_TRANSLATION = str.maketrans({
    "\u202f": " ",
    "\u2009": " ",
    "\u200a": " ",
    "\u00a0": " ",
    "–": "-",
    "—": "-",
    "−": "-",
})


def _normalize_opening_text(value: str) -> str:
    return value.translate(_SPACE_TRANSLATION).strip()


def _parse_time_minutes(value: str) -> int:
    text = _normalize_opening_text(value).upper().replace(".", ":")
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", text)
    if not match:
        raise ValueError(f"Unsupported time token: {value!r}")
    hour = int(match.group(1)) % 12
    minute = int(match.group(2) or 0)
    if match.group(3) == "PM":
        hour += 12
    return hour * 60 + minute


def parse_open_at(value: str) -> tuple[str, int]:
    day, _, time_text = value.partition(" ")
    if not day or not time_text:
        raise ValueError("Expected format 'Day HH:MM' (example: Thursday 23:00)")
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", time_text.strip())
    if not match:
        raise ValueError("Time must be in 24-hour format HH:MM")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ValueError("Time must be a valid 24-hour clock value")
    normalized_day = day.strip().capitalize()
    valid_days = {
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday",
    }
    if normalized_day not in valid_days:
        raise ValueError(
            "Day must be one of Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday"
        )
    return normalized_day, hour * 60 + minute


def _is_open_at(opening_hours_json: str | None, day: str, target_minutes: int) -> bool:
    if not opening_hours_json:
        return False
    try:
        descriptions = json.loads(opening_hours_json)
    except json.JSONDecodeError:
        return False
    if not isinstance(descriptions, list):
        return False

    prefix = f"{day}:"
    for description in descriptions:
        if not isinstance(description, str):
            continue
        text = _normalize_opening_text(description)
        if not text.startswith(prefix):
            continue
        body = text.split(":", 1)[1].strip()
        if body == "Closed":
            return False
        if body == "Open 24 hours":
            return True
        for segment in body.split(","):
            segment = segment.strip()
            if "-" not in segment:
                continue
            start_text, end_text = [part.strip() for part in segment.split("-", 1)]
            try:
                start = _parse_time_minutes(start_text)
                end = _parse_time_minutes(end_text)
            except ValueError:
                continue
            if end <= start:
                end += 24 * 60
            if start <= target_minutes < end:
                return True
            if start <= target_minutes + 24 * 60 < end:
                return True
        return False
    return False


def _rows_to_dicts(rows: list[sqlite3.Row],
                   near: tuple[float, float] | None = None,
                   max_distance_km: float | None = None,
                   type_labels: list[str] | None = None,
                   min_rating: float | None = None,
                   min_reviews: int | None = None,
                   open_at: tuple[str, int] | None = None) -> list[dict]:
    result = []
    for row in rows:
        if type_labels and row["maps_type_label"] not in type_labels:
            continue
        if min_rating is not None and (row["rating"] is None or row["rating"] < min_rating):
            continue
        if min_reviews is not None and (row["review_count"] is None or row["review_count"] < min_reviews):
            continue
        if open_at is not None and not _is_open_at(row["opening_hours"], open_at[0], open_at[1]):
            continue
        d = {col: row[col] for col in EXPORT_COLUMNS}
        if near and row["latitude"] and row["longitude"]:
            dist = round(haversine_km(near[0], near[1], row["latitude"], row["longitude"]), 2)
            d["distance_km"] = dist
            if max_distance_km is not None and dist > max_distance_km:
                continue
        elif near:
            d["distance_km"] = None
        result.append(d)
    return result


def export_csv(conn: sqlite3.Connection, search_id: int,
               output: Path | None = None,
               near: tuple[float, float] | None = None,
               max_distance_km: float | None = None,
               type_labels: list[str] | None = None,
               min_rating: float | None = None,
               min_reviews: int | None = None,
               open_at: tuple[str, int] | None = None) -> str:
    rows = get_places_near(conn, search_id, *near) if near else get_places_by_search(conn, search_id)
    dicts = _rows_to_dicts(rows, near, max_distance_km, type_labels, min_rating, min_reviews, open_at)
    columns = DEFAULT_EXPORT_COLUMNS + (["distance_km"] if near else [])

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns)
    writer.writeheader()
    writer.writerows({col: row.get(col) for col in columns} for row in dicts)
    content = buf.getvalue()

    if output:
        output.write_text(content, encoding="utf-8")
    return content


def export_json(conn: sqlite3.Connection, search_id: int,
                output: Path | None = None,
                near: tuple[float, float] | None = None,
                max_distance_km: float | None = None,
                type_labels: list[str] | None = None,
                min_rating: float | None = None,
                min_reviews: int | None = None,
                open_at: tuple[str, int] | None = None) -> str:
    rows = get_places_near(conn, search_id, *near) if near else get_places_by_search(conn, search_id)
    dicts = _rows_to_dicts(rows, near, max_distance_km, type_labels, min_rating, min_reviews, open_at)
    columns = DEFAULT_EXPORT_COLUMNS + (["distance_km"] if near else [])
    dicts = [{col: row.get(col) for col in columns} for row in dicts]
    content = json.dumps(dicts, ensure_ascii=False, indent=2)

    if output:
        output.write_text(content, encoding="utf-8")
    return content

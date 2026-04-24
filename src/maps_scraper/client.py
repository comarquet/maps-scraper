from __future__ import annotations

import logging
import socket
import time

import httpx

from .models import BoundingBox, Place

logger = logging.getLogger(__name__)

SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"

# Force IPv4 to avoid conflicts with API key IP restrictions
_transport = httpx.HTTPTransport(local_address="0.0.0.0")
_client = httpx.Client(transport=_transport)

FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.rating,"
    "places.userRatingCount,"
    "places.priceLevel,"
    "places.types,"
    "places.primaryType,"
    "places.googleMapsTypeLabel,"
    "places.location,"
    "places.nationalPhoneNumber,"
    "places.websiteUri,"
    "places.googleMapsUri,"
    "places.regularOpeningHours,"
    "nextPageToken"
)

PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

# Pause between API calls (seconds)
RATE_LIMIT_DELAY = 0.3


def _parse_place(raw: dict) -> Place:
    loc = raw.get("location", {})
    display_name = raw.get("displayName", {})
    return Place(
        place_id=raw.get("id", ""),
        name=display_name.get("text", ""),
        address=raw.get("formattedAddress"),
        rating=raw.get("rating"),
        review_count=raw.get("userRatingCount"),
        price_level=PRICE_LEVEL_MAP.get(raw.get("priceLevel", ""), None),
        types=raw.get("types", []),
        primary_type=raw.get("primaryType"),
        maps_type_label=raw.get("googleMapsTypeLabel", {}).get("text"),
        latitude=loc.get("latitude"),
        longitude=loc.get("longitude"),
        phone=raw.get("nationalPhoneNumber"),
        website=raw.get("websiteUri"),
        maps_url=raw.get("googleMapsUri"),
        opening_hours=raw.get("regularOpeningHours", {}).get("weekdayDescriptions"),
    )


def _paginate(query: str, location_restriction: dict, api_key: str,
              included_type: str | None = None) -> list[Place]:
    """Shared pagination logic for all search types."""
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body: dict = {
        "textQuery": query,
        "locationRestriction": location_restriction,
        "pageSize": 20,
    }
    all_places: list[Place] = []
    page = 0
    while True:
        page += 1
        time.sleep(RATE_LIMIT_DELAY)
        resp = _client.post(SEARCH_TEXT_URL, json=body, headers=headers, timeout=30)
        if resp.status_code >= 400:
            logger.error("API error %d: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        data = resp.json()
        raw_places = data.get("places", [])
        all_places.extend(_parse_place(p) for p in raw_places)
        logger.debug("  Page %d: %d results", page, len(raw_places))
        next_token = data.get("nextPageToken")
        if not next_token or page >= 3:
            break
        body["pageToken"] = next_token
    return all_places



def search_in_bbox(query: str, bbox: BoundingBox, api_key: str,
                   included_type: str | None = None) -> list[Place]:
    """Search for places within a bounding box."""
    return _paginate(query, {
        "rectangle": {
            "low": {
                "latitude": bbox.sw.latitude,
                "longitude": bbox.sw.longitude,
            },
            "high": {
                "latitude": bbox.ne.latitude,
                "longitude": bbox.ne.longitude,
            },
        }
    }, api_key, included_type)

from __future__ import annotations

import logging

import httpx

from .models import BoundingBox, LatLng

logger = logging.getLogger(__name__)

GEOCODING_URL = "https://maps.googleapis.com/maps/api/geocode/json"


def geocode_to_bbox(location: str, api_key: str) -> BoundingBox:
    """Resolve a place name to a bounding box via Google Geocoding API."""
    resp = httpx.get(
        GEOCODING_URL,
        params={"address": location, "key": api_key},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    if data["status"] != "OK" or not data.get("results"):
        raise ValueError(f"Geocoding failed for '{location}': {data.get('status')}")

    bounds = data["results"][0]["geometry"].get("bounds")
    if bounds is None:
        # Some results only have viewport, fall back to that
        bounds = data["results"][0]["geometry"]["viewport"]

    sw = bounds["southwest"]
    ne = bounds["northeast"]

    bbox = BoundingBox(
        sw=LatLng(latitude=sw["lat"], longitude=sw["lng"]),
        ne=LatLng(latitude=ne["lat"], longitude=ne["lng"]),
    )
    logger.info("Geocoded '%s' → SW(%f, %f) NE(%f, %f)",
                location, bbox.sw.latitude, bbox.sw.longitude,
                bbox.ne.latitude, bbox.ne.longitude)
    return bbox

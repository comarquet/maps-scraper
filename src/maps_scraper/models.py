from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict


@dataclass
class LatLng:
    latitude: float
    longitude: float


@dataclass
class BoundingBox:
    """Rectangle defined by south-west and north-east corners."""
    sw: LatLng
    ne: LatLng

    @property
    def lat_span(self) -> float:
        return self.ne.latitude - self.sw.latitude

    @property
    def lng_span(self) -> float:
        return self.ne.longitude - self.sw.longitude

    @property
    def area_deg2(self) -> float:
        return self.lat_span * self.lng_span

    def subdivide(self) -> list[BoundingBox]:
        """Split into 4 equal sub-boxes (quadrants)."""
        mid_lat = (self.sw.latitude + self.ne.latitude) / 2
        mid_lng = (self.sw.longitude + self.ne.longitude) / 2
        return [
            BoundingBox(LatLng(self.sw.latitude, self.sw.longitude), LatLng(mid_lat, mid_lng)),
            BoundingBox(LatLng(self.sw.latitude, mid_lng), LatLng(mid_lat, self.ne.longitude)),
            BoundingBox(LatLng(mid_lat, self.sw.longitude), LatLng(self.ne.latitude, mid_lng)),
            BoundingBox(LatLng(mid_lat, mid_lng), LatLng(self.ne.latitude, self.ne.longitude)),
        ]


@dataclass
class Place:
    place_id: str
    name: str
    address: str | None = None
    rating: float | None = None
    review_count: int | None = None
    price_level: int | None = None
    types: list[str] = field(default_factory=list)
    primary_type: str | None = None
    maps_type_label: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    phone: str | None = None
    website: str | None = None
    maps_url: str | None = None
    opening_hours: list[str] | None = None

    @property
    def types_json(self) -> str:
        return json.dumps(self.types)

    @property
    def opening_hours_json(self) -> str | None:
        return json.dumps(self.opening_hours, ensure_ascii=False) if self.opening_hours is not None else None

    def to_row(self) -> dict:
        d = asdict(self)
        d["types"] = self.types_json
        return d


@dataclass
class Circle:
    center: LatLng
    radius_km: float


@dataclass
class SearchParams:
    query: str
    location: str


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def bbox_from_center_radius(lat: float, lng: float, radius_km: float) -> BoundingBox:
    """Build a BoundingBox that circumscribes a circle of *radius_km* around (lat, lng)."""
    lat_delta = radius_km / 111.32
    lng_delta = radius_km / (111.32 * math.cos(math.radians(lat)))
    return BoundingBox(
        sw=LatLng(lat - lat_delta, lng - lng_delta),
        ne=LatLng(lat + lat_delta, lng + lng_delta),
    )


# ~0.000009° ≈ 1 metre at equator
MIN_CELL_AREA_DEG2 = 1e-8
MAX_RESULTS_PER_SEARCH = 60

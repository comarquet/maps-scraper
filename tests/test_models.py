"""Tests for models."""
from maps_scraper.models import BoundingBox, LatLng, MIN_CELL_AREA_DEG2


def test_bbox_properties():
    bbox = BoundingBox(sw=LatLng(48.0, 2.0), ne=LatLng(49.0, 3.0))
    assert bbox.lat_span == 1.0
    assert bbox.lng_span == 1.0
    assert bbox.area_deg2 == 1.0


def test_bbox_subdivide():
    bbox = BoundingBox(sw=LatLng(0.0, 0.0), ne=LatLng(1.0, 1.0))
    subs = bbox.subdivide()
    assert len(subs) == 4
    # Each sub-box has 1/4 the area
    for s in subs:
        assert abs(s.area_deg2 - 0.25) < 1e-9


def test_bbox_subdivide_preserves_coverage():
    bbox = BoundingBox(sw=LatLng(48.8, 2.2), ne=LatLng(48.9, 2.4))
    subs = bbox.subdivide()
    # SW corner of first sub = SW of original
    assert subs[0].sw.latitude == bbox.sw.latitude
    assert subs[0].sw.longitude == bbox.sw.longitude
    # NE corner of last sub = NE of original
    assert subs[3].ne.latitude == bbox.ne.latitude
    assert subs[3].ne.longitude == bbox.ne.longitude


def test_min_cell_area():
    assert MIN_CELL_AREA_DEG2 == 1e-8

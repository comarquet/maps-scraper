"""Tests for grid search logic."""
from unittest.mock import patch, MagicMock

from maps_scraper.grid import GridSearcher
from maps_scraper.models import BoundingBox, LatLng, Place


def _make_places(n: int) -> list[Place]:
    return [Place(place_id=f"p{i}", name=f"Place {i}") for i in range(n)]


def test_initial_grid_size():
    bbox = BoundingBox(sw=LatLng(0.0, 0.0), ne=LatLng(1.0, 1.0))
    searcher = GridSearcher("test", bbox, "fake_key", initial_grid=3)
    assert len(searcher._queue) == 9  # 3x3


def test_no_subdivision_when_under_limit():
    """When all cells return < 60 results, no subdivision occurs."""
    bbox = BoundingBox(sw=LatLng(0.0, 0.0), ne=LatLng(1.0, 1.0))

    call_count = 0
    def mock_search(query, cell_bbox, api_key, included_type=None):
        nonlocal call_count
        call_count += 1
        return _make_places(10)

    with patch("maps_scraper.grid.search_in_bbox", side_effect=mock_search):
        searcher = GridSearcher("test", bbox, "fake_key", initial_grid=2)
        results = searcher.run()

    assert call_count == 4  # 2x2 grid, no subdivision
    assert searcher.cells_searched == 4


def test_subdivision_on_saturation():
    """When a cell returns 60 results, it gets subdivided into 4."""
    bbox = BoundingBox(sw=LatLng(0.0, 0.0), ne=LatLng(1.0, 1.0))

    call_count = 0
    def mock_search(query, cell_bbox, api_key, included_type=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_places(60)
        return _make_places(5)

    with patch("maps_scraper.grid.search_in_bbox", side_effect=mock_search):
        searcher = GridSearcher("test", bbox, "fake_key", initial_grid=1)
        results = searcher.run()

    # 1 initial cell (saturated) + 4 subdivisions = 5 cells searched
    assert searcher.cells_searched == 5
    assert call_count == 5


def test_deduplication():
    """Duplicate place_ids are deduplicated."""
    bbox = BoundingBox(sw=LatLng(0.0, 0.0), ne=LatLng(1.0, 1.0))

    def mock_search(query, cell_bbox, api_key, included_type=None):
        return [Place(place_id="same", name="Same Place")]

    with patch("maps_scraper.grid.search_in_bbox", side_effect=mock_search):
        searcher = GridSearcher("test", bbox, "fake_key", initial_grid=2)
        results = searcher.run()

    assert len(results) == 1  # Deduplicated
    assert results[0].place_id == "same"

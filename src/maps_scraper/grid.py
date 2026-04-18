from __future__ import annotations

import logging
from collections import deque

from .client import search_in_bbox
from .models import BoundingBox, LatLng, Place, MAX_RESULTS_PER_SEARCH, MIN_CELL_AREA_DEG2

logger = logging.getLogger(__name__)


class GridSearcher:
    """Exhaustive search with recursive grid subdivision."""

    def __init__(self, query: str, bbox: BoundingBox, api_key: str,
                 initial_grid: int = 3, included_type: str | None = None):
        self.query = query
        self.api_key = api_key
        self.initial_grid = initial_grid
        self.included_type = included_type

        self.all_places: dict[str, Place] = {}  # place_id → Place (dedup)
        self.cells_searched = 0

        self._queue: deque[BoundingBox] = deque()
        self._build_initial_grid(bbox)

    def _build_initial_grid(self, bbox: BoundingBox) -> None:
        lat_step = bbox.lat_span / self.initial_grid
        lng_step = bbox.lng_span / self.initial_grid
        for row in range(self.initial_grid):
            for col in range(self.initial_grid):
                cell = BoundingBox(
                    sw=LatLng(
                        latitude=bbox.sw.latitude + row * lat_step,
                        longitude=bbox.sw.longitude + col * lng_step,
                    ),
                    ne=LatLng(
                        latitude=bbox.sw.latitude + (row + 1) * lat_step,
                        longitude=bbox.sw.longitude + (col + 1) * lng_step,
                    ),
                )
                self._queue.append(cell)

    def _process_places(self, places: list[Place]) -> int:
        new_count = 0
        for p in places:
            if p.place_id not in self.all_places:
                self.all_places[p.place_id] = p
                new_count += 1
        return new_count

    def run(self) -> list[Place]:
        logger.info("Starting grid search: %d initial cells", len(self._queue))

        while self._queue:
            cell = self._queue.popleft()
            self.cells_searched += 1

            logger.info(
                "[Cell %d] Searching (%.6f,%.6f)→(%.6f,%.6f)...",
                self.cells_searched,
                cell.sw.latitude, cell.sw.longitude,
                cell.ne.latitude, cell.ne.longitude,
            )

            places = search_in_bbox(self.query, cell, self.api_key, self.included_type)
            new_count = self._process_places(places)

            logger.info(
                "[Cell %d] Found %d results (%d new). Total unique: %d",
                self.cells_searched, len(places), new_count, len(self.all_places),
            )

            if len(places) >= MAX_RESULTS_PER_SEARCH:
                if cell.area_deg2 < MIN_CELL_AREA_DEG2:
                    logger.warning(
                        "[Cell %d] Saturated (%d results) but cell too small to subdivide "
                        "(area=%.2e deg²). Some results may be missing.",
                        self.cells_searched, len(places), cell.area_deg2,
                    )
                else:
                    sub_cells = cell.subdivide()
                    self._queue.extend(sub_cells)
                    logger.info(
                        "[Cell %d] Saturated (%d results) → subdividing into 4 cells. "
                        "Queue: %d remaining",
                        self.cells_searched, len(places), len(self._queue),
                    )

        logger.info(
            "Search complete: %d unique places, %d cells searched",
            len(self.all_places), self.cells_searched,
        )
        return list(self.all_places.values())

# Google Maps Places Scraper

Exhaustive Google Maps scraper with recursive grid subdivision.
Retrieves **all** results in an area by working around the 60-result-per-query limit.

## Installation

```bash
cd maps-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Configuration

1. Create a Google Cloud project with the following APIs enabled:
   - **Places API (New)**
   - **Geocoding API**

2. Copy the example env file and add your key:
```bash
cp .env.example .env
# Edit .env with your API key
```

---

## `maps-scraper search` — Run a search

The scraper:
1. Resolves the area (geocodes a city or computes a bounding box from center + radius)
2. Splits the area into a 3x3 grid
3. Searches each cell via the Places API
4. Subdivides saturated cells (>= 60 results) into 4 sub-cells
5. Repeats until exhaustive coverage
6. Stores results in a `.db` file (SQLite)

### Options

| Option | Alias | Description |
|--------|-------|-------------|
| `query` | — | Text query (e.g., `"coffee shop"`, `"italian restaurant"`) |
| `--location` | `-l` | Place name to geocode (e.g., `"London"`) |
| `--center` | — | Area center as `LAT,LNG` (e.g., `51.50,-0.12`) |
| `--radius` | `-r` | Radius in km around `--center` (e.g., `15`) |
| `--type` | `-t` | Filter by Google Maps type (e.g., `restaurant`, `dentist`) |
| `--verbose` | `-v` | Detailed logs |

> `--location` and `--center/--radius` are mutually exclusive.
> `--radius` is required when using `--center`.
> `query` and/or `--type` must be provided.

### Examples

```bash
# By city name
maps-scraper search "italian restaurant" --location "London"

# By GPS coordinates + radius
maps-scraper search "dentist" --center "51.5074,-0.1278" --radius 10

# By Google Maps type only (no text query)
maps-scraper search --location "New York" --type dentist

# Combined: query + type + verbose logs
maps-scraper search "bakery" --location "Berlin" --type bakery -v
```

---

## `maps-scraper export` — Export results

Exports search results to CSV (default) or JSON.

**Exported columns:** `name`, `rating`, `review_count`, `maps_url` (+ `distance_km` if `--near` is used)

### Options

| Option | Alias | Description |
|--------|-------|-------------|
| `--format` | `-f` | Output format: `csv` (default) or `json` |
| `--output` | `-o` | Output file (default: stdout) |
| `--search-id` | — | Search ID to export (default: latest) |
| `--db` | — | `.db` file to use (default: most recent in current directory) |
| `--near` | — | Sort by distance to this `LAT,LNG` point (e.g., `51.50,-0.12`) |
| `--max-distance` | — | Only export places within X km of `--near` |
| `--type` | `-t` | Filter by Google Maps type label (repeatable: `-t Restaurant -t Cafe`) |
| `--min-rating` | — | Minimum rating (e.g., `4.0`) |
| `--min-reviews` | — | Minimum number of reviews (e.g., `5`) |
| `--open-at` | — | Only places open at this time: `"Day HH:MM"` (e.g., `"Thursday 23:00"`) |

> `--max-distance` requires `--near`.

### Examples

```bash
# Export latest search as CSV to stdout
maps-scraper export

# Export CSV to a file
maps-scraper export -o results.csv

# Export JSON for a specific search
maps-scraper export --format json --search-id 3 -o results.json

# Sort by distance, limit to 5 km
maps-scraper export --near "51.50,-0.12" --max-distance 5 -o nearby.csv

# Filter by Google Maps type (multiple types)
maps-scraper export -t Restaurant -t Cafe -o food.csv

# Filter by rating and review count
maps-scraper export --min-rating 4.0 --min-reviews 10 -o top.csv

# Places open on Thursday at 8pm
maps-scraper export --open-at "Thursday 20:00" -o open_thursday.csv

# From a specific database, JSON export with all filters
maps-scraper export --db dentist_london.db --format json \
  --near "51.50,-0.12" --max-distance 10 \
  --min-rating 4.0 --min-reviews 5 \
  --open-at "Saturday 10:00" \
  -o filtered_results.json
```

---

## `maps-scraper history` — Search history

```bash
maps-scraper history

# From a specific database
maps-scraper history --db dentist_london.db
```

---

## Query the database directly

```bash
sqlite3 my-search.db
```

### Top rated with minimum reviews

```sql
SELECT name, address, rating, review_count
FROM places
WHERE rating >= 4.0
  AND review_count >= 20
ORDER BY rating DESC, review_count DESC
LIMIT 20;
```

### Sort by distance from a point

```sql
SELECT name, address, rating, review_count,
    ((latitude - 48.7161) * (latitude - 48.7161)
     + (longitude - 2.1039) * (longitude - 2.1039)) AS dist_sq
FROM places
ORDER BY dist_sq ASC;
```

### Closest places with minimum rating and reviews

```sql
SELECT name, address, rating, review_count,
    ((latitude - 48.7161) * (latitude - 48.7161)
     + (longitude - 2.1039) * (longitude - 2.1039)) AS dist_sq
FROM places
WHERE rating >= 4.0
  AND review_count >= 3
ORDER BY dist_sq ASC;
```

### Filter by type

```sql
SELECT name, address, rating, review_count
FROM places
WHERE maps_type_label = 'Computer repair service'
ORDER BY rating DESC;
```

### Places with a website and phone number

```sql
SELECT name, phone, website, rating
FROM places
WHERE website IS NOT NULL
  AND phone IS NOT NULL
ORDER BY rating DESC;
```

### Count results per search

```sql
SELECT s.id, s.query, s.location, s.total_found, s.searched_at
FROM searches s
ORDER BY s.searched_at DESC;
```

## Project structure

```
src/maps_scraper/
  cli.py        # CLI entry point
  client.py     # Google Places API client (searchText + pagination)
  geocoder.py   # Geocoding API → bounding box
  grid.py       # Recursive subdivision for exhaustive coverage
  db.py         # SQLite layer
  models.py     # Dataclasses (Place, BoundingBox, etc.)
  export.py     # CSV / JSON export
```

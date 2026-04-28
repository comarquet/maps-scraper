SELECT
    name,
    address,
    rating,
    review_count,
    maps_url,
    round(
        2 * 6371 * asin(sqrt(
            sin((radians(latitude) - radians(48.716120035005716)) / 2) *
            sin((radians(latitude) - radians(48.716120035005716)) / 2) +
            cos(radians(48.716120035005716)) * cos(radians(latitude)) *
            sin((radians(longitude) - radians(2.1039126029380464)) / 2) *
            sin((radians(longitude) - radians(2.1039126029380464)) / 2)
        )),
    2) AS distance_km
FROM places
WHERE rating >= 4
  AND review_count >= 3
ORDER BY distance_km ASC;

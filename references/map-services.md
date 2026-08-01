# Map Services

## Preferred Provider: Gaode/Amap Web Service

Use Gaode/Amap for mainland China self-driving routes.

Relevant official docs:

- Driving route planning: https://lbs.amap.com/api/webservice/guide/api/direction
- Geocoding: https://lbs.amap.com/api/webservice/guide/api/georegeo
- Static map: https://lbs.amap.com/api/webservice/guide/api/staticmaps

Environment variables:

- `AMAP_KEY`
- `GAODE_KEY`
- `SDTP_ROUTE_CACHE` (optional local JSON cache for successful geocoding and
  Amap driving-route responses)

Lookup sequence:

1. Geocode each stop name to `lng,lat`.
2. Call driving route planning for each adjacent origin/destination pair.
3. Read distance in meters and convert to kilometers.
4. Read duration in seconds and convert to minutes.
5. Read tolls if present. If tolls are absent, calculate the documented
   per-kilometer estimate and mark the leg as estimated so `toll_cny` remains
   numeric.
6. Collect step polylines when available and keep them in JSON for route drawing.
7. When `SDTP_ROUTE_CACHE` is set, reuse successful geocoding and route
   responses from that local JSON file before calling Amap. Do not cache failed
   lookups, quota errors, estimate fallback metrics, malformed coordinates, or
   incomplete route objects. Ignore cache files with unknown schema versions.
   Concurrent writers use a short-lived lock and merge before atomically replacing
   the cache file, so parallel trip generations do not lose unrelated entries.
8. Render the map with **Leaflet + Amap tiles** (see `scripts/leaflet_map.py`):
   - The interactive map is embedded in `trip.html` and shows the **real driving
     route** (the polylines from step 5) on top of public Amap raster tiles
     (`webrd0{1-4}.is.autonavi.com`). No web-service key is needed for the
     tiles — only for the routing/geocoding calls above.
   - Each leg is drawn with its own polyline; color reflects data source
     (blue `#2c6bb2` for real API data, orange `#d97036` for estimates). Stops
     are drawn as labeled markers (green start / blue mid / red end) with
     day labels and place names; stay-only days are folded into matching city
     labels when possible.
   - `map.fitBounds()` frames the whole route — this replaces the old Amap
     static-map approach, whose auto-fit was unreliable when both `paths` and
     `markers` were present (it squeezed the route into a corner).
   - A shareable `route-map.png` is produced by rendering the same Leaflet
     page headless via **Playwright** and screenshotting it. Playwright is an
     **optional** dependency: when it is not installed or screenshotting fails,
     a clearly marked `route-map.svg` schematic is generated as the static
     fallback and the interactive HTML map still works.

Failure handling:

- Retry geocoding and driving-route network errors, API failures, empty results,
  and malformed success responses up to three times with bounded backoff.
- Preserve the final lookup failure in leg metadata before falling back.
- If API quota, key, or network fails, do not block HTML generation.
- Use estimates and schematic SVG only as a preview, mark `estimated: true`, and tell the user to verify.

Static map constraints (historical, applies only if you revert to the Amap
static-map API — the current implementation uses Leaflet instead):

- Maximum image size is `1024*1024`.
- `markers` and `labels` are limited, so prefer major stops when a trip has many points.
- `paths` has a low overlay count limit. Combine route points into one simplified path for whole-trip maps.
- **Known issue:** when both `paths` and `markers` are sent, Amap's auto-fit
  miscomputes the viewport and squeezes the route into ~50% of the image.
  Passing `location`/`zoom` does not help (they are ignored when overlays are
  present). This is why the project moved to Leaflet for map rendering.

Estimate fallback:

- Distance: haversine distance times a road factor when coordinates are known.
- If coordinates are unknown, use a low-confidence placeholder value and mark it clearly.
- Duration: distance divided by an average long-distance driving speed.
- Toll: distance times a per-kilometer toll factor, rounded to the nearest yuan.

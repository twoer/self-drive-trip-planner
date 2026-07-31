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

Lookup sequence:

1. Geocode each stop name to `lng,lat`.
2. Call driving route planning for each adjacent origin/destination pair.
3. Read distance in meters and convert to kilometers.
4. Read duration in seconds and convert to minutes.
5. Read tolls if present. If tolls are absent, mark toll as estimated or unknown.
6. Collect step polylines when available and keep them in JSON for route drawing.
7. Render the map with **Leaflet + Amap tiles** (see `scripts/leaflet_map.py`):
   - The interactive map is embedded in `trip.html` and shows the **real driving
     route** (the polylines from step 5) on top of public Amap raster tiles
     (`webrd0{1-4}.is.autonavi.com`). No web-service key is needed for the
     tiles — only for the routing/geocoding calls above.
   - Each leg is drawn with its own polyline; color reflects data source
     (blue `#2c6bb2` for real API data, orange `#d97036` for estimates). Stops
     are drawn as circle markers (green start / blue mid / red end) with
     A/B/C... letters explained in the on-map legend and the HTML overview.
   - `map.fitBounds()` frames the whole route — this replaces the old Amap
     static-map approach, whose auto-fit was unreliable when both `paths` and
     `markers` were present (it squeezed the route into a corner).
   - A shareable `route-map.png` is produced by rendering the same Leaflet
     page headless via **Playwright** and screenshotting it. Playwright is an
     **optional** dependency: when it is not installed, PNG generation is
     skipped silently and the interactive HTML map still works.

Failure handling:

- If geocoding fails, retry with the raw user label plus nearby province/city context when the user provided it.
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

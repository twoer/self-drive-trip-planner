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
7. Generate `route-map.png` with the static map API:
   - Use `paths` for the driving route polyline.
   - Omit explicit `location` and `zoom` for overview maps unless there is a strong reason; let the provider auto-fit route paths and markers.
   - Use provider-drawn `markers` for stop positions so markers align with the route.
   - Draw a local annotation panel on top of the downloaded map image.
   - Explain marker letters in the panel with the day each stop is reached. Do not merge departure and arrival days into labels such as `D1/D2` unless the user explicitly asks for overnight continuity.
   - For whole-trip overview maps, mark at most 10 stops with provider-drawn markers. If the route has more stops, select the start, end, daily endpoints, and evenly distributed major stops; keep the complete stop list in JSON/HTML instead of drawing local projected markers.
   - Put daily route, duration, and toll details in a compact summary panel instead of scattering metric callouts across the map.

Failure handling:

- If geocoding fails, retry with the raw user label plus nearby province/city context when the user provided it.
- If API quota, key, or network fails, do not block HTML generation.
- Use estimates and schematic SVG only as a preview, mark `estimated: true`, and tell the user to verify.

Static map constraints to respect:

- Maximum image size is `1024*1024`.
- `markers` and `labels` are limited, so prefer major stops when a trip has many points.
- `paths` has a low overlay count limit. Combine route points into one simplified path for whole-trip maps.
- If the route has many legs, keep the map labels limited to `D几 + 地点名` and move detailed metrics into the summary panel or HTML overview cards.

Estimate fallback:

- Distance: haversine distance times a road factor when coordinates are known.
- If coordinates are unknown, use a low-confidence placeholder value and mark it clearly.
- Duration: distance divided by an average long-distance driving speed.
- Toll: distance times a per-kilometer toll factor, rounded to the nearest yuan.

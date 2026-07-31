# Output Contract

The CLI writes a stable set of files so an agent can verify and summarize results without guessing.

## Standard Modes

Modes `auto`, `estimate`, and `accurate` write:

```text
<out>/
  trip-data.json
  trip.html
  manifest.json
  route-map.png | route-map.svg
```

- `trip-data.json`: normalized route data, metrics, source metadata, map metadata.
- `trip.html`: standalone mobile-friendly itinerary page with an embedded interactive Leaflet map.
- `manifest.json`: machine-readable run summary, file contract, data source, counts, totals, and warnings.
- `route-map.png`: optional Playwright screenshot of the Leaflet map when available.
- `route-map.svg`: schematic fallback when PNG generation is unavailable.

Mode `publish-demo` writes the same contract, except the HTML entry is
`index.html` so the output directory can be served directly by GitHub Pages:

```text
docs/
  trip-data.json
  index.html
  manifest.json
  route-map.png | route-map.svg
```

## Data-Only Mode

Mode `data-only` writes:

```text
<out>/
  trip-data.json
  manifest.json
```

It skips HTML and map image generation.

## Manifest Shape

```json
{
  "schema_version": 1,
  "mode": "estimate",
  "title": "Demo 自驾游",
  "start_date": "2026-07-17",
  "data_source": "amap",
  "source_counts": {"amap": 13},
  "files": {
    "data": "trip-data.json",
    "manifest": "manifest.json",
    "html": "trip.html",
    "map_image": "route-map.png"
  },
  "map": {
    "file": "route-map.png",
    "source": "leaflet-playwright-screenshot",
    "fallback": false
  },
  "totals": {
    "distance_km": 3918.7,
    "duration_min": 2838,
    "toll_cny": 2444.0
  },
  "counts": {
    "days": 10,
    "driving_days": 8,
    "legs": 13,
    "estimated_legs": 0
  },
  "warnings": []
}
```

## Agent Reporting Checklist

After running the script:

- Read `manifest.json` first.
- Verify every non-null file in `manifest.files` exists.
- Read `manifest.data_source`, `manifest.source_counts`, and `manifest.warnings`.
- Summarize `manifest.totals` and the output directory.
- If `manifest.warnings` is non-empty, include the warnings in the final response.
- If `mode` is `accurate` or `publish-demo`, treat a non-zero CLI exit code as a failed run even when partial files exist.

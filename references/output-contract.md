# Output Contract

The CLI writes a stable set of files so an agent can verify and summarize results without guessing.
Before a successful run exits, the CLI re-checks the generated directory with
`scripts/verify_outputs.py`. Contract failures are printed to stderr and return
exit code `4`.

Each run builds the current mode's generated files in a same-filesystem staging
directory, then replaces the previous generated-file set. If generation or
publication fails, the previous set is preserved or restored. The verifier
rejects stale generated files such as an old `trip.html`, `index.html`,
`route-map.png`, `route-map.svg`, `budget-summary.png`, `budget-summary.svg`,
or `trip.pdf` when those files are not
referenced by `manifest.files`.

The verifier also enforces that every `trip-data.json` day has a non-empty,
unique normalized `day` label such as `D1` or `D2`, because route markers,
calendar labels, scenic fee attribution, and daily rollups all treat that label
as a stable day key.
Each day must also include a non-empty string title, a string-only notes list,
finite non-negative numeric daily metric fields, a boolean `estimated` equal to
the aggregate leg state, and a legs list so HTML rendering and metric rollups
consume the same normalized structure.
Generated trip data must include at least one driving leg.
The verifier checks that `budget` has the expected CNY schema, that
`budget.configured` is a boolean, that budget items sum to their category
totals, and that category totals sum to `budget.total_cny`.
Budget item rows must also contain renderable label/detail strings; optional
component rows and missing-attraction reminders must match their documented
object shapes. Budget categories are a closed set (`toll`, `vehicle_energy`,
`hotel`, `meal`, `attraction`, and `misc`), and budget top-level fields follow
the documented closed schema. Route metrics and budget amounts must be finite and
non-negative; malformed JSON numeric extensions such as `NaN` and `Infinity`
are rejected.
Budget assumptions are also verified against trip day/distance totals,
passenger count types, and the calculated EV, hotel, and meal category totals.
Budget item/component arithmetic is reproducible from unit prices and
quantities; per-person and ticket quantities must match passenger assumptions.
When present, leg `origin`, `destination`, and `polyline` fields must use
finite, in-range numeric coordinates so map rendering cannot silently consume
malformed geometry. A one-point polyline is invalid.
Leg `from`, `to`, and `source` must be non-empty strings. Leg `source` must be
one of `amap` or `estimated`; optional `lookup_error` must be a non-empty
string; `accurate` and `publish-demo` outputs must contain only complete,
non-estimated Amap leg data, including origin, destination, and a route
polyline with at least two points.
The verifier checks the manifest's top-level schema before deeper consistency
checks: `schema_version` must be `1`, `title` must be a non-empty string, `start_date`
must be `null` or a valid `YYYY-MM-DD` date string, `data_source` must be a
non-empty string, and `counts` / `source_counts` values must be non-negative
integers. All documented top-level fields are required and unknown top-level
fields are rejected.
User-facing title, place, note, label, and warning strings cannot contain only
whitespace. Warning lists cannot contain duplicates, and known derived warnings
are rejected after their triggering condition no longer exists.
File references in `manifest.files` are mode-specific, not arbitrary existing
paths: data and manifest files must be `trip-data.json` and `manifest.json`;
standard modes use `trip.html`; `publish-demo` uses `index.html`; map images
must be `route-map.png` or `route-map.svg`; and PDF output, when present, must
be `trip.pdf`.
When a visual mode has a configured budget with item rows, `budget_image` must
reference `budget-summary.png` or `budget-summary.svg`. It must be `null` for
unconfigured budgets, empty item lists, and `data-only` mode.
Map metadata is a closed state contract: `leaflet-playwright-screenshot`
requires `route-map.png` and `fallback=false`; `fallback-svg` requires
`route-map.svg` and `fallback=true`. The same map object must appear in both
`manifest.json` and `trip-data.json`.
If Playwright is discovered but route-map rendering fails, the browser failure
is preserved in `trip-data.json.map_png_error` and surfaced in manifest warnings
before the SVG fallback is published.
If the SVG fallback also fails, `trip-data.json.map_svg_error` preserves that
failure and the manifest surfaces both causes. Generated error fields must be
non-empty strings when present.
The editorial budget asset uses a fixed 16:10 canvas. The preferred PNG is
3200x2000 for article publishing; if Playwright is unavailable or fails, the
1600x1000 SVG is retained. A Playwright failure is preserved in
`trip-data.json.budget_image_png_error`, and manifest warnings disclose both
the failure and SVG fallback.
For non-data-only output, the verifier also checks that the HTML contains the
Leaflet map container, Leaflet script and stylesheet, embedded map data, and a
link to the current static map asset. When a budget summary exists, the cost tab
links directly to that pre-generated article asset for download; it does not
capture the cost-tab DOM. PNG files must have a PNG signature; SVG
fallbacks must parse as SVG XML and contain rendered elements.
The embedded map data is structured JSON and must exactly match the compact
Leaflet projection rebuilt from `trip-data.json`.
The verifier also checks that `manifest.title` and `manifest.start_date` match
the same fields in `trip-data.json` so reporting and rendering consume one
consistent trip identity.

## Standard Modes

Modes `auto`, `estimate`, and `accurate` write:

```text
<out>/
  trip-data.json
  trip.html
  manifest.json
  route-map.png | route-map.svg
  budget-summary.png | budget-summary.svg (when budget items are configured)
  trip.pdf (optional, only with --pdf)
```

- `trip-data.json`: normalized route data, metrics, source metadata, map metadata.
- `trip.html`: standalone mobile-friendly itinerary page with an embedded interactive Leaflet map.
- `manifest.json`: machine-readable run summary, file contract, data source, counts, totals, and warnings.
- `route-map.png`: optional Playwright screenshot of the Leaflet map when available.
- `route-map.svg`: schematic fallback when PNG generation is unavailable.
- `budget-summary.png`: standalone editorial trip-scale and cost overview for
  article headers, generated at 3200x2000.
- `budget-summary.svg`: 1600x1000 fallback when budget PNG rendering is
  unavailable.
- `trip.pdf`: optional PDF export when `--pdf` is requested and Playwright is available.
  The verifier checks its PDF header and end-of-file marker; a run carrying
  `pdf_error` cannot also publish a PDF reference.
  PDF and PNG generation use the same discovered Playwright Python runtime.

Mode `publish-demo` writes the same contract, except the HTML entry is
`index.html` so the output directory can be served directly by GitHub Pages:

```text
docs/
  trip-data.json
  index.html
  manifest.json
  route-map.png | route-map.svg
  budget-summary.png | budget-summary.svg (when budget items are configured)
```

## Data-Only Mode

Mode `data-only` writes:

```text
<out>/
  trip-data.json
  manifest.json
```

It skips HTML and map image generation.
It also skips budget summary image generation.
It also rejects PDF references because PDF rendering requires generated HTML.

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
    "map_image": "route-map.png",
    "budget_image": "budget-summary.png",
    "pdf": "trip.pdf"
  },
  "map": {
    "file": "route-map.png",
    "source": "leaflet-playwright-screenshot",
    "fallback": false
  },
  "budget": {
    "currency": "CNY",
    "configured": true,
    "total_cny": 7344.5,
    "category_totals": {
      "toll": 2444.0,
      "vehicle_energy": 940.5,
      "hotel": 2700.0,
      "meal": 1000.0,
      "attraction": 260.0
    },
    "assumptions": {
      "trip_days": 10,
      "passengers": {
        "adults": 2,
        "children_under_1_2m": 1,
        "children_over_1_2m": 0
      }
    }
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
- Confirm the CLI printed `Verified: output contract`. For an existing output
  directory, run `python3 scripts/verify_outputs.py <out>` before reporting it
  as complete.
- Verify every non-null file in `manifest.files` exists.
- Read `manifest.data_source`, `manifest.source_counts`, and `manifest.warnings`.
- Summarize `manifest.totals` and the output directory.
- If `manifest.budget.configured` is true, summarize `manifest.budget.total_cny`; otherwise mention that the cost tab contains an activation reminder.
- If `manifest.files.budget_image` is non-null, report it as the article-ready
  cost overview asset; disclose SVG fallback warnings.
- If `manifest.warnings` is non-empty, include the warnings in the final response.
- If `mode` is `accurate` or `publish-demo`, treat a non-zero CLI exit code as a failed run even when partial files exist.

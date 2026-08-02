# Architecture

This skill is intentionally built as a local, script-first pipeline. The CLI is
the public integration surface for agents, while smaller modules own the
business rules that are likely to change.

## Module Boundaries

- `scripts/route_trip.py`
  - CLI argument parsing and end-to-end orchestration.
  - File output sequencing and final output-contract verification.
  - Compatibility re-exports for historical tests and agent callers, such as
    `route_trip.build_budget()`, `route_trip.enrich()`, and
    `route_trip.generate_html()`.
- `scripts/itinerary_parser.py`
  - Compact itinerary text parsing (`D1`, `A 到 B`, stay notes, multi-stop
    connector lines).
- `scripts/trip_pipeline.py`
  - Reusable generation pipeline for mode resolution, natural-language budget
    merging, route enrichment, output directory selection, and file writing.
  - `generate_trip_output()` is the shared end-to-end API for text-to-output
    generation, output-contract verification, and accurate/publish-demo failure
    detection.
  - Prefer this module when adding non-CLI entry points such as future editors,
    automations, or batch generation.
- `scripts/run_demo.py` and `scripts/generate_demo_batch.py`
  - Demo entry points that call `trip_pipeline.py` directly.
  - Keep demo/batch behavior aligned with CLI output verification without
    shelling out to `route_trip.py`.
- `scripts/html_renderer.py`
  - Mobile-first standalone HTML rendering.
  - Calendar/date labels, display-friendly distance/duration labels, budget tab
    rendering, and Leaflet snippet embedding.
  - Keep generated HTML UI rules aligned with `references/ui-generation-baseline.md`.
- `scripts/routing.py`
  - Amap/Gaode key discovery and `.env` loading.
  - Provider-style geocoding and driving-route lookup through
    `AmapRouteProvider`, estimate fallback through `EstimateRouteProvider`, and
    day/total metric enrichment through `RouteEnricher`.
  - Provider calls retry network, API-status, and malformed-response failures
    up to three times with bounded backoff before estimate fallback.
  - Optional successful-response persistence through `JsonRouteCache` when
    `SDTP_ROUTE_CACHE` points to a local JSON file.
  - Cache schema, coordinate ranges, finite metrics, and route geometry are
    validated before reuse; invalid entries fall through to provider lookup.
  - Concurrent cache writers serialize updates, merge the latest on-disk data,
    and publish through a unique same-directory temporary file plus atomic replace.
  - This is the extension point for additional map providers.
- `scripts/budget.py`
  - Natural-language budget parsing.
  - CLI budget argument parsers.
  - EV, hotel, meal, attraction, component fee, child ticket, and missing scenic
    spot calculations.
  - This is the extension point for new budget categories or destination rules.
- `scripts/budget_image.py`
  - Fixed 16:10 editorial budget-summary composition for article sharing.
  - Generates a 1600x1000 SVG source and prefers a 3200x2000 Playwright PNG;
    retains the SVG as the portable fallback.
  - Owns visual selection and text fitting for trip scale, category composition,
    itemized costs, and missing scenic-fee reminders.
- `scripts/manifest_contract.py`
  - `manifest.json` source counts, warning generation, file contract, and
    accurate-mode failure detection.
  - Owns the shared mode constants used by CLI/demo entry points, pipeline
    mode resolution, and output verification.
  - Keep this module aligned with `references/output-contract.md`.
  - Owns manifest top-level and file-field sets; verifiers import these sets
    instead of duplicating contract keys.
- `scripts/leaflet_map.py`
  - Compact map-data projection for Leaflet.
  - Interactive map snippet and optional Playwright PNG screenshot.
  - Responsive route-focus mask that preserves nearby map context while
    de-emphasizing labels, roads, and boundaries outside the route corridor.
  - Client-side HTML escaping for map labels and popups.
- `scripts/output_assets.py`
  - SVG schematic fallback route rendering.
  - Static route-map asset generation and optional PDF export.
  - PNG and PDF exports share the same Playwright interpreter discovery so a
    runtime available outside the project virtualenv behaves consistently.
  - This is the boundary for optional Playwright/PDF behavior.
- `scripts/output_reporter.py`
  - Shared console reporting for output runs.
  - Keep `Wrote`, `Sources`, warnings, verification failures, and optional
    `Open` lines consistent across CLI/demo entry points.
- `scripts/verify_outputs.py`
  - Standalone output-contract verifier for `manifest.json`, referenced files,
    `trip-data.json`, leg metadata, count/source consistency, HTML/route-map
    asset integrity, and required warning coverage for generated risk metadata.
  - Rebuilds the compact Leaflet projection from `trip-data.json` and compares
    it with the structured JSON embedded in generated HTML.
  - Imports closed manifest and budget field sets from their producer modules.
  - Use this after generation when an agent or CI needs a deterministic pass/fail
    signal.
- `scripts/skill_layout.py`
  - Shared install/package copy layout for runtime skill files.
  - Keep `install_skill.py` and `package_plugin.py` using this module so the
    local skill install and packaged plugin cannot drift.

## Execution Flow

1. A caller such as `route_trip.py`, `run_demo.py`, or `generate_demo_batch.py`
   reads or creates itinerary text.
2. Budget text is split and parsed by `budget.py`.
3. Day blocks and route legs are parsed by `itinerary_parser.py`.
4. `trip_pipeline.py` resolves mode/key behavior and passes the effective route
   key into `routing.py`.
5. Budget totals are calculated by `budget.py` through `trip_pipeline.py`.
6. Map image metadata is generated by `output_assets.py` and `leaflet_map.py`.
7. When configured budget rows exist, `budget_image.py` generates the standalone
   article-ready budget summary asset.
8. `trip-data.json`, HTML from `html_renderer.py`, optional PDF, and
   `manifest.json` are generated in a same-filesystem staging directory.
9. `manifest_contract.py` provides the machine-readable run summary.
10. `trip_pipeline.py` publishes the staged generated-file set with rollback of
   the previous set on publication failure, then verifies the output contract
   before a caller reports success. `output_reporter.py` prints a consistent
   run summary.

## Invariants

- `trip-data.json` must be written before `manifest.json`.
- Each output run must rebuild mode-specific generated metadata from scratch;
  stale `map`, `map_png_error`, `map_svg_error`, or `pdf_error` values from a
  reused data object must not leak into a later run.
- Generation failures must leave the previous generated-file set and caller's
  data object unchanged. Files are published only after staging completes.
- When HTML is generated, the embedded Leaflet map is the primary route view.
- `route-map.png` is optional; `route-map.svg` is the static fallback when PNG
  screenshotting is unavailable.
- Configured budget rows in visual modes require `budget-summary.png` or its
  `budget-summary.svg` fallback; unconfigured budgets and `data-only` mode must
  not publish either asset.
- `accurate` and `publish-demo` modes fail if any driving leg is not complete
  Amap data.
- Estimated metrics must be marked in leg data and surfaced in warnings.
- Manifest top-level fields are a closed schema; missing and unknown fields fail
  verification instead of being silently ignored.
- Missing scenic fees are reminders only and must not change `budget.total_cny`.

## Maintenance Guidance

- Add map provider behavior in `routing.py`, not in `route_trip.py`.
- Keep route provider orchestration in `RouteEnricher`; callers should pass the
  already-resolved key instead of making routing read process state twice.
- Keep persistent route caches opt-in and local; cache successful Amap
  geocoding/routes only, never failed lookups or estimate fallback metrics.
- Add parser behavior in `itinerary_parser.py`, not in the CLI.
- Add mode/key/budget orchestration behavior in `trip_pipeline.py`, not in the
  CLI.
- Reuse `trip_pipeline.py` from demo or automation scripts instead of invoking
  the CLI as a subprocess.
- Use `generate_trip_output()` for new output-generating entry points so mode
  preflight, manifest verification, and accuracy-mode gates stay consistent.
- Use `output_reporter.py` for console output from successful or failed runs.
- Add budget categories and ticket rules in `budget.py`, not in HTML rendering.
- Add article budget-image composition behavior in `budget_image.py`, not in
  HTML rendering or budget calculation.
- Add manifest fields in `manifest_contract.py` and update
  `references/output-contract.md` in the same change.
- Add generated HTML behavior in `html_renderer.py`, not in route parsing or map
  enrichment modules.
- Add static map/PDF behavior in `output_assets.py`, not in CLI argument
  handling.
- Keep generated HTML UI rules aligned with `references/ui-generation-baseline.md`.
- Keep verifier checks aligned with `references/output-contract.md`.
- Keep install/package file selection in `skill_layout.py`, not duplicated in
  installation or packaging entry points.
- Avoid reintroducing the old Amap static-map/Pillow rendering path; Leaflet is
  the current map architecture.

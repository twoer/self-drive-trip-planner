---
name: self-drive-trip-planner
description: Create agent-verifiable self-driving trip outputs from structured itinerary text such as D1/D2 day blocks and "A 到 B" legs. Use when Codex needs to parse road-trip stops, enrich point-to-point legs with distance, duration, tolls, generate normalized JSON, manifest.json, mobile-friendly Chinese itinerary HTML, and an interactive route map/PNG/SVG with source and warning metadata.
---

# Self-Drive Trip Planner

## Workflow

1. Parse the user's itinerary text into day blocks and driving legs.
2. Enrich every leg with driving metrics:
   - Prefer a map API when credentials are available.
   - Fall back to clearly marked estimates if an API key is unavailable or a lookup fails.
3. Choose a CLI mode:
   - `--mode estimate` for quick no-key previews.
   - `--mode accurate` when all driving legs must use Amap data.
   - `--mode publish-demo` for GitHub Pages/static demo generation.
   - `--mode data-only` when only JSON/manifest outputs are needed.
4. Generate a normalized `trip-data.json` and `manifest.json`. Read `references/output-contract.md` before changing output files or explaining the manifest.
   - When budget inputs are provided, calculate a rough total budget and write it under `budget`.
   - When configured budget item rows exist in a visual mode, generate a
     standalone 16:10 `budget-summary.png` article asset (3200x2000), with a
     1600x1000 SVG fallback when Playwright is unavailable.
   - When no budget inputs are provided, keep `budget.configured=false` and show an activation reminder in the generated cost tab.
   - The CLI validates the written output directory with `scripts/verify_outputs.py` before reporting success.
5. Generate an interactive map showing the **real driving route**:
   - Embed a Leaflet map in `trip.html` using Amap raster tiles (no tile key needed); draw each leg's actual polyline from the routing API.
   - Color each leg by data source: blue for real API data, orange for estimates.
   - Use labeled stop markers with day labels and place names, with start (green) and end (red) highlighted; let `fitBounds` frame the whole route.
   - Keep the map uncluttered: put daily route, duration, toll details in the HTML overview cards and an on-map legend, not as scattered callouts along the route.
   - Optionally produce `route-map.png` by screenshotting the same Leaflet page with Playwright (an optional dependency); when Playwright is missing or screenshotting fails, generate `route-map.svg` as the static fallback — the interactive HTML map still works.
   - Treat the schematic SVG as a clearly disclosed static fallback; the embedded Leaflet map remains the primary route view when HTML is generated.
6. Generate a mobile-first HTML itinerary page inspired by the user's reference style:
   - Header with trip title and route summary.
   - Tabs for route overview, daily itinerary, and cost estimate.
   - When calculated budget rows exist, generate a standalone editorial budget summary image for article sharing.
   - Daily cards with each driving segment.
   - Lucide icons, compact cards, and Chinese labels.
7. Embed the interactive map in the HTML. Link to `route-map.png` or `route-map.svg` when a static image exists.

## Quick Start

Use the bundled script for repeatable work:

```bash
python3 scripts/route_trip.py input.txt --out ./trip-output --title "2026 暑假自驾游"
```

For agent-safe runs, prefer explicit modes:

```bash
python3 scripts/route_trip.py input.txt --out ./trip-output --title "2026 暑假自驾游" --mode accurate
```

Set one of these environment variables before running if map enrichment is needed:

```bash
export AMAP_KEY="your-gaode-web-service-key"
```

or:

```bash
export GAODE_KEY="your-gaode-web-service-key"
```

Optionally set a local route cache so repeated accurate/demo runs can reuse
successful Amap geocoding and route responses:

```bash
export SDTP_ROUTE_CACHE=".zcode/self-drive-trip-planner-routes.json"
```

If no key is available, still run the script. Keep the generated estimates visibly marked and tell the user they should verify route metrics before booking or departure.

This skill is intentionally text-first. When a user wants to edit a trip, ask for
the updated D1/D2 text or update the input file, then rerun the CLI and verify
the generated manifest.

## Input Rules

Accept compact Chinese itinerary text:

```text
D1
合肥 到 岳阳

D2
岳阳 到 韶山

D5
荔波 到 小七孔
小七孔 到 中国天眼
中国天眼 到 安顺
```

Also accept `->`, `→`, `回`, `回到`, `返回`, `到达`, `前往`, `去往`,
`至`, spaced dash connectors such as `合肥 - 岳阳`, and multi-stop lines such
as `荔波 到 小七孔 到 中国天眼 到 安顺`.

Lines without route connectors, such as `贵阳市区`, are treated as non-driving stay notes for that day. Keep them in `trip-data.json` and the HTML, but do not include them in driving distance, duration, toll, or route-map paths.

Each generated trip must include at least one driving leg. Reject note-only
inputs with a clean error instead of producing a route output with zero legs.

Day labels must start at `D1`. Reject `D0` or other non-positive day labels
with a clean error. If note-only text appears before the first explicit day
label, attach it to that first day; if route lines appear before explicit day
labels, assign them to an implicit day label that does not collide with explicit
labels. Reject duplicate explicit day labels with a clean error. Also accept day
labels with same-line content, such as `D1：合肥 到 岳阳`, `Day2 岳阳 到 韶山`,
`D3：贵阳市区`, `第1天：合肥 到 岳阳`, or `第二天 岳阳 到 韶山`.

Accept a leading or trailing natural-language `费用预算：` section. Do not treat
it as a day note. Parse budget details such as:

```text
费用预算：
我们是两大一小（高于 1.2m），开电车，电价 1.5 元/度，百公里电耗 16 度。
酒店每晚 300 元，餐费每天 100 元。
景点门票：小七孔成人票 120 元，中国天眼成人票 140 元。
```

Also support component-style fees:

```text
景点门票：天眼景区门票不要钱，摆渡车 50 元一人，保险 10 元一人。
```

Budget rules:

- Hotel nights default to trip days minus one.
- Meal days default to trip day count.
- Approximate single amounts such as `酒店每晚约300元`, `酒店每晚300元左右`, and `餐费每天约100元` are accepted as configured amounts.
- Ambiguous hotel, meal, EV price/consumption, ticket, component, or misc-fee ranges such as `300-400 元`, `电价 1.2-1.5 元/度`, or `成人票 100-120 元` are not included in totals; surface them in `budget.warnings` and `manifest.warnings` until the user provides one amount or a CLI override.
- Adult attraction tickets use full price.
- Children below 1.2m are free by default.
- Children at or above 1.2m use half adult price by default.
- Per-person fee components such as shuttle bus, sightseeing bus, and insurance are multiplied by all travelers.
- Detect known scenic stops such as `小七孔`, `黄果树`, `韶山`, and `中国天眼`; when a scenic stop has no configured ticket/component fee, list it as missing in `budget.missing_attractions` and the `费用` tab. Do not include missing scenic fees in the total.
- If the user provides only attraction names without prices, browse current official or authoritative pages for ticket/component prices, then add the discovered prices to the budget input. If no reliable source is found, leave the item out of the total and report it as "待核实"; do not invent prices.

Read `references/architecture.md` before changing module boundaries or moving responsibilities between scripts. Read `references/data-schema.md` when changing the parser, consuming user-provided JSON, or explaining the normalized schema. Read `references/output-contract.md` when changing output files, `manifest.json`, modes, or final reporting behavior.

## Map Service

Prefer Gaode/Amap Web Service for mainland China driving routes because it can return driving distance, duration, toll, and route polyline data. Render maps through the Leaflet helper; do not reintroduce the old Amap static-map/Pillow rendering path. Read `references/map-services.md` before changing the map lookup behavior or adding another provider.

Do not invent precise tolls. If a toll is estimated, mark it as estimated in JSON and in user-facing summaries.

## HTML UI Rules

When generating or editing HTML/CSS, follow `references/ui-generation-baseline.md`.

Hard requirements:

- Use flex or inline-flex plus centered alignment and gap for icon + text pairs.
- Do not use left/right margins to separate icons from text.
- Give icons explicit width/height and prevent shrinking.
- Use one consistent gap token per tab group, toolbar, or action group.
- Prefer reusable utilities such as `.ui-icon-text` and `.ui-action-group` in generated standalone HTML.

## Output Checklist

Before finishing a trip output task:

- Confirm the CLI printed `Verified: output contract`, or run `python3 scripts/verify_outputs.py <out>` manually for an existing output directory.
- Confirm every requested leg appears in `trip-data.json`.
- Confirm each leg has distance, duration, toll, and source metadata.
- Confirm `manifest.json` exists and every non-null file in `manifest.files` exists.
- Confirm the HTML opens without build tooling when not using `--mode data-only`.
- Confirm the route map file exists when not using `--mode data-only`. Prefer `route-map.png`; use `route-map.svg` only as a clearly disclosed fallback.
- When configured budget rows exist outside `data-only` mode, confirm
  `manifest.files.budget_image` references an existing `budget-summary.png` or
  `budget-summary.svg`; report SVG fallback warnings.
- If `--pdf` is requested, confirm `trip.pdf` exists or report the PDF warning from `manifest.json`.
- State `manifest.data_source`, totals, output directory, and every warning in `manifest.warnings`.

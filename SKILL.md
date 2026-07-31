---
name: self-drive-trip-planner
description: Create self-driving trip outputs from structured itinerary text such as D1/D2 day blocks and "A 到 B" legs. Use when Codex needs to parse road-trip stops, enrich each point-to-point leg with driving distance, duration, tolls, generate a mobile-friendly Chinese itinerary HTML page, and create a route map image/SVG with labels for route, distance, time, and toll.
---

# Self-Drive Trip Planner

## Workflow

1. Parse the user's itinerary text into day blocks and driving legs.
2. Enrich every leg with driving metrics:
   - Prefer a map API when credentials are available.
   - Fall back to clearly marked estimates if an API key is unavailable or a lookup fails.
3. Generate a normalized `trip-data.json` before creating visual outputs.
4. Generate a map-based route image:
   - Prefer a real static map image with route polylines and a custom readable annotation layer.
   - Let the map provider draw route markers so marker positions stay aligned with the route.
   - Use marker letters (`A`, `B`, `C`, ...) on the map, then explain those letters in a compact panel.
   - Mark the start city and end city explicitly in the panel, such as `A 起点D1 合肥` and `H 终点D5 安顺`.
   - Keep the map itself uncluttered: do not place city-name labels or every segment's metrics beside the route line.
   - Put daily route, duration, toll details, and marker legend in the map panel, usually at the top-left.
   - Use the schematic SVG only as a fallback when map credentials/network/polyline data are unavailable.
5. Generate a mobile-first HTML itinerary page inspired by the user's reference style:
   - Header with trip title and route summary.
   - Tabs for daily itinerary, route overview, toll summary, and total stats.
   - Daily cards with each driving segment.
   - Lucide icons, compact cards, and Chinese labels.
6. Embed the map-based route image in the HTML. Keep distance, duration, and toll details in the route overview and toll tabs when the static map cannot render long text labels cleanly.

## Quick Start

Use the bundled script for repeatable work:

```bash
python3 scripts/route_trip.py input.txt --out ./trip-output --title "2026 暑假自驾游"
```

Set one of these environment variables before running if map enrichment is needed:

```bash
export AMAP_KEY="your-gaode-web-service-key"
```

or:

```bash
export GAODE_KEY="your-gaode-web-service-key"
```

If no key is available, still run the script. Keep the generated estimates visibly marked and tell the user they should verify route metrics before booking or departure.

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

Also accept `->`, `→`, `回`, `返回`, and multi-stop lines such as `荔波 到 小七孔 到 中国天眼 到 安顺`.

Lines without route connectors, such as `贵阳市区`, are treated as non-driving stay notes for that day. Keep them in `trip-data.json` and the HTML, but do not include them in driving distance, duration, toll, or route-map paths.

Read `references/data-schema.md` when changing the parser, consuming user-provided JSON, or explaining the normalized schema.

## Map Service

Prefer Gaode/Amap Web Service for mainland China driving routes because it can return driving distance, duration, toll, route polyline, and static map images with markers/paths. Read `references/map-services.md` before changing the map lookup behavior or adding another provider.

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

- Confirm every requested leg appears in `trip-data.json`.
- Confirm each leg has distance, duration, toll, and source metadata.
- Confirm the HTML opens without build tooling.
- Confirm the route map file exists. Prefer `route-map.png` from a real map provider with readable custom annotations; use `route-map.svg` only as a clearly disclosed fallback.
- State whether data came from the map API or estimates.

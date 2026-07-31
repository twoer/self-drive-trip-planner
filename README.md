# Self-Drive Trip Planner Skill

Codex skill for turning compact Chinese self-drive itinerary text into:

- normalized `trip-data.json`
- mobile-friendly Chinese itinerary HTML
- interactive route map plus optional shareable PNG/SVG image
- clearly marked estimated fallback output when no map API key is available
- machine-readable `manifest.json` so agents can verify files, warnings, and data source

## Live Demo

[Open the generated static demo](https://twoer.github.io/self-drive-trip-planner/)

The published demo is generated from `examples/simple-trip.txt` with Gaode/Amap API data, then committed as static HTML/JSON/image files under `docs/`. No API key is stored in this repository.

## 30-Second Start

```bash
git clone https://github.com/twoer/self-drive-trip-planner.git
cd self-drive-trip-planner
make install
make setup
make demo
open trip-output/trip.html
```

`make demo` automatically uses Amap route data when `.env`, `AMAP_KEY`, or `GAODE_KEY` is configured. Without a key, it runs an estimated preview and records warnings in `trip-output/manifest.json`.

For accurate mainland China routes, create a Web Service key in the [Gaode/Amap Open Platform console](https://console.amap.com/dev/key/app) and put it in local `.env`:

```bash
AMAP_KEY=your-gaode-web-service-key
```

The local `.env` file is ignored by git and is not copied into generated plugin packages.

## Install As A Codex Skill

Install a clean copy into the default Codex skills directory:

```bash
make install-skill
```

Then ask Codex to use `$self-drive-trip-planner` with an itinerary.

## Plugin Package

Download the latest packaged plugin from GitHub Releases:

[self-drive-trip-planner-plugin.zip](https://github.com/twoer/self-drive-trip-planner/releases/download/v0.1.0/self-drive-trip-planner-plugin.zip)

Install this repository into your personal Codex plugin marketplace:

```bash
make install-plugin
```

This builds the plugin, copies it to `~/plugins/self-drive-trip-planner`, updates
`~/.agents/plugins/marketplace.json`, and runs
`codex plugin add self-drive-trip-planner@personal`. Start a new Codex task after
installing so the newly installed skill list is refreshed.

Build a clean skills-only Codex plugin package:

```bash
make package-plugin
```

This writes:

- `dist/self-drive-trip-planner/`
- `dist/self-drive-trip-planner-plugin.zip`

The package excludes generated trip outputs, local caches, `.env`, and repository metadata. It contains only the plugin manifest plus the skill files needed to run locally.

Validate the generated plugin package when the local Codex plugin validator is available:

```bash
make validate-plugin
```

Run the portable package checks used by CI:

```bash
make check-plugin-package
```

## CLI Usage

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run an estimated fallback preview:

```bash
python3 scripts/route_trip.py examples/simple-trip.txt --out ./trip-output --title "Demo 自驾游" --mode estimate
```

Run with required Gaode/Amap route data:

```bash
export AMAP_KEY="your-gaode-web-service-key"
python3 scripts/route_trip.py examples/simple-trip.txt --out ./trip-output --title "Demo 自驾游" --mode accurate
```

`GAODE_KEY` is also supported.

Mode summary:

- `auto`: default; use API when a key is configured, otherwise estimate.
- `estimate`: skip API and clearly mark estimated route metrics.
- `accurate`: require every driving leg to use complete Amap data; exits non-zero if not.
- `publish-demo`: like `accurate`, defaults output to `docs/` for GitHub Pages.
- `data-only`: write only `trip-data.json` and `manifest.json`.

Legacy `--no-api` is still accepted as an alias for `--mode estimate`.

Every run writes `manifest.json`; read it first when integrating from an agent.

### Optional: generate a shareable route-map image

`trip.html` always includes an interactive Leaflet map (real driving route,
pan/zoom/click) that needs no extra dependencies — only a browser with network
access to load the map tiles.

To additionally produce a standalone `route-map.png` (e.g. for sharing in
chat or embedding in a document), install Playwright:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

When Playwright is not installed, PNG generation is skipped silently; the
interactive HTML map is unaffected.

## Input Format

```text
D1
合肥 到 岳阳
D2
岳阳 到 韶山
D3
韶山 到 凤凰古城
D4
凤凰古城 到 荔波
D5
荔波 到 小七孔
小七孔 到 中国天眼
中国天眼 到 安顺
D6
安顺 到 黄果树
黄果树 到 贵阳
D7
贵阳市区
D8
贵阳 到 茅台镇红军桥
茅台镇红军桥 到 遵义会议遗址
遵义会议遗址 到 重庆
D9
重庆市区
D10
重庆 回 合肥
```

Supported route connectors: `到`, `回`, `返回`, `->`, `→`.

Lines without route connectors, such as `贵阳市区`, are treated as non-driving stay notes. They appear in JSON and HTML, but do not count toward driving distance, duration, toll, or route-map paths.

## API Keys And Safety

Do not commit API keys. Use environment variables:

- `AMAP_KEY`
- `GAODE_KEY`

If no key is available, the script uses coordinate-based estimates where possible and marks generated metrics with `source: "estimated"` and `estimated: true`.

Route distance, duration, tolls, and route polylines come from the configured map service when API mode is used. Users are responsible for following the provider's terms and verifying metrics before booking or departure.

## Agent Contract

This repository is shaped to be called by another agent with a low-friction contract:

- pass itinerary text to `scripts/route_trip.py`
- choose an explicit `--mode`
- read `manifest.json`
- verify every non-null path in `manifest.files`
- report `manifest.data_source`, `manifest.totals`, and `manifest.warnings`

For GitHub Pages, `--mode publish-demo` writes `docs/index.html` plus `trip-data.json`, `manifest.json`, and a route-map asset.

## Development

Run the fast checks:

```bash
python3 -m py_compile scripts/route_trip.py
python3 -m unittest discover -s tests
```

Generate a local estimated fallback demo:

```bash
make demo-estimate
```

Generate a local API-backed demo when `AMAP_KEY` or `GAODE_KEY` is configured:

```bash
make demo-api
```

Generate the GitHub Pages demo:

```bash
make pages-demo
```

Generate 20 dense random demo trips for UI stress testing:

```bash
make demo-batch
```

Generated outputs are ignored by git.

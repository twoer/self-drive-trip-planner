# Self-Drive Trip Planner Skill

Codex skill for turning compact Chinese self-drive itinerary text into:

- normalized `trip-data.json`
- mobile-friendly Chinese itinerary HTML
- route map image from Gaode/Amap when an API key is available
- clearly marked estimated fallback output when no map API key is available

## Install

Copy this folder into a Codex skills directory, for example:

```bash
cp -R self-drive-trip-planner ~/.codex/skills/
```

Then ask Codex to use `$self-drive-trip-planner` with an itinerary.

## CLI Usage

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Run with estimated fallback data:

```bash
python3 scripts/route_trip.py examples/simple-trip.txt --out ./trip-output --title "Demo 自驾游" --no-api
```

Run with Gaode/Amap route data:

```bash
export AMAP_KEY="your-gaode-web-service-key"
python3 scripts/route_trip.py examples/simple-trip.txt --out ./trip-output --title "Demo 自驾游"
```

`GAODE_KEY` is also supported.

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

Route distance, duration, tolls, static maps, and base map data come from the configured map service when API mode is used. Users are responsible for following the provider's terms and verifying metrics before booking or departure.

## Static Map Markers

Whole-trip overview maps use provider-drawn markers so marker positions stay aligned with the map. Static map services limit how many markers can be shown. This skill marks at most 10 overview stops:

- start
- end
- daily endpoints
- evenly distributed major stops

Complete stop and leg data remains in `trip-data.json` and the HTML even when some stops are omitted from the overview map.

## Development

Run the fast checks:

```bash
python3 -m py_compile scripts/route_trip.py
python3 -m unittest discover -s tests
```

Generate a local estimated demo:

```bash
python3 scripts/route_trip.py examples/simple-trip.txt --out ./trip-output --title "Demo 自驾游" --no-api
```

Generated outputs are ignored by git.

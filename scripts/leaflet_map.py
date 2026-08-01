"""Leaflet interactive map generation for the trip planner.

This module produces a self-contained Leaflet map that renders the *real*
driving route (using the polylines returned by the routing API) on top of
Amap tiles. It replaces the old Amap static-map approach, which suffered from
an auto-fit bug that squeezed the route into a corner of the image.

Two public entry points:

* ``build_leaflet_snippet(data)`` -> str
    Returns an HTML fragment (``<div>`` + inline ``<style>``/``<script>``)
    suitable for embedding inside ``trip.html``'s overview tab. The map is
    interactive (pan / zoom / click segments for details) and only needs
    network access to load the Leaflet CDN and Amap tiles — no API key.

* ``render_route_png(data, out_path)`` -> bool
    Renders a full-page version of the same Leaflet map and screenshots it
    with Playwright to produce ``route-map.png``. Returns ``False`` (and is
    safe to call) when Playwright is not installed — callers should treat PNG
    generation as an optional enhancement.
"""

from __future__ import annotations

import json
import html
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# CSS for the labeled stop markers (dot + name). Shared by snippet & PNG page.
STOP_MARKER_CSS = """
.trip-stop { background: transparent !important; border: none !important; }
.trip-stop-dot {
  display: inline-block; width: 10px; height: 10px; border-radius: 50%;
  border: 2px solid #fff; box-shadow: 0 0 0 1px rgba(0,0,0,0.25), 0 1px 3px rgba(0,0,0,0.3);
  vertical-align: middle;
}
.trip-stop-label {
  display: inline-block; margin-left: 4px; padding: 1px 6px;
  background: rgba(255,255,255,0.92); border-radius: 4px;
  font-size: 11px; font-weight: 600; color: #1f2937; white-space: nowrap;
  box-shadow: 0 1px 3px rgba(0,0,0,0.18); vertical-align: middle;
}
"""

LEAFLET_VERSION = "1.9.4"
LEAFLET_CSS = f"https://unpkg.com/leaflet@LEAFLET_VERSION/dist/leaflet.css".replace("LEAFLET_VERSION", LEAFLET_VERSION)
LEAFLET_JS = f"https://unpkg.com/leaflet@LEAFLET_VERSION/dist/leaflet.js".replace("LEAFLET_VERSION", LEAFLET_VERSION)

# Amap raster tiles (public, no web-service key required). ``webrd`` = standard
# road map in Chinese. Subdomains 01-04 spread the tile load.
AMAP_TILE_URL = "https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}"
AMAP_TILE_SUBDOMAINS = ["1", "2", "3", "4"]

ROUTE_COLOR_REAL = "#2c6bb2"      # blue — real API data
ROUTE_COLOR_ESTIMATE = "#d97036"  # orange — estimated data
MARKER_COLOR_START = "#25955b"    # green
MARKER_COLOR_END = "#d25240"      # red
MARKER_COLOR_MID = "#2c6bb2"      # blue

MAX_POINTS_PER_LEG = 80  # simplify each leg's polyline to keep HTML small


def json_for_script(value: Any) -> str:
    """Serialize JSON safely for direct embedding inside a ``<script>`` tag."""
    text = json.dumps(value, ensure_ascii=False)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _simplify_polyline(points: list[list[float]], max_points: int = MAX_POINTS_PER_LEG) -> list[list[float]]:
    """Reduce a polyline to at most ``max_points`` by even stride sampling.

    Keeps the first and last point so segments connect cleanly. The driving
    API returns thousands of points per leg; sampling preserves the route
    shape while shrinking the inlined JSON to a reasonable size.
    """
    if len(points) <= max_points:
        return points
    step = math.ceil(len(points) / max_points)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def build_map_data(data: dict[str, Any]) -> dict[str, Any]:
    """Project ``data`` into the compact shape the Leaflet client needs.

    Returns ``{title, totals, days:[{day,title,estimated,legs:[{points,...}]}],
    stops:[{name,lng,lat,day}]}``. Each leg's polyline is simplified; stops
    are de-duplicated by coordinate so the start/end markers line up.
    """
    days_out: list[dict[str, Any]] = []
    for day in data.get("days", []):
        legs_out: list[dict[str, Any]] = []
        for leg in day.get("legs", []):
            points = leg.get("polyline") or []
            if not points:
                # Fall back to origin->destination straight line if no polyline.
                origin = leg.get("origin")
                destination = leg.get("destination")
                if origin and destination:
                    points = [[origin["lng"], origin["lat"]], [destination["lng"], destination["lat"]]]
            if not points:
                continue
            legs_out.append({
                "from": leg.get("from", ""),
                "to": leg.get("to", ""),
                "distance_km": leg.get("distance_km", 0),
                "duration_min": leg.get("duration_min", 0),
                "toll_cny": leg.get("toll_cny", 0),
                "estimated": bool(leg.get("estimated")),
                "points": _simplify_polyline(points),
            })
        days_out.append({
            "day": day.get("day", ""),
            "title": day.get("title", ""),
            "distance_km": day.get("distance_km", 0),
            "duration_min": day.get("duration_min", 0),
            "toll_cny": day.get("toll_cny", 0),
            "estimated": bool(day.get("estimated")),
            "legs": legs_out,
        })

    # Collect ordered, de-duplicated stops for markers. Each stop accumulates
    # ALL days it is involved in (arrived / stayed / departed), so the map
    # labels never skip a day. e.g. 重庆 is reached on D8, stayed on D9,
    # departed on D10 → labeled "D8/D9/D10 重庆". A stay-only day (legs empty,
    # notes like "贵阳市区") is matched to an existing stop by name so its day
    # is folded into that city's label.
    stop_by_coord: dict[tuple[float, float], dict[str, Any]] = {}
    order: list[tuple[float, float]] = []

    def _add_day(stop_entry: dict[str, Any], day_label: str) -> None:
        days = stop_entry.setdefault("days", [])
        if day_label and day_label not in days:
            days.append(day_label)

    for day in data.get("days", []):
        day_label = day.get("day", "")
        for leg in day.get("legs", []):
            origin = leg.get("origin")
            if origin:
                key = (round(origin["lng"], 4), round(origin["lat"], 4))
                if key not in stop_by_coord:
                    stop_by_coord[key] = {"name": leg.get("from", ""), "lng": origin["lng"], "lat": origin["lat"], "days": []}
                    order.append(key)
                _add_day(stop_by_coord[key], day_label)
            destination = leg.get("destination")
            if destination:
                key = (round(destination["lng"], 4), round(destination["lat"], 4))
                if key not in stop_by_coord:
                    stop_by_coord[key] = {"name": leg.get("to", ""), "lng": destination["lng"], "lat": destination["lat"], "days": []}
                    order.append(key)
                _add_day(stop_by_coord[key], day_label)

    # Fold stay-only days (no legs) into the matching city by name so their
    # day appears in that city's label (e.g. D7 贵阳市区 -> 贵阳).
    name_index: dict[str, tuple[float, float]] = {}
    for key, stop in stop_by_coord.items():
        name_index.setdefault(stop["name"], key)
    for day in data.get("days", []):
        if day.get("legs"):
            continue  # only stay-only days
        day_label = day.get("day", "")
        note = " ".join(day.get("notes") or [])
        if not note:
            continue
        # Match the note text to a known stop name by substring (贵阳 <- 贵阳市区).
        matched_key = None
        for name, key in name_index.items():
            if name and (name in note or note in name):
                matched_key = key
                break
        if matched_key:
            _add_day(stop_by_coord[matched_key], day_label)

    # Build a readable day label: collapse consecutive runs like D8,D9,D10.
    def _collapse(days: list[str]) -> str:
        nums = []
        for d in days:
            m = re.search(r"(\d+)", d)
            if m:
                nums.append(int(m.group(1)))
        nums = sorted(set(nums))
        if not nums:
            return "/".join(days)
        parts = []
        run_start = prev = nums[0]
        for n in nums[1:]:
            if n == prev + 1:
                prev = n
                continue
            parts.append(f"D{run_start}" if run_start == prev else f"D{run_start}-D{prev}")
            run_start = prev = n
        parts.append(f"D{run_start}" if run_start == prev else f"D{run_start}-D{prev}")
        return "/".join(parts)

    stops = []
    for key in order:
        entry = stop_by_coord[key]
        days = entry.get("days", [])
        stops.append({
            "name": entry["name"],
            "lng": entry["lng"],
            "lat": entry["lat"],
            "days": days,
            "day": _collapse(days),  # human-readable label, kept for back-compat
        })

    return {
        "title": data.get("title", ""),
        "totals": data.get("totals", {}),
        "days": days_out,
        "stops": stops,
        "colors": {
            "real": ROUTE_COLOR_REAL,
            "estimate": ROUTE_COLOR_ESTIMATE,
            "start": MARKER_COLOR_START,
            "end": MARKER_COLOR_END,
            "mid": MARKER_COLOR_MID,
        },
    }


def _client_js() -> str:
    """The Leaflet initialization script shared by the snippet and the PNG page."""
    return r"""
(function () {
  var data = window.__MAP_DATA__;
  if (!data || !data.days) return;
  var map = L.map('trip-map', { zoomControl: true, scrollWheelZoom: false, attributionControl: false });
  // detectRetina makes Leaflet request higher-resolution tiles on HiDPI
  // screens (including the device_scale_factor=2 headless screenshot), so
  // both the interactive map and the PNG stay sharp instead of blurry.
  L.tileLayer('https://webrd0{s}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scale=1&style=8&x={x}&y={y}&z={z}', {
    subdomains: ['1','2','3','4'], maxZoom: 18, detectRetina: true, maxNativeZoom: 18
  }).addTo(map);

  function durLabel(min){ min=Math.round(min/5)*5; var h=Math.floor(min/60), m=min%60; return h+'h'+(m<10?'0':'')+m+'m'; }
  function distLabel(km){ return Math.round(km/5)*5+'km'; }
  function escapeHtml(value){
    return String(value == null ? '' : value).replace(/[&<>"']/g, function(ch){
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch];
    });
  }
  var c = data.colors || {};
  var allLatLng = [];

  data.days.forEach(function(day){
    day.legs.forEach(function(leg){
      if (!leg.points || leg.points.length < 2) return;
      var latlngs = leg.points.map(function(p){ return [p[1], p[0]]; });
      var color = leg.estimated ? (c.estimate||'#d97036') : (c.real||'#2c6bb2');
      L.polyline(latlngs, { color: '#ffffff', weight: 5, opacity: 0.65 }).addTo(map);
      var line = L.polyline(latlngs, { color: color, weight: 2.5, opacity: 0.95 }).addTo(map);
      var popup = '<b>'+escapeHtml(day.day)+' · '+escapeHtml(leg.from)+' → '+escapeHtml(leg.to)+'</b><br>'
                + distLabel(leg.distance_km)+' · '+durLabel(leg.duration_min)+' · ¥'+leg.toll_cny
                + (leg.estimated ? '<br><span style=\"color:#d97036\">估算数据</span>' : '');
      line.bindPopup(popup);
      allLatLng = allLatLng.concat(latlngs);
    });
  });

  // Stops as labeled markers (dot + permanent name label), color-coded by role.
  data.stops.forEach(function(stop, i){
    var isFirst = i === 0;
    var isLast = i === data.stops.length - 1;
    var color = isFirst ? (c.start||'#25955b') : isLast ? (c.end||'#d25240') : (c.mid||'#2c6bb2');
    var tag = stop.day || '';
    var label = tag ? (tag + ' ' + stop.name) : stop.name;
    var icon = L.divIcon({
      className: 'trip-stop',
      html: '<span class="trip-stop-dot" style="background:'+color+'"></span>'
          + '<span class="trip-stop-label">'+escapeHtml(label)+'</span>',
      iconSize: [10, 10], iconAnchor: [5, 5]
    });
    L.marker([stop.lat, stop.lng], { icon: icon })
      .addTo(map).bindPopup('<b>'+escapeHtml((stop.day||'')+' '+stop.name)+'</b>');
  });

  if (allLatLng.length) {
    map.fitBounds(L.latLngBounds(allLatLng), { padding: [30, 30] });
  } else {
    map.setView([28.5, 111.5], 6);
  }
  window.__MAP_READY__ = true;
})();
"""


def build_leaflet_snippet(data: dict[str, Any], height: int = 420) -> str:
    """Return a self-contained HTML fragment that renders an interactive map.

    The fragment includes its own scoped ``<style>`` and ``<script>`` so it can
    be dropped into ``trip.html`` without polluting the host page. Map data is
    inlined as ``window.__MAP_DATA__`` so the page works from ``file://``.
    """
    map_data = build_map_data(data)
    data_json = json_for_script(map_data)
    client = _client_js()
    # Map height is responsive via CSS class + media queries (wider screens get
    # a taller map). The ``height`` arg is the mobile baseline.
    return f"""<div class="leaflet-wrap">
  <link rel="stylesheet" href="{LEAFLET_CSS}">
  <style>
{STOP_MARKER_CSS}
  #trip-map {{ height: {height}px; width: 100%; border-radius: 8px; border: 1px solid #dce3ed; background: #f6f8fa; }}
  @media (min-width: 768px) {{ #trip-map {{ height: {max(height, 480)}px; }} }}
  @media (min-width: 1024px) {{ #trip-map {{ height: {max(height, 560)}px; }} }}
  </style>
  <div id="trip-map"></div>
  <script src="{LEAFLET_JS}"></script>
  <script id="trip-map-data" type="application/json">{data_json}</script>
  <script>window.__MAP_DATA__ = JSON.parse(document.getElementById('trip-map-data').textContent);</script>
  <script>{client}</script>
</div>"""


def _full_page_html(data: dict[str, Any]) -> str:
    """A standalone full-viewport Leaflet page used for PNG screenshots."""
    map_data = build_map_data(data)
    data_json = json_for_script(map_data)
    client = _client_js()
    totals = data.get("totals", {})

    # Optional date range in the title (e.g. "7.17-7.26").
    import datetime as _dt
    import re as _re
    title_text = data.get("title", "")
    _sd_raw = data.get("start_date")
    try:
        _sd = _dt.date.fromisoformat(_sd_raw) if _sd_raw else None
    except (ValueError, TypeError):
        _sd = None
    if _sd:
        _max_off = 0
        for _d in data.get("days", []):
            _m = _re.search(r"(\d+)", _d.get("day", ""))
            if _m:
                _max_off = max(_max_off, int(_m.group(1)) - 1)
        _last = _sd + _dt.timedelta(days=_max_off)
        _range = f"{_sd.month}.{_sd.day}-{_last.month}.{_last.day}" if _last != _sd else f"{_sd.month}.{_sd.day}"
        title_text = f"{title_text} · {_range}"

    def _r5(v):
        return int(round(float(v) / 5) * 5)

    def _dist(km):
        return f"{_r5(km)}km"

    def _dur(mins):
        mins = _r5(mins)
        return f"{mins // 60}h{mins % 60:02d}m"

    total_dur = _r5(totals.get("duration_min", 0))
    th, tm = total_dur // 60, total_dur % 60
    summary = (f"总里程 {_dist(totals.get('distance_km', 0))} · "
               f"{th}h{tm:02d}m · 过路费 ¥{totals.get('toll_cny', 0)}")

    # Compact legend panel rows.
    rows = []
    for day in data.get("days", []):
        dur = _dur(day.get("duration_min", 0))
        dist = (f"{_dist(day.get('distance_km', 0))} · {dur} · ¥{day.get('toll_cny', 0)}"
                if day.get("legs") else "停留游玩")
        day_label = html.escape(str(day.get("day", "")), quote=True)
        day_title = html.escape(str(day.get("title", "")), quote=True)
        metric = html.escape(dist, quote=True)
        rows.append(f"<tr><td><span class='d-tag'>{day_label}</span></td>"
                    f"<td class='route'>{day_title}</td><td class='metric'>{metric}</td></tr>")
    rows_html = "".join(rows)
    escaped_title = html.escape(str(title_text), quote=True)
    escaped_summary = html.escape(summary, quote=True)

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<link rel="stylesheet" href="{LEAFLET_CSS}">
<style>
  html,body{{margin:0;padding:0;height:100%;font-family:-apple-system,"PingFang SC",sans-serif;}}
  #trip-map{{position:absolute;inset:0;background:#f6f8fa;}}
  .legend{{position:absolute;top:8px;left:8px;z-index:1000;background:rgba(255,255,255,0.78);
    backdrop-filter:blur(2px);border-radius:12px;padding:10px 13px;box-shadow:0 2px 10px rgba(0,0,0,.10);
    max-width:300px;font-size:12px;border:1px solid rgba(220,227,237,0.8);}}
  .legend h2{{margin:0 0 3px;font-size:15px;color:#1f2937;}}
  .legend .summary{{color:#6b7280;font-size:11px;margin-bottom:6px;}}
  .legend table{{border-collapse:collapse;width:100%;}}
  .legend td{{padding:1px 0;vertical-align:top;}}
  .legend td.route{{word-break:break-word;}}
  .legend td.metric{{white-space:nowrap;text-align:right;padding-left:8px;}}
  .d-tag{{display:inline-block;background:#2c6bb2;color:#fff;border-radius:5px;
    padding:0 6px;font-size:10px;margin-right:5px;font-weight:600;}}
  .metric{{color:#b95c24;font-size:10px;}}
  {STOP_MARKER_CSS}
</style></head>
<body>
<div id="trip-map"></div>
<div class="legend">
  <h2>{escaped_title}</h2>
  <div class="summary">{escaped_summary}</div>
  <table>{rows_html}</table>
</div>
<script src="{LEAFLET_JS}"></script>
<script id="trip-map-data" type="application/json">{data_json}</script>
<script>window.__MAP_DATA__ = JSON.parse(document.getElementById('trip-map-data').textContent);</script>
<script>{client}</script>
</body></html>"""


def find_playwright_python() -> str | None:
    """Return the path of a Python interpreter that can import Playwright.

    We probe the current interpreter first (the one running route_trip, where
    users most likely installed Playwright per the README), then fall back to
    common system Pythons. Returning the actual path — not just a boolean —
    ensures the screenshot subprocess uses the SAME interpreter that was
    probed, avoiding mismatches (e.g. Playwright on 3.13 but /usr/bin/python3
    is 3.9 without it).

    Setting env var SDTP_NO_PLAYWRIGHT=1 forces a None return, which lets tests
    exercise the SVG fallback path on machines that DO have Playwright.
    """
    if os.environ.get("SDTP_NO_PLAYWRIGHT") == "1":
        return None
    candidates = [sys.executable, sys.executable.replace("python3", "python"), "/usr/bin/python3", "python3"]
    seen: set[str] = set()
    for py in candidates:
        if py in seen:
            continue
        seen.add(py)
        try:
            result = subprocess.run(
                [py, "-c", "import playwright; print(playwright.__file__)"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return py
        except Exception:
            continue
    return None


def render_route_png(data: dict[str, Any], out_path: Path, width: int = 1600, height: int = 1000) -> bool:
    """Render the Leaflet map to ``out_path`` via Playwright. Returns success.

    Writes a temporary full-page HTML, then launches a headless browser to
    load it, waits for the map to signal readiness, and screenshots it.
    Returns ``False`` (no exception) when Playwright is unavailable — callers
    treat PNG as optional.
    """
    py_exe = find_playwright_python()
    if not py_exe:
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        html_path = Path(tmpdir) / "route-map.html"
        html_path.write_text(_full_page_html(data), encoding="utf-8")
        html_url = "file://" + str(html_path.resolve())

        # Delegate to a subprocess so we can pick whichever Python has
        # Playwright installed. The probe script returns the interpreter path.
        script = f"""
import sys
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("NO_PLAYWRIGHT"); sys.exit(0)

url = {json.dumps(html_url)}
out = {json.dumps(str(out_path))}
w, h = {width}, {height}
with sync_playwright() as p:
    browser = p.chromium.launch()
    # device_scale_factor=2 renders at Retina resolution so the PNG stays
    # sharp on HiDPI displays (final image is w*2 by h*2 pixels).
    page = browser.new_page(viewport={{"width": w, "height": h}}, device_scale_factor=2)
    page.goto(url)
    try:
        page.wait_for_function("window.__MAP_READY__ === true", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(3500)
    page.screenshot(path=out, full_page=False)
    browser.close()
print("OK")
"""
        try:
            result = subprocess.run(
                [py_exe, "-c", script],
                capture_output=True, text=True, timeout=90,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError(f"Playwright route-map generation failed: {exc}") from exc

        if result.returncode == 0 and "OK" in result.stdout and out_path.exists() and out_path.stat().st_size > 10000:
            return True
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(f"Playwright route-map generation failed: {detail}")

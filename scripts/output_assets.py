#!/usr/bin/env python3
"""Generate static route assets and optional PDF exports."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import money_label
from html_renderer import duration_label, escape, ordered_stops
import leaflet_map


def flatten_route_points(data: dict[str, Any]) -> list[list[float]]:
    points: list[list[float]] = []
    for day in data["days"]:
        for leg in day["legs"]:
            polyline = leg.get("polyline") or []
            if not polyline:
                origin = leg.get("origin")
                destination = leg.get("destination")
                if origin and destination:
                    polyline = [[origin["lng"], origin["lat"]], [destination["lng"], destination["lat"]]]
            for point in polyline:
                if not points or points[-1] != point:
                    points.append(point)
    return points


def project_points(stops: list[dict[str, Any]], width: int, height: int) -> list[tuple[float, float]]:
    coords = [stop["point"] for stop in stops if stop.get("point")]
    padding = 84
    if len(coords) < len(stops) or not coords:
        return diagram_points(len(stops), width, height)

    lngs = [coord["lng"] for coord in coords]
    lats = [coord["lat"] for coord in coords]
    min_lng, max_lng = min(lngs), max(lngs)
    min_lat, max_lat = min(lats), max(lats)
    lng_span = max(max_lng - min_lng, 0.01)
    lat_span = max(max_lat - min_lat, 0.01)
    points = []
    for stop in stops:
        point = stop["point"]
        x = padding + (point["lng"] - min_lng) / lng_span * (width - padding * 2)
        y = height - padding - (point["lat"] - min_lat) / lat_span * (height - padding * 2)
        points.append((x, y))
    if closest_distance(points) < 92:
        return diagram_points(len(stops), width, height)
    return points


def diagram_points(count: int, width: int, height: int) -> list[tuple[float, float]]:
    columns = min(4, max(1, count))
    rows = math.ceil(count / columns)
    x_step = (width - 180) / max(1, columns - 1)
    y_step = min(220, (height - 250) / max(1, rows - 1))
    points = []
    for index in range(count):
        row = index // columns
        col = index % columns
        display_col = columns - 1 - col if row % 2 else col
        x = 90 + display_col * x_step
        y = 230 + row * y_step
        points.append((x, y))
    return points


def closest_distance(points: list[tuple[float, float]]) -> float:
    if len(points) < 2:
        return float("inf")
    closest = float("inf")
    for index, point in enumerate(points):
        for other in points[index + 1 :]:
            closest = min(closest, math.dist(point, other))
    return closest


def generate_svg(data: dict[str, Any], path: Path) -> None:
    width, height = 1200, 800
    stops = ordered_stops(data["days"])
    points = project_points(stops, width, height)
    point_by_name = {stop["name"]: points[index] for index, stop in enumerate(stops)}

    segments = []
    for day in data["days"]:
        for leg in day["legs"]:
            a = point_by_name.get(leg["from"])
            b = point_by_name.get(leg["to"])
            if not a or not b:
                continue
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            label = f'{leg["distance_km"]}km · {duration_label(int(leg["duration_min"]))} · {money_label(leg.get("toll_cny"))}'
            segments.append((a, b, mx, my, label, leg.get("estimated")))

    segment_svg = []
    for index, (a, b, mx, my, label, estimated) in enumerate(segments):
        color = "#D97036" if estimated else "#2C6BB2"
        label_y = my + [-42, 0, 42][index % 3]
        segment_svg.append(
            f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
            f'stroke="{color}" stroke-width="5" stroke-linecap="round"/>'
        )
        segment_svg.append(
            f'<rect x="{mx - 112:.1f}" y="{label_y - 17:.1f}" width="224" height="34" rx="10" fill="#FFFFFF" '
            f'stroke="#E8EDF3"/>'
        )
        segment_svg.append(
            f'<text x="{mx:.1f}" y="{label_y + 5:.1f}" text-anchor="middle" font-size="16" '
            f'fill="#4B5563">{escape(label)}</text>'
        )

    stop_svg = []
    for index, stop in enumerate(stops):
        x, y = points[index]
        label_y = y - 26 if index % 2 == 0 else y + 44
        stop_svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" fill="#FFFFFF" stroke="#2C6BB2" stroke-width="5"/>')
        stop_svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="#2C6BB2"/>')
        stop_svg.append(
            f'<text x="{x:.1f}" y="{label_y:.1f}" text-anchor="middle" font-size="22" '
            f'font-weight="700" fill="#1F2937">{escape(stop["name"])}</text>'
        )

    title = escape(data["title"])
    totals = data["totals"]
    subtitle = escape(f'总里程 {totals["distance_km"]}km · 总时长 {duration_label(int(totals["duration_min"]))} · 过路费 {money_label(totals["toll_cny"])}')
    share_credit = escape(leaflet_map.SHARE_CREDIT)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="#F6F8FA"/>
  <rect x="36" y="34" width="{width - 72}" height="{height - 68}" rx="28" fill="#FFFFFF" stroke="#E8EDF3"/>
  <text x="72" y="86" font-size="34" font-weight="800" fill="#1F2937">{title}</text>
  <text x="72" y="124" font-size="20" fill="#6B7280">{subtitle}</text>
  <g>{''.join(segment_svg)}</g>
  <g>{''.join(stop_svg)}</g>
  <text x="72" y="{height - 58}" font-size="17" fill="#8A929C">橙色线路为估算数据</text>
  <text x="{width - 72}" y="{height - 58}" text-anchor="end" font-size="15" fill="#687587">{share_credit}</text>
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def generate_route_map(data: dict[str, Any], out_dir: Path, key: str | None) -> str | None:
    """Generate a shareable route-map image. Returns the filename, or ``None``.

    Strategy (best first):
      1. Leaflet + Playwright screenshot → real driving route PNG. Requires
         the optional ``playwright`` dependency.
      2. SVG schematic fallback → used when Playwright is unavailable or the
         screenshot attempt fails.

    Note: the interactive Leaflet map inside trip.html is generated
    independently of this function and does NOT need Playwright — it works as
    long as the browser can load the Leaflet CDN and map tiles.
    """
    png_path = out_dir / "route-map.png"
    try:
        if leaflet_map.render_route_png(data, png_path):
            data["map"] = {
                "file": png_path.name,
                "source": "leaflet-playwright-screenshot",
                "fallback": False,
            }
            return png_path.name
    except Exception as exc:
        data["map_png_error"] = str(exc)

    # No Playwright (or screenshot failed) and we still want a static asset:
    # fall back to the SVG schematic so there is always a route-map file.
    svg_path = out_dir / "route-map.svg"
    try:
        generate_svg(data, svg_path)
        data["map"] = {
            "file": svg_path.name,
            "source": "fallback-svg",
            "fallback": True,
            "note": "Playwright unavailable; interactive Leaflet map in trip.html shows the real route.",
        }
        return svg_path.name
    except Exception as exc:
        data["map_svg_error"] = str(exc) or exc.__class__.__name__
        return None


def generate_pdf(html_path: Path, pdf_path: Path) -> bool:
    """Render the generated HTML to PDF with Playwright when available."""
    py_exe = leaflet_map.find_playwright_python()
    if not py_exe:
        py = str(Path(sys.executable))
        raise RuntimeError(
            f"Playwright is not installed; run `{py} -m pip install playwright && {py} -m playwright install chromium`."
        )

    script = f"""
from playwright.sync_api import sync_playwright

url = {json.dumps("file://" + str(html_path.resolve()))}
out = {json.dumps(str(pdf_path))}
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={{"width": 960, "height": 1280}}, device_scale_factor=1)
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    page.emulate_media(media="print")
    page.pdf(
        path=out,
        format="A4",
        print_background=True,
        margin={{"top": "12mm", "right": "10mm", "bottom": "12mm", "left": "10mm"}},
    )
    browser.close()
print("OK")
"""
    try:
        result = subprocess.run(
            [py_exe, "-c", script],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Playwright PDF generation failed: {exc}") from exc
    if result.returncode != 0 or "OK" not in result.stdout:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(f"Playwright PDF generation failed: {detail}")
    return pdf_path.is_file()

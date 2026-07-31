#!/usr/bin/env python3
"""Parse self-drive itinerary text and generate JSON, HTML, and a map-based route image."""

from __future__ import annotations

import argparse
import html
import io
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

# Local helper: interactive Leaflet map (real driving route) + optional PNG.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import leaflet_map


KNOWN_COORDS = {
    "合肥": (117.2272, 31.8206),
    "岳阳": (113.1289, 29.3571),
    "韶山": (112.5253, 27.9150),
    "凤凰": (109.5983, 27.9480),
    "凤凰古城": (109.5983, 27.9480),
    "荔波": (107.8860, 25.4102),
    "小七孔": (107.7170, 25.2580),
    "中国天眼": (106.8567, 25.6529),
    "天眼": (106.8567, 25.6529),
    "安顺": (105.9476, 26.2531),
    "黄果树": (105.6692, 25.9900),
    "贵阳": (106.6302, 26.6477),
    "茅台": (106.3822, 27.8162),
    "茅台镇": (106.3822, 27.8162),
    "茅台镇红军桥": (106.3863, 27.8204),
    "遵义": (106.9274, 27.7257),
    "遵义会议遗址": (106.9271, 27.6931),
    "重庆": (106.5516, 29.5630),
    "重庆市": (106.5516, 29.5630),
    "荆州": (112.2419, 30.3348),
}


def parse_itinerary(text: str) -> list[dict[str, Any]]:
    days: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        day_match = re.match(r"^(?:D|DAY)\s*(\d+)\s*$", line, re.IGNORECASE)
        if day_match:
            current = {"day": f"D{int(day_match.group(1))}", "legs": [], "notes": []}
            days.append(current)
            continue

        if current is None:
            current = {"day": "D1", "legs": [], "notes": []}
            days.append(current)

        normalized = re.sub(r"\s*(?:->|→|到|回|返回)\s*", " 到 ", line)
        if " 到 " not in normalized:
            current.setdefault("notes", []).append(line)
            continue

        stops = [part.strip() for part in normalized.split(" 到 ") if part.strip()]
        for origin, destination in zip(stops, stops[1:]):
            current["legs"].append({"from": origin, "to": destination})

    return [day for day in days if day["legs"] or day.get("notes")]


def amap_key() -> str | None:
    return os.getenv("AMAP_KEY") or os.getenv("GAODE_KEY")


def fetch_json(url: str, params: dict[str, str]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "codex-self-drive-trip-planner/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_bytes(url: str, params: dict[str, str]) -> bytes:
    query = urllib.parse.urlencode(params, safe=":,;|")
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "codex-self-drive-trip-planner/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def geocode(place: str, key: str | None, cache: dict[str, tuple[float, float] | None]) -> tuple[float, float] | None:
    if place in cache:
        return cache[place]

    if place in KNOWN_COORDS:
        cache[place] = KNOWN_COORDS[place]
        return cache[place]

    if not key:
        cache[place] = None
        return None

    payload = fetch_json(
        "https://restapi.amap.com/v3/geocode/geo",
        {"key": key, "address": place, "output": "json"},
    )
    geocodes = payload.get("geocodes") or []
    if payload.get("status") == "1" and geocodes:
        lng, lat = geocodes[0]["location"].split(",")
        cache[place] = (float(lng), float(lat))
    else:
        cache[place] = None
    return cache[place]


def parse_polyline(steps: list[dict[str, Any]]) -> list[list[float]]:
    points: list[list[float]] = []
    for step in steps:
        for pair in (step.get("polyline") or "").split(";"):
            if not pair:
                continue
            lng, lat = pair.split(",")[:2]
            points.append([float(lng), float(lat)])
    return points


def route_with_amap(origin: tuple[float, float], destination: tuple[float, float], key: str) -> dict[str, Any] | None:
    last_error = None
    for attempt in range(3):
        payload = fetch_json(
            "https://restapi.amap.com/v3/direction/driving",
            {
                "key": key,
                "origin": f"{origin[0]},{origin[1]}",
                "destination": f"{destination[0]},{destination[1]}",
                "extensions": "all",
                "output": "json",
            },
        )
        route = payload.get("route") or {}
        paths = route.get("paths") or []
        if payload.get("status") == "1" and paths:
            break
        last_error = payload.get("info") or payload.get("infocode") or "empty route"
        if attempt < 2:
            time.sleep(0.4 * (attempt + 1))
    else:
        raise RuntimeError(f"amap route failed: {last_error}")

    path = paths[0]
    distance_km = round(float(path.get("distance", 0)) / 1000, 1)
    duration_min = max(1, round(float(path.get("duration", 0)) / 60))
    toll_raw = path.get("tolls")
    toll_cny = round(float(toll_raw), 0) if toll_raw not in (None, "") else None
    return {
        "distance_km": distance_km,
        "duration_min": duration_min,
        "toll_cny": toll_cny,
        "polyline": parse_polyline(path.get("steps") or []),
        "source": "amap",
        "estimated": toll_cny is None,
    }


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(h))


def estimate_route(origin: tuple[float, float] | None, destination: tuple[float, float] | None) -> dict[str, Any]:
    if origin and destination:
        distance_km = round(max(8.0, haversine_km(origin, destination) * 1.35), 1)
        polyline = [[origin[0], origin[1]], [destination[0], destination[1]]]
    else:
        distance_km = 100.0
        polyline = []
    duration_min = max(15, round(distance_km / 72 * 60))
    toll_cny = round(distance_km * 0.5)
    return {
        "distance_km": distance_km,
        "duration_min": duration_min,
        "toll_cny": toll_cny,
        "polyline": polyline,
        "source": "estimated",
        "estimated": True,
    }


def enrich(days: list[dict[str, Any]], use_api: bool) -> dict[str, Any]:
    key = amap_key() if use_api else None
    cache: dict[str, tuple[float, float] | None] = {}

    for day in days:
        for leg in day["legs"]:
            origin = geocode(leg["from"], key, cache)
            destination = geocode(leg["to"], key, cache)
            metrics = None
            if key and origin and destination:
                try:
                    metrics = route_with_amap(origin, destination, key)
                except Exception as exc:
                    leg["lookup_error"] = str(exc)
            if metrics is None:
                metrics = estimate_route(origin, destination)

            leg.update(metrics)
            leg["origin"] = point_json(origin)
            leg["destination"] = point_json(destination)

        summarize_day(day)

    totals = {
        "distance_km": round(sum(day["distance_km"] for day in days), 1),
        "duration_min": sum(day["duration_min"] for day in days),
        "toll_cny": round(sum(day["toll_cny"] for day in days), 0),
    }
    return {"days": days, "totals": totals}


def point_json(point: tuple[float, float] | None) -> dict[str, float] | None:
    if not point:
        return None
    return {"lng": point[0], "lat": point[1]}


def summarize_day(day: dict[str, Any]) -> None:
    if not day["legs"]:
        notes = day.get("notes") or ["市区停留"]
        day["title"] = " / ".join(notes)
        day["distance_km"] = 0.0
        day["duration_min"] = 0
        day["toll_cny"] = 0
        day["estimated"] = False
        return

    day["title"] = " → ".join([day["legs"][0]["from"], *[leg["to"] for leg in day["legs"]]])
    day["distance_km"] = round(sum(float(leg["distance_km"]) for leg in day["legs"]), 1)
    day["duration_min"] = sum(int(leg["duration_min"]) for leg in day["legs"])
    day["toll_cny"] = round(sum(float(leg["toll_cny"] or 0) for leg in day["legs"]), 0)
    day["estimated"] = any(bool(leg.get("estimated")) for leg in day["legs"])


def _round_to_step(value: float, step: int = 5) -> int:
    """Round ``value`` to the nearest multiple of ``step`` (e.g. 5).

    Used for display-friendly distances/durations: 593.1km -> 595km,
    34 min -> 35 min. Applied only at the display layer; the stored data in
    trip-data.json keeps its original precision.
    """
    if step <= 0:
        return int(round(value))
    return int(round(float(value) / step) * step)


def distance_label(km: float | int) -> str:
    """Display a distance rounded to the nearest 5 km (595km, not 593.1km)."""
    return f"{_round_to_step(km, 5)}km"


def duration_label(minutes: int) -> str:
    # Round to nearest 5 min for readability (6h34m -> 6h35m).
    minutes = _round_to_step(minutes, 5)
    hours = minutes // 60
    mins = minutes % 60
    if hours and mins:
        return f"{hours}h{mins:02d}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def parse_start_date(value: str | None) -> Any:
    """Parse a YYYY-MM-DD string into a date, or return None if invalid/empty."""
    if not value:
        return None
    import datetime
    try:
        return datetime.date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def day_date_label(day_label: str, start_date: Any) -> str:
    """Return a calendar label for a day block, e.g. '7月17日 周四'.

    ``day_label`` is like 'D5'; the offset is parsed from the number. When
    ``start_date`` is None the function returns "" (no date shown).
    """
    if not start_date:
        return ""
    import datetime
    m = re.search(r"(\d+)", day_label or "")
    if not m:
        return ""
    offset = int(m.group(1)) - 1  # D1 is the start date itself
    the_date = start_date + datetime.timedelta(days=offset)
    weekday = WEEKDAY_LABELS[the_date.weekday()]
    return f"{the_date.month}月{the_date.day}日 {weekday}"


def trip_date_range(days: list[dict[str, Any]], start_date: Any) -> str:
    """Return a compact trip date range like '7.17-7.26' or '' if no start date.

    Uses the highest day number across all day blocks as the last day, so
    stay-only days are counted too.
    """
    if not start_date:
        return ""
    import datetime
    max_offset = 0
    for day in days:
        m = re.search(r"(\d+)", day.get("day", ""))
        if m:
            max_offset = max(max_offset, int(m.group(1)) - 1)
    last_date = start_date + datetime.timedelta(days=max_offset)
    if last_date == start_date:
        return f"{start_date.month}.{start_date.day}"
    return f"{start_date.month}.{start_date.day}-{last_date.month}.{last_date.day}"


def money_label(value: float | int | None) -> str:
    if value is None:
        return "待核实"
    return f"¥{int(round(float(value)))}"


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


def simplify_points(points: list[list[float]], max_points: int = 180) -> list[list[float]]:
    if len(points) <= max_points:
        return points
    step = (len(points) - 1) / (max_points - 1)
    simplified = [points[round(index * step)] for index in range(max_points)]
    simplified[0] = points[0]
    simplified[-1] = points[-1]
    return simplified


def index_label(index: int) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if index < len(alphabet):
        return alphabet[index]
    return str(index + 1)


def mercator_xy(lng: float, lat: float, zoom: int) -> tuple[float, float]:
    sin_lat = math.sin(math.radians(max(min(lat, 85.05112878), -85.05112878)))
    world = 256 * (2**zoom)
    x = (lng + 180) / 360 * world
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * world
    return x, y


def mercator_lng_lat(x: float, y: float, zoom: int) -> tuple[float, float]:
    world = 256 * (2**zoom)
    lng = x / world * 360 - 180
    n = math.pi - 2 * math.pi * y / world
    lat = math.degrees(math.atan(math.sinh(n)))
    return lng, lat


def map_view(points: list[list[float]], logical_width: int, logical_height: int) -> dict[str, Any]:
    padding_x = min(160, round(logical_width * 0.16))
    padding_y = min(100, round(logical_height * 0.16))
    if not points:
        return {"center": (105.0, 35.0), "zoom": 4}

    best: dict[str, Any] | None = None
    for zoom in range(12, 3, -1):
        projected = [mercator_xy(point[0], point[1], zoom) for point in points]
        min_x, max_x = min(x for x, _ in projected), max(x for x, _ in projected)
        min_y, max_y = min(y for _, y in projected), max(y for _, y in projected)
        if max_x - min_x <= logical_width - padding_x * 2 and max_y - min_y <= logical_height - padding_y * 2:
            center = mercator_lng_lat((min_x + max_x) / 2, (min_y + max_y) / 2, zoom)
            best = {"center": center, "zoom": zoom}
            break

    if best:
        return best

    projected = [mercator_xy(point[0], point[1], 4) for point in points]
    center = mercator_lng_lat(
        (min(x for x, _ in projected) + max(x for x, _ in projected)) / 2,
        (min(y for _, y in projected) + max(y for _, y in projected)) / 2,
        4,
    )
    return {"center": center, "zoom": 4}


def point_to_image_xy(
    point: list[float] | tuple[float, float],
    center: tuple[float, float],
    zoom: int,
    logical_size: tuple[int, int],
    image_size: tuple[int, int],
) -> tuple[float, float]:
    point_x, point_y = mercator_xy(float(point[0]), float(point[1]), zoom)
    center_x, center_y = mercator_xy(center[0], center[1], zoom)
    logical_width, logical_height = logical_size
    image_width, image_height = image_size
    scale_x = image_width / logical_width
    scale_y = image_height / logical_height
    x = (point_x - center_x + logical_width / 2) * scale_x
    y = (point_y - center_y + logical_height / 2) * scale_y
    return x, y


def boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int], padding: int = 8) -> bool:
    return not (
        a[2] + padding < b[0]
        or a[0] - padding > b[2]
        or a[3] + padding < b[1]
        or a[1] - padding > b[3]
    )


def clamp_box(box: tuple[int, int, int, int], width: int, height: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    dx = min(0, x1) + max(0, x2 - width)
    dy = min(0, y1) + max(0, y2 - height)
    return x1 - dx, y1 - dy, x2 - dx, y2 - dy


def place_label_box(
    anchor: tuple[float, float],
    size: tuple[int, int],
    used: list[tuple[int, int, int, int]],
    canvas: tuple[int, int],
    preferred: int,
) -> tuple[int, int, int, int]:
    x, y = anchor
    width, height = size
    offsets = [
        (26, -height - 18),
        (26, 18),
        (-width - 26, -height - 18),
        (-width - 26, 18),
        (-width / 2, -height - 34),
        (-width / 2, 34),
        (34, -height / 2),
        (-width - 34, -height / 2),
    ]
    offsets = offsets[preferred % len(offsets) :] + offsets[: preferred % len(offsets)]
    for offset_x, offset_y in offsets:
        box = (
            round(x + offset_x),
            round(y + offset_y),
            round(x + offset_x + width),
            round(y + offset_y + height),
        )
        box = clamp_box(box, canvas[0] - 16, canvas[1] - 16)
        if not any(boxes_overlap(box, used_box) for used_box in used):
            used.append(box)
            return box

    box = clamp_box(
        (round(x + 24), round(y + 24), round(x + 24 + width), round(y + 24 + height)),
        canvas[0] - 16,
        canvas[1] - 16,
    )
    used.append(box)
    return box


def text_size(draw: Any, text: str, font: Any) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def fit_text(draw: Any, text: str, font: Any, max_width: int) -> str:
    if text_size(draw, text, font)[0] <= max_width:
        return text
    suffix = "..."
    result = text
    while result and text_size(draw, result + suffix, font)[0] > max_width:
        result = result[:-1]
    return (result + suffix) if result else suffix


def escape(value: Any) -> str:
    return html.escape(str(value), quote=True)


def ordered_stops(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stops: list[dict[str, Any]] = []

    def add(name: str, point: dict[str, float] | None) -> None:
        if stops and stops[-1]["name"] == name:
            return
        stops.append({"name": name, "point": point})

    for day in days:
        for index, leg in enumerate(day["legs"]):
            if index == 0:
                add(leg["from"], leg.get("origin"))
            add(leg["to"], leg.get("destination"))
    return stops


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
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="{width}" height="{height}" fill="#F6F8FA"/>
  <rect x="36" y="34" width="{width - 72}" height="{height - 68}" rx="28" fill="#FFFFFF" stroke="#E8EDF3"/>
  <text x="72" y="86" font-size="34" font-weight="800" fill="#1F2937">{title}</text>
  <text x="72" y="124" font-size="20" fill="#6B7280">{subtitle}</text>
  <g>{''.join(segment_svg)}</g>
  <g>{''.join(stop_svg)}</g>
  <text x="{width - 72}" y="{height - 58}" text-anchor="end" font-size="17" fill="#8A929C">橙色线路为估算数据</text>
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def load_font(size: int, bold: bool = False) -> Any:
    from PIL import ImageFont

    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc" if bold else "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def stop_infos(data: dict[str, Any]) -> list[dict[str, Any]]:
    infos: list[dict[str, Any]] = []

    def add(name: str, point: dict[str, float] | None, day: str, role: str = "") -> None:
        if not point:
            return
        if infos and infos[-1]["name"] == name:
            if role:
                infos[-1]["role"] = role
            return
        info = {"name": name, "point": point, "day": day, "role": role}
        infos.append(info)

    if not data["days"]:
        return infos

    first_day_with_legs = next((day for day in data["days"] if day["legs"]), None)
    if not first_day_with_legs:
        return infos

    first_leg = first_day_with_legs["legs"][0]
    add(first_leg["from"], first_leg.get("origin"), first_day_with_legs["day"], "起点")
    for day in data["days"]:
        for leg in day["legs"]:
            add(leg["to"], leg.get("destination"), day["day"])
    if infos:
        infos[-1]["role"] = "终点"
    return infos


def leg_midpoint(leg: dict[str, Any]) -> list[float] | None:
    polyline = leg.get("polyline") or []
    if polyline:
        return polyline[len(polyline) // 2]
    origin = leg.get("origin")
    destination = leg.get("destination")
    if origin and destination:
        return [(origin["lng"] + destination["lng"]) / 2, (origin["lat"] + destination["lat"]) / 2]
    return None


def draw_round_label(
    draw: Any,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    width: int = 2,
) -> None:
    draw.rounded_rectangle(box, radius=14, fill=fill, outline=outline, width=width)


MAP_MARKER_LIMIT = 10


def pick_evenly(indices: list[int], limit: int) -> list[int]:
    if limit <= 0:
        return []
    if len(indices) <= limit:
        return indices

    picked: list[int] = []
    for index in range(limit):
        source_index = round(index * (len(indices) - 1) / max(1, limit - 1))
        value = indices[source_index]
        if value not in picked:
            picked.append(value)

    for value in indices:
        if len(picked) >= limit:
            break
        if value not in picked:
            picked.append(value)

    return sorted(picked)


def same_point(a: dict[str, Any], b: dict[str, Any]) -> bool:
    point_a = a.get("point") or {}
    point_b = b.get("point") or {}
    return (
        abs(float(point_a.get("lng", 0)) - float(point_b.get("lng", 1))) < 0.000001
        and abs(float(point_a.get("lat", 0)) - float(point_b.get("lat", 1))) < 0.000001
    )


def merge_marker_stops(stops: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for stop in stops:
        existing = next((item for item in merged if same_point(item, stop)), None)
        if not existing:
            merged.append({**stop})
            continue

        roles = [part for part in [existing.get("role"), stop.get("role")] if part]
        days = [part for part in [existing.get("day"), stop.get("day")] if part]
        existing["role"] = "/".join(dict.fromkeys(roles))
        existing["day"] = "/".join(dict.fromkeys(days))
        if existing["name"] != stop["name"]:
            existing["name"] = f'{existing["name"]}/{stop["name"]}'
    return merged


def overview_marker_stops(data: dict[str, Any], limit: int = MAP_MARKER_LIMIT) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stops = merge_marker_stops(stop_infos(data))
    if len(stops) <= limit:
        return stops, []

    priority_indices: list[int] = []

    def add_index(index: int | None) -> None:
        if index is not None and index not in priority_indices:
            priority_indices.append(index)

    add_index(0)
    for day in data["days"]:
        if not day["legs"]:
            continue
        endpoint = day["legs"][-1].get("destination")
        for index, stop in enumerate(stops):
            if endpoint and same_point(stop, {"point": endpoint}):
                add_index(index)
                break
    add_index(len(stops) - 1)
    priority_indices = sorted(priority_indices)

    if len(priority_indices) > limit:
        selected_indices = pick_evenly(priority_indices, limit)
    else:
        selected_indices = priority_indices[:]
        remaining_indices = [index for index in range(len(stops)) if index not in selected_indices]
        selected_indices.extend(pick_evenly(remaining_indices, limit - len(selected_indices)))
        selected_indices = sorted(selected_indices)

    selected_index_set = set(selected_indices)
    selected = [stops[index] for index in selected_indices]
    omitted = [stop for index, stop in enumerate(stops) if index not in selected_index_set]
    return selected, omitted


def static_map_markers(stops: list[dict[str, Any]]) -> str:
    marker_parts = []
    for index, stop in enumerate(stops[:MAP_MARKER_LIMIT]):
        point = stop.get("point")
        if not point:
            continue
        color = "0x25945B" if index == 0 else "0xD25240" if index == len(stops[:MAP_MARKER_LIMIT]) - 1 else "0x2C6BB2"
        marker_parts.append(
            f'mid,{color},{index_label(index)}:{point["lng"]:.6f},{point["lat"]:.6f}'
        )
    return "|".join(marker_parts)


# Marker colors used by static_map_markers (RGB tuples). Keep in sync with the
# hex colors above so detection can locate the provider-drawn markers on the
# downloaded static map image.
MARKER_COLOR_START = (37, 148, 91)      # 0x25945B green (first stop)
MARKER_COLOR_MID = (44, 107, 178)       # 0x2C6BB2 blue (intermediate stops)
MARKER_COLOR_END = (210, 82, 64)        # 0xD25240 red (last stop)


def _connected_components(image: Any, target: tuple[int, int, int], tol: int = 30,
                           min_size: int = 100, max_size: int = 400) -> list[tuple[float, float]]:
    """Find marker centroids of a given color in ``image`` via flood fill.

    Returns centroids (x, y) of color blobs whose pixel count is within
    [min_size, max_size] — the size range of Amap ``mid`` markers. Filters out
    large map-background regions that merely happen to match the target color.
    """
    from PIL import Image  # noqa: F401  (image is already a PIL Image)

    width, height = image.size
    pixels = image.load()

    def rgb(x: int, y: int) -> tuple[int, int, int]:
        """Read a pixel as RGB regardless of the image mode (RGB or RGBA)."""
        px = pixels[x, y]
        return px[0], px[1], px[2]

    visited = bytearray(width * height)
    centroids: list[tuple[float, float]] = []
    for start_y in range(height):
        for start_x in range(width):
            if visited[start_y * width + start_x]:
                continue
            r, g, b = rgb(start_x, start_y)
            if not (abs(r - target[0]) < tol and abs(g - target[1]) < tol and abs(b - target[2]) < tol):
                continue
            stack = [(start_x, start_y)]
            visited[start_y * width + start_x] = 1
            blob: list[tuple[int, int]] = []
            while stack:
                x, y = stack.pop()
                blob.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height and not visited[ny * width + nx]:
                        visited[ny * width + nx] = 1
                        rr, gg, bb = rgb(nx, ny)
                        if abs(rr - target[0]) < tol and abs(gg - target[1]) < tol and abs(bb - target[2]) < tol:
                            stack.append((nx, ny))
            size = len(blob)
            if min_size <= size <= max_size:
                cx = sum(p[0] for p in blob) / size
                cy = sum(p[1] for p in blob) / size
                centroids.append((cx, cy))
    return centroids


def detect_marker_pixels(image: Any) -> tuple[tuple[float, float] | None, list[tuple[float, float]], tuple[float, float] | None]:
    """Detect provider-drawn start/mid/end marker positions on the static map.

    Returns (start_pixel, mid_pixels, end_pixel). Any of them may be missing
    (``None`` / empty) if the provider did not render that color.
    """
    starts = _connected_components(image, MARKER_COLOR_START)
    mids = _connected_components(image, MARKER_COLOR_MID)
    ends = _connected_components(image, MARKER_COLOR_END)
    return (starts[0] if starts else None, mids, ends[0] if ends else None)


def _mercator_y(lat: float) -> float:
    sin_lat = math.sin(math.radians(max(min(lat, 85.05112878), -85.05112878)))
    return 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)


def predict_stop_pixels(stops: list[dict[str, Any]],
                        start_pixel: tuple[float, float],
                        end_pixel: tuple[float, float]) -> list[tuple[float, float] | None]:
    """Predict pixel position of every stop using a 2-anchor linear map.

    Amap's static-map auto-fit lays the stop bounding box roughly linearly
    across the image. Anchoring on the detected start (green) and end (red)
    markers, every intermediate stop is interpolated by longitude (x) and
    Mercator latitude (y). Empirically the error is ~1px, which is precise
    enough to draw connecting segments between provider-drawn markers.
    """
    points = [stop.get("point") for stop in stops]
    if not points or not points[0] or not points[-1]:
        return [None] * len(stops)

    start_lng = float(points[0]["lng"])
    start_lat = float(points[0]["lat"])
    end_lng = float(points[-1]["lng"])
    end_lat = float(points[-1]["lat"])
    start_my = _mercator_y(start_lat)
    end_my = _mercator_y(end_lat)

    result: list[tuple[float, float] | None] = []
    for point in points:
        if not point:
            result.append(None)
            continue
        lng = float(point["lng"])
        lat = float(point["lat"])
        t_x = (lng - start_lng) / (end_lng - start_lng) if end_lng != start_lng else 0.5
        my = _mercator_y(lat)
        t_y = (my - start_my) / (end_my - start_my) if end_my != start_my else 0.5
        px_x = start_pixel[0] + t_x * (end_pixel[0] - start_pixel[0])
        px_y = start_pixel[1] + t_y * (end_pixel[1] - start_pixel[1])
        result.append((px_x, px_y))
    return result


def render_labeled_map(
    data: dict[str, Any],
    content: bytes,
    path: Path,
) -> None:
    from PIL import Image, ImageDraw

    image = Image.open(io.BytesIO(content)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    canvas = image.size
    font_title = load_font(40, bold=True)
    font_small = load_font(22)
    font_row = load_font(22)
    font_row_bold = load_font(22, bold=True)
    font_legend = load_font(20)
    font_legend_bold = load_font(20, bold=True)

    all_stops = stop_infos(data)
    map_stops, omitted_stops = overview_marker_stops(data)
    start_name = all_stops[0]["name"] if all_stops else ""
    end_name = all_stops[-1]["name"] if all_stops else ""
    totals = data["totals"]

    # ---- Route segments: detect provider-drawn markers, then connect stops ----
    # Amap drew the markers (with correct auto-fit). We detect their pixel
    # positions and draw straight segments between consecutive stops so the
    # route spans the whole map instead of being squeezed by the broken
    # paths+markers auto-fit. Segment color reflects data source: blue for real
    # API data, orange for estimates.
    start_pixel, _mid_pixels, end_pixel = detect_marker_pixels(image)
    stop_pixels: list[tuple[float, float] | None] = []
    if start_pixel and end_pixel and len(map_stops) >= 2:
        stop_pixels = predict_stop_pixels(map_stops, start_pixel, end_pixel)
    route_real_color = (44, 107, 178, 235)       # 0x2C6BB2 — real API data
    route_estimate_color = (217, 112, 54, 235)   # 0xD97036 — estimated data
    if len(stop_pixels) == len(map_stops):
        # Walk every leg and draw a segment between its endpoints. Each leg's
        # endpoints are resolved to the nearest map stop pixel so omitted stops
        # still connect through their nearest labeled neighbor.
        stop_point_to_pixel: dict[tuple[float, float], tuple[float, float]] = {}
        for stop, pixel in zip(map_stops, stop_pixels):
            if pixel and stop.get("point"):
                key = (round(stop["point"]["lng"], 4), round(stop["point"]["lat"], 4))
                stop_point_to_pixel[key] = pixel

        def pixel_for(point: dict[str, float] | None) -> tuple[float, float] | None:
            if not point:
                return None
            return stop_point_to_pixel.get((round(point["lng"], 4), round(point["lat"], 4)))

        for day in data["days"]:
            day_estimated = bool(day.get("estimated"))
            color = route_estimate_color if day_estimated else route_real_color
            for leg in day["legs"]:
                a = pixel_for(leg.get("origin"))
                b = pixel_for(leg.get("destination"))
                if a and b:
                    # White halo for contrast against any map background.
                    draw.line([a, b], fill=(255, 255, 255, 180), width=6, joint="curve")
                    draw.line([a, b], fill=color, width=3, joint="curve")

    # ---- Summary panel (compact + translucent so underlying route stays visible) ----
    _sd = parse_start_date(data.get("start_date"))
    _range = trip_date_range(data["days"], _sd) if _sd else ""
    _title_with_date = f"{data['title']} · {_range}" if _range else data["title"]
    title_line = f'{_title_with_date} · 自驾线路图'
    summary_line = f'起点 {start_name} · 终点 {end_name} · {distance_label(totals["distance_km"])} · {duration_label(int(totals["duration_min"]))} · {money_label(totals["toll_cny"])}'
    panel_width = min(680, canvas[0] - 52)
    row_height = 40
    legend_row_height = 30
    omitted_note_height = 34 if omitted_stops else 0
    panel_height = 120 + len(data["days"]) * row_height + 28 + len(map_stops) * legend_row_height + omitted_note_height
    panel_box = (26, 26, 26 + panel_width, min(canvas[1] - 26, 26 + panel_height))
    draw_round_label(draw, panel_box, (255, 255, 255, 205), (44, 107, 178, 200), width=3)
    draw.text((panel_box[0] + 22, panel_box[1] + 18), title_line, font=font_title, fill=(31, 41, 55, 255))
    draw.text((panel_box[0] + 22, panel_box[1] + 70), summary_line, font=font_small, fill=(75, 85, 99, 255))
    separator_y = panel_box[1] + 108
    draw.line((panel_box[0] + 20, separator_y, panel_box[2] - 20, separator_y), fill=(222, 229, 237, 255), width=2)
    for row_index, day in enumerate(data["days"]):
        y = separator_y + 10 + row_index * row_height
        metrics = f'{duration_label(int(day["duration_min"]))} · {money_label(day["toll_cny"])}'
        metric_width = text_size(draw, metrics, font_row)[0]
        route_x = panel_box[0] + 86
        metric_x = panel_box[2] - 20 - metric_width
        route = fit_text(draw, day["title"], font_row_bold, max(80, metric_x - route_x - 16))
        draw.rounded_rectangle((panel_box[0] + 18, y + 2, panel_box[0] + 68, y + 30), radius=10, fill=(44, 107, 178, 255))
        draw.text((panel_box[0] + 29, y + 5), day["day"], font=font_row_bold, fill=(255, 255, 255, 255))
        draw.text((route_x, y + 4), route, font=font_row_bold, fill=(31, 41, 55, 255))
        draw.text((metric_x, y + 5), metrics, font=font_row, fill=(185, 92, 36, 255))

    legend_y = separator_y + 18 + len(data["days"]) * row_height
    draw.line((panel_box[0] + 20, legend_y - 10, panel_box[2] - 20, legend_y - 10), fill=(222, 229, 237, 255), width=2)
    draw.text((panel_box[0] + 22, legend_y), "地图点位", font=font_legend_bold, fill=(75, 85, 99, 255))
    for index, stop in enumerate(map_stops):
        is_start = index == 0
        is_end = index == len(map_stops) - 1
        color = (37, 148, 91, 255) if is_start else (210, 82, 64, 255) if is_end else (44, 107, 178, 255)
        role_text = stop["role"] if stop.get("role") else ""
        marker = index_label(index)
        label = f"{role_text}{stop['day']} {stop['name']}"
        col = index % 2
        row = index // 2
        x = panel_box[0] + 120 + col * 290
        y = legend_y + row * legend_row_height - 1
        draw.rounded_rectangle((x, y, x + 30, y + 26), radius=8, fill=color)
        draw.text((x + 9, y + 2), marker, font=font_legend_bold, fill=(255, 255, 255, 255))
        draw.text((x + 40, y + 2), label, font=font_legend, fill=(31, 41, 55, 255))
    if omitted_stops:
        omitted_y = legend_y + math.ceil(len(map_stops) / 2) * legend_row_height + 4
        omitted_text = f"另有 {len(omitted_stops)} 个途经点未在总览图标注，详见每日行程。"
        draw.text((panel_box[0] + 22, omitted_y), omitted_text, font=font_legend, fill=(75, 85, 99, 255))

    image = Image.alpha_composite(image, overlay).convert("RGB")
    image.save(path, format="PNG", optimize=True)


def generate_static_map(data: dict[str, Any], path: Path, key: str | None) -> bool:
    if not key:
        return False

    flat_points = flatten_route_points(data)
    if len(flat_points) < 2:
        return False

    logical_width, logical_height = 1024, 640
    map_stops, omitted_stops = overview_marker_stops(data)

    # NOTE: We intentionally do NOT send `paths` to the static map API.
    # When both `paths` and `markers` are present, Amap's auto-fit miscomputes
    # the viewport and squeezes the whole route into ~50% of the image
    # (confirmed by direct API experiments). Sending only `markers` gives a
    # correct auto-fit that frames all stops. The route polyline is then drawn
    # locally in render_labeled_map, anchored on the detected marker positions.
    marker_value = static_map_markers(map_stops)
    if not marker_value:
        return False

    params = {
        "key": key,
        "size": f"{logical_width}*{logical_height}",
        "scale": "2",
        "markers": marker_value,
    }

    content = b""
    for attempt in range(3):
        try:
            content = fetch_bytes("https://restapi.amap.com/v3/staticmap", params)
        except Exception as exc:
            data["map_error"] = str(exc)
            if attempt < 2:
                time.sleep(0.8 * (attempt + 1))
                continue
            return False
        if content.startswith(b"\x89PNG") or content.startswith(b"\xff\xd8"):
            break
        error_text = content[:300].decode("utf-8", errors="replace")
        data["map_error"] = error_text
        if "CUQPS" not in error_text and "QPS" not in error_text:
            break
        time.sleep(0.6 * (attempt + 1))

    if content.startswith(b"\x89PNG") or content.startswith(b"\xff\xd8"):
        try:
            render_labeled_map(
                data=data,
                content=content,
                path=path,
            )
        except Exception as exc:
            data["map_label_error"] = str(exc)
            path.write_bytes(content)
        data["map"] = {
            "file": path.name,
            "source": "amap-staticmap-labeled",
            "fallback": False,
            "fit": "provider-autofit-markers-only",
            "route": "local-drawn-segments",
            "markers": "provider-drawn",
            "marker_count": len(map_stops),
            "omitted_stop_count": len(omitted_stops),
        }
        return True

    data["map_error"] = content[:300].decode("utf-8", errors="replace")
    return False


def generate_route_map(data: dict[str, Any], out_dir: Path, key: str | None) -> str | None:
    """Generate a shareable route-map image. Returns the filename, or ``None``.

    Strategy (best first):
      1. Leaflet + Playwright screenshot → real driving route PNG. Requires
         the optional ``playwright`` dependency; skipped silently if absent.
      2. SVG schematic fallback → only when there is no usable route data at
         all (kept for fully-offline / no-network scenarios).

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
    except Exception:
        return None


def generate_html(data: dict[str, Any], path: Path, map_file: str | None = None) -> None:
    days_html = []
    overview_html = []
    dots_html = []
    start_date = parse_start_date(data.get("start_date"))
    for day in data["days"]:
        date_label = day_date_label(day["day"], start_date)
        leg_items = []
        if not day["legs"]:
            note_text = " / ".join(day.get("notes") or [day["title"]])
            leg_items.append(
                f'''<div class="item">
  <span class="item-icon"><i data-lucide="map-pin"></i></span>
  <div class="item-body">
    <div class="item-label">市区停留</div>
    <div class="item-text">{escape(note_text)}</div>
  </div>
  <div class="item-right">不计入<br>城际驾车</div>
</div>'''
            )
        else:
            for leg in day["legs"]:
                est = " · 估算" if leg.get("estimated") else ""
                leg_items.append(
                    f'''<div class="item">
  <span class="item-icon"><i data-lucide="car"></i></span>
  <div class="item-body">
    <div class="item-label">驾车{escape(est)}</div>
    <div class="item-text">{escape(leg["from"])} → {escape(leg["to"])}</div>
  </div>
  <div class="item-right">{escape(distance_label(leg["distance_km"]))} · {escape(duration_label(int(leg["duration_min"])))}<br>{escape(money_label(leg.get("toll_cny")))}</div>
</div>'''
                )

        days_html.append(
            f'''<section class="slide" aria-label="{escape(day["day"])} {escape(day["title"])}">
  <div class="day-card">
    <div class="day-top">
      <div class="day-num">{escape(day["day"])}{(' · ' + date_label) if date_label else ''}</div>
      <div class="day-title">{escape(day["title"])}</div>
      <div class="day-date">{escape(distance_label(day["distance_km"]))} · {escape(duration_label(int(day["duration_min"])))} · {escape(money_label(day["toll_cny"]))}</div>
    </div>
    <div class="items">{''.join(leg_items)}</div>
    <div class="day-foot">
      <div class="stat"><div class="stat-num">{escape(day["distance_km"])}</div><div class="stat-lbl">公里</div></div>
      <div class="stat"><div class="stat-num">{escape(duration_label(int(day["duration_min"])))}</div><div class="stat-lbl">驾车</div></div>
      <div class="stat"><div class="stat-num">{escape(money_label(day["toll_cny"]))}</div><div class="stat-lbl">过路费</div></div>
    </div>
  </div>
</section>'''
        )
        dots_html.append(
            f'''<button class="pager-dot" type="button" data-slide="{len(dots_html)}" aria-label="切换到 {escape(day["day"])}"></button>'''
        )

        overview_html.append(
            f'''<div class="ov-day-card">
  <div class="ov-day-head">
    <span class="ov-day-tag">{escape(day["day"])}</span>
    <span class="ov-day-route">{escape(day["title"])}</span>
    <span class="ov-day-dist">{escape(distance_label(day["distance_km"]))}</span>
  </div>
  <div class="ov-day-body">
    <div class="ov-line"><span class="ui-icon-text"><i data-lucide="clock"></i><span>{escape(duration_label(int(day["duration_min"])))}</span></span></div>
    <div class="ov-line"><span class="ui-icon-text"><i data-lucide="banknote"></i><span>{escape(money_label(day["toll_cny"]))}</span></span></div>
  </div>
</div>'''
        )

    totals = data["totals"]
    title = escape(data["title"])
    _sd = parse_start_date(data.get("start_date"))
    _range = trip_date_range(data["days"], _sd) if _sd else ""
    title_with_date = f"{title} · {_range}" if _range else title
    route_summary = " → ".join(stop["name"] for stop in ordered_stops(data["days"]))
    any_estimated = any(leg.get("estimated") for day in data["days"] for leg in day["legs"])
    toll_hint = "估算参考" if any_estimated else "地图数据"
    # Interactive Leaflet map snippet (real driving route, inline data).
    leaflet_snippet = leaflet_map.build_leaflet_snippet(data)
    # Optional: link to the standalone PNG if it was generated.
    png_link = ""
    if map_file and (path.parent / map_file).exists():
        png_link = f'<div class="map-note">真实路线地图 · 可缩放拖动 · 点击路段看详情 · <a href="./{escape(map_file)}" target="_blank" rel="noopener">查看路线图</a></div>'
    else:
        png_link = f'<div class="map-note">真实路线地图 · 可缩放拖动 · 点击路段看详情</div>'
    html_text = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>{title}</title>
<script src="https://unpkg.com/lucide@latest"></script>
<style>
:root {{
  --primary: #2C6BB2;
  --bg: #F6F8FA;
  --card: #FFFFFF;
  --accent: #D97036;
  --green: #25945B;
  --text: #26313B;
  --text2: #7B8490;
  --line: #E9EDF2;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }}
html, body {{ min-height: 100%; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  font-size: 14px;
}}
svg {{ stroke-width: 2; }}
.app {{ width: 100%; max-width: 520px; margin: 0 auto; min-height: 100vh; display: flex; flex-direction: column; }}
/* Responsive: widen on larger screens (mobile-first baseline is 520px). */
@media (min-width: 768px) {{ .app {{ max-width: 760px; }} .header h1 {{ font-size: 22px; }} }}
@media (min-width: 1024px) {{ .app {{ max-width: 960px; }} }}
.header {{ padding: 16px 20px 10px; flex-shrink: 0; }}
.header h1 {{ font-size: 18px; font-weight: 800; letter-spacing: 0; }}
.subtitle {{ font-size: 11px; color: var(--text2); margin-top: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tabs {{ display: flex; align-items: center; gap: 6px; padding: 0 20px 10px; overflow-x: auto; scrollbar-width: none; flex-shrink: 0; }}
.tabs::-webkit-scrollbar {{ display: none; }}
.tab {{
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--text2);
  border-radius: 20px;
  padding: 6px 14px;
  font-size: 13px;
  white-space: nowrap;
  cursor: pointer;
}}
.tab.active {{ background: var(--primary); border-color: var(--primary); color: #FFFFFF; font-weight: 700; }}
.main {{ flex: 1; min-height: 0; }}
.tab-panel {{ display: none; padding: 8px 20px 28px; }}
.tab-panel.active {{ display: block; }}
.overview-stack {{ display: grid; gap: 10px; }}
.overview-stats {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }}
.stat-tile {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 12px 10px;
  min-width: 0;
}}
.stat-tile .ui-icon-text {{ color: var(--text2); font-size: 11px; }}
.stat-tile .value {{ margin-top: 7px; color: var(--primary); font-size: 16px; font-weight: 900; line-height: 1.15; word-break: break-word; }}
.stat-tile .hint {{ margin-top: 2px; color: var(--text2); font-size: 10px; }}
.day-pager {{ display: grid; gap: 10px; }}
.pager-head {{ display: flex; align-items: center; justify-content: space-between; gap: 10px; }}
.pager-title {{ min-width: 0; }}
.pager-kicker {{ font-size: 11px; color: var(--text2); }}
.pager-current {{ margin-top: 2px; font-size: 16px; font-weight: 800; color: var(--text); word-break: break-word; }}
.pager-actions {{ display: inline-flex; align-items: center; gap: 8px; flex-shrink: 0; }}
.pager-button {{
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--card);
  color: var(--primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}}
.pager-button:focus-visible, .tab:focus-visible {{ outline: 2px solid color-mix(in srgb, var(--primary) 60%, white); outline-offset: 2px; }}
.pager-button svg {{ width: 17px; height: 17px; flex-shrink: 0; }}
.slider {{
  display: flex;
  gap: 12px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scroll-behavior: smooth;
  scrollbar-width: none;
  touch-action: pan-x;
}}
.slider::-webkit-scrollbar {{ display: none; }}
.slide {{ flex: 0 0 100%; min-width: 0; scroll-snap-align: start; }}
.pager-dots {{ display: flex; align-items: center; justify-content: center; gap: 6px; min-height: 18px; }}
.pager-dot {{
  width: 7px;
  height: 7px;
  border: 0;
  border-radius: 999px;
  background: #C9D2DE;
  cursor: pointer;
}}
.pager-dot.active {{ width: 20px; background: var(--primary); }}
.day-card, .ov-day-card, .t-card, .big-card, .map-card {{
  background: var(--card);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 8px rgba(20, 33, 48, 0.05);
}}
.day-top {{ padding: 18px 18px 14px; border-bottom: 1px solid var(--line); }}
.day-num {{ font-size: 12px; color: var(--primary); font-weight: 800; }}
.day-title {{ font-size: 17px; font-weight: 800; margin-top: 3px; word-break: break-word; }}
.day-date {{ font-size: 12px; color: var(--text2); margin-top: 3px; }}
.item {{ display: flex; align-items: flex-start; gap: 12px; padding: 13px 18px; border-bottom: 1px solid var(--line); }}
.item:last-child {{ border-bottom: 0; }}
.item-icon {{ width: 22px; display: flex; justify-content: center; padding-top: 2px; flex-shrink: 0; }}
.item-icon svg, .ui-icon-text svg {{ width: 16px; height: 16px; flex-shrink: 0; }}
.item-icon svg {{ stroke: var(--primary); }}
.item-body {{ flex: 1; min-width: 0; }}
.item-label {{ font-size: 11px; color: var(--text2); }}
.item-text {{ font-size: 13px; word-break: break-word; }}
.item-right {{ flex-shrink: 0; text-align: right; font-size: 11px; color: var(--text2); line-height: 1.45; }}
.day-foot {{ display: flex; align-items: center; gap: 8px; padding: 13px 18px; background: #FAFBFC; border-top: 1px solid var(--line); }}
.stat {{ flex: 1; text-align: center; min-width: 0; }}
.stat-num {{ font-size: 15px; font-weight: 800; color: var(--primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.stat-lbl {{ font-size: 10px; color: var(--text2); margin-top: 1px; }}
.ov-day-card {{ margin-bottom: 8px; }}
.ov-day-head {{ display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-bottom: 1px solid var(--line); }}
.ov-day-tag {{ font-size: 12px; font-weight: 800; color: var(--primary); min-width: 28px; }}
.ov-day-route {{ flex: 1; min-width: 0; font-size: 14px; font-weight: 700; word-break: break-word; }}
.ov-day-dist {{ font-size: 13px; color: var(--accent); font-weight: 800; flex-shrink: 0; }}
.ov-day-body {{ display: flex; align-items: center; gap: 14px; padding: 9px 16px 12px; color: var(--text2); font-size: 12px; }}
.ui-icon-text {{ display: inline-flex; align-items: center; gap: 6px; min-width: 0; }}
.t-card {{ display: flex; align-items: center; gap: 10px; padding: 14px 16px; margin-bottom: 8px; }}
.t-day {{ font-size: 13px; font-weight: 800; color: var(--primary); min-width: 30px; }}
.t-route {{ flex: 1; min-width: 0; }}
.t-route .name {{ font-size: 13px; word-break: break-word; }}
.t-route .info {{ font-size: 11px; color: var(--text2); }}
.t-fee {{ font-size: 15px; font-weight: 800; color: var(--accent); flex-shrink: 0; }}
.big-card {{ padding: 24px 20px; text-align: center; margin-top: 8px; }}
.big-card .num {{ font-size: 32px; font-weight: 900; color: var(--primary); }}
.big-card .lbl {{ font-size: 12px; color: var(--text2); margin-top: 4px; }}
.map-card {{ padding: 12px; }}
.map-scroll {{ overflow: hidden; }}
.map-scroll a {{ display: block; }}
.leaflet-wrap {{ width: 100%; }}
.leaflet-container {{ font: inherit; }}
.map-note {{ padding: 9px 4px 2px; font-size: 11px; color: var(--text2); text-align: center; }}
.map-note a {{ color: var(--accent, #2c6bb2); }}
</style>
</head>
<body>
<div class="app">
  <header class="header">
    <h1>{title_with_date}</h1>
    <div class="subtitle">{escape(route_summary)}</div>
  </header>
  <nav class="tabs" aria-label="行程视图">
    <button class="tab active" data-tab="overview">总览</button>
    <button class="tab" data-tab="daily">行程</button>
  </nav>
  <main class="main">
    <section class="tab-panel active" id="tab-overview">
      <div class="overview-stack">
        <div class="map-card"><div class="map-scroll">__LEAFLET_MAP__</div>{png_link}</div>
        <div class="overview-stats">
          <div class="stat-tile"><span class="ui-icon-text"><i data-lucide="route"></i><span>总里程</span></span><div class="value">{escape(distance_label(totals["distance_km"]))}</div><div class="hint">全程驾车</div></div>
          <div class="stat-tile"><span class="ui-icon-text"><i data-lucide="clock"></i><span>总时长</span></span><div class="value">{escape(duration_label(int(totals["duration_min"])))}</div><div class="hint">不含停留</div></div>
          <div class="stat-tile"><span class="ui-icon-text"><i data-lucide="banknote"></i><span>过路费</span></span><div class="value">{escape(money_label(totals["toll_cny"]))}</div><div class="hint">{escape(toll_hint)}</div></div>
        </div>
        <div>{''.join(overview_html)}</div>
      </div>
    </section>
    <section class="tab-panel" id="tab-daily">
      <div class="day-pager">
        <div class="pager-head">
          <div class="pager-title"><div class="pager-kicker">DAY <span id="pagerIndex">1</span> / {len(data["days"])}</div><div class="pager-current" id="pagerTitle">{escape(data["days"][0]["title"])}</div></div>
          <div class="pager-actions">
            <button class="pager-button" type="button" id="prevDay" aria-label="上一天"><i data-lucide="chevron-left"></i></button>
            <button class="pager-button" type="button" id="nextDay" aria-label="下一天"><i data-lucide="chevron-right"></i></button>
          </div>
        </div>
        <div class="slider" id="daySlider">{''.join(days_html)}</div>
        <div class="pager-dots" id="pagerDots">{''.join(dots_html)}</div>
      </div>
    </section>
  </main>
</div>
<script>
const dayTitles = {json.dumps([day["title"] for day in data["days"]], ensure_ascii=False)};
const daySlider = document.getElementById('daySlider');
const pagerIndex = document.getElementById('pagerIndex');
const pagerTitle = document.getElementById('pagerTitle');
const pagerDots = Array.from(document.querySelectorAll('.pager-dot'));
let currentDay = 0;

function setCurrentDay(index, shouldScroll = true) {{
  const total = dayTitles.length;
  currentDay = Math.max(0, Math.min(index, total - 1));
  pagerIndex.textContent = String(currentDay + 1);
  pagerTitle.textContent = dayTitles[currentDay];
  pagerDots.forEach((dot, dotIndex) => dot.classList.toggle('active', dotIndex === currentDay));
  if (shouldScroll && daySlider) {{
    daySlider.scrollTo({{ left: currentDay * daySlider.clientWidth, behavior: 'smooth' }});
  }}
}}

document.querySelectorAll('.tab').forEach((tab) => {{
  tab.addEventListener('click', () => {{
    document.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach((panel) => panel.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('tab-' + tab.dataset.tab).classList.add('active');
    if (window.lucide) window.lucide.createIcons();
  }});
}});
document.getElementById('prevDay').addEventListener('click', () => setCurrentDay(currentDay - 1));
document.getElementById('nextDay').addEventListener('click', () => setCurrentDay(currentDay + 1));
pagerDots.forEach((dot) => dot.addEventListener('click', () => setCurrentDay(Number(dot.dataset.slide))));
daySlider.addEventListener('scroll', () => {{
  window.clearTimeout(daySlider._snapTimer);
  daySlider._snapTimer = window.setTimeout(() => {{
    setCurrentDay(Math.round(daySlider.scrollLeft / daySlider.clientWidth), false);
  }}, 80);
}});
window.addEventListener('resize', () => setCurrentDay(currentDay, true));
setCurrentDay(0, false);
if (window.lucide) window.lucide.createIcons();
</script>
</body>
</html>
'''
    # The Leaflet snippet contains CSS/JS with curly braces, so it cannot live
    # inside the f-string above. Inject it now via placeholder replacement.
    html_text = html_text.replace("__LEAFLET_MAP__", leaflet_snippet)
    path.write_text(html_text, encoding="utf-8")


def write_outputs(data: dict[str, Any], out_dir: Path, key: str | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # Write data JSON first (fast) so it lands even if PNG generation is slow/fails.
    (out_dir / "trip-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    # PNG generation is optional (needs Playwright); may return None.
    map_file = generate_route_map(data, out_dir, key)
    generate_html(data, out_dir / "trip.html", map_file)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate self-drive trip data, HTML, and a map-based route image.")
    parser.add_argument("input", help="Text file containing D1/D2 day blocks and A 到 B route lines.")
    parser.add_argument("--out", default="./trip-output", help="Output directory.")
    parser.add_argument("--title", default="自驾行程", help="Trip title used in generated outputs.")
    parser.add_argument("--start-date", default=None,
                        help="Departure date YYYY-MM-DD (e.g. 2026-07-17). When set, each day shows its calendar date and weekday.")
    parser.add_argument("--no-api", action="store_true", help="Skip map API calls and generate estimated preview data.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    days = parse_itinerary(input_path.read_text(encoding="utf-8"))
    if not days:
        print("No route legs found. Use lines such as: 合肥 到 岳阳", file=sys.stderr)
        return 2

    key = None if args.no_api else amap_key()
    data = enrich(days, use_api=not args.no_api)
    data["title"] = args.title
    start_date = parse_start_date(getattr(args, "start_date", None))
    if start_date:
        data["start_date"] = start_date.isoformat()
    write_outputs(data, Path(args.out), key)

    source_count: dict[str, int] = {}
    for day in data["days"]:
        for leg in day["legs"]:
            source_count[leg["source"]] = source_count.get(leg["source"], 0) + 1
    print(f"Wrote: {Path(args.out).resolve()}")
    print("Sources:", ", ".join(f"{source}={count}" for source, count in sorted(source_count.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

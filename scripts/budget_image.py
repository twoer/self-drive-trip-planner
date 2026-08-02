#!/usr/bin/env python3
"""Generate a fixed-format editorial budget summary image."""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import leaflet_map
from budget import BUDGET_CATEGORY_LABELS


WIDTH = 1600
HEIGHT = 1000
PNG_SCALE = 2
MAX_ITEMS_PER_COLUMN = 5
CATEGORY_COLORS = {
    "toll": "#2C6BB2",
    "vehicle_energy": "#25945B",
    "hotel": "#D08A24",
    "meal": "#D25240",
    "attraction": "#7357A6",
    "misc": "#687587",
}
CATEGORY_TINTS = {
    "toll": "#EAF2FB",
    "vehicle_energy": "#E8F5EE",
    "hotel": "#FBF1DF",
    "meal": "#FBECEA",
    "attraction": "#F1ECF8",
    "misc": "#EEF1F4",
}
CATEGORY_ICONS = {
    "toll": "car",
    "vehicle_energy": "zap",
    "hotel": "bed-double",
    "meal": "utensils",
    "attraction": "map-pin",
    "misc": "receipt-text",
}
# Lucide v1.28.0 icon geometry, licensed under ISC.
LUCIDE_ICON_ELEMENTS = {
    "car": (
        '<path d="M19 17h2c.6 0 1-.4 1-1v-3c0-.9-.7-1.7-1.5-1.9C18.7 10.6 16 10 16 10s-1.3-1.4-2.2-2.3c-.5-.4-1.1-.7-1.8-.7H5c-.6 0-1.1.4-1.4.9l-1.4 2.9A3.7 3.7 0 0 0 2 12v4c0 .6.4 1 1 1h2"/>',
        '<circle cx="7" cy="17" r="2"/><path d="M9 17h6"/><circle cx="17" cy="17" r="2"/>',
    ),
    "zap": (
        '<path d="M15.914 4a1.5 1.5 0 00-2.474-1.561l-9 9A1.5 1.5 0 005.5 14h4.002a.5.5 0 01.471.666L8.086 20a1.5 1.5 0 002.475 1.56l9-9A1.5 1.5 0 0018.5 10h-3.997a.5.5 0 01-.472-.667z"/>',
    ),
    "bed-double": (
        '<path d="M2 20v-8a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v8"/>',
        '<path d="M4 10V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v4"/>',
        '<path d="M12 4v6"/><path d="M2 18h20"/>',
    ),
    "utensils": (
        '<path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/>',
        '<path d="M7 2v20"/>',
        '<path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/>',
    ),
    "map-pin": (
        '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/>',
        '<circle cx="12" cy="10" r="3"/>',
    ),
    "receipt-text": (
        '<path d="M13 16H8"/><path d="M14 8H8"/><path d="M16 12H8"/>',
        '<path d="M4 3a1 1 0 0 1 1-1 1.3 1.3 0 0 1 .7.2l.933.6a1.3 1.3 0 0 0 1.4 0l.934-.6a1.3 1.3 0 0 1 1.4 0l.933.6a1.3 1.3 0 0 0 1.4 0l.933-.6a1.3 1.3 0 0 1 1.4 0l.934.6a1.3 1.3 0 0 0 1.4 0l.933-.6A1.3 1.3 0 0 1 19 2a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1 1.3 1.3 0 0 1-.7-.2l-.933-.6a1.3 1.3 0 0 0-1.4 0l-.934.6a1.3 1.3 0 0 1-1.4 0l-.933-.6a1.3 1.3 0 0 0-1.4 0l-.933.6a1.3 1.3 0 0 1-1.4 0l-.934-.6a1.3 1.3 0 0 0-1.4 0l-.933.6a1.3 1.3 0 0 1-.7.2 1 1 0 0 1-1-1z"/>',
    ),
}


def budget_image_eligible(data: dict[str, Any]) -> bool:
    budget = data.get("budget") or {}
    return bool(budget.get("configured") and budget.get("items"))


def display_width(value: str) -> float:
    return sum(0.55 if ord(char) < 128 else 1.0 for char in value)


def clip_text(value: Any, max_width: float) -> str:
    text = str(value or "").strip()
    if display_width(text) <= max_width:
        return text
    result = ""
    for char in text:
        if display_width(result + char + "…") > max_width:
            break
        result += char
    return result.rstrip() + "…"


def wrap_text(value: Any, max_width: float, max_lines: int = 2) -> list[str]:
    remaining = str(value or "").strip()
    if not remaining:
        return []
    lines: list[str] = []
    while remaining and len(lines) < max_lines:
        current = ""
        split_at = 0
        for index, char in enumerate(remaining):
            if display_width(current + char) > max_width:
                break
            current += char
            if char in " ，,。；;·/":
                split_at = index + 1
        if not current:
            current = remaining[0]
        elif len(current) < len(remaining) and split_at > 0:
            current = remaining[:split_at].rstrip()
        lines.append(current)
        remaining = remaining[len(current):].lstrip()
    if remaining and lines:
        lines[-1] = clip_text(lines[-1] + remaining, max_width)
    return lines


def money(value: Any) -> str:
    amount = round(float(value or 0))
    return f"¥{amount:,}"


def svg_text(
    value: Any,
    x: float,
    y: float,
    *,
    size: int,
    color: str,
    weight: int = 400,
    anchor: str = "start",
    max_width: float | None = None,
    max_lines: int = 1,
    line_height: int | None = None,
) -> str:
    lines = wrap_text(value, max_width, max_lines) if max_width else [str(value or "")]
    if not lines:
        return ""
    escaped = [html.escape(line, quote=True) for line in lines]
    line_height = line_height or round(size * 1.35)
    tspans = []
    for index, line in enumerate(escaped):
        dy = 0 if index == 0 else line_height
        tspans.append(f'<tspan x="{x}" dy="{dy}">{line}</tspan>')
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{color}" text-anchor="{anchor}">{"".join(tspans)}</text>'
    )


def svg_icon(category: str, x: float, y: float, size: int = 20) -> str:
    icon_name = CATEGORY_ICONS.get(category, "receipt-text")
    elements = "".join(LUCIDE_ICON_ELEMENTS[icon_name])
    color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["misc"])
    scale = size / 24
    return (
        f'<g data-icon="{icon_name}" transform="translate({x} {y}) scale({scale:.4f})" '
        f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        f'{elements}</g>'
    )


def detail_item_columns(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    basic_items: list[dict[str, Any]] = []
    attraction_items: list[dict[str, Any]] = []
    attraction_by_label: dict[str, dict[str, Any]] = {}
    for item in items:
        if item.get("category") != "attraction":
            basic_items.append(item)
            continue
        label = str(item.get("label") or "景点费用")
        if label not in attraction_by_label:
            merged = dict(item)
            attraction_by_label[label] = merged
            attraction_items.append(merged)
            continue
        merged = attraction_by_label[label]
        merged["amount_cny"] = round(
            float(merged.get("amount_cny") or 0) + float(item.get("amount_cny") or 0),
            2,
        )
        detail = str(item.get("detail") or "").strip()
        if detail and detail not in str(merged.get("detail") or ""):
            merged["detail"] = "；".join(
                part for part in (str(merged.get("detail") or "").strip(), detail) if part
            )
    shown_count = min(len(basic_items), MAX_ITEMS_PER_COLUMN) + min(
        len(attraction_items), MAX_ITEMS_PER_COLUMN
    )
    hidden_count = len(basic_items) + len(attraction_items) - shown_count
    return (
        basic_items[:MAX_ITEMS_PER_COLUMN],
        attraction_items[:MAX_ITEMS_PER_COLUMN],
        hidden_count,
    )


def trip_context(data: dict[str, Any]) -> tuple[str, str]:
    days = data.get("days") or []
    legs = [leg for day in days for leg in day.get("legs") or []]
    names = []
    if legs:
        names = [str(legs[0].get("from") or ""), *[str(leg.get("to") or "") for leg in legs]]
    unique_places = len(dict.fromkeys(name for name in names if name))
    distance = round(float((data.get("totals") or {}).get("distance_km") or 0))
    passengers = ((data.get("budget") or {}).get("assumptions") or {}).get("passengers") or {}
    passenger_count = sum(int(passengers.get(key) or 0) for key in ("adults", "children_under_1_2m", "children_over_1_2m"))
    meta_parts = [f"{len(days)} 天", f"{distance:,} 公里", f"{len(legs)} 段驾驶"]
    if passenger_count:
        meta_parts.append(f"{passenger_count} 人")

    route = ""
    if names:
        start, end = names[0], names[-1]
        middle_count = max(unique_places - (1 if start == end else 2), 0)
        ending = f"回到 {end}" if start == end else f"抵达 {end}"
        route = f"{start} 出发 · 途经 {middle_count} 地 · {ending}"

    raw_start_date = data.get("start_date")
    if raw_start_date and days:
        try:
            start_date = date.fromisoformat(str(raw_start_date))
            day_numbers = [int(match.group(1)) for day in days if (match := re.search(r"(\d+)", str(day.get("day") or "")))]
            last_date = start_date + timedelta(days=max(day_numbers or [1]) - 1)
            route = " · ".join(part for part in [route, f"{start_date.month}.{start_date.day}-{last_date.month}.{last_date.day}"] if part)
        except ValueError:
            pass
    return " · ".join(meta_parts), route


def generate_budget_summary_svg(data: dict[str, Any], path: Path) -> None:
    budget = data.get("budget") or {}
    items = list(budget.get("items") or [])
    category_totals = [
        (category, float(amount or 0))
        for category, amount in (budget.get("category_totals") or {}).items()
        if float(amount or 0) > 0
    ]
    total = float(budget.get("total_cny") or 0)
    basic_items, attraction_items, hidden_item_count = detail_item_columns(items)
    meta, route = trip_context(data)
    title = clip_text(data.get("title") or "自驾行程", 24)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" '
        'font-family="-apple-system, BlinkMacSystemFont, Segoe UI, PingFang SC, Microsoft YaHei, sans-serif">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#F6F8FA"/>',
        '<rect x="0" y="0" width="1600" height="12" fill="#2C6BB2"/>',
        '<defs><clipPath id="budget-bar-clip"><rect x="80" y="350" width="1440" height="28" rx="14"/></clipPath></defs>',
        svg_text(title, 80, 112, size=46, color="#26313B", weight=900),
        svg_text(meta, 80, 170, size=22, color="#687587", weight=600),
        svg_text(route, 80, 214, size=18, color="#7B8490", max_width=48),
        '<rect x="1120" y="52" width="400" height="214" rx="8" fill="#2C6BB2"/>',
        svg_text("当前预算合计", 1160, 105, size=20, color="#DCEBFA", weight=700),
        svg_text(money(total), 1160, 183, size=58, color="#FFFFFF", weight=900),
        svg_text("按已确认参数计算", 1160, 226, size=17, color="#DCEBFA"),
        '<line x1="80" y1="292" x2="1520" y2="292" stroke="#DCE3EB"/>',
        svg_text("费用构成", 80, 326, size=24, color="#26313B", weight=900),
    ]

    bar_x, bar_y, bar_width, bar_height = 80.0, 350.0, 1440.0, 28.0
    parts.append(f'<g clip-path="url(#budget-bar-clip)"><rect x="{bar_x}" y="{bar_y}" width="{bar_width}" height="{bar_height}" fill="#E5EAF0"/>')
    positive_total = sum(amount for _, amount in category_totals)
    offset = bar_x
    for category, amount in category_totals:
        width = bar_width * amount / positive_total if positive_total else 0
        color = CATEGORY_COLORS.get(category, "#687587")
        parts.append(f'<rect x="{offset:.1f}" y="{bar_y}" width="{width:.1f}" height="{bar_height}" fill="{color}"/>')
        offset += width
    parts.append("</g>")

    legend_count = max(1, len(category_totals))
    legend_width = bar_width / legend_count
    for index, (category, amount) in enumerate(category_totals[:6]):
        x = bar_x + index * legend_width
        color = CATEGORY_COLORS.get(category, "#687587")
        label = BUDGET_CATEGORY_LABELS.get(category, category)
        parts.extend([
            f'<rect x="{x:.1f}" y="402" width="12" height="12" rx="3" fill="{color}"/>',
            svg_text(label, x + 22, 414, size=17, color="#687587", weight=700),
            svg_text(money(amount), x, 452, size=24, color="#26313B", weight=900),
        ])

    parts.extend([
        '<line x1="80" y1="486" x2="1520" y2="486" stroke="#DCE3EB"/>',
        svg_text("费用明细", 80, 532, size=24, color="#26313B", weight=900),
        '<rect x="80" y="551" width="4" height="24" rx="2" fill="#2C6BB2"/>',
        svg_text("基础费用", 96, 570, size=17, color="#687587", weight=800),
        '<rect x="840" y="551" width="4" height="24" rx="2" fill="#7357A6"/>',
        svg_text("景点费用", 856, 570, size=17, color="#7357A6", weight=800),
    ])

    for column, column_items in enumerate((basic_items, attraction_items)):
        for row, item in enumerate(column_items):
            x = 80 + column * 760
            row_top = 588 + row * 68
            category = str(item.get("category") or "misc")
            color = CATEGORY_COLORS.get(category, CATEGORY_COLORS["misc"])
            tint = CATEGORY_TINTS.get(category, CATEGORY_TINTS["misc"])
            if category == "attraction":
                parts.extend([
                    f'<rect x="{x}" y="{row_top + 2}" width="680" height="58" rx="6" fill="{tint}"/>',
                    f'<rect x="{x}" y="{row_top + 2}" width="4" height="58" rx="2" fill="{color}"/>',
                ])
            parts.extend([
                f'<rect x="{x + 12}" y="{row_top + 8}" width="38" height="38" rx="8" fill="{tint}"/>',
                svg_icon(category, x + 21, row_top + 17, 20),
            ])
            label = clip_text(item.get("label") or "费用", 15)
            detail = item.get("detail") or BUDGET_CATEGORY_LABELS.get(category, "")
            label_y = row_top + (27 if category == "attraction" else 24)
            detail_y = row_top + (51 if category == "attraction" else 49)
            parts.extend([
                svg_text(label, x + 62, label_y, size=20, color="#26313B", weight=900),
                svg_text(money(item.get("amount_cny")), x + 660, row_top + 39, size=23, color=color if category == "attraction" else "#D97036", weight=900, anchor="end"),
                svg_text(detail, x + 62, detail_y, size=15, color="#7B8490", max_width=32),
            ])
            if row < len(column_items) - 1:
                parts.append(
                    f'<line x1="{x + 62}" y1="{row_top + 61}" x2="{x + 660}" y2="{row_top + 61}" stroke="#E2E7ED"/>'
                )

    missing = budget.get("missing_attractions") or []
    footer_parts = ["规划参考：实际价格请以预订和现场为准"]
    if hidden_item_count:
        footer_parts.append(f"另有 {hidden_item_count} 项明细")
    if missing:
        missing_names = "、".join(str(item.get("name") or "") for item in missing[:3])
        footer_parts.append(f"待补费用：{missing_names}")
    parts.extend([
        svg_text(" · ".join(footer_parts), 80, 964, size=17, color="#687587", max_width=44),
        svg_text(leaflet_map.SHARE_CREDIT, 1520, 964, size=14, color="#7B8490", weight=600, anchor="end"),
        "</svg>",
    ])
    path.write_text("".join(parts) + "\n", encoding="utf-8")


def render_budget_summary_png(svg_path: Path, png_path: Path) -> bool:
    py_exe = leaflet_map.find_playwright_python()
    if not py_exe:
        return False
    script = f'''
from playwright.sync_api import sync_playwright
url = {json.dumps(svg_path.resolve().as_uri())}
out = {json.dumps(str(png_path))}
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={{"width": {WIDTH}, "height": {HEIGHT}}}, device_scale_factor={PNG_SCALE})
    page.goto(url, wait_until="domcontentloaded")
    page.screenshot(path=out, full_page=False)
    browser.close()
print("OK")
'''
    try:
        result = subprocess.run([py_exe, "-c", script], capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"Playwright budget image generation failed: {exc}") from exc
    if result.returncode != 0 or "OK" not in result.stdout or not png_path.is_file() or png_path.stat().st_size < 10000:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise RuntimeError(f"Playwright budget image generation failed: {detail}")
    return True


def generate_budget_summary_image(data: dict[str, Any], out_dir: Path) -> str | None:
    if not budget_image_eligible(data):
        return None
    svg_path = out_dir / "budget-summary.svg"
    png_path = out_dir / "budget-summary.png"
    generate_budget_summary_svg(data, svg_path)
    try:
        if render_budget_summary_png(svg_path, png_path):
            svg_path.unlink()
            return png_path.name
    except Exception as exc:
        data["budget_image_png_error"] = str(exc) or exc.__class__.__name__
        if png_path.is_file():
            png_path.unlink()
    return svg_path.name

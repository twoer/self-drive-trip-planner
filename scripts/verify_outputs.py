#!/usr/bin/env python3
"""Verify generated self-drive trip output files against the manifest contract."""

from __future__ import annotations

import argparse
from datetime import date
from html.parser import HTMLParser
import json
import math
import re
import sys
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest_contract import (
    GENERATED_OUTPUT_FILES,
    KEY_REQUIRED_MODES,
    LEG_SOURCE_CHOICES,
    MANIFEST_CONTRACT_FIELDS,
    MANIFEST_FILE_FIELDS,
    MAP_OUTPUT_CONTRACT,
    MODE_CHOICES,
    is_complete_amap_leg,
)
from leaflet_map import build_map_data
from budget import BUDGET_CATEGORY_CHOICES, BUDGET_CONTRACT_FIELDS


def load_json(path: Path, errors: list[str]) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"missing JSON file: {path.name}")
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON in {path.name}: {exc}")
    return None


def is_number(value: Any) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_iso_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_normalized_day_label(value: str) -> bool:
    return bool(re.fullmatch(r"D[1-9]\d*", value))


def rounded_total(value: float | int, digits: int) -> float | int:
    rounded = round(float(value), digits)
    if digits == 0:
        return int(rounded)
    return rounded


def totals_match(actual: Any, expected: float | int, digits: int) -> bool:
    if not is_number(actual):
        return False
    return rounded_total(actual, digits) == rounded_total(expected, digits)


def money_totals_match(actual: Any, expected: float | int) -> bool:
    return totals_match(actual, expected, 2)


def manifest_file_path(out_dir: Path, rel_path: Any, field: str, errors: list[str]) -> Path | None:
    if rel_path is None:
        return None
    if not isinstance(rel_path, str) or not rel_path:
        errors.append(f"manifest.files.{field} must be a relative path string or null")
        return None
    candidate = Path(rel_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"manifest.files.{field} must stay inside the output directory: {rel_path}")
        return None
    path = out_dir / candidate
    if not path.is_file():
        errors.append(f"manifest.files.{field} points to a missing file: {rel_path}")
    return path


class OutputHTMLInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.has_html_root = False
        self.has_trip_map = False
        self.leaflet_scripts: list[str] = []
        self.leaflet_stylesheets: list[str] = []
        self.links: list[str] = []
        self.map_data_chunks: list[str] = []
        self._inside_map_data = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "html":
            self.has_html_root = True
        if attributes.get("id") == "trip-map":
            self.has_trip_map = True
        if tag == "script" and "leaflet" in (attributes.get("src") or "").lower():
            self.leaflet_scripts.append(attributes["src"] or "")
        if (
            tag == "link"
            and "stylesheet" in (attributes.get("rel") or "").lower()
            and "leaflet" in (attributes.get("href") or "").lower()
        ):
            self.leaflet_stylesheets.append(attributes["href"] or "")
        if tag == "a" and attributes.get("href"):
            self.links.append(attributes["href"] or "")
        if tag == "script" and attributes.get("id") == "trip-map-data":
            self._inside_map_data = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._inside_map_data:
            self._inside_map_data = False

    def handle_data(self, data: str) -> None:
        if self._inside_map_data:
            self.map_data_chunks.append(data)


def verify_html_output(path: Path, map_file: str, errors: list[str]) -> Any:
    try:
        html = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"manifest.files.html is not readable UTF-8 HTML: {exc}")
        return None

    inspector = OutputHTMLInspector()
    inspector.feed(html)
    if not inspector.has_html_root:
        errors.append("manifest.files.html must contain an html root element")
    if not inspector.has_trip_map:
        errors.append("manifest.files.html must contain the #trip-map Leaflet container")
    if not inspector.leaflet_scripts:
        errors.append("manifest.files.html must load the Leaflet script")
    if not inspector.leaflet_stylesheets:
        errors.append("manifest.files.html must load the Leaflet stylesheet")
    if "window.__MAP_DATA__" not in html:
        errors.append("manifest.files.html must embed window.__MAP_DATA__")
    embedded_map_data = None
    if not inspector.map_data_chunks:
        errors.append("manifest.files.html must include structured #trip-map-data JSON")
    else:
        try:
            embedded_map_data = json.loads("".join(inspector.map_data_chunks))
        except json.JSONDecodeError as exc:
            errors.append(f"manifest.files.html contains invalid #trip-map-data JSON: {exc}")
    if map_file not in inspector.links and f"./{map_file}" not in inspector.links:
        errors.append(f"manifest.files.html must link to the current map asset: {map_file}")
    return embedded_map_data


def verify_map_asset(path: Path, map_file: str, errors: list[str]) -> None:
    if map_file == "route-map.png":
        try:
            signature = path.read_bytes()[:8]
        except OSError as exc:
            errors.append(f"manifest.files.map_image is not readable: {exc}")
            return
        if signature != b"\x89PNG\r\n\x1a\n":
            errors.append("route-map.png must have a valid PNG signature")
        return

    if map_file == "route-map.svg":
        try:
            root = ElementTree.parse(path).getroot()
        except (OSError, ElementTree.ParseError) as exc:
            errors.append(f"route-map.svg must be valid XML: {exc}")
            return
        if root.tag.rsplit("}", 1)[-1] != "svg":
            errors.append("route-map.svg root element must be svg")
        if not list(root):
            errors.append("route-map.svg must contain rendered map elements")


def verify_pdf_asset(path: Path, errors: list[str]) -> None:
    try:
        with path.open("rb") as handle:
            signature = handle.read(5)
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 1024))
            trailer = handle.read()
    except OSError as exc:
        errors.append(f"manifest.files.pdf is not readable: {exc}")
        return
    if signature != b"%PDF-":
        errors.append("trip.pdf must have a valid PDF signature")
    if b"%%EOF" not in trailer:
        errors.append("trip.pdf must contain a PDF end-of-file marker")


def verify_manifest_schema(manifest: dict[str, Any], errors: list[str]) -> None:
    for field in sorted(MANIFEST_CONTRACT_FIELDS - manifest.keys()):
        errors.append(f"manifest missing required field: {field}")
    for field in sorted(manifest.keys() - MANIFEST_CONTRACT_FIELDS):
        errors.append(f"manifest has unsupported field: {field}")

    if manifest.get("schema_version") != 1:
        errors.append(f"manifest.schema_version is {manifest.get('schema_version')}, expected 1")

    if manifest.get("mode") not in MODE_CHOICES:
        errors.append(f"manifest.mode is unsupported: {manifest.get('mode')}")

    if not isinstance(manifest.get("title"), str):
        errors.append("manifest.title must be a string")
    elif not is_non_empty_string(manifest["title"]):
        errors.append("manifest.title must be a non-empty string")

    start_date = manifest.get("start_date")
    if start_date is not None and (not isinstance(start_date, str) or not is_iso_date(start_date)):
        errors.append("manifest.start_date must be null or an ISO date string YYYY-MM-DD")

    if not is_non_empty_string(manifest.get("data_source")):
        errors.append("manifest.data_source must be a non-empty string")

    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        errors.append("manifest.counts must be an object")
    else:
        for key in ("days", "driving_days", "legs", "estimated_legs"):
            if not is_integer(counts.get(key)) or counts.get(key) < 0:
                errors.append(f"manifest.counts.{key} must be a non-negative integer")

    source_counts = manifest.get("source_counts")
    if not isinstance(source_counts, dict):
        errors.append("manifest.source_counts must be an object")
    else:
        for source, count in source_counts.items():
            if not is_non_empty_string(source):
                errors.append("manifest.source_counts keys must be non-empty strings")
            if not is_integer(count) or count < 0:
                errors.append(f"manifest.source_counts.{source} must be a non-negative integer")


def verify_manifest_files_contract(files: dict[str, Any], mode: Any, errors: list[str]) -> None:
    for field in files:
        if field not in MANIFEST_FILE_FIELDS:
            errors.append(f"manifest.files has unsupported field: {field}")

    if files.get("data") != "trip-data.json":
        errors.append("manifest.files.data must be trip-data.json")
    if files.get("manifest") != "manifest.json":
        errors.append("manifest.files.manifest must be manifest.json")

    html = files.get("html")
    if mode == "publish-demo":
        if html != "index.html":
            errors.append("manifest.files.html must be index.html in publish-demo mode")
    elif mode in ("auto", "estimate", "accurate"):
        if html != "trip.html":
            errors.append(f"manifest.files.html must be trip.html in {mode} mode")
    elif mode == "data-only":
        if html is not None:
            errors.append("manifest.files.html must be null in data-only mode")

    map_image = files.get("map_image")
    if mode == "data-only":
        if map_image is not None:
            errors.append("manifest.files.map_image must be null in data-only mode")
    elif mode in ("auto", "estimate", "accurate", "publish-demo"):
        if map_image not in ("route-map.png", "route-map.svg"):
            errors.append("manifest.files.map_image must be route-map.png or route-map.svg")

    pdf = files.get("pdf")
    if mode == "data-only" and pdf is not None:
        errors.append("manifest.files.pdf must be null in data-only mode")
    elif pdf is not None and pdf != "trip.pdf":
        errors.append("manifest.files.pdf must be trip.pdf or null")


def verify_trip_data_schema(data: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(data.get("title"), str):
        errors.append("trip-data.json.title must be a string")
    elif not is_non_empty_string(data["title"]):
        errors.append("trip-data.json.title must be a non-empty string")

    start_date = data.get("start_date")
    if start_date is not None and (not isinstance(start_date, str) or not is_iso_date(start_date)):
        errors.append("trip-data.json.start_date must be null or an ISO date string YYYY-MM-DD")

    for field in ("map_png_error", "map_svg_error", "pdf_error"):
        if field in data and not is_non_empty_string(data[field]):
            errors.append(f"trip-data.json.{field} must be a non-empty string when present")


def verify_day_schema(day: dict[str, Any], label: str, errors: list[str]) -> None:
    title = day.get("title")
    if not is_non_empty_string(title):
        errors.append(f"{label} field title must be a non-empty string")

    notes = day.get("notes")
    if not isinstance(notes, list) or any(not is_non_empty_string(note) for note in notes):
        errors.append(f"{label} field notes must be a list of non-empty strings")

    for key in ("distance_km", "duration_min", "toll_cny"):
        if key not in day:
            errors.append(f"{label} missing required field: {key}")
        elif not is_number(day[key]):
            errors.append(f"{label} field {key} must be numeric")
        elif day[key] < 0:
            errors.append(f"{label} field {key} must be non-negative")
    if "estimated" not in day:
        errors.append(f"{label} missing required field: estimated")
    elif not isinstance(day["estimated"], bool):
        errors.append(f"{label} field estimated must be a boolean")
    elif isinstance(day.get("legs"), list):
        expected_estimated = any(
            isinstance(leg, dict) and leg.get("estimated") is True
            for leg in day["legs"]
        )
        if day["estimated"] != expected_estimated:
            errors.append(
                f"{label}.estimated is {str(day['estimated']).lower()}, "
                f"expected {str(expected_estimated).lower()} from its legs"
            )


def driving_legs(data: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    days = data.get("days")
    if not isinstance(days, list):
        errors.append("trip-data.json field days must be a list")
        return []

    legs: list[dict[str, Any]] = []
    seen_day_labels: set[str] = set()
    for day_index, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            errors.append(f"day #{day_index} must be an object")
            continue
        day_label = day.get("day")
        if not isinstance(day_label, str) or not day_label:
            label = f"day #{day_index}"
            errors.append(f"{label} field day must be a non-empty string")
        else:
            label = day_label
            if not is_normalized_day_label(day_label):
                errors.append(f"{label} field day must use normalized D1/D2 format")
            if day_label in seen_day_labels:
                errors.append(f"duplicate trip-data.json day label: {day_label}")
            seen_day_labels.add(day_label)
        verify_day_schema(day, label, errors)
        day_legs = day.get("legs")
        if not isinstance(day_legs, list):
            errors.append(f"{label} field legs must be a list")
            continue
        for leg_index, leg in enumerate(day_legs, start=1):
            if not isinstance(leg, dict):
                errors.append(f"{label} leg #{leg_index} must be an object")
                continue
            legs.append(leg)
    return legs


def verify_leg_contract(legs: list[dict[str, Any]], errors: list[str]) -> None:
    required_keys = ("from", "to", "distance_km", "duration_min", "toll_cny", "source", "estimated")
    for index, leg in enumerate(legs, start=1):
        label = f"leg #{index} {leg.get('from', '?')}->{leg.get('to', '?')}"
        for key in required_keys:
            if key not in leg:
                errors.append(f"{label} missing required field: {key}")
        for key in ("from", "to", "source"):
            if key in leg and not is_non_empty_string(leg[key]):
                errors.append(f"{label} field {key} must be a non-empty string")
        if isinstance(leg.get("source"), str) and leg["source"] not in LEG_SOURCE_CHOICES:
            errors.append(f"{label} field source is unsupported: {leg['source']}")
        for key in ("distance_km", "duration_min", "toll_cny"):
            if key in leg and not is_number(leg[key]):
                errors.append(f"{label} field {key} must be numeric")
            elif key in leg and leg[key] < 0:
                errors.append(f"{label} field {key} must be non-negative")
        if "estimated" in leg and not isinstance(leg["estimated"], bool):
            errors.append(f"{label} field estimated must be a boolean")
        if leg.get("source") == "estimated" and leg.get("estimated") is False:
            errors.append(f"{label} source estimated requires estimated=true")
        if "lookup_error" in leg and not is_non_empty_string(leg["lookup_error"]):
            errors.append(f"{label} field lookup_error must be a non-empty string when present")
        for key in ("origin", "destination"):
            if key in leg and leg[key] is not None:
                verify_point(leg[key], f"{label}.{key}", errors)
        if "polyline" in leg and leg["polyline"] is not None:
            verify_polyline(leg["polyline"], f"{label}.polyline", errors)


def verify_point(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object with numeric lng/lat")
        return
    for key in ("lng", "lat"):
        if not is_number(value.get(key)):
            errors.append(f"{label}.{key} must be numeric")
    if is_number(value.get("lng")) and not -180 <= value["lng"] <= 180:
        errors.append(f"{label}.lng must be between -180 and 180")
    if is_number(value.get("lat")) and not -90 <= value["lat"] <= 90:
        errors.append(f"{label}.lat must be between -90 and 90")


def verify_polyline(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list of [lng, lat] points")
        return
    if len(value) == 1:
        errors.append(f"{label} must be empty or contain at least two points")
    for point_index, point in enumerate(value, start=1):
        if (
            not isinstance(point, list)
            or len(point) != 2
            or not is_number(point[0])
            or not is_number(point[1])
        ):
            errors.append(f"{label}[{point_index}] must be [lng, lat] numeric pair")
            continue
        if not -180 <= point[0] <= 180:
            errors.append(f"{label}[{point_index}] longitude must be between -180 and 180")
        if not -90 <= point[1] <= 90:
            errors.append(f"{label}[{point_index}] latitude must be between -90 and 90")


def verify_totals_and_counts(manifest: dict[str, Any], data: dict[str, Any], legs: list[dict[str, Any]], errors: list[str]) -> None:
    counts = manifest.get("counts")
    if not isinstance(counts, dict):
        errors.append("manifest.counts must be an object")
        return

    days = data.get("days") or []
    expected = {
        "days": len(days) if isinstance(days, list) else 0,
        "driving_days": sum(1 for day in days if isinstance(day, dict) and day.get("legs")),
        "legs": len(legs),
        "estimated_legs": sum(1 for leg in legs if leg.get("estimated")),
    }
    for key, expected_value in expected.items():
        actual_value = counts.get(key)
        if actual_value != expected_value:
            errors.append(f"manifest.counts.{key} is {actual_value}, expected {expected_value}")

    source_counts: dict[str, int] = {}
    for leg in legs:
        source = str(leg.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    if manifest.get("source_counts") != source_counts:
        errors.append(f"manifest.source_counts is {manifest.get('source_counts')}, expected {source_counts}")

    for owner_name, owner in (("manifest", manifest), ("trip-data.json", data)):
        totals = owner.get("totals")
        if not isinstance(totals, dict):
            errors.append(f"{owner_name}.totals must be an object")
            continue
        for key in ("distance_km", "duration_min", "toll_cny"):
            if key not in totals:
                errors.append(f"{owner_name}.totals missing required field: {key}")
            elif not is_number(totals[key]):
                errors.append(f"{owner_name}.totals.{key} must be numeric")
            elif totals[key] < 0:
                errors.append(f"{owner_name}.totals.{key} must be non-negative")

    verify_metric_rollups(manifest, data, errors)


def verify_metric_rollups(manifest: dict[str, Any], data: dict[str, Any], errors: list[str]) -> None:
    days = data.get("days")
    if not isinstance(days, list):
        return

    day_specs = (("distance_km", 1), ("duration_min", 0), ("toll_cny", 0))
    for day_index, day in enumerate(days, start=1):
        if not isinstance(day, dict):
            continue
        legs = day.get("legs")
        if not isinstance(legs, list):
            continue
        label = day.get("day", f"day #{day_index}")
        expected = {
            "distance_km": sum(float(leg.get("distance_km", 0)) for leg in legs if isinstance(leg, dict) and is_number(leg.get("distance_km"))),
            "duration_min": sum(int(leg.get("duration_min", 0)) for leg in legs if isinstance(leg, dict) and is_number(leg.get("duration_min"))),
            "toll_cny": sum(float(leg.get("toll_cny", 0)) for leg in legs if isinstance(leg, dict) and is_number(leg.get("toll_cny"))),
        }
        for key, digits in day_specs:
            actual = day.get(key)
            if not totals_match(actual, expected[key], digits):
                errors.append(f"{label}.{key} is {actual}, expected {rounded_total(expected[key], digits)}")

    data_totals = data.get("totals")
    manifest_totals = manifest.get("totals")
    if not isinstance(data_totals, dict) or not isinstance(manifest_totals, dict):
        return

    expected_trip = {
        "distance_km": sum(float(day.get("distance_km", 0)) for day in days if isinstance(day, dict) and is_number(day.get("distance_km"))),
        "duration_min": sum(int(day.get("duration_min", 0)) for day in days if isinstance(day, dict) and is_number(day.get("duration_min"))),
        "toll_cny": sum(float(day.get("toll_cny", 0)) for day in days if isinstance(day, dict) and is_number(day.get("toll_cny"))),
    }
    for key, digits in day_specs:
        expected_value = rounded_total(expected_trip[key], digits)
        if not totals_match(data_totals.get(key), expected_trip[key], digits):
            errors.append(f"trip-data.json.totals.{key} is {data_totals.get(key)}, expected {expected_value}")
        if is_number(data_totals.get(key)) and not totals_match(manifest_totals.get(key), data_totals[key], digits):
            errors.append(f"manifest.totals.{key} is {manifest_totals.get(key)}, expected {rounded_total(data_totals[key], digits)}")


def verify_budget_rollups(data: dict[str, Any], errors: list[str]) -> None:
    budget = data.get("budget")
    if not isinstance(budget, dict):
        errors.append("trip-data.json.budget must be an object")
        return

    for field in sorted(BUDGET_CONTRACT_FIELDS - budget.keys()):
        errors.append(f"trip-data.json.budget missing required field: {field}")
    for field in sorted(budget.keys() - BUDGET_CONTRACT_FIELDS):
        errors.append(f"trip-data.json.budget has unsupported field: {field}")

    if budget.get("currency") != "CNY":
        errors.append(f"trip-data.json.budget.currency is {budget.get('currency')}, expected CNY")
    if not isinstance(budget.get("configured"), bool):
        errors.append("trip-data.json.budget.configured must be a boolean")
    if not is_number(budget.get("total_cny")):
        errors.append("trip-data.json.budget.total_cny must be numeric")
    elif budget["total_cny"] < 0:
        errors.append("trip-data.json.budget.total_cny must be non-negative")

    category_totals = budget.get("category_totals")
    if not isinstance(category_totals, dict):
        errors.append("trip-data.json.budget.category_totals must be an object")
        return

    items = budget.get("items")
    if not isinstance(items, list):
        errors.append("trip-data.json.budget.items must be a list")
        return

    missing_attractions = budget.get("missing_attractions")
    if not isinstance(missing_attractions, list):
        errors.append("trip-data.json.budget.missing_attractions must be a list")
    else:
        verify_missing_attractions_schema(missing_attractions, errors)
    warnings = budget.get("warnings")
    if not isinstance(warnings, list) or any(not is_non_empty_string(warning) for warning in warnings):
        errors.append("trip-data.json.budget.warnings must be a list of non-empty strings")
    elif len(warnings) != len(set(warnings)):
        errors.append("trip-data.json.budget.warnings must not contain duplicates")
    verify_budget_assumptions(budget, data, errors)
    assumptions = budget.get("assumptions")
    passenger_counts = assumptions.get("passengers") if isinstance(assumptions, dict) else None
    if not isinstance(passenger_counts, dict) or any(
        not is_integer(passenger_counts.get(key)) or passenger_counts.get(key) < 0
        for key in ("adults", "children_under_1_2m", "children_over_1_2m")
    ):
        passenger_counts = None

    expected_by_category: dict[str, float] = {}
    for item_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"trip-data.json.budget.items[{item_index}] must be an object")
            continue
        verify_budget_item_schema(item, item_index, errors, passenger_counts)
        category = item.get("category")
        amount = item.get("amount_cny")
        if not is_non_empty_string(category):
            errors.append(f"trip-data.json.budget.items[{item_index}].category must be a non-empty string")
            continue
        if category not in BUDGET_CATEGORY_CHOICES:
            errors.append(
                f"trip-data.json.budget.items[{item_index}].category is unsupported: {category}"
            )
        if not is_number(amount):
            errors.append(f"trip-data.json.budget.items[{item_index}].amount_cny must be numeric")
            continue
        if amount < 0:
            errors.append(f"trip-data.json.budget.items[{item_index}].amount_cny must be non-negative")
        expected_by_category[category] = expected_by_category.get(category, 0.0) + float(amount)

    for category, expected_amount in sorted(expected_by_category.items()):
        actual_amount = category_totals.get(category)
        if not money_totals_match(actual_amount, expected_amount):
            errors.append(
                f"trip-data.json.budget.category_totals.{category} is {actual_amount}, "
                f"expected {rounded_total(expected_amount, 2)}"
            )

    for category, actual_amount in sorted(category_totals.items()):
        if category not in BUDGET_CATEGORY_CHOICES:
            errors.append(f"trip-data.json.budget.category_totals has unsupported category: {category}")
        if not is_number(actual_amount):
            errors.append(f"trip-data.json.budget.category_totals.{category} must be numeric")
        elif actual_amount < 0:
            errors.append(f"trip-data.json.budget.category_totals.{category} must be non-negative")
        elif category not in expected_by_category:
            errors.append(f"trip-data.json.budget.category_totals.{category} has no matching budget items")

    expected_total = sum(float(amount) for amount in category_totals.values() if is_number(amount))
    if not money_totals_match(budget.get("total_cny"), expected_total):
        errors.append(f"trip-data.json.budget.total_cny is {budget.get('total_cny')}, expected {rounded_total(expected_total, 2)}")


def expected_trip_day_count(data: dict[str, Any]) -> int:
    days = data.get("days")
    if not isinstance(days, list):
        return 0
    day_numbers = [
        int(day["day"][1:])
        for day in days
        if isinstance(day, dict)
        and isinstance(day.get("day"), str)
        and is_normalized_day_label(day["day"])
    ]
    return max([len(days), *day_numbers])


def verify_budget_assumptions(
    budget: dict[str, Any],
    data: dict[str, Any],
    errors: list[str],
) -> None:
    assumptions = budget.get("assumptions")
    label = "trip-data.json.budget.assumptions"
    if not isinstance(assumptions, dict):
        errors.append(f"{label} must be an object")
        return

    trip_days = assumptions.get("trip_days")
    if not is_integer(trip_days) or trip_days < 1:
        errors.append(f"{label}.trip_days must be a positive integer")
    else:
        expected_days = expected_trip_day_count(data)
        if trip_days != expected_days:
            errors.append(f"{label}.trip_days is {trip_days}, expected {expected_days}")

    distance_km = assumptions.get("distance_km")
    if not is_number(distance_km):
        errors.append(f"{label}.distance_km must be numeric")
    elif distance_km < 0:
        errors.append(f"{label}.distance_km must be non-negative")
    else:
        totals = data.get("totals")
        if isinstance(totals, dict) and is_number(totals.get("distance_km")):
            if not totals_match(distance_km, totals["distance_km"], 1):
                errors.append(
                    f"{label}.distance_km is {distance_km}, "
                    f"expected {rounded_total(totals['distance_km'], 1)}"
                )

    passengers = assumptions.get("passengers")
    if not isinstance(passengers, dict):
        errors.append(f"{label}.passengers must be an object")
    else:
        for key in ("adults", "children_under_1_2m", "children_over_1_2m"):
            if not is_integer(passengers.get(key)) or passengers.get(key) < 0:
                errors.append(f"{label}.passengers.{key} must be a non-negative integer")

    expected_category_amounts: dict[str, float] = {}

    if "vehicle" in assumptions:
        vehicle = assumptions["vehicle"]
        vehicle_label = f"{label}.vehicle"
        if not isinstance(vehicle, dict):
            errors.append(f"{vehicle_label} must be an object")
        else:
            if vehicle.get("type") != "ev":
                errors.append(f"{vehicle_label}.type must be ev")
            numeric_fields = ("kwh_price_cny", "kwh_per_100km", "estimated_kwh")
            valid_numbers = True
            for key in numeric_fields:
                if not is_number(vehicle.get(key)):
                    errors.append(f"{vehicle_label}.{key} must be numeric")
                    valid_numbers = False
                elif vehicle[key] < 0:
                    errors.append(f"{vehicle_label}.{key} must be non-negative")
                    valid_numbers = False
            if valid_numbers and is_number(distance_km):
                expected_kwh = float(distance_km) * float(vehicle["kwh_per_100km"]) / 100
                if not totals_match(vehicle["estimated_kwh"], expected_kwh, 1):
                    errors.append(
                        f"{vehicle_label}.estimated_kwh is {vehicle['estimated_kwh']}, "
                        f"expected {rounded_total(expected_kwh, 1)}"
                    )
                expected_category_amounts["vehicle_energy"] = (
                    expected_kwh * float(vehicle["kwh_price_cny"])
                )

    for assumption_key, rate_key, count_key, category in (
        ("hotel", "nightly_cny", "nights", "hotel"),
        ("meal", "daily_cny", "days", "meal"),
    ):
        if assumption_key not in assumptions:
            continue
        value = assumptions[assumption_key]
        value_label = f"{label}.{assumption_key}"
        if not isinstance(value, dict):
            errors.append(f"{value_label} must be an object")
            continue
        rate = value.get(rate_key)
        count = value.get(count_key)
        valid_rate = is_number(rate) and rate >= 0
        valid_count = is_integer(count) and count >= 0
        if not is_number(rate):
            errors.append(f"{value_label}.{rate_key} must be numeric")
        elif rate < 0:
            errors.append(f"{value_label}.{rate_key} must be non-negative")
        if not valid_count:
            errors.append(f"{value_label}.{count_key} must be a non-negative integer")
        if valid_rate and valid_count:
            expected_category_amounts[category] = float(rate) * int(count)

    category_totals = budget.get("category_totals")
    if not isinstance(category_totals, dict):
        return
    assumption_categories = {
        "vehicle": "vehicle_energy",
        "hotel": "hotel",
        "meal": "meal",
    }
    for assumption_key, category in assumption_categories.items():
        if category in category_totals and assumption_key not in assumptions:
            errors.append(f"{label}.{assumption_key} is required for budget category {category}")
    for category, expected_amount in expected_category_amounts.items():
        actual_amount = category_totals.get(category)
        if not money_totals_match(actual_amount, expected_amount):
            errors.append(
                f"trip-data.json.budget.category_totals.{category} is {actual_amount}, "
                f"expected {rounded_total(expected_amount, 2)} from assumptions"
            )


def verify_budget_item_schema(
    item: dict[str, Any],
    item_index: int,
    errors: list[str],
    passenger_counts: dict[str, int] | None,
) -> None:
    label = f"trip-data.json.budget.items[{item_index}]"
    if not is_non_empty_string(item.get("label")):
        errors.append(f"{label}.label must be a non-empty string")
    if not is_non_empty_string(item.get("detail")):
        errors.append(f"{label}.detail must be a non-empty string")

    for key in ("quantity", "unit_price_cny", "adult_price_cny"):
        if key in item and not is_number(item[key]):
            errors.append(f"{label}.{key} must be numeric")
        elif key in item and item[key] < 0:
            errors.append(f"{label}.{key} must be non-negative")
    for key in ("charged_adults", "free_children_under_1_2m", "half_price_children_over_1_2m"):
        if key in item and (not is_integer(item[key]) or item[key] < 0):
            errors.append(f"{label}.{key} must be a non-negative integer")

    has_quantity = "quantity" in item
    has_unit_price = "unit_price_cny" in item
    if has_quantity != has_unit_price:
        errors.append(f"{label}.quantity and unit_price_cny must be provided together")
    elif (
        has_quantity
        and is_number(item.get("quantity"))
        and item["quantity"] >= 0
        and is_number(item.get("unit_price_cny"))
        and item["unit_price_cny"] >= 0
        and is_number(item.get("amount_cny"))
    ):
        expected_item_amount = float(item["quantity"]) * float(item["unit_price_cny"])
        if not money_totals_match(item["amount_cny"], expected_item_amount):
            errors.append(
                f"{label}.amount_cny is {item['amount_cny']}, "
                f"expected {rounded_total(expected_item_amount, 2)} from quantity * unit price"
            )

    ticket_fields = (
        "adult_price_cny",
        "charged_adults",
        "free_children_under_1_2m",
        "half_price_children_over_1_2m",
    )
    if any(key in item for key in ticket_fields):
        for key in ticket_fields:
            if key not in item:
                errors.append(f"{label} missing ticket field: {key}")
        adult_price = item.get("adult_price_cny")
        charged_adults = item.get("charged_adults")
        free_children = item.get("free_children_under_1_2m")
        half_children = item.get("half_price_children_over_1_2m")
        valid_ticket_numbers = (
            is_number(adult_price)
            and adult_price >= 0
            and is_integer(charged_adults)
            and charged_adults >= 0
            and is_integer(free_children)
            and free_children >= 0
            and is_integer(half_children)
            and half_children >= 0
        )
        if valid_ticket_numbers and is_number(item.get("amount_cny")):
            expected_ticket_amount = (
                int(charged_adults) * float(adult_price)
                + int(half_children) * float(adult_price) * 0.5
            )
            if not money_totals_match(item["amount_cny"], expected_ticket_amount):
                errors.append(
                    f"{label}.amount_cny is {item['amount_cny']}, "
                    f"expected {rounded_total(expected_ticket_amount, 2)} from ticket counts"
                )
        if passenger_counts is not None:
            passenger_fields = {
                "charged_adults": "adults",
                "free_children_under_1_2m": "children_under_1_2m",
                "half_price_children_over_1_2m": "children_over_1_2m",
            }
            for item_key, passenger_key in passenger_fields.items():
                if is_integer(item.get(item_key)) and item[item_key] != passenger_counts[passenger_key]:
                    errors.append(
                        f"{label}.{item_key} is {item[item_key]}, "
                        f"expected passengers.{passenger_key} {passenger_counts[passenger_key]}"
                    )

    components = item.get("components")
    if components is None:
        return
    if not isinstance(components, list):
        errors.append(f"{label}.components must be a list")
        return

    expected_amount = 0.0
    all_amounts_valid = True
    for component_index, component in enumerate(components, start=1):
        component_label = f"{label}.components[{component_index}]"
        if not isinstance(component, dict):
            errors.append(f"{component_label} must be an object")
            all_amounts_valid = False
            continue
        if not is_non_empty_string(component.get("label")):
            errors.append(f"{component_label}.label must be a non-empty string")
        if component.get("charge") not in ("free", "per_person"):
            errors.append(f"{component_label}.charge must be free or per_person")
        for key in ("unit_price_cny", "quantity", "amount_cny"):
            if not is_number(component.get(key)):
                errors.append(f"{component_label}.{key} must be numeric")
                all_amounts_valid = False
            elif component[key] < 0:
                errors.append(f"{component_label}.{key} must be non-negative")
                all_amounts_valid = False
        component_numbers_valid = all(
            is_number(component.get(key)) and component[key] >= 0
            for key in ("unit_price_cny", "quantity", "amount_cny")
        )
        if component_numbers_valid:
            expected_component_amount = None
            if component.get("charge") == "free":
                expected_component_amount = 0.0
                if component["quantity"] != 0:
                    errors.append(f"{component_label}.quantity must be 0 when charge is free")
            elif component.get("charge") == "per_person":
                expected_component_amount = float(component["unit_price_cny"]) * float(component["quantity"])
                if passenger_counts is not None:
                    expected_people = sum(
                        passenger_counts[key]
                        for key in ("adults", "children_under_1_2m", "children_over_1_2m")
                    )
                    if component["quantity"] != expected_people:
                        errors.append(
                            f"{component_label}.quantity is {component['quantity']}, "
                            f"expected total passengers {expected_people}"
                        )
            if (
                expected_component_amount is not None
                and not money_totals_match(component["amount_cny"], expected_component_amount)
            ):
                errors.append(
                    f"{component_label}.amount_cny is {component['amount_cny']}, "
                    f"expected {rounded_total(expected_component_amount, 2)} from component rules"
                )
        if is_number(component.get("amount_cny")):
            expected_amount += float(component["amount_cny"])

    if all_amounts_valid and is_number(item.get("amount_cny")) and not money_totals_match(item.get("amount_cny"), expected_amount):
        errors.append(f"{label}.components total is {rounded_total(expected_amount, 2)}, expected item amount {item.get('amount_cny')}")


def verify_missing_attractions_schema(missing_attractions: list[Any], errors: list[str]) -> None:
    for item_index, item in enumerate(missing_attractions, start=1):
        label = f"trip-data.json.budget.missing_attractions[{item_index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        if not is_non_empty_string(item.get("name")):
            errors.append(f"{label}.name must be a non-empty string")
        if not isinstance(item.get("matched_names"), list) or any(not is_non_empty_string(value) for value in item.get("matched_names") or []):
            errors.append(f"{label}.matched_names must be a list of non-empty strings")
        if not isinstance(item.get("days"), list) or any(not is_non_empty_string(value) for value in item.get("days") or []):
            errors.append(f"{label}.days must be a list of non-empty strings")
        if not is_non_empty_string(item.get("suggestion")):
            errors.append(f"{label}.suggestion must be a non-empty string")


def verify_mode_source_contract(mode: str, legs: list[dict[str, Any]], errors: list[str]) -> None:
    if mode not in KEY_REQUIRED_MODES:
        return
    for leg in legs:
        if not is_complete_amap_leg(leg):
            errors.append(
                f"{mode} mode requires complete Amap leg data: "
                f"{leg.get('from', '?')}->{leg.get('to', '?')}"
            )


def verify_manifest_data_consistency(
    manifest: dict[str, Any],
    data: dict[str, Any],
    files: dict[str, Any],
    legs: list[dict[str, Any]],
    mode: str,
    errors: list[str],
) -> None:
    expected_source_counts = manifest.get("source_counts") or {}
    if not isinstance(expected_source_counts, dict):
        errors.append("manifest.source_counts must be an object")
        expected_source_counts = {}
    if not expected_source_counts:
        expected_data_source = "none"
    elif len(expected_source_counts) == 1:
        expected_data_source = next(iter(expected_source_counts))
    else:
        expected_data_source = "mixed"
    if manifest.get("data_source") != expected_data_source:
        errors.append(f"manifest.data_source is {manifest.get('data_source')}, expected {expected_data_source}")

    if manifest.get("title") != data.get("title"):
        errors.append("manifest.title must match trip-data.json title")
    if manifest.get("start_date") != data.get("start_date"):
        errors.append("manifest.start_date must match trip-data.json start_date")

    warnings = manifest.get("warnings")
    if not isinstance(warnings, list) or any(not is_non_empty_string(warning) for warning in warnings):
        errors.append("manifest.warnings must be a list of non-empty strings")
        warnings = []
    elif len(warnings) != len(set(warnings)):
        errors.append("manifest.warnings must not contain duplicates")

    if manifest.get("budget") != data.get("budget"):
        errors.append("manifest.budget must match trip-data.json budget")
    if data.get("pdf_error") and files.get("pdf"):
        errors.append("manifest.files.pdf must be null when trip-data.json contains pdf_error")

    verify_warning_coverage(data, legs, list(warnings), files, mode, errors)

    manifest_map = manifest.get("map")
    data_map = data.get("map")
    map_file = files.get("map_image")
    if mode == "data-only":
        if manifest_map is not None:
            errors.append("data-only output must not include manifest.map")
        if data_map is not None:
            errors.append("data-only output must not include trip-data.json map")
        return

    if not isinstance(manifest_map, dict):
        errors.append("non-data-only output must include manifest.map")
        return
    if manifest_map != data_map:
        errors.append("manifest.map must match trip-data.json map")
    if manifest_map.get("file") != map_file:
        errors.append(f"manifest.map.file is {manifest_map.get('file')}, expected manifest.files.map_image {map_file}")
    source = manifest_map.get("source")
    if not isinstance(source, str) or source not in MAP_OUTPUT_CONTRACT:
        errors.append(f"manifest.map.source is unsupported: {source}")
    else:
        expected_map = MAP_OUTPUT_CONTRACT[source]
        if manifest_map.get("file") != expected_map["file"]:
            errors.append(
                f"manifest.map source {source} requires file {expected_map['file']}"
            )
        if manifest_map.get("fallback") != expected_map["fallback"]:
            errors.append(
                f"manifest.map source {source} requires fallback={str(expected_map['fallback']).lower()}"
            )
    if not isinstance(manifest_map.get("fallback"), bool):
        errors.append("manifest.map.fallback must be a boolean")
    if "note" in manifest_map and not is_non_empty_string(manifest_map["note"]):
        errors.append("manifest.map.note must be a non-empty string when present")


def require_warning(warnings: list[str], expected_text: str, errors: list[str]) -> None:
    if not any(expected_text in warning for warning in warnings):
        errors.append(f"manifest.warnings missing expected text: {expected_text}")


def reject_stale_warning(warnings: list[str], expected_text: str, errors: list[str]) -> None:
    if any(expected_text in warning for warning in warnings):
        errors.append(f"manifest.warnings contains stale expected text: {expected_text}")


def verify_derived_warning(
    warnings: list[str],
    condition: bool,
    expected_text: str,
    errors: list[str],
) -> None:
    if condition:
        require_warning(warnings, expected_text, errors)
    else:
        reject_stale_warning(warnings, expected_text, errors)


def verify_warning_coverage(
    data: dict[str, Any],
    legs: list[dict[str, Any]],
    warnings: list[str],
    files: dict[str, Any],
    mode: str,
    errors: list[str],
) -> None:
    verify_derived_warning(warnings, any(leg.get("estimated") for leg in legs), "estimated metrics", errors)
    verify_derived_warning(
        warnings,
        any(not leg.get("origin") or not leg.get("destination") for leg in legs),
        "could not be geocoded",
        errors,
    )
    verify_derived_warning(warnings, any(leg.get("lookup_error") for leg in legs), "Map lookup errors occurred", errors)
    verify_derived_warning(warnings, bool(data.get("map_png_error")), "PNG map generation failed", errors)
    verify_derived_warning(warnings, bool(data.get("map_svg_error")), "SVG map generation failed", errors)
    verify_derived_warning(warnings, bool(data.get("pdf_error")), "PDF generation failed", errors)
    verify_derived_warning(
        warnings,
        bool(data.get("map", {}).get("fallback")) and mode != "data-only",
        "Static route image fell back",
        errors,
    )
    verify_derived_warning(
        warnings,
        mode != "data-only" and not files.get("map_image"),
        "No static route image was generated",
        errors,
    )
    verify_derived_warning(
        warnings,
        mode == "data-only",
        "Data-only mode skipped HTML and route image generation",
        errors,
    )

    budget = data.get("budget")
    if isinstance(budget, dict):
        for warning in budget.get("warnings") or []:
            require_warning(warnings, str(warning), errors)


def verify_output_dir(out_dir: Path) -> list[str]:
    errors: list[str] = []
    manifest_path = out_dir / "manifest.json"
    manifest = load_json(manifest_path, errors)
    if not isinstance(manifest, dict):
        return errors
    verify_manifest_schema(manifest, errors)

    files = manifest.get("files")
    if not isinstance(files, dict):
        errors.append("manifest.files must be an object")
        return errors
    verify_manifest_files_contract(files, manifest.get("mode"), errors)

    if not files.get("manifest"):
        errors.append("manifest.files.manifest is required")
    if not files.get("data"):
        errors.append("manifest.files.data is required")

    expected_generated_files = {str(value) for value in files.values() if value}
    for filename in GENERATED_OUTPUT_FILES:
        if filename not in expected_generated_files and (out_dir / filename).exists():
            errors.append(f"stale generated file is not referenced by manifest.files: {filename}")

    manifest_file_path(out_dir, files.get("manifest"), "manifest", errors)
    data_path = manifest_file_path(out_dir, files.get("data"), "data", errors)
    html_path = manifest_file_path(out_dir, files.get("html"), "html", errors)
    map_path = manifest_file_path(out_dir, files.get("map_image"), "map_image", errors)
    pdf_path = manifest_file_path(out_dir, files.get("pdf"), "pdf", errors)

    mode = manifest.get("mode")
    embedded_map_data = None
    if mode != "data-only":
        if html_path is None:
            errors.append("non-data-only output must include manifest.files.html")
        if map_path is None:
            errors.append("non-data-only output must include manifest.files.map_image")
        if html_path is not None and html_path.is_file() and isinstance(files.get("map_image"), str):
            embedded_map_data = verify_html_output(html_path, files["map_image"], errors)
        if map_path is not None and map_path.is_file() and isinstance(files.get("map_image"), str):
            verify_map_asset(map_path, files["map_image"], errors)
        if pdf_path is not None and pdf_path.is_file():
            verify_pdf_asset(pdf_path, errors)
    else:
        if html_path is not None:
            errors.append("data-only output must not include manifest.files.html")
        if map_path is not None:
            errors.append("data-only output must not include manifest.files.map_image")
        if pdf_path is not None:
            errors.append("data-only output must not include manifest.files.pdf")

    if data_path is None or not data_path.is_file():
        return errors
    data = load_json(data_path, errors)
    if not isinstance(data, dict):
        return errors

    if mode != "data-only" and embedded_map_data is not None:
        expected_map_data = build_map_data(data)
        if embedded_map_data != expected_map_data:
            errors.append("manifest.files.html #trip-map-data must match trip-data.json map projection")

    verify_trip_data_schema(data, errors)
    legs = driving_legs(data, errors)
    if not legs:
        errors.append("trip-data.json must include at least one driving leg")
    verify_leg_contract(legs, errors)
    verify_totals_and_counts(manifest, data, legs, errors)
    verify_budget_rollups(data, errors)
    verify_mode_source_contract(str(mode), legs, errors)
    verify_manifest_data_consistency(manifest, data, files, legs, str(mode), errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a generated self-drive trip output directory.")
    parser.add_argument("out_dir", help="Directory containing manifest.json and trip-data.json.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    errors = verify_output_dir(out_dir)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Output contract OK: {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

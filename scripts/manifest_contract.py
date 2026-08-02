"""Manifest and reporting contract helpers for generated trip outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any


MODE_CHOICES = ("auto", "estimate", "accurate", "publish-demo", "data-only")
DEMO_MODE_CHOICES = ("auto", "estimate", "accurate")
API_CAPABLE_MODES = ("auto", "accurate", "publish-demo", "data-only")
KEY_REQUIRED_MODES = ("accurate", "publish-demo")
LEG_SOURCE_CHOICES = ("amap", "estimated")
MAP_OUTPUT_CONTRACT = {
    "leaflet-playwright-screenshot": {"file": "route-map.png", "fallback": False},
    "fallback-svg": {"file": "route-map.svg", "fallback": True},
}
GENERATED_OUTPUT_FILES = (
    "trip-data.json",
    "manifest.json",
    "trip.html",
    "index.html",
    "route-map.png",
    "route-map.svg",
    "budget-summary.png",
    "budget-summary.svg",
    "trip.pdf",
)
MANIFEST_CONTRACT_FIELDS = frozenset(
    {
        "schema_version",
        "mode",
        "title",
        "start_date",
        "data_source",
        "source_counts",
        "files",
        "map",
        "budget",
        "totals",
        "counts",
        "warnings",
    }
)
MANIFEST_FILE_FIELDS = frozenset({"data", "manifest", "html", "map_image", "budget_image", "pdf"})


def unique_warnings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        warning = str(value).strip()
        if warning and warning not in result:
            result.append(warning)
    return result


def source_counts(data: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for day in data["days"]:
        for leg in day["legs"]:
            source = str(leg.get("source") or "unknown")
            counts[source] = counts.get(source, 0) + 1
    return counts


def output_warnings(
    data: dict[str, Any],
    mode: str,
    key: str | None,
    map_file: str | None,
    budget_image_file: str | None = None,
) -> list[str]:
    warnings: list[str] = []
    legs = [leg for day in data["days"] for leg in day["legs"]]
    if mode in ("auto", "data-only") and not key:
        warnings.append("No AMAP_KEY/GAODE_KEY configured; route metrics use estimates where API data is unavailable.")
    if any(leg.get("estimated") for leg in legs):
        warnings.append("One or more driving legs contain estimated metrics; verify before booking or departure.")
    missing_coords = [f'{leg["from"]}->{leg["to"]}' for leg in legs if not leg.get("origin") or not leg.get("destination")]
    if missing_coords:
        warnings.append("Some places could not be geocoded: " + ", ".join(missing_coords))
    lookup_errors = [f'{leg["from"]}->{leg["to"]}: {leg.get("lookup_error")}' for leg in legs if leg.get("lookup_error")]
    if lookup_errors:
        warnings.append("Map lookup errors occurred: " + " | ".join(lookup_errors))
    if data.get("map_png_error"):
        warnings.append(f'PNG map generation failed: {data["map_png_error"]}')
    if data.get("map_svg_error"):
        warnings.append(f'SVG map generation failed: {data["map_svg_error"]}')
    if data.get("budget_image_png_error"):
        warnings.append(f'Budget summary PNG generation failed: {data["budget_image_png_error"]}')
    if data.get("pdf_error"):
        warnings.append(f'PDF generation failed: {data["pdf_error"]}')
    if data.get("budget", {}).get("warnings"):
        warnings.extend(str(warning) for warning in data["budget"]["warnings"])
    if data.get("map", {}).get("fallback"):
        warnings.append("Static route image fell back to schematic SVG; the HTML still contains the interactive route map.")
    if budget_image_file == "budget-summary.svg":
        warnings.append("Budget summary image fell back to SVG.")
    if mode != "data-only" and not map_file:
        warnings.append("No static route image was generated.")
    if mode == "data-only":
        warnings.append("Data-only mode skipped HTML and route image generation.")
    return unique_warnings(warnings)


def build_manifest(
    data: dict[str, Any],
    mode: str,
    out_dir: Path,
    key: str | None,
    html_file: str | None,
    map_file: str | None,
    pdf_file: str | None,
    budget_image_file: str | None = None,
) -> dict[str, Any]:
    counts = source_counts(data)
    if not counts:
        data_source = "none"
    elif len(counts) == 1:
        data_source = next(iter(counts))
    else:
        data_source = "mixed"

    files = {
        "data": "trip-data.json",
        "manifest": "manifest.json",
        "html": html_file if html_file and (out_dir / html_file).exists() else None,
        "map_image": map_file,
        "budget_image": budget_image_file,
        "pdf": pdf_file if pdf_file and (out_dir / pdf_file).exists() else None,
    }
    totals = data.get("totals", {})
    legs = [leg for day in data["days"] for leg in day["legs"]]
    return {
        "schema_version": 1,
        "mode": mode,
        "title": data.get("title", ""),
        "start_date": data.get("start_date"),
        "data_source": data_source,
        "source_counts": counts,
        "files": files,
        "map": data.get("map"),
        "budget": data.get("budget"),
        "totals": totals,
        "counts": {
            "days": len(data["days"]),
            "driving_days": sum(1 for day in data["days"] if day["legs"]),
            "legs": len(legs),
            "estimated_legs": sum(1 for leg in legs if leg.get("estimated")),
        },
        "warnings": output_warnings(data, mode, key, map_file, budget_image_file),
    }


def has_complete_route_geometry(leg: dict[str, Any]) -> bool:
    polyline = leg.get("polyline")
    return bool(
        leg.get("origin")
        and leg.get("destination")
        and isinstance(polyline, list)
        and len(polyline) >= 2
    )


def is_complete_amap_leg(leg: dict[str, Any]) -> bool:
    return bool(
        leg.get("source") == "amap"
        and leg.get("estimated") is False
        and not leg.get("lookup_error")
        and has_complete_route_geometry(leg)
    )


def has_accuracy_failure(data: dict[str, Any]) -> bool:
    legs = [leg for day in data["days"] for leg in day["legs"]]
    return any(not is_complete_amap_leg(leg) for leg in legs)

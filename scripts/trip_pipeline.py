#!/usr/bin/env python3
"""Reusable trip generation pipeline shared by the CLI and agent callers."""

from __future__ import annotations

from copy import deepcopy
import json
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import build_budget, ensure_budget, parse_budget_text, split_budget_section
from html_renderer import generate_html, parse_start_date
from itinerary_parser import parse_itinerary
from manifest_contract import API_CAPABLE_MODES, GENERATED_OUTPUT_FILES, KEY_REQUIRED_MODES, build_manifest, has_accuracy_failure
from output_assets import generate_pdf, generate_route_map
from routing import enrich
from verify_outputs import verify_output_dir


class OutputRunResult:
    def __init__(
        self,
        data: dict[str, Any],
        manifest: dict[str, Any],
        verification_errors: list[str],
        gate_error: str | None = None,
    ) -> None:
        self.data = data
        self.manifest = manifest
        self.verification_errors = verification_errors
        self.gate_error = gate_error

    @property
    def returncode(self) -> int:
        if self.verification_errors:
            return 4
        if self.gate_error:
            return 3
        return 0

    @property
    def stderr(self) -> str:
        if self.verification_errors:
            return "\n".join(self.verification_errors)
        return self.gate_error or ""

    @property
    def accuracy_error(self) -> str | None:
        return self.gate_error


def resolve_mode(requested_mode: str, no_api: bool, key: str | None) -> tuple[str, str | None, bool]:
    mode = "estimate" if no_api else requested_mode
    effective_key = None if mode == "estimate" else key
    use_api = mode in API_CAPABLE_MODES and bool(effective_key)
    return mode, effective_key, use_api


def mode_key_error(mode: str, key: str | None) -> str | None:
    if mode in KEY_REQUIRED_MODES and not key:
        return f"{mode} mode requires AMAP_KEY or GAODE_KEY."
    return None


def default_output_dir(mode: str, out: str | None) -> Path:
    return Path(out) if out else Path("docs" if mode == "publish-demo" else "trip-output")


def clear_generated_metadata(data: dict[str, Any]) -> None:
    for key in ("map", "map_png_error", "map_svg_error", "pdf_error"):
        data.pop(key, None)


def clear_generated_files(out_dir: Path) -> None:
    for filename in GENERATED_OUTPUT_FILES:
        path = out_dir / filename
        if path.is_file():
            path.unlink()


def publish_generated_files(staging_dir: Path, out_dir: Path) -> None:
    """Replace generated outputs and restore the previous set if publishing fails."""
    out_dir.mkdir(parents=True, exist_ok=True)
    publish_order = [
        filename for filename in GENERATED_OUTPUT_FILES
        if filename != "manifest.json"
    ]
    publish_order.append("manifest.json")
    with TemporaryDirectory(prefix=".sdtp-output-backup-", dir=out_dir.parent) as backup_name:
        backup_dir = Path(backup_name)
        backed_up: list[str] = []
        published: list[str] = []
        try:
            for filename in GENERATED_OUTPUT_FILES:
                current_path = out_dir / filename
                if current_path.is_file():
                    os.replace(current_path, backup_dir / filename)
                    backed_up.append(filename)
            # Publish the manifest last so readers only discover the new
            # contract after all files it references are in place.
            for filename in publish_order:
                staged_path = staging_dir / filename
                if staged_path.is_file():
                    os.replace(staged_path, out_dir / filename)
                    published.append(filename)
        except Exception:
            for filename in published:
                published_path = out_dir / filename
                if published_path.is_file():
                    published_path.unlink()
            for filename in backed_up:
                backup_path = backup_dir / filename
                if backup_path.is_file():
                    os.replace(backup_path, out_dir / filename)
            raise


def build_trip_data(
    input_text: str,
    *,
    title: str,
    start_date: str | None = None,
    use_api: bool,
    route_key: str | None = None,
    vehicle_type: str = "none",
    ev_kwh_price: float | None = None,
    ev_kwh_per_100km: float | None = None,
    hotel_nightly: float | None = None,
    hotel_nights: int | None = None,
    meal_daily: float | None = None,
    meal_days: int | None = None,
    attractions: list[dict[str, Any]] | None = None,
    misc_fees: list[dict[str, Any]] | None = None,
    adults: int | None = None,
    children_under_1_2m: int | None = None,
    children_over_1_2m: int | None = None,
) -> dict[str, Any]:
    itinerary_text, budget_text = split_budget_section(input_text)
    natural_budget = parse_budget_text(budget_text)
    days = parse_itinerary(itinerary_text)
    if not any(day.get("legs") for day in days):
        raise ValueError("No route legs found. Use lines such as: 合肥 到 岳阳")

    data = enrich(days, use_api=use_api, key=route_key)
    data["title"] = title
    parsed_start_date = parse_start_date(start_date)
    if parsed_start_date:
        data["start_date"] = parsed_start_date.isoformat()

    resolved_vehicle_type = vehicle_type
    natural_vehicle_type = natural_budget.get("vehicle_type", "none")
    if resolved_vehicle_type == "none" and natural_vehicle_type != "none":
        resolved_vehicle_type = str(natural_vehicle_type)

    resolved_ev_kwh_price = ev_kwh_price if ev_kwh_price is not None else natural_budget.get("ev_kwh_price")
    resolved_ev_kwh_per_100km = ev_kwh_per_100km if ev_kwh_per_100km is not None else natural_budget.get("ev_kwh_per_100km")
    resolved_hotel_nightly = hotel_nightly if hotel_nightly is not None else natural_budget.get("hotel_nightly")
    resolved_meal_daily = meal_daily if meal_daily is not None else natural_budget.get("meal_daily")
    resolved_attractions = [*(natural_budget.get("attractions") or []), *(attractions or [])]
    resolved_misc_fees = [*(natural_budget.get("misc_fees") or []), *(misc_fees or [])]
    passengers = dict(natural_budget.get("passengers") or {})

    if adults is not None:
        passengers["adults"] = adults
    if children_under_1_2m is not None:
        passengers["children_under_1_2m"] = children_under_1_2m
    if children_over_1_2m is not None:
        passengers["children_over_1_2m"] = children_over_1_2m
    if resolved_ev_kwh_price is not None and resolved_vehicle_type == "none":
        resolved_vehicle_type = "ev"
    if resolved_vehicle_type == "ev" and resolved_ev_kwh_price is not None and resolved_ev_kwh_per_100km is None:
        resolved_ev_kwh_per_100km = 16.0

    data["budget"] = build_budget(
        data,
        vehicle_type=resolved_vehicle_type,
        ev_kwh_price=resolved_ev_kwh_price,
        ev_kwh_per_100km=resolved_ev_kwh_per_100km,
        hotel_nightly=resolved_hotel_nightly,
        hotel_nights=hotel_nights,
        meal_daily=resolved_meal_daily,
        meal_days=meal_days,
        attractions=resolved_attractions,
        misc_fees=resolved_misc_fees,
        passengers=passengers,
        warnings=natural_budget.get("warnings"),
    )
    return data


def write_outputs_in_place(
    data: dict[str, Any],
    out_dir: Path,
    key: str | None,
    mode: str,
    pdf: bool,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    clear_generated_files(out_dir)
    ensure_budget(data)
    clear_generated_metadata(data)
    map_file = None
    html_file = None
    pdf_file = None
    if mode != "data-only":
        # IMPORTANT: generate the map FIRST. generate_route_map() mutates
        # data["map"] (file/source/fallback), and that metadata must be present
        # when we serialize trip-data.json below so downstream consumers know
        # which map file exists and whether it is a fallback.
        map_file = generate_route_map(data, out_dir, key)
    if mode != "data-only":
        html_file = "index.html" if mode == "publish-demo" else "trip.html"
        html_path = out_dir / html_file
        generate_html(data, html_path, map_file)
        if pdf:
            pdf_file = "trip.pdf"
            try:
                if not generate_pdf(html_path, out_dir / pdf_file):
                    data["pdf_error"] = "PDF generation did not create trip.pdf."
                    pdf_file = None
            except Exception as exc:
                data["pdf_error"] = str(exc)
                pdf_file = None
    elif pdf:
        data["pdf_error"] = "Data-only mode skipped HTML, so PDF output was not generated."
    (out_dir / "trip-data.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = build_manifest(data, mode, out_dir, key, html_file, map_file, pdf_file)
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_outputs(
    data: dict[str, Any],
    out_dir: Path,
    key: str | None,
    mode: str = "auto",
    pdf: bool = False,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    working_data = deepcopy(data)
    with TemporaryDirectory(prefix=f".{out_dir.name}.staging-", dir=out_dir.parent) as staging_name:
        staging_dir = Path(staging_name)
        manifest = write_outputs_in_place(working_data, staging_dir, key, mode, pdf)
        publish_generated_files(staging_dir, out_dir)
    data.clear()
    data.update(working_data)
    return manifest


def write_and_verify_outputs(
    data: dict[str, Any],
    out_dir: Path,
    key: str | None,
    mode: str = "auto",
    pdf: bool = False,
) -> OutputRunResult:
    manifest = write_outputs(data, out_dir, key, mode, pdf=pdf)
    verification_errors = verify_output_dir(out_dir)
    gate_error = None
    if mode in KEY_REQUIRED_MODES and has_accuracy_failure(data):
        gate_error = f"{mode} mode failed: one or more legs did not use complete Amap data."
        verification_errors = [
            error for error in verification_errors
            if not error.startswith(f"{mode} mode requires complete Amap leg data:")
        ]
    return OutputRunResult(
        data=data,
        manifest=manifest,
        verification_errors=verification_errors,
        gate_error=gate_error,
    )


def generate_trip_output(
    input_text: str,
    out_dir: Path,
    *,
    mode: str,
    key: str | None,
    use_api: bool,
    title: str,
    start_date: str | None = None,
    pdf: bool = False,
    vehicle_type: str = "none",
    ev_kwh_price: float | None = None,
    ev_kwh_per_100km: float | None = None,
    hotel_nightly: float | None = None,
    hotel_nights: int | None = None,
    meal_daily: float | None = None,
    meal_days: int | None = None,
    attractions: list[dict[str, Any]] | None = None,
    misc_fees: list[dict[str, Any]] | None = None,
    adults: int | None = None,
    children_under_1_2m: int | None = None,
    children_over_1_2m: int | None = None,
) -> OutputRunResult:
    preflight_error = mode_key_error(mode, key)
    if preflight_error:
        return OutputRunResult(data={}, manifest={}, verification_errors=[], gate_error=preflight_error)

    data = build_trip_data(
        input_text,
        title=title,
        start_date=start_date,
        use_api=use_api,
        route_key=key,
        vehicle_type=vehicle_type,
        ev_kwh_price=ev_kwh_price,
        ev_kwh_per_100km=ev_kwh_per_100km,
        hotel_nightly=hotel_nightly,
        hotel_nights=hotel_nights,
        meal_daily=meal_daily,
        meal_days=meal_days,
        attractions=attractions,
        misc_fees=misc_fees,
        adults=adults,
        children_under_1_2m=children_under_1_2m,
        children_over_1_2m=children_over_1_2m,
    )
    return write_and_verify_outputs(data, out_dir, key, mode, pdf=pdf)

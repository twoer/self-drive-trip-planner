#!/usr/bin/env python3
"""Parse self-drive itinerary text and generate JSON, HTML, and a map-based route image."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Keep these helper imports at module scope so existing tests and agent callers
# can still access route_trip.build_budget(), route_trip.enrich(), etc.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import (
    BUDGET_CATEGORY_LABELS,
    CHINESE_NUMBER_VALUES,
    SCENIC_SPOT_ALIASES,
    attraction_fee_text_from_line,
    budget_category_label,
    budget_item,
    build_budget,
    clean_fee_name,
    compact_number_label,
    ensure_budget,
    missing_attraction_candidates,
    money_label,
    normalize_place_name,
    parse_attraction_fee_items,
    parse_budget_fee_items,
    parse_budget_text,
    parse_first_amount,
    parse_named_amount,
    parse_non_negative_float,
    parse_non_negative_int,
    parse_passenger_counts,
    parse_positive_float,
    parse_small_count,
    route_scenic_candidates,
    scenic_rule_for_name,
    split_budget_section,
    split_fee_fragments,
    total_passenger_count,
    trip_day_count,
    unit_money_label,
)
import leaflet_map
from html_renderer import (
    _round_to_step,
    day_date_label,
    distance_label,
    duration_label,
    escape,
    generate_html,
    ordered_stops,
    parse_start_date,
    trip_date_range,
)
from itinerary_parser import parse_itinerary
from manifest_contract import MODE_CHOICES, build_manifest, output_warnings, source_counts
from output_assets import (
    closest_distance,
    diagram_points,
    flatten_route_points,
    generate_pdf,
    generate_route_map,
    generate_svg,
    project_points,
)
from routing import (
    AmapRouteProvider,
    KNOWN_COORDS,
    RouteEnricher,
    EstimateRouteProvider,
    amap_key,
    build_route_provider,
    enrich,
    estimate_route,
    fetch_json,
    geocode,
    haversine_km,
    load_dotenv,
    parse_polyline,
    point_json,
    route_with_amap,
    summarize_day,
)
from output_reporter import emit_run_report
from trip_pipeline import (
    build_trip_data,
    default_output_dir,
    generate_trip_output,
    resolve_mode,
    write_and_verify_outputs,
    write_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate self-drive trip data, HTML, and a map-based route image.")
    parser.add_argument("input", help="Text file containing D1/D2 day blocks and A 到 B route lines.")
    parser.add_argument("--out", default=None, help="Output directory. Defaults to ./trip-output, or ./docs in publish-demo mode.")
    parser.add_argument("--title", default="自驾行程", help="Trip title used in generated outputs.")
    parser.add_argument("--start-date", default=None,
                        help="Departure date YYYY-MM-DD (e.g. 2026-07-17). When set, each day shows its calendar date and weekday.")
    parser.add_argument("--pdf", action="store_true", help="Also generate trip.pdf from the HTML output when Playwright is available.")
    parser.add_argument("--vehicle-type", choices=("none", "ev"), default="none", help="Vehicle type for budget calculation. Use ev for electric cars.")
    parser.add_argument("--ev-kwh-price", type=parse_non_negative_float, default=None, help="EV charging price in CNY per kWh, e.g. 1.5.")
    parser.add_argument("--ev-kwh-per-100km", type=parse_positive_float, default=None, help="EV consumption in kWh/100km. Defaults to 16 when EV price is provided.")
    parser.add_argument("--hotel-nightly", type=parse_non_negative_float, default=None, help="Hotel cost in CNY per night, e.g. 300.")
    parser.add_argument("--hotel-nights", type=parse_non_negative_int, default=None, help="Hotel nights. Defaults to trip days minus one.")
    parser.add_argument("--meal-daily", type=parse_non_negative_float, default=None, help="Meal cost in CNY per day, e.g. 100.")
    parser.add_argument("--meal-days", type=parse_non_negative_int, default=None, help="Meal days. Defaults to trip day count.")
    parser.add_argument("--attraction", action="append", type=parse_named_amount, default=[], help="Attraction fee item, repeatable. Format: NAME=AMOUNT, e.g. 小七孔=120.")
    parser.add_argument("--misc-fee", action="append", type=parse_named_amount, default=[], help="Other budget item, repeatable. Format: NAME=AMOUNT.")
    parser.add_argument("--adults", type=parse_non_negative_int, default=None, help="Adult count for attraction ticket calculation.")
    parser.add_argument("--children-under-1-2m", type=parse_non_negative_int, default=None, help="Children below 1.2m; attraction tickets are free by default.")
    parser.add_argument("--children-over-1-2m", type=parse_non_negative_int, default=None, help="Children at or above 1.2m; attraction tickets use half adult price by default.")
    parser.add_argument(
        "--mode",
        choices=MODE_CHOICES,
        default="auto",
        help="Generation mode: auto uses API when configured; estimate skips API; accurate/publish-demo require all legs from API; data-only skips HTML/map.",
    )
    parser.add_argument("--no-api", action="store_true", help="Legacy alias for --mode estimate.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    if args.no_api and args.mode != "auto":
        print("--no-api cannot be combined with --mode; use --mode estimate instead.", file=sys.stderr)
        return 2

    load_dotenv(Path(".env"))
    key = amap_key()
    mode, key, use_api = resolve_mode(args.mode, args.no_api, key)

    try:
        out_dir = default_output_dir(mode, args.out)
        result = generate_trip_output(
            input_path.read_text(encoding="utf-8"),
            out_dir,
            mode=mode,
            key=key,
            use_api=use_api,
            title=args.title,
            start_date=args.start_date,
            pdf=args.pdf,
            vehicle_type=args.vehicle_type,
            ev_kwh_price=args.ev_kwh_price,
            ev_kwh_per_100km=args.ev_kwh_per_100km,
            hotel_nightly=args.hotel_nightly,
            meal_daily=args.meal_daily,
            attractions=args.attraction,
            misc_fees=args.misc_fee,
            adults=args.adults,
            children_under_1_2m=args.children_under_1_2m,
            children_over_1_2m=args.children_over_1_2m,
            hotel_nights=args.hotel_nights,
            meal_days=args.meal_days,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return emit_run_report(result, out_dir, mode)


if __name__ == "__main__":
    raise SystemExit(main())

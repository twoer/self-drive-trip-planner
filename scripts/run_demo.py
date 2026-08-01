#!/usr/bin/env python3
"""Run the bundled demo with the best available mode."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from manifest_contract import DEMO_MODE_CHOICES
from output_reporter import emit_run_report
from routing import amap_key, load_dotenv
from trip_pipeline import generate_trip_output, resolve_mode


ROOT = Path(__file__).resolve().parents[1]


def read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def key_configured() -> bool:
    values = read_dotenv(ROOT / ".env")
    for key in ("AMAP_KEY", "GAODE_KEY"):
        value = os.getenv(key) or values.get(key)
        if value and "your-gaode" not in value:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the example trip with automatic mode selection.")
    parser.add_argument("--input", default="examples/simple-trip.txt", help="Demo itinerary input file.")
    parser.add_argument("--out", default="trip-output", help="Output directory.")
    parser.add_argument("--title", default="Demo 自驾游", help="Trip title.")
    parser.add_argument("--start-date", default="2026-07-17", help="Departure date YYYY-MM-DD.")
    parser.add_argument("--mode", choices=DEMO_MODE_CHOICES, default=None,
                        help="Override automatic mode selection.")
    args = parser.parse_args()

    requested_mode = args.mode or ("auto" if key_configured() else "estimate")
    input_path = ROOT / args.input
    if not input_path.exists():
        print(f"Input file not found: {input_path}")
        return 2

    load_dotenv(ROOT / ".env")
    mode, key, use_api = resolve_mode(requested_mode, False, amap_key())

    out_dir = ROOT / args.out
    try:
        result = generate_trip_output(
            input_path.read_text(encoding="utf-8"),
            out_dir,
            mode=mode,
            key=key,
            use_api=use_api,
            title=args.title,
            start_date=args.start_date,
        )
    except ValueError as exc:
        print(str(exc))
        return 2
    return emit_run_report(result, out_dir, mode, open_path=out_dir / "trip.html")


if __name__ == "__main__":
    raise SystemExit(main())

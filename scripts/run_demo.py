#!/usr/bin/env python3
"""Run the bundled demo with the best available mode."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


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
    parser.add_argument("--mode", choices=("auto", "estimate", "accurate"), default=None,
                        help="Override automatic mode selection.")
    args = parser.parse_args()

    mode = args.mode or ("auto" if key_configured() else "estimate")
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "route_trip.py"),
        str(ROOT / args.input),
        "--out",
        str(ROOT / args.out),
        "--title",
        args.title,
        "--start-date",
        args.start_date,
        "--mode",
        mode,
    ]
    print("Running:", " ".join(cmd), flush=True)
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode

    html_file = ROOT / args.out / "trip.html"
    print(f"Open: {html_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

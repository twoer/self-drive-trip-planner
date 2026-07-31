#!/usr/bin/env python3
"""Create or inspect local .env configuration for route generation."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"


def read_env(path: Path) -> dict[str, str]:
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


def has_real_key(values: dict[str, str]) -> bool:
    for key in ("AMAP_KEY", "GAODE_KEY"):
        value = values.get(key) or os.getenv(key)
        if value and "your-gaode" not in value:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up local .env for Gaode/Amap keys.")
    parser.add_argument("--key", default=None, help="Optional AMAP_KEY value to write into .env.")
    args = parser.parse_args()

    if not ENV_PATH.exists():
        if EXAMPLE_PATH.exists():
            ENV_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            ENV_PATH.write_text("# Do not commit real keys.\nAMAP_KEY=your-gaode-web-service-key\n", encoding="utf-8")
        print(f"Created: {ENV_PATH}")

    if args.key:
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
        wrote = False
        for index, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("AMAP_KEY="):
                lines[index] = f"AMAP_KEY={args.key}"
                wrote = True
                break
        if not wrote:
            lines.append(f"AMAP_KEY={args.key}")
        ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        print("Updated AMAP_KEY in .env")

    values = read_env(ENV_PATH)
    if has_real_key(values):
        print("Map key: configured")
        print("Demo mode: auto/accurate can use Amap route data")
    else:
        print("Map key: not configured")
        print(f"Edit {ENV_PATH} and replace AMAP_KEY=your-gaode-web-service-key")
        print("No-key demos still work with --mode estimate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

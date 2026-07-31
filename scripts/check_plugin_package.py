#!/usr/bin/env python3
"""Portable checks for the generated Codex plugin package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REQUIRED_SKILL_FILES = [
    "SKILL.md",
    "requirements.txt",
    "examples/simple-trip.txt",
    "references/output-contract.md",
    "scripts/route_trip.py",
    "scripts/leaflet_map.py",
]

FORBIDDEN_PARTS = {
    ".env",
    ".git",
    "__pycache__",
    "dist",
    "docs",
    "trip-output",
}


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check generated plugin package contents.")
    parser.add_argument("plugin", help="Path to generated plugin folder.")
    args = parser.parse_args()

    plugin_dir = Path(args.plugin)
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        fail(f"missing plugin manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("name") != "self-drive-trip-planner":
        fail("plugin name must be self-drive-trip-planner")
    if manifest.get("skills") != "./skills/":
        fail("plugin skills path must be ./skills/")

    interface = manifest.get("interface") or {}
    for key in ("privacyPolicyURL", "termsOfServiceURL", "websiteURL"):
        value = interface.get(key)
        if not isinstance(value, str) or not value.startswith("https://"):
            fail(f"interface.{key} must be an https URL")

    screenshots = interface.get("screenshots") or []
    if len(screenshots) < 2:
        fail("plugin must include at least two screenshots")
    for screenshot in screenshots:
        if not screenshot.endswith(".png"):
            fail(f"screenshot must be a PNG path: {screenshot}")
        path = plugin_dir / screenshot.replace("./", "", 1)
        if not path.is_file():
            fail(f"missing screenshot file: {path}")

    skill_dir = plugin_dir / "skills" / "self-drive-trip-planner"
    for rel_path in REQUIRED_SKILL_FILES:
        if not (skill_dir / rel_path).is_file():
            fail(f"missing required skill file: {rel_path}")

    for path in plugin_dir.rglob("*"):
        if any(part in FORBIDDEN_PARTS for part in path.relative_to(plugin_dir).parts):
            fail(f"forbidden generated/local path in package: {path}")

    print(f"Plugin package checks passed: {plugin_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

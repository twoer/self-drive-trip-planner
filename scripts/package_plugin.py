#!/usr/bin/env python3
"""Build a clean skills-only Codex plugin package for distribution."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "self-drive-trip-planner"


PLUGIN_JSON = {
    "name": PLUGIN_NAME,
    "version": "0.1.2",
    "description": "Generate agent-verifiable Chinese self-drive trip plans with route data, HTML, maps, and manifests.",
    "author": {
        "name": "twoer",
        "email": "zhangkun_net@hotmail.com",
        "url": "https://github.com/twoer",
    },
    "homepage": "https://twoer.github.io/self-drive-trip-planner/",
    "repository": "https://github.com/twoer/self-drive-trip-planner",
    "license": "MIT",
    "keywords": [
        "self-drive",
        "road-trip",
        "itinerary",
        "amap",
        "gaode",
        "travel",
        "china",
    ],
    "skills": "./skills/",
    "interface": {
        "displayName": "Self-Drive Trip Planner",
        "shortDescription": "Generate verifiable Chinese road-trip JSON, HTML, route maps, and manifests.",
        "longDescription": (
            "Self-Drive Trip Planner turns compact D1/D2 Chinese road-trip text into "
            "normalized JSON, a standalone mobile-friendly itinerary page, an interactive "
            "route map, optional PNG/SVG route images, and a machine-readable manifest. "
            "It can use Gaode/Amap route data when AMAP_KEY or GAODE_KEY is configured, "
            "or clearly marked estimates for no-key previews."
        ),
        "developerName": "twoer",
        "category": "Productivity",
        "capabilities": ["Write"],
        "websiteURL": "https://twoer.github.io/self-drive-trip-planner/",
        "privacyPolicyURL": "https://twoer.github.io/self-drive-trip-planner/privacy.html",
        "termsOfServiceURL": "https://twoer.github.io/self-drive-trip-planner/terms.html",
        "defaultPrompt": [
            "Use my D1/D2 road-trip text to generate JSON, HTML, map, and manifest.",
            "Create an accurate Amap-backed self-drive itinerary from this route.",
            "Generate a no-key estimated road-trip preview and report warnings.",
        ],
        "brandColor": "#2C6BB2",
        "screenshots": [
            "./assets/screenshot-desktop.png",
            "./assets/screenshot-mobile.png",
        ],
    },
}


SKILL_FILES = [
    "SKILL.md",
    "requirements.txt",
    ".env.example",
]


SKILL_DIRS = [
    "agents",
    "examples",
    "references",
    "scripts",
]


def copy_tree(src: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns(
        "__pycache__",
        "*.pyc",
        ".DS_Store",
        "package_plugin.py",
        "check_plugin_package.py",
        "install_plugin_local.py",
    )
    shutil.copytree(src, dst, ignore=ignore)


def build_plugin(out_dir: Path, zip_path: Path | None = None) -> tuple[Path, Path]:
    plugin_dir = out_dir / PLUGIN_NAME
    if plugin_dir.exists():
        shutil.rmtree(plugin_dir)

    skill_dir = plugin_dir / "skills" / PLUGIN_NAME
    (plugin_dir / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    skill_dir.mkdir(parents=True, exist_ok=True)

    (plugin_dir / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(PLUGIN_JSON, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    for rel_path in SKILL_FILES:
        src = ROOT / rel_path
        if src.exists():
            shutil.copy2(src, skill_dir / rel_path)

    for rel_path in SKILL_DIRS:
        src = ROOT / rel_path
        if src.exists():
            copy_tree(src, skill_dir / rel_path)

    assets_dir = ROOT / "assets"
    if assets_dir.exists():
        copy_tree(assets_dir, plugin_dir / "assets")

    for rel_path in ("README.md", "INSTALL.md"):
        src = ROOT / rel_path
        if src.exists():
            shutil.copy2(src, plugin_dir / rel_path)

    if zip_path is None:
        zip_path = out_dir / f"{PLUGIN_NAME}-plugin.zip"
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
        for path in sorted(plugin_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(out_dir))

    return plugin_dir, zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a clean Codex plugin package.")
    parser.add_argument("--out", default="dist", help="Output directory for plugin folder and zip.")
    parser.add_argument("--zip", default=None, help="Optional explicit zip path.")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = Path(args.zip) if args.zip else None
    plugin_dir, archive_path = build_plugin(out_dir, zip_path)
    print(f"Plugin folder: {plugin_dir.resolve()}")
    print(f"Plugin zip: {archive_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

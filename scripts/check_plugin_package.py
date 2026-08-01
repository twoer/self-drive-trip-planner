#!/usr/bin/env python3
"""Portable checks for the generated Codex plugin package."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_SKILL_FILES = [
    "SKILL.md",
    ".env.example",
    "requirements.txt",
    "agents/openai.yaml",
    "examples/simple-trip.txt",
    "references/architecture.md",
    "references/data-schema.md",
    "references/map-services.md",
    "references/output-contract.md",
    "references/ui-generation-baseline.md",
    "scripts/route_trip.py",
    "scripts/run_demo.py",
    "scripts/generate_demo_batch.py",
    "scripts/setup_env.py",
    "scripts/install_skill.py",
    "scripts/itinerary_parser.py",
    "scripts/trip_pipeline.py",
    "scripts/routing.py",
    "scripts/budget.py",
    "scripts/manifest_contract.py",
    "scripts/leaflet_map.py",
    "scripts/html_renderer.py",
    "scripts/output_assets.py",
    "scripts/output_reporter.py",
    "scripts/skill_layout.py",
    "scripts/verify_outputs.py",
]

REQUIRED_PLUGIN_FILES = [
    "README.md",
    "INSTALL.md",
]

FORBIDDEN_PARTS = {
    ".env",
    ".git",
    "__pycache__",
    "dist",
    "docs",
    "trip-output",
}

FORBIDDEN_FILENAMES = {
    "check_plugin_package.py",
    "check_installed_plugin.py",
    "install_plugin_local.py",
    "package_plugin.py",
}

SKILL_REFERENCE_RE = re.compile(r"((?:scripts|references|examples)/[A-Za-z0-9_./-]+(?:\.py|\.md|\.txt)?)")
MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_-]+):(?:\s|$)", re.MULTILINE)
DOCUMENTED_MAKE_RE = re.compile(r"\bmake\s+([A-Za-z0-9_-]+)")
DOCUMENTATION_FILES = [
    "README.md",
    "INSTALL.md",
    "SUBMISSION.md",
    "SKILL.md",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def referenced_skill_paths(skill_text: str) -> list[str]:
    paths = {match.rstrip(".,;:)`") for match in SKILL_REFERENCE_RE.findall(skill_text)}
    return sorted(path for path in paths if path)


def validate_skill_references(skill_dir: Path) -> list[str]:
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.is_file():
        return ["missing SKILL.md"]
    missing = []
    for rel_path in referenced_skill_paths(skill_path.read_text(encoding="utf-8")):
        if not (skill_dir / rel_path).is_file():
            missing.append(rel_path)
    return missing


def validate_python_scripts(skill_dir: Path) -> list[str]:
    errors = []
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return ["missing scripts directory"]
    for path in sorted(scripts_dir.glob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            errors.append(f"{path.relative_to(skill_dir)}: {exc}")
    return errors


def submission_version_info(path: Path) -> tuple[str | None, list[str]]:
    if not path.is_file():
        return None, []
    text = path.read_text(encoding="utf-8")
    version_match = re.search(r"^- Version:\s*`([^`]+)`", text, re.MULTILINE)
    release_versions = sorted(set(re.findall(r"/releases/download/v([^/]+)/", text)))
    return (version_match.group(1) if version_match else None), release_versions


def validate_submission_version(plugin_version: str, submission_path: Path) -> list[str]:
    version, release_versions = submission_version_info(submission_path)
    errors = []
    if version is None:
        errors.append("SUBMISSION.md is missing a Version field")
    elif version != plugin_version:
        errors.append(f"SUBMISSION.md version is {version}, expected {plugin_version}")
    for release_version in release_versions:
        if release_version != plugin_version:
            errors.append(f"SUBMISSION.md release URL uses {release_version}, expected {plugin_version}")
    return errors


def package_archive_path(plugin_dir: Path) -> Path:
    return plugin_dir.parent / f"{plugin_dir.name}-plugin.zip"


def folder_file_entries(plugin_dir: Path) -> set[str]:
    base = plugin_dir.parent
    return {path.relative_to(base).as_posix() for path in plugin_dir.rglob("*") if path.is_file()}


def archive_file_entries(archive_path: Path) -> tuple[set[str], list[str]]:
    errors = []
    try:
        with ZipFile(archive_path) as archive:
            names = [name for name in archive.namelist() if not name.endswith("/")]
    except (BadZipFile, OSError) as exc:
        return set(), [f"cannot read plugin archive: {exc}"]

    duplicate_names = sorted(name for name in set(names) if names.count(name) > 1)
    for name in duplicate_names:
        errors.append(f"duplicate archive entry: {name}")

    entries = set()
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"unsafe archive entry path: {name}")
            continue
        entries.add(path.as_posix())
    return entries, errors


def validate_archive_matches_folder(plugin_dir: Path) -> list[str]:
    archive_path = package_archive_path(plugin_dir)
    if not archive_path.is_file():
        return [f"missing plugin archive: {archive_path}"]

    folder_entries = folder_file_entries(plugin_dir)
    archive_entries, errors = archive_file_entries(archive_path)
    missing = sorted(folder_entries - archive_entries)
    extra = sorted(archive_entries - folder_entries)
    errors.extend(f"archive missing file: {name}" for name in missing)
    errors.extend(f"archive contains extra file: {name}" for name in extra)
    return errors


def make_targets(makefile_path: Path) -> set[str]:
    if not makefile_path.is_file():
        return set()
    return set(MAKE_TARGET_RE.findall(makefile_path.read_text(encoding="utf-8")))


def validate_documented_commands(root: Path) -> list[str]:
    targets = make_targets(root / "Makefile")
    errors = []
    for rel_path in DOCUMENTATION_FILES:
        path = root / rel_path
        if not path.is_file():
            errors.append(f"missing documentation file: {rel_path}")
            continue
        text = path.read_text(encoding="utf-8")
        for target in sorted(set(DOCUMENTED_MAKE_RE.findall(text))):
            if target not in targets:
                errors.append(f"{rel_path} references missing make target: {target}")
        for script_path in referenced_skill_paths(text):
            if script_path.startswith("scripts/") and not (root / script_path).is_file():
                errors.append(f"{rel_path} references missing script: {script_path}")
    return errors


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
    plugin_version = manifest.get("version")
    if not isinstance(plugin_version, str) or not plugin_version:
        fail("plugin version must be a non-empty string")
    if manifest.get("skills") != "./skills/":
        fail("plugin skills path must be ./skills/")

    for error in validate_submission_version(plugin_version, ROOT / "SUBMISSION.md"):
        fail(error)
    for error in validate_documented_commands(ROOT):
        fail(error)

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

    for rel_path in REQUIRED_PLUGIN_FILES:
        if not (plugin_dir / rel_path).is_file():
            fail(f"missing required plugin file: {rel_path}")

    skill_dir = plugin_dir / "skills" / "self-drive-trip-planner"
    for rel_path in REQUIRED_SKILL_FILES:
        if not (skill_dir / rel_path).is_file():
            fail(f"missing required skill file: {rel_path}")

    for rel_path in validate_skill_references(skill_dir):
        fail(f"SKILL.md references missing file: {rel_path}")

    for error in validate_python_scripts(skill_dir):
        fail(f"packaged Python script failed to compile: {error}")

    for path in plugin_dir.rglob("*"):
        parts = path.relative_to(plugin_dir).parts
        if any(part in FORBIDDEN_PARTS for part in parts):
            fail(f"forbidden generated/local path in package: {path}")
        if path.name in FORBIDDEN_FILENAMES:
            fail(f"forbidden repository helper in package: {path}")

    for error in validate_archive_matches_folder(plugin_dir):
        fail(error)

    print(f"Plugin package checks passed: {plugin_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

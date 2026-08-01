#!/usr/bin/env python3
"""Verify that the local plugin install and Codex cache match the packaged plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from package_plugin import PLUGIN_JSON, PLUGIN_NAME


DEFAULT_INSTALLED_PLUGIN = Path(f"~/plugins/{PLUGIN_NAME}")
DEFAULT_MARKETPLACE = Path("~/.agents/plugins/marketplace.json")
DEFAULT_CACHE_ROOT = Path("~/.codex/plugins/cache")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def plugin_manifest(plugin_dir: Path) -> dict[str, Any]:
    return read_json(plugin_dir / ".codex-plugin" / "plugin.json")


def plugin_version(plugin_dir: Path) -> str | None:
    manifest_path = plugin_dir / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        return None
    version = plugin_manifest(plugin_dir).get("version")
    return version if isinstance(version, str) else None


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entries(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
    }


def compare_trees(expected: Path, actual: Path, label: str) -> list[str]:
    errors = []
    expected_files = file_entries(expected)
    actual_files = file_entries(actual)
    for rel_path in sorted(expected_files.keys() - actual_files.keys()):
        errors.append(f"{label} missing file: {rel_path}")
    for rel_path in sorted(actual_files.keys() - expected_files.keys()):
        errors.append(f"{label} contains extra file: {rel_path}")
    for rel_path in sorted(expected_files.keys() & actual_files.keys()):
        if file_digest(expected_files[rel_path]) != file_digest(actual_files[rel_path]):
            errors.append(f"{label} differs from expected file: {rel_path}")
    return errors


def marketplace_entry(marketplace_path: Path) -> tuple[str | None, dict[str, Any] | None]:
    if not marketplace_path.is_file():
        return None, None
    data = read_json(marketplace_path)
    marketplace_name = data.get("name")
    plugins = data.get("plugins") or []
    for plugin in plugins:
        if plugin.get("name") == PLUGIN_NAME:
            return marketplace_name if isinstance(marketplace_name, str) else None, plugin
    return marketplace_name if isinstance(marketplace_name, str) else None, None


def cache_plugin_dir(cache_root: Path, marketplace_name: str, version: str) -> Path:
    return cache_root / marketplace_name / PLUGIN_NAME / version


def codex_plugin_list() -> tuple[dict[str, Any] | None, str | None]:
    if shutil.which("codex") is None:
        return None, "Codex CLI not found"
    try:
        result = subprocess.run(
            ["codex", "plugin", "list", "--json"],
            check=True,
            text=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or str(exc)).strip()
        return None, f"codex plugin list failed: {message}"
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError as exc:
        return None, f"codex plugin list returned invalid JSON: {exc}"


def validate_codex_plugin_state(state: dict[str, Any], marketplace_name: str, version: str, installed_plugin: Path) -> list[str]:
    installed = state.get("installed")
    if not isinstance(installed, list):
        return ["codex plugin list JSON is missing installed plugins"]
    plugin_id = f"{PLUGIN_NAME}@{marketplace_name}"
    exact_matches = [plugin for plugin in installed if plugin.get("pluginId") == plugin_id]
    name_matches = [plugin for plugin in installed if plugin.get("name") == PLUGIN_NAME]
    if not exact_matches and not name_matches:
        return [f"Codex installed plugin is missing: {plugin_id}"]

    errors = []
    plugin = (exact_matches or name_matches)[0]
    if plugin.get("pluginId") != plugin_id:
        errors.append(f"Codex plugin id is {plugin.get('pluginId')}, expected {plugin_id}")
    if plugin.get("marketplaceName") != marketplace_name:
        errors.append(f"Codex marketplace is {plugin.get('marketplaceName')}, expected {marketplace_name}")
    if plugin.get("version") != version:
        errors.append(f"Codex installed plugin version is {plugin.get('version')}, expected {version}")
    if plugin.get("installed") is not True:
        errors.append("Codex plugin is not marked installed")
    if plugin.get("enabled") is not True:
        errors.append("Codex plugin is not enabled")
    source = plugin.get("source") or {}
    source_path = source.get("path")
    if source_path and Path(source_path).expanduser().resolve() != installed_plugin.resolve():
        errors.append(f"Codex source path is {source_path}, expected {installed_plugin.resolve()}")
    return errors


def validate_installed_plugin(
    installed_plugin: Path,
    marketplace_path: Path,
    cache_root: Path,
    *,
    expected_plugin: Path | None = None,
    require_cache: bool = False,
    require_codex_list: bool = False,
) -> list[str]:
    errors = []
    installed_plugin = installed_plugin.expanduser()
    marketplace_path = marketplace_path.expanduser()
    cache_root = cache_root.expanduser()
    expected_plugin = expected_plugin.expanduser() if expected_plugin else None

    if not installed_plugin.is_dir():
        return [f"installed plugin folder is missing: {installed_plugin}"]

    version = plugin_version(installed_plugin)
    expected_version = plugin_version(expected_plugin) if expected_plugin else PLUGIN_JSON["version"]
    if version != expected_version:
        errors.append(f"installed plugin version is {version}, expected {expected_version}")

    skill_path = installed_plugin / "skills" / PLUGIN_NAME / "SKILL.md"
    if not skill_path.is_file():
        errors.append(f"installed skill is missing: {skill_path}")

    if expected_plugin:
        if not expected_plugin.is_dir():
            errors.append(f"expected plugin folder is missing: {expected_plugin}")
        else:
            errors.extend(compare_trees(expected_plugin, installed_plugin, "installed plugin"))

    marketplace_name, entry = marketplace_entry(marketplace_path)
    if not marketplace_name:
        errors.append(f"marketplace name is missing: {marketplace_path}")
    if entry is None:
        errors.append(f"marketplace entry is missing for {PLUGIN_NAME}: {marketplace_path}")
    else:
        source = entry.get("source") or {}
        if source.get("source") != "local":
            errors.append("marketplace entry must use a local source")
        expected_source_path = f"./plugins/{PLUGIN_NAME}"
        if source.get("path") != expected_source_path:
            errors.append(f"marketplace source path is {source.get('path')}, expected {expected_source_path}")

    if marketplace_name and version:
        cache_dir = cache_plugin_dir(cache_root, marketplace_name, version)
        if cache_dir.is_dir():
            errors.extend(compare_trees(installed_plugin, cache_dir, "Codex cache"))
        elif require_cache:
            errors.append(f"Codex cache is missing current plugin version: {cache_dir}")

        if require_codex_list:
            state, error = codex_plugin_list()
            if error:
                errors.append(error)
            elif state is not None:
                errors.extend(validate_codex_plugin_state(state, marketplace_name, version, installed_plugin))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify installed self-drive-trip-planner plugin files and Codex cache.")
    parser.add_argument("--installed-plugin", default=str(DEFAULT_INSTALLED_PLUGIN), help="Installed local plugin folder.")
    parser.add_argument("--marketplace", default=str(DEFAULT_MARKETPLACE), help="Personal marketplace JSON path.")
    parser.add_argument("--cache-root", default=str(DEFAULT_CACHE_ROOT), help="Codex plugin cache root.")
    parser.add_argument("--expected-plugin", default=None, help="Expected packaged plugin folder to compare against.")
    parser.add_argument("--require-cache", action="store_true", help="Fail when the current plugin version is missing from the Codex cache.")
    parser.add_argument("--require-codex-list", action="store_true", help="Fail unless `codex plugin list --json` reports the current plugin installed and enabled.")
    args = parser.parse_args()

    errors = validate_installed_plugin(
        Path(args.installed_plugin),
        Path(args.marketplace),
        Path(args.cache_root),
        expected_plugin=Path(args.expected_plugin) if args.expected_plugin else None,
        require_cache=args.require_cache,
        require_codex_list=args.require_codex_list,
    )
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Installed plugin checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

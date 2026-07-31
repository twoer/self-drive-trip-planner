#!/usr/bin/env python3
"""Install this repository as a local Codex plugin via the personal marketplace."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

from package_plugin import PLUGIN_NAME, build_plugin


DEFAULT_MARKETPLACE = Path("~/.agents/plugins/marketplace.json")
DEFAULT_PLUGIN_PARENT = Path("~/plugins")


def load_json(path: Path) -> dict:
    if not path.exists():
        return {
            "name": "personal",
            "interface": {"displayName": "Personal"},
            "plugins": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def upsert_marketplace_entry(marketplace_path: Path) -> str:
    marketplace_path = marketplace_path.expanduser()
    data = load_json(marketplace_path)
    marketplace_name = data.setdefault("name", "personal")
    interface = data.setdefault("interface", {})
    interface.setdefault("displayName", marketplace_name.title())

    plugins = data.setdefault("plugins", [])
    entry = {
        "name": PLUGIN_NAME,
        "source": {
            "source": "local",
            "path": f"./plugins/{PLUGIN_NAME}",
        },
        "policy": {
            "installation": "AVAILABLE",
            "authentication": "ON_INSTALL",
        },
        "category": "Productivity",
    }

    for index, plugin in enumerate(plugins):
        if plugin.get("name") == PLUGIN_NAME:
            plugins[index] = entry
            break
    else:
        plugins.append(entry)

    marketplace_path.parent.mkdir(parents=True, exist_ok=True)
    marketplace_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(marketplace_name)


def install_plugin(plugin_parent: Path, build_dir: Path) -> Path:
    plugin_parent = plugin_parent.expanduser()
    build_dir = build_dir.expanduser()
    source_plugin, _archive_path = build_plugin(build_dir)
    target = plugin_parent / PLUGIN_NAME

    resolved_source = source_plugin.resolve()
    resolved_target = target.resolve()
    if resolved_target == resolved_source or resolved_source in resolved_target.parents:
        raise RuntimeError(f"Refusing to install into build output path: {target}")

    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_plugin, target)
    return target


def run_codex_add(plugin_ref: str, skip: bool) -> None:
    if skip:
        print(f"Skipped Codex install. Add later with: codex plugin add {plugin_ref}")
        return

    if shutil.which("codex") is None:
        print(f"Codex CLI not found. Marketplace entry is ready; add later with: codex plugin add {plugin_ref}")
        return

    subprocess.run(["codex", "plugin", "add", plugin_ref, "--json"], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install self-drive-trip-planner as a local Codex plugin.")
    parser.add_argument("--marketplace", default=str(DEFAULT_MARKETPLACE), help="Personal marketplace JSON path.")
    parser.add_argument("--plugin-parent", default=str(DEFAULT_PLUGIN_PARENT), help="Directory that stores local plugins.")
    parser.add_argument("--build-dir", default="dist/local-plugin-install", help="Temporary build output directory.")
    parser.add_argument("--skip-codex-add", action="store_true", help="Update files only; do not call codex plugin add.")
    args = parser.parse_args()

    marketplace_path = Path(args.marketplace)
    plugin_parent = Path(args.plugin_parent)
    build_dir = Path(args.build_dir)

    target = install_plugin(plugin_parent, build_dir)
    marketplace_name = upsert_marketplace_entry(marketplace_path)
    plugin_ref = f"{PLUGIN_NAME}@{marketplace_name}"
    run_codex_add(plugin_ref, args.skip_codex_add)

    print(f"Installed plugin folder: {target.expanduser().resolve()}")
    print(f"Marketplace file: {marketplace_path.expanduser().resolve()}")
    print(f"Plugin reference: {plugin_ref}")
    print("Start a new Codex task after installing so the skill list refreshes.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: command failed with exit code {exc.returncode}: {' '.join(exc.cmd)}", file=sys.stderr)
        raise SystemExit(exc.returncode)

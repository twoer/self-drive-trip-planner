#!/usr/bin/env python3
"""Install this repository as a clean local Codex skill."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "self-drive-trip-planner"

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


def install_skill(dest_root: Path, overwrite: bool = True) -> Path:
    target = dest_root.expanduser() / SKILL_NAME
    resolved_target = target.resolve()
    resolved_root = ROOT.resolve()
    if resolved_target == resolved_root or resolved_root in resolved_target.parents:
        raise RuntimeError(f"Refusing to install into repository path: {target}")

    if target.exists():
        if not overwrite:
            raise RuntimeError(f"Skill already exists: {target}")
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    for rel_path in SKILL_FILES:
        src = ROOT / rel_path
        if src.exists():
            shutil.copy2(src, target / rel_path)

    for rel_path in SKILL_DIRS:
        src = ROOT / rel_path
        if src.exists():
            copy_tree(src, target / rel_path)

    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Install self-drive-trip-planner into a Codex skills directory.")
    parser.add_argument("--dest", default="~/.codex/skills", help="Codex skills directory.")
    parser.add_argument("--no-overwrite", action="store_true", help="Fail if the target skill already exists.")
    args = parser.parse_args()

    target = install_skill(Path(args.dest), overwrite=not args.no_overwrite)
    print(f"Installed skill: {target.expanduser().resolve()}")
    print("Use it in Codex with: $self-drive-trip-planner")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

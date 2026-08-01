#!/usr/bin/env python3
"""Install this repository as a clean local Codex skill."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_layout import copy_skill_contents


ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "self-drive-trip-planner"


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

    copy_skill_contents(ROOT, target)

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

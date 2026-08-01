"""Shared file layout helpers for installing and packaging the skill."""

from __future__ import annotations

import shutil
from pathlib import Path


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

SKILL_COPY_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    ".DS_Store",
    "package_plugin.py",
    "check_plugin_package.py",
    "check_installed_plugin.py",
    "install_plugin_local.py",
)


def copy_tree(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, ignore=SKILL_COPY_IGNORE)


def copy_skill_contents(root: Path, target: Path) -> None:
    for rel_path in SKILL_FILES:
        src = root / rel_path
        if src.exists():
            shutil.copy2(src, target / rel_path)

    for rel_path in SKILL_DIRS:
        src = root / rel_path
        if src.exists():
            copy_tree(src, target / rel_path)

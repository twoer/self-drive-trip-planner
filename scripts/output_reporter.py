#!/usr/bin/env python3
"""Shared console reporting for trip output runs."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

sys.path.insert(0, str(Path(__file__).resolve().parent))
from trip_pipeline import OutputRunResult


def source_summary(manifest: dict) -> str:
    return ", ".join(f"{source}={count}" for source, count in sorted((manifest.get("source_counts") or {}).items()))


def emit_run_report(
    result: OutputRunResult,
    out_dir: Path,
    mode: str,
    *,
    open_path: Path | None = None,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    manifest = result.manifest
    if result.gate_error and not manifest:
        print(result.gate_error, file=err)
        return result.returncode

    print(f"Wrote: {out_dir.resolve()}", file=out)
    print("Mode:", mode, file=out)
    if manifest:
        print("Sources:", source_summary(manifest), file=out)
        if manifest.get("warnings"):
            print("Warnings:", " | ".join(manifest["warnings"]), file=out)

    if result.verification_errors:
        print("Output verification failed:", file=err)
        for error in result.verification_errors:
            print(f"- {error}", file=err)
        return result.returncode

    print("Verified: output contract", file=out)
    if result.gate_error:
        print(result.gate_error, file=err)
        return result.returncode
    if open_path:
        print(f"Open: {open_path}", file=out)
    return 0

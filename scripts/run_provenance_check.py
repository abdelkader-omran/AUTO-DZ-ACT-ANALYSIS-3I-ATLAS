#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Validation CLI — TRIZEL Provenance Gate Runner

Callable independently to validate provenance for one or more observation
directories before any temporal or epistemic execution.

The gate is deterministic: identical inputs always produce identical outcomes.

Usage
-----
    python scripts/run_provenance_check.py \\
        --observation-root data/observations/2026-03-21

    python scripts/run_provenance_check.py \\
        --observation-root data/observations/2026-03-21 \\
        --observation-root data/observations/2026-03-22

Exit codes
----------
    0  — ALL observations are VALID (gate passed)
    1  — At least one observation is INVALID (gate failed — full abort)
    2  — Bad arguments or unresolvable observation root path

Constraints
-----------
*   No interpretation
*   No fallback behavior
*   No auto-correction
*   No modification of data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from validation.provenance_validator import abort_if_invalid, validate_observations


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="run_provenance_check",
        description=(
            "TRIZEL Provenance Gate — validate observation provenance "
            "before any analysis execution."
        ),
    )
    ap.add_argument(
        "--observation-root",
        dest="observation_roots",
        required=True,
        action="append",
        metavar="DIR",
        help=(
            "Path to a per-date observation directory containing "
            "normalized_observation.json. May be repeated for batch validation."
        ),
    )
    return ap


def main() -> None:
    """Entry point for the provenance gate CLI."""
    ap = _build_parser()
    args = ap.parse_args()

    # Resolve and validate each supplied path before running the gate.
    resolved: list[str] = []
    for raw in args.observation_roots:
        path = Path(raw).resolve()
        if not path.is_dir():
            print(
                f"ERROR: --observation-root not found or not a directory: {path}",
                file=sys.stderr,
            )
            sys.exit(2)
        resolved.append(str(path))

    report = validate_observations(resolved)

    # Emit the machine-readable report to stdout.
    print(json.dumps(report, indent=2))

    # Enforce the gate: exits non-zero if any observation is INVALID.
    abort_if_invalid(report)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Temporal Analysis — Provenance-Valid Contiguous Window

Executes deterministic temporal analysis over a provenance-valid contiguous
window of observation days.

The script:
  - validates provenance for every day in the window (HARD GATE)
  - runs the epistemic engine on each day
  - compares epistemic states and orbital parameters across consecutive days
  - writes a deterministic temporal analysis record to analysis/temporal/

Constraints
-----------
*  No public/ updates
*  No releases or Zenodo operations
*  No synthetic continuity
*  No carry-forward
*  No interpretative or theoretical claims
*  Source must be AUTO-DZ-ACT-3I-ATLAS-DAILY only
*  Window is fixed; no extension permitted

Usage
-----
    python scripts/temporal_analysis.py \\
        --window 2026-03-15 2026-03-16 2026-03-17 \\
        --observation-dir data/observations \\
        --output-dir analysis/temporal

Exit codes
----------
    0  — temporal analysis completed successfully
    1  — provenance gate failed (ABORT)
    2  — bad arguments or missing input files
    3  — window is not contiguous
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scripts.epistemic_engine import run_for_date
from validation.provenance_validator import abort_if_invalid, validate_observations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEMPORAL_ANALYSIS_VERSION = "1.0.0"
_REQUIRED_PROVENANCE_ROOT = "AUTO-DZ-ACT-3I-ATLAS-DAILY"

# Repository root — the parent directory of this script's package directory.
# Used to normalize absolute paths in the output record to repo-relative paths.
_REPO_ROOT: Path = Path(__file__).resolve().parent.parent

TRIZEL_METADATA: Dict[str, Any] = {
    "project": "TRIZEL",
    "kernel_version": "V1",
    "kernel_status": "frozen",
    "artifact_type": "temporal_analysis",
    "generated_by": "scripts/temporal_analysis.py",
    "repository": "AUTO-DZ-ACT-ANALYSIS-3I-ATLAS",
    "governance_layer": "analysis",
    "citation_required": True,
    "license_reference": "SEE LICENSE IF PRESENT",
    "notice_reference": "SEE NOTICE",
}

# Orbital parameters compared across days
_ORBITAL_PARAMS = ("e", "a", "i", "q")


# ---------------------------------------------------------------------------
# Path normalization
# ---------------------------------------------------------------------------

def _to_repo_relative(path_str: str, repo_root: Path = _REPO_ROOT) -> str:
    """Return a repository-relative path string for *path_str*.

    If *path_str* is an absolute path that can be expressed as a relative path
    from *repo_root*, the relative form is returned (using forward slashes for
    portability).  Otherwise *path_str* is returned unchanged.

    Args:
        path_str: An absolute or relative path string.
        repo_root: The repository root directory; defaults to ``_REPO_ROOT``.

    Returns:
        A repository-relative POSIX path string, or the original string if
        relativisation is not possible.
    """
    try:
        relative = Path(path_str).relative_to(repo_root)
        return relative.as_posix()
    except ValueError:
        return path_str


def _normalize_provenance_observations(
    observations: List[Dict[str, Any]],
    repo_root: Path = _REPO_ROOT,
) -> List[Dict[str, Any]]:
    """Return a copy of *observations* with ``path`` values made repo-relative.

    Each element is a shallow copy; only the ``path`` field is replaced.

    Args:
        observations: List of observation dicts as returned by
            ``validate_observations``.
        repo_root: Repository root used to relativise paths.

    Returns:
        New list of observation dicts with portable relative paths.
    """
    result: List[Dict[str, Any]] = []
    for obs in observations:
        entry = dict(obs)
        if "path" in entry:
            entry["path"] = _to_repo_relative(str(entry["path"]), repo_root)
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# Window validation
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> Optional[dt.date]:
    """Parse a YYYY-MM-DD string into a date object."""
    try:
        return dt.date.fromisoformat(date_str)
    except ValueError:
        return None


def validate_contiguous_window(dates: List[str]) -> Optional[str]:
    """Validate that the supplied date strings form a contiguous window.

    Args:
        dates: List of YYYY-MM-DD strings, expected in ascending order.

    Returns:
        ``None`` on success, or an error message string on failure.
    """
    if not dates:
        return "window is empty"

    parsed: List[dt.date] = []
    for d in dates:
        parsed_date = _parse_date(d)
        if parsed_date is None:
            return f"invalid date format: {d!r}"
        parsed.append(parsed_date)

    for i in range(1, len(parsed)):
        gap = (parsed[i] - parsed[i - 1]).days
        if gap != 1:
            return (
                f"window is not contiguous: gap of {gap} day(s) between "
                f"{parsed[i-1]} and {parsed[i]}"
            )

    return None


# ---------------------------------------------------------------------------
# Temporal comparison
# ---------------------------------------------------------------------------

def _extract_orbital_params(
    epistemic_record: Dict[str, Any],
) -> Optional[Dict[str, Optional[float]]]:
    """Extract orbital parameters from an epistemic record.

    Returns a dict mapping parameter name to float/None, or None if no
    parameters are present.
    """
    parameters = epistemic_record.get("parameters", {})
    if not parameters:
        return None

    for _src, src_params in parameters.items():
        if isinstance(src_params, dict):
            return {
                k: (float(v) if v is not None else None)
                for k, v in src_params.items()
                if k in _ORBITAL_PARAMS
            }

    return None


def _compare_consecutive_days(
    date_a: str,
    record_a: Dict[str, Any],
    date_b: str,
    record_b: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare epistemic records for two consecutive days.

    Performs exact equality comparison only; no tolerance, no inference.

    Args:
        date_a: Earlier date string (YYYY-MM-DD).
        record_a: Epistemic record for date_a.
        date_b: Later date string (YYYY-MM-DD).
        record_b: Epistemic record for date_b.

    Returns:
        Dict describing the comparison result.
    """
    params_a = _extract_orbital_params(record_a)
    params_b = _extract_orbital_params(record_b)

    if params_a is None or params_b is None:
        consistency = "insufficient_data"
        changed_params: List[str] = []
    else:
        changed_params = [
            p for p in _ORBITAL_PARAMS
            if params_a.get(p) != params_b.get(p)
        ]
        consistency = "evolved" if changed_params else "stable"

    return {
        "from_date": date_a,
        "to_date": date_b,
        "from_epistemic_state": record_a.get("epistemic_state"),
        "to_epistemic_state": record_b.get("epistemic_state"),
        "orbital_consistency": consistency,
        "changed_parameters": changed_params,
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def _validate_provenance(
    window: List[str],
    observation_dir: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """Validate provenance for all days in the window.

    Returns:
        Tuple of (obs_dirs, provenance_report) on success, or raises SystemExit.
    """
    obs_dirs: List[str] = []
    for date_str in window:
        obs_path = observation_dir / date_str
        if not obs_path.is_dir():
            print(
                f"ERROR: observation directory not found: {obs_path}",
                file=sys.stderr,
            )
            sys.exit(2)
        obs_dirs.append(str(obs_path))

    print("Running provenance validation (HARD GATE)...")
    report = validate_observations(obs_dirs)
    return obs_dirs, report


def _run_epistemic_engine(
    window: List[str],
    observation_dir: Path,
) -> Dict[str, Dict[str, Any]]:
    """Run the epistemic engine for each day and return records keyed by date."""
    print("Running epistemic engine for each day...")
    records: Dict[str, Dict[str, Any]] = {}
    for date_str in window:
        record = run_for_date(observation_dir / date_str)
        records[date_str] = record
        print(
            f"  {date_str}: epistemic_state={record.get('epistemic_state')!r}  "
            f"temporal_consistency={record.get('temporal_consistency')!r}"
        )
    return records


def _build_comparisons(
    window: List[str],
    epistemic_records: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build temporal comparisons for consecutive day pairs."""
    comparisons: List[Dict[str, Any]] = []
    for i in range(1, len(window)):
        comparison = _compare_consecutive_days(
            window[i - 1],
            epistemic_records[window[i - 1]],
            window[i],
            epistemic_records[window[i]],
        )
        comparisons.append(comparison)
        print(
            f"  {comparison['from_date']} → {comparison['to_date']}: "
            f"orbital_consistency={comparison['orbital_consistency']!r}  "
            f"changed_params={comparison['changed_parameters']}"
        )
    return comparisons


def run_temporal_analysis(
    window: List[str],
    observation_dir: Path,
    output_dir: Path,
) -> int:
    """Execute temporal analysis over the provenance-valid contiguous window.

    Steps:
      1. Validate window contiguity (hard check).
      2. Validate provenance for each day (HARD GATE — abort on any failure).
      3. Run epistemic engine for each day.
      4. Compare consecutive day pairs.
      5. Write deterministic temporal analysis record.

    Args:
        window: Ordered list of YYYY-MM-DD date strings.
        observation_dir: Base directory containing per-date observation dirs.
        output_dir: Directory where the analysis record will be written.

    Returns:
        0 on success, non-zero on failure.
    """
    # Step 1 — Validate window contiguity
    err = validate_contiguous_window(window)
    if err:
        print(f"ERROR [contiguity]: {err}", file=sys.stderr)
        return 3

    print(f"OK: contiguous window confirmed: {window[0]} → {window[-1]}")

    # Step 2 — Provenance validation (HARD GATE)
    _obs_dirs, provenance_report = _validate_provenance(window, observation_dir)
    if provenance_report.get("batch_outcome", "INVALID") != "VALID":
        print(
            "ERROR [provenance gate]: at least one observation failed provenance "
            "validation — ABORT",
            file=sys.stderr,
        )
        print(json.dumps(provenance_report, indent=2), file=sys.stderr)
        abort_if_invalid(provenance_report)
        return 1

    print("OK: provenance passes for all days in window.")

    # Step 3 — Run epistemic engine for each day
    epistemic_records = _run_epistemic_engine(window, observation_dir)
    print("OK: epistemic engine completed for all days.")

    # Step 4 — Temporal comparison across consecutive pairs
    comparisons = _build_comparisons(window, epistemic_records)

    # Step 5 — Write deterministic output record
    output_path = output_dir / f"{window[0]}--{window[-1]}" / "temporal_analysis.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    analysis_record: Dict[str, Any] = {
        "trizel_metadata": TRIZEL_METADATA,
        "temporal_analysis_version": _TEMPORAL_ANALYSIS_VERSION,
        "window": {
            "start": window[0],
            "end": window[-1],
            "days": window,
            "length": len(window),
        },
        "provenance_gate": {
            "outcome": "VALID",
            "source_required": _REQUIRED_PROVENANCE_ROOT,
            "observations": _normalize_provenance_observations(
                provenance_report.get("observations", [])
            ),
        },
        "epistemic_states": {
            date_str: {
                "epistemic_state": epistemic_records[date_str].get("epistemic_state"),
                "temporal_consistency": epistemic_records[date_str].get(
                    "temporal_consistency"
                ),
                "confidence": epistemic_records[date_str].get("confidence"),
                "sources": epistemic_records[date_str].get("sources", []),
            }
            for date_str in window
        },
        "temporal_comparisons": comparisons,
        "execution_outcome": "SUCCESS",
    }

    output_path.write_text(
        json.dumps(analysis_record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"OK: temporal analysis record written to {output_path}")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="temporal_analysis",
        description=(
            "TRIZEL Temporal Analysis — execute deterministic temporal analysis "
            "over a provenance-valid contiguous observation window."
        ),
    )
    ap.add_argument(
        "--window",
        dest="window",
        required=True,
        nargs="+",
        metavar="YYYY-MM-DD",
        help="Ordered list of dates forming the contiguous window.",
    )
    ap.add_argument(
        "--observation-dir",
        dest="observation_dir",
        default="data/observations",
        metavar="DIR",
        help=(
            "Base directory containing per-date observation subdirectories "
            "(default: data/observations)."
        ),
    )
    ap.add_argument(
        "--output-dir",
        dest="output_dir",
        default="analysis/temporal",
        metavar="DIR",
        help=(
            "Directory where the temporal analysis record will be written "
            "(default: analysis/temporal)."
        ),
    )
    return ap


def main() -> int:
    """CLI entry point."""
    ap = _build_parser()
    args = ap.parse_args()

    observation_dir = Path(args.observation_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    return run_temporal_analysis(
        window=args.window,
        observation_dir=observation_dir,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    sys.exit(main())

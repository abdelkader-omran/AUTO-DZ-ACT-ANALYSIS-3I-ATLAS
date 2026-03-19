#!/usr/bin/env python3
"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Pipeline — Reprocessing with Archive Traceability

Provides deterministic reprocessing of any window of raw snapshots from the
AUTO-DZ-ACT-3I-ATLAS-DAILY source repository, and records a complete
provenance run-metadata record so that every pipeline run can be exactly
reproduced.

Provenance record written to:
    provenance/runs/<run_id>.json

Run-metadata model:
    {
      "run_id":               "<ISO-8601 timestamp>",
      "object_key":           "atlas-2025-n1",
      "registry_version":     "v1.0",
      "source_repository":    "AUTO-DZ-ACT-3I-ATLAS-DAILY",
      "source_snapshot_root": "data/snapshots",
      "source_snapshots":     ["YYYY-MM-DD", ...],
      "pipeline_commit":      "<git-sha>",
      "pipeline_version":     "1.0.0",
      "generated_utc":        "<ISO-8601 timestamp>"
    }

Usage (CLI):
    python -m pipeline.reprocessing \\
        --raw-dir /path/to/AUTO-DZ-ACT-3I-ATLAS-DAILY/data/snapshots \\
        --snapshots 2026-03-15 2026-03-16 2026-03-17 \\
        --public-dir public \\
        [--run-id 2026-03-22T10:00:00Z]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from pipeline.build_observations import (
    OBJECT_KEY,
    PIPELINE_VERSION,
    _REGISTRY,
    _now_utc_iso,
    process_dates,
    write_latest_file,
    write_summary_file,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Matches a YYYY-MM-DD date string
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Matches an ISO-8601 run_id timestamp (e.g. 2026-03-22T10:00:00Z)
_RUN_ID_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

# Timeout (seconds) for the git subprocess used to resolve the pipeline commit
_GIT_COMMAND_TIMEOUT_SECONDS = 10


# ---------------------------------------------------------------------------
# Run-ID and commit helpers
# ---------------------------------------------------------------------------

def build_run_id() -> str:
    """Return a deterministic run_id based on the current UTC time.

    Format: ``YYYY-MM-DDTHH:MM:SSZ``

    Returns:
        ISO-8601 UTC timestamp string.
    """
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_pipeline_commit(repo_root: Path = _REPO_ROOT) -> str:
    """Return the current HEAD git commit SHA of the pipeline repository.

    Falls back to ``"unknown"`` when git is not available or the directory is
    not a git repository.

    Args:
        repo_root: Path to the repository root (defaults to the module root).

    Returns:
        40-character hex SHA string, or ``"unknown"`` on failure.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_GIT_COMMAND_TIMEOUT_SECONDS,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return "unknown"


# ---------------------------------------------------------------------------
# Provenance writer
# ---------------------------------------------------------------------------

def write_run_metadata(
    run_metadata: Dict[str, Any],
    provenance_dir: Path,
) -> Path:
    """Write the run-metadata record to ``provenance/runs/<run_id>.json``.

    Creates the ``provenance/runs/`` directory if it does not already exist.

    Args:
        run_metadata: Dict conforming to the run-metadata model.
        provenance_dir: Path to the repository's ``provenance/`` directory.

    Returns:
        Path to the written JSON file.
    """
    runs_dir = provenance_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    run_id = run_metadata["run_id"]
    # Replace colons with hyphens so the run_id is safe to use as a filename
    filename_safe_run_id = run_id.replace(":", "-")
    out_path = runs_dir / f"{filename_safe_run_id}.json"

    out_path.write_text(
        json.dumps(run_metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# Core reprocessing entry point
# ---------------------------------------------------------------------------

def reprocess(
    raw_dir: Path,
    source_snapshots: List[str],
    public_dir: Path,
    provenance_dir: Path = _REPO_ROOT / "provenance",
    run_id: Optional[str] = None,
    source_repository: str = "AUTO-DZ-ACT-3I-ATLAS-DAILY",
    source_snapshot_root: str = "data/snapshots",
) -> Dict[str, Any]:
    """Run the pipeline over a specific set of snapshots and record provenance.

    This function is the deterministic-rerun entry point.  It:

    1. Resolves the pipeline git commit.
    2. Calls :func:`~pipeline.build_observations.process_dates` for the
       requested snapshots.
    3. Writes ``public/latest.json`` and ``public/summary.json``.
    4. Writes a provenance run-metadata record to
       ``provenance/runs/<run_id>.json``.

    Args:
        raw_dir: Path to the raw snapshot root
                 (``AUTO-DZ-ACT-3I-ATLAS-DAILY/data/snapshots``).
        source_snapshots: Ordered list of YYYY-MM-DD snapshot dates to process.
        public_dir: Output directory for publishable JSON files.
        provenance_dir: Repository ``provenance/`` directory.
        run_id: Explicit run identifier (``YYYY-MM-DDTHH:MM:SSZ``).
                Auto-generated from the current UTC time if omitted.
        source_repository: Canonical name of the source daily repository.
        source_snapshot_root: Relative path to snapshot data within the source
                               repository (used for traceability only).

    Returns:
        The run-metadata dict that was written to disk.

    Raises:
        ValueError: If any snapshot date is not in YYYY-MM-DD format.
    """
    for date_str in source_snapshots:
        if not _DATE_RE.match(date_str):
            raise ValueError(
                f"Invalid snapshot date (expected YYYY-MM-DD): {date_str!r}"
            )

    if run_id is None:
        run_id = build_run_id()
    else:
        if not _RUN_ID_RE.match(run_id):
            raise ValueError(
                f"Invalid run_id (expected YYYY-MM-DDTHH:MM:SSZ): {run_id!r}"
            )

    generated_utc = _now_utc_iso()
    pipeline_commit = resolve_pipeline_commit(_REPO_ROOT)

    # Run the observation pipeline
    all_day_summaries = process_dates(
        source_snapshots, raw_dir, public_dir, generated_utc
    )

    # Write latest.json / summary.json
    if all_day_summaries:
        latest = all_day_summaries[-1]
        latest_day = latest["date"]
        latest_obs_path = public_dir / "observations" / f"{latest_day}.json"
        try:
            latest_observations = json.loads(
                latest_obs_path.read_text(encoding="utf-8")
            )["observations"]
        except (OSError, json.JSONDecodeError, KeyError):
            latest_observations = []
        write_latest_file(public_dir, generated_utc, latest_observations, latest_day)

    write_summary_file(all_day_summaries, public_dir, generated_utc)

    # Build and write run-metadata
    run_metadata: Dict[str, Any] = {
        "run_id": run_id,
        "object_key": OBJECT_KEY,
        "registry_version": _REGISTRY.get("registry_version", ""),
        "source_repository": source_repository,
        "source_snapshot_root": source_snapshot_root,
        "source_snapshots": list(source_snapshots),
        "pipeline_commit": pipeline_commit,
        "pipeline_version": PIPELINE_VERSION,
        "generated_utc": generated_utc,
    }

    metadata_path = write_run_metadata(run_metadata, provenance_dir)
    print(f"provenance run metadata -> {metadata_path}")

    return run_metadata


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point for the reprocessing pipeline."""
    ap = argparse.ArgumentParser(
        description=(
            "Reprocess a deterministic window of raw snapshots from "
            "AUTO-DZ-ACT-3I-ATLAS-DAILY and record a provenance run-metadata "
            "record for archive traceability."
        )
    )
    ap.add_argument(
        "--raw-dir",
        required=True,
        help=(
            "Path to the raw snapshot root of AUTO-DZ-ACT-3I-ATLAS-DAILY "
            "(e.g. /path/to/AUTO-DZ-ACT-3I-ATLAS-DAILY/data/snapshots). "
            "The directory must contain YYYY-MM-DD sub-directories."
        ),
    )
    ap.add_argument(
        "--snapshots",
        nargs="+",
        required=True,
        metavar="YYYY-MM-DD",
        help=(
            "One or more snapshot dates to (re-)process (space-separated, "
            "YYYY-MM-DD format). Processed in the order given."
        ),
    )
    ap.add_argument(
        "--public-dir",
        default="public",
        help="Output directory for publishable JSON files (default: public/).",
    )
    ap.add_argument(
        "--provenance-dir",
        default=None,
        help=(
            "Directory where provenance/runs/ metadata is written "
            "(default: <repo_root>/provenance)."
        ),
    )
    ap.add_argument(
        "--run-id",
        default=None,
        help=(
            "Explicit run identifier in YYYY-MM-DDTHH:MM:SSZ format. "
            "Auto-generated from current UTC time if omitted."
        ),
    )
    ap.add_argument(
        "--source-repository",
        default="AUTO-DZ-ACT-3I-ATLAS-DAILY",
        help="Canonical name of the source daily repository (for traceability).",
    )
    ap.add_argument(
        "--source-snapshot-root",
        default="data/snapshots",
        help="Relative path to snapshot data within the source repository.",
    )
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir).resolve()
    public_dir = Path(args.public_dir).resolve()
    provenance_dir = (
        Path(args.provenance_dir).resolve()
        if args.provenance_dir
        else _REPO_ROOT / "provenance"
    )

    if not raw_dir.is_dir():
        print(
            f"ERROR: --raw-dir not found or not a directory: {raw_dir}",
            file=sys.stderr,
        )
        return 2

    try:
        run_metadata = reprocess(
            raw_dir=raw_dir,
            source_snapshots=args.snapshots,
            public_dir=public_dir,
            provenance_dir=provenance_dir,
            run_id=args.run_id,
            source_repository=args.source_repository,
            source_snapshot_root=args.source_snapshot_root,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"run_id:          {run_metadata['run_id']}")
    print(f"pipeline_commit: {run_metadata['pipeline_commit']}")
    print(f"snapshots:       {run_metadata['source_snapshots']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

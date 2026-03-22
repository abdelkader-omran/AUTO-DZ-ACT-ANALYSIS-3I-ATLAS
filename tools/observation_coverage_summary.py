#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRIZEL Scientific Ingest Layer — Observation Coverage Summary Utility

Repo:
  AUTO-DZ-ACT-ANALYSIS-3I-ATLAS

Scans all dated directories under data/observations/, reads each
normalized_observation.json file, and produces a deterministic structured
summary of:

  - observation coverage (total_days, first_day, last_day, contiguous, missing_days)
  - metadata field presence per day
  - provenance field presence per day
  - date continuity

This utility is descriptive only.  It does not validate, enforce, mutate,
or gate execution.

Output is written to stdout as a JSON object.

Usage:
  python tools/observation_coverage_summary.py
  python tools/observation_coverage_summary.py --observations-dir data/observations
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from _obs_cli import _load_json, parse_observations_dir


def _per_day_entry(date_str: str, obs_file: Optional[Path]) -> Dict[str, Any]:
    """Return a per-day summary entry for the given date."""
    entry: Dict[str, Any] = {
        "date": date_str,
        "file_present": obs_file is not None and obs_file.is_file(),
    }

    if not entry["file_present"]:
        for field in (
            "object_present",
            "source_present",
            "retrieved_utc_present",
            "identity_present",
            "orbital_present",
            "physical_present",
            "provenance_present",
            "snapshot_id_present",
            "sha256_present",
            "manifest_ref_present",
            "doi_present",
            "doi_absent_present",
        ):
            entry[field] = False
        return entry

    obs: Dict[str, Any] = _load_json(obs_file)  # type: ignore[arg-type]
    provenance = obs.get("provenance") or {}

    entry["object_present"] = "object" in obs
    entry["source_present"] = "source" in obs
    entry["retrieved_utc_present"] = "retrieved_utc" in obs
    entry["identity_present"] = "identity" in obs
    entry["orbital_present"] = "orbital" in obs
    entry["physical_present"] = "physical" in obs
    entry["provenance_present"] = "provenance" in obs
    entry["snapshot_id_present"] = "snapshot_id" in provenance
    entry["sha256_present"] = "sha256" in provenance
    entry["manifest_ref_present"] = "manifest_ref" in provenance
    entry["doi_present"] = "doi" in provenance
    entry["doi_absent_present"] = "doi_absent" in provenance

    return entry


def _find_missing_days(
    first_day: str, last_day: str, per_day: List[Dict[str, Any]]
) -> List[str]:
    """Return ISO date strings absent from *per_day* between first and last day."""
    present_dates = {d["date"] for d in per_day}
    missing: List[str] = []
    cursor = date.fromisoformat(first_day)
    end = date.fromisoformat(last_day)
    while cursor <= end:
        if cursor.isoformat() not in present_dates:
            missing.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return missing


def build_summary(observations_dir: Path) -> Dict[str, Any]:
    """Return a deterministic structured coverage summary."""
    per_day: List[Dict[str, Any]] = []

    if observations_dir.is_dir():
        for entry in sorted(observations_dir.iterdir()):
            if not entry.is_dir():
                continue
            # Accept only valid YYYY-MM-DD directory names
            try:
                date.fromisoformat(entry.name)
            except ValueError:
                continue
            obs_file = entry / "normalized_observation.json"
            per_day.append(_per_day_entry(entry.name, obs_file))

    # --- Top-level aggregates ---
    total_days = len(per_day)
    first_day: Optional[str] = per_day[0]["date"] if per_day else None
    last_day: Optional[str] = per_day[-1]["date"] if per_day else None

    # Date continuity
    missing_days: List[str] = []
    if first_day and last_day:
        missing_days = _find_missing_days(first_day, last_day, per_day)

    contiguous: bool = len(missing_days) == 0

    # Per-field coverage counts (count of days where the field is present)
    metadata_field_coverage: Dict[str, int] = {
        f: sum(1 for d in per_day if d.get(f)) for f in _COVERAGE_FIELDS
    }
    provenance_field_coverage: Dict[str, int] = {
        f: sum(1 for d in per_day if d.get(f)) for f in _PROVENANCE_FIELDS
    }

    return {
        "total_days": total_days,
        "first_day": first_day,
        "last_day": last_day,
        "contiguous": contiguous,
        "missing_days": missing_days,
        "observation_count": sum(1 for d in per_day if d["file_present"]),
        "provenance_field_coverage": provenance_field_coverage,
        "metadata_field_coverage": metadata_field_coverage,
        "days": per_day,
    }


def main(argv: List[str]) -> int:
    """Parse arguments, build the summary, and print it as JSON to stdout."""
    observations_dir = parse_observations_dir(
        argv,
        "Produce a deterministic coverage summary of normalized observation files.",
    )
    summary = build_summary(observations_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

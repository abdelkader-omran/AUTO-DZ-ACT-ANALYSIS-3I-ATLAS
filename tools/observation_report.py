#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRIZEL Scientific Ingest Layer — Observation Metadata Report Utility

Repo:
  AUTO-DZ-ACT-ANALYSIS-3I-ATLAS

For each dated directory under data/observations/, reads the
normalized_observation.json file and extracts provenance metadata:
  - provenance.snapshot_id
  - provenance.sha256
  - provenance.manifest_ref

Output is written to stdout as a JSON array.

Usage:
  python tools/observation_report.py
  python tools/observation_report.py --observations-dir data/observations
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from observation_utils import iter_observations, parse_observations_dir


def _extract_entry(date: str, obs: Dict[str, Any]) -> Dict[str, Optional[str]]:
    provenance = obs.get("provenance") or {}
    return {
        "date": date,
        "snapshot_id": provenance.get("snapshot_id"),
        "sha256": provenance.get("sha256"),
        "manifest_ref": provenance.get("manifest_ref"),
    }


def build_report(observations_dir: Path) -> List[Dict[str, Optional[str]]]:
    """Return a list of provenance metadata entries, one per dated observation directory."""
    return [_extract_entry(date, obs) for date, obs in iter_observations(observations_dir)]


def main(argv: List[str]) -> int:
    """Parse arguments, build the report, and print it as JSON to stdout."""
    observations_dir = parse_observations_dir(
        argv,
        "Report provenance metadata from normalized observation files.",
    )
    report = build_report(observations_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

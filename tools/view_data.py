#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRIZEL Scientific Ingest Layer — Observation Data Viewer

Repo:
  AUTO-DZ-ACT-ANALYSIS-3I-ATLAS

Reads and displays each normalized_observation.json found under
data/observations/, one entry per dated directory.

This utility is read-only and descriptive.  It does not validate,
enforce, mutate, or gate execution.

Output is written to stdout as a JSON array, with one entry per
observation day.

Usage:
  python tools/view_data.py
  python tools/view_data.py --observations-dir data/observations
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from observation_utils import iter_observations, parse_observations_dir


def load_observations(observations_dir: Path) -> List[Dict[str, Any]]:
    """Return all normalized observations found under *observations_dir*."""
    return [
        {"date": date, "observation": obs}
        for date, obs in iter_observations(observations_dir)
    ]


def main(argv: List[str]) -> int:
    """Parse arguments, load observations, and print them as JSON to stdout."""
    observations_dir = parse_observations_dir(
        argv,
        "Display normalized observation files from the observations directory.",
    )
    observations = load_observations(observations_dir)
    print(json.dumps(observations, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

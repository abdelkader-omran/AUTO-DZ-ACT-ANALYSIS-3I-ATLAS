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

from observation_utils import parse_observations_dir


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_observations(observations_dir: Path) -> List[Dict[str, Any]]:
    """Return all normalized observations found under *observations_dir*."""
    result: List[Dict[str, Any]] = []

    if not observations_dir.is_dir():
        return result

    for entry in sorted(observations_dir.iterdir()):
        if not entry.is_dir():
            continue
        obs_file = entry / "normalized_observation.json"
        if not obs_file.is_file():
            continue
        obs = _load_json(obs_file)
        result.append({"date": entry.name, "observation": obs})

    return result


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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRIZEL Scientific Ingest Layer — Shared observation-tool utilities

Provides the common path constants, CLI argument parsing, and observation
iteration used by observation_coverage_summary.py, observation_report.py,
and view_data.py so that those modules do not repeat the same code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Generator, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBSERVATIONS_DIR = REPO_ROOT / "data" / "observations"


def parse_observations_dir(argv: List[str], description: str) -> Path:
    """Parse --observations-dir from *argv* and return the resolved Path."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--observations-dir",
        default=str(DEFAULT_OBSERVATIONS_DIR),
        help="Path to observations directory (default: data/observations)",
    )
    args = parser.parse_args(argv[1:])
    return Path(args.observations_dir)


def iter_observations(
    observations_dir: Path,
) -> Generator[Tuple[str, Any], None, None]:
    """Yield ``(date_str, obs_data)`` for every valid observation directory.

    Iterates *observations_dir* in sorted order, skipping non-directory
    entries and directories that lack ``normalized_observation.json``.
    """
    if not observations_dir.is_dir():
        return
    for entry in sorted(observations_dir.iterdir()):
        if not entry.is_dir():
            continue
        obs_file = entry / "normalized_observation.json"
        if not obs_file.is_file():
            continue
        obs: Any = json.loads(obs_file.read_text(encoding="utf-8"))
        yield entry.name, obs

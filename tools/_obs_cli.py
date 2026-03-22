# -*- coding: utf-8 -*-

"""
Shared CLI helpers for observation tool scripts.

Provides common constants and the parse_observations_dir() helper used by
observation_coverage_summary.py and observation_report.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, List

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OBSERVATIONS_DIR = REPO_ROOT / "data" / "observations"


def _load_json(path: Path) -> Any:
    """Load a JSON file and return the parsed content."""
    return json.loads(path.read_text(encoding="utf-8"))


def parse_observations_dir(argv: List[str], description: str) -> Path:
    """Parse --observations-dir from *argv* and return a resolved Path."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--observations-dir",
        default=str(DEFAULT_OBSERVATIONS_DIR),
        help="Path to observations directory (default: data/observations)",
    )
    args = parser.parse_args(argv[1:])
    return Path(args.observations_dir)

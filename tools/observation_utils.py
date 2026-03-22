#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRIZEL Scientific Ingest Layer — Shared observation-tool utilities

Provides the common path constants and CLI argument parsing used by
observation_coverage_summary.py and observation_report.py so that
those modules do not repeat the same code.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

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

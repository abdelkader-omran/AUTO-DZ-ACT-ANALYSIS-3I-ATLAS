# scripts package
"""Shared CLI utilities for the scripts layer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Tuple


def add_observation_root_arg(
    ap: argparse.ArgumentParser,
    help_detail: str,
) -> None:
    """Register ``--observation-root`` with *ap*.

    Args:
        ap: ArgumentParser to which the argument is added.
        help_detail: Tool-specific suffix appended to the shared help prefix.
    """
    ap.add_argument(
        "--observation-root",
        required=True,
        help="Path to the per-date observation directory " + help_detail,
    )


def parse_and_resolve_observation_root(
    ap: argparse.ArgumentParser,
) -> Tuple[Optional[Path], int]:
    """Parse ``--observation-root`` from *ap* and validate it as a directory.

    Returns:
        ``(path, 0)`` on success, or ``(None, 2)`` after printing an error
        message to *stderr*.
    """
    args = ap.parse_args()
    path = Path(args.observation_root).resolve()
    if not path.is_dir():
        print(
            f"ERROR: --observation-root not found or not a directory: {path}",
            file=sys.stderr,
        )
        return None, 2
    return path, 0

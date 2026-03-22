# scripts package
"""Shared CLI utilities for the scripts layer."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ---------------------------------------------------------------------------
# TRIZEL kernel metadata
# ---------------------------------------------------------------------------

# Fields shared by every artifact produced in this analysis layer.
_TRIZEL_KERNEL_BASE: Dict[str, Any] = {
    "project": "TRIZEL",
    "kernel_version": "V1",
    "kernel_status": "frozen",
    "repository": "AUTO-DZ-ACT-ANALYSIS-3I-ATLAS",
    "governance_layer": "analysis",
    "citation_required": True,
    "license_reference": "SEE LICENSE IF PRESENT",
    "notice_reference": "SEE NOTICE",
}


def build_trizel_metadata(artifact_type: str, generated_by: str) -> Dict[str, Any]:
    """Return a canonical TRIZEL metadata block for the given artifact.

    Args:
        artifact_type: Short identifier for the artifact kind
                       (e.g. ``"inconsistency_report"``).
        generated_by:  Repo-relative path of the script that produces the
                       artifact (e.g. ``"scripts/detect_inconsistencies.py"``).

    Returns:
        A new dict containing all shared TRIZEL kernel fields plus the two
        artifact-specific fields.
    """
    return {
        **_TRIZEL_KERNEL_BASE,
        "artifact_type": artifact_type,
        "generated_by": generated_by,
    }


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

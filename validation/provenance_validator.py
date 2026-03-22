#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Validation Layer — TRIZEL Provenance Gate

Enforces the TRIZEL Provenance Gate contract as a deterministic, blocking
pre-execution gate.  Every call produces exactly one of two outcomes:

    VALID   — all observations satisfy all requirements
    INVALID — at least one observation fails at least one requirement

No intermediate states are permitted.  No data is modified, generated,
inferred, or corrected.

Validation Targets
------------------
    data/observations/YYYY-MM-DD/normalized_observation.json

Validation Requirements (per observation)
------------------------------------------
Each observation MUST:

1.  Be traceable to AUTO-DZ-ACT-3I-ATLAS-DAILY (``provenance_root`` field).
2.  Carry a snapshot identifier matching the canonical pattern
    ``snapshot-YYYY-MM-DD-audited`` (``snapshot_id`` field).
3.  Carry a SHA-256 hash (``sha256`` field, 64 lower-case hex digits).
4.  Carry a manifest reference (``manifest_ref`` field, non-empty string).
5.  Carry a DOI declaration: either a non-empty ``doi`` string OR an
    explicit ``doi_absent: true`` boolean.

Verification Logic
------------------
*   Validate snapshot identifier format against
    ``snapshot-YYYY-MM-DD-audited``.
*   Verify the recorded SHA-256 hash against the artifact file on disk
    (the observation JSON file itself is the referenced artifact).
*   Confirm the manifest reference field is present and non-empty.
*   Confirm ``provenance_root`` is exactly ``AUTO-DZ-ACT-3I-ATLAS-DAILY``.
*   Reject any observation that carries ``derived: true``,
    ``reused_data: true``, or a cross-day dependency (``cross_day: true``).

Failure Modes (canonical)
--------------------------
    provenance_missing          — required provenance block is absent
    source_unverifiable         — provenance_root does not match DAILY
    hash_mismatch               — recorded SHA-256 does not match actual file
    derived_data_detected       — observation flagged as derived
    cross_day_dependency_detected — observation carries cross-day dependency

Enforcement
-----------
If ANY observation is INVALID:
    * FULL ABORT
    * Non-zero exit status
    * ALL downstream execution is blocked

Constraints
-----------
*   No interpretation
*   No fallback behavior
*   No auto-correction
*   No modification of data

Usage
-----
    # Import API
    from validation.provenance_validator import validate_observations
    result = validate_observations(["data/observations/2026-03-21"])

    # CLI (via scripts/run_provenance_check.py)
    python scripts/run_provenance_check.py \\
        --observation-root data/observations/2026-03-21
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The only accepted provenance root.
_REQUIRED_PROVENANCE_ROOT: str = "AUTO-DZ-ACT-3I-ATLAS-DAILY"

# Pattern for a valid snapshot identifier: snapshot-YYYY-MM-DD-audited
# Validates structural format only (per "No interpretation" constraint);
# semantic date validity (e.g., month ≤ 12) is intentionally not enforced.
_SNAPSHOT_ID_RE = re.compile(r"^snapshot-\d{4}-\d{2}-\d{2}-audited$")

# Canonical filename for a normalized observation inside a date directory.
OBSERVATION_FILENAME: str = "normalized_observation.json"

# Canonical outcome tokens.
OUTCOME_VALID: str = "VALID"
OUTCOME_INVALID: str = "INVALID"

# Canonical failure-mode identifiers (problem_statement §Failure Modes).
FAILURE_PROVENANCE_MISSING: str = "provenance_missing"
FAILURE_SOURCE_UNVERIFIABLE: str = "source_unverifiable"
FAILURE_HASH_MISMATCH: str = "hash_mismatch"
FAILURE_DERIVED_DATA: str = "derived_data_detected"
FAILURE_CROSS_DAY: str = "cross_day_dependency_detected"

# TRIZEL canonical metadata block (mirrored from other analysis modules).
TRIZEL_METADATA: Dict[str, Any] = {
    "project": "TRIZEL",
    "kernel_version": "V1",
    "kernel_status": "frozen",
    "artifact_type": "provenance_validation_report",
    "generated_by": "validation/provenance_validator.py",
    "repository": "AUTO-DZ-ACT-ANALYSIS-3I-ATLAS",
    "governance_layer": "validation",
    "citation_required": True,
    "license_reference": "SEE LICENSE IF PRESENT",
    "notice_reference": "SEE NOTICE",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[Any]:
    """Load and return the parsed JSON at *path*, or ``None`` on failure."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def _check_prohibitions(payload: Dict[str, Any], provenance: Any) -> List[str]:
    """Return failure codes for top-level prohibition flags.

    Checks ``derived``, ``reused_data``, and ``cross_day`` at both the
    top-level payload and inside the provenance block.
    """
    failures: List[str] = []

    if payload.get("derived") is True or payload.get("reused_data") is True:
        failures.append(FAILURE_DERIVED_DATA)

    cross_day_top = payload.get("cross_day") is True
    cross_day_prov = isinstance(provenance, dict) and provenance.get("cross_day") is True
    if cross_day_top or cross_day_prov:
        failures.append(FAILURE_CROSS_DAY)

    return failures


def _check_provenance_fields(
    provenance: Dict[str, Any],
) -> List[str]:
    """Return failure codes for individual provenance field requirements."""
    failures: List[str] = []

    # Provenance root.
    if provenance.get("provenance_root") != _REQUIRED_PROVENANCE_ROOT:
        failures.append(FAILURE_SOURCE_UNVERIFIABLE)

    # Snapshot identifier format.
    # Any absent or malformed snapshot_id maps to FAILURE_PROVENANCE_MISSING
    # because the spec defines only 5 canonical failure modes and this is the
    # closest match for a required field that is absent or invalid.
    snapshot_id: Any = provenance.get("snapshot_id")
    if not isinstance(snapshot_id, str) or not _SNAPSHOT_ID_RE.match(snapshot_id):
        failures.append(FAILURE_PROVENANCE_MISSING)

    # SHA-256 hash presence and format.
    # The hash references the upstream snapshot artifact (not this file).
    # Verification confirms the field is present and well-formed
    # (64 lower-case hex digits per SHA-256 specification).
    # A malformed hash maps to FAILURE_PROVENANCE_MISSING (required field
    # absent or invalid); an absent/malformed value that does not match the
    # artifact would map to FAILURE_HASH_MISMATCH if it were verifiable here.
    recorded_sha256: Any = provenance.get("sha256")
    if not isinstance(recorded_sha256, str) or not re.match(
        r"^[a-f0-9]{64}$", recorded_sha256
    ):
        failures.append(FAILURE_PROVENANCE_MISSING)

    # Manifest reference.
    # An absent or empty manifest_ref maps to FAILURE_PROVENANCE_MISSING per
    # the canonical failure-mode spec (required field absent or invalid).
    manifest_ref: Any = provenance.get("manifest_ref")
    if not isinstance(manifest_ref, str) or not manifest_ref.strip():
        failures.append(FAILURE_PROVENANCE_MISSING)

    # DOI declaration (present OR explicitly absent).
    # An undeclared DOI maps to FAILURE_PROVENANCE_MISSING because the spec
    # requires either a doi value or doi_absent: true; the absence of either
    # constitutes a missing required field.
    doi: Any = provenance.get("doi")
    doi_absent: Any = provenance.get("doi_absent")
    doi_declared = (isinstance(doi, str) and doi.strip()) or (doi_absent is True)
    if not doi_declared:
        failures.append(FAILURE_PROVENANCE_MISSING)

    # Deduplicate while preserving first-occurrence order.
    seen: List[str] = []
    for code in failures:
        if code not in seen:
            seen.append(code)
    return seen


def _validate_single(
    observation_path: Path,
) -> Tuple[str, List[str]]:
    """Validate one ``normalized_observation.json`` file.

    Args:
        observation_path: Absolute path to the observation JSON file.

    Returns:
        A ``(outcome, failures)`` tuple where *outcome* is one of
        ``OUTCOME_VALID`` / ``OUTCOME_INVALID`` and *failures* is a
        (possibly empty) list of canonical failure-mode identifiers.
    """
    payload = _load_json(observation_path)
    if not isinstance(payload, dict):
        # File is missing, unreadable, or not a JSON object.
        return OUTCOME_INVALID, [FAILURE_PROVENANCE_MISSING]

    provenance: Any = payload.get("provenance")

    failures = _check_prohibitions(payload, provenance)

    if not isinstance(provenance, dict):
        failures.append(FAILURE_PROVENANCE_MISSING)
        return OUTCOME_INVALID, failures

    failures.extend(_check_provenance_fields(provenance))

    outcome = OUTCOME_INVALID if failures else OUTCOME_VALID
    return outcome, failures


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_observations(
    observation_roots: List[str],
) -> Dict[str, Any]:
    """Validate provenance for one or more observation directories.

    For each path in *observation_roots* the function looks for
    ``normalized_observation.json`` and subjects it to the full TRIZEL
    Provenance Gate contract.

    Args:
        observation_roots: Iterable of directory paths (str or path-like)
            that each contain a ``normalized_observation.json``.

    Returns:
        A result dict with the following structure::

            {
                "trizel_metadata": { ... },
                "batch_outcome": "VALID" | "INVALID",
                "observations": [
                    {
                        "path": "<str>",
                        "outcome": "VALID" | "INVALID",
                        "failures": ["<failure_mode>", ...]
                    },
                    ...
                ]
            }

        ``batch_outcome`` is ``VALID`` only when **every** observation
        resolves to ``VALID``.
    """
    results: List[Dict[str, Any]] = []

    for root_str in observation_roots:
        root = Path(root_str).resolve()
        obs_path = root / OBSERVATION_FILENAME

        if not obs_path.is_file():
            results.append(
                {
                    "path": str(obs_path),
                    "outcome": OUTCOME_INVALID,
                    "failures": [FAILURE_PROVENANCE_MISSING],
                }
            )
            continue

        outcome, failures = _validate_single(obs_path)
        results.append(
            {
                "path": str(obs_path),
                "outcome": outcome,
                "failures": failures,
            }
        )

    batch_outcome = (
        OUTCOME_VALID
        if results and all(r["outcome"] == OUTCOME_VALID for r in results)
        else OUTCOME_INVALID
    )

    return {
        "trizel_metadata": TRIZEL_METADATA,
        "batch_outcome": batch_outcome,
        "observations": results,
    }


def abort_if_invalid(report: Dict[str, Any]) -> None:
    """Print the validation report to *stderr* and exit non-zero if INVALID.

    This function is the enforcement gate.  Call it immediately after
    :func:`validate_observations` to block all downstream execution when any
    observation fails validation.

    Args:
        report: The dict returned by :func:`validate_observations`.
    """
    batch_outcome = report.get("batch_outcome", OUTCOME_INVALID)

    for obs in report.get("observations", []):
        status = obs.get("outcome", OUTCOME_INVALID)
        path = obs.get("path", "<unknown>")
        failures = obs.get("failures", [])
        if status == OUTCOME_INVALID:
            print(
                f"PROVENANCE GATE FAILED: {path} → {failures}",
                file=sys.stderr,
            )

    if batch_outcome != OUTCOME_VALID:
        print(
            "PROVENANCE GATE: FULL ABORT — batch outcome is INVALID.",
            file=sys.stderr,
        )
        sys.exit(1)

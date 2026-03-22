#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Analysis Layer — Deterministic Inconsistency Detection Tool

Reads data from a per-date observation root directory and produces a
canonical data artifact recording all observable inconsistencies between
sources.

Inconsistency types are defined canonically in docs/COMPARISON_SEMANTICS.md:

  §3.1  existence_mismatch    — object present in one source but absent in another
  §3.2  parameter_mismatch    — same parameter reported with differing values
  §3.3  availability_mismatch — conflicting availability states across sources
  §3.4  temporal_inconsistency — one source has data; another explicitly reports
                                  data not yet available or not published

Constraints (COMPARISON_SEMANTICS.md §4):

  1. No interpretation — inconsistencies are recorded as observed differences only.
  2. No source prioritization — all sources are treated as peers.
  3. No correctness determination — the tool does not decide which source is correct.
  4. Pure detection only.

Each inconsistency entry carries:
  - type:              one of the four canonical type identifiers above
  - involved_sources:  sorted list of every source contributing to the entry
  - observed_states:   dict mapping each involved source to its observed state
                       (used for §3.1, §3.3, §3.4)
  - observed_values:   dict mapping each involved source to its reported value
                       (used for §3.2 parameter_mismatch)
  - parameter:         name of the differing parameter (§3.2 only)

The top-level ``source_inputs`` block embeds all input data read during
detection, providing full traceability to raw_sources.json, normalized
parameter files, and ingestion-status files without requiring the caller to
re-read those files.

Input files (per observation root, docs/data_structure.md §3):
  raw_sources.json             — source availability states  (§3.1, §3.3, §3.4)
  normalized_observation.json  — JPL SBDB orbital parameters (§3.1, §3.2)
  mpc_normalized.json          — MPC orbital parameters      (§3.2, when present)
  mpc_object_ingest.json       — MPC ingestion status        (§3.4)

Output: <observation_root>/inconsistencies.json

Usage:
  python scripts/detect_inconsistencies.py --observation-root data/observations/YYYY-MM-DD

Integration (run_for_date pattern):
  from scripts.detect_inconsistencies import run_for_date
  run_for_date(observation_root)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from scripts import (
    add_observation_root_arg,
    build_trizel_metadata,
    parse_and_resolve_observation_root,
)

OBJECT_NAME = "3I/ATLAS"

# Maps canonical source key (lowercase) to its normalized parameter file.
# Aligned with scripts/epistemic_engine.py SOURCE_FILES.
_NORMALIZED_FILES: Dict[str, str] = {
    "jpl_sbdb": "normalized_observation.json",
    "mpc": "mpc_normalized.json",
}

# Maps canonical source key (lowercase) to its ingestion-status file.
# These files carry an explicit temporal-absence marker when data has not yet
# been published (COMPARISON_SEMANTICS.md §3.4).
_INGESTION_STATUS_FILES: Dict[str, str] = {
    "mpc": "mpc_object_ingest.json",
}

# Status values representing explicit "not yet published" temporal absence (§3.4).
# These are distinct from generic retrieval failure values in _UNAVAILABLE_STATUSES.
_TEMPORAL_ABSENCE_STATUSES: Set[str] = {
    "not_ingested",
    "not_yet_available",
    "not_published",
}

# Status values representing generic source unavailability (§3.3).
_UNAVAILABLE_STATUSES: Set[str] = {
    "not_available",
    "unavailable",
}

# Observed-state label used in §3.1 and §3.4 entries to indicate that a
# source contributed normalized parameter data.
_STATE_DATA_PRESENT = "data_present"

# Observed-state label used in §3.1 entries to indicate that a source is
# tracked but contributed no normalized parameter data.
_STATE_DATA_ABSENT = "data_absent"

# TRIZEL canonical metadata block.
# Every artifact produced by this layer carries this block for traceability
# and attribution (TRIZEL_KERNEL_V1.md).
TRIZEL_METADATA: Dict[str, Any] = build_trizel_metadata(
    artifact_type="inconsistency_report",
    generated_by="scripts/detect_inconsistencies.py",
)


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Optional[Any]:
    """Load and parse a JSON file. Returns None if missing or unparseable."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def _load_raw_sources(observation_root: Path) -> Dict[str, str]:
    """Load raw_sources.json and return {source_key_lower: status} mapping.

    Each entry in raw_sources.json is expected as:
      {"source": "<NAME>", "status": "<STATUS>"}
    """
    payload = _load_json(observation_root / "raw_sources.json")
    if not isinstance(payload, dict):
        return {}
    result: Dict[str, str] = {}
    for entry in payload.get("sources", []):
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        status = entry.get("status")
        if isinstance(source, str) and isinstance(status, str):
            result[source.lower()] = status
    return result


def _load_normalized_parameters(
    observation_root: Path,
) -> Dict[str, Dict[str, Any]]:
    """Load orbital parameters from all known normalized source files.

    Returns {source_key_lower: orbital_dict}.
    Only sources whose file exists and contains a non-empty ``"orbital"``
    block are included.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for source_key, filename in _NORMALIZED_FILES.items():
        payload = _load_json(observation_root / filename)
        if isinstance(payload, dict):
            orbital = payload.get("orbital")
            if isinstance(orbital, dict) and orbital:
                result[source_key] = orbital
    return result


def _load_ingestion_statuses(observation_root: Path) -> Dict[str, str]:
    """Load ingestion-status files and return {source_key_lower: status}.

    Only sources listed in ``_INGESTION_STATUS_FILES`` are checked.
    """
    result: Dict[str, str] = {}
    for source_key, filename in _INGESTION_STATUS_FILES.items():
        payload = _load_json(observation_root / filename)
        if isinstance(payload, dict):
            status = payload.get("status")
            if isinstance(status, str) and status:
                result[source_key] = status
    return result


# ---------------------------------------------------------------------------
# §3.1 — existence_mismatch
# ---------------------------------------------------------------------------

def detect_existence_mismatch(
    raw_source_statuses: Dict[str, str],
    normalized_params: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Detect existence_mismatch (COMPARISON_SEMANTICS.md §3.1).

    Triggered when at least one tracked source has normalized parameter data
    and at least one other tracked source does not.

    No source is assigned higher authority.  ``observed_states`` records each
    source's data-presence state without interpretation.

    Args:
        raw_source_statuses: {source_key: status} from :func:`_load_raw_sources`.
        normalized_params:   {source_key: orbital_dict} from
                             :func:`_load_normalized_parameters`.

    Returns:
        An inconsistency dict, or ``None`` when no mismatch exists.
    """
    all_sources = set(raw_source_statuses.keys()) | set(normalized_params.keys())
    if len(all_sources) < 2:
        return None

    with_data = [s for s in all_sources if s in normalized_params]
    without_data = [s for s in all_sources if s not in normalized_params]

    if not with_data or not without_data:
        return None

    involved = sorted(all_sources)
    observed_states = {
        s: (_STATE_DATA_PRESENT if s in normalized_params else _STATE_DATA_ABSENT)
        for s in involved
    }

    return {
        "type": "existence_mismatch",
        "involved_sources": involved,
        "observed_states": observed_states,
    }


# ---------------------------------------------------------------------------
# §3.2 — parameter_mismatch
# ---------------------------------------------------------------------------

def detect_parameter_mismatches(
    normalized_params: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Detect parameter_mismatch entries (COMPARISON_SEMANTICS.md §3.2).

    For every orbital parameter present in two or more source files, the
    reported values are compared.  One entry is emitted per parameter whose
    values differ across sources.

    Comparison is exact — no tolerance is applied, and no source is treated
    as authoritative.  ``observed_values`` preserves the full value reported
    by each source without modification.

    Args:
        normalized_params: {source_key: orbital_dict} from
                           :func:`_load_normalized_parameters`.

    Returns:
        A list of inconsistency dicts sorted deterministically by parameter
        name.
    """
    if len(normalized_params) < 2:
        return []

    all_params: Set[str] = set()
    for params in normalized_params.values():
        all_params.update(params.keys())

    mismatches: List[Dict[str, Any]] = []
    for param in sorted(all_params):
        # Collect values only from sources that report this parameter.
        values: Dict[str, Any] = {
            source: params[param]
            for source, params in normalized_params.items()
            if param in params
        }
        if len(values) < 2:
            continue

        # Exact equality check — no tolerance, no normalization.
        unique_values = set(
            tuple(v) if isinstance(v, list) else v
            for v in values.values()
        )
        if len(unique_values) > 1:
            mismatches.append(
                {
                    "type": "parameter_mismatch",
                    "involved_sources": sorted(values.keys()),
                    "parameter": param,
                    "observed_values": dict(sorted(values.items())),
                }
            )

    return mismatches


# ---------------------------------------------------------------------------
# §3.3 — availability_mismatch
# ---------------------------------------------------------------------------

def detect_availability_mismatch(
    raw_source_statuses: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Detect availability_mismatch (COMPARISON_SEMANTICS.md §3.3).

    Triggered when at least one source reports an available state and at
    least one other source reports a generic unavailable state
    (``not_available`` or ``unavailable``).

    ``observed_states`` carries the exact status string from raw_sources.json
    for each source — no aggregation or re-labelling is applied.

    Args:
        raw_source_statuses: {source_key: status} from :func:`_load_raw_sources`.

    Returns:
        An inconsistency dict, or ``None`` when no mismatch exists.
    """
    if len(raw_source_statuses) < 2:
        return None

    available = [
        s
        for s, st in raw_source_statuses.items()
        if st not in _UNAVAILABLE_STATUSES and st not in _TEMPORAL_ABSENCE_STATUSES
    ]
    unavailable = [
        s for s, st in raw_source_statuses.items() if st in _UNAVAILABLE_STATUSES
    ]

    if not available or not unavailable:
        return None

    involved = sorted(raw_source_statuses.keys())
    observed_states = {s: raw_source_statuses[s] for s in involved}

    return {
        "type": "availability_mismatch",
        "involved_sources": involved,
        "observed_states": observed_states,
    }


# ---------------------------------------------------------------------------
# §3.4 — temporal_inconsistency
# ---------------------------------------------------------------------------

def detect_temporal_inconsistency(
    normalized_params: Dict[str, Dict[str, Any]],
    ingestion_statuses: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Detect temporal_inconsistency (COMPARISON_SEMANTICS.md §3.4).

    Triggered when at least one source has normalized parameter data AND at
    least one other source carries an explicit temporal-absence marker in its
    ingestion-status file (a status in ``_TEMPORAL_ABSENCE_STATUSES``).

    Generic unavailability due to retrieval failure is NOT a temporal-absence
    marker; it is captured by :func:`detect_availability_mismatch`.

    ``observed_states`` uses ``"data_present"`` for sources that have
    normalized data, and the verbatim ingestion-status string for sources
    that carry a temporal-absence marker.

    Args:
        normalized_params:  {source_key: orbital_dict} from
                            :func:`_load_normalized_parameters`.
        ingestion_statuses: {source_key: status} from
                            :func:`_load_ingestion_statuses`.

    Returns:
        An inconsistency dict, or ``None`` when no inconsistency is detected.
    """
    sources_with_explicit_absence = [
        source
        for source, status in ingestion_statuses.items()
        if status in _TEMPORAL_ABSENCE_STATUSES and source not in normalized_params
    ]

    if not normalized_params or not sources_with_explicit_absence:
        return None

    involved = sorted(set(normalized_params.keys()) | set(sources_with_explicit_absence))
    observed_states = {
        s: (
            _STATE_DATA_PRESENT
            if s in normalized_params
            else ingestion_statuses[s]
        )
        for s in involved
    }

    return {
        "type": "temporal_inconsistency",
        "involved_sources": involved,
        "observed_states": observed_states,
    }


# ---------------------------------------------------------------------------
# Detection orchestrator
# ---------------------------------------------------------------------------

def detect_inconsistencies(observation_root: Path) -> Dict[str, Any]:
    """Run the full inconsistency detection pipeline for one observation root.

    Orchestration order (mirrors COMPARISON_SEMANTICS.md §3):
      1. Load raw_sources.json         (§3.1, §3.3, §3.4 inputs)
      2. Load normalized source files  (§3.1, §3.2 inputs)
      3. Load ingestion-status files   (§3.4 input)
      4. Apply §3.1 existence_mismatch detection
      5. Apply §3.2 parameter_mismatch detection
      6. Apply §3.3 availability_mismatch detection
      7. Apply §3.4 temporal_inconsistency detection
      8. Assemble and return the canonical data artifact

    The top-level ``source_inputs`` block embeds the data read from each input
    file so that the artifact is self-contained and fully traceable to its
    inputs without requiring the caller to re-read those files.

    No estimation, interpolation, or inference is applied at any step.
    Missing or absent values are recorded as absent, not inferred.

    Args:
        observation_root: Path to the per-date observation directory.

    Returns:
        A dict suitable for serialization to ``inconsistencies.json``.
    """
    raw_source_statuses = _load_raw_sources(observation_root)
    normalized_params = _load_normalized_parameters(observation_root)
    ingestion_statuses = _load_ingestion_statuses(observation_root)

    inconsistencies: List[Dict[str, Any]] = []

    # §3.1 existence_mismatch
    existence = detect_existence_mismatch(raw_source_statuses, normalized_params)
    if existence is not None:
        inconsistencies.append(existence)

    # §3.2 parameter_mismatch (one entry per differing parameter)
    inconsistencies.extend(detect_parameter_mismatches(normalized_params))

    # §3.3 availability_mismatch
    availability = detect_availability_mismatch(raw_source_statuses)
    if availability is not None:
        inconsistencies.append(availability)

    # §3.4 temporal_inconsistency
    temporal = detect_temporal_inconsistency(normalized_params, ingestion_statuses)
    if temporal is not None:
        inconsistencies.append(temporal)

    # Build the source_inputs traceability block.  All input data used during
    # detection is embedded verbatim so the artifact is self-contained.
    source_inputs: Dict[str, Any] = {
        "raw_sources": dict(sorted(raw_source_statuses.items())),
        "normalized_parameters": {
            source: dict(sorted(params.items()))
            for source, params in sorted(normalized_params.items())
        },
        "ingestion_statuses": dict(sorted(ingestion_statuses.items())),
    }

    return {
        "object": OBJECT_NAME,
        "source_inputs": source_inputs,
        "inconsistency_count": len(inconsistencies),
        "inconsistencies": inconsistencies,
        "trizel_metadata": TRIZEL_METADATA,
    }


# ---------------------------------------------------------------------------
# Integration entry point
# ---------------------------------------------------------------------------

def run_for_date(observation_root: Path) -> Dict[str, Any]:
    """Run inconsistency detection for a given observation root and write output.

    Intended to be called after normalization and analysis steps in the
    per-date processing pipeline::

        report = run_for_date(observation_root)
        # writes: observation_root / "inconsistencies.json"

    Args:
        observation_root: Path to the per-date observation directory.

    Returns:
        The inconsistency report dict that was written to disk.
    """
    report = detect_inconsistencies(observation_root)
    out_path = observation_root / "inconsistencies.json"
    observation_root.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point for the inconsistency detection tool."""
    ap = argparse.ArgumentParser(
        description=(
            "Deterministic inconsistency detection tool — detects and records "
            "observable inconsistencies between sources for one observation date. "
            "Writes inconsistencies.json to the observation root directory. "
            "Compliant with docs/COMPARISON_SEMANTICS.md."
        )
    )
    add_observation_root_arg(
        ap,
        "(e.g. data/observations/2026-03-21). "
        "Must contain raw_sources.json.",
    )
    observation_root, err = parse_and_resolve_observation_root(ap)
    if err:
        return err

    report = run_for_date(observation_root)
    out_path = observation_root / "inconsistencies.json"

    print(f"inconsistencies.json -> {out_path}")
    print(f"  object:              {report['object']}")
    print(f"  inconsistency_count: {report['inconsistency_count']}")
    for item in report["inconsistencies"]:
        print(f"  - {item['type']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

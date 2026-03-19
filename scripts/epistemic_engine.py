#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Layer-5 — Cross-Source Epistemic Consistency Engine (Deterministic)

Evaluates cross-source agreement on orbital parameters for 3I/ATLAS.

The engine:
  - does NOT infer scientific truth
  - does NOT perform modeling or estimation
  - ONLY compares available sources and classifies epistemic state

Object:
  3I/ATLAS

Input sources (current):
  - jpl_sbdb  (normalized_observation.json)

Input sources (planned):
  - mpc       (mpc_normalized.json)
  - imcce
  - esa

Comparable parameters:
  - eccentricity (e)
  - semi_major_axis (a)
  - inclination (i)
  - perihelion_distance (q)

Output:
  observations/YYYY-MM-DD/epistemic_state.json

Usage:
  python scripts/epistemic_engine.py --observation-root observations/YYYY-MM-DD

Integration (run_for_date pattern):
  from scripts.epistemic_engine import run_for_date
  run_for_date(observation_root)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

OBJECT_NAME = "3I/ATLAS"

# Matches a YYYY-MM-DD date string used as observation directory names.
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Maps each source key to the corresponding normalized filename in the observation root.
SOURCE_FILES: Dict[str, str] = {
    "jpl_sbdb": "normalized_observation.json",
    "mpc": "mpc_normalized.json",
}


# ---------------------------------------------------------------------------
# Step 1 — Load sources
# ---------------------------------------------------------------------------

def load_sources(observation_root: Path) -> Dict[str, Any]:
    """Load available source payloads from the observation root directory.

    Only sources whose normalized file exists are included.
    Files that cannot be parsed as JSON are silently skipped.

    Args:
        observation_root: Path to the per-date observation directory.

    Returns:
        Dict mapping source key (e.g. "jpl_sbdb") to parsed JSON payload.
    """
    sources: Dict[str, Any] = {}
    for source_key, filename in SOURCE_FILES.items():
        filepath = observation_root / filename
        if filepath.exists():
            try:
                payload = json.loads(filepath.read_text(encoding="utf-8"))
                sources[source_key] = payload
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
    return sources


# ---------------------------------------------------------------------------
# Step 2 — Extract parameters
# ---------------------------------------------------------------------------

def _get_float(mapping: Dict[str, Any], key: str) -> Optional[float]:
    """Return a float value from a dict, or None if missing or non-numeric."""
    val = mapping.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def extract_parameters(payload: Any) -> Dict[str, Optional[float]]:
    """Extract comparable orbital parameters from a normalized source payload.

    Reads from ``payload["orbital"]``.  Any missing or non-numeric value is
    preserved as ``None`` (no estimation or interpolation is applied).

    Args:
        payload: Parsed JSON payload from a normalized source file.

    Returns:
        Dict with keys ``e``, ``a``, ``i``, ``q`` mapping to float or None.
    """
    null_result: Dict[str, Optional[float]] = {
        "e": None,
        "a": None,
        "i": None,
        "q": None,
    }
    if not isinstance(payload, dict):
        return null_result

    orbital = payload.get("orbital")
    if not isinstance(orbital, dict):
        return null_result

    return {
        "e": _get_float(orbital, "eccentricity"),
        "a": _get_float(orbital, "semi_major_axis"),
        "i": _get_float(orbital, "inclination"),
        "q": _get_float(orbital, "perihelion_distance"),
    }


# ---------------------------------------------------------------------------
# Step 3 — Build parameter table
# ---------------------------------------------------------------------------

def build_table(
    sources: Dict[str, Any],
) -> Dict[str, Dict[str, Optional[float]]]:
    """Build a parameter table mapping each source to its extracted parameters.

    Args:
        sources: Dict mapping source key to parsed JSON payload
                 (as returned by :func:`load_sources`).

    Returns:
        Dict mapping source key to extracted parameter dict.
    """
    return {
        source_key: extract_parameters(payload)
        for source_key, payload in sources.items()
    }


# ---------------------------------------------------------------------------
# Step 4 — Compute pairwise deltas
# ---------------------------------------------------------------------------

def _pair_deltas(
    params_1: Dict[str, Optional[float]],
    params_2: Dict[str, Optional[float]],
) -> Dict[str, Optional[float]]:
    """Return absolute deltas for one (s1, s2) parameter pair.

    A delta is ``None`` when either source has no value for that parameter.

    Args:
        params_1: Parameter dict for the first source.
        params_2: Parameter dict for the second source.

    Returns:
        Dict with keys ``Δe``, ``Δa``, ``Δi``, ``Δq``.
    """
    def _delta(key: str) -> Optional[float]:
        v1 = params_1.get(key)
        v2 = params_2.get(key)
        if v1 is None or v2 is None:
            return None
        return abs(v1 - v2)

    return {
        "\u0394e": _delta("e"),
        "\u0394a": _delta("a"),
        "\u0394i": _delta("i"),
        "\u0394q": _delta("q"),
    }


def compute_deltas(
    table: Dict[str, Dict[str, Optional[float]]],
) -> Optional[Dict[str, Dict[str, Optional[float]]]]:
    """Compute pairwise absolute deltas between all source pairs.

    Args:
        table: Parameter table as returned by :func:`build_table`.

    Returns:
        Dict mapping ``"s1__vs__s2"`` pair keys to delta dicts, or ``None``
        if fewer than 2 sources are present.
    """
    source_keys: List[str] = list(table.keys())
    if len(source_keys) < 2:
        return None

    deltas: Dict[str, Dict[str, Optional[float]]] = {}
    pair: Tuple[str, str]
    for pair in combinations(source_keys, 2):
        s1, s2 = pair
        pair_key = f"{s1}__vs__{s2}"
        deltas[pair_key] = _pair_deltas(table[s1], table[s2])

    return deltas


# ---------------------------------------------------------------------------
# Step 5 — Classify epistemic state
# ---------------------------------------------------------------------------

def classify_state(
    deltas: Optional[Dict[str, Dict[str, Optional[float]]]],
    source_count: int,
) -> str:
    """Classify the epistemic state from computed deltas and source count.

    Rules (applied in order):
      1. ``source_count < 2``  →  ``"insufficient_data"``
      2. All non-null deltas are exactly 0  →  ``"consensus"``
      3. Any non-null delta > 0  →  ``"divergence"``
      4. No comparable parameters available  →  ``"insufficient_data"``

    Args:
        deltas: Pairwise delta dict as returned by :func:`compute_deltas`,
                or ``None`` when fewer than 2 sources are present.
        source_count: Number of available sources.

    Returns:
        One of ``"insufficient_data"``, ``"consensus"``, or ``"divergence"``.
    """
    if source_count < 2:
        return "insufficient_data"

    all_delta_values: List[float] = []
    if deltas:
        for pair_deltas in deltas.values():
            for delta_val in pair_deltas.values():
                if delta_val is not None:
                    all_delta_values.append(delta_val)

    if not all_delta_values:
        return "insufficient_data"

    if all(d == 0.0 for d in all_delta_values):
        return "consensus"

    if any(d > 0.0 for d in all_delta_values):
        return "divergence"

    return "insufficient_data"  # pragma: no cover


# ---------------------------------------------------------------------------
# Step 5b — Temporal consistency helpers
# ---------------------------------------------------------------------------

def load_previous_epistemic(observation_root: Path) -> Optional[Dict[str, Any]]:
    """Load the nearest previous day's epistemic state record.

    Searches sibling directories of *observation_root* for the most recent
    date directory that precedes the current date and contains an
    ``epistemic_state.json`` file.

    Args:
        observation_root: Path to the current per-date observation directory.

    Returns:
        Parsed ``epistemic_state.json`` from the nearest previous day,
        or ``None`` if no previous day with a readable record exists.
    """
    current_date = observation_root.name
    if not _DATE_RE.match(current_date):
        return None

    obs_parent = observation_root.parent
    if not obs_parent.is_dir():
        return None

    previous_dates = sorted(
        d.name
        for d in obs_parent.iterdir()
        if d.is_dir() and _DATE_RE.match(d.name) and d.name < current_date
    )

    for prev_date in reversed(previous_dates):
        prev_path = obs_parent / prev_date / "epistemic_state.json"
        if prev_path.exists():
            try:
                return json.loads(prev_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

    return None


def evaluate_temporal_consistency(
    current_params: Dict[str, Optional[float]],
    previous_params: Optional[Dict[str, Optional[float]]],
) -> str:
    """Evaluate temporal consistency between current and previous parameters.

    Performs an exact comparison with no tolerance thresholds, no interpolation,
    and no statistical smoothing.

    Args:
        current_params: Current day's extracted parameter dict
                        (keys: ``e``, ``a``, ``i``, ``q``).
        previous_params: Previous day's extracted parameter dict, or ``None``
                         when no prior observation day is available.

    Returns:
        One of:

        * ``"no_history"``  — no previous observation day exists
        * ``"stable"``      — all four parameters are exactly equal
        * ``"evolved"``     — at least one parameter differs
    """
    if previous_params is None:
        return "no_history"

    for key in ("e", "a", "i", "q"):
        if current_params.get(key) != previous_params.get(key):
            return "evolved"

    return "stable"


# ---------------------------------------------------------------------------
# Step 6 — Build output record
# ---------------------------------------------------------------------------

def build_epistemic_record(observation_root: Path) -> Dict[str, Any]:
    """Build a complete epistemic consistency record for the observation root.

    Orchestrates the full pipeline:
      1. Load sources
      2. Build parameter table
      3. Compute pairwise deltas
      4. Classify epistemic state (with temporal enrichment for single-source)
      5. Assemble and return the output record

    For single-source observations the engine evaluates temporal consistency
    against the nearest previous day and returns one of the temporal states
    (``"single_source_no_history"``, ``"single_source_temporally_stable"``,
    ``"single_source_temporally_evolved"``).  Multi-source classification
    (``"consensus"``, ``"divergence"``, ``"insufficient_data"``) is unchanged.

    No estimation, interpolation, or statistical inference is performed.
    Null values are preserved exactly as received from the source files.

    Args:
        observation_root: Path to the per-date observation directory.

    Returns:
        Dict suitable for serialization to ``epistemic_state.json``.
    """
    sources = load_sources(observation_root)
    table = build_table(sources)
    deltas = compute_deltas(table)
    source_count = len(sources)

    if source_count < 2:
        # Single-source path: enrich with temporal consistency evaluation.
        prev_record = load_previous_epistemic(observation_root)

        prev_params: Optional[Dict[str, Optional[float]]] = None
        if prev_record is not None:
            prev_params_raw = prev_record.get("parameters", {})
            for _src_params in prev_params_raw.values():
                if isinstance(_src_params, dict):
                    prev_params = {
                        k: (float(v) if v is not None else None)
                        for k, v in _src_params.items()
                        if k in ("e", "a", "i", "q")
                    }
                    break

        current_params: Dict[str, Optional[float]] = (
            next(iter(table.values())) if table else {}
        )

        temporal_consistency = evaluate_temporal_consistency(
            current_params, prev_params
        )

        _temporal_to_state: Dict[str, str] = {
            "no_history": "single_source_no_history",
            "stable": "single_source_temporally_stable",
            "evolved": "single_source_temporally_evolved",
        }
        state = _temporal_to_state[temporal_consistency]
        confidence = "limited"
    else:
        # Multi-source path: cross-source comparison (unchanged logic).
        # temporal_consistency is null — not applicable when multiple sources
        # are available for direct cross-source comparison.
        state = classify_state(deltas, source_count)
        confidence = "multi_source_comparison"
        temporal_consistency = None

    return {
        "object": OBJECT_NAME,
        "sources": list(sources.keys()),
        "parameters": table,
        "comparison": deltas,
        "temporal_consistency": temporal_consistency,  # null for multi-source
        "epistemic_state": state,
        "confidence": confidence,
    }


# ---------------------------------------------------------------------------
# Integration entry point
# ---------------------------------------------------------------------------

def run_for_date(observation_root: Path) -> Dict[str, Any]:
    """Run the epistemic engine for a given observation root and write output.

    Intended to be called after normalization, analysis, and time-series steps
    in the per-date processing pipeline::

        epistemic = run_for_date(observation_root)
        # writes: observation_root / "epistemic_state.json"

    Args:
        observation_root: Path to the per-date observation directory.

    Returns:
        The epistemic record dict that was written to disk.
    """
    record = build_epistemic_record(observation_root)
    out_path = observation_root / "epistemic_state.json"
    observation_root.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return record


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point for the epistemic consistency engine."""
    ap = argparse.ArgumentParser(
        description=(
            "Layer-5 Epistemic Consistency Engine — evaluates cross-source "
            "agreement on 3I/ATLAS orbital parameters. "
            "Writes epistemic_state.json to the observation root directory."
        )
    )
    ap.add_argument(
        "--observation-root",
        required=True,
        help=(
            "Path to the per-date observation directory "
            "(e.g. observations/2026-03-18). "
            "Must contain normalized_observation.json and/or mpc_normalized.json."
        ),
    )
    args = ap.parse_args()

    observation_root = Path(args.observation_root).resolve()

    if not observation_root.is_dir():
        print(
            f"ERROR: --observation-root not found or not a directory: "
            f"{observation_root}",
            file=sys.stderr,
        )
        return 2

    record = run_for_date(observation_root)
    out_path = observation_root / "epistemic_state.json"

    print(f"epistemic_state.json -> {out_path}")
    print(f"  object:          {record['object']}")
    print(f"  sources:         {record['sources']}")
    print(f"  epistemic_state: {record['epistemic_state']}")
    print(f"  confidence:      {record['confidence']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

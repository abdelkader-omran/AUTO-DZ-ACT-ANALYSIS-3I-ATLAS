"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Temporal Observational Availability — Layer 4B

Deterministic, profile-driven helper for computing temporal observational
availability for capability-attributed observables.

This module answers only:
  given a field that is already capability-attributed, what is its temporal
  availability state in principle at the current layer?

It does NOT infer actual observation, source activation, scheduling outcome,
missed opportunity, proposal history, or mission log evidence.
"""

from datetime import date
from typing import Dict


def parse_iso_date(date_str: str) -> date:
    """Parse YYYY-MM-DD into a date object."""
    return date.fromisoformat(date_str)


def evaluate_source_family_temporal_availability(
    source_family: str,
    snapshot_day: date,
    reference_day: date,
    context: Dict,
) -> str:
    """Return the temporal availability state for a single source family.

    Returns one of:
    - ``"unknown"``       – insufficient temporal knowledge at this layer
    - ``"possible"``      – not ruled out at this deterministic layer
    - ``"not_possible"``  – deterministically ruled out at this layer

    Deterministic rules (in order):
    1. If snapshot_day > reference_day: return ``"unknown"``.
    2. Otherwise:
       - If context is missing or empty: return ``"unknown"``.
       - If context explicitly marks visibility as ``"visible"``:
         return ``"possible"``.
       - If context explicitly marks visibility as ``"not_visible"``:
         return ``"not_possible"``.
       - Otherwise: return ``"unknown"``.

    This function MUST NOT use real mission schedules, telescope pointing logs,
    proposal systems, or actual source activity data.
    """
    # Suppress unused-argument warning; source_family is part of the public
    # interface for future callers that may dispatch on family name.
    _ = source_family

    if snapshot_day > reference_day:
        return "unknown"

    if not context:
        return "unknown"

    visibility = context.get("visibility")
    if visibility == "visible":
        return "possible"
    if visibility == "not_visible":
        return "not_possible"
    return "unknown"


def build_temporal_availability_for_field(
    capability_info: Dict,
    snapshot_day: date,
    reference_day: date,
    context: Dict,
) -> Dict:
    """Build temporal availability for a single capability-attributed field.

    Args:
        capability_info: Dict with ``capability_type`` and
            ``possible_source_families`` keys, e.g.::

                {
                  "capability_type": "spectroscopy",
                  "possible_source_families": ["jwst", "alma", "vlt"]
                }

        snapshot_day: The observation date for the snapshot being processed.
        reference_day: The reference date (typically today in UTC).
        context: Deterministic context dict used to evaluate availability.

    Returns:
        Dict with keys ``capability_type``, ``possible_source_families``,
        ``source_temporal_availability``, and ``availability``.

    Aggregation rule:
    - If any source family is ``"possible"``          → ``availability = "possible"``
    - Elif all source families are ``"not_possible"`` → ``availability = "not_possible"``
    - Else                                            → ``availability = "unknown"``
    """
    capability_type = capability_info.get("capability_type", "")
    families = list(capability_info.get("possible_source_families") or [])

    source_temporal_availability: Dict[str, str] = {
        family: evaluate_source_family_temporal_availability(
            family, snapshot_day, reference_day, context
        )
        for family in families
    }

    statuses = list(source_temporal_availability.values())
    if "possible" in statuses:
        availability = "possible"
    elif statuses and all(s == "not_possible" for s in statuses):
        availability = "not_possible"
    else:
        availability = "unknown"

    return {
        "capability_type": capability_type,
        "possible_source_families": families,
        "source_temporal_availability": source_temporal_availability,
        "availability": availability,
    }


def build_temporal_availability_block(
    attribution_block: Dict,
    snapshot_date_str: str,
    reference_date_str: str,
    context: Dict,
) -> Dict:
    """Build temporal availability for all fields in an attribution block.

    Args:
        attribution_block: Dict mapping field names to capability-info dicts,
            e.g.::

                {
                  "gas_species": {
                    "capability_type": "spectroscopy",
                    "possible_source_families": ["jwst", "alma", "vlt"]
                  }
                }

        snapshot_date_str: Snapshot date as ``"YYYY-MM-DD"`` string.
        reference_date_str: Reference date as ``"YYYY-MM-DD"`` string.
        context: Deterministic context dict passed to each field evaluation.

    Returns:
        Dict mapping each field name to its temporal availability result.
    """
    snapshot_day = parse_iso_date(snapshot_date_str)
    reference_day = parse_iso_date(reference_date_str)

    return {
        field: build_temporal_availability_for_field(
            capability_info, snapshot_day, reference_day, context
        )
        for field, capability_info in attribution_block.items()
    }

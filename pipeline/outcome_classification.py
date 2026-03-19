"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Observational Outcome Classification — Layer 5

Deterministic, profile-driven helper for classifying per-field observational
outcome states.

This module answers only:
  given the current epistemic stack, what is the correct deterministic outcome
  state for each observable field at this layer?

It does NOT infer scheduling, proposal history, mission activity, source-specific
operational facts, missed opportunities, source blame, or performance judgments.
"""

from typing import Any, Dict, Optional


def classify_field_outcome(
    field_name: str,
    available_data: Dict,
    profile_completeness: Dict,
    profile_temporal_availability: Dict,
) -> str:
    """Classify the outcome state for a single observable field.

    Returns one of:

    - ``"observed"``      – field has a non-null value in available_data
    - ``"not_observed"``  – temporally possible but absent from available_data
    - ``"not_available"`` – deterministically ruled out by temporal layer
    - ``"not_ingested"``  – outside current ingestion/pipeline capability
    - ``"unknown"``       – insufficient epistemic basis at this layer

    Deterministic rules applied in order:

    Rule 1:
        If available_data contains a non-null value for field_name →
        return ``"observed"``.

    Rule 2:
        If field_name is in profile_completeness["missing_not_ingested"] →
        return ``"not_ingested"``.

    Rule 3:
        If field_name appears in profile_temporal_availability and its
        aggregated availability is ``"not_possible"`` →
        return ``"not_available"``.

    Rule 4:
        If field_name appears in profile_temporal_availability and its
        aggregated availability is ``"possible"`` →
        return ``"not_observed"``.

    Rule 5:
        Otherwise → return ``"unknown"``.

    Args:
        field_name: Name of the observable field to classify.
        available_data: Flat dict of currently ingested field values.
        profile_completeness: Profile completeness dict as returned by
            :func:`pipeline.phenomenon_profiles.build_profile_completeness`.
        profile_temporal_availability: Temporal availability block dict, keyed
            by field name, each value containing an ``"availability"`` key.

    Returns:
        One of ``"observed"``, ``"not_observed"``, ``"not_available"``,
        ``"not_ingested"``, or ``"unknown"``.
    """
    # Rule 1: field is present and non-null
    if available_data.get(field_name) is not None:
        return "observed"

    # Rule 2: field is outside ingestion capability
    missing_not_ingested = profile_completeness.get("missing_not_ingested") or []
    if field_name in missing_not_ingested:
        return "not_ingested"

    # Rules 3 & 4: consult temporal availability if the field appears there
    field_temporal = _find_field_in_temporal_block(
        field_name, profile_temporal_availability
    )
    if field_temporal is not None:
        availability = field_temporal.get("availability")
        if availability == "not_possible":
            return "not_available"
        if availability == "possible":
            return "not_observed"

    # Rule 5: default
    return "unknown"


def _find_field_in_temporal_block(
    field_name: str,
    profile_temporal_availability: Dict,
) -> Optional[Dict[str, Any]]:
    """Return the temporal availability entry for field_name, or None.

    The temporal availability block produced by the pipeline has the shape::

        {
          "missing_not_ingested_temporal": { "<field>": { "availability": ... } },
          "missing_potentially_observable_temporal": { "<field>": { "availability": ... } }
        }

    This helper searches both sub-blocks without assuming which one the field
    belongs to.

    Args:
        field_name: Field to look up.
        profile_temporal_availability: Temporal availability block dict.

    Returns:
        The per-field dict (containing at least ``"availability"``), or
        ``None`` if the field does not appear in any sub-block.
    """
    for sub_key in (
        "missing_not_ingested_temporal",
        "missing_potentially_observable_temporal",
    ):
        sub_block = profile_temporal_availability.get(sub_key) or {}
        if field_name in sub_block:
            return sub_block[field_name]
    return None


def build_outcome_classification_block(
    available_data: Dict,
    profile_completeness: Dict,
    profile_temporal_availability: Dict,
) -> Dict:
    """Build the full observational outcome classification block.

    Classifies every field already referenced by profile_completeness
    (required_fields + optional_fields) and returns a structured block
    with per-field outcomes and a summary grouped by outcome state.

    Example output::

        {
          "field_outcomes": {
            "e": "observed",
            "coma": "unknown",
            "gas_species": "not_ingested"
          },
          "outcome_summary": {
            "observed":      ["e", "a"],
            "not_observed":  [],
            "not_available": [],
            "not_ingested":  ["gas_species"],
            "unknown":       ["coma"]
          }
        }

    The set of evaluated fields is taken exclusively from profile_completeness
    so that no additional fields are inferred.  Output is deterministic.

    Args:
        available_data: Flat dict of currently ingested field values.
        profile_completeness: Profile completeness dict as returned by
            :func:`pipeline.phenomenon_profiles.build_profile_completeness`.
        profile_temporal_availability: Temporal availability block dict as
            returned by
            :func:`pipeline.build_observations._compute_temporal_availability_for_day`.

    Returns:
        Dict with ``"field_outcomes"`` and ``"outcome_summary"`` keys.
    """
    required = list(profile_completeness.get("required_fields") or [])
    optional = list(profile_completeness.get("optional_fields") or [])
    all_fields = required + [f for f in optional if f not in required]

    field_outcomes: Dict[str, str] = {
        field: classify_field_outcome(
            field,
            available_data,
            profile_completeness,
            profile_temporal_availability,
        )
        for field in all_fields
    }

    outcome_summary: Dict[str, list] = {
        "observed": [],
        "not_observed": [],
        "not_available": [],
        "not_ingested": [],
        "unknown": [],
    }
    for field, outcome in field_outcomes.items():
        if outcome in outcome_summary:
            outcome_summary[outcome].append(field)

    return {
        "field_outcomes": field_outcomes,
        "outcome_summary": outcome_summary,
    }

"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Pipeline — Generic Phenomenon Profile Helpers

Provides schema-agnostic helpers for loading phenomenon profiles and computing
profile-driven epistemic completeness.  No domain-specific logic lives here;
all specialisation is encoded in the profile JSON files under
``data/phenomenon_profiles/``.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_phenomenon_profile(phenomenon_type: str, repo_root: Path) -> dict:
    """Load a phenomenon profile JSON from ``data/phenomenon_profiles/``.

    Args:
        phenomenon_type: Profile identifier, e.g. ``"small_body_orbit"``.
        repo_root: Absolute path to the repository root.

    Returns:
        Parsed profile dict.

    Raises:
        FileNotFoundError: When no profile file exists for *phenomenon_type*.
    """
    path = repo_root / "data" / "phenomenon_profiles" / f"{phenomenon_type}.json"
    if not path.exists():
        raise FileNotFoundError(f"Phenomenon profile not found: {phenomenon_type}")
    return json.loads(path.read_text(encoding="utf-8"))


def extract_profile_field_sets(profile: dict) -> dict:
    """Extract required, optional, and currently-ingested field lists from a profile.

    Reads the family-aware ``expected_schema`` structure where each family maps
    to a dict with ``required``, ``optional``, and ``currently_ingested`` keys.

    Args:
        profile: A loaded phenomenon profile dict.

    Returns:
        Dict with keys ``required_fields``, ``optional_fields``, and
        ``currently_ingested_fields``, each holding a flat list of field names.
    """
    schema = profile.get("expected_schema", {})
    required_fields: list = []
    optional_fields: list = []
    currently_ingested_fields: list = []

    for family_def in schema.values():
        if not isinstance(family_def, dict):
            continue
        required_fields.extend(family_def.get("required") or [])
        optional_fields.extend(family_def.get("optional") or [])
        currently_ingested_fields.extend(family_def.get("currently_ingested") or [])

    return {
        "required_fields": required_fields,
        "optional_fields": optional_fields,
        "currently_ingested_fields": currently_ingested_fields,
    }


def detect_missing_fields(expected_fields: list, available_data: dict) -> list:
    """Return fields from *expected_fields* that are absent or ``None`` in *available_data*.

    Args:
        expected_fields: List of field names to check.
        available_data: Flat dict of currently available values, keyed by field name.

    Returns:
        List of field names whose value is missing or ``None``.
    """
    return [field for field in expected_fields if available_data.get(field) is None]


def detect_missing_expected_fields(expected_fields: list, available_data: dict) -> list:
    """Alias for :func:`detect_missing_fields` kept for backward compatibility.

    Args:
        expected_fields: List of field names to check.
        available_data: Flat dict of currently available values, keyed by field name.

    Returns:
        List of field names whose value is missing or ``None``.
    """
    return detect_missing_fields(expected_fields, available_data)


def extract_profile_structure(profile: dict) -> dict:
    """Extract per-family structure including capability_mode from a profile.

    Reads the family-aware ``expected_schema`` and returns a mapping from
    family name to its full definition dict (including ``capability_mode`` when
    present).

    Args:
        profile: A loaded phenomenon profile dict.

    Returns:
        Dict mapping family name to its definition dict.
    """
    return {
        family: definition
        for family, definition in profile.get("expected_schema", {}).items()
        if isinstance(definition, dict)
    }


# Capability modes that classify a missing optional field as "not ingested by
# the current pipeline" rather than "potentially observable but unmeasured".
_NOT_INGESTED_MODES = {"instrument_optional"}

# Capability modes that classify a missing optional field as "observable in
# principle but absent from current available_data".
_POTENTIALLY_OBSERVABLE_MODES = {"contextual_optional", "measurement_optional"}


def classify_missing_optional_fields(
    profile: dict,
    missing_optional_fields: list,
) -> dict:
    """Classify missing optional fields by capability mode.

    For each field in *missing_optional_fields*, look up the ``capability_mode``
    of its parent family and sort it into one of two buckets:

    * ``missing_not_ingested`` — the current ingestion pipeline does not
      support this observable (``capability_mode == "instrument_optional"``).
    * ``missing_potentially_observable`` — the field is observable in principle
      but was not present in the available data (``capability_mode`` is
      ``"contextual_optional"`` or ``"measurement_optional"``).

    Fields whose family carries ``capability_mode == "core"`` or an unrecognised
    mode are silently omitted from both buckets (they should not appear in the
    optional list in the first place).

    Args:
        profile: A loaded phenomenon profile dict.
        missing_optional_fields: List of optional field names that are absent
            from available_data.

    Returns:
        Dict with keys ``missing_not_ingested`` and
        ``missing_potentially_observable``, each holding a list of field names.
    """
    # Build a reverse map: field_name -> capability_mode
    field_to_mode: dict = {}
    for family_def in profile.get("expected_schema", {}).values():
        if not isinstance(family_def, dict):
            continue
        mode = family_def.get("capability_mode", "")
        for field in family_def.get("optional") or []:
            field_to_mode[field] = mode

    missing_not_ingested: list = []
    missing_potentially_observable: list = []

    for field in missing_optional_fields:
        mode = field_to_mode.get(field, "")
        if mode in _NOT_INGESTED_MODES:
            missing_not_ingested.append(field)
        elif mode in _POTENTIALLY_OBSERVABLE_MODES:
            missing_potentially_observable.append(field)

    return {
        "missing_not_ingested": missing_not_ingested,
        "missing_potentially_observable": missing_potentially_observable,
    }


def extract_field_capabilities(profile: dict) -> dict:
    """Return a flat mapping of field name to its capability metadata.

    Reads ``field_capabilities`` from each family in the profile's
    ``expected_schema`` and merges them into a single dict keyed by field name.
    Families that do not carry a ``field_capabilities`` block are silently
    skipped.

    Args:
        profile: A loaded phenomenon profile dict.

    Returns:
        Dict of the form::

            {
              "field_name": {
                "capability_type": "...",
                "possible_source_families": [...]
              }
            }
    """
    capability_map: dict = {}
    for family_def in profile.get("expected_schema", {}).values():
        if not isinstance(family_def, dict):
            continue
        field_caps = family_def.get("field_capabilities")
        if not isinstance(field_caps, dict):
            continue
        for field, cap_info in field_caps.items():
            if isinstance(cap_info, dict):
                capability_map[field] = cap_info
    return capability_map


def build_missing_field_attribution(field_names: list, capability_map: dict) -> dict:
    """Return capability attribution for a list of missing field names.

    For each field in *field_names* that has an entry in *capability_map*,
    copies the attribution metadata (``capability_type`` and
    ``possible_source_families``) into the result.  Fields absent from
    *capability_map* are omitted without error.

    This function is strictly attribution-only: it does not infer source
    activity, observing windows, or date-specific availability.

    Args:
        field_names: List of missing field names to attribute.
        capability_map: Flat capability map as returned by
            :func:`extract_field_capabilities`.

    Returns:
        Dict of the form::

            {
              "field_name": {
                "capability_type": "...",
                "possible_source_families": [...]
              }
            }
    """
    return {
        field: capability_map[field]
        for field in field_names
        if field in capability_map
    }


def build_profile_completeness(profile: dict, available_data: dict) -> dict:
    """Compute a capability-aware profile completeness summary for a given observation.

    Distinguishes between required fields (core orbital completeness) and
    optional fields (broader observational richness).  Missing optional fields
    do not downgrade core completeness and are further classified by capability
    mode into ``missing_not_ingested`` and ``missing_potentially_observable``.

    Attribution metadata is attached to each classified bucket via
    ``missing_not_ingested_attribution`` and
    ``missing_potentially_observable_attribution`` when ``field_capabilities``
    are defined in the profile.  Attribution is deterministic and purely
    profile-driven; it does not infer source activity, observing windows, or
    date-specific availability.

    Args:
        profile: A loaded phenomenon profile dict.
        available_data: Flat dict mapping profile field names to their values.

    Returns:
        Dict with keys ``phenomenon_type``, ``required_fields``,
        ``missing_required_fields``, ``optional_fields``,
        ``missing_optional_fields``, ``missing_not_ingested``,
        ``missing_potentially_observable``,
        ``missing_not_ingested_attribution``,
        ``missing_potentially_observable_attribution``,
        ``currently_ingested_fields``,
        ``completeness_state`` (``"core_complete"`` or ``"core_incomplete"``),
        and ``profile_version``.
    """
    field_sets = extract_profile_field_sets(profile)
    required_fields = field_sets["required_fields"]
    optional_fields = field_sets["optional_fields"]
    currently_ingested_fields = field_sets["currently_ingested_fields"]

    missing_required_fields = detect_missing_fields(required_fields, available_data)
    missing_optional_fields = detect_missing_fields(optional_fields, available_data)

    capability_gaps = classify_missing_optional_fields(profile, missing_optional_fields)

    capability_map = extract_field_capabilities(profile)
    missing_not_ingested_attribution = build_missing_field_attribution(
        capability_gaps["missing_not_ingested"], capability_map
    )
    missing_potentially_observable_attribution = build_missing_field_attribution(
        capability_gaps["missing_potentially_observable"], capability_map
    )

    completeness_state = (
        "core_complete" if not missing_required_fields else "core_incomplete"
    )

    return {
        "phenomenon_type": profile.get("phenomenon_type"),
        "required_fields": required_fields,
        "missing_required_fields": missing_required_fields,
        "optional_fields": optional_fields,
        "missing_optional_fields": missing_optional_fields,
        "missing_not_ingested": capability_gaps["missing_not_ingested"],
        "missing_potentially_observable": capability_gaps["missing_potentially_observable"],
        "missing_not_ingested_attribution": missing_not_ingested_attribution,
        "missing_potentially_observable_attribution": missing_potentially_observable_attribution,
        "currently_ingested_fields": currently_ingested_fields,
        "completeness_state": completeness_state,
        "profile_version": profile.get("profile_version"),
    }

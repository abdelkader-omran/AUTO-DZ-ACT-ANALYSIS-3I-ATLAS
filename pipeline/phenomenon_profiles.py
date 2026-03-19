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


def build_profile_completeness(profile: dict, available_data: dict) -> dict:
    """Compute a family-aware profile completeness summary for a given observation.

    Distinguishes between required fields (core orbital completeness) and
    optional fields (broader observational richness).  Missing optional fields
    do not downgrade core completeness.

    Args:
        profile: A loaded phenomenon profile dict.
        available_data: Flat dict mapping profile field names to their values.

    Returns:
        Dict with keys ``phenomenon_type``, ``required_fields``,
        ``missing_required_fields``, ``optional_fields``,
        ``missing_optional_fields``, ``currently_ingested_fields``,
        ``completeness_state`` (``"core_complete"`` or ``"core_incomplete"``),
        and ``profile_version``.
    """
    field_sets = extract_profile_field_sets(profile)
    required_fields = field_sets["required_fields"]
    optional_fields = field_sets["optional_fields"]
    currently_ingested_fields = field_sets["currently_ingested_fields"]

    missing_required_fields = detect_missing_fields(required_fields, available_data)
    missing_optional_fields = detect_missing_fields(optional_fields, available_data)

    completeness_state = (
        "core_complete" if not missing_required_fields else "core_incomplete"
    )

    return {
        "phenomenon_type": profile.get("phenomenon_type"),
        "required_fields": required_fields,
        "missing_required_fields": missing_required_fields,
        "optional_fields": optional_fields,
        "missing_optional_fields": missing_optional_fields,
        "currently_ingested_fields": currently_ingested_fields,
        "completeness_state": completeness_state,
        "profile_version": profile.get("profile_version"),
    }

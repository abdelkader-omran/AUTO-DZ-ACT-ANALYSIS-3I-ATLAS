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


def get_expected_fields(profile: dict) -> list:
    """Return the flat list of expected field names from a profile's schema.

    Args:
        profile: A loaded phenomenon profile dict.

    Returns:
        Ordered list of field name strings.
    """
    schema = profile.get("expected_schema", {})
    fields = []
    for family_fields in schema.values():
        fields.extend(family_fields)
    return fields


def detect_missing_expected_fields(expected_fields: list, available_data: dict) -> list:
    """Return fields from *expected_fields* that are absent or ``None`` in *available_data*.

    Args:
        expected_fields: List of field names required by the profile.
        available_data: Flat dict of currently available values, keyed by field name.

    Returns:
        List of field names whose value is missing or ``None``.
    """
    return [field for field in expected_fields if available_data.get(field) is None]


def build_profile_completeness(profile: dict, available_data: dict) -> dict:
    """Compute a profile completeness summary for a given observation.

    Args:
        profile: A loaded phenomenon profile dict.
        available_data: Flat dict mapping expected field names to their values.

    Returns:
        Dict with keys ``phenomenon_type``, ``expected_fields``,
        ``missing_fields``, ``missing_count``, ``completeness_state``, and
        ``profile_version``.
    """
    expected_fields = get_expected_fields(profile)
    missing_fields = detect_missing_expected_fields(expected_fields, available_data)

    return {
        "phenomenon_type": profile.get("phenomenon_type"),
        "expected_fields": expected_fields,
        "missing_fields": missing_fields,
        "missing_count": len(missing_fields),
        "completeness_state": "complete" if not missing_fields else "incomplete",
        "profile_version": profile.get("profile_version"),
    }

"""Identity helper module for canonical object registry and designation resolution."""

import json
from pathlib import Path
from typing import Optional


def load_object_registry(object_key: str, repo_root: Path) -> dict:
    """Load the object registry JSON for a given object key.

    Args:
        object_key: The registry key for the object (e.g. ``"atlas-2025-n1"``).
        repo_root:  Absolute path to the repository root.

    Returns:
        Parsed registry dictionary.

    Raises:
        FileNotFoundError: If the registry file does not exist.
    """
    path = repo_root / "data" / "object_registry" / f"{object_key}.json"
    if not path.exists():
        raise FileNotFoundError(f"Registry not found: {object_key}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_designation_at_time(registry: dict, snapshot_date: str) -> Optional[str]:
    """Resolve the canonical designation active on a given snapshot date.

    Iterates through ``designation_history`` in order and returns the last
    entry whose ``timestamp`` is less than or equal to *snapshot_date*.
    Falls back to ``canonical_current`` when no history entry matches.

    Args:
        registry:      Parsed object registry dictionary.
        snapshot_date: ISO-8601 date string (``YYYY-MM-DD``) for the snapshot.

    Returns:
        The resolved designation string, or ``None`` if the registry contains
        neither matching history nor a ``canonical_current`` value.
    """
    history = registry.get("designation_history", [])
    selected = None

    # Normalise to date-only (YYYY-MM-DD) so the comparison is unambiguous
    # regardless of whether snapshot_date includes a time component.
    snapshot_day = snapshot_date[:10]

    for entry in history:
        if entry["timestamp"][:10] <= snapshot_day:
            selected = entry["designation"]

    return selected or registry.get("canonical_current")

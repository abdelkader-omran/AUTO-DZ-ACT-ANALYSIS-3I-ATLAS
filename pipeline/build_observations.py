#!/usr/bin/env python3
# pylint: disable=too-many-lines
"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Analysis Pipeline — Build Observation Dataset

Reads raw evidence from:
  <daily-repo>/data/raw/YYYY-MM-DD/

Parses files downloaded from official sources:
  - IAU MPC        (source_id: MPC)
  - NASA JPL SBDB  (source_id: NASA_JPL_SBDB)
  - NASA JPL Horizons (source_id: JPL_HORIZONS)
  - ESA NEOCC      (source_id: ESA_NEOCC)
  - NASA CNEOS     (source_id: NASA_CNEOS)
  - NASA PDS Small Bodies (source_id: NASA_PDS)

Produces publishable JSON files:
  public/observations/YYYY-MM-DD.json
  public/latest.json
  public/summary.json

Pipeline is deterministic and preserves scientific traceability.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.epistemic_engine import run_for_date
from pipeline.identity import load_object_registry, resolve_designation_at_time
from pipeline.phenomenon_profiles import (
    build_profile_completeness,
    extract_field_capabilities,
    load_phenomenon_profile,
)
from pipeline.temporal_availability import build_temporal_availability_block
from pipeline.outcome_classification import (
    build_outcome_classification_block,
    build_source_outcome_block,
)
from pipeline.source_evidence import build_source_evidence_block
from pipeline.multi_source_consistency import build_multi_source_consistency

PIPELINE_VERSION = "1.0.0"

TRIZEL_METADATA: Dict[str, Any] = {
    "project": "TRIZEL",
    "artifact_type": "epistemic_output",
    "generated_by": "TRIZEL epistemic pipeline",
    "repository": "AUTO-DZ-ACT-ANALYSIS-3I-ATLAS",
    "governance_layer": "publication",
    "citation_required": True,
    "license_reference": "SEE LICENSE IF PRESENT",
    "notice_reference": "SEE NOTICE",
}

OBJECT_KEY = "atlas-2025-n1"
# Phenomenon type for the current first implementation.
# This mapping will later be replaced by a registry-driven object → phenomenon_type
# resolution without redesigning the module.
_PHENOMENON_TYPE = "small_body_orbit"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = load_object_registry(OBJECT_KEY, _REPO_ROOT)
_PHENOMENON_PROFILE = load_phenomenon_profile(_PHENOMENON_TYPE, _REPO_ROOT)

# Canonical source IDs and their primary URLs for traceability
KNOWN_SOURCES: Dict[str, str] = {
    "MPC": "https://minorplanetcenter.net/",
    "JPL_HORIZONS": "https://ssd.jpl.nasa.gov/api/horizons.api",
    "NASA_JPL_SBDB": "https://ssd-api.jpl.nasa.gov/sbdb.api",
    "ESA_NEOCC": "https://neo.ssa.esa.int/",
    "NASA_CNEOS": "https://cneos.jpl.nasa.gov/",
    "NASA_PDS": "https://pds.nasa.gov/",
    "MAST": "https://mast.stsci.edu/api/v0.1/",
    "ESO": "https://archive.eso.org/",
}

# Regex that matches a YYYY-MM-DD date string
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------------------
# SHA-256 helpers
# ---------------------------------------------------------------------------

def _sha256_of_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file's content."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Source-ID detection from file path
# ---------------------------------------------------------------------------

def _detect_source_id_from_path(file_path: Path) -> Optional[str]:
    """
    Try to detect a canonical source_id from path components.

    Matching order:
    1. Any path segment exactly equal to a known source_id (case-insensitive)
    2. Any path segment containing a known source_id token (longest match wins)
    3. Filename stem containing a known source_id token
    """
    candidates = list(file_path.parts) + [file_path.stem]
    for part in candidates:
        upper = part.upper()
        # Exact segment match
        for sid in KNOWN_SOURCES:
            if upper == sid:
                return sid
    for part in candidates:
        upper = part.upper()
        # Substring match (longest source_id wins to avoid false positives)
        found = [sid for sid in KNOWN_SOURCES if sid in upper]
        if found:
            return max(found, key=len)
    return None


# ---------------------------------------------------------------------------
# Parsers for canonical raw-record JSON format
# ---------------------------------------------------------------------------

def _resolve_source_url(
    source_block: Dict[str, Any],
    raw: Dict[str, Any],
    source_id: str,
) -> str:
    """
    Resolve the source URL from the canonical raw record.

    Priority:
    1. source.url field
    2. GET URL extracted from provenance.source_query
    3. Known source registry fallback
    """
    source_url = str(source_block.get("url") or "")
    if source_url:
        return source_url

    prov = raw.get("provenance")
    if isinstance(prov, dict):
        query = str(prov.get("source_query") or "")
        parts = query.split()
        if len(parts) >= 2 and parts[0].upper() == "GET":
            return parts[1]
        if parts:
            return parts[0]

    return KNOWN_SOURCES.get(source_id, "")


def _is_placeholder_sha256(sha256: str) -> bool:
    """Return True if sha256 is empty or an all-zeros placeholder."""
    return not sha256 or not sha256.strip("0")


def _parse_canonical_record(
    raw: Dict[str, Any],
    file_path: Path,
    requested_day_utc: str,
    raw_root: Path,
) -> Optional[Dict[str, Any]]:
    """
    Extract a normalized observation from the canonical raw-record JSON format
    used by the AUTO-DZ-ACT-3I-ATLAS-DAILY ingest layer.

    The canonical format contains:
      source.source_id
      source.url
      acquisition.retrieved_utc
      files[].path, files[].sha256
      integrity.record_sha256
    """
    # Must have at least a source block
    source_block = raw.get("source")
    if not isinstance(source_block, dict):
        return None

    source_id = source_block.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        return None

    source_url = _resolve_source_url(source_block, raw, source_id)

    # Retrieved UTC from acquisition block
    acq = raw.get("acquisition") or {}
    retrieved_utc = str(acq.get("retrieved_utc") or "")

    # SHA-256: prefer per-file hash, then record-level integrity hash
    sha256 = ""
    raw_path_str = ""
    files = raw.get("files")
    if isinstance(files, list) and files:
        first_file = files[0]
        if isinstance(first_file, dict):
            sha256 = str(first_file.get("sha256") or "")
            raw_path_str = str(first_file.get("path") or "")

    integrity = raw.get("integrity") or {}
    if not sha256:
        sha256 = str(integrity.get("record_sha256") or "")

    # If sha256 is a placeholder, compute the real digest from the file
    if _is_placeholder_sha256(sha256):
        sha256 = _sha256_of_file(file_path)

    # raw_path relative to the raw_root if not provided by the record
    if not raw_path_str:
        try:
            raw_path_str = str(file_path.relative_to(raw_root))
        except ValueError:
            raw_path_str = str(file_path)

    return {
        "requested_day_utc": requested_day_utc,
        "source_id": source_id,
        "retrieved_utc": retrieved_utc,
        "sha256": sha256,
        "raw_path": raw_path_str,
        "source_url": source_url,
    }


def _parse_generic_file(
    file_path: Path,
    requested_day_utc: str,
    raw_root: Path,
) -> Dict[str, Any]:
    """
    Build a normalized observation for any file that is not a canonical
    JSON raw record.  Source ID is inferred from the file's path.
    """
    source_id = _detect_source_id_from_path(file_path) or "UNKNOWN"
    sha256 = _sha256_of_file(file_path)

    try:
        raw_path_str = str(file_path.relative_to(raw_root))
    except ValueError:
        raw_path_str = str(file_path)

    return {
        "requested_day_utc": requested_day_utc,
        "source_id": source_id,
        "retrieved_utc": "",
        "sha256": sha256,
        "raw_path": raw_path_str,
        "source_url": KNOWN_SOURCES.get(source_id, ""),
    }


# ---------------------------------------------------------------------------
# Main file-processing logic
# ---------------------------------------------------------------------------

def process_file(
    file_path: Path,
    requested_day_utc: str,
    raw_root: Path,
) -> Optional[Dict[str, Any]]:
    """
    Process a single raw file and return a normalized observation dict,
    or None if the file should be skipped (e.g. .gitkeep, hidden files).
    """
    name = file_path.name
    # Skip hidden files and .gitkeep placeholders
    if name.startswith(".") or name == ".gitkeep":
        return None

    if file_path.suffix.lower() == ".json":
        try:
            raw = json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Not valid JSON — treat as binary blob
            return _parse_generic_file(file_path, requested_day_utc, raw_root)

        if isinstance(raw, dict):
            obs = _parse_canonical_record(raw, file_path, requested_day_utc, raw_root)
            if obs is not None:
                return obs

        # JSON but not canonical format — generic handler
        source_id = _detect_source_id_from_path(file_path) or "UNKNOWN"
        sha256 = _sha256_of_bytes(file_path.read_bytes())
        try:
            raw_path_str = str(file_path.relative_to(raw_root))
        except ValueError:
            raw_path_str = str(file_path)
        return {
            "requested_day_utc": requested_day_utc,
            "source_id": source_id,
            "retrieved_utc": "",
            "sha256": sha256,
            "raw_path": raw_path_str,
            "source_url": KNOWN_SOURCES.get(source_id, ""),
        }

    # Non-JSON file (HTML, text, binary, etc.)
    return _parse_generic_file(file_path, requested_day_utc, raw_root)


def build_observations_for_day(
    day_dir: Path,
    requested_day_utc: str,
    raw_root: Path,
) -> List[Dict[str, Any]]:
    """
    Walk the raw day directory and build normalized observations.

    Records are sorted deterministically by (source_id, raw_path) so that
    the output is reproducible regardless of filesystem traversal order.
    """
    observations: List[Dict[str, Any]] = []

    if not day_dir.is_dir():
        return observations

    for file_path in sorted(day_dir.rglob("*")):
        if not file_path.is_file():
            continue
        obs = process_file(file_path, requested_day_utc, raw_root)
        if obs is not None:
            observations.append(obs)

    # Deterministic sort: source_id then raw_path
    observations.sort(key=lambda r: (r["source_id"], r["raw_path"]))
    return observations


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def _now_utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_day_file(
    observations: List[Dict[str, Any]],
    requested_day_utc: str,
    public_dir: Path,
    generated_utc: str,
    identity_meta: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write public/observations/YYYY-MM-DD.json."""
    obs_dir = public_dir / "observations"
    obs_dir.mkdir(parents=True, exist_ok=True)
    out_path = obs_dir / f"{requested_day_utc}.json"

    payload: Dict[str, Any] = {
        "trizel_metadata": TRIZEL_METADATA,
        "pipeline_version": PIPELINE_VERSION,
        "generated_utc": generated_utc,
        "requested_day_utc": requested_day_utc,
        "record_count": len(observations),
        "observations": observations,
    }

    if identity_meta:
        payload.update(identity_meta)

    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def write_latest_file(
    public_dir: Path,
    generated_utc: str,
    latest_observations: List[Dict[str, Any]],
    latest_day: str,
) -> Path:
    """Write public/latest.json pointing to the most recent day's data."""
    out_path = public_dir / "latest.json"

    payload: Dict[str, Any] = {
        "trizel_metadata": TRIZEL_METADATA,
        "pipeline_version": PIPELINE_VERSION,
        "generated_utc": generated_utc,
        "latest_day": latest_day,
        "redirect": f"observations/{latest_day}.json",
        "record_count": len(latest_observations),
        "observations": latest_observations,
    }

    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


def write_summary_file(
    all_day_summaries: List[Dict[str, Any]],
    public_dir: Path,
    generated_utc: str,
) -> Path:
    """Write public/summary.json aggregating all processed days."""
    out_path = public_dir / "summary.json"

    payload: Dict[str, Any] = {
        "trizel_metadata": TRIZEL_METADATA,
        "pipeline_version": PIPELINE_VERSION,
        "generated_utc": generated_utc,
        "total_days": len(all_day_summaries),
        "total_records": sum(d["record_count"] for d in all_day_summaries),
        "days": all_day_summaries,
    }

    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return out_path


# ---------------------------------------------------------------------------
# JPL SBDB normalization helpers
# ---------------------------------------------------------------------------

def _try_parse_jpl_sbdb_orbital(raw_file: Path) -> Optional[Dict[str, Any]]:
    """Try to extract orbital parameters from a JPL SBDB raw file.

    The JPL SBDB API returns JSON with an ``orbit.elements`` array whose
    entries carry ``label`` (e.g. ``"e"``) and ``value`` fields.

    Args:
        raw_file: Path to the raw JPL SBDB file (JSON or JSON-in-HTML).

    Returns:
        Dict with keys ``eccentricity``, ``semi_major_axis``, ``inclination``,
        ``perihelion_distance`` mapping to float values, or ``None`` if the
        file cannot be parsed or the expected structure is absent.
    """
    if not raw_file.exists():
        return None
    try:
        content = raw_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    try:
        data: Any = json.loads(content)
    except json.JSONDecodeError:
        return None

    orbit = data.get("orbit") if isinstance(data, dict) else None
    elements = orbit.get("elements") if isinstance(orbit, dict) else None
    if not isinstance(elements, list):
        return None

    _label_to_field: Dict[str, str] = {
        "e": "eccentricity",
        "a": "semi_major_axis",
        "i": "inclination",
        "q": "perihelion_distance",
    }

    orbital: Dict[str, Any] = {}
    for elem in elements:
        if not isinstance(elem, dict):
            continue
        label = elem.get("label", "")
        value = elem.get("value")
        if label in _label_to_field and value is not None:
            try:
                orbital[_label_to_field[label]] = float(value)
            except (TypeError, ValueError):
                pass

    return orbital if orbital else None


def _write_jpl_sbdb_normalized(
    observations: List[Dict[str, Any]],
    raw_root: Path,
    obs_root: Path,
) -> Optional[Dict[str, Any]]:
    """Create ``normalized_observation.json`` for the ``jpl_sbdb`` epistemic source.

    Locates the ``NASA_JPL_SBDB`` raw observation, parses the JPL SBDB JSON
    response to extract orbital elements, and writes the normalized payload to
    ``obs_root/normalized_observation.json``.  Skips silently when the raw
    file is absent or cannot be parsed.

    Args:
        observations: Normalized observation list for the day.
        raw_root: Root directory of the raw snapshot repository.
        obs_root: Per-date observation directory under ``public/observations/``.

    Returns:
        The parsed orbital dict (e.g. ``{"eccentricity": ..., ...}``), or
        ``None`` if no data could be extracted.
    """
    sbdb_obs = next(
        (obs for obs in observations if obs.get("source_id") == "NASA_JPL_SBDB"),
        None,
    )
    if sbdb_obs is None:
        return None

    raw_path_str = sbdb_obs.get("raw_path", "")
    if not raw_path_str:
        return None

    raw_file = raw_root / raw_path_str
    orbital = _try_parse_jpl_sbdb_orbital(raw_file)
    if not orbital:
        return None

    obs_root.mkdir(parents=True, exist_ok=True)
    normalized_path = obs_root / "normalized_observation.json"
    normalized_path.write_text(
        json.dumps({"orbital": orbital}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  normalized_observation.json -> {normalized_path}")
    return orbital


# Mapping from normalized orbital field names to the profile's short-form field names.
# Only build_observations.py adapts the current normalized structure; the core
# phenomenon_profiles module remains schema-agnostic.
_ORBITAL_NORM_TO_PROFILE_FIELD: Dict[str, str] = {
    "eccentricity": "e",
    "semi_major_axis": "a",
    "inclination": "i",
    "perihelion_distance": "q",
}


def _orbital_to_available_data(orbital: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a normalized orbital dict to the flat available_data mapping.

    Translates long-form keys (e.g. ``"eccentricity"``) to the profile
    short-form keys (e.g. ``"e"``) expected by the generic profile completeness
    engine.

    Args:
        orbital: Dict as produced by :func:`_try_parse_jpl_sbdb_orbital`.

    Returns:
        Flat dict keyed by profile field names.
    """
    return {
        short: orbital.get(long)
        for long, short in _ORBITAL_NORM_TO_PROFILE_FIELD.items()
    }


def _embed_epistemic_in_day_file(
    day_file_path: Path,
    epistemic_record: Dict[str, Any],
) -> None:
    """Embed the epistemic state record into the flat daily JSON file.

    Reads the existing flat daily JSON, adds (or replaces) a top-level
    ``"epistemic_state"`` field with the given record, and writes it back.
    Existing fields are preserved unchanged.

    Args:
        day_file_path: Path to the ``public/observations/YYYY-MM-DD.json`` file.
        epistemic_record: The record returned by :func:`run_for_date`.
    """
    try:
        payload: Dict[str, Any] = json.loads(
            day_file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["epistemic_state"] = epistemic_record

    day_file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_trizel_metadata_in_epistemic_file(obs_root: Path) -> None:
    """Inject ``trizel_metadata`` into the per-date ``epistemic_state.json``.

    If the file does not exist the call is a no-op.

    Args:
        obs_root: Per-date observation directory under ``public/observations/``.
    """
    epistemic_path = obs_root / "epistemic_state.json"
    if not epistemic_path.exists():
        return

    try:
        payload: Dict[str, Any] = json.loads(
            epistemic_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["trizel_metadata"] = TRIZEL_METADATA

    epistemic_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_profile_completeness_in_day_file(
    day_file_path: Path,
    profile_completeness: Dict[str, Any],
) -> None:
    """Inject ``profile_completeness`` into the flat daily JSON file.

    Reads the existing flat daily JSON, adds (or replaces) a top-level
    ``"profile_completeness"`` field, and writes it back.  All other existing
    fields are preserved unchanged.

    Args:
        day_file_path: Path to the ``public/observations/YYYY-MM-DD.json`` file.
        profile_completeness: Profile completeness summary dict.
    """
    try:
        payload: Dict[str, Any] = json.loads(
            day_file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["profile_completeness"] = profile_completeness

    day_file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_profile_completeness_in_epistemic_file(
    obs_root: Path,
    profile_completeness: Dict[str, Any],
) -> None:
    """Inject ``profile_completeness`` into the per-date ``epistemic_state.json``.

    If the file does not exist the call is a no-op.

    Args:
        obs_root: Per-date observation directory under ``public/observations/``.
        profile_completeness: Profile completeness summary dict.
    """
    epistemic_path = obs_root / "epistemic_state.json"
    if not epistemic_path.exists():
        return

    try:
        payload: Dict[str, Any] = json.loads(
            epistemic_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["profile_completeness"] = profile_completeness

    epistemic_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Temporal availability helpers
# ---------------------------------------------------------------------------

def _embed_temporal_availability_in_day_file(
    day_file_path: Path,
    temporal_availability: Dict[str, Any],
) -> None:
    """Inject ``profile_temporal_availability`` into the flat daily JSON file.

    Reads the existing flat daily JSON, adds (or replaces) a top-level
    ``"profile_temporal_availability"`` field, and writes it back.  All other
    existing fields are preserved unchanged.

    Args:
        day_file_path: Path to the ``public/observations/YYYY-MM-DD.json`` file.
        temporal_availability: Temporal availability block to inject.
    """
    try:
        payload: Dict[str, Any] = json.loads(
            day_file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["profile_temporal_availability"] = temporal_availability

    day_file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_temporal_availability_in_epistemic_file(
    obs_root: Path,
    temporal_availability: Dict[str, Any],
) -> None:
    """Inject ``profile_temporal_availability`` into the per-date epistemic_state.json.

    If the file does not exist the call is a no-op.

    Args:
        obs_root: Per-date observation directory under ``public/observations/``.
        temporal_availability: Temporal availability block to inject.
    """
    epistemic_path = obs_root / "epistemic_state.json"
    if not epistemic_path.exists():
        return

    try:
        payload: Dict[str, Any] = json.loads(
            epistemic_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["profile_temporal_availability"] = temporal_availability

    epistemic_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _compute_temporal_availability_for_day(
    profile_completeness: Dict[str, Any],
    date_str: str,
    reference_date_str: str,
) -> Optional[Dict[str, Any]]:
    """Compute the temporal availability block for a single day.

    Uses the capability attribution blocks already produced by the profile
    completeness layer.

    Args:
        profile_completeness: Profile completeness dict as returned by
            :func:`build_profile_completeness`.
        date_str: Snapshot date in ``YYYY-MM-DD`` format.
        reference_date_str: Reference date in ``YYYY-MM-DD`` format (UTC today).

    Returns:
        Dict with ``missing_not_ingested_temporal``,
        ``missing_potentially_observable_temporal``, and ``reference_date``
        keys, or ``None`` on failure.
    """
    temporal_context: Dict[str, Any] = {
        # Intentional placeholder for layer-4b: no geometry engine or telescope
        # scheduling is available yet.  All evaluations resolve to "unknown" at
        # this layer, which is the correct baseline state.  Future PRs will
        # supply a richer context (e.g. geometric visibility) to unlock
        # "possible" / "not_possible" states.
        "visibility": "unknown",
    }

    not_ingested_attribution: Dict[str, Any] = profile_completeness.get(
        "missing_not_ingested_attribution", {}
    ) or {}
    potentially_observable_attribution: Dict[str, Any] = profile_completeness.get(
        "missing_potentially_observable_attribution", {}
    ) or {}

    try:
        missing_not_ingested_temporal = build_temporal_availability_block(
            not_ingested_attribution,
            date_str,
            reference_date_str,
            temporal_context,
        )
        missing_potentially_observable_temporal = build_temporal_availability_block(
            potentially_observable_attribution,
            date_str,
            reference_date_str,
            temporal_context,
        )
    except Exception as exc:  # pylint: disable=broad-except
        print(
            f"  WARNING: temporal availability failed for {date_str}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None

    return {
        "missing_not_ingested_temporal": missing_not_ingested_temporal,
        "missing_potentially_observable_temporal": missing_potentially_observable_temporal,
        "reference_date": reference_date_str,
    }


# ---------------------------------------------------------------------------
# Observational outcome classification helpers
# ---------------------------------------------------------------------------

def _embed_observational_outcome_in_day_file(
    day_file_path: Path,
    observational_outcome: Dict[str, Any],
) -> None:
    """Inject ``observational_outcome`` into the flat daily JSON file.

    Reads the existing flat daily JSON, adds (or replaces) a top-level
    ``"observational_outcome"`` field, and writes it back.  All other existing
    fields are preserved unchanged.

    Args:
        day_file_path: Path to the ``public/observations/YYYY-MM-DD.json`` file.
        observational_outcome: Outcome classification block to inject.
    """
    try:
        payload: Dict[str, Any] = json.loads(
            day_file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["observational_outcome"] = observational_outcome

    day_file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_observational_outcome_in_epistemic_file(
    obs_root: Path,
    observational_outcome: Dict[str, Any],
) -> None:
    """Inject ``observational_outcome`` into the per-date ``epistemic_state.json``.

    If the file does not exist the call is a no-op.

    Args:
        obs_root: Per-date observation directory under ``public/observations/``.
        observational_outcome: Outcome classification block to inject.
    """
    epistemic_path = obs_root / "epistemic_state.json"
    if not epistemic_path.exists():
        return

    try:
        payload: Dict[str, Any] = json.loads(
            epistemic_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["observational_outcome"] = observational_outcome

    epistemic_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Source-aware outcome attribution helpers (Layer 5B)
# ---------------------------------------------------------------------------

def _embed_source_outcome_attribution_in_day_file(
    day_file_path: Path,
    source_outcome_attribution: Dict[str, Any],
) -> None:
    """Inject ``source_outcome_attribution`` into the flat daily JSON file.

    Reads the existing flat daily JSON, adds (or replaces) a top-level
    ``"source_outcome_attribution"`` field, and writes it back.  All other
    existing fields are preserved unchanged.

    Args:
        day_file_path: Path to the ``public/observations/YYYY-MM-DD.json`` file.
        source_outcome_attribution: Source outcome attribution block to inject.
    """
    try:
        payload: Dict[str, Any] = json.loads(
            day_file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["source_outcome_attribution"] = source_outcome_attribution

    day_file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_source_outcome_attribution_in_epistemic_file(
    obs_root: Path,
    source_outcome_attribution: Dict[str, Any],
) -> None:
    """Inject ``source_outcome_attribution`` into the per-date epistemic_state.json.

    If the file does not exist the call is a no-op.

    Args:
        obs_root: Per-date observation directory under ``public/observations/``.
        source_outcome_attribution: Source outcome attribution block to inject.
    """
    epistemic_path = obs_root / "epistemic_state.json"
    if not epistemic_path.exists():
        return

    try:
        payload: Dict[str, Any] = json.loads(
            epistemic_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["source_outcome_attribution"] = source_outcome_attribution

    epistemic_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_source_evidence_in_day_file(
    day_file_path: Path,
    source_evidence: Dict[str, Any],
) -> None:
    """Inject ``source_evidence`` into the flat daily JSON file.

    Reads the existing flat daily JSON, adds (or replaces) a top-level
    ``"source_evidence"`` field, and writes it back.  All other existing
    fields are preserved unchanged.

    Args:
        day_file_path: Path to the ``public/observations/YYYY-MM-DD.json`` file.
        source_evidence: Source evidence block to inject.
    """
    try:
        payload: Dict[str, Any] = json.loads(
            day_file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["source_evidence"] = source_evidence

    day_file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_source_evidence_in_epistemic_file(
    obs_root: Path,
    source_evidence: Dict[str, Any],
) -> None:
    """Inject ``source_evidence`` into the per-date epistemic_state.json.

    If the file does not exist the call is a no-op.

    Args:
        obs_root: Per-date observation directory under ``public/observations/``.
        source_evidence: Source evidence block to inject.
    """
    epistemic_path = obs_root / "epistemic_state.json"
    if not epistemic_path.exists():
        return

    try:
        payload: Dict[str, Any] = json.loads(
            epistemic_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["source_evidence"] = source_evidence

    epistemic_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_multi_source_consistency_in_day_file(
    day_file_path: Path,
    multi_source_consistency: Dict[str, Any],
) -> None:
    """Inject ``multi_source_consistency`` into the flat daily JSON file.

    Reads the existing flat daily JSON, adds (or replaces) a top-level
    ``"multi_source_consistency"`` field, and writes it back.  All other
    existing fields are preserved unchanged.

    Args:
        day_file_path: Path to the ``public/observations/YYYY-MM-DD.json`` file.
        multi_source_consistency: Consistency block to inject.
    """
    try:
        payload: Dict[str, Any] = json.loads(
            day_file_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["multi_source_consistency"] = multi_source_consistency

    day_file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _embed_multi_source_consistency_in_epistemic_file(
    obs_root: Path,
    multi_source_consistency: Dict[str, Any],
) -> None:
    """Inject ``multi_source_consistency`` into the per-date epistemic_state.json.

    If the file does not exist the call is a no-op.

    Args:
        obs_root: Per-date observation directory under ``public/observations/``.
        multi_source_consistency: Consistency block to inject.
    """
    epistemic_path = obs_root / "epistemic_state.json"
    if not epistemic_path.exists():
        return

    try:
        payload: Dict[str, Any] = json.loads(
            epistemic_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return

    payload["multi_source_consistency"] = multi_source_consistency

    epistemic_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _compute_observational_outcome_for_day(
    orbital: Optional[Dict[str, Any]],
    profile_completeness: Dict[str, Any],
    temporal_availability: Dict[str, Any],
    date_str: str,
) -> Optional[Dict[str, Any]]:
    """Compute the observational outcome classification block for a single day.

    Args:
        orbital: Parsed orbital dict, or ``None`` if unavailable.
        profile_completeness: Profile completeness dict as returned by
            :func:`build_profile_completeness`.
        temporal_availability: Temporal availability block as returned by
            :func:`_compute_temporal_availability_for_day`.
        date_str: Date string used for warning messages only.

    Returns:
        Observational outcome block, or ``None`` on failure.
    """
    available_data: Dict[str, Any] = _orbital_to_available_data(orbital) if orbital else {}
    try:
        result = build_outcome_classification_block(
            available_data=available_data,
            profile_completeness=profile_completeness,
            profile_temporal_availability=temporal_availability,
        )
        return result
    except Exception as exc:  # pylint: disable=broad-except
        print(
            f"  WARNING: outcome classification failed for {date_str}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None


def _apply_consistency_layer(
    orbital: Optional[Dict[str, Any]],
    source_evidence: Dict[str, Any],
    out_path: Path,
    obs_root: Path,
    *,
    date_str: str,
) -> None:
    """Compute and embed the multi-source consistency block for a single day.

    Args:
        orbital: Parsed orbital dict, or ``None`` if unavailable.
        source_evidence: Source evidence block as returned by
            :func:`build_source_evidence_block`.
        out_path: Path to the flat daily JSON file.
        obs_root: Per-date observation directory.
        date_str: Date string used for warning messages only.
    """
    try:
        source_values_by_field: Dict[str, Any] = {}
        if orbital:
            for long_name, short_name in _ORBITAL_NORM_TO_PROFILE_FIELD.items():
                value = orbital.get(long_name)
                if value is not None:
                    source_values_by_field[short_name] = {"jpl_sbdb": value}
        multi_source_consistency = build_multi_source_consistency(
            source_evidence=source_evidence,
            source_values_by_field=source_values_by_field,
        )
        _embed_multi_source_consistency_in_day_file(out_path, multi_source_consistency)
        _embed_multi_source_consistency_in_epistemic_file(obs_root, multi_source_consistency)
    except Exception as exc:  # pylint: disable=broad-except
        print(
            f"  WARNING: multi-source consistency failed for {date_str}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )


def _apply_outcome_layer(  # pylint: disable=too-many-arguments
    orbital: Optional[Dict[str, Any]],
    profile_completeness: Dict[str, Any],
    temporal_availability: Dict[str, Any],
    out_path: Path,
    obs_root: Path,
    *,
    date_str: str,
) -> None:
    """Compute and embed the observational outcome block for a single day.

    Also computes and embeds the source-aware outcome attribution block
    (Layer 5B) immediately after the outcome classification.

    Combines the compute and embed steps so that the calling function does not
    need to hold the outcome block as a local variable.

    Args:
        orbital: Parsed orbital dict, or ``None`` if unavailable.
        profile_completeness: Profile completeness dict.
        temporal_availability: Temporal availability block.
        out_path: Path to the flat daily JSON file.
        obs_root: Per-date observation directory.
        date_str: Date string used for warning messages only.
    """
    outcome = _compute_observational_outcome_for_day(
        orbital, profile_completeness, temporal_availability, date_str
    )
    if outcome is not None:
        _embed_observational_outcome_in_day_file(out_path, outcome)
        _embed_observational_outcome_in_epistemic_file(obs_root, outcome)

        # Layer 5B: source-aware outcome attribution
        try:
            capability_attribution = extract_field_capabilities(_PHENOMENON_PROFILE)
            source_outcome = build_source_outcome_block(
                outcome, capability_attribution, temporal_availability
            )
            _embed_source_outcome_attribution_in_day_file(out_path, source_outcome)
            _embed_source_outcome_attribution_in_epistemic_file(obs_root, source_outcome)

            # Layer 6: source-level observational evidence grounding
            try:
                source_evidence = build_source_evidence_block(source_outcome)
                _embed_source_evidence_in_day_file(out_path, source_evidence)
                _embed_source_evidence_in_epistemic_file(obs_root, source_evidence)

                # Layer 7: deterministic multi-source epistemic consistency
                _apply_consistency_layer(
                    orbital, source_evidence, out_path, obs_root, date_str=date_str
                )
            except Exception as exc:  # pylint: disable=broad-except
                print(
                    f"  WARNING: source evidence grounding failed for {date_str}: "
                    f"{type(exc).__name__}: {exc}",
                    file=sys.stderr,
                )
        except Exception as exc:  # pylint: disable=broad-except
            print(
                f"  WARNING: source outcome attribution failed for {date_str}: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )


# ---------------------------------------------------------------------------
# Date processing helper
# ---------------------------------------------------------------------------

def _compute_profile_completeness_for_day(
    orbital: Optional[Dict[str, Any]],
    date_str: str,
) -> Optional[Dict[str, Any]]:
    """Compute profile completeness for a single day from normalized orbital data.

    Args:
        orbital: Parsed orbital dict, or ``None`` if unavailable.
        date_str: Date string used for warning messages only.

    Returns:
        Profile completeness dict, or ``None`` on failure.
    """
    available_data: Dict[str, Any] = _orbital_to_available_data(orbital) if orbital else {}
    try:
        result = build_profile_completeness(_PHENOMENON_PROFILE, available_data)
        print(f"  profile_completeness: {result['completeness_state']}")
        return result
    except Exception as exc:  # pylint: disable=broad-except
        print(
            f"  WARNING: profile completeness failed for {date_str}: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None


def _process_single_date(
    date_str: str,
    raw_root: Path,
    public_dir: Path,
    generated_utc: str,
) -> Dict[str, Any]:
    """Process one date and return its day-summary dict.

    Writes the per-day observation file, normalized orbital data, epistemic
    state, and profile completeness outputs for *date_str*.

    Args:
        date_str: Date in ``YYYY-MM-DD`` format.
        raw_root: Root of the raw snapshot repository.
        public_dir: Output directory for publishable JSON files.
        generated_utc: ISO-8601 UTC timestamp string for this pipeline run.

    Returns:
        Day-summary dict with ``date``, ``record_count``, ``sources``, and
        ``path`` keys.
    """
    day_dir = raw_root / date_str
    print(f"Processing {date_str} from {day_dir} …")

    observations = build_observations_for_day(day_dir, date_str, raw_root)

    designation_snapshot = resolve_designation_at_time(_REGISTRY, date_str)
    identity_meta: Dict[str, Any] = {
        "object_key": OBJECT_KEY,
        "designation_snapshot": designation_snapshot,
        "designation_current": _REGISTRY.get("canonical_current"),
        "aliases": _REGISTRY.get("aliases", []),
        "registry_version": _REGISTRY.get("registry_version"),
    }

    out_path = write_day_file(observations, date_str, public_dir, generated_utc, identity_meta)
    print(f"  -> {out_path} ({len(observations)} records)")

    obs_root = public_dir / "observations" / date_str
    obs_root.mkdir(parents=True, exist_ok=True)

    orbital = _write_jpl_sbdb_normalized(observations, raw_root, obs_root)
    profile_completeness = _compute_profile_completeness_for_day(orbital, date_str)

    epistemic_record: Optional[Dict[str, Any]] = None
    try:
        epistemic_record = run_for_date(obs_root)
    except Exception as exc:  # pylint: disable=broad-except
        print(f"  WARNING: epistemic engine failed for {date_str}: {exc}", file=sys.stderr)

    if epistemic_record is not None:
        _embed_epistemic_in_day_file(out_path, epistemic_record)

    if profile_completeness is not None:
        _embed_profile_completeness_in_day_file(out_path, profile_completeness)
        _embed_profile_completeness_in_epistemic_file(obs_root, profile_completeness)

        temporal_availability = _compute_temporal_availability_for_day(
            profile_completeness,
            date_str,
            dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"),
        )
        if temporal_availability is not None:
            _embed_temporal_availability_in_day_file(out_path, temporal_availability)
            _embed_temporal_availability_in_epistemic_file(obs_root, temporal_availability)

            _apply_outcome_layer(
                orbital,
                profile_completeness,
                temporal_availability,
                out_path,
                obs_root,
                date_str=date_str,
            )

    _embed_trizel_metadata_in_epistemic_file(obs_root)

    return {
        "date": date_str,
        "record_count": len(observations),
        "sources": sorted({obs["source_id"] for obs in observations}),
        "path": f"observations/{date_str}.json",
    }


def process_dates(
    dates_to_process: List[str],
    raw_root: Path,
    public_dir: Path,
    generated_utc: str,
) -> List[Dict[str, Any]]:
    """
    Process each date, write per-day observation files, and return a list of
    day-summary dicts suitable for inclusion in summary.json.
    """
    return [
        _process_single_date(date_str, raw_root, public_dir, generated_utc)
        for date_str in dates_to_process
    ]


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """Main entry point for the analysis pipeline."""
    ap = argparse.ArgumentParser(
        description=(
            "Build normalized observation dataset from "
            "AUTO-DZ-ACT-3I-ATLAS-DAILY raw snapshots."
        )
    )
    ap.add_argument(
        "--raw-dir",
        required=True,
        help=(
            "Path to the raw data root of AUTO-DZ-ACT-3I-ATLAS-DAILY "
            "(e.g. /path/to/AUTO-DZ-ACT-3I-ATLAS-DAILY/data/raw). "
            "The pipeline processes all YYYY-MM-DD sub-directories found here, "
            "or only the date(s) specified via --date."
        ),
    )
    ap.add_argument(
        "--date",
        default=None,
        help=(
            "Process only this specific date (YYYY-MM-DD). "
            "If omitted, all YYYY-MM-DD sub-directories under --raw-dir are processed."
        ),
    )
    ap.add_argument(
        "--public-dir",
        default="public",
        help="Output directory for publishable JSON files (default: public/).",
    )
    args = ap.parse_args()

    raw_root = Path(args.raw_dir).resolve()
    public_dir = Path(args.public_dir).resolve()

    if not raw_root.is_dir():
        print(f"ERROR: --raw-dir not found or not a directory: {raw_root}", file=sys.stderr)
        return 2

    # Determine which dates to process
    if args.date:
        if not _DATE_RE.match(args.date):
            print(f"ERROR: --date must be YYYY-MM-DD, got: {args.date!r}", file=sys.stderr)
            return 2
        dates_to_process = [args.date]
    else:
        dates_to_process = sorted(
            d.name
            for d in raw_root.iterdir()
            if d.is_dir() and _DATE_RE.match(d.name)
        )
        if not dates_to_process:
            print(
                f"WARNING: No YYYY-MM-DD sub-directories found under {raw_root}",
                file=sys.stderr,
            )

    generated_utc = _now_utc_iso()

    all_day_summaries = process_dates(dates_to_process, raw_root, public_dir, generated_utc)

    # Write latest.json (last entry in sorted summaries is the most recent day)
    if all_day_summaries:
        latest = all_day_summaries[-1]
        latest_day = latest["date"]
        latest_obs_path = public_dir / "observations" / f"{latest_day}.json"
        latest_observations = json.loads(
            latest_obs_path.read_text(encoding="utf-8")
        )["observations"]
        latest_path = write_latest_file(
            public_dir, generated_utc, latest_observations, latest_day
        )
        print(f"latest.json -> {latest_path}")

    summary_path = write_summary_file(all_day_summaries, public_dir, generated_utc)
    print(f"summary.json -> {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

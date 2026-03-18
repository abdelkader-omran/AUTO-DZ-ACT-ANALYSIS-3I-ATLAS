#!/usr/bin/env python3
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

PIPELINE_VERSION = "1.0.0"

OBJECT_KEY = "atlas-2025-n1"
_REPO_ROOT = Path(__file__).resolve().parents[1]
_REGISTRY = load_object_registry(OBJECT_KEY, _REPO_ROOT)

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
) -> None:
    """Create ``normalized_observation.json`` for the ``jpl_sbdb`` epistemic source.

    Locates the ``NASA_JPL_SBDB`` raw observation, parses the JPL SBDB JSON
    response to extract orbital elements, and writes the normalized payload to
    ``obs_root/normalized_observation.json``.  Skips silently when the raw
    file is absent or cannot be parsed.

    Args:
        observations: Normalized observation list for the day.
        raw_root: Root directory of the raw snapshot repository.
        obs_root: Per-date observation directory under ``public/observations/``.
    """
    sbdb_obs = next(
        (obs for obs in observations if obs.get("source_id") == "NASA_JPL_SBDB"),
        None,
    )
    if sbdb_obs is None:
        return

    raw_path_str = sbdb_obs.get("raw_path", "")
    if not raw_path_str:
        return

    raw_file = raw_root / raw_path_str
    orbital = _try_parse_jpl_sbdb_orbital(raw_file)
    if not orbital:
        return

    obs_root.mkdir(parents=True, exist_ok=True)
    normalized_path = obs_root / "normalized_observation.json"
    normalized_path.write_text(
        json.dumps({"orbital": orbital}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  normalized_observation.json -> {normalized_path}")


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


# ---------------------------------------------------------------------------
# Date processing helper
# ---------------------------------------------------------------------------

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
    all_day_summaries: List[Dict[str, Any]] = []

    for date_str in dates_to_process:
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

        # Prepare per-date observation root for Layer-5 inputs and outputs.
        obs_root = public_dir / "observations" / date_str
        obs_root.mkdir(parents=True, exist_ok=True)

        # Create normalized_observation.json from JPL SBDB raw data if available.
        _write_jpl_sbdb_normalized(observations, raw_root, obs_root)

        # Run Layer-5 epistemic engine on the per-date observation root.
        epistemic_record: Optional[Dict[str, Any]] = None
        try:
            epistemic_record = run_for_date(obs_root)
        except Exception as exc:  # pylint: disable=broad-except
            print(f"  WARNING: epistemic engine failed for {date_str}: {exc}", file=sys.stderr)

        # Embed epistemic state into the flat daily JSON.
        if epistemic_record is not None:
            _embed_epistemic_in_day_file(out_path, epistemic_record)

        sources_present = sorted({obs["source_id"] for obs in observations})
        all_day_summaries.append({
            "date": date_str,
            "record_count": len(observations),
            "sources": sources_present,
            "path": f"observations/{date_str}.json",
        })

    return all_day_summaries


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

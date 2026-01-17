#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRIZEL Scientific Ingest Layer — JPL Horizons Fetcher (Reproducible)

Repo:
  AUTO-DZ-ACT-ANALYSIS-3I-ATLAS

Creates a raw Horizons fetch + a schema+registry-compliant raw_record under data/records/.

Outputs:
  1) Raw response file under: data/raw/JPL_HORIZONS/<YYYY-MM-DD>/
  2) Record JSON under:       data/records/

Hard guarantees:
  - Stores response verbatim (no interpretation)
  - Computes file sha256 + record_sha256
  - Includes endpoint_id for registry reproducibility
  - (Optional) Validates the produced record via tools/validate_raw_record.py logic

Usage examples:
  python tools/fetch_horizons.py --command "DES=C/2025 N1" --date 2025-12-20
  python tools/fetch_horizons.py --command "DES=3I/ATLAS" --date 2025-12-20
  python tools/fetch_horizons.py --command "C/2025 N1" --date 2025-12-20
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4


REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCES_JSON = REPO_ROOT / "data" / "metadata" / "sources.json"
SCHEMA_JSON = REPO_ROOT / "spec" / "raw_record.schema.json"

RAW_BASE = REPO_ROOT / "data" / "raw" / "JPL_HORIZONS"
RECORDS_DIR = REPO_ROOT / "data" / "records"


@dataclass(frozen=True)
class RegistryEndpoint:
    source_id: str
    endpoint_id: str
    url: str
    method: str
    authority_rank: int


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json_bytes(obj: Any) -> bytes:
    # Deterministic serialization for record_sha256
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _find_registry_endpoint(source_id: str, endpoint_id: str) -> RegistryEndpoint:
    reg = _load_json(SOURCES_JSON)

    src = None
    for s in reg.get("sources", []):
        if isinstance(s, dict) and s.get("source_id") == source_id:
            src = s
            break
    if src is None:
        raise ValueError(f"source_id not found in sources.json: {source_id}")

    ep = None
    for e in src.get("endpoints", []):
        if isinstance(e, dict) and e.get("endpoint_id") == endpoint_id:
            ep = e
            break
    if ep is None:
        available = [x.get("endpoint_id") for x in src.get("endpoints", []) if isinstance(x, dict)]
        raise ValueError(
            f"endpoint_id not found for source_id={source_id}: {endpoint_id}. Available: {available}"
        )

    url = ep.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError(f"Invalid endpoint url in sources.json for {source_id}.{endpoint_id}")

    retrieval = ep.get("retrieval", {})
    method = "GET"
    if isinstance(retrieval, dict) and isinstance(retrieval.get("method"), str):
        method = retrieval["method"].upper().strip()

    ar = src.get("authority_rank")
    if not isinstance(ar, int) or ar < 1:
        raise ValueError(f"Invalid authority_rank in sources.json for source_id={source_id}")

    return RegistryEndpoint(
        source_id=source_id,
        endpoint_id=endpoint_id,
        url=url,
        method=method,
        authority_rank=ar,
    )


def _normalize_command(command: str) -> str:
    c = command.strip()
    if not c:
        raise ValueError("Empty --command is not allowed")

    # Allow user to pass plain designation like: "C/2025 N1" or "3I/ATLAS"
    # Horizons "COMMAND" parameter can accept many syntaxes; we do minimal normalization:
    if c.upper().startswith("DES=") or c.upper().startswith("COMMAND="):
        # If user provided DES=..., keep it (we will map it into COMMAND param below)
        return c
    return c  # pass-through


def _build_horizons_params(command: str, center: str, ephem_type: str, fmt: str) -> Dict[str, str]:
    # Always request JSON container. Horizons returns JSON with "result" string.
    # If user passed DES=..., we set COMMAND to that value verbatim (including DES=...).
    c = command
    if c.upper().startswith("COMMAND="):
        c = c.split("=", 1)[1].strip()

    params: Dict[str, str] = {
        "format": fmt,
        "COMMAND": c,
        "EPHEM_TYPE": ephem_type,
        "CENTER": center,
    }
    return params


def _http_get(url: str, params: Dict[str, str], timeout_s: int = 60) -> Tuple[str, bytes]:
    q = urllib.parse.urlencode(params, doseq=True, safe=":/@+(),;=")
    full_url = f"{url}?{q}"
    req = urllib.request.Request(full_url, method="GET", headers={"User-Agent": "TRIZEL-AUTO-DZ-ACT/1.0"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = resp.read()
    return full_url, data


def _ensure_dirs(date_str: str) -> Path:
    out_dir = RAW_BASE / date_str
    out_dir.mkdir(parents=True, exist_ok=True)
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    return out_dir


def _write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _validate_created_record(record_path: Path) -> Tuple[bool, List[str]]:
    # Reuse existing validator logic if present
    validator_path = REPO_ROOT / "tools" / "validate_raw_record.py"
    if not validator_path.exists():
        return True, ["(validator not found)"]

    try:
        # Import as module by path (no extra deps)
        import importlib.util

        spec = importlib.util.spec_from_file_location("validate_raw_record", str(validator_path))
        if spec is None or spec.loader is None:
            return False, ["Failed to load validator module"]

        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore

        validate_record = getattr(mod, "validate_record", None)
        if not callable(validate_record):
            return False, ["validate_record() not found or not callable in validator"]

        ok, msgs = validate_record(record_path)  # type: ignore
        return bool(ok), list(msgs)
    except Exception as e:
        return False, [f"Validator execution failed: {e}"]


def main(argv: List[str]) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--target-id", default="3I_ATLAS", help="Canonical target_id (default: 3I_ATLAS)")
    p.add_argument(
        "--aliases",
        default="3I/ATLAS,3I ATLAS,C/2025 N1 (ATLAS)",
        help="Comma-separated human designations stored in target.aliases[]",
    )
    p.add_argument(
        "--command",
        required=True,
        help="Horizons COMMAND value (e.g., 'DES=C/2025 N1', 'DES=3I/ATLAS', or 'C/2025 N1')",
    )
    p.add_argument("--date", default=None, help="UTC date folder YYYY-MM-DD (default: today UTC)")
    p.add_argument("--center", default="500@0", help="Horizons CENTER (default: 500@0)")
    p.add_argument("--ephem-type", default="V", help="Horizons EPHEM_TYPE (default: V)")
    p.add_argument("--timeout", type=int, default=60, help="HTTP timeout seconds (default: 60)")
    p.add_argument(
        "--validate",
        action="store_true",
        help="Validate produced record using tools/validate_raw_record.py",
    )
    args = p.parse_args(argv[1:])

    date_str = args.date
    if date_str is None:
        date_str = datetime.now(timezone.utc).date().isoformat()

    target_id = str(args.target_id).strip()
    if not target_id:
        raise ValueError("target-id must be non-empty")

    aliases = [x.strip() for x in str(args.aliases).split(",") if x.strip()]
    cmd = _normalize_command(str(args.command))

    # Registry endpoint (must exist in data/metadata/sources.json)
    reg_ep = _find_registry_endpoint(source_id="JPL_HORIZONS", endpoint_id="horizons_api")
    if reg_ep.method != "GET":
        raise ValueError(f"Unsupported method for horizons_api: {reg_ep.method} (expected GET)")

    out_dir = _ensure_dirs(date_str)

    # Build request
    params = _build_horizons_params(command=cmd, center=str(args.center), ephem_type=str(args.ephem_type), fmt="json")

    # Execute fetch
    full_url, raw_bytes = _http_get(reg_ep.url, params, timeout_s=int(args.timeout))

    # Persist raw response (verbatim)
    raw_filename = f"{target_id}__JPL_HORIZONS__horizons_api__{date_str}.json"
    raw_path = out_dir / raw_filename
    _write_bytes(raw_path, raw_bytes)

    file_sha = _sha256_file(raw_path)
    size_bytes = raw_path.stat().st_size

    retrieved_utc = _utc_now_iso()

    # Build record
    record_id = f"{target_id}__JPL_HORIZONS__{date_str}__{uuid4().hex}"

    record: Dict[str, Any] = {
        "record_id": record_id,
        "target": {
            "target_id": target_id,
            "target_type": "object",
            "aliases": aliases,
        },
        "dataset_role": "ephemeris",
        "priority_profile": "3I_ATLAS_DEFAULT",
        "source": {
            "source_id": reg_ep.source_id,
            "source_type": "ephemeris_service",
            "authority_rank": reg_ep.authority_rank,
            "endpoint_id": reg_ep.endpoint_id,
            "url": reg_ep.url,
            "license": "Public Domain",
            "citation": "NASA/JPL Horizons API (ephemeris service)",
        },
        "acquisition": {
            "retrieved_utc": retrieved_utc,
            "time_coverage": {
                "start_utc": retrieved_utc,
                "end_utc": retrieved_utc,
            },
            "facility": {
                "facility_id": "JPL",
                "instrument": "",
                "program_id": "",
            },
        },
        "files": [
            {
                "path": str(raw_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "media_type": "application/json",
                "role": "primary",
                "size_bytes": int(size_bytes),
                "sha256": file_sha,
            }
        ],
        "provenance": {
            "source_query": f"GET {full_url} (endpoint_id={reg_ep.endpoint_id})",
            "upstream_ids": {
                "COMMAND": params.get("COMMAND", ""),
                "EPHEM_TYPE": params.get("EPHEM_TYPE", ""),
                "CENTER": params.get("CENTER", ""),
                "format": params.get("format", ""),
            },
        },
        "integrity": {
            "record_sha256": "0" * 64,  # set after canonicalization below
        },
        "notes": "Canonical JPL Horizons ephemeris record. Response stored verbatim; no interpretation applied.",
    }

    # Compute record_sha256 over canonical JSON with record_sha256 field set to zeros
    record_bytes = _canonical_json_bytes(record)
    record_sha = _sha256_bytes(record_bytes)
    record["integrity"]["record_sha256"] = record_sha

    # Write record JSON
    record_filename = f"{target_id}__JPL_HORIZONS__horizons_api.sample.json"
    record_path = RECORDS_DIR / record_filename
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("FETCH: OK")
    print(f"  Raw saved:    {raw_path.relative_to(REPO_ROOT)}")
    print(f"  Raw sha256:   {file_sha}")
    print(f"  Record saved: {record_path.relative_to(REPO_ROOT)}")
    print(f"  Record sha256:{record_sha}")
    print(f"  Request URL:  {full_url}")

    if args.validate:
        ok, msgs = _validate_created_record(record_path)
        print("\nVALIDATION:")
        print("\n".join(msgs))
        return 0 if ok else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
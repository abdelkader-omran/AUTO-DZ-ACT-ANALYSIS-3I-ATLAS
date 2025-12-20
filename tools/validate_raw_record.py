#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TRIZEL Scientific Ingest Layer — Raw Record Validator

Repo:
  AUTO-DZ-ACT-ANALYSIS-3I-ATLAS

Validates a single raw record JSON file against:
  1) spec/raw_record.schema.json  (JSON Schema)
  2) data/metadata/sources.json   (authoritative source registry)

Hard rules enforced:
  - Record MUST validate against schema
  - source.source_id MUST exist in sources.json
  - source.endpoint_id MUST exist under that source's endpoints[]
  - (Optional) If record includes source.authority_rank:
      it MUST equal the authority_rank declared for that source in sources.json

Usage:
  python tools/validate_raw_record.py data/records/<record>.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = REPO_ROOT / "spec" / "raw_record.schema.json"
DEFAULT_SOURCES = REPO_ROOT / "data" / "metadata" / "sources.json"


def _load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {path}: {e}") from e


def _require_field(obj: Dict[str, Any], field: str, ctx: str) -> Any:
    if field not in obj:
        raise ValueError(f"Missing required field: {ctx}.{field}")
    return obj[field]


def _find_source(registry: Dict[str, Any], source_id: str) -> Optional[Dict[str, Any]]:
    for s in registry.get("sources", []):
        if isinstance(s, dict) and s.get("source_id") == source_id:
            return s
    return None


def _find_endpoint(source: Dict[str, Any], endpoint_id: str) -> Optional[Dict[str, Any]]:
    for ep in source.get("endpoints", []):
        if isinstance(ep, dict) and ep.get("endpoint_id") == endpoint_id:
            return ep
    return None


def _validate_schema(record: Any, schema: Any) -> List[str]:
    """
    Returns list of human-readable errors; empty list => OK.
    """
    try:
        # jsonschema is expected to be installed in your environment.
        from jsonschema import Draft202012Validator  # type: ignore
    except Exception:
        return [
            "Missing dependency: jsonschema",
            "Install with: pip install jsonschema",
        ]

    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(record), key=lambda e: e.path)

    out: List[str] = []
    for e in errors:
        path = "$"
        if e.path:
            path += "".join([f"[{repr(p)}]" if isinstance(p, int) else f".{p}" for p in e.path])
        out.append(f"{path}: {e.message}")
    return out


def validate_record(
    record_path: Path,
    schema_path: Path = DEFAULT_SCHEMA,
    sources_path: Path = DEFAULT_SOURCES,
) -> Tuple[bool, List[str]]:
    messages: List[str] = []

    record = _load_json(record_path)
    schema = _load_json(schema_path)
    registry = _load_json(sources_path)

    # 1) Schema validation
    schema_errors = _validate_schema(record, schema)
    if schema_errors:
        messages.append("✘ Schema validation: FAILED")
        messages.extend([f"  - {x}" for x in schema_errors])
        return False, messages
    messages.append("✔ Schema validation: OK")

    # 2) Registry consistency checks (source_id + endpoint_id)
    if not isinstance(record, dict):
        return False, ["✘ Record root must be a JSON object"]

    source_obj = _require_field(record, "source", "record")
    if not isinstance(source_obj, dict):
        return False, ["✘ record.source must be an object"]

    source_id = _require_field(source_obj, "source_id", "record.source")
    if not isinstance(source_id, str) or not source_id.strip():
        return False, ["✘ record.source.source_id must be a non-empty string"]

    endpoint_id = source_obj.get("endpoint_id")
    if endpoint_id is None:
        return False, ["✘ record.source.endpoint_id is required (must match sources.json endpoints[].endpoint_id)"]
    if not isinstance(endpoint_id, str) or not endpoint_id.strip():
        return False, ["✘ record.source.endpoint_id must be a non-empty string"]

    src = _find_source(registry, source_id)
    if src is None:
        return False, [f"✘ source_id not found in sources.json: {source_id}"]
    messages.append(f"✔ source_id: {source_id} (found)")

    ep = _find_endpoint(src, endpoint_id)
    if ep is None:
        available = [x.get("endpoint_id") for x in src.get("endpoints", []) if isinstance(x, dict)]
        return False, [
            f"✘ endpoint_id not found for source_id={source_id}: {endpoint_id}",
            f"  Available endpoint_id: {available}",
        ]
    messages.append(f"✔ endpoint_id: {endpoint_id} (valid)")

    # 3) Optional authority_rank consistency (if present in record)
    if "authority_rank" in source_obj:
        rec_rank = source_obj.get("authority_rank")
        reg_rank = src.get("authority_rank")

        if rec_rank is not None:
            if not isinstance(rec_rank, int):
                return False, ["✘ record.source.authority_rank must be integer if present"]
            if isinstance(reg_rank, int) and rec_rank != reg_rank:
                return False, [
                    "✘ authority_rank mismatch",
                    f"  record.source.authority_rank = {rec_rank}",
                    f"  sources.json authority_rank     = {reg_rank} (for source_id={source_id})",
                ]
            messages.append("✔ authority_rank: consistent")

    messages.append("RESULT: RECORD IS VALID")
    return True, messages


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Usage: python tools/validate_raw_record.py <path/to/record.json>")
        return 2

    record_path = (REPO_ROOT / argv[1]).resolve() if not Path(argv[1]).is_absolute() else Path(argv[1]).resolve()

    ok, msgs = validate_record(record_path)
    print("\n".join(msgs))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
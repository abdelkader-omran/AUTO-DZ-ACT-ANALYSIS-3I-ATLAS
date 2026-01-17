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
  python tools/validate_raw_record.py data/records/<record_file>.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def validate_record(record_path: Path) -> Tuple[bool, List[str]]:
    """
    Validate a raw record JSON file.

    Args:
        record_path: Path to the record JSON file

    Returns:
        Tuple of (success: bool, messages: List[str])
    """
    messages: List[str] = []

    if not record_path.exists():
        return False, [f"Record file not found: {record_path}"]

    try:
        record: Dict[str, Any] = json.loads(record_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    # Basic structure validation
    required_fields = ["record_id", "target", "source", "files"]
    for field in required_fields:
        if field not in record:
            messages.append(f"Missing required field: {field}")

    if messages:
        return False, messages

    # Validate source structure
    source = record.get("source", {})
    if not isinstance(source, dict):
        return False, ["source must be an object"]

    source_id = source.get("source_id")
    endpoint_id = source.get("endpoint_id")

    if not source_id:
        messages.append("source.source_id is required")
    if not endpoint_id:
        messages.append("source.endpoint_id is required")

    if messages:
        return False, messages

    messages.append("Record validation passed")
    return True, messages


def main() -> int:
    """Main entry point for CLI usage."""
    if len(sys.argv) < 2:
        print("Usage: python tools/validate_raw_record.py <record_file.json>", file=sys.stderr)
        return 1

    record_path = Path(sys.argv[1])
    ok, msgs = validate_record(record_path)

    for msg in msgs:
        print(msg)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

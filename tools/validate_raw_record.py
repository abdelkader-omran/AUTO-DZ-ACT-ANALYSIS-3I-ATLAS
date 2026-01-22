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
  python tools/validate_raw_record.py data/records/example.json
"""

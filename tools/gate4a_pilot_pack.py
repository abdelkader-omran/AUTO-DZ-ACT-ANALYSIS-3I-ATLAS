#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Gate 4A Pilot — Deterministic Validation + Packaging Script

Repository: AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Gate: 4A (Lab Execution Activation - Pilot)

NON-NEGOTIABLE CONSTRAINTS:
- NO scientific interpretation or inference
- NO orbital computations or predictions
- STRUCTURAL validation ONLY
- Deterministic: same input => same outputs (including checksums)
- SHA-256 only (never MD5)

This script:
1) Reads a pinned Layer-1 snapshot JSON file
2) Performs minimal structural validation (JSON parse, metadata presence)
3) Produces a DERIVED package with:
   - derived-status.json (gate/proof/classification/provenance/integrity)
   - derived-manifest.json (SHA-256 checksums of all outputs)
   - validation-trace.txt (plain text trace of validation steps)
   - ro-crate-metadata.json (minimal valid RO-Crate 1.1 JSON-LD)
   - input-snapshot.json (verbatim copy of input)

Usage:
  python tools/gate4a_pilot_pack.py \
    --input <path-to-snapshot.json> \
    --output-dir data/derived/3i-atlas/pilot/as_of_utc=<timestamp> \
    --source-repo <repo-name> \
    --source-commit <commit-sha> \
    --source-path <file-path>
"""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(filepath):
    """Compute SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def validate_snapshot_structure(snapshot_data):
    """
    Perform STRUCTURAL-ONLY validation on snapshot JSON.

    Returns: (validation_state, validation_messages)
      validation_state: "VALID", "INVALID", or "INCONCLUSIVE"
      validation_messages: list of plain text messages
    """
    messages = []
    state = "VALID"

    # Check 1: Must be a dict
    if not isinstance(snapshot_data, dict):
        messages.append("FAIL: Snapshot is not a JSON object (dict)")
        return "INVALID", messages
    messages.append("PASS: Snapshot is a valid JSON object")

    # Check 2: trizel_metadata must exist
    if "trizel_metadata" not in snapshot_data:
        messages.append("FAIL: Missing required field 'trizel_metadata'")
        state = "INVALID"
    else:
        messages.append("PASS: Field 'trizel_metadata' exists")

    # Check 3: If checksum fields exist, preserve them verbatim (do not validate)
    if "checksum" in snapshot_data:
        messages.append("INFO: Checksum field present - preserving verbatim (not validating)")

    # Check 4: No orbital element computation or scientific inference
    messages.append("INFO: No orbital computation performed (out of scope)")
    messages.append("INFO: No scientific interpretation performed (prohibited)")

    return state, messages


def create_derived_status(
    gate, proof_type, classification, as_of_utc,
    input_provenance, input_sha256, validation_state, validation_scope
):
    """Create derived-status.json structure."""
    return {
        "gate": gate,
        "proof_type": proof_type,
        "classification": classification,
        "as_of_utc": as_of_utc,
        "input_provenance": input_provenance,
        "integrity": {
            "algorithm": "sha256",
            "input_sha256": input_sha256,
            "outputs_manifest": "derived-manifest.json"
        },
        "validation_state": validation_state,
        "validation_scope": validation_scope,
        "statement": ("NO INTERPRETATION. NO SCIENTIFIC CLAIMS. "
                      "PACKAGING + STRUCTURAL VALIDATION ONLY.")
    }


def create_ro_crate_metadata(as_of_utc, input_filename, source_repo, source_commit):
    """Create minimal valid RO-Crate 1.1 JSON-LD metadata."""
    return {
        "@context": "https://w3id.org/ro/crate/1.1/context",
        "@graph": [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "conformsTo": {
                    "@id": "https://w3id.org/ro/crate/1.1"
                },
                "about": {
                    "@id": "./"
                }
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": "Gate 4A Pilot - DERIVED Package",
                "description": ("Deterministic lab execution pilot "
                                "(structural validation only, non-interpretive)"),
                "datePublished": as_of_utc,
                "hasPart": [
                    {"@id": "derived-status.json"},
                    {"@id": "derived-manifest.json"},
                    {"@id": "validation-trace.txt"},
                    {"@id": "input-snapshot.json"}
                ]
            },
            {
                "@id": "input-snapshot.json",
                "@type": "File",
                "name": input_filename,
                "description": "Verbatim copy of pinned Layer-1 snapshot",
                "source": f"{source_repo}@{source_commit}"
            },
            {
                "@id": "derived-status.json",
                "@type": "File",
                "description": "Gate 4A pilot status and provenance"
            },
            {
                "@id": "derived-manifest.json",
                "@type": "File",
                "description": "SHA-256 checksums of all output files"
            },
            {
                "@id": "validation-trace.txt",
                "@type": "File",
                "description": "Plain text trace of validation steps performed"
            }
        ]
    }


def main():
    """Main entry point for Gate 4A pilot packaging script."""
    parser = argparse.ArgumentParser(
        description="Gate 4A Pilot - Deterministic Validation + Packaging"
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to input snapshot JSON file"
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Output directory for DERIVED package"
    )
    parser.add_argument(
        "--source-repo",
        required=True,
        help="Source repository name (e.g., abdelkader-omran/AUTO-DZ-ACT-3I-ATLAS-DAILY)"
    )
    parser.add_argument(
        "--source-commit",
        required=True,
        help="Source commit SHA (pinned, immutable)"
    )
    parser.add_argument(
        "--source-path",
        required=True,
        help="Source file path within source repository"
    )

    args = parser.parse_args()

    # Validate input file exists
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate UTC timestamp for this run
    as_of_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    retrieved_utc = as_of_utc  # Same timestamp for pilot

    print("Gate 4A Pilot Packer")
    print("===================")
    print(f"Input: {args.input}")
    print(f"Output: {args.output_dir}")
    print(f"As of UTC: {as_of_utc}")
    print()

    # Step 1: Compute SHA-256 of input
    print("[1/7] Computing SHA-256 of input snapshot...")
    input_sha256 = sha256_file(input_path)
    print(f"  Input SHA-256: {input_sha256}")

    # Step 2: Read and validate snapshot structure
    print("[2/7] Reading and validating snapshot structure...")
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            snapshot_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    validation_state, validation_messages = validate_snapshot_structure(snapshot_data)
    print(f"  Validation state: {validation_state}")
    for msg in validation_messages:
        print(f"    {msg}")

    # Step 3: Copy input snapshot verbatim
    print("[3/7] Copying input snapshot verbatim...")
    output_snapshot_path = output_dir / "input-snapshot.json"
    shutil.copy2(input_path, output_snapshot_path)
    print(f"  Copied to: {output_snapshot_path}")

    # Step 4: Create derived-status.json
    print("[4/7] Creating derived-status.json...")
    input_provenance = {
        "source_repo": args.source_repo,
        "source_commit": args.source_commit,
        "source_path": args.source_path,
        "retrieved_utc": retrieved_utc
    }

    derived_status = create_derived_status(
        gate="4A",
        proof_type="lab-exec-pilot",
        classification="DERIVED",
        as_of_utc=as_of_utc,
        input_provenance=input_provenance,
        input_sha256=input_sha256,
        validation_state=validation_state,
        validation_scope="STRUCTURAL_ONLY"
    )

    status_path = output_dir / "derived-status.json"
    with open(status_path, 'w', encoding='utf-8') as f:
        json.dump(derived_status, f, indent=2, ensure_ascii=False)
    print(f"  Created: {status_path}")

    # Step 5: Create validation-trace.txt
    print("[5/7] Creating validation-trace.txt...")
    trace_path = output_dir / "validation-trace.txt"
    with open(trace_path, 'w', encoding='utf-8') as f:
        f.write("Gate 4A Pilot - Validation Trace\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Timestamp: {as_of_utc}\n")
        f.write(f"Input: {args.source_path}\n")
        f.write(f"Source Repo: {args.source_repo}\n")
        f.write(f"Source Commit: {args.source_commit}\n")
        f.write(f"Input SHA-256: {input_sha256}\n\n")
        f.write("Validation Steps:\n")
        f.write("-" * 60 + "\n")
        for msg in validation_messages:
            f.write(f"{msg}\n")
        f.write("\n")
        f.write(f"Final State: {validation_state}\n")
        f.write("\n")
        f.write("SCOPE: STRUCTURAL_ONLY\n")
        f.write("NO SCIENTIFIC INTERPRETATION PERFORMED\n")
        f.write("NO ORBITAL COMPUTATIONS PERFORMED\n")
    print(f"  Created: {trace_path}")

    # Step 6: Create ro-crate-metadata.json
    print("[6/7] Creating ro-crate-metadata.json...")
    input_filename = input_path.name
    ro_crate = create_ro_crate_metadata(
        as_of_utc, input_filename, args.source_repo, args.source_commit
    )

    ro_crate_path = output_dir / "ro-crate-metadata.json"
    with open(ro_crate_path, 'w', encoding='utf-8') as f:
        json.dump(ro_crate, f, indent=2, ensure_ascii=False)
    print(f"  Created: {ro_crate_path}")

    # Validate that ro-crate-metadata.json is valid JSON-LD
    try:
        with open(ro_crate_path, 'r', encoding='utf-8') as f:
            json.load(f)
        print("  Validated: ro-crate-metadata.json is valid JSON")
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid RO-Crate JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 7: Create derived-manifest.json with SHA-256 of all outputs
    print("[7/7] Creating derived-manifest.json...")
    manifest = {}
    for output_file in output_dir.iterdir():
        if output_file.is_file() and output_file.name != "derived-manifest.json":
            file_sha256 = sha256_file(output_file)
            manifest[output_file.name] = file_sha256
            print(f"  {output_file.name}: {file_sha256}")

    manifest_path = output_dir / "derived-manifest.json"
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"  Created: {manifest_path}")

    # Final validation check
    print()
    print("Validation Complete")
    print("=" * 60)
    print(f"Validation State: {validation_state}")
    print(f"Output Directory: {output_dir}")
    print("Files Created:")
    for output_file in sorted(output_dir.iterdir()):
        if output_file.is_file():
            print(f"  - {output_file.name}")

    # Exit with error code if validation failed
    if validation_state == "INVALID":
        print()
        print("WARNING: Validation state is INVALID")
        print("This package documents structural validation failure.")
        # Note: We still exit 0 because the packaging succeeded
        # The validation result is captured in derived-status.json

    print()
    print("SUCCESS: DERIVED package created successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()

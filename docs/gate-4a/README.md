# Gate 4A — Lab Execution Activation (Pilot)

## Overview

Gate 4A implements a **single deterministic pilot workflow** that produces a DERIVED package from a pinned Layer-1 snapshot file. This is a **lab/analysis-only** execution with strict constraints.

### What Gate 4A Does

✅ **DOES:**
- Fetches a pinned snapshot from Layer-1 repository at a fixed commit (deterministic)
- Performs **STRUCTURAL validation ONLY** (JSON parsing, metadata presence)
- Computes SHA-256 checksums for input and all outputs
- Produces a DERIVED package with provenance and integrity metadata
- Creates valid RO-Crate 1.1 JSON-LD metadata
- Commits results back to this repository under `data/derived/`

### What Gate 4A Does NOT Do

❌ **DOES NOT:**
- Perform any scientific interpretation or inference
- Compute orbital elements, trajectories, or predictions
- Make scientific claims or conclusions
- Create publications, narratives, or dashboards
- Fetch data from external sources (NASA, ESA, etc.)
- Modify the input snapshot in any way
- Use floating/latest versions (everything is pinned)

## Pinned Input Reference

The pilot uses a **frozen, immutable snapshot** from the Layer-1 repository:

- **Source Repository:** `abdelkader-omran/AUTO-DZ-ACT-3I-ATLAS-DAILY`
- **Pinned Commit:** `cc4d8f9020e2a7e084ab643645bc75c18d642188`
- **File Path:** `data/snapshots/official_snapshot_3I_ATLAS_20251219_123807.json`

This ensures **deterministic execution**: same pinned input → same outputs (including checksums).

## How to Run the Workflow

The workflow is **manual-only** (no automatic triggers):

1. Navigate to the repository on GitHub
2. Go to **Actions** → **Gate 4A - Lab Execution Pilot (Manual Only)**
3. Click **Run workflow**
4. Select the branch (typically `feature/gate-4a-lab-exec-pilot-v1` or `main`)
5. Click **Run workflow** button

The workflow will:
1. Checkout this repository
2. Checkout the Layer-1 repository at the pinned commit
3. Verify the pinned snapshot file exists
4. Run the packaging script (`tools/gate4a_pilot_pack.py`)
5. Validate all outputs (checksums, JSON-LD, required files)
6. Upload the DERIVED package as a workflow artifact
7. Commit the package back to this repository

## Output Location and Structure

DERIVED packages are stored under:

```
data/derived/3i-atlas/pilot/as_of_utc=YYYY-MM-DDTHH:MM:SSZ/
├── derived-status.json       # Gate/proof/classification/provenance/integrity
├── derived-manifest.json     # SHA-256 checksums of all output files
├── validation-trace.txt      # Plain text trace of validation steps
├── ro-crate-metadata.json    # RO-Crate 1.1 JSON-LD metadata
└── input-snapshot.json       # Verbatim copy of pinned input snapshot
```

### File Descriptions

**derived-status.json**
- Gate: `4A`
- Proof Type: `lab-exec-pilot`
- Classification: `DERIVED`
- Validation Scope: `STRUCTURAL_ONLY`
- Input provenance (repo/commit/path/timestamp)
- Integrity metadata (SHA-256 checksums)
- Validation state: `VALID`, `INVALID`, or `INCONCLUSIVE`
- Explicit statement: "NO INTERPRETATION. NO SCIENTIFIC CLAIMS. PACKAGING + STRUCTURAL VALIDATION ONLY."

**derived-manifest.json**
- SHA-256 checksums for every output file
- Used to verify integrity of the DERIVED package

**validation-trace.txt**
- Plain text log of all validation steps performed
- Includes checks done (JSON parsing, metadata presence)
- Explicitly states NO scientific interpretation was performed

**ro-crate-metadata.json**
- Minimal valid RO-Crate 1.1 JSON-LD metadata
- Documents the DERIVED package as a dataset
- Links to all component files

**input-snapshot.json**
- Verbatim copy of the pinned input snapshot
- Preserved exactly as retrieved (no modifications)

## Validation Scope

**STRUCTURAL_ONLY** means:

✅ **Validated:**
- JSON parses successfully
- Required metadata fields exist (e.g., `trizel_metadata`)
- File integrity via SHA-256 checksums

❌ **NOT Validated:**
- Scientific accuracy or correctness
- Orbital element values
- Physical interpretations
- Predictions or forecasts

## Explicit Prohibitions

This pilot workflow is **strictly prohibited** from:

1. **Scientific Interpretation:** No analysis, inference, or claims about the object
2. **Orbital Computation:** No trajectory calculations or predictions
3. **External Data Sources:** No calls to NASA, ESA, or any external APIs
4. **Floating Inputs:** Must use the exact pinned commit (no "latest" or branch references)
5. **Non-Deterministic Behavior:** Same input must produce same outputs
6. **MD5 Hashes:** Only SHA-256 is allowed
7. **Site/Publication:** No website changes, no public claims, no narratives

## Deterministic Execution

The workflow is designed to be **fully deterministic**:

- **Pinned Input:** Fixed commit SHA, never a floating branch
- **Timestamp:** Generated at runtime but preserved in metadata
- **Checksums:** SHA-256 hashes are reproducible for same input
- **No External Calls:** No network requests to external services
- **Stable Sorting:** Manifest keys are sorted for consistency

Running the workflow multiple times with the same pinned input will produce packages with:
- Identical input SHA-256
- Identical file content (except timestamps which are metadata)
- Identical validation results

## Troubleshooting

**Workflow fails at "Verify Pinned Snapshot File":**
- The pinned commit or file path may have changed in the Layer-1 repo
- Verify the commit SHA and file path are correct

**Workflow fails at "Validate Manifest Checksums":**
- Output files may have been modified after creation
- Re-run the workflow to regenerate the package

**Workflow fails at "Validate RO-Crate Metadata":**
- The ro-crate-metadata.json is not valid JSON-LD
- Check the packaging script for errors

## Technical Details

**Script:** `tools/gate4a_pilot_pack.py`
- Language: Python 3.12+
- Dependencies: Standard library only (no external packages)
- Exit codes: 0 = success, 1 = error

**Workflow:** `.github/workflows/gate-4a-pilot.yml`
- Trigger: `workflow_dispatch` only
- Runner: `ubuntu-latest`
- Artifact retention: 90 days

## References

- Gate 3A/3B Documentation: Theory-neutral, non-interpretive framework
- RO-Crate Specification: https://w3id.org/ro/crate/1.1
- TRIZEL Governance: See `docs/GOVERNANCE_REFERENCE.md`

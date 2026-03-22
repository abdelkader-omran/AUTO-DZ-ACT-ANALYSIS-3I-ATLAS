# PR Execution Contract — Populate Contiguous Observation Window

Repository: AUTO-DZ-ACT-ANALYSIS-3I-ATLAS  
Layer: Layer-1 — Analysis Input (Consumer Side)  
Status: **ABORTED** — provenance constraints not satisfiable  
Recorded: 2026-03-22

---

## Contract

```
PR_EXECUTION_CONTRACT

TITLE:
Populate Contiguous Observation Window from DAILY Audited Artifacts

TYPE:
DATA_ONLY

LAYER:
LAYER-1 → ANALYSIS INPUT (CONSUMER SIDE)

---

OBJECTIVE:

Populate a contiguous, provenance-valid observation window using ONLY
authoritative DAILY audited artifacts.

---

AUTHORITATIVE_SOURCE:

AUTO-DZ-ACT-3I-ATLAS-DAILY

ACCEPTED:
- audited snapshots
- manifests
- SHA-256 verified artifacts
- DOI-linked artifacts (attestation only)

REJECTED:
- public/
- local repository copies as authority
- cached data
- derived datasets
- inferred data
- reconstructed observations
- mirrored/presentation outputs
- Zenodo as independent source

---

INPUT_DOMAIN:

TARGET_PATH:
data/observations/YYYY-MM-DD/

REQUIRED_FILE:
normalized_observation.json

---

HARD_CONSTRAINTS:

C1: MIN_WINDOW_SIZE ≥ 10 days
C2: DAYS MUST BE CONTIGUOUS (no gaps)
C3: EACH DAY MUST EXIST IN DAILY audited outputs
C4: EACH DAY MUST BE TRACEABLE TO DAILY OR DOI-ATTESTED ARTIFACT
C5: NO PARTIAL POPULATION
C6: NO CROSS-DAY DEPENDENCY
C7: NO DATA REUSE WITHOUT RE-VALIDATION AGAINST DAILY
C8: NO SYNTHETIC CONTINUITY
C9: NO INTERPOLATION
C10: NO INFERENCE

---

VALIDITY_RULE:

FOR EACH DAY d:

IF NOT (provenance_traceable_to_DAILY(d))
→ REJECT d

IF NOT (hash_or_manifest_verifiable(d))
→ REJECT d

IF (derived_or_cached(d))
→ REJECT d

---

WINDOW_RULE:

LET W = set of candidate days

IF NOT (|W| ≥ 10 AND contiguous(W))
→ ABORT

IF EXISTS d ∈ W WHERE d is REJECTED
→ ABORT

---

ATOMICITY_RULE:

IF ABORT:
- NO FILES WRITTEN
- NO PARTIAL STATE

IF SUCCESS:
- WRITE ALL DAYS IN W

---

PROHIBITIONS:

- NO modification of:
  - analysis logic
  - validation logic
  - workflows
  - governance contracts

- NO execution of:
  - epistemic_engine

- NO introduction of:
  - new sources
  - fallback mechanisms
  - bypass flags

---

ABORT_CONDITIONS:

- provenance ambiguity
- missing DAILY linkage
- hash mismatch
- non-contiguous window
- insufficient days (<10)
- any derived data detected

→ FULL ABORT

---

EXPECTED_STATE:

ALL populated observations MUST pass:
provenance_validator → VALID

---

OUTPUT:

A contiguous, provenance-valid observation window ready for temporal analysis.

---

EXECUTION_DIRECTIVE:

Execute deterministically.
Populate ONLY from DAILY authoritative artifacts.
Abort on ANY constraint violation.
No interpretation. No expansion. No deviation.

END_CONTRACT
```

---

## Execution Record — 2026-03-22

### Outcome: ABORT

**Trigger date:** 2026-03-22T03:50:12Z  
**Executed by:** automated analysis agent  
**Result:** FULL ABORT

---

### Abort Reason

The WINDOW_RULE abort condition was reached:

```
IF NOT (|W| ≥ 10 AND contiguous(W))
→ ABORT
```

**Constraint violated:** C1 — MIN_WINDOW_SIZE ≥ 10 days

**Current state of `data/observations/`:**

| Day | Status |
|-----|--------|
| 2026-03-21 | PRESENT — single day only |

Only **1 day** is present in `data/observations/`.  No DAILY audited snapshot
artifacts with independent provenance exist for the 9 additional contiguous
days required to open a valid temporal window.

A previous attempt (2026-03-11 through 2026-03-20) was also rejected for
provenance violation — see `docs/TEMPORAL_WINDOW_GAP_REPORT.md` for the
full abort record of that earlier attempt.

---

### Atomicity Rule Applied

Per the ATOMICITY_RULE:

```
IF ABORT:
- NO FILES WRITTEN
- NO PARTIAL STATE
```

**No files were written to `data/observations/`.** The repository is in the
same state as before this execution attempt.  No partial population, no
synthetic continuity, no carry-forward.

---

### Conditions Required to Unblock

Independent per-day audited snapshots with full provenance linkage must be
supplied by `AUTO-DZ-ACT-3I-ATLAS-DAILY` before this window can be populated.
Each day requires all four linkage elements:

| Linkage element | Requirement |
|---|---|
| Snapshot identifier | `snapshot-YYYY-MM-DD-audited` |
| SHA-256 hash | 64 lower-case hex digits |
| Manifest reference | non-empty string |
| DOI | non-empty string or `doi_absent: true` |

A minimum of 10 contiguous days satisfying all requirements must be available
before execution can proceed.

---

### Reference Documents

- `docs/TEMPORAL_WINDOW_GAP_REPORT.md` — Detailed analysis of the gap and
  earlier abort record
- `docs/governance/provenance_gate.md` — Provenance gate contract
- `validation/provenance_validator.py` — Enforcement implementation

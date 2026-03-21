TRIZEL EXECUTION PROTOCOL (MANDATORY)

Canonical Reference: TRIZEL_SYSTEM_MAP

----------------------------------

STEP 0 — SYSTEM POSITION (MANDATORY)

- Layer: Layer-1
- Repository: AUTO-DZ-ACT-ANALYSIS-3I-ATLAS

- Upstream:
  AUTO-DZ-ACT-3I-ATLAS-DAILY

- Downstream:
  trizel-lab
  trizel-site-artifacts

- Final Output:
  Scientifically validated analysis artifacts published on TRIZEL site (Layer-2) and optionally Zenodo

----------------------------------

STEP 1 — REPO STATE INSPECTION (MANDATORY)

Before any action, the system MUST enumerate exactly what exists:

- directories
- files
- scripts
- workflows
- datasets
- pull requests

No assumptions allowed.

----------------------------------

STEP 2 — COMPLETED WORK (MANDATORY)

The system MUST identify:

- implemented components
- operational pipelines
- partially completed logic
- declared but non-functional elements

----------------------------------

STEP 3 — GAP IDENTIFICATION (MANDATORY)

The system MUST detect:

- missing pipeline connections
- broken upstream/downstream links
- duplication risks
- unused or dead outputs

----------------------------------

STEP 4 — ACTION (ONLY AFTER STEPS 0–3)

Allowed action constraints:

- modify or create ONE file only
- extend existing structure only
- no new architecture
- no duplication
- strictly aligned with repository role

----------------------------------

EXECUTION RULES (ABSOLUTE)

- No step skipping
- No implementation before inspection
- No repository work without full pipeline awareness
- No cross-layer confusion
- No new structures
- No forgetting Layer-2 publication responsibility

----------------------------------

OPERATIONAL MODE

This repository is ANALYSIS layer.

Its responsibility is:
- transforming observational data into structured, verifiable analysis outputs

It MUST NOT:
- perform ingestion (Layer-1 DATA)
- perform publication (Layer-2)
- redefine epistemic structure (Layer-0)

----------------------------------
ENFORCEMENT

Any execution that violates this protocol is invalid.

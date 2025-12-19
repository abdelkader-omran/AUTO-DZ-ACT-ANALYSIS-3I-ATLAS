## TASK 001 — Minimal State Table Generator

### Goal:
Implement `analysis/build_state_table.py` that reads:
- `input/observables.json`
- One snapshot JSON produced by `AUTO-DZ-ACT-3I-ATLAS-DAILY`

and writes:
- `outputs/state_tables/state_table_YYYY-MM-DD.csv`.

### Requirements:
- Deterministic measurement selection by `authority_rank`.
- Enforce tolerances: `epsilon`, `delta`, `time_window_days`.
- Emit epistemic states:
  - NON_COMPARABLE
  - INFTY_OVER_INFTY
  - ZERO_OVER_ZERO
  - D0_OVER_DZ
  - DZ
- Include provenance columns, if available:
  - snapshot_sha256
  - source_id
  - retrieved_utc
  - raw_path
  - measurement_sha256

### Edge Cases:
- Missing or invalid observables.
- Measurement ambiguities.
- Tolerance conflicts.

### Acceptance Test:
```bash
python analysis/build_state_table.py \
  --snapshot <file> \
  --observables input/observables.json \
  --out outputs/state_tables/state_table.csv

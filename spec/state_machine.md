# AUTO DZ ACT — Epistemic State Machine (Formal Definition)

This document defines the epistemic state machine used by **AUTO-DZ-ACT-ANALYSIS-3I-ATLAS**.
It classifies the *verification status* of claims against authoritative observations without imposing physical interpretation.

## 1. Entities and Notation

Let each row in the output state table correspond to one **claim/observable** entry (identified by `observable_id`).

### 1.1 Observable definition
An observable specification **O** is defined by `spec/observables.schema.json` and instantiated in `input/observables.json`.

Each observable includes:
- `id`
- `unit`
- `sources_allowed[]`
- `authority_rank[]`
- `tolerances.epsilon`, `tolerances.delta` with `delta ≥ epsilon`
- `tolerances.time_window_days`
- `tolerances.distance_metric ∈ {abs, relative, L2}`
- optional `normalization.function` (default: identity)

### 1.2 Prediction and Observation
For each observable **O**, define:

- **T**: theoretical/predicted value(s) asserted by a claim.
- **E**: observed/measured value(s) extracted from an authoritative snapshot.

AUTO DZ ACT does not assume T exists in every case. If a claim is “data-only”, then T may be absent by design.

Both T and E may be:
- Scalar number (e.g., perihelion distance)
- Vector (e.g., A1/A2/A3)
- Interval/bounds (e.g., nucleus diameter [min,max])

### 1.3 Time alignment
Let:
- `t_T` be the timestamp/epoch of T (if defined).
- `t_E` be the timestamp/epoch of E (must be present if E exists).
- `W = time_window_days(O)`.

Define time mismatch:
\[
\Delta t = |t_T - t_E| \;\; \text{(in days)}
\]
Time-aligned if:
\[
\Delta t \le W
\]

If `t_T` is undefined, time alignment is evaluated as **pass** (T is treated as time-agnostic), but this must be recorded in provenance.

## 2. Normalization and Distance

### 2.1 Normalization
Let `N_O(·)` be the normalization function for observable O (default identity).
Compute:
\[
T' = N_O(T), \quad E' = N_O(E)
\]

### 2.2 Distance metric D
Define discrepancy **D(T',E')** based on `distance_metric`:

#### A) Absolute (abs)
For scalars:
\[
D = |T' - E'|
\]
For vectors:
\[
D = \|T' - E'\|_2
\]
For intervals [a,b], compare midpoints unless specified otherwise in the observable:
\[
m_T = (a_T+b_T)/2,\; m_E=(a_E+b_E)/2,\; D = |m_T - m_E|
\]

#### B) Relative (relative)
For scalars:
\[
D = \frac{|T' - E'|}{\max(|E'|,\eta)}
\]
where \(\eta>0\) is a small stabilization constant (implementation-defined; default \(\eta=10^{-12}\)).

For vectors:
\[
D = \frac{\|T'-E'\|_2}{\max(\|E'\|_2,\eta)}
\]

#### C) L2 (L2)
Explicit Euclidean norm (same as vector abs case):
\[
D = \|T' - E'\|_2
\]

**Note:** Any non-finite result (NaN/Inf) triggers NON_COMPARABLE unless explicitly allowed by the observable.

## 3. Epistemic States (Precise Definitions)

AUTO DZ ACT states are epistemic; they describe comparability and agreement, not physical nature.

Let:
- \(\varepsilon = \text{epsilon}(O)\)
- \(\delta = \text{delta}(O)\), with \(\delta \ge \varepsilon\)

### 3.1 NON_COMPARABLE
State: `NON_COMPARABLE`

Assigned iff any of the following holds:
1) Units mismatch or missing units preventing comparison.
2) T or E exists but cannot be parsed into the required numeric structure for O.
3) Required metadata for the comparison is missing (e.g., `t_E` absent when E exists).
4) Time misalignment: \(\Delta t > W\)
5) Distance metric cannot be applied to the value type (e.g., incompatible shapes).

Formally:
\[
\text{NON\_COMPARABLE} \iff \neg \text{Comparable}(T,E,O)
\]

### 3.2 INFTY_OVER_INFTY
State: `INFTY_OVER_INFTY`

Assigned iff:
- The observable is well-defined (schema-valid), **but** neither a usable T nor a usable E exists in the snapshot and claim registry.

Interpretation: “No valid comparison possible because both sides are absent.”

Formally:
\[
\text{INFTY\_OVER\_INFTY} \iff (T=\varnothing) \land (E=\varnothing) \land \text{Comparable-by-definition}(O)
\]

### 3.3 ZERO_OVER_ZERO
State: `ZERO_OVER_ZERO`

Assigned iff:
- T and E exist and are comparable, and:
\[
D(T',E') \le \varepsilon
\]

Interpretation: “Claim supported within strict tolerance.”

### 3.4 D0_OVER_DZ
State: `D0_OVER_DZ`

Assigned iff:
- T and E exist and are comparable, and:
\[
\varepsilon < D(T',E') \le \delta
\]

Interpretation: “Ambiguous / insufficient discriminative power under declared tolerances.”

### 3.5 DZ
State: `DZ`

Assigned iff:
- T and E exist and are comparable, and:
\[
D(T',E') > \delta
\]

Interpretation: “Contradiction / falsification under declared tolerances.”

## 4. Authority-Based Measurement Selection

For each observable O:
- Only consider measurements with `source_id ∈ sources_allowed(O)`.
- If multiple candidates exist, select deterministically using `authority_rank(O)`:
  1) choose the highest-ranked `source_id` that has a valid measurement for O;
  2) if multiple measurements exist within that same source, select the one with:
     - the most recent `retrieved_utc` (if present),
     - else stable ordering by `raw_path` ascending,
     - else stable ordering by snapshot-provided index.

The selection algorithm must record:
- `source_id`
- `retrieved_utc`
- `raw_path`
- `measurement_sha256` (if available)
- `snapshot_sha256` (if available)

## 5. Decision Procedure (Canonical)

Given observable O and snapshot S:

### Step 0 — Validate observable schema
If O fails schema validation → `NON_COMPARABLE` (with reason: schema_invalid).

### Step 1 — Extract E from snapshot
Attempt to obtain candidate measurement list for O from S.
If no candidates found → `E = ∅`.

### Step 2 — Select authoritative E*
Apply Section 4. If E exists but none are valid after parsing → treat as `E = ∅` and record parse failure.

### Step 3 — Obtain T
Obtain T from claim registry / configuration for O (implementation-defined).
If not defined → `T = ∅`.

### Step 4 — Determine comparability
Comparable(T,E,O) is true iff:
- O is schema-valid,
- If E exists then it is parseable and has timestamp `t_E`,
- Units and type constraints allow distance metric,
- Time alignment passes (if `t_T` defined): \(\Delta t \le W\).

If not comparable → `NON_COMPARABLE`.

### Step 5 — Assign state
- If `T = ∅` and `E = ∅` → `INFTY_OVER_INFTY`
- Else if `T = ∅` XOR `E = ∅` → `NON_COMPARABLE`
  - reason must identify which side is missing (missing_T or missing_E)
- Else compute D and compare to ε, δ:
  - `D ≤ ε` → `ZERO_OVER_ZERO`
  - `ε < D ≤ δ` → `D0_OVER_DZ`
  - `D > δ` → `DZ`

## 6. Reference Pseudocode (Implementation-Neutral)

```text
function assign_state(observable O, snapshot S, claim_registry R):
  if not schema_valid(O):
    return NON_COMPARABLE(reason="schema_invalid")

  candidates = extract_measurements(S, O.id)
  E = select_authoritative(candidates, O)  # may return None
  T = R.get_prediction(O.id)               # may return None

  if E is None and T is None:
    return INFTY_OVER_INFTY(reason="missing_T_and_E")

  if E is None or T is None:
    return NON_COMPARABLE(reason = E is None ? "missing_E" : "missing_T")

  if not comparable(T, E, O):
    return NON_COMPARABLE(reason="not_comparable")

  D = distance(normalize(T,O), normalize(E,O), O.distance_metric)
  if not finite(D):
    return NON_COMPARABLE(reason="non_finite_distance")

  eps = O.tolerances.epsilon
  delt = O.tolerances.delta

  if D <= eps:
    return ZERO_OVER_ZERO(D=D)
  else if D <= delt:
    return D0_OVER_DZ(D=D)
  else:
    return DZ(D=D)

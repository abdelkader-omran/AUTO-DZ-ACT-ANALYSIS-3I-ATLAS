# Provenance Gate — TRIZEL Contract

## Status

**ACTIVE** — This document constitutes a binding governance contract enforcing
strict provenance constraints on all observational data used in this repository.

---

## Authoritative Provenance Root

The **sole** authoritative provenance root for this repository is:

```
AUTO-DZ-ACT-3I-ATLAS-DAILY
```

No other repository, dataset, service, or derived artifact may act as a
provenance source. This constraint is absolute and admits no exceptions.

---

## Role of ANALYSIS

`AUTO-DZ-ACT-ANALYSIS-3I-ATLAS` is a **consumer only**.

- ANALYSIS **MUST NOT** act as a data source.
- ANALYSIS **MUST NOT** generate, synthesise, carry forward, or re-emit
  observational data.
- Any output produced by ANALYSIS is a governed analytic artifact, not a
  provenance root.

---

## Traceability Requirement

Every observation used in this repository **MUST** be traceable to one of the
following, produced by the DAILY authoritative root:

1. A DAILY audited snapshot identified as `snapshot-YYYY-MM-DD-audited`
2. DOI-linked artifacts are accepted only as attestations of DAILY outputs

Traceability is satisfied only when **all four** of the following linkage
elements are present and verifiable:

| Linkage element | Format / requirement |
|---|---|
| Snapshot identifier | `snapshot-YYYY-MM-DD-audited` |
| SHA-256 hash | hex-encoded digest of the snapshot payload |
| Manifest reference | path or identifier within the DAILY manifest |
| DOI | if available; otherwise explicitly declared absent |

---

## Validation Status

An observation carries one of exactly two statuses:

| Status | Meaning |
|---|---|
| `VALID` | All four linkage elements are present and verified against the DAILY audited snapshot |
| `INVALID` | Any linkage element is absent, unverifiable, or fails verification |

**Structural validity does NOT imply epistemic validity.**  
Passing structural schema checks does not satisfy this gate; full provenance
linkage and hash verification are required independently.

Absence of DAILY-traceable provenance **MUST** result in `INVALID` status.

---

## Atomic Observation Principle

Each observation is atomic with respect to calendar days:

- An observation belongs to exactly one audited snapshot day.
- **No cross-day dependency is permitted.**
- An observation from day *D* must not reference, depend on, or be conditioned
  by any observation from any other day.

Violation of the atomic observation principle results in the
`cross_day_dependency_detected` failure mode (see below).

---

## Canonical Failure Modes

The following failure modes are defined. Each failure mode causes `INVALID`
status and triggers a **FULL ABORT** (see Enforcement).

| Failure mode | Description |
|---|---|
| `provenance_missing` | No provenance linkage is present for the observation |
| `source_unverifiable` | The claimed DAILY source cannot be independently verified |
| `hash_mismatch` | The SHA-256 hash does not match the content of the referenced snapshot |
| `derived_data_detected` | The observation originates from a derived, cached, or synthetic dataset rather than a DAILY audited snapshot |
| `cross_day_dependency_detected` | The observation references or depends on data from a different calendar day |

---

## Prohibitions

The following are **absolutely prohibited**:

- Reuse of existing repository data as a provenance source
- Carry-forward of observations from one day to subsequent days
- Synthetic continuity or gap-filling
- Interpolation or inference of missing observations
- Use of data from `public/`, cached datasets, or any derived dataset
- Any modification outside the `docs/` directory under this gate

---

## Enforcement

1. Every observation **MUST** pass provenance validation before it is used in
   any analytic step.
2. If **any** observation fails provenance validation → **FULL ABORT**.
3. **No partial acceptance is allowed.** A batch of observations is accepted in
   its entirety only if every individual observation in the batch is `VALID`.

---

## Scope of Modification

This gate governs only the `docs/` directory.

- No scripts, epistemic engine components, workflows, or data files are
  modified by this governance document.
- This document itself **MUST NOT** be interpreted as authorising changes
  outside `docs/`.

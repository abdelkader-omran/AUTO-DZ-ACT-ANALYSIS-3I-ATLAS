# COMPARISON SEMANTICS — AUTO-DZ-ACT-3I-ATLAS

## 1. Purpose

This document formally defines the comparison semantics used in the analysis
layer of this repository.

It serves as a canonical reference for any implementation of inconsistency
detection between data sources.

---

## 2. Definition of Inconsistency

An **inconsistency** is an observable difference between two or more sources for
the same object and the same parameter at the same retrieval time.

Inconsistencies are recorded strictly as detected differences.

- No interpretation is applied.
- No source is prioritized over another.
- No determination is made about which source is correct.

---

## 3. Inconsistency Types

### 3.1 `existence_mismatch`

**Definition:**
An object is present in one source but absent in another.

**Condition:**
Source A returns a record for the object. Source B returns no record for the
same object at the same retrieval time.

**Involved sources:**
Any combination of upstream providers tracked in `raw_sources.json`
(e.g., `jpl_sbdb`, `mpc`).

---

### 3.2 `parameter_mismatch`

**Definition:**
The same parameter exists in multiple sources but the reported values differ.

**Condition:**
Source A and Source B both return a value for parameter P, and the values are
not equal.

**Involved sources:**
Any two or more sources that provide overlapping orbital or physical parameters,
as represented in `normalized_observation.json`.

---

### 3.3 `availability_mismatch`

**Definition:**
Two or more sources report conflicting availability states for the same object.

**Condition:**
Source A reports status `ok` and Source B reports status `unavailable` (or
equivalent) for the same object at the same retrieval time.

**Involved sources:**
Sources tracked in `raw_sources.json`, where availability state is explicitly
recorded per provider.

---

### 3.4 `temporal_inconsistency`

**Definition:**
One source reports data for an object while another source explicitly reports
that data is not yet available or not published.

**Condition:**
Source A returns a populated record. Source B returns an explicit marker
indicating data is not yet available or not published, rather than a generic
unavailability or retrieval failure.

**Involved sources:**
Any upstream provider tracked in `raw_sources.json` that distinguishes between
data absence due to non-publication and absence due to retrieval failure.

---

## 4. Constraints

The following constraints apply unconditionally to all comparison operations
defined in this document:

1. **No interpretation** — Inconsistencies are recorded as observed differences
   only. No cause or explanation is inferred.

2. **No source prioritization** — All sources are treated as peers. No source
   is assigned higher authority or trustworthiness.

3. **No correctness determination** — The comparison layer does not decide
   which source value is correct. That determination is outside the scope of
   this layer.

---

## 5. Alignment with Data Structure

This document is aligned with the data structure defined in
[docs/data_structure.md](data_structure.md).

| Inconsistency Type       | Primary Data Files                                    |
|--------------------------|-------------------------------------------------------|
| `existence_mismatch`     | `raw_sources.json`, `normalized_observation.json`     |
| `parameter_mismatch`     | `normalized_observation.json`                         |
| `availability_mismatch`  | `raw_sources.json`                                    |
| `temporal_inconsistency` | `raw_sources.json`, `observation.json`                |

Comparisons operate on the contents of daily snapshots stored under
`observations/YYYY-MM-DD/` as described in the data structure document.

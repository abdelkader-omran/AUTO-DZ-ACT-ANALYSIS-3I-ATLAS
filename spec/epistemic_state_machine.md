# Formal Epistemic State Machine (AUTO DZ ACT)

This document provides a formal, implementation-ready mathematical definition of the epistemic state machine used by AUTO DZ ACT.  
It defines: (i) observables and measurement selection, (ii) discrepancy metrics, (iii) tolerance parameters (ε, δ), and (iv) state assignment rules.  
It does not contain physical interpretation.

---

## 1. Objects and Notation

### 1.1 Observable
An **observable** is a specification entry \(O\) with identifier `id`, unit `unit`, and tolerances:
- \( \varepsilon_O \) (epsilon): strict acceptance tolerance
- \( \delta_O \) (delta): deviation tolerance, with \( \delta_O \ge \varepsilon_O \)
- \( w_O \) (time window in days): allowable epoch mismatch
- \( m_O \) (distance metric): `abs`, `relative`, or `L2`
as defined in `spec/observables.schema.json`.

### 1.2 Theoretical value (T) and Observational value (E)
For each observable \(O\), we consider:
- \( T_O \): theoretical / predicted value (from an explicit claim model or prediction registry).
- \( E_O \): observational / measured value (from authoritative snapshot provenance).

Both may be scalar, vector, or structured values that can be mapped into a numeric representation (Section 2).

### 1.3 Time tagging
- Each value carries an epoch: \( t(T_O) \) and \( t(E_O) \) in UTC.
- Define the epoch mismatch:
\[
\Delta t_O = |t(T_O) - t(E_O)|
\]
(in days).

---

## 2. Normalization and Discrepancy Function

AUTO DZ ACT assigns states based on a non-negative discrepancy \( D_O(T_O, E_O) \).

### 2.1 Numeric representation
Each observable provides (implicitly or explicitly) a mapping:
\[
\phi_O : \text{ValueSpace}(O) \rightarrow \mathbb{R}^k
\]
where \(k=1\) for scalar observables and \(k>1\) for vector/structured observables.
If such a mapping is undefined for the given \(T_O\) or \(E_O\), the comparison is **non-comparable** (Section 4.1).

### 2.2 Distance metrics
Let:
\[
\mathbf{x} = \phi_O(T_O), \quad \mathbf{y} = \phi_O(E_O)
\]

The discrepancy is defined by the metric \(m_O\):

**(a) Absolute distance (`abs`)**
- For \(k=1\):
\[
D_O = |x - y|
\]
- For \(k>1\) use L2 by default unless explicitly overridden:
\[
D_O = \|\mathbf{x}-\mathbf{y}\|_2
\]

**(b) Relative distance (`relative`)**
- For \(k=1\):
\[
D_O =
\begin{cases}
\frac{|x-y|}{\max(|y|, \eta)} & \text{if } y \text{ defined}\\
\text{undefined} & \text{otherwise}
\end{cases}
\]
where \(\eta>0\) is a small constant to avoid division by zero (implementation constant).
- For \(k>1\), use component-wise relative then aggregate by L2 or mean; the aggregation must be declared in the implementation.

**(c) L2 distance (`L2`)**
\[
D_O = \|\mathbf{x}-\mathbf{y}\|_2
\]

### 2.3 Time-window gate
A comparison is allowed only if:
\[
\Delta t_O \le w_O
\]
If not, state assignment proceeds to **non-comparable** unless an explicit time-alignment rule exists for that observable.

---

## 3. Data Availability and Selection

### 3.1 Measurement candidates
Given a snapshot \(S\), define the set of observational candidates for \(O\):
\[
\mathcal{E}_O(S) = \{ E_{O,i} : \text{candidate measurements for } O \text{ in } S\}
\]
Each candidate includes:
- `source_id` (must be in `sources_allowed`)
- `retrieved_utc`
- `raw_path`
- optional hashes/checksums

### 3.2 Authority-ranked deterministic selection
Let `authority_rank = [a_1, a_2, \dots, a_r]` be a strict priority ordering.

Select the measurement \(E_O^\*\) deterministically:
1. Filter candidates to allowed sources:
\[
\mathcal{E}'_O(S)=\{E\in \mathcal{E}_O(S): \text{source}(E)\in \text{sources\_allowed}\}
\]
2. Choose the smallest \(j\) such that there exists a candidate with source \(a_j\).
3. If multiple candidates share the same highest-ranked source, select the one with maximal provenance completeness, then by earliest `retrieved_utc`, then by stable lexical sort of `raw_path` (to ensure determinism).

If \(\mathcal{E}'_O(S)=\emptyset\), observational value is **absent** (Section 4.2).

### 3.3 Theoretical value requirement
If \(T_O\) is not defined (no model output, missing units, missing mapping \(\phi_O\)), then comparison is not possible (Section 4.1).

---

## 4. Epistemic States (Formal Definitions)

Let \(E_O^\*\) be the selected measurement if it exists.

AUTO DZ ACT uses the following states:

### 4.1 NON_COMPARABLE
State:
\[
\texttt{NON\_COMPARABLE}
\]
iff at least one of the following holds:
1. \(T_O\) is undefined or cannot be mapped by \(\phi_O\).
2. \(E_O^\*\) exists but is not in a comparable unit space (unit mismatch not resolvable).
3. The discrepancy \(D_O(T_O,E_O^\*)\) is undefined under the declared metric.
4. The time-window gate fails:
\[
\Delta t_O > w_O
\]

This state means a valid \(D_O\) cannot be computed under declared rules.

### 4.2 INFTY_OVER_INFTY
State:
\[
\texttt{INFTY\_OVER\_

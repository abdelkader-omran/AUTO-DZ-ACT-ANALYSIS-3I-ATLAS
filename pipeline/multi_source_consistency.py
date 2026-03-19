"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Pipeline Layer 7 — Deterministic Multi-Source Epistemic Consistency

Evaluates, per observable field, the consistency state across sources that
have provided grounded observational evidence.

This module is:
- deterministic
- non-probabilistic
- non-inferential
- evidence-grounded
- schema-agnostic
- pure-Python

This module must NOT:
- derive or transform values
- apply scoring or confidence weighting
- apply tolerance thresholds
- apply unit normalization
- apply statistical reasoning
- assume domain-specific field semantics
"""

from typing import Dict


def get_comparable_sources_for_field(field_sources: Dict) -> Dict:
    """
    Select sources eligible for comparison.

    Deterministic rule (strict):

    A source is comparable ONLY if:
    - source state == "observed"
    - evidence.trace_type == "observational_evidence"

    No other condition is allowed in this PR.
    """

    comparable = {}

    for source, source_data in field_sources.items():
        state = source_data.get("state")
        evidence = source_data.get("evidence", {})
        trace_type = evidence.get("trace_type")

        if state == "observed" and trace_type == "observational_evidence":
            comparable[source] = source_data

    return comparable


def classify_consistency_from_values(source_values: Dict) -> str:
    """
    Deterministic consistency classification.

    Rules:
    - fewer than 2 comparable values → "insufficient_evidence"
    - all values exactly equal → "agreement"
    - otherwise → "contradiction"

    Important:
    - exact equality only
    - no tolerance
    - no normalization
    """

    if len(source_values) < 2:
        return "insufficient_evidence"

    values = list(source_values.values())
    first = values[0]

    for value in values[1:]:
        if value != first:
            return "contradiction"

    return "agreement"


def build_field_consistency(
    field: str,
    source_evidence_entry: Dict,
    source_values: Dict,
) -> Dict:
    """
    Build consistency result for a single field.

    source_values MUST be externally provided and MUST NOT be derived here.
    """

    _ = field

    field_sources = source_evidence_entry.get("sources", {})
    comparable_sources = get_comparable_sources_for_field(field_sources)

    comparable_values = {}

    for source in comparable_sources:
        if source in source_values:
            comparable_values[source] = source_values[source]

    consistency_state = classify_consistency_from_values(comparable_values)

    return {
        "state": consistency_state,
        "comparable_sources": list(comparable_values.keys()),
        "source_values": comparable_values,
    }


def build_multi_source_consistency(
    source_evidence: Dict,
    source_values_by_field: Dict,
) -> Dict:
    """
    Build consistency block for all fields.

    This function must:
    - not infer values
    - not transform values
    - not introduce missing data
    """

    consistency_block = {}

    for field, evidence_entry in source_evidence.items():
        field_values = source_values_by_field.get(field, {})

        consistency_block[field] = build_field_consistency(
            field=field,
            source_evidence_entry=evidence_entry,
            source_values=field_values,
        )

    return consistency_block

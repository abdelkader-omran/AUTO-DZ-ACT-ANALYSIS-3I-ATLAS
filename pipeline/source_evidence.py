"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Pipeline Layer 6 — Source-Level Observational Evidence Grounding

Provides deterministic, source-level evidence blocks for each source-level
observational outcome.  Every source state is grounded in an explicit,
machine-readable trace structure.

This module is:
- deterministic
- additive
- non-inferential
- profile-compatible
- architecture-safe

Evidence labels are layer-local epistemic trace labels only.
They are NOT claims of source blame, scheduling failure, telescope behaviour,
or archival completeness.
"""

from typing import Dict


def build_default_evidence_block() -> Dict:
    """
    Return the default deterministic evidence block.

    This function must not infer anything.
    It must only provide the fallback minimal evidence state.
    """
    return {
        "ingested": False,
        "present_in_snapshot": False,
        "trace_type": "no_source_evidence",
    }


def build_evidence_for_source(
    field: str,
    source: str,
    source_state: str,
) -> Dict:
    """
    Return a deterministic evidence block for one source-level field outcome.

    Allowed output keys:
    - ingested
    - present_in_snapshot
    - trace_type

    Allowed trace_type values in this layer:
    - observational_evidence
    - no_detection
    - not_ingested
    - not_available
    - no_source_evidence

    Args:
        field: Field name (used for traceability; not evaluated).
        source: Source identifier (used for traceability; not evaluated).
        source_state: Observed state string for this source/field combination.

    Returns:
        A dict with keys ``ingested``, ``present_in_snapshot``, and
        ``trace_type``.

    Important:
        This rule set is an operational deterministic baseline only.
        It must NOT be interpreted as a claim of real source-specific
        archival binding.  It must NOT attempt to prove that a
        source-specific raw observation exists.
    """
    # Suppress unused-argument warnings — parameters are accepted for
    # traceability by callers even though only source_state drives the logic.
    _ = field
    _ = source

    if source_state == "observed":
        return {
            "ingested": True,
            "present_in_snapshot": True,
            "trace_type": "observational_evidence",
        }

    if source_state == "not_ingested":
        return {
            "ingested": False,
            "present_in_snapshot": False,
            "trace_type": "not_ingested",
        }

    if source_state == "not_available":
        return {
            "ingested": False,
            "present_in_snapshot": False,
            "trace_type": "not_available",
        }

    if source_state == "not_observed":
        return {
            "ingested": False,
            "present_in_snapshot": False,
            "trace_type": "no_detection",
        }

    return build_default_evidence_block()


def build_source_evidence_block(
    source_outcome_attribution: Dict,
) -> Dict:
    """
    Build the full source_evidence structure.

    Input example::

        {
          "gas_species": {
            "state": "not_ingested",
            "sources": {
              "jwst": "not_ingested",
              "alma": "not_ingested"
            }
          },
          "e": {
            "state": "observed",
            "sources": {
              "jpl_sbdb": "observed",
              "mpc": "unknown"
            }
          }
        }

    Returns a dict with the same top-level field keys.  Each field value
    retains its ``state`` entry and its ``sources`` dict is expanded so that
    every source entry becomes::

        {
          "state": "<original_source_state>",
          "evidence": { ... }
        }

    Implementation constraints:
    - Do not infer additional sources
    - Do not invent fields
    - Operate only on the existing source_outcome_attribution block
    - Keep the helper generic
    - Do not hardcode orbital field names
    - Do not hardcode source-family semantics

    Args:
        source_outcome_attribution: Dict as produced by the Layer 5B
            ``build_source_outcome_block`` function.

    Returns:
        The source_evidence structure as described above.
    """
    result: Dict = {}

    for field, field_block in source_outcome_attribution.items():
        if not isinstance(field_block, dict):
            continue

        field_state = field_block.get("state", "")
        raw_sources = field_block.get("sources", {})

        expanded_sources: Dict = {}
        for source, source_state in raw_sources.items():
            # Defensively convert non-string values to an empty string so that
            # build_evidence_for_source returns the default fallback block
            # instead of raising an exception.  Non-string values should not
            # appear in a well-formed source_outcome_attribution block, so this
            # path only activates when upstream data is malformed.
            state_str = source_state if isinstance(source_state, str) else ""
            evidence = build_evidence_for_source(field, source, state_str)
            expanded_sources[source] = {
                "state": state_str,
                "evidence": evidence,
            }

        result[field] = {
            "state": field_state,
            "sources": expanded_sources,
        }

    return result

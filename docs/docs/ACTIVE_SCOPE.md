# ACTIVE_SCOPE

Repository: AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
Layer: Layer-1
Role: Analysis (Current Active Scope)

## Scope Definition

This document defines what is considered ACTIVE inside this repository at the current stage.

Due to historical development, this repository contains multiple functional areas.
However, not all of them are currently active.

## ACTIVE

The following areas are considered ACTIVE:

- analysis-related inspection of observational data
- claim-oriented analytical structuring
- preparation of structured outputs for downstream use

## INACTIVE (or not primary responsibility)

The following areas are NOT considered active responsibilities of this repository:

- ingestion (handled by AUTO-DZ-ACT-3I-ATLAS-DAILY)
- publication (handled by trizel-site-artifacts / Layer-2)
- lab validation (handled by trizel-lab)

## RESTRICTION

No new work should:

- expand inactive areas
- reintroduce ingestion logic
- implement publication logic
- duplicate downstream responsibilities

## INTENT

The repository is transitioning toward:

- clear analysis-only responsibility
- structured outputs
- clean integration into the TRIZEL pipeline

## ENFORCEMENT

Any work outside ACTIVE scope is invalid.

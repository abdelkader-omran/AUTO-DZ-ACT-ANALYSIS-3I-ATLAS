# DATA STRUCTURE — AUTO-DZ-ACT-3I-ATLAS

## 1. Overview

This repository follows a deterministic, time-indexed observational pipeline.

Data is generated automatically and stored as immutable daily snapshots under:

observations/YYYY-MM-DD/

Each snapshot contains a complete state of the observed object at retrieval time.

## 2. Directory Structure

observations/
├── YYYY-MM-DD/
│   ├── observation.json
│   ├── normalized_observation.json
│   ├── analysis.json
│   ├── raw_sources.json
│   └── mpc_object_ingest.json (optional)

Global aggregated outputs:

observations/
├── time_series.json
├── trajectory_model.json

## 3. File Definitions

### 3.1 observation.json

Raw retrieval metadata from source API.

Contains:
- Source URL
- Retrieval timestamp (UTC)
- SHA-256 checksum
- Payload size
- Status flag

Purpose:
Ensures traceability and data integrity.

### 3.2 normalized_observation.json

Standardized representation of orbital and physical parameters.

Fields:
- identity
- orbital parameters
- physical parameters

Purpose:
Provides a consistent schema independent of source format.

### 3.3 analysis.json

Derived analytical interpretation from normalized data.

Includes:
- orbit classification (e.g. hyperbolic)
- interstellar flag
- inclination class
- derived indicators

Purpose:
Transforms raw data into structured scientific meaning.

### 3.4 raw_sources.json

Status of each upstream provider.

Example:
- jpl_sbdb → ok
- mpc → unavailable

Purpose:
Tracks availability and reliability of data sources.

### 3.5 mpc_object_ingest.json

Optional file.

Used when MPC provides object-level data.

If unavailable:
- status = unavailable
- reason documented

## 4. Time Series Structure

### 4.1 time_series.json

Aggregated multi-day dataset.

Contains:
- daily orbital snapshots
- derived analysis per day
- delta evolution between days

Purpose:
Tracks temporal stability and variation.

### 4.2 trajectory_model.json

Higher-level model derived from time series.

Purpose:
Represents long-term orbital behavior.

## 5. Data Characteristics

- Immutable daily snapshots
- Deterministic pipeline execution
- Full provenance tracking (SHA-256)
- Source-aware ingestion
- Explicit handling of missing data

## 6. Key Observational Properties (3I/ATLAS case)

Observed characteristics:
- Orbit class: hyperbolic
- Interstellar: true
- Semi-major axis: negative
- Inclination: retrograde (~175°)
- High hyperbolic excess

Stability:
- No variation across observed days
- All deltas = 0

## 7. Design Principles

- No manual intervention
- No hidden transformations
- All stages explicitly stored
- Reproducibility by design
- Separation between:
  - raw data
  - normalized data
  - analysis

## 8. Interpretation Boundary

This repository stores:
- Observations
- Transformations
- Derived indicators

It does NOT enforce:
- Scientific conclusions
- Theoretical interpretations

Interpretation remains external.

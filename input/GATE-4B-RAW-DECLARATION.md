# GATE 4B: RAW Input Declaration
**Project:** 3I / Atlas  
**Repository:** AUTO-DZ-ACT-ANALYSIS-3I-ATLAS  
**Layer:** Layer-1 (Lab / Analysis)  
**Prepared by:** trizel-admin  
**Declaration date:** 2026-01-27  
**STATUS:** PRE-EXECUTION / NO ANALYSIS

---

## 1. Data Sources

- **Origin:** [EXPLICITLY STATE ORIGINS HERE; e.g., "Lab Instrument XYZ, Data Lake Bucket, SFTP: institutional-server/data/YYYYMMDD/"]
- **Format:** [EXPLICIT FILE FORMATS; e.g., "CSV", "NetCDF", "HDF5", "proprietary .dat"]
- **Access Method:** [E.g., "Direct filesystem read", "S3 API", "SCP transfer", "manual upload by operator"]

## 2. Time Range Covered

- **Earliest Data Timestamp:** [YYYY-MM-DDTHH:MM:SS±ZZZZ]
- **Latest Data Timestamp:** [YYYY-MM-DDTHH:MM:SS±ZZZZ]
- **Acquisition Window:** [E.g., "Monitored batch, run window: 2025-12-12T08:00Z — 2026-01-16T18:00Z"]

## 3. Acquisition Method

- **Process:** [Describe HOW data arrived: E.g., "Lab-instrument scheduled export," "Automated ETL (pipeline_id:xyz-1234)," or "Manual drop, operator ID: j.smith"]
- **Controls:** [State controls if any: E.g., "Operator badge required for collection," "Checksum at ingest", "Preliminary validation script run"]

## 4. Integrity Checks

- **Hash/Checksum:** [Document raw data hashes if available: E.g., "SHA256: bcae..."]
- **Validation:** [Describe sanity checks, schema validation, or parsing tests performed at collection time]
- **Storage Location:** [Immutable object store, path or bucket; e.g., "S3://trizel-3i-atlas-layer1/raw/202601/"]

## 5. Provenance Statement

> Data originated from [ORIGIN] and was acquired on [DATE/TIME] by [MEANS].  
> At no stage prior to Gate 4B preparation was the data altered, transformed, or processed by this repository or any derivative workflow.  
> Prepared by: trizel-admin on 2026-01-27  
> Source logs and controls stored at [location; e.g., “/logs/acquisition/YYYYMMDD/”].  
> Diagnostic checks and hashes available in auxiliary record [reference or file].

---

**NOTE:**  
- This document explicitly declares ONLY the RAW input dataset.  
- No analysis, transformation, or result generation has been performed.  
- All details subject to direct audit via access logs and storage records.

**LABEL:** PRE-EXECUTION / NO ANALYSIS  

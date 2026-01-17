#!/usr/bin/env python3
"""
AUTO-DZ-ACT-ANALYSIS-3I-ATLAS
TASK 001 — Minimal State Table Generator

Reads:
- input/observables.json
- one snapshot JSON (from AUTO-DZ-ACT-3I-ATLAS-DAILY)
Writes:
- outputs/state_tables/state_table_YYYY-MM-DD.csv (or user --out)

Deterministic selection by authority_rank.
Enforces tolerances: epsilon, delta, time_window_days.
Emits states:
- NON_COMPARABLE
- INFTY_OVER_INFTY
- ZERO_OVER_ZERO
- D0_OVER_DZ
- DZ
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


STATE_NON_COMPARABLE = "NON_COMPARABLE"
STATE_INFTY_OVER_INFTY = "INFTY_OVER_INFTY"
STATE_ZERO_OVER_ZERO = "ZERO_OVER_ZERO"
STATE_D0_OVER_DZ = "D0_OVER_DZ"
STATE_DZ = "DZ"


def _parse_iso_datetime(s: Optional[str]) -> Optional[dt.datetime]:
    if not s:
        return None
    s = s.strip()
    # Accept "Z" suffix
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def _safe_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return float(x)
    if isinstance(x, str):
        x2 = x.strip()
        if not x2:
            return None
        try:
            return float(x2)
        except ValueError:
            return None
    return None


def _is_finite_number(x: Any) -> bool:
    v = _safe_float(x)
    return v is not None and math.isfinite(v)


def _vectorize(value: Any) -> Optional[List[float]]:
    """
    Converts scalar or list/object into a vector for distance calculations.
    Supported:
    - number -> [number]
    - [n1, n2, ...]
    - {"min_km": a, "max_km": b} or {"min": a, "max": b}
    - {"A1": a, "A2": b, "A3": c} (any numeric-valued dict; sorted keys)
    """
    if value is None:
        return None

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)):
            return [float(value)]
        return None

    if isinstance(value, str):
        v = _safe_float(value)
        if v is None or not math.isfinite(v):
            return None
        return [v]

    if isinstance(value, list):
        out: List[float] = []
        for item in value:
            fv = _safe_float(item)
            if fv is None or not math.isfinite(fv):
                return None
            out.append(fv)
        return out if out else None

    if isinstance(value, dict):
        # Special-case bounds
        keys = set(value.keys())
        if {"min_km", "max_km"}.issubset(keys):
            a = _safe_float(value.get("min_km"))
            b = _safe_float(value.get("max_km"))
            if a is None or b is None:
                return None
            return [a, b]
        if {"min", "max"}.issubset(keys):
            a = _safe_float(value.get("min"))
            b = _safe_float(value.get("max"))
            if a is None or b is None:
                return None
            return [a, b]

        # Generic numeric dict vector (stable order by key)
        items: List[Tuple[str, float]] = []
        for k in sorted(value.keys()):
            fv = _safe_float(value.get(k))
            if fv is None or not math.isfinite(fv):
                # If any component is non-numeric, treat as non-vectorizable
                return None
            items.append((k, fv))
        return [v for _, v in items] if items else None

    return None


def _distance_abs(tv: List[float], ev: List[float]) -> float:
    if len(tv) != len(ev):
        return float("inf")
    return max(abs(t - e) for t, e in zip(tv, ev))


def _distance_relative(tv: List[float], ev: List[float]) -> float:
    """
    Relative distance: max(|T-E| / max(|E|, tiny))
    """
    if len(tv) != len(ev):
        return float("inf")
    tiny = 1e-12
    ratios = []
    for t, e in zip(tv, ev):
        denom = max(abs(e), tiny)
        ratios.append(abs(t - e) / denom)
    return max(ratios) if ratios else float("inf")


def _distance_l2(tv: List[float], ev: List[float]) -> float:
    if len(tv) != len(ev):
        return float("inf")
    s = 0.0
    for t, e in zip(tv, ev):
        d = t - e
        s += d * d
    return math.sqrt(s)


def compute_distance(metric: str, t_val: Any, e_val: Any) -> Optional[float]:
    tv = _vectorize(t_val)
    ev = _vectorize(e_val)
    if tv is None or ev is None:
        return None
    if metric == "abs":
        return _distance_abs(tv, ev)
    if metric == "relative":
        return _distance_relative(tv, ev)
    if metric == "L2":
        return _distance_l2(tv, ev)
    return None


@dataclass(frozen=True)
class ObservableSpec:
    obs_id: str
    unit: str
    sources_allowed: List[str]
    authority_rank: List[str]
    epsilon: float
    delta: float
    time_window_days: float
    distance_metric: str
    description: str = ""


@dataclass(frozen=True)
class Measurement:
    obs_id: str
    value: Any
    unit: Optional[str]
    source_id: Optional[str]
    retrieved_utc: Optional[str]
    raw_path: Optional[str]
    measurement_sha256: Optional[str]
    epoch_utc: Optional[str]  # optional measurement epoch


def load_observables(observables_path: Path) -> List[ObservableSpec]:
    data = json.loads(observables_path.read_text(encoding="utf-8"))
    obs_list = data.get("observables", [])
    out: List[ObservableSpec] = []
    for o in obs_list:
        tol = o.get("tolerances", {})
        out.append(
            ObservableSpec(
                obs_id=o["id"],
                unit=o["unit"],
                sources_allowed=list(o.get("sources_allowed", [])),
                authority_rank=list(o.get("authority_rank", o.get("sources_allowed", []))),
                epsilon=float(tol["epsilon"]),
                delta=float(tol["delta"]),
                time_window_days=float(tol["time_window_days"]),
                distance_metric=str(tol["distance_metric"]),
                description=str(o.get("description", "")),
            )
        )
    return out


def _extract_snapshot_provenance(snapshot: Dict[str, Any]) -> Dict[str, Optional[str]]:
    return {
        "snapshot_sha256": snapshot.get("snapshot_sha256") or snapshot.get("sha256") or snapshot.get("checksum"),
        "snapshot_date": snapshot.get("snapshot_date") or snapshot.get("date") or snapshot.get("as_of_date"),
    }


def _iter_measurements_from_snapshot(snapshot: Dict[str, Any]) -> Iterable[Measurement]:
    """
    Supports:
    A) snapshot["observables"] = { "eccentricity": {...}, ... }
       where each value may include:
       - value
       - unit
       - source_id
       - retrieved_utc
       - raw_path
       - measurement_sha256
       - epoch_utc
    B) snapshot["measurements"] = [ {id/value/unit/source_id/...}, ... ]
    """
    if isinstance(snapshot.get("observables"), dict):
        for obs_id, rec in snapshot["observables"].items():
            if not isinstance(rec, dict):
                rec = {"value": rec}
            yield Measurement(
                obs_id=str(obs_id),
                value=rec.get("value"),
                unit=rec.get("unit"),
                source_id=rec.get("source_id") or rec.get("source"),
                retrieved_utc=rec.get("retrieved_utc") or rec.get("retrieved"),
                raw_path=rec.get("raw_path") or rec.get("path"),
                measurement_sha256=rec.get("measurement_sha256") or rec.get("sha256"),
                epoch_utc=rec.get("epoch_utc") or rec.get("epoch"),
            )
        return

    if isinstance(snapshot.get("measurements"), list):
        for rec in snapshot["measurements"]:
            if not isinstance(rec, dict):
                continue
            obs_id = rec.get("id") or rec.get("observable_id") or rec.get("name")
            if not obs_id:
                continue
            yield Measurement(
                obs_id=str(obs_id),
                value=rec.get("value"),
                unit=rec.get("unit"),
                source_id=rec.get("source_id") or rec.get("source"),
                retrieved_utc=rec.get("retrieved_utc") or rec.get("retrieved"),
                raw_path=rec.get("raw_path") or rec.get("path"),
                measurement_sha256=rec.get("measurement_sha256") or rec.get("sha256"),
                epoch_utc=rec.get("epoch_utc") or rec.get("epoch"),
            )
        return


def select_measurement(
    spec: ObservableSpec,
    candidates: List[Measurement],
    snapshot_ref_time: Optional[dt.datetime],
) -> Optional[Measurement]:
    """
    Deterministic selection:
    1) Filter sources_allowed (if provided)
    2) Rank by authority_rank (first match)
    3) If multiple in same rank: choose closest by epoch_utc (if available) else by retrieved_utc else stable sort
    """
    if spec.sources_allowed:
        candidates = [m for m in candidates if (m.source_id in spec.sources_allowed) or (m.source_id is None)]
        # If all have source_id and none allowed -> empty
        if not candidates:
            return None

    # Group by authority rank index
    rank_index: Dict[str, int] = {s: i for i, s in enumerate(spec.authority_rank)}
    def _rk(m: Measurement) -> int:
        if m.source_id is None:
            # If source unknown, treat as lowest priority
            return 10_000
        return rank_index.get(m.source_id, 9_999)

    # Time closeness
    def _time_delta_days(m: Measurement) -> float:
        # prefer epoch_utc if snapshot_ref_time exists
        if snapshot_ref_time:
            t = _parse_iso_datetime(m.epoch_utc) or _parse_iso_datetime(m.retrieved_utc)
            if t:
                return abs((t - snapshot_ref_time).total_seconds()) / 86400.0
        return float("inf")

    # Stable deterministic key
    def _stable_key(m: Measurement) -> Tuple[int, float, str, str]:
        return (
            _rk(m),
            _time_delta_days(m),
            str(m.retrieved_utc or ""),
            str(m.raw_path or ""),
        )

    candidates_sorted = sorted(candidates, key=_stable_key)
    if not candidates_sorted:
        return None

    # Enforce time window (only if we can compute it)
    chosen = candidates_sorted[0]
    if snapshot_ref_time:
        t = _parse_iso_datetime(chosen.epoch_utc) or _parse_iso_datetime(chosen.retrieved_utc)
        if t:
            days = abs((t - snapshot_ref_time).total_seconds()) / 86400.0
            if days > spec.time_window_days:
                return None

    return chosen


def compute_state(spec: ObservableSpec, t_pred: Any, e_obs: Any) -> Tuple[str, Optional[float]]:
    """
    State rules:
    - If both T and E not comparable (missing/undefined/units mismatch): INFTY_OVER_INFTY
    - If only one missing: NON_COMPARABLE
    - Else compute D via metric:
        if D <= epsilon: ZERO_OVER_ZERO
        elif D <= delta: D0_OVER_DZ
        else: DZ
    """
    # Missing / undefined
    t_missing = t_pred is None
    e_missing = e_obs is None

    # Unit mismatch is treated as non-comparable at this minimal layer.
    # (Unit harmonization can be introduced later as an explicit normalization stage.)
    if t_missing and e_missing:
        return (STATE_INFTY_OVER_INFTY, None)
    if t_missing or e_missing:
        return (STATE_NON_COMPARABLE, None)

    d = compute_distance(spec.distance_metric, t_pred, e_obs)
    if d is None or not math.isfinite(d):
        # Value exists but can't be compared numerically
        return (STATE_NON_COMPARABLE, None)

    if d <= spec.epsilon:
        return (STATE_ZERO_OVER_ZERO, d)
    if d <= spec.delta:
        return (STATE_D0_OVER_DZ, d)
    return (STATE_DZ, d)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True, help="Path to snapshot JSON (from DAILY repo).")
    ap.add_argument("--observables", required=True, help="Path to input/observables.json")
    ap.add_argument("--out", required=True, help="Output CSV path")
    ap.add_argument("--theory", default=None, help="Optional path to theoretical predictions JSON {id: value} or {predictions:{id:value}}.")
    args = ap.parse_args()

    snapshot_path = Path(args.snapshot)
    observables_path = Path(args.observables)
    out_path = Path(args.out)

    if not snapshot_path.exists():
        print(f"ERROR: snapshot not found: {snapshot_path}", file=sys.stderr)
        return 2
    if not observables_path.exists():
        print(f"ERROR: observables not found: {observables_path}", file=sys.stderr)
        return 2

    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    prov = _extract_snapshot_provenance(snapshot)

    # Reference time for time_window enforcement: snapshot_date if parseable, else now-UTC
    snapshot_ref_time = _parse_iso_datetime(snapshot.get("snapshot_utc") or snapshot.get("snapshot_time_utc") or snapshot.get("snapshot_time"))
    if snapshot_ref_time is None:
        sd = prov.get("snapshot_date")
        snapshot_ref_time = _parse_iso_datetime(sd) if isinstance(sd, str) else None

    # Load theory predictions (optional)
    theory_map: Dict[str, Any] = {}
    if args.theory:
        theory_path = Path(args.theory)
        if not theory_path.exists():
            print(f"ERROR: theory file not found: {theory_path}", file=sys.stderr)
            return 2
        tdata = json.loads(theory_path.read_text(encoding="utf-8"))
        if isinstance(tdata, dict) and "predictions" in tdata and isinstance(tdata["predictions"], dict):
            theory_map = tdata["predictions"]
        elif isinstance(tdata, dict):
            theory_map = tdata
        else:
            print("ERROR: theory JSON must be an object", file=sys.stderr)
            return 2

    specs = load_observables(observables_path)

    # Index snapshot measurements by obs_id
    snap_meas: Dict[str, List[Measurement]] = {}
    for m in _iter_measurements_from_snapshot(snapshot):
        snap_meas.setdefault(m.obs_id, []).append(m)

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Build rows
    rows: List[Dict[str, Any]] = []
    for spec in specs:
        meas_list = snap_meas.get(spec.obs_id, [])
        chosen_meas = select_measurement(spec, meas_list, snapshot_ref_time)

        e_val = chosen_meas.value if chosen_meas else None
        t_val = theory_map.get(spec.obs_id)

        state, dist = compute_state(spec, t_val, e_val)

        row = {
            "observable_id": spec.obs_id,
            "unit": spec.unit,
            "state": state,
            "distance": dist if dist is not None else "",
            "theory_value": t_val if t_val is not None else "",
            "empirical_value": e_val if e_val is not None else "",
            "empirical_source_id": chosen_meas.source_id if chosen_meas else "",
            "empirical_retrieved_utc": chosen_meas.retrieved_utc if chosen_meas else "",
            "empirical_epoch_utc": chosen_meas.epoch_utc if chosen_meas else "",
            "snapshot_sha256": prov.get("snapshot_sha256") or "",
            "snapshot_date": prov.get("snapshot_date") or "",
        }
        rows.append(row)

    # Write CSV
    fieldnames = [
        "observable_id",
        "unit",
        "state",
        "distance",
        "theory_value",
        "empirical_value",
        "empirical_source_id",
        "empirical_retrieved_utc",
        "empirical_epoch_utc",
        "snapshot_sha256",
        "snapshot_date",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"State table written: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

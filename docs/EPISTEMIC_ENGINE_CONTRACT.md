# Epistemic Engine — Frozen Execution Contract

Repository: AUTO-DZ-ACT-ANALYSIS-3I-ATLAS  
Component: `scripts/epistemic_engine.py`  
Helper package: `scripts/__init__.py`  
Status: **FROZEN** — inspection-backed, no execution changes permitted

---

## Scope

This document freezes the verified execution contract of
`scripts/epistemic_engine.py` as determined by direct inspection of
`scripts/__init__.py` and `scripts/epistemic_engine.py`.

No workflow changes, execution changes, automation, or architectural
modifications are introduced by this document.

---

## 1. Entry Mode

**Verified canonical entry mode:**

```
python scripts/epistemic_engine.py --observation-root <path>
```

Executed from the repository root so that the `scripts` package is importable.

The `if __name__ == "__main__": sys.exit(main())` guard at the bottom of
`scripts/epistemic_engine.py` is the only verified execution entry point.

**Module mode** (`python -m scripts.epistemic_engine`) is **not canonically
verified**.  No `scripts/__main__.py` exists.  Direct file execution remains
the only confirmed execution mode.

---

## 2. CLI Contract

| Argument             | Required | Type   | Description |
|----------------------|----------|--------|-------------|
| `--observation-root` | Yes      | string | Path to the per-date observation directory |

The argument is registered by `scripts.__init__.add_observation_root_arg`:

```python
ap.add_argument(
    "--observation-root",
    required=True,
    help="Path to the per-date observation directory " + help_detail,
)
```

`argparse` handles the missing-argument case: if `--observation-root` is
absent, `argparse` prints its own usage error to stderr and exits with code 2
before `parse_and_resolve_observation_root` is reached.

---

## 3. Input Path Contract

Path resolution is performed by `scripts.__init__.parse_and_resolve_observation_root`:

```python
path = Path(args.observation_root).resolve()
```

- **Absolute or relative**: both accepted; relative paths are resolved against
  the process current working directory at invocation time.
- **Symlink behaviour**: `Path.resolve()` follows symlinks to the real path.
- **Existence requirement**: the resolved path must exist and must be a
  directory.  Plain files are rejected (see §5).

### Source files read from the observation root

| Source key  | Filename                   | Behaviour when absent |
|-------------|----------------------------|-----------------------|
| `jpl_sbdb`  | `normalized_observation.json` | silently skipped   |
| `mpc`       | `mpc_normalized.json`      | silently skipped       |

Files that fail JSON or UTF-8 decoding are also silently skipped.  Absence of
any or all source files is not a CLI error; it affects the epistemic
classification output only.

---

## 4. Output Path Contract

| Item           | Value |
|----------------|-------|
| Output file    | `<observation_root>/epistemic_state.json` |
| Encoding       | UTF-8 |
| JSON indent    | 2 spaces |
| Line ending    | single trailing newline (`\n`) |
| Directory creation | `mkdir(parents=True, exist_ok=True)` — created if absent |

The output record schema written to `epistemic_state.json`:

```json
{
  "object": "3I/ATLAS",
  "sources": ["<source_key>", "..."],
  "parameters": { "<source_key>": { "e": null, "a": null, "i": null, "q": null } },
  "comparison": null,
  "temporal_consistency": "<temporal_state_or_null>",
  "epistemic_state": "<state>",
  "confidence": "<confidence>"
}
```

Possible `epistemic_state` values:

| Value | Condition |
|-------|-----------|
| `insufficient_data` | Fewer than 2 sources, or no comparable parameters |
| `consensus` | All non-null cross-source deltas are exactly 0 |
| `divergence` | At least one non-null cross-source delta > 0 |
| `single_source_no_history` | Single source, no previous day record |
| `single_source_temporally_stable` | Single source, all four parameters unchanged |
| `single_source_temporally_evolved` | Single source, at least one parameter changed |

---

## 5. Error Behavior of `parse_and_resolve_observation_root`

Function signature (from `scripts/__init__.py`):

```python
def parse_and_resolve_observation_root(
    ap: argparse.ArgumentParser,
) -> Tuple[Optional[Path], int]:
```

| Condition | Return value | stderr message | Exit code |
|-----------|-------------|---------------|-----------|
| Resolved path is an existing directory | `(path, 0)` | none | 0 |
| Resolved path does not exist or is not a directory | `(None, 2)` | `ERROR: --observation-root not found or not a directory: <resolved_path>` | 2 |
| `--observation-root` missing from argv (argparse) | n/a — argparse exits before this function runs | argparse usage error | 2 |

The CLI `main()` function propagates the integer code directly to
`sys.exit(main())`, so the process exit code equals the return value.

---

## 6. Integration Path

For programmatic (non-CLI) use, the canonical integration entry point is:

```python
from scripts.epistemic_engine import run_for_date
from pathlib import Path

record = run_for_date(Path("observations/2026-03-18"))
# writes: observations/2026-03-18/epistemic_state.json
# returns: the dict that was written
```

`run_for_date` does **not** validate that the directory exists before writing;
it calls `observation_root.mkdir(parents=True, exist_ok=True)` and then
writes the output.  Callers are responsible for ensuring source files are
present before invoking `run_for_date`.

Documented integration pattern (from `epistemic_engine.py` module docstring):

```
Integration (run_for_date pattern):
  from scripts.epistemic_engine import run_for_date
  run_for_date(observation_root)
```

---

## 7. Inspection Basis

This contract was derived by direct static inspection of:

- `scripts/__init__.py` — `add_observation_root_arg`, `parse_and_resolve_observation_root`
- `scripts/epistemic_engine.py` — `main()`, `run_for_date()`, `build_epistemic_record()`, `load_sources()`

No execution was performed.  No code was modified.  This document reflects the
state of those files at the time of inspection and is authoritative as a
frozen reference.

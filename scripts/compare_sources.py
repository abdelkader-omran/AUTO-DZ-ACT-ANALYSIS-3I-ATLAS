import json
from pathlib import Path

BASE_PATH = Path("data/observations")


def load_json(path):
    with open(path, "r") as f:
        return json.load(f)


def compare_sources(date):
    day_path = BASE_PATH / date

    normalized_path = day_path / "normalized_observation.json"
    mpc_path = day_path / "mpc_object_ingest.json"
    raw_sources_path = day_path / "raw_sources.json"

    print(f"\n=== Comparing sources for {date} ===")

    if normalized_path.exists():
        normalized = load_json(normalized_path)
        print("\n[JPL_SBDB]")
        print(f"Object: {normalized.get('object')}")
        print(f"Eccentricity: {normalized['orbital'].get('eccentricity')}")
        print(f"Inclination: {normalized['orbital'].get('inclination')}")
        print(f"Semi-major axis: {normalized['orbital'].get('semi_major_axis')}")
    else:
        print("\n[JPL_SBDB] Missing")

    if mpc_path.exists():
        mpc = load_json(mpc_path)
        print("\n[MPC]")
        print(f"Status: {mpc.get('status')}")
        print(f"Reason: {mpc.get('reason')}")
    else:
        print("\n[MPC] File not found")

    if raw_sources_path.exists():
        raw = load_json(raw_sources_path)
        print("\n[RAW SOURCES STATUS]")
        for src in raw.get("sources", []):
            print(f"{src['source']} → {src['status']}")
    else:
        print("\n[RAW SOURCES] Missing")


if __name__ == "__main__":
    # Example: latest available date
    compare_sources("2026-03-21")

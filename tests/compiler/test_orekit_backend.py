import json
from pathlib import Path

import pytest

from compiler.artifacts.bundle import compile_bundle, validate_mission
from compiler.backends.registry import get_backend


def _orekit_two_body_spec() -> dict:
    return {
        "schema_version": "1.0.0",
        "mission_id": "orekit_two_body",
        "mission_name": "Orekit Two Body",
        "conventions": {
            "time_scale": "UTC",
            "distance_unit": "km",
            "velocity_unit": "km/s",
            "angle_unit": "deg",
            "mass_unit": "kg",
            "time_format": "ISO-8601",
        },
        "spacecraft": [
            {
                "id": "sat",
                "name": "OrekitSat",
                "epoch": "2026-01-01T00:00:00Z",
                "frame": "EarthMJ2000Eq",
                "state_type": "keplerian",
                "sma_km": 7000.0,
                "ecc": 0.001,
                "inc_deg": 28.5,
                "raan_deg": 10.0,
                "aop_deg": 20.0,
                "ta_deg": 30.0,
                "dry_mass_kg": 1000.0,
            }
        ],
        "force_models": [
            {
                "id": "earth_two_body",
                "name": "EarthTwoBody",
                "central_body": "Earth",
                "gravity": {"type": "point_mass"},
            }
        ],
        "propagators": [
            {
                "id": "prop",
                "name": "OrekitProp",
                "force_model": "earth_two_body",
                "integrator": "RungeKutta89",
                "accuracy": 1e-9,
                "initial_step_s": 30.0,
                "min_step_s": 0.1,
                "max_step_s": 300.0,
            }
        ],
        "mission_sequence": [
            {
                "phase_id": "coast",
                "name": "Coast",
                "steps": [
                    {
                        "step_id": "coast_10_min",
                        "type": "propagate",
                        "spacecraft": "sat",
                        "propagator": "prop",
                        "duration_s": 600.0,
                    }
                ],
            }
        ],
        "outputs": [
            {
                "id": "ephem",
                "type": "spacecraft_ephemeris",
                "spacecraft": "sat",
                "frames": ["EarthMJ2000Eq"],
                "state_groups": ["elapsed_time", "cartesian"],
                "path_template": "outputs/_Ephemeris_{spacecraft}_{frame}.csv",
            }
        ],
    }


def test_orekit_backend_compiles_two_body_runner(tmp_path: Path) -> None:
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(_orekit_two_body_spec()), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    compile_result = result["compile_result"]
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "simulation" / "artifact_manifest.json").read_text(encoding="utf-8"))

    assert compile_result["status"] == "success"
    assert compile_result["backend_id"] == "orekit"
    assert "OREKIT_DATA_PATH" in script
    assert "KeplerianPropagator" in script
    assert "--no-save-script" in script
    assert '"backend": "orekit"' in json.dumps(manifest)


def test_orekit_backend_rejects_unsupported_maneuvers() -> None:
    spec = _orekit_two_body_spec()
    spec["burns"] = [{"id": "dv", "name": "DV", "type": "impulsive", "frame": "VNB", "delta_v_km_s": [0.1, 0.0, 0.0]}]
    spec["mission_sequence"][0]["steps"].insert(0, {"step_id": "burn", "type": "maneuver", "spacecraft": "sat", "burn": "dv"})

    report = validate_mission(spec, "orekit")

    assert report["status"] == "failed"
    assert "does not yet support burn" in report["errors"][0]


def test_orekit_backend_is_registered() -> None:
    assert get_backend("orekit").backend_id == "orekit"
    assert get_backend("OREKIT").backend_id == "orekit"

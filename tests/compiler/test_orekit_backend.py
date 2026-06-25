import json
import os
from pathlib import Path
import subprocess
import sys

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
    assert f'{{sc_name}}.{{central_body}}.SMA' in script
    assert f'{{sc_name}}.{{frame_name}}.INC' in script
    assert "--no-save-script" in script
    assert '"backend": "orekit"' in json.dumps(manifest)


def test_orekit_backend_accepts_direct_impulsive_maneuver_steps() -> None:
    spec = _orekit_two_body_spec()
    spec["burns"] = [{"id": "dv", "name": "DV", "type": "impulsive", "frame": "VNB", "delta_v_km_s": [0.1, 0.0, 0.0]}]
    spec["mission_sequence"][0]["steps"].insert(0, {"step_id": "burn", "type": "maneuver", "spacecraft": "sat", "burn": "dv"})

    report = validate_mission(spec, "orekit")

    assert report["status"] == "passed"


def test_orekit_backend_renders_runtime_spec_as_python_safe_json(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["visualization"] = {"enabled": True, "clean_csv": False}
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    assert "RUNTIME_SPEC = json.loads" in script
    assert '"enabled": true' in script


def test_orekit_compile_writes_visualization_manifest_with_static_body_context(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["reference_frames"] = [
        {
            "id": "earth_mj2000eq",
            "name": "EarthMJ2000Eq",
            "origin": "Earth",
            "axes": "MJ2000Eq",
            "orientation": "MJ2000Eq",
            "type": "body_inertial_equatorial",
        }
    ]
    spec["outputs"][0]["frames"] = ["EarthMJ2000Eq", "EarthFixed"]
    spec["outputs"].append(
        {
            "id": "earth_ground_track",
            "type": "ground_track",
            "spacecraft": "sat",
            "body": "Earth",
            "path": "outputs/_GroundTrack_{spacecraft}_{body}.csv",
        }
    )
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    manifest = json.loads((tmp_path / "simulation" / "visualization_manifest.json").read_text(encoding="utf-8"))
    runtime_script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    frames = {entry["name"]: entry for entry in manifest["frames"]}
    ephemeris_frames = {entry["frame"] for entry in manifest["spacecraft_ephemerides"]}
    ground_tracks = manifest["ground_tracks"]

    assert "Earth" in manifest["force_model_bodies"]
    assert frames["EarthMJ2000Eq"]["origin"] == "Earth"
    assert frames["EarthFixed"]["origin"] == "Earth"
    assert frames["EarthFixed"]["axes"] == "BodyFixed"
    assert ephemeris_frames == {"EarthMJ2000Eq", "EarthFixed"}
    assert ground_tracks
    assert ground_tracks[0]["file"] == "outputs/_GroundTrack_OrekitSat_Earth.csv"
    assert "_Ephemeris_OrekitSat_EarthFixed.csv" in runtime_script
    assert "_GroundTrack_OrekitSat_Earth.csv" in runtime_script
    assert "getITRF" in runtime_script
    assert '"mode": "frame_fallback"' in runtime_script


def test_orekit_backend_is_registered() -> None:
    assert get_backend("orekit").backend_id == "orekit"
    assert get_backend("OREKIT").backend_id == "orekit"


def test_generated_orekit_runner_executes_when_runtime_is_available(tmp_path: Path) -> None:
    if not os.environ.get("OREKIT_DATA_PATH"):
        pytest.skip("OREKIT_DATA_PATH is not set")
    try:
        import jpype  # noqa: F401
        import orekit_jpype  # noqa: F401
    except Exception as exc:
        pytest.skip(f"Orekit JPype runtime is unavailable: {exc}")

    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(_orekit_two_body_spec()), encoding="utf-8")
    out_dir = tmp_path / "simulation"
    compile_bundle(spec_path, out_dir, "orekit")

    proc = subprocess.run(
        [sys.executable, str(out_dir / "generated_mission.py"), "--run"],
        cwd=out_dir,
        text=True,
        capture_output=True,
        timeout=120,
    )

    ephemeris = out_dir / "outputs" / "_Ephemeris_OrekitSat_EarthMJ2000Eq.csv"
    report = out_dir / "outputs" / "_OrekitBackendReport.json"
    assert proc.returncode == 0, proc.stderr
    assert ephemeris.exists()
    assert report.exists()
    lines = ephemeris.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("OrekitSat.ElapsedSecs,OrekitSat.EarthMJ2000Eq.X")
    assert len(lines) > 2

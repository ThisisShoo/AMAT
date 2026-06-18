from pathlib import Path
import json

import pytest

from mission_compiler.artifacts.bundle import compile_bundle
from mission_compiler.io import read_json
from mission_compiler.ir.canonicalize import canonicalize
from mission_compiler.validation.validate_bounds import validate_bounds
from mission_compiler.validation.validate_dependencies import validate_dependencies
from mission_compiler.validation.validate_schema import validate_schema
from mission_compiler.visualization import build_visualization_manifest


EXAMPLES = [
    Path("examples/elliptical_LEO_to_GEO/mission_spec.json"),
    Path("examples/cislunar_demo/mission_spec.json"),
    Path("examples/MEO_demo/mission_spec.json"),
]


def _validate(path: Path) -> dict:
    validate_schema(read_json(path))
    spec = canonicalize(read_json(path))
    checks = []
    checks += validate_dependencies(spec)
    checks += validate_bounds(spec)
    failures = [c for c in checks if c.get("status") != "passed"]
    assert failures == []
    return spec


@pytest.mark.parametrize("path", EXAMPLES)
def test_demonstration_examples_validate_and_compile(path: Path, tmp_path: Path) -> None:
    _validate(path)
    result = compile_bundle(path, tmp_path / path.parent.name, "gmat")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    assert (tmp_path / path.parent.name / "generated_mission.py").exists()
    assert (tmp_path / path.parent.name / "generated_mission.script").exists()


def test_meo_demo_manifest_lists_ground_track(tmp_path: Path) -> None:
    spec_path = Path("examples/MEO_demo/mission_spec.json")
    spec = _validate(spec_path)
    result = compile_bundle(spec_path, tmp_path / "MEO_demo", "gmat")
    assert result["compile_result"]["status"] == "success"

    manifest = build_visualization_manifest(spec, tmp_path / "MEO_demo")

    assert manifest["ground_tracks"]
    assert manifest["ground_tracks"][0]["file"] == "outputs/_GroundTrack_MeoDemoSat_Earth.csv"
    assert manifest["sources"]["ground_tracks"][0]["provider"] == "gmat"


def test_targeting_generated_geo_manifest_lists_ground_track(tmp_path: Path) -> None:
    from mission_targeting.domain import canonicalize_target_problem
    from mission_targeting.initial_guess import generate_hohmann_candidate
    from mission_targeting.materialization import materialize_mission_spec

    problem = canonicalize_target_problem(read_json(Path("examples/elliptical_LEO_to_GEO/target_problem.json")))
    candidate = generate_hohmann_candidate(problem)
    spec = canonicalize(materialize_mission_spec(problem, candidate))
    spec_path = tmp_path / "candidate_mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    result = compile_bundle(spec_path, tmp_path / "elliptical_LEO_to_GEO", "gmat")
    assert result["compile_result"]["status"] == "success", result["compile_result"]

    manifest = build_visualization_manifest(spec, tmp_path / "elliptical_LEO_to_GEO")

    assert manifest["ground_tracks"]
    assert manifest["ground_tracks"][0]["file"] == "outputs/_GroundTrack_TargetSat_Earth.csv"
    assert manifest["sources"]["ground_tracks"][0]["provider"] == "gmat"
    frames = {entry["frame"] for entry in manifest["spacecraft_ephemerides"]}
    assert frames == {"EarthMJ2000Eq", "EarthFixed"}


def test_cislunar_manifest_exposes_rotating_frame_bodies(tmp_path: Path) -> None:
    spec_path = Path("examples/cislunar_demo/mission_spec.json")
    spec = _validate(spec_path)
    manifest = build_visualization_manifest(spec, tmp_path / "cislunar_demo")

    earth_luna = next(f for f in manifest["frames"] if f["name"] == "EarthLunaRotating")
    luna_earth = next(f for f in manifest["frames"] if f["name"] == "LunaEarthRotating")

    assert earth_luna["primary"] == "Earth"
    assert earth_luna["secondary"] == "Luna"
    assert luna_earth["primary"] == "Luna"
    assert luna_earth["secondary"] == "Earth"
    assert {"Earth", "Luna", "Sun"}.issubset(set(manifest["force_model_bodies"]))
    body_ephemerides = {(entry["body"], entry["frame"], entry["source"]) for entry in manifest["body_ephemerides"]}
    assert ("Sun", "EarthMJ2000Eq", "gmat") in body_ephemerides
    assert ("Sun", "EarthLunaRotating", "gmat") in body_ephemerides
    assert ("Luna", "EarthLunaRotating", "gmat") in body_ephemerides
    assert ("Earth", "LunaEarthRotating", "gmat") in body_ephemerides


def test_cislunar_compile_requests_force_model_body_ephemerides_from_gmat(tmp_path: Path) -> None:
    spec_path = Path("examples/cislunar_demo/mission_spec.json")
    result = compile_bundle(spec_path, tmp_path / "cislunar_demo", "gmat")
    assert result["compile_result"]["status"] == "success", result["compile_result"]

    script = (tmp_path / "cislunar_demo" / "generated_mission.script").read_text(encoding="utf-8")

    assert "Sun.EarthMJ2000Eq.X" in script
    assert "Sun.EarthLunaRotating.X" in script
    assert "Luna.EarthLunaRotating.X" in script
    assert "Earth.LunaEarthRotating.X" in script


def test_leo_to_geo_initial_coast_is_event_driven_before_transfer_injection(tmp_path: Path) -> None:
    spec_path = Path("examples/elliptical_LEO_to_GEO/mission_spec.json")
    result = compile_bundle(spec_path, tmp_path / "elliptical_LEO_to_GEO", "gmat")
    assert result["compile_result"]["status"] == "success", result["compile_result"]

    script = (tmp_path / "elliptical_LEO_to_GEO" / "generated_mission.script").read_text(encoding="utf-8")

    assert "Propagate EarthProp(TargetSat) { TargetSat.ElapsedSecs = 10800.0 };" in script
    assert script.index("TargetSat.ElapsedSecs = 10800.0") < script.index("Maneuver TransferInjection(TargetSat);")
    assert "Propagate EarthProp(TargetSat) { TargetSat.Earth.TA = 150.0 };" in script
    assert "Maneuver TransferInjection(TargetSat);" in script


def test_leo_to_geo_plane_change_is_combined_with_apogee_insertion(tmp_path: Path) -> None:
    spec_path = Path("examples/elliptical_LEO_to_GEO/mission_spec.json")
    spec = _validate(spec_path)

    initial_coast = next(event for event in spec["events"] if event["id"] == "event_initial_coast")
    geo_burn = next(burn for burn in spec["burns"] if burn["id"] == "orbit_insertion")
    transfer_event = next(event for event in spec["events"] if event["id"] == "event_transfer_injection")
    insertion_event = next(event for event in spec["events"] if event["id"] == "event_orbit_insertion")

    assert initial_coast["type"] == "parameter_reaches"
    assert initial_coast["stop_condition"] == {"parameter": "ElapsedSecs", "value": 10800.0}
    assert transfer_event["type"] == "parameter_reaches"
    assert transfer_event["stop_condition"] == {"parameter": "Earth.TA", "value": 150.0}
    assert insertion_event["type"] == "orbital_event"
    assert insertion_event["event"] == "apoapsis"
    assert geo_burn["delta_v_km_s"][1] != 0.0
    assert all(burn["id"] != "plane_change_at_node" for burn in spec["burns"])

    result = compile_bundle(spec_path, tmp_path / "elliptical_LEO_to_GEO", "gmat")
    assert result["compile_result"]["status"] == "success", result["compile_result"]

    script = (tmp_path / "elliptical_LEO_to_GEO" / "generated_mission.script").read_text(encoding="utf-8")

    assert "Propagate EarthProp(TargetSat) { TargetSat.Earth.TA = 150.0 };" in script
    assert "Maneuver OrbitInsertion(TargetSat);" in script
    assert "Maneuver PlaneChangeAtNode(TargetSat);" not in script
    assert "Propagate EarthProp(TargetSat) { TargetSat.ElapsedSecs = 172800.0 };" in script


def test_surface_fixed_ephemeris_uses_inertial_keplerian_angles(tmp_path: Path) -> None:
    spec_path = Path("examples/elliptical_LEO_to_GEO/mission_spec.json")
    result = compile_bundle(spec_path, tmp_path / "elliptical_LEO_to_GEO", "gmat")
    assert result["compile_result"]["status"] == "success", result["compile_result"]

    script = (tmp_path / "elliptical_LEO_to_GEO" / "generated_mission.script").read_text(encoding="utf-8")

    assert "TargetSat.EarthFixed.X" in script
    assert "TargetSat.EarthFixed.INC" not in script
    assert "TargetSat.EarthFixed.RAAN" not in script
    assert "TargetSat.EarthFixed.AOP" not in script
    assert "TargetSat.EarthMJ2000Eq.INC" in script

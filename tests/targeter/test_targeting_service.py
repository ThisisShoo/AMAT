from pathlib import Path
import json
from targeter.service import solve_file, validate_file
from targeter.domain import canonicalize_target_problem
from targeter.formulation import build_targeting_formulation
from compiler.io import read_json
from compiler.ir.canonicalize import canonicalize
from compiler.ir.backend_spec import to_backend_spec
from compiler.validation.validate_schema import validate_schema
from compiler.validation.validate_bounds import validate_bounds

TARGET_PROBLEM = {
    "schema_version": "1.0.0",
    "problem_id": "leo_300km_to_geo",
    "mission_id": "leo_300km_to_geo",
    "transfer_strategy": {
        "type": "hohmann_transfer",
        "central_body": "Earth",
        "maneuver_model": "impulsive",
        "maneuver_policy": "valid_node_low_speed"
    },
    "initial_state": {
        "representation": "circular_orbit",
        "altitude": {"value": 300.0, "unit": "km"},
        "inclination": {"value": 0.0, "unit": "deg"},
        "raan": {"value": 0.0, "unit": "deg"},
        "aop": {"value": 0.0, "unit": "deg"},
        "true_anomaly": {"value": 0.0, "unit": "deg"},
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq"
    },
    "target": {
        "type": "geostationary_orbit",
        "inclination": {"value": 0.0, "unit": "deg"},
        "eccentricity_max": 0.001
    }
}


def _example(tmp_path: Path) -> Path:
    path = tmp_path / "target_problem.json"
    path.write_text(json.dumps(TARGET_PROBLEM, indent=2), encoding="utf-8")
    return path


def test_one_file_problem_validates(tmp_path):
    result = validate_file(_example(tmp_path))
    assert result["status"] == "valid"
    assert result["transfer_strategy"] == "hohmann_transfer"

def test_solve_emits_new_artifact_set(tmp_path):
    result = solve_file(_example(tmp_path), tmp_path)
    assert result["status"] == "analytically_feasible"
    assert result["artifact_profile"] == "standard"
    assert 3.8 < result["total_delta_v_km_s"] < 4.0
    for name in ["target_problem.canonical.json", "maneuver_plan.json", "targeting_result.json", "candidate_mission_spec.json"]:
        assert (tmp_path/name).exists()
    for name in ["targeting_formulation.json", "initial_candidate.json", "acceptance_result.json", "provenance.json"]:
        assert not (tmp_path/name).exists()
    maneuver_plan = read_json(tmp_path/"maneuver_plan.json")
    assert maneuver_plan["status"] == "analytically_feasible"
    target_result = read_json(tmp_path/"targeting_result.json")
    assert target_result["targeting_status"] == "not_run"
    assert target_result["simulation_status"] == "not_run"
    solved = read_json(tmp_path/"candidate_mission_spec.json")
    backend_ir = canonicalize(to_backend_spec(solved))
    failures = [x for x in validate_schema(solved) + validate_bounds(backend_ir) if x.get("status") != "passed"]
    assert failures == []


def test_solve_debug_profile_writes_diagnostic_artifacts(tmp_path):
    result = solve_file(_example(tmp_path), tmp_path, artifact_profile="debug")

    assert result["artifact_profile"] == "debug"
    for name in [
        "target_problem.canonical.json",
        "targeting_formulation.json",
        "maneuver_plan.json",
        "initial_candidate.json",
        "targeting_result.json",
        "candidate_mission_spec.json",
        "acceptance_result.json",
        "provenance.json",
    ]:
        assert (tmp_path/name).exists()


def test_target_argument_of_latitude_is_optional_constraint():
    raw = json.loads(json.dumps(TARGET_PROBLEM))
    raw["target"]["argument_of_latitude"] = {"value": 45.0, "unit": "deg"}
    raw["target"]["argument_of_latitude_max"] = {"value": 0.1, "unit": "deg"}

    problem = canonicalize_target_problem(raw)
    formulation = build_targeting_formulation(problem)

    assert problem["target"]["argument_of_latitude"] == {"value": 45.0, "unit": "deg"}
    assert any(
        constraint["metric_id"] == "spacecraft.final.orbit.argument_of_latitude"
        for constraint in formulation["constraints"]
    )


def test_initial_state_frame_defaults_to_earth_equatorial():
    raw = json.loads(json.dumps(TARGET_PROBLEM))
    raw["initial_state"].pop("frame")

    problem = canonicalize_target_problem(raw)

    assert problem["initial_state"]["frame"] == "EarthMJ2000Eq"


def test_initial_state_frame_defaults_to_ecliptic_for_non_earth_body():
    raw = json.loads(json.dumps(TARGET_PROBLEM))
    raw["problem_id"] = "mars_transfer"
    raw["mission_id"] = "mars_transfer"
    raw["transfer_strategy"]["central_body"] = "Mars"
    raw["transfer_strategy"]["type"] = "two_impulse_apsidal_transfer"
    raw["initial_state"].pop("frame")
    raw["target"] = {
        "type": "circular_orbit",
        "altitude": {"value": 5000.0, "unit": "km"},
        "inclination": {"value": 0.0, "unit": "deg"},
    }

    problem = canonicalize_target_problem(raw)

    assert problem["initial_state"]["frame"] == "MarsMJ2000Ec"


def test_explicit_initial_state_frame_is_preserved_for_non_earth_body():
    raw = json.loads(json.dumps(TARGET_PROBLEM))
    raw["problem_id"] = "mars_transfer"
    raw["mission_id"] = "mars_transfer"
    raw["transfer_strategy"]["central_body"] = "Mars"
    raw["transfer_strategy"]["type"] = "two_impulse_apsidal_transfer"
    raw["initial_state"]["frame"] = "MarsMJ2000Eq"
    raw["target"] = {
        "type": "circular_orbit",
        "altitude": {"value": 5000.0, "unit": "km"},
        "inclination": {"value": 0.0, "unit": "deg"},
    }

    problem = canonicalize_target_problem(raw)

    assert problem["initial_state"]["frame"] == "MarsMJ2000Eq"


def test_custom_central_body_requires_and_uses_constants(tmp_path):
    raw = json.loads(json.dumps(TARGET_PROBLEM))
    raw["problem_id"] = "custom_body_transfer"
    raw["mission_id"] = "custom_body_transfer"
    raw["transfer_strategy"]["central_body"] = "DemoBody"
    raw["transfer_strategy"]["central_body_radius"] = {"value": 1000.0, "unit": "km"}
    raw["transfer_strategy"]["central_body_mu"] = {"value": 20000.0, "unit": "km^3/s^2"}
    raw["transfer_strategy"]["type"] = "two_impulse_apsidal_transfer"
    raw["initial_state"]["frame"] = "DemoBodyMJ2000Eq"
    raw["target"] = {
        "type": "circular_orbit",
        "altitude": {"value": 5000.0, "unit": "km"},
        "inclination": {"value": 0.0, "unit": "deg"},
    }
    path = tmp_path / "custom_target_problem.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    result = solve_file(path, tmp_path)
    problem = read_json(tmp_path / "target_problem.canonical.json")
    spec = read_json(tmp_path / "candidate_mission_spec.json")

    assert result["status"] == "analytically_feasible"
    assert problem["initial_state"]["sma"] == {"value": 1300.0, "unit": "km"}
    assert problem["target"]["sma"] == {"value": 6000.0, "unit": "km"}
    assert spec["force_models"][0]["central_body"] == "DemoBody"
    assert spec["propagators"][0]["id"] == "demoBody_prop"

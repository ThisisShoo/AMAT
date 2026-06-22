from pathlib import Path
import json
<<<<<<< Updated upstream:tests/targeting/test_targeting_service.py
from mission_targeting.service import solve_file, validate_file
from mission_compiler.io import read_json
from mission_compiler.ir.canonicalize import canonicalize
from mission_compiler.validation.validate_schema import validate_schema
from mission_compiler.validation.validate_bounds import validate_bounds
=======
from targeter.service import solve_file, validate_file
from targeter.domain import canonicalize_target_problem
from targeter.formulation import build_targeting_formulation
from compiler.io import read_json
from compiler.ir.canonicalize import canonicalize
from compiler.validation.validate_schema import validate_schema
from compiler.validation.validate_bounds import validate_bounds
>>>>>>> Stashed changes:tests/targeter/test_targeting_service.py

TARGET_PROBLEM = {
    "schema_version": "1.0.0",
    "problem_id": "leo_300km_to_geo",
    "mission_id": "leo_300km_to_geo",
    "transfer_strategy": {
        "type": "hohmann_transfer",
        "central_body": "Earth",
        "maneuver_model": "impulsive",
        "plane_change_policy": "concurrent_minimum_delta_v"
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
    assert 3.8 < result["total_delta_v_km_s"] < 4.0
    for name in ["target_problem.canonical.json", "targeting_formulation.json", "initial_candidate.json", "targeting_result.json", "candidate_mission_spec.json", "acceptance_result.json", "provenance.json"]:
        assert (tmp_path/name).exists()
    target_result = read_json(tmp_path/"targeting_result.json")
    assert target_result["targeting_status"] == "not_run"
    assert target_result["simulation_status"] == "not_run"
    solved = canonicalize(read_json(tmp_path/"candidate_mission_spec.json"))
    failures = [x for x in validate_schema(solved) + validate_bounds(solved) if x.get("status") != "passed"]
    assert failures == []
<<<<<<< Updated upstream:tests/targeting/test_targeting_service.py
=======


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

>>>>>>> Stashed changes:tests/targeter/test_targeting_service.py

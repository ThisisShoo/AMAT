from __future__ import annotations

import copy

from compiler.ir.canonicalize import canonicalize
from compiler.io import read_json
from compiler.validation.validate_bounds import validate_bounds
from compiler.validation.validate_schema import validate_schema
from targeter.domain import canonicalize_target_problem
from targeter.initial_guess import generate_hohmann_candidate
from targeter.materialization import materialize_mission_spec
from targeter.phase import apply_phase_strategy, select_phase_strategy
from targeter.service import solve_file


BASE_PROBLEM = {
    "schema_version": "1.0.0",
    "problem_id": "leo_geo_phase",
    "mission_id": "leo_geo_phase",
    "transfer_strategy": {
        "type": "two_impulse_apsidal_transfer",
        "central_body": "Earth",
        "phase_policy": {
            "mode": "auto",
            "allowed_strategies": ["coast_to_phase", "in_plane_drift"],
            "max_revolutions": 5,
            "restore_target_orbit": True,
        },
        "maneuver_policy": {
            "type": "valid_node_low_speed",
            "departure_event": {"type": "node"},
            "arrival_event": {"type": "apoapsis"},
            "allow_departure_phasing": True,
            "prefer_apsis_alignment": True,
        },
    },
    "initial_state": {
        "representation": "circular_orbit",
        "altitude": {"value": 300.0, "unit": "km"},
        "inclination": {"value": 23.0, "unit": "deg"},
        "raan": {"value": 60.0, "unit": "deg"},
        "aop": {"value": 30.0, "unit": "deg"},
        "true_anomaly": {"value": 0.0, "unit": "deg"},
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq",
    },
    "target": {
        "type": "geostationary_orbit",
        "inclination": {"value": 0.0, "unit": "deg"},
        "raan": {"value": 0.0, "unit": "deg"},
        "aop": {"value": 0.0, "unit": "deg"},
        "eccentricity": 0.0,
        "eccentricity_max": 0.001,
        "inclination_max": {"value": 0.05, "unit": "deg"},
        "argument_of_latitude": {"value": 45.0, "unit": "deg"},
        "argument_of_latitude_max": {"value": 0.25, "unit": "deg"},
    },
    "execution": {
        "initial_coast_s": 10800.0,
        "post_insertion_coast_s": 172800.0,
    },
}


def _problem() -> dict:
    return canonicalize_target_problem(copy.deepcopy(BASE_PROBLEM))


def test_phase_strategy_selector_picks_in_plane_drift_for_fixed_final_phase():
    problem = _problem()
    nominal = generate_hohmann_candidate(problem)

    decision = select_phase_strategy(problem, nominal)

    assert decision["selected"] == "in_plane_drift"
    assert decision["status"] == "selected"
    assert decision["phase_assessment"]["target_parameter"] == "argument_of_latitude"
    assert decision["phase_plan"]["total_delta_v_km_s"] > 0.0
    assert decision["controls"] == [
        "enter_phase_drift.delta_v_v",
        "phase_drift.duration_s",
        "exit_phase_drift.delta_v_v",
    ]


def test_in_plane_drift_augments_candidate_with_in_plane_restore_burns():
    problem = _problem()
    nominal = generate_hohmann_candidate(problem)
    candidate = apply_phase_strategy(problem, nominal)

    maneuver_ids = [maneuver["maneuver_id"] for maneuver in candidate["maneuvers"]]
    assert maneuver_ids[-2:] == ["enter_phase_drift", "exit_phase_drift"]
    assert candidate["phase_strategy_decision"]["selected"] == "in_plane_drift"
    assert candidate["analytic_assessment"]["total_delta_v_km_s"] > nominal["analytic_assessment"]["total_delta_v_km_s"]

    enter, exit_ = candidate["maneuvers"][-2:]
    assert enter["components_km_s"][1:] == [0.0, 0.0]
    assert exit_["components_km_s"][1:] == [0.0, 0.0]
    assert enter["components_km_s"][0] == -exit_["components_km_s"][0]
    assert enter["post_maneuver_coast_s"] == candidate["phase_strategy_decision"]["phase_plan"]["drift_duration_s"]


def test_phase_drift_materializes_as_burn_coast_burn_sequence():
    problem = _problem()
    candidate = apply_phase_strategy(problem, generate_hohmann_candidate(problem))
    spec = canonicalize(materialize_mission_spec(problem, candidate))

    failures = [item for item in validate_schema(spec) + validate_bounds(spec) if item.get("status") != "passed"]
    assert failures == []
    burn_ids = [burn["id"] for burn in spec["burns"]]
    assert "enter_phase_drift" in burn_ids
    assert "exit_phase_drift" in burn_ids

    steps = [step for phase in spec["mission_sequence"] for step in phase["steps"]]
    enter_index = next(i for i, step in enumerate(steps) if step.get("burn") == "enter_phase_drift")
    coast_index = next(i for i, step in enumerate(steps) if step.get("step_id") == "coast_after_enter_phase_drift")
    exit_index = next(i for i, step in enumerate(steps) if step.get("burn") == "exit_phase_drift")
    assert enter_index < coast_index < exit_index
    assert steps[coast_index]["type"] == "propagate"
    assert steps[coast_index]["duration_s"] == candidate["phase_strategy_decision"]["phase_plan"]["drift_duration_s"]


def test_phase_policy_disabled_leaves_candidate_shape_only():
    raw = copy.deepcopy(BASE_PROBLEM)
    raw["transfer_strategy"]["phase_policy"] = {"mode": "disabled"}
    problem = canonicalize_target_problem(raw)
    nominal = generate_hohmann_candidate(problem)
    candidate = apply_phase_strategy(problem, nominal)

    assert [m["maneuver_id"] for m in candidate["maneuvers"]] == [m["maneuver_id"] for m in nominal["maneuvers"]]
    assert candidate["phase_strategy_decision"]["status"] == "disabled"


def test_solve_writes_phase_strategy_decision_artifact(tmp_path):
    path = tmp_path / "target_problem.json"
    import json

    path.write_text(json.dumps(BASE_PROBLEM), encoding="utf-8")

    result = solve_file(path, tmp_path / "targeting")
    decision = read_json(tmp_path / "targeting" / "phase_strategy_decision.json")

    assert result["status"] == "analytically_feasible"
    assert "phase_strategy_decision.json" in result["artifacts"]
    assert decision["selected"] == "in_plane_drift"

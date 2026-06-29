from __future__ import annotations

from pathlib import Path

from targeter.domain import canonicalize_target_problem
from targeter.io import read_json
from targeter.maneuver_planner import ManeuverPlanRequest, ManeuverPlanner, plan_target_problem
from targeter.maneuver_planner.operations import (
    BODY_TRANSFER_OPERATION_TYPES,
    RENDEZVOUS_OPERATION_TYPES,
    plan_circular_coplanar_patched_conics,
    plan_lambert_intercept,
)
from targeter.maneuver_planner.timing import SUPPORTED_TIMING_SELECTORS
from targeter.patched_conics import CircularOrbitState


def _problem() -> dict:
    return canonicalize_target_problem(read_json(Path("examples/LEO_to_GEO/target_problem.json")))


def test_maneuver_planner_generates_targeter_candidate() -> None:
    result = plan_target_problem(_problem())

    assert result.status == "analytically_feasible"
    assert result.operation_type == _problem()["transfer_strategy"]["type"]
    candidate = result.selected_candidate_payload
    assert candidate["generation_status"] == "candidate_generated"
    assert candidate["maneuvers"][0]["maneuver_id"] == "transfer_injection"
    assert candidate["maneuvers"][-1]["maneuver_id"] in {"orbit_insertion", "exit_phase_drift"}
    assert result.selected_candidate is not None
    assert result.selected_candidate.objective_breakdown.total_delta_v_km_s == candidate["analytic_assessment"]["total_delta_v_km_s"]


def test_maneuver_planner_accepts_explicit_request_object() -> None:
    problem = _problem()
    request = ManeuverPlanRequest.from_target_problem(problem)

    result = ManeuverPlanner().plan(request)

    assert result.selected_candidate_payload["problem_id"] == problem["problem_id"]
    assert result.to_dict()["candidates"][0]["operation_type"] == problem["transfer_strategy"]["type"]


def test_maneuver_planner_applies_phasing_inside_planner_boundary() -> None:
    problem = _problem()

    candidate = plan_target_problem(problem).selected_candidate_payload

    assert "phase_strategy_decision" in candidate
    if candidate["phase_strategy_decision"]["selected"] == "in_plane_drift":
        maneuver_ids = [maneuver["maneuver_id"] for maneuver in candidate["maneuvers"]]
        assert "enter_phase_drift" in maneuver_ids
        assert "exit_phase_drift" in maneuver_ids


def test_maneuver_planner_declares_mechjeb_style_timing_selectors() -> None:
    assert {
        "apoapsis",
        "periapsis",
        "true_anomaly",
        "argument_of_latitude",
        "equatorial_ascending_node",
        "equatorial_descending_node",
        "target_relative_ascending_node",
        "target_relative_descending_node",
        "closest_approach",
        "fixed_epoch",
    }.issubset(SUPPORTED_TIMING_SELECTORS)


def test_transfer_wrappers_are_available_from_maneuver_planner_namespace() -> None:
    assert "lambert_intercept" in RENDEZVOUS_OPERATION_TYPES
    assert "conic_chain" in BODY_TRANSFER_OPERATION_TYPES

    lambert = plan_lambert_intercept((7000.0, 0.0, 0.0), (0.0, 9000.0, 0.0), 398600.4418, 3600.0)
    assert len(lambert.v1_km_s) == 3

    departure = CircularOrbitState(radius_km=7000.0, phase_rad=0.0, mu_central_km3_s2=398600.4418)
    arrival = CircularOrbitState(radius_km=12000.0, phase_rad=1.0, mu_central_km3_s2=398600.4418)
    patched = plan_circular_coplanar_patched_conics(
        departure,
        arrival,
        central_mu_km3_s2=398600.4418,
        samples=5,
    )
    assert patched.departure_delta_v_magnitude_km_s > 0.0


def test_targeter_orchestration_uses_maneuver_planner_not_legacy_modules() -> None:
    service = Path("targeter/service.py").read_text(encoding="utf-8")
    execution = Path("targeter/execution.py").read_text(encoding="utf-8")

    assert "targeter.maneuver_planner" in service
    assert "targeter.maneuver_planner" in execution
    assert "targeter.initial_guess" not in service
    assert "targeter.initial_guess" not in execution
    assert "targeter.phase" not in service
    assert "targeter.phase" not in execution

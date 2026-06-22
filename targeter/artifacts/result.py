from __future__ import annotations
from typing import Any


def build_targeting_result(problem: dict[str, Any], formulation: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    assessment = candidate["analytic_assessment"]
    max_dv = problem["limits"].get("maximum_total_delta_v")
    violations = []
    if max_dv and assessment["total_delta_v_km_s"] > max_dv["value"]:
        violations.append({"limit": "maximum_total_delta_v", "measured": assessment["total_delta_v_km_s"], "allowed": max_dv})
    return {
        "schema_version": "1.1.0",
        "problem_id": problem["problem_id"],
        "mission_id": problem["mission_id"],
        "generation_status": "candidate_generated",
        "targeting_status": "not_run",
        "simulation_status": "not_run",
        "verification_status": "not_run",
        "summary_status": "analytically_feasible" if not violations else "limit_violation",
        "termination_reason": "analytic_initial_guess_generated",
        "transfer_strategy": problem["transfer_strategy"],
        "candidate_id": candidate["candidate_id"],
        "analytic_assessment": assessment,
        "maneuvers": candidate["maneuvers"],
        "limit_violations": violations,
        "solver": formulation["solver_policy"],
        "warnings": [
            "This result is assessed only under a two-body impulsive model.",
            "Concurrent plane-change estimates assume compatible apsidal/node geometry.",
            "Run the generated MissionSpec before claiming simulation feasibility.",
        ],
    }

from __future__ import annotations
from typing import Any

def not_run_acceptance(problem: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "problem_id": problem["problem_id"],
        "candidate_id": candidate["candidate_id"],
        "simulation_status": "not_run",
        "verification_status": "not_run",
        "required_verification_level": problem["verification"]["required_level"],
        "reason": "SimulationEvaluation is the next implementation milestone. The generated MissionSpec must be compiled and run before requirements can be accepted.",
    }

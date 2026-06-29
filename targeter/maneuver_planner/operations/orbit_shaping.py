from __future__ import annotations

from typing import Any

from targeter.initial_guess.hohmann import generate_hohmann_candidate

from ..models import ManeuverCandidate, ManeuverObjectiveBreakdown
from ..timing import timing_from_maneuver


ORBIT_SHAPING_OPERATION_TYPES = {
    "hohmann_transfer",
    "two_impulse_apsidal_transfer",
    "orbit_shaping",
    "change_apoapsis",
    "change_periapsis",
    "circularize",
    "change_apsides",
    "change_sma",
    "change_eccentricity",
}


def plan_apsidal_transfer(problem: dict[str, Any]) -> ManeuverCandidate:
    candidate = generate_hohmann_candidate(problem)
    assessment = candidate.get("analytic_assessment", {})
    transfer_time = candidate.get("variable_values", {}).get("transfer.coast_time", {}).get("value")
    return ManeuverCandidate(
        operation_type=problem["transfer_strategy"]["type"],
        candidate=candidate,
        timing=[timing_from_maneuver(maneuver) for maneuver in candidate.get("maneuvers", [])],
        objective_breakdown=ManeuverObjectiveBreakdown(
            total_delta_v_km_s=assessment.get("total_delta_v_km_s"),
            transfer_time_s=transfer_time,
            plane_change_deg=assessment.get("plane_change_total_deg"),
            score=assessment.get("total_delta_v_km_s"),
            metadata={"analytic_model": assessment.get("model")},
        ),
        score=assessment.get("total_delta_v_km_s"),
    )

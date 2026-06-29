from __future__ import annotations

from typing import Any

from .models import MANEUVER_PLAN_STATUSES, ManeuverPlanRequest, ManeuverPlanResult
from .operations.body_transfer import BODY_TRANSFER_OPERATION_TYPES
from .operations.orbit_shaping import ORBIT_SHAPING_OPERATION_TYPES, plan_apsidal_transfer
from .operations.phasing import apply_phasing
from .operations.plane_change import PLANE_CHANGE_OPERATION_TYPES
from .operations.rendezvous import RENDEZVOUS_OPERATION_TYPES


SUPPORTED_OPERATION_TYPES = (
    ORBIT_SHAPING_OPERATION_TYPES
    | BODY_TRANSFER_OPERATION_TYPES
    | PLANE_CHANGE_OPERATION_TYPES
    | RENDEZVOUS_OPERATION_TYPES
    | {"phasing", "resonant_phasing", "phase_match"}
)


class ManeuverPlanner:
    """Backend-neutral maneuver synthesis facade.

    The planner owns analytic and heuristic burn generation.  It intentionally
    returns AMAT's existing candidate dictionary as the executable payload so
    downstream materialization, simulation, correction, and optimization stay
    decoupled from the synthesis implementation.
    """

    schema_version = "1.0.0"

    def plan(self, request: ManeuverPlanRequest | dict[str, Any]) -> ManeuverPlanResult:
        req = _coerce_request(request)
        if req.operation_type in ORBIT_SHAPING_OPERATION_TYPES:
            if req.problem is None:
                return _failed(req.operation_type, "failed_invalid_input", "orbit-shaping operations require a target problem")
            candidate = plan_apsidal_transfer(req.problem)
            payload = apply_phasing(req.problem, candidate.candidate)
            candidate = _replace_candidate_payload(candidate, payload)
            status = payload.get("analytic_assessment", {}).get("status", "candidate_generated")
            if status not in MANEUVER_PLAN_STATUSES:
                status = "candidate_generated"
            return ManeuverPlanResult(
                schema_version=self.schema_version,
                operation_type=req.operation_type,
                status=status,
                candidates=[candidate],
            )
        if req.operation_type in SUPPORTED_OPERATION_TYPES:
            return _failed(
                req.operation_type,
                "failed_unsupported_operation",
                f"{req.operation_type} is registered in the maneuver planner but does not yet have a full ManeuverPlanRequest adapter",
            )
        return _failed(req.operation_type, "failed_unsupported_operation", f"Unsupported maneuver planner operation: {req.operation_type}")


def plan_target_problem(problem: dict[str, Any]) -> ManeuverPlanResult:
    return ManeuverPlanner().plan(ManeuverPlanRequest.from_target_problem(problem))


def _coerce_request(request: ManeuverPlanRequest | dict[str, Any]) -> ManeuverPlanRequest:
    if isinstance(request, ManeuverPlanRequest):
        return request
    if "problem" in request and "operation_type" in request:
        return ManeuverPlanRequest(
            operation_type=str(request["operation_type"]),
            problem=request.get("problem"),
            spacecraft_state=request.get("spacecraft_state"),
            central_body=request.get("central_body"),
            frame=request.get("frame"),
            target=request.get("target"),
            parameters=request.get("parameters", {}),
            timing=request.get("timing", {}),
            execution_profile=request.get("execution_profile", {}),
        )
    if "transfer_strategy" in request:
        return ManeuverPlanRequest.from_target_problem(request)
    raise ValueError("ManeuverPlanner.plan requires a ManeuverPlanRequest, request dictionary, or canonical TargetProblem")


def _replace_candidate_payload(candidate, payload: dict[str, Any]):
    from dataclasses import replace

    assessment = payload.get("analytic_assessment", {})
    transfer_time = payload.get("variable_values", {}).get("transfer.coast_time", {}).get("value")
    return replace(
        candidate,
        candidate=payload,
        objective_breakdown=replace(
            candidate.objective_breakdown,
            total_delta_v_km_s=assessment.get("total_delta_v_km_s"),
            transfer_time_s=transfer_time,
            plane_change_deg=assessment.get("plane_change_total_deg"),
            score=assessment.get("total_delta_v_km_s"),
        ),
        score=assessment.get("total_delta_v_km_s"),
    )


def _failed(operation_type: str, status: str, warning: str) -> ManeuverPlanResult:
    return ManeuverPlanResult(
        schema_version=ManeuverPlanner.schema_version,
        operation_type=operation_type,
        status=status,
        candidates=[],
        warnings=[warning],
    )

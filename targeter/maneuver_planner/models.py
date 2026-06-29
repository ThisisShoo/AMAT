from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


MANEUVER_PLAN_STATUSES = {
    "candidate_generated",
    "analytically_feasible",
    "targeted",
    "simulation_feasible",
    "verified",
    "failed_invalid_input",
    "failed_no_solution",
    "failed_unsupported_operation",
    "failed_backend_error",
}


@dataclass(frozen=True)
class ManeuverTiming:
    selector: str
    epoch: str | None = None
    elapsed_s: float | None = None
    true_anomaly_deg: float | None = None
    argument_of_latitude_deg: float | None = None
    direction: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != {}}


@dataclass(frozen=True)
class ManeuverObjectiveBreakdown:
    total_delta_v_km_s: float | None = None
    transfer_time_s: float | None = None
    plane_change_deg: float | None = None
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != {}}


@dataclass(frozen=True)
class ManeuverCandidate:
    operation_type: str
    candidate: dict[str, Any]
    timing: list[ManeuverTiming] = field(default_factory=list)
    objective_breakdown: ManeuverObjectiveBreakdown = field(default_factory=ManeuverObjectiveBreakdown)
    score: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "operation_type": self.operation_type,
            "candidate": self.candidate,
            "timing": [entry.to_dict() for entry in self.timing],
            "objective_breakdown": self.objective_breakdown.to_dict(),
            "warnings": self.warnings,
        }
        if self.score is not None:
            payload["score"] = self.score
        return payload


@dataclass(frozen=True)
class ManeuverPlanRequest:
    operation_type: str
    problem: dict[str, Any] | None = None
    spacecraft_state: dict[str, Any] | None = None
    central_body: str | None = None
    frame: str | None = None
    target: dict[str, Any] | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    timing: dict[str, Any] = field(default_factory=dict)
    execution_profile: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_target_problem(cls, problem: dict[str, Any]) -> "ManeuverPlanRequest":
        strategy = problem["transfer_strategy"]
        return cls(
            operation_type=strategy["type"],
            problem=problem,
            spacecraft_state=problem["initial_state"],
            central_body=strategy["central_body"],
            frame=problem["initial_state"].get("frame"),
            target=problem["target"],
            parameters={"transfer_strategy": strategy},
            timing={
                "departure_event": strategy.get("departure_event"),
                "arrival_event": strategy.get("arrival_event"),
                "maneuver_policy": strategy.get("maneuver_policy"),
                "phase_policy": strategy.get("phase_policy"),
            },
            execution_profile=problem.get("execution", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None and v != {}}


@dataclass(frozen=True)
class ManeuverPlanResult:
    schema_version: str
    operation_type: str
    status: str
    candidates: list[ManeuverCandidate] = field(default_factory=list)
    selected_index: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def selected_candidate(self) -> ManeuverCandidate | None:
        if not self.candidates:
            return None
        return self.candidates[self.selected_index]

    @property
    def selected_candidate_payload(self) -> dict[str, Any]:
        selected = self.selected_candidate
        if selected is None:
            raise RuntimeError("maneuver plan has no selected candidate")
        return selected.candidate

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operation_type": self.operation_type,
            "status": self.status,
            "selected_index": self.selected_index,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "warnings": self.warnings,
        }

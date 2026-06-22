from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Generic, Sequence, TypeVar

from .stm_correction import StmCorrectionResult, solve_stm_target_state_correction


CandidateT = TypeVar("CandidateT")
AssessmentT = TypeVar("AssessmentT")


@dataclass(frozen=True)
class StmClosedLoopIteration(Generic[CandidateT, AssessmentT]):
    index: int
    candidate: CandidateT
    assessment: AssessmentT
    correction: StmCorrectionResult | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "candidate": _to_dict(self.candidate),
            "assessment": _to_dict(self.assessment),
            "correction": self.correction.to_dict() if self.correction is not None else None,
        }


@dataclass(frozen=True)
class StmClosedLoopResult(Generic[CandidateT, AssessmentT]):
    status: str
    final_candidate: CandidateT
    final_assessment: AssessmentT
    iterations: tuple[StmClosedLoopIteration[CandidateT, AssessmentT], ...]

    @property
    def converged(self) -> bool:
        return self.status == "converged"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "converged": self.converged,
            "final_candidate": _to_dict(self.final_candidate),
            "final_assessment": _to_dict(self.final_assessment),
            "iterations": [item.to_dict() for item in self.iterations],
        }


@dataclass(frozen=True)
class StmTargetStateAssessment:
    achieved_state: tuple[float, ...]
    target_state: tuple[float, ...]
    state_transition_matrix: tuple[tuple[float, ...], ...]
    converged: bool
    scaled_residual_vector: tuple[float, ...]
    tolerance: float
    control_influence_matrix: tuple[tuple[float, ...], ...] | None = None
    weights: tuple[float, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _to_dict(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def _assessment_converged(assessment: Any) -> bool:
    converged = getattr(assessment, "converged", None)
    if converged is None:
        raise ValueError("assessment must expose a converged property")
    return bool(converged)


def _tuple_vector(value: Sequence[float], name: str) -> tuple[float, ...]:
    try:
        out = tuple(float(x) for x in value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a numeric sequence") from exc
    if not out:
        raise ValueError(f"{name} must not be empty")
    return out


def _tuple_matrix(value: Sequence[Sequence[float]], name: str) -> tuple[tuple[float, ...], ...]:
    try:
        out = tuple(tuple(float(x) for x in row) for row in value)
    except TypeError as exc:
        raise ValueError(f"{name} must be a numeric matrix") from exc
    if not out or not out[0]:
        raise ValueError(f"{name} must not be empty")
    width = len(out[0])
    if any(len(row) != width for row in out):
        raise ValueError(f"{name} must be rectangular")
    return out


def build_stm_target_state_assessment(
    achieved_state: Sequence[float],
    target_state: Sequence[float],
    state_transition_matrix: Sequence[Sequence[float]],
    *,
    tolerance: float,
    control_influence_matrix: Sequence[Sequence[float]] | None = None,
    weights: Sequence[float] | None = None,
) -> StmTargetStateAssessment:
    achieved = _tuple_vector(achieved_state, "achieved_state")
    target = _tuple_vector(target_state, "target_state")
    residual = tuple(a - b for a, b in zip(achieved, target, strict=True))
    if weights is not None:
        w = _tuple_vector(weights, "weights")
        scaled = tuple(r * scale for r, scale in zip(residual, w, strict=True))
    else:
        scaled = residual
    residual_norm = sum(x * x for x in scaled) ** 0.5
    return StmTargetStateAssessment(
        achieved_state=achieved,
        target_state=target,
        state_transition_matrix=_tuple_matrix(state_transition_matrix, "state_transition_matrix"),
        converged=residual_norm <= tolerance,
        scaled_residual_vector=scaled,
        tolerance=float(tolerance),
        control_influence_matrix=_tuple_matrix(control_influence_matrix, "control_influence_matrix")
        if control_influence_matrix is not None
        else None,
        weights=_tuple_vector(weights, "weights") if weights is not None else None,
    )


def close_with_stm(
    initial_candidate: CandidateT,
    evaluate: Callable[[CandidateT], AssessmentT],
    apply_correction: Callable[[CandidateT, StmCorrectionResult], CandidateT],
    *,
    max_iterations: int = 5,
    damping: float = 1.0,
    max_step_norm: float | None = None,
    rcond: float | None = None,
) -> StmClosedLoopResult[CandidateT, AssessmentT]:
    """Iterate high-fidelity evaluation and STM correction until accepted."""

    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    current = initial_candidate
    iterations: list[StmClosedLoopIteration[CandidateT, AssessmentT]] = []
    for index in range(max_iterations):
        assessment = evaluate(current)
        if _assessment_converged(assessment):
            iterations.append(StmClosedLoopIteration(index, current, assessment, None))
            return StmClosedLoopResult("converged", current, assessment, tuple(iterations))

        correction = solve_stm_target_state_correction(
            getattr(assessment, "achieved_state"),
            getattr(assessment, "target_state"),
            getattr(assessment, "state_transition_matrix"),
            control_influence_matrix=getattr(assessment, "control_influence_matrix", None),
            weights=getattr(assessment, "weights", None),
            tolerance=float(getattr(assessment, "tolerance")),
            damping=damping,
            max_step_norm=max_step_norm,
            rcond=rcond,
        )
        iterations.append(StmClosedLoopIteration(index, current, assessment, correction))
        current = apply_correction(current, correction)

    final_assessment = evaluate(current)
    status = "converged" if _assessment_converged(final_assessment) else "max_iterations"
    iterations.append(StmClosedLoopIteration(max_iterations, current, final_assessment, None))
    return StmClosedLoopResult(status, current, final_assessment, tuple(iterations))


def execute_patched_conics_stm_closed_loop(
    generate_seed: Callable[[], CandidateT],
    evaluate: Callable[[CandidateT], AssessmentT],
    apply_correction: Callable[[CandidateT, StmCorrectionResult], CandidateT],
    *,
    max_iterations: int = 5,
    damping: float = 1.0,
    max_step_norm: float | None = None,
    rcond: float | None = None,
) -> StmClosedLoopResult[CandidateT, AssessmentT]:
    """Start from a patched-conics seed, then close the high-fidelity STM loop."""

    return close_with_stm(
        generate_seed(),
        evaluate,
        apply_correction,
        max_iterations=max_iterations,
        damping=damping,
        max_step_norm=max_step_norm,
        rcond=rcond,
    )

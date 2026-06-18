from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Generic, TypeVar


SeedT = TypeVar("SeedT")
RefinedT = TypeVar("RefinedT")
AssessmentT = TypeVar("AssessmentT")
CorrectionT = TypeVar("CorrectionT")


@dataclass(frozen=True)
class TargetingPolicyResult(Generic[SeedT, RefinedT, AssessmentT, CorrectionT]):
    """Result of the analytic-to-STM targeting policy."""

    status: str
    selected_stage: str
    seed: SeedT
    refined_seed: RefinedT | None
    assessment: AssessmentT
    correction: CorrectionT | None
    history: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if hasattr(value, "to_dict"):
                return value.to_dict()
            if hasattr(value, "__dataclass_fields__"):
                return asdict(value)
            return value

        return {
            "status": self.status,
            "selected_stage": self.selected_stage,
            "seed": convert(self.seed),
            "refined_seed": convert(self.refined_seed) if self.refined_seed is not None else None,
            "assessment": convert(self.assessment),
            "correction": convert(self.correction) if self.correction is not None else None,
            "history": list(self.history),
        }


def _assessment_converged(assessment: Any) -> bool:
    converged = getattr(assessment, "converged", None)
    if converged is None:
        raise ValueError("assessment must expose a converged property")
    return bool(converged)


def _assessment_norm(assessment: Any) -> float | None:
    vector = getattr(assessment, "scaled_residual_vector", None)
    if vector is None:
        return None
    return float(sum(float(x) ** 2 for x in vector) ** 0.5)


def execute_targeting_policy(
    generate_seed: Callable[[], SeedT],
    evaluate: Callable[[Any], AssessmentT],
    *,
    match_hyperbola: Callable[[SeedT], RefinedT] | None = None,
    correct_with_stm: Callable[[RefinedT | SeedT, AssessmentT], CorrectionT] | None = None,
) -> TargetingPolicyResult[SeedT, RefinedT, AssessmentT, CorrectionT]:
    """Run AMAT's targeting ladder.

    Policy:
    1. Generate an analytic patched-conics seed.
    2. Refine the seed with SOI/hyperbola/B-plane matching when available.
    3. Evaluate the high-fidelity final orbital state vector.
    4. If it misses tolerance, invoke STM correction when available.

    The callables keep this backend-neutral. For fast tests they can be pure
    Python functions; in production the evaluator/corrector can compile and run
    GMAT, then read the propagated final-state vector and STM artifacts.
    """

    history: list[dict[str, Any]] = []
    seed = generate_seed()
    current: RefinedT | SeedT = seed
    refined: RefinedT | None = None
    history.append({"stage": "patched_conics_seed", "status": "completed"})

    if match_hyperbola is not None:
        refined = match_hyperbola(seed)
        current = refined
        history.append({"stage": "hyperbola_bplane_matching", "status": "completed"})

    assessment = evaluate(current)
    residual_norm = _assessment_norm(assessment)
    history.append(
        {
            "stage": "high_fidelity_vector_evaluation",
            "status": "passed" if _assessment_converged(assessment) else "failed",
            "residual_norm": residual_norm,
        }
    )
    if _assessment_converged(assessment):
        return TargetingPolicyResult(
            status="accepted",
            selected_stage="hyperbola_bplane_matching" if match_hyperbola is not None else "patched_conics_seed",
            seed=seed,
            refined_seed=refined,
            assessment=assessment,
            correction=None,
            history=tuple(history),
        )

    if correct_with_stm is None:
        history.append({"stage": "stm_correction", "status": "required_not_available"})
        return TargetingPolicyResult(
            status="requires_stm_correction",
            selected_stage="high_fidelity_vector_evaluation",
            seed=seed,
            refined_seed=refined,
            assessment=assessment,
            correction=None,
            history=tuple(history),
        )

    correction = correct_with_stm(current, assessment)
    correction_converged = bool(getattr(correction, "converged", False))
    history.append(
        {
            "stage": "stm_correction",
            "status": "passed" if correction_converged else "failed",
            "predicted_residual_norm": getattr(correction, "predicted_residual_norm", None),
        }
    )
    return TargetingPolicyResult(
        status="stm_corrected" if correction_converged else "stm_correction_failed",
        selected_stage="stm_correction",
        seed=seed,
        refined_seed=refined,
        assessment=assessment,
        correction=correction,
        history=tuple(history),
    )

from __future__ import annotations

from copy import deepcopy
from typing import Any

from targeter.backends.base import CorrectionResult, SimulationRunResult
from targeter.stm_correction import solve_stm_target_state_correction


class StmCorrectionBackend:
    """Linear STM correction backend.

    The backend consumes an explicit STM assessment artifact. It intentionally
    does not synthesize sensitivities from residuals; another backend can do
    finite differencing or optimizer-based correction later.
    """

    backend_id = "stm"

    def correct(
        self,
        problem: dict[str, Any],
        candidate: dict[str, Any],
        simulation: SimulationRunResult,
        config: dict[str, Any],
    ) -> CorrectionResult:
        assessment = _assessment_payload(simulation, config)
        if assessment is None:
            return CorrectionResult(
                backend_id=self.backend_id,
                status="missing_stm_assessment",
                candidate=None,
                errors=("No STM assessment artifact was produced by the simulation backend.",),
            )
        try:
            correction = solve_stm_target_state_correction(
                assessment["achieved_state"],
                assessment["target_state"],
                assessment["state_transition_matrix"],
                control_influence_matrix=assessment.get("control_influence_matrix"),
                weights=assessment.get("weights"),
                tolerance=float(assessment.get("tolerance", config.get("tolerance", 1e-9))),
                damping=float(config.get("damping", 1.0)),
                max_step_norm=config.get("max_step_norm"),
                rcond=config.get("rcond"),
            )
            corrected = apply_candidate_correction(candidate, correction.correction, config.get("decision_variables", []))
        except (KeyError, TypeError, ValueError) as exc:
            return CorrectionResult(
                backend_id=self.backend_id,
                status="correction_failed",
                candidate=None,
                errors=(str(exc),),
            )
        return CorrectionResult(
            backend_id=self.backend_id,
            status="corrected" if correction.converged else "predicted_miss",
            candidate=corrected if correction.converged else None,
            correction=correction.to_dict(),
        )


def _assessment_payload(simulation: SimulationRunResult, config: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(config.get("assessment"), dict):
        return config["assessment"]
    artifacts = simulation.correction_artifacts or {}
    for key in ("stm_assessment", "stm_state_transition_matrix"):
        item = artifacts.get(key)
        if isinstance(item, dict) and isinstance(item.get("payload"), dict):
            return item["payload"]
    return None


def apply_candidate_correction(
    candidate: dict[str, Any],
    correction: tuple[float, ...],
    decision_variables: list[dict[str, Any]],
) -> dict[str, Any]:
    if not decision_variables:
        raise ValueError("STM correction requires correction.decision_variables")
    if len(decision_variables) != len(correction):
        raise ValueError("correction length must match correction.decision_variables")

    updated = deepcopy(candidate)
    for spec, delta in zip(decision_variables, correction, strict=True):
        path = spec.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("each decision variable requires a non-empty path")
        _add_at_path(updated, path.split("."), float(delta))
    return updated


def _add_at_path(root: dict[str, Any], parts: list[str], delta: float) -> None:
    current: Any = root
    for part in parts[:-1]:
        current = _descend(current, part)
    leaf = parts[-1]
    if isinstance(current, list):
        index = int(leaf)
        current[index] = float(current[index]) + delta
        return
    value = current[leaf]
    if isinstance(value, dict) and "value" in value:
        value["value"] = float(value["value"]) + delta
    else:
        current[leaf] = float(value) + delta


def _descend(current: Any, part: str) -> Any:
    if isinstance(current, list):
        return current[int(part)]
    return current[part]

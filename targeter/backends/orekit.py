from __future__ import annotations

from pathlib import Path
from typing import Any

from compiler.artifacts.bundle import compile_bundle
from compiler.runtime.run_python import run_generated_python
from targeter.backends.base import SimulationRunResult
from targeter.backends.stm import apply_candidate_correction
from targeter.evaluation import evaluate_simulation
from targeter.io import read_json, write_json
from targeter.materialization import materialize_mission_spec


class OrekitSimulationBackend:
    """Simulation adapter that uses AMAT's Orekit compiler/runtime path."""

    backend_id = "orekit"

    def evaluate_candidate(
        self,
        problem: dict[str, Any],
        candidate: dict[str, Any],
        mission_spec: dict[str, Any],
        out_dir: Path,
        *,
        run: bool,
    ) -> SimulationRunResult:
        out_dir.mkdir(parents=True, exist_ok=True)
        spec_path = out_dir / "candidate_mission_spec.json"
        write_json(spec_path, mission_spec)

        compile_report = compile_bundle(spec_path, out_dir, self.backend_id)
        compile_result = compile_report.get("compile_result")
        if compile_result and compile_result.get("status") != "success":
            return SimulationRunResult(
                backend_id=self.backend_id,
                status="compile_failed",
                simulation_dir=str(out_dir),
                mission_spec=mission_spec,
                evaluation=None,
                compile_result=compile_result,
                errors=tuple(str(item) for item in compile_result.get("errors", [])),
            )

        run_result = None
        if run:
            run_result = run_generated_python(out_dir / "generated_mission.py")
            if not run_result.get("ok"):
                return SimulationRunResult(
                    backend_id=self.backend_id,
                    status="run_failed",
                    simulation_dir=str(out_dir),
                    mission_spec=mission_spec,
                    evaluation=None,
                    compile_result=compile_result,
                    run_result=run_result,
                    errors=(str(run_result.get("stderr", "")),),
                )

        evaluation = evaluate_simulation(problem, out_dir) if run else None
        correction_artifacts = {}
        if run and evaluation and evaluation.get("evaluation_status") != "passed":
            correction_artifacts = _write_finite_difference_stm_assessment(
                problem,
                candidate,
                mission_spec,
                out_dir,
                evaluation,
                self.backend_id,
            )
        status = "accepted" if evaluation and evaluation.get("evaluation_status") == "passed" else ("evaluated" if run else "compiled")
        return SimulationRunResult(
            backend_id=self.backend_id,
            status=status,
            simulation_dir=str(out_dir),
            mission_spec=mission_spec,
            evaluation=evaluation,
            compile_result=compile_result,
            run_result=run_result,
            correction_artifacts=correction_artifacts or _discover_correction_artifacts(out_dir),
        )


def _write_finite_difference_stm_assessment(
    problem: dict[str, Any],
    candidate: dict[str, Any],
    mission_spec: dict[str, Any],
    out_dir: Path,
    nominal_evaluation: dict[str, Any],
    backend_id: str,
) -> dict[str, Any]:
    loop_config = (problem.get("execution", {}) or {}).get("closed_loop", {}) or {}
    correction_config = loop_config.get("correction", loop_config) or {}
    decision_variables = correction_config.get("decision_variables", []) or []
    if not decision_variables:
        return {}

    nominal = _state_vector_from_evaluation(nominal_evaluation)
    if nominal is None:
        return {}
    state_ids, achieved, target, weights = nominal

    rows: list[list[float]] = [[] for _ in state_ids]
    perturbations: list[dict[str, Any]] = []
    base_dir = out_dir / "targeting" / "orekit_stm"
    for index, variable in enumerate(decision_variables):
        step = _perturbation_step(variable)
        perturb_candidate = apply_candidate_correction(candidate, (step,), [variable])
        perturb_spec = materialize_mission_spec(problem, perturb_candidate)
        if "targeting" in mission_spec:
            perturb_spec["targeting"] = mission_spec["targeting"]
        perturb_dir = base_dir / f"perturb_{index:03d}"
        perturb_eval = _run_perturbed_candidate(problem, perturb_spec, perturb_dir, backend_id)
        perturb_vector = _state_vector_from_evaluation(perturb_eval, metric_ids=state_ids)
        if perturb_vector is None:
            return {}
        _, perturb_achieved, _, _ = perturb_vector
        column = [(p - n) / step for p, n in zip(perturb_achieved, achieved, strict=True)]
        for row, value in zip(rows, column, strict=True):
            row.append(float(value))
        perturbations.append(
            {
                "index": index,
                "decision_variable": variable,
                "step": step,
                "simulation_dir": str(perturb_dir),
            }
        )

    tolerance = float(correction_config.get("tolerance", 1e-8))
    assessment = {
        "schema_version": "1.0.0",
        "backend_id": backend_id,
        "method": "finite_difference_control_sensitivity",
        "state_vector": state_ids,
        "decision_variables": decision_variables,
        "achieved_state": achieved,
        "target_state": target,
        "state_transition_matrix": rows,
        "weights": weights,
        "tolerance": tolerance,
        "perturbations": perturbations,
    }
    path = out_dir / "outputs" / "stm_assessment.json"
    write_json(path, assessment)
    return {"stm_assessment": {"path": str(path), "payload": assessment}}


def _run_perturbed_candidate(
    problem: dict[str, Any],
    mission_spec: dict[str, Any],
    perturb_dir: Path,
    backend_id: str,
) -> dict[str, Any]:
    perturb_dir.mkdir(parents=True, exist_ok=True)
    spec_path = perturb_dir / "candidate_mission_spec.json"
    write_json(spec_path, mission_spec)
    compile_report = compile_bundle(spec_path, perturb_dir, backend_id)
    compile_result = compile_report.get("compile_result")
    if compile_result and compile_result.get("status") != "success":
        raise RuntimeError(f"Orekit STM perturbation compile failed: {compile_result.get('errors', [])}")
    run_result = run_generated_python(perturb_dir / "generated_mission.py")
    if not run_result.get("ok"):
        raise RuntimeError(f"Orekit STM perturbation run failed: {run_result.get('stderr', '')}")
    return evaluate_simulation(problem, perturb_dir)


def _state_vector_from_evaluation(
    evaluation: dict[str, Any],
    *,
    metric_ids: list[str] | None = None,
) -> tuple[list[str], list[float], list[float], list[float]] | None:
    residuals = evaluation.get("residuals", []) or []
    by_id = {item.get("metric_id"): item for item in residuals}
    selected_ids = metric_ids or [
        str(item.get("metric_id"))
        for item in residuals
        if str(item.get("metric_id", "")).startswith("spacecraft.final.orbit.")
        and item.get("relation", "eq") == "eq"
    ]
    if not selected_ids:
        return None
    achieved: list[float] = []
    target: list[float] = []
    weights: list[float] = []
    for metric_id in selected_ids:
        item = by_id.get(metric_id)
        if not item:
            return None
        target_value = float(item["target"]["value"])
        residual_value = float(item["residual"]["value"])
        tolerance = float(item.get("tolerance", {}).get("value", 1.0))
        target.append(target_value)
        achieved.append(target_value + residual_value)
        weights.append(1.0 / tolerance if tolerance > 0.0 else 1.0)
    return selected_ids, achieved, target, weights


def _perturbation_step(variable: dict[str, Any]) -> float:
    if "step" in variable:
        return float(variable["step"])
    path = str(variable.get("path", "")).lower()
    if "coast" in path or "time" in path or "duration" in path:
        return 1.0
    if "deg" in path or "argument_of_latitude" in path or "true_anomaly" in path:
        return 1.0e-2
    return 1.0e-4


def _discover_correction_artifacts(simulation_dir: Path) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for rel in (
        Path("targeting") / "stm_assessment.json",
        Path("outputs") / "stm_assessment.json",
        Path("outputs") / "stm_state_transition_matrix.json",
    ):
        path = simulation_dir / rel
        if path.exists():
            key = path.stem
            try:
                artifacts[key] = {"path": str(path), "payload": read_json(path)}
            except Exception:
                artifacts[key] = {"path": str(path)}
    return artifacts

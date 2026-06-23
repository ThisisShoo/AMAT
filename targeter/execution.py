from __future__ import annotations

from pathlib import Path
from typing import Any

from targeter.backends import get_correction_backend, get_simulation_backend
from targeter.domain import canonicalize_target_problem, validate_target_problem
from targeter.initial_guess import generate_hohmann_candidate
from targeter.io import read_json, write_json
from targeter.materialization import materialize_mission_spec
from targeter.phase import apply_phase_strategy


def execute_closed_loop_file(
    target_problem: str | Path,
    out_dir: str | Path,
    *,
    simulation_backend: str | None = None,
    correction_backend: str | None = None,
    run: bool = False,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    problem = canonicalize_target_problem(read_json(target_problem))
    validate_target_problem(problem)
    return execute_closed_loop(
        problem,
        Path(out_dir),
        simulation_backend=simulation_backend,
        correction_backend=correction_backend,
        run=run,
        max_iterations=max_iterations,
    )


def execute_closed_loop(
    problem: dict[str, Any],
    out_dir: Path,
    *,
    simulation_backend: str | None = None,
    correction_backend: str | None = None,
    run: bool = False,
    max_iterations: int | None = None,
) -> dict[str, Any]:
    problem = canonicalize_target_problem(problem)
    execution = problem.get("execution", {})
    loop_config = execution.get("closed_loop", {}) or {}
    sim_backend_id = simulation_backend or loop_config.get("simulation_backend") or execution.get("backend", "gmat")
    corr_backend_id = correction_backend or loop_config.get("correction_backend", "stm")
    max_iter = int(max_iterations if max_iterations is not None else loop_config.get("max_iterations", 3))
    if max_iter < 1:
        raise ValueError("max_iterations must be at least 1")

    sim_backend = get_simulation_backend(sim_backend_id)
    corr_backend = get_correction_backend(corr_backend_id)

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "target_problem.canonical.json", problem)

    candidate = apply_phase_strategy(problem, generate_hohmann_candidate(problem))
    iterations: list[dict[str, Any]] = []
    status = "max_iterations"
    termination_reason = "maximum_iterations_reached"

    for index in range(max_iter):
        mission_spec = materialize_mission_spec(problem, candidate)
        mission_spec = _attach_closed_loop_metadata(mission_spec, problem, loop_config)
        iteration_dir = out_dir / f"iteration_{index:03d}" / "simulation"
        simulation = sim_backend.evaluate_candidate(problem, candidate, mission_spec, iteration_dir, run=run)
        iteration: dict[str, Any] = {
            "iteration": index,
            "candidate": candidate,
            "mission_spec": str(iteration_dir / "candidate_mission_spec.json"),
            "simulation": simulation.to_dict(),
        }
        if simulation.status in {"compile_failed", "run_failed"}:
            status = simulation.status
            termination_reason = simulation.status
            iterations.append(iteration)
            break
        if not run:
            status = "compiled_not_run"
            termination_reason = "run_false"
            iterations.append(iteration)
            break
        if simulation.converged:
            status = "converged"
            termination_reason = "target_accepted"
            iterations.append(iteration)
            break

        correction = corr_backend.correct(problem, candidate, simulation, loop_config.get("correction", loop_config))
        iteration["correction"] = correction.to_dict()
        iterations.append(iteration)
        if not correction.corrected:
            status = correction.status
            termination_reason = correction.status
            break
        candidate = correction.candidate

    final_candidate = iterations[-1]["candidate"] if iterations else candidate
    result = {
        "schema_version": "1.0.0",
        "problem_id": problem["problem_id"],
        "mission_id": problem["mission_id"],
        "status": status,
        "converged": status == "converged",
        "termination_reason": termination_reason,
        "simulation_backend": sim_backend_id,
        "correction_backend": corr_backend_id,
        "run": run,
        "max_iterations": max_iter,
        "iterations": iterations,
        "final_candidate": final_candidate,
    }
    write_json(out_dir / "closed_loop_result.json", result)
    return result


def _attach_closed_loop_metadata(
    mission_spec: dict[str, Any],
    problem: dict[str, Any],
    loop_config: dict[str, Any],
) -> dict[str, Any]:
    mission_spec = dict(mission_spec)
    stm_config = loop_config.get("stm")
    if stm_config:
        mission_spec["targeting"] = {"stm": stm_config}
    return mission_spec

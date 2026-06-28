from __future__ import annotations

from pathlib import Path
from typing import Any

from targeter.backends.base import SimulationRunResult
from targeter.backends.registry import get_correction_backend
from targeter.cli import main as targeting_main
from targeter.execution import execute_closed_loop
from targeter.io import read_json, write_json


def _problem() -> dict[str, Any]:
    problem = read_json("examples/LEO_to_GEO/target_problem.json")
    problem["execution"]["closed_loop"] = {
        "simulation_backend": "fake_truth",
        "correction_backend": "stm",
        "max_iterations": 2,
        "correction": {
            "decision_variables": [{"path": "maneuvers.0.components_km_s.0"}],
            "tolerance": 1e-9,
        },
    }
    return problem


class FakeTruthSimulationBackend:
    backend_id = "fake_truth"

    def __init__(self) -> None:
        self.calls = 0

    def evaluate_candidate(self, problem, candidate, mission_spec, out_dir: Path, *, run: bool):
        out_dir.mkdir(parents=True, exist_ok=True)
        accepted = self.calls > 0
        self.calls += 1
        evaluation = {
            "evaluation_status": "passed" if accepted else "failed",
            "residuals": [],
        }
        artifacts = {}
        if not accepted:
            artifacts["stm_assessment"] = {
                "path": str(out_dir / "targeting" / "stm_assessment.json"),
                "payload": {
                    "achieved_state": [1.0],
                    "target_state": [0.0],
                    "state_transition_matrix": [[1.0]],
                    "tolerance": 1e-9,
                },
            }
        return SimulationRunResult(
            backend_id=self.backend_id,
            status="accepted" if accepted else "evaluated",
            simulation_dir=str(out_dir),
            mission_spec=mission_spec,
            evaluation=evaluation,
            correction_artifacts=artifacts,
        )


def test_closed_loop_keeps_simulation_backend_swappable(monkeypatch, tmp_path: Path) -> None:
    backend = FakeTruthSimulationBackend()

    def fake_registry(backend_id: str):
        assert backend_id == "fake_truth"
        return backend

    monkeypatch.setattr("targeter.execution.get_simulation_backend", fake_registry)

    result = execute_closed_loop(_problem(), tmp_path, run=True)

    assert result["status"] == "converged"
    assert result["simulation_backend"] == "fake_truth"
    assert result["correction_backend"] == "stm"
    assert len(result["iterations"]) == 2
    assert result["iterations"][0]["correction"]["status"] == "corrected"
    assert result["iterations"][1]["simulation"]["converged"] is True


def test_orekit_fd_correction_backend_is_registered() -> None:
    backend = get_correction_backend("orekit_fd")

    assert backend.backend_id == "orekit_fd"


def test_closed_loop_cli_can_compile_first_gmat_iteration_without_running(tmp_path: Path) -> None:
    problem = read_json("examples/LEO_to_GEO/target_problem.json")
    problem["execution"]["closed_loop"] = {"max_iterations": 1}
    problem_path = tmp_path / "target_problem.json"
    write_json(problem_path, problem)

    code = targeting_main(["closed-loop", str(problem_path), "--out", str(tmp_path / "targeting")])

    assert code == 0
    result = read_json(tmp_path / "targeting" / "closed_loop_result.json")
    assert result["status"] == "compiled_not_run"
    assert result["simulation_backend"] == "gmat"
    assert (tmp_path / "targeting" / "iteration_000" / "simulation" / "generated_mission.py").exists()


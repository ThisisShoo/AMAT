from __future__ import annotations

from pathlib import Path
from typing import Any

from compiler.artifacts.bundle import compile_bundle
from compiler.runtime.run_python import run_generated_python
from targeter.backends.base import SimulationRunResult
from targeter.evaluation import evaluate_simulation
from targeter.io import read_json, write_json


class GmatSimulationBackend:
    """Simulation adapter that uses AMAT's GMAT compiler/runtime path."""

    backend_id = "gmat"

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

        compile_report = compile_bundle(spec_path, out_dir, "gmat")
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
            run_result = run_generated_python(out_dir / "generated_mission.py", save_script=True)
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
        correction_artifacts = _discover_correction_artifacts(out_dir)
        status = "accepted" if evaluation and evaluation.get("evaluation_status") == "passed" else ("evaluated" if run else "compiled")
        return SimulationRunResult(
            backend_id=self.backend_id,
            status=status,
            simulation_dir=str(out_dir),
            mission_spec=mission_spec,
            evaluation=evaluation,
            compile_result=compile_result,
            run_result=run_result,
            correction_artifacts=correction_artifacts,
        )


def _discover_correction_artifacts(simulation_dir: Path) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for rel in (
        Path("targeting") / "stm_assessment.json",
        Path("targeting") / "stm_artifact_contract.json",
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

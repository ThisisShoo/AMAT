from __future__ import annotations

from pathlib import Path
from typing import Any

from compiler.artifacts.bundle import compile_bundle
from compiler.runtime.run_python import run_generated_python
from targeter.backends.base import SimulationRunResult
from targeter.evaluation import evaluate_simulation
from targeter.io import write_json


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
        status = "accepted" if evaluation and evaluation.get("evaluation_status") == "passed" else ("evaluated" if run else "compiled")
        return SimulationRunResult(
            backend_id=self.backend_id,
            status=status,
            simulation_dir=str(out_dir),
            mission_spec=mission_spec,
            evaluation=evaluation,
            compile_result=compile_result,
            run_result=run_result,
        )


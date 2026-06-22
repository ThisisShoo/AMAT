from __future__ import annotations

from pathlib import Path
from typing import Any

from compiler.artifacts.bundle import compile_bundle
from compiler.runtime.run_python import run_generated_python


class GmatOptimizationBackend:
    """GMAT-backed optimization adapter.

    The first implementation is a single-candidate evaluator: it compiles the
    supplied MissionSpec through the simulation layer and optionally runs the
    generated GMAT script. Search algorithms can sit behind this same backend
    contract later without changing callers.
    """

    backend_id = "gmat"
    module_id = "gmat_single_candidate"

    def solve(self, problem: dict[str, Any], out_dir: Path, run: bool = False) -> dict[str, Any]:
        simulation = problem["simulation"]
        mission_spec = Path(simulation["mission_spec"])
        simulation_out = Path(simulation.get("out_dir") or (out_dir / "simulation"))
        simulation_backend = simulation.get("backend") or self.backend_id

        compile_report = compile_bundle(mission_spec, simulation_out, simulation_backend)
        compile_result = compile_report["compile_result"]
        run_result = None
        status = "candidate_compiled" if compile_result.get("status") == "success" else "failed"

        if run and status != "failed":
            run_result = run_generated_python(simulation_out / "generated_mission.py", save_script=True)
            status = "candidate_evaluated" if run_result.get("ok") else "failed"

        candidate = {
            "candidate_id": "candidate_000",
            "mission_spec": str(mission_spec),
            "simulation_dir": str(simulation_out),
            "compile_status": compile_result.get("status"),
            "generated_artifacts": compile_result.get("generated_artifacts", []),
        }
        if run_result is not None:
            candidate["run_status"] = "passed" if run_result.get("ok") else "failed"

        return {
            "schema_version": "1.0.0",
            "optimization_id": problem["optimization_id"],
            "mission_id": problem["mission_id"],
            "backend_id": self.backend_id,
            "module_id": self.module_id,
            "optimization_status": status,
            "strategy": problem.get("strategy", {"type": "single_candidate"}),
            "design_variables": problem.get("design_variables", []),
            "objectives": problem.get("objectives", []),
            "constraints": problem.get("constraints", []),
            "best_candidate": candidate if status != "failed" else None,
            "iterations": [
                {
                    "iteration": 0,
                    "candidate_id": candidate["candidate_id"],
                    "status": status,
                    "candidate": candidate,
                }
            ],
            "artifacts": {
                "simulation_dir": str(simulation_out),
                "compile_result": str(simulation_out / "compile_result.json"),
                "validation_report": str(simulation_out / "validation_report.json"),
            },
            "run_result": run_result,
            "limitations": [
                "GMAT optimization backend currently performs single-candidate evaluation; iterative search is not implemented yet."
            ],
            "errors": compile_result.get("errors", []) + ([] if not run_result or run_result.get("ok") else [run_result.get("stderr", "")]),
        }


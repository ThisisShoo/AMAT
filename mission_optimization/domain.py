from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from .errors import OptimizationError


def _as_list(value: Any, field: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise OptimizationError(f"{field} must be a list")
    return value


def validate_optimization_problem(raw: dict[str, Any]) -> list[str]:
    if not isinstance(raw, dict):
        raise OptimizationError("Optimization problem must be a JSON object")
    if not raw.get("optimization_id"):
        raise OptimizationError("optimization_id is required")
    simulation = raw.get("simulation")
    if not isinstance(simulation, dict):
        raise OptimizationError("simulation object is required")
    if not simulation.get("mission_spec"):
        raise OptimizationError("simulation.mission_spec is required")
    if "design_variables" in raw:
        _as_list(raw.get("design_variables"), "design_variables")
    if "objectives" in raw:
        _as_list(raw.get("objectives"), "objectives")
    if "constraints" in raw:
        _as_list(raw.get("constraints"), "constraints")
    return []


def canonicalize_optimization_problem(raw: dict[str, Any], source_path: str | Path | None = None) -> dict[str, Any]:
    validate_optimization_problem(raw)
    problem = deepcopy(raw)
    problem.setdefault("schema_version", "1.0.0")
    problem.setdefault("mission_id", problem["optimization_id"])
    problem.setdefault("backend", "gmat")
    problem.setdefault("strategy", {"type": "single_candidate"})
    problem.setdefault("design_variables", [])
    problem.setdefault("objectives", [])
    problem.setdefault("constraints", [])

    simulation = problem.setdefault("simulation", {})
    simulation.setdefault("backend", problem["backend"])
    simulation.setdefault("out_dir", f"generated/{problem['mission_id']}/optimization/simulation")

    if source_path is not None:
        base = Path(source_path).resolve().parent
        mission_spec = Path(str(simulation["mission_spec"]))
        if not mission_spec.is_absolute():
            simulation["mission_spec"] = str((base / mission_spec).resolve())
        out_dir = Path(str(simulation["out_dir"]))
        if not out_dir.is_absolute():
            simulation["out_dir"] = str((base / out_dir).resolve())
    return problem

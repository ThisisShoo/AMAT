from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Any

from .backends.registry import get_backend
from .domain import canonicalize_optimization_problem, validate_optimization_problem
from .io import read_json, write_json


def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_file(path: str | Path) -> dict[str, Any]:
    raw = read_json(path)
    warnings = validate_optimization_problem(raw)
    problem = canonicalize_optimization_problem(raw, path)
    return {
        "ok": True,
        "status": "valid",
        "optimization_id": problem["optimization_id"],
        "mission_id": problem["mission_id"],
        "backend": problem["backend"],
        "warnings": warnings,
    }


def solve_file(path: str | Path, out_dir: str | Path, run: bool = False) -> dict[str, Any]:
    raw = read_json(path)
    problem = canonicalize_optimization_problem(raw, path)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    backend = get_backend(problem["backend"])
    result = backend.solve(problem, out, run=run)
    provenance = {
        "schema_version": "1.0.0",
        "optimization_problem_hash": _hash(problem),
        "backend_id": result.get("backend_id"),
        "module_id": result.get("module_id"),
        "python_version": platform.python_version(),
    }

    write_json(out / "optimization_problem.canonical.json", problem)
    write_json(out / "optimization_result.json", result)
    write_json(out / "provenance.json", provenance)

    return {
        "ok": result["optimization_status"] != "failed",
        "status": result["optimization_status"],
        "optimization_id": problem["optimization_id"],
        "mission_id": problem["mission_id"],
        "backend": result.get("backend_id"),
        "module": result.get("module_id"),
        "artifacts": {
            "optimization_problem": str(out / "optimization_problem.canonical.json"),
            "optimization_result": str(out / "optimization_result.json"),
            "provenance": str(out / "provenance.json"),
            **result.get("artifacts", {}),
        },
    }

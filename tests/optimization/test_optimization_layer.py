import json
from pathlib import Path

import pytest

from mission_optimization.backends.registry import get_backend
from mission_optimization.cli import main as optimization_main
from mission_optimization.domain import canonicalize_optimization_problem
from mission_optimization.service import solve_file, validate_file


def _problem(tmp_path: Path) -> Path:
    path = tmp_path / "optimization_problem.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "optimization_id": "geo_opt",
                "mission_id": "geo_opt",
                "backend": "gmat",
                "strategy": {"type": "single_candidate"},
                "simulation": {
                    "mission_spec": str(Path("examples/MEO_demo/mission_spec.json").resolve()),
                    "out_dir": str(tmp_path / "simulation"),
                },
                "design_variables": [
                    {"id": "burn.dv", "type": "scalar", "unit": "km/s", "initial": 0.0}
                ],
                "objectives": [
                    {"id": "minimize_total_delta_v", "type": "minimize", "metric": "mission.total_delta_v"}
                ],
                "constraints": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_canonical_optimization_problem_defaults_paths_relative_to_problem_file(tmp_path: Path) -> None:
    raw = {
        "optimization_id": "demo",
        "simulation": {"mission_spec": "mission_spec.json"},
    }

    problem = canonicalize_optimization_problem(raw, tmp_path / "optimization_problem.json")

    assert problem["backend"] == "gmat"
    assert problem["strategy"] == {"type": "single_candidate"}
    assert problem["simulation"]["backend"] == "gmat"
    assert problem["simulation"]["mission_spec"] == str((tmp_path / "mission_spec.json").resolve())


def test_gmat_optimization_backend_compiles_single_candidate(tmp_path: Path) -> None:
    problem_path = _problem(tmp_path)

    result = solve_file(problem_path, tmp_path / "optimization")

    assert result["ok"]
    assert result["status"] == "candidate_compiled"
    assert result["backend"] == "gmat"
    opt_result = json.loads((tmp_path / "optimization" / "optimization_result.json").read_text(encoding="utf-8"))
    assert opt_result["module_id"] == "gmat_single_candidate"
    assert opt_result["best_candidate"]["compile_status"] == "success"
    assert (tmp_path / "simulation" / "generated_mission.script").exists()


def test_optimization_cli_validate_and_solve(tmp_path: Path) -> None:
    problem_path = _problem(tmp_path)

    assert optimization_main(["validate", str(problem_path)]) == 0
    assert optimization_main(["solve", str(problem_path), "--out", str(tmp_path / "opt_cli")]) == 0
    assert (tmp_path / "opt_cli" / "optimization_problem.canonical.json").exists()


def test_validate_file_rejects_missing_mission_spec(tmp_path: Path) -> None:
    problem = tmp_path / "bad.json"
    problem.write_text(json.dumps({"optimization_id": "bad", "simulation": {}}), encoding="utf-8")

    with pytest.raises(Exception, match="simulation.mission_spec is required"):
        validate_file(problem)


def test_unknown_optimization_backend_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown optimization backend"):
        get_backend("not-gmat")

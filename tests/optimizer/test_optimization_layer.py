import json
from pathlib import Path

import pytest

from optimizer.backends.registry import get_backend
from optimizer.cli import main as optimization_main
from optimizer.domain import canonicalize_optimization_problem
from optimizer.service import solve_file, validate_file


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


def test_orekit_optimization_backend_compiles_single_candidate(tmp_path: Path) -> None:
    mission_spec = tmp_path / "mission_spec.json"
    mission_spec.write_text(
        json.dumps(
            {
                "schema_version": "1.0.0",
                "mission_id": "orekit_opt",
                "mission_name": "Orekit Optimization Smoke",
                "conventions": {
                    "time_scale": "UTC",
                    "distance_unit": "km",
                    "velocity_unit": "km/s",
                    "angle_unit": "deg",
                    "mass_unit": "kg",
                    "time_format": "ISO-8601",
                },
                "spacecraft": [
                    {
                        "id": "sat",
                        "name": "OrekitSat",
                        "epoch": "2026-01-01T00:00:00Z",
                        "frame": "EarthMJ2000Eq",
                        "state_type": "cartesian",
                        "position_km": [7000.0, 0.0, 0.0],
                        "velocity_km_s": [0.0, 7.5, 0.0],
                        "dry_mass_kg": 1000.0,
                    }
                ],
                "force_models": [
                    {
                        "id": "earth_two_body",
                        "name": "EarthTwoBody",
                        "central_body": "Earth",
                        "gravity": {"type": "point_mass"},
                    }
                ],
                "propagators": [
                    {
                        "id": "prop",
                        "name": "Prop",
                        "force_model": "earth_two_body",
                        "integrator": "RungeKutta89",
                        "accuracy": 1e-9,
                        "initial_step_s": 30.0,
                        "min_step_s": 0.1,
                        "max_step_s": 300.0,
                    }
                ],
                "mission_sequence": [
                    {
                        "phase_id": "coast",
                        "name": "Coast",
                        "steps": [
                            {
                                "step_id": "coast_60",
                                "type": "propagate",
                                "spacecraft": "sat",
                                "propagator": "prop",
                                "duration_s": 60.0,
                            }
                        ],
                    }
                ],
                "outputs": [
                    {
                        "id": "ephem",
                        "type": "spacecraft_ephemeris",
                        "spacecraft": "sat",
                        "frames": ["EarthMJ2000Eq"],
                        "state_groups": ["elapsed_time", "cartesian"],
                        "path_template": "outputs/_Ephemeris_{spacecraft}_{frame}.csv",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    problem_path = tmp_path / "optimization_problem.json"
    problem_path.write_text(
        json.dumps(
            {
                "optimization_id": "orekit_opt",
                "mission_id": "orekit_opt",
                "backend": "orekit",
                "simulation": {
                    "backend": "orekit",
                    "mission_spec": str(mission_spec),
                    "out_dir": str(tmp_path / "simulation"),
                },
            }
        ),
        encoding="utf-8",
    )

    result = solve_file(problem_path, tmp_path / "optimization")

    assert result["ok"]
    assert result["backend"] == "orekit"
    opt_result = json.loads((tmp_path / "optimization" / "optimization_result.json").read_text(encoding="utf-8"))
    assert opt_result["module_id"] == "orekit_single_candidate"
    assert (tmp_path / "simulation" / "generated_mission.py").exists()


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


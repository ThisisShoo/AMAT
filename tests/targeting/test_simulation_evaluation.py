import json
from pathlib import Path

from mission_targeting.cli import main as targeting_main
from mission_targeting.evaluation import build_acceptance_result, evaluate_simulation


def _problem() -> dict:
    return {
        "schema_version": "1.0.0",
        "problem_id": "eval_geo",
        "mission_id": "eval_geo",
        "transfer_strategy": {
            "type": "hohmann_transfer",
            "central_body": "Earth",
            "maneuver_model": "impulsive",
            "departure_apsis": "periapsis",
            "arrival_apsis": "apoapsis",
            "plane_change_policy": "concurrent_minimum_delta_v",
        },
        "initial_state": {
            "representation": "circular_orbit",
            "altitude": {"value": 300.0, "unit": "km"},
            "inclination": {"value": 0.0, "unit": "deg"},
            "raan": {"value": 0.0, "unit": "deg"},
            "epoch": "2026-01-01T00:00:00.000Z",
            "frame": "EarthMJ2000Eq",
        },
        "target": {"type": "geostationary_orbit"},
        "limits": {
            "maximum_total_delta_v": {"value": 4.5, "unit": "km/s"},
            "minimum_altitude": {"value": 200.0, "unit": "km"},
        },
        "verification": {"required_level": "L1"},
    }


def _write_simulation(tmp_path: Path) -> Path:
    sim = tmp_path / "simulation"
    outputs = sim / "outputs"
    outputs.mkdir(parents=True)
    (sim / "mission_spec.canonical.json").write_text(
        json.dumps(
            {
                "burns": [
                    {"id": "tli", "delta_v_km_s": [2.4, 0.0, 0.0]},
                    {"id": "oi", "delta_v_km_s": [1.4, 0.0, 0.0]},
                ],
                "outputs": [
                    {
                        "id": "targeted_ephemeris",
                        "type": "spacecraft_ephemeris",
                        "spacecraft": "sat",
                        "path": "outputs/_Ephemeris_TargetSat_EarthMJ2000Eq.csv",
                        "frames": ["EarthMJ2000Eq"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (outputs / "final_state_checkpoint.csv").write_text(
        "\n".join(
            [
                "TargetSat.UTCGregorian,TargetSat.ElapsedSecs,TargetSat.EarthMJ2000Eq.X,TargetSat.EarthMJ2000Eq.Y,TargetSat.EarthMJ2000Eq.Z,TargetSat.EarthMJ2000Eq.VX,TargetSat.EarthMJ2000Eq.VY,TargetSat.EarthMJ2000Eq.VZ,TargetSat.Earth.SMA,TargetSat.Earth.ECC,TargetSat.EarthMJ2000Eq.INC,TargetSat.EarthMJ2000Eq.RAAN,TargetSat.EarthMJ2000Eq.AOP,TargetSat.Earth.TA",
                "01 Jan 2026 05:16:30.000  18990.0  42164.1696  0.0  0.0  0.0  3.0746  0.0  42164.1696  0.0  0.0  0.0  0.0  0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (outputs / "_Ephemeris_TargetSat_EarthMJ2000Eq.csv").write_text(
        "\n".join(
            [
                "TargetSat.ElapsedSecs,TargetSat.EarthMJ2000Eq.X,TargetSat.EarthMJ2000Eq.Y,TargetSat.EarthMJ2000Eq.Z",
                "0.0,6678.1363,0.0,0.0",
                "18990.0,42164.1696,0.0,0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return sim


def test_evaluate_simulation_extracts_metrics_and_acceptance(tmp_path):
    sim = _write_simulation(tmp_path)

    evaluation = evaluate_simulation(_problem(), sim)
    acceptance = build_acceptance_result(_problem(), evaluation, candidate_id="candidate_001")

    assert evaluation["evaluation_status"] == "passed"
    assert evaluation["metrics"]["spacecraft.final.orbit.sma"]["value"] == 42164.1696
    assert evaluation["metrics"]["mission.total_delta_v"]["value"] == 3.8
    metric_ids = {item["metric_id"] for item in evaluation["residuals"]}
    assert "spacecraft.final.orbit.raan" not in metric_ids
    assert "spacecraft.final.orbit.aop" not in metric_ids
    assert all(item["passed"] for item in evaluation["residuals"])
    assert acceptance["acceptance_status"] == "passed"
    assert acceptance["verification_status"] == "L1_passed"


def test_evaluate_simulation_ignores_stale_ephemeris_not_declared_in_spec(tmp_path):
    sim = _write_simulation(tmp_path)
    stale = sim / "outputs" / "_Ephemeris_TargetSat_EarthFixed.csv"
    stale.write_text(
        "\n".join(
            [
                "TargetSat.ElapsedSecs,TargetSat.EarthFixed.X,TargetSat.EarthFixed.Y,TargetSat.EarthFixed.Z",
                "0.0,1.0,0.0,0.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    evaluation = evaluate_simulation(_problem(), sim)

    assert evaluation["evidence"]["minimum_altitude"]["ephemeris"].endswith("_Ephemeris_TargetSat_EarthMJ2000Eq.csv")


def test_evaluate_simulation_rejects_final_orbit_angle_miss(tmp_path):
    sim = _write_simulation(tmp_path)
    problem = _problem()
    problem["target"]["eccentricity"] = 0.01
    problem["target"]["aop"] = {"value": 1.0, "unit": "deg"}

    evaluation = evaluate_simulation(problem, sim)
    aop = next(item for item in evaluation["residuals"] if item["metric_id"] == "spacecraft.final.orbit.aop")

    assert evaluation["evaluation_status"] == "failed"
    assert not aop["passed"]
    assert aop["residual"]["value"] == -1.0


def test_targeting_cli_evaluate_writes_artifacts(tmp_path):
    sim = _write_simulation(tmp_path)
    problem = tmp_path / "target_problem.json"
    problem.write_text(json.dumps(_problem()), encoding="utf-8")
    out = tmp_path / "targeting"

    code = targeting_main(["evaluate", str(problem), "--simulation-dir", str(sim), "--out", str(out)])

    assert code == 0
    evaluation = json.loads((out / "simulation_evaluation.json").read_text(encoding="utf-8"))
    acceptance = json.loads((out / "acceptance_result.json").read_text(encoding="utf-8"))
    assert evaluation["evaluation_status"] == "passed"
    assert acceptance["acceptance_status"] == "passed"

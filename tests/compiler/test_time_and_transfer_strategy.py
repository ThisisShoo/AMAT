from copy import deepcopy
import json
import math
from pathlib import Path

import pytest

from compiler.backends.gmat.compiler import GmatCompiler
from compiler.ir.sequence import append_mission_sequence_phase
from compiler.ir.canonicalize import canonicalize
from compiler.time_formats import canonicalize_epoch, format_epoch_for_backend
from compiler.validation.validate_bounds import validate_bounds
from compiler.validation.validate_dependencies import validate_dependencies
from compiler.validation.validate_schema import validate_schema
from targeter.domain import canonicalize_target_problem, validate_target_problem
from targeter.errors import TargetingError
from targeter.initial_guess import generate_hohmann_candidate
from targeter.io import read_json
from targeter.materialization import materialize_mission_spec
import targeter.initial_guess.hohmann as hohmann_guess

TARGET_PROBLEM = {
    "schema_version": "1.0.0",
    "problem_id": "leo_300km_to_geo",
    "mission_id": "leo_300km_to_geo",
    "transfer_strategy": {
        "type": "hohmann_transfer",
        "central_body": "Earth",
        "maneuver_model": "impulsive",
        "maneuver_policy": "valid_node_low_speed",
    },
    "initial_state": {
        "representation": "circular_orbit",
        "altitude": {"value": 300.0, "unit": "km"},
        "inclination": {"value": 0.0, "unit": "deg"},
        "raan": {"value": 0.0, "unit": "deg"},
        "aop": {"value": 0.0, "unit": "deg"},
        "true_anomaly": {"value": 0.0, "unit": "deg"},
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq",
    },
    "target": {
        "type": "geostationary_orbit",
        "inclination": {"value": 0.0, "unit": "deg"},
        "eccentricity_max": 0.001,
    },
}


def _example(tmp_path: Path) -> Path:
    path = tmp_path / "target_problem.json"
    path.write_text(json.dumps(TARGET_PROBLEM, indent=2), encoding="utf-8")
    return path


def test_epoch_is_canonical_iso_and_gmat_is_rendered_at_backend_boundary(tmp_path):
    assert canonicalize_epoch("01 Jan 2026 00:00:00.000") == "2026-01-01T00:00:00.000Z"
    assert format_epoch_for_backend("2026-01-01T00:00:00.000Z", "gmat") == "01 Jan 2026 00:00:00.000"
    p = canonicalize_target_problem(read_json(_example(tmp_path)))
    candidate = generate_hohmann_candidate(p)
    spec = canonicalize(materialize_mission_spec(p, candidate))
    assert spec["spacecraft"][0]["epoch"] == "2026-01-01T00:00:00.000Z"
    script = GmatCompiler().render_gmat_script(spec, tmp_path)
    assert "TargetSat.Epoch = '01 Jan 2026 00:00:00.000';" in script
    assert "EarthFM.GravityField.Earth.Degree = 0;" in script
    assert "EarthFM.GravityField.Earth.Order = 0;" in script


def test_append_mission_sequence_phase_normalizes_and_appends():
    spec = {
        "mission_sequence": [
            {"type": "propagate", "spacecraft": "sat", "propagator": "earth_prop", "duration_s": 60.0}
        ]
    }

    phase = append_mission_sequence_phase(
        spec,
        phase_id="phase_manual",
        name="Manual phase",
        steps=[
            {
                "step_id": "manual_coast",
                "type": "propagate",
                "spacecraft": "sat",
                "propagator": "earth_prop",
                "duration_s": 120.0,
            }
        ],
    )

    assert phase == spec["mission_sequence"][-1]
    assert spec["mission_sequence"][0]["phase_id"] == "default_phase"
    assert spec["mission_sequence"][-1]["phase_id"] == "phase_manual"


def test_gmat_compiler_emits_stm_artifact_contract(tmp_path):
    p = canonicalize_target_problem(read_json(_example(tmp_path)))
    candidate = generate_hohmann_candidate(p)
    spec = canonicalize(materialize_mission_spec(p, candidate))
    spec["targeting"] = {
        "stm": {
            "enabled": True,
            "spacecraft": spec["spacecraft"][0]["id"],
            "state_vector": ["X", "Y", "Z", "VX", "VY", "VZ"],
            "decision_variables": ["initial_cartesian_state"],
        }
    }

    result = GmatCompiler().compile(spec, tmp_path)
    script = (tmp_path / "generated_mission.script").read_text(encoding="utf-8")
    contract = read_json(tmp_path / "targeting" / "stm_artifact_contract.json")

    assert result["status"] == "success"
    assert any(item["artifact_id"] == "STM_ARTIFACT_CONTRACT" for item in result["generated_artifacts"])
    assert "% STM artifact request: stm" in script
    assert "Native GMAT STM ReportFile is not emitted" in script
    assert contract["consumer"] == "targeter.solve_stm_target_state_correction"
    assert contract["artifacts"][0]["has_native_report"] is False


def test_gmat_compiler_can_emit_native_stm_report_when_parameters_are_validated(tmp_path):
    p = canonicalize_target_problem(read_json(_example(tmp_path)))
    candidate = generate_hohmann_candidate(p)
    spec = canonicalize(materialize_mission_spec(p, candidate))
    spec["targeting"] = {
        "stm": {
            "enabled": True,
            "spacecraft": spec["spacecraft"][0]["id"],
            "path": "outputs/stm.csv",
            "parameters": [
                "STM_11",
                "STM_12",
            ],
        }
    }

    script = GmatCompiler().render_gmat_script(spec, tmp_path)

    assert "Create ReportFile RF_TargetSat_STM;" in script
    assert "GMAT RF_TargetSat_STM.Add = { TargetSat.STM_11, TargetSat.STM_12 };" in script
    assert "GMAT RF_TargetSat_STM.Filename = 'stm.csv';" in script.replace("\\", "/")


def test_finite_burn_mission_spec_compiles_to_timed_finite_burn(tmp_path):
    p = canonicalize_target_problem(read_json(_example(tmp_path)))
    candidate = generate_hohmann_candidate(p)
    spec = canonicalize(materialize_mission_spec(p, candidate))
    first_burn_id = spec["burns"][0]["id"]
    spec["burns"][0] = {
        "id": first_burn_id,
        "name": spec["burns"][0]["name"],
        "type": "finite",
        "frame": "VNB",
        "origin": "Earth",
        "thrust_N": 450.0,
        "isp_s": 315.0,
        "direction": [1.0, 0.0, 0.0],
        "decrement_mass": False,
    }
    for phase in spec["mission_sequence"]:
        for step in phase["steps"]:
            if step.get("type") == "maneuver" and step.get("burn") == first_burn_id:
                step["duration_s"] = 120.0
                step["propagator"] = spec["propagators"][0]["id"]
            if step.get("type") == "event_action":
                event = next(e for e in spec["events"] if e["id"] == step["event_id"])
                for action in event["actions"]:
                    if action.get("type") == "maneuver" and action.get("burn") == first_burn_id:
                        action["duration_s"] = 120.0
                        action["propagator"] = spec["propagators"][0]["id"]

    validate_schema(spec)
    validate_dependencies(spec)
    validate_bounds(spec)
    compiler = GmatCompiler()
    compiler.validate_capability(spec)
    result = compiler.compile(spec, tmp_path)
    script = (tmp_path / "generated_mission.script").read_text(encoding="utf-8")
    manifest = read_json(tmp_path / "visualization_manifest.json")

    assert result["status"] == "success"
    assert "Create ChemicalThruster" in script
    assert "Create FiniteBurn" in script
    assert "BeginFiniteBurn" in script
    assert "Propagate " in script and "TargetSat.ElapsedSecs = 120.0" in script
    assert "EndFiniteBurn" in script
    assert manifest["finite_burns"][0]["duration_s"] == 120.0


def test_standard_case_reduces_to_coplanar_hohmann(tmp_path):
    p = canonicalize_target_problem(read_json(_example(tmp_path)))
    candidate = generate_hohmann_candidate(p)
    assert candidate["analytic_assessment"]["model"] == "two_body_impulsive_coplanar_hohmann"
    assert candidate["maneuvers"][0]["plane_change_deg"] == 0.0
    assert candidate["maneuvers"][1]["plane_change_deg"] == 0.0
    assert 3.8 < candidate["analytic_assessment"]["total_delta_v_km_s"] < 4.0


def test_inclined_case_merges_plane_change_at_apoapsis_node(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["initial_state"]["inclination"] = {"value": 28.5, "unit": "deg"}
    validate_target_problem(raw)
    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    assert candidate["analytic_assessment"]["plane_change_total_deg"] == 28.5
    assert candidate["analytic_assessment"]["plane_change_merge_target"] == "arrival"
    assert candidate["analytic_assessment"]["plane_change_node_true_anomaly_deg"] == 180.0
    assert len(candidate["maneuvers"]) == 2
    assert candidate["maneuvers"][0]["components_km_s"][1] == 0.0
    assert candidate["maneuvers"][1]["maneuver_type"] == "combined_impulsive"
    assert candidate["maneuvers"][1]["components_km_s"][1] > 0.0
    assert candidate["maneuvers"][1]["components_km_s"][2] == pytest.approx(0.0, abs=1e-12)
    spec = materialize_mission_spec(p, candidate)
    assert spec["burns"][1]["delta_v_km_s"][1] == candidate["variable_values"]["orbit_insertion.delta_v_n"]["value"]
    assert spec["burns"][1]["delta_v_km_s"][2] == pytest.approx(0.0, abs=1e-12)


def test_valid_node_low_speed_policy_phases_circular_departure_to_arrival_node(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["transfer_strategy"]["maneuver_policy"] = {
        "type": "valid_node_low_speed",
        "maneuver_model": "impulsive",
        "departure_event": {"type": "initial_state"},
        "arrival_event": {"type": "apoapsis"},
        "allow_departure_phasing": True,
        "prefer_apsis_alignment": True,
        "fallback": "split_at_nearest_valid_node",
    }
    raw["initial_state"]["inclination"] = {"value": 23.0, "unit": "deg"}
    raw["initial_state"]["aop"] = {"value": 30.0, "unit": "deg"}
    raw["initial_state"]["true_anomaly"] = {"value": 0.0, "unit": "deg"}

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)

    assert p["transfer_strategy"]["maneuver_policy"] == "valid_node_low_speed"
    assert p["transfer_strategy"]["maneuver_policy_config"]["allow_departure_phasing"] is True
    assert candidate["analytic_assessment"]["departure_phasing_applied"] is True
    assert candidate["analytic_assessment"]["plane_change_merge_target"] == "arrival"
    assert len(candidate["maneuvers"]) == 2
    assert candidate["maneuvers"][0]["event_type"] == "parameter_reaches"
    assert candidate["maneuvers"][1]["maneuver_type"] == "combined_impulsive"
    assert candidate["maneuvers"][1]["plane_change_deg"] > 0.0

    insertion = candidate["maneuvers"][1]
    assessment = candidate["analytic_assessment"]
    initial_basis = hohmann_guess._orbit_basis(
        p["initial_state"]["inclination"]["value"],
        p["initial_state"]["raan"]["value"],
        p["initial_state"]["aop"]["value"],
    )
    transfer_basis = hohmann_guess._rotate_basis_to_true_anomaly(initial_basis, assessment["departure_true_anomaly_deg"])
    target_basis = hohmann_guess._orbit_basis(
        p["target"]["inclination"]["value"],
        p["target"]["raan"]["value"],
        p["target"]["aop"]["value"],
    )
    ta = float(insertion["true_anomaly_deg"])
    r_hat = (
        math.cos(math.radians(ta)) * transfer_basis["p"][0] + math.sin(math.radians(ta)) * transfer_basis["q"][0],
        math.cos(math.radians(ta)) * transfer_basis["p"][1] + math.sin(math.radians(ta)) * transfer_basis["q"][1],
        math.cos(math.radians(ta)) * transfer_basis["p"][2] + math.sin(math.radians(ta)) * transfer_basis["q"][2],
    )
    v_before = hohmann_guess._transfer_velocity_vector(
        transfer_basis,
        p["transfer_strategy"]["central_body_mu"]["value"],
        assessment["transfer_sma_km"],
        assessment["transfer_eccentricity"],
        ta,
    )
    v_axis = hohmann_guess._unit(v_before)
    n_axis = transfer_basis["h"]
    b_axis = hohmann_guess._unit(hohmann_guess._cross(v_axis, n_axis))
    dv_v, dv_n, dv_b = insertion["components_km_s"]
    dv_vec = (
        dv_v * v_axis[0] + dv_n * n_axis[0] + dv_b * b_axis[0],
        dv_v * v_axis[1] + dv_n * n_axis[1] + dv_b * b_axis[1],
        dv_v * v_axis[2] + dv_n * n_axis[2] + dv_b * b_axis[2],
    )
    v_after = (
        v_before[0] + dv_vec[0],
        v_before[1] + dv_vec[1],
        v_before[2] + dv_vec[2],
    )
    final_h = hohmann_guess._unit(hohmann_guess._cross(r_hat, v_after))
    assert abs(hohmann_guess._dot(final_h, target_basis["h"])) == pytest.approx(1.0)

    spec = materialize_mission_spec(p, candidate)
    transfer_event = next(e for e in spec["events"] if e["id"] == "event_transfer_injection")
    insertion_burn = next(b for b in spec["burns"] if b["id"] == "orbit_insertion")
    assert transfer_event["type"] == "parameter_reaches"
    assert transfer_event["stop_condition"]["parameter"] == "Earth.TA"
    assert insertion_burn["delta_v_km_s"][1] != 0.0


def test_circular_target_altitude_canonicalizes_to_radius_plus_altitude(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["target"] = {
        "type": "circular_orbit",
        "altitude": {"value": 2000.0, "unit": "km"},
        "inclination": {"value": 60.0, "unit": "deg"},
    }

    p = canonicalize_target_problem(raw)

    assert p["target"]["sma"]["value"] == 8378.1363


def test_luna_centered_target_problem_uses_lunar_constants(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["problem_id"] = "lunar_low_to_high"
    raw["mission_id"] = "lunar_low_to_high"
    raw["transfer_strategy"]["central_body"] = "Luna"
    raw["transfer_strategy"]["type"] = "two_impulse_apsidal_transfer"
    raw["initial_state"]["frame"] = "LunaMJ2000Eq"
    raw["target"] = {
        "type": "circular_orbit",
        "altitude": {"value": 2000.0, "unit": "km"},
        "inclination": {"value": 10.0, "unit": "deg"},
    }

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    spec = materialize_mission_spec(p, candidate)

    assert p["transfer_strategy"]["central_body_radius"] == {"value": 1737.4, "unit": "km"}
    assert p["transfer_strategy"]["central_body_mu"] == {"value": 4902.800118, "unit": "km^3/s^2"}
    assert p["initial_state"]["sma"]["value"] == pytest.approx(2037.4)
    assert p["target"]["sma"]["value"] == pytest.approx(3737.4)
    assert spec["force_models"][0]["central_body"] == "Luna"
    assert spec["propagators"][0]["id"] == "luna_prop"
    assert spec["outputs"][0]["frames"] == ["LunaMJ2000Eq", "LunaFixed"]
    assert spec["outputs"][2]["body"] == "Luna"


def test_off_node_plane_change_is_seeded_at_transfer_arc_node(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["transfer_strategy"]["maneuver_policy"] = {
        "type": "valid_node_low_speed",
        "maneuver_model": "impulsive",
        "departure_event": {"type": "initial_state"},
        "arrival_event": {"type": "apoapsis"},
        "allow_departure_phasing": False,
        "prefer_apsis_alignment": False,
        "fallback": "split_at_nearest_valid_node",
    }
    raw["initial_state"]["inclination"] = {"value": 23.0, "unit": "deg"}
    raw["initial_state"]["aop"] = {"value": 30.0, "unit": "deg"}
    raw["initial_state"]["true_anomaly"] = {"value": 0.0, "unit": "deg"}
    validate_target_problem(raw)

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)

    assert len(candidate["maneuvers"]) == 3
    node_burn = candidate["maneuvers"][1]
    assert node_burn["maneuver_id"] == "plane_change_at_node"
    assert node_burn["event_type"] == "parameter_reaches"
    assert node_burn["true_anomaly_deg"] == 150.0
    assert node_burn["components_km_s"][1] > 0.0
    assert node_burn["components_km_s"][2] != 0.0
    assert candidate["analytic_assessment"]["plane_change_merge_target"] is None
    assert candidate["analytic_assessment"]["plane_change_node_true_anomaly_deg"] == 150.0

    spec = materialize_mission_spec(p, candidate)
    node_event = next(e for e in spec["events"] if e["id"] == "event_plane_change_at_node")
    assert node_event["type"] == "parameter_reaches"
    assert node_event["stop_condition"] == {"parameter": "Earth.TA", "value": 150.0}
    ground_track = next(out for out in spec["outputs"] if out["type"] == "ground_track")
    assert ground_track == {
        "id": "earth_ground_track",
        "type": "ground_track",
        "spacecraft": "sat",
        "body": "Earth",
        "path": "outputs/_GroundTrack_{spacecraft}_{body}.csv",
    }
    ephemeris = next(out for out in spec["outputs"] if out["id"] == "targeted_ephemeris")
    assert ephemeris["frames"] == ["EarthMJ2000Eq", "EarthFixed"]
    assert ephemeris["path_template"] == "outputs/_Ephemeris_{spacecraft}_{frame}.csv"

    coast_step = next(
        step
        for phase in spec["mission_sequence"]
        for step in phase["steps"]
        if step.get("step_id") == "propagate_post_insertion_two_days"
    )
    assert coast_step == {
        "step_id": "propagate_post_insertion_two_days",
        "type": "propagate",
        "spacecraft": "sat",
        "propagator": "earth_prop",
        "duration_s": 172800.0,
    }

    final_phase = spec["mission_sequence"][-1]
    assert final_phase["phase_id"] == "phase_006_final_state"
    assert final_phase["steps"] == [
        {"step_id": "checkpoint_final_state", "type": "checkpoint", "checkpoint_id": "final_state_checkpoint"}
    ]


def test_elliptical_initial_state_supported_at_selected_apsis(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["transfer_strategy"]["type"] = "two_impulse_apsidal_transfer"
    raw["initial_state"] = {
        "representation": "keplerian",
        "sma": {"value": 10000.0, "unit": "km"},
        "eccentricity": 0.2,
        "inclination": {"value": 0.0, "unit": "deg"},
        "raan": {"value": 0.0, "unit": "deg"},
        "aop": {"value": 0.0, "unit": "deg"},
        "true_anomaly": {"value": 0.0, "unit": "deg"},
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq"
    }
    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    assert candidate["analytic_assessment"]["departure_radius_km"] == 8000.0
    spec = materialize_mission_spec(p, candidate)
    sc = spec["spacecraft"][0]
    assert sc["sma_km"] == 10000.0
    assert sc["ecc"] == 0.2


def test_keplerian_initial_state_can_depart_away_from_apsis(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["transfer_strategy"]["type"] = "two_impulse_apsidal_transfer"
    raw["initial_state"] = {
        "representation": "keplerian",
        "sma": {"value": 10000.0, "unit": "km"},
        "eccentricity": 0.2,
        "inclination": {"value": 0.0, "unit": "deg"},
        "raan": {"value": 0.0, "unit": "deg"},
        "aop": {"value": 0.0, "unit": "deg"},
        "true_anomaly": {"value": 45.0, "unit": "deg"},
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq",
    }

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    spec = materialize_mission_spec(p, candidate)

    assert p["initial_state"]["true_anomaly"]["value"] == 45.0
    assert candidate["maneuvers"][0]["event_type"] == "immediate"
    assert candidate["maneuvers"][0]["true_anomaly_deg"] == 45.0
    assert spec["mission_sequence"][1]["steps"][0]["type"] == "maneuver"


def test_cartesian_initial_state_is_supported_and_materialized_as_cartesian(tmp_path):
    raw = read_json(_example(tmp_path))
    radius = 6678.1363
    raw["initial_state"] = {
        "representation": "cartesian",
        "position_km": [radius, 0.0, 0.0],
        "velocity_km_s": [0.0, math.sqrt(398600.435507 / radius), 0.0],
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq",
    }

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    spec = materialize_mission_spec(p, candidate)

    assert p["initial_state"]["sma"]["value"] == pytest.approx(radius)
    assert p["initial_state"]["eccentricity"] == pytest.approx(0.0, abs=1e-12)
    assert p["initial_state"]["inclination"]["value"] == pytest.approx(0.0, abs=1e-12)
    assert p["initial_state"]["true_anomaly"]["value"] == pytest.approx(0.0, abs=1e-12)
    assert spec["spacecraft"][0]["state_type"] == "cartesian"
    assert spec["spacecraft"][0]["position_km"] == [radius, 0.0, 0.0]
    assert spec["spacecraft"][0]["velocity_km_s"][0] == 0.0
    assert spec["spacecraft"][0]["velocity_km_s"][1] == pytest.approx(math.sqrt(398600.435507 / radius))
    assert spec["spacecraft"][0]["velocity_km_s"][2] == 0.0


def test_cometary_initial_and_target_states_are_supported(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["transfer_strategy"]["type"] = "two_impulse_apsidal_transfer"
    raw["initial_state"] = {
        "representation": "cometary",
        "periapsis_radius": {"value": 8000.0, "unit": "km"},
        "eccentricity": 0.2,
        "inclination": {"value": 5.0, "unit": "deg"},
        "raan": {"value": 10.0, "unit": "deg"},
        "aop": {"value": 20.0, "unit": "deg"},
        "true_anomaly": {"value": 30.0, "unit": "deg"},
        "epoch": "2026-01-01T00:00:00Z",
        "frame": "EarthMJ2000Eq",
    }
    raw["target"] = {
        "type": "cometary_state",
        "periapsis_radius": {"value": 42164.1696, "unit": "km"},
        "eccentricity": 0.0,
        "inclination": {"value": 0.0, "unit": "deg"},
        "raan": {"value": 0.0, "unit": "deg"},
        "aop": {"value": 0.0, "unit": "deg"},
    }

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    spec = materialize_mission_spec(p, candidate)

    assert p["initial_state"]["sma"]["value"] == pytest.approx(10000.0)
    assert p["target"]["sma"]["value"] == pytest.approx(42164.1696)
    assert candidate["generation_status"] == "candidate_generated"
    assert spec["spacecraft"][0]["state_type"] == "keplerian"


def test_maneuver_policy_can_depart_at_explicit_true_anomaly(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["transfer_strategy"]["maneuver_policy"] = {
        "type": "valid_node_low_speed",
        "departure_event": {"type": "true_anomaly", "value": {"value": 45.0, "unit": "deg"}},
        "arrival_event": {"type": "true_anomaly", "value": {"value": 180.0, "unit": "deg"}},
        "allow_departure_phasing": False,
    }

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    spec = materialize_mission_spec(p, candidate)

    assert candidate["maneuvers"][0]["event_type"] == "parameter_reaches"
    assert candidate["maneuvers"][0]["true_anomaly_deg"] == 45.0
    assert candidate["maneuvers"][-1]["event_type"] == "parameter_reaches"
    departure_event = next(e for e in spec["events"] if e["id"] == "event_transfer_injection")
    arrival_event = next(e for e in spec["events"] if e["id"] == "event_orbit_insertion")
    assert departure_event["stop_condition"] == {"parameter": "Earth.TA", "value": 45.0}
    assert arrival_event["stop_condition"] == {"parameter": "Earth.TA", "value": 180.0}


def test_maneuver_policy_node_shortcuts_resolve_to_true_anomaly(tmp_path):
    raw = read_json(_example(tmp_path))
    raw["transfer_strategy"]["maneuver_policy"] = {
        "type": "valid_node_low_speed",
        "departure_event": {"type": "ascending_node"},
        "arrival_event": {"type": "descending_node"},
        "allow_departure_phasing": False,
    }
    raw["initial_state"]["aop"] = {"value": 30.0, "unit": "deg"}
    raw["target"]["type"] = "keplerian_state"
    raw["target"]["sma"] = {"value": 42164.1696, "unit": "km"}
    raw["target"]["eccentricity"] = 0.0
    raw["target"]["aop"] = {"value": 20.0, "unit": "deg"}

    p = canonicalize_target_problem(raw)
    candidate = generate_hohmann_candidate(p)
    spec = materialize_mission_spec(p, candidate)

    assert p["transfer_strategy"]["departure_true_anomaly"] == 330.0
    assert p["transfer_strategy"]["arrival_true_anomaly"] == 160.0
    assert p["transfer_strategy"]["departure_event"]["resolved_true_anomaly"] == {"value": 330.0, "unit": "deg"}
    assert p["transfer_strategy"]["arrival_event"]["resolved_true_anomaly"] == {"value": 160.0, "unit": "deg"}
    assert candidate["maneuvers"][0]["event_type"] == "parameter_reaches"
    assert candidate["maneuvers"][-1]["event_type"] == "parameter_reaches"
    departure_event = next(e for e in spec["events"] if e["id"] == "event_transfer_injection")
    arrival_event = next(e for e in spec["events"] if e["id"] == "event_orbit_insertion")
    assert departure_event["stop_condition"] == {"parameter": "Earth.TA", "value": 330.0}
    assert arrival_event["stop_condition"] == {"parameter": "Earth.TA", "value": 160.0}


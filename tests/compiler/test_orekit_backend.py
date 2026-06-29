import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from compiler.artifacts.bundle import compile_bundle, validate_mission
from compiler.backends.registry import get_backend


def _orekit_two_body_spec() -> dict:
    return {
        "schema_version": "2.0.0",
        "mission_id": "orekit_two_body",
        "mission_name": "Orekit Two Body",
        "conventions": {
            "time_scale": "UTC",
            "epoch_format": "ISO-8601",
            "distance_unit": "km",
            "velocity_unit": "km/s",
            "angle_unit": "deg",
            "mass_unit": "kg",
        },
        "spacecraft": [
            {
                "id": "sat",
                "name": "OrekitSat",
                "epoch": "2026-01-01T00:00:00Z",
                "reference_frame": "EarthMJ2000Eq",
                "dry_mass": 1000.0,
                "orbit_state": {
                    "representation": "Keplerian",
                    "keplerian": {
                        "semi_major_axis": 7000.0,
                        "eccentricity": 0.001,
                        "inclination": 28.5,
                        "right_ascension_of_ascending_node": 10.0,
                        "argument_of_periapsis": 20.0,
                        "anomaly": 30.0,
                        "anomaly_type": "True",
                    },
                },
            }
        ],
        "force_models": [
            {
                "id": "earth_two_body",
                "name": "EarthTwoBody",
                "central_body": "Earth",
                "gravity": {"model": "PointMass"},
            }
        ],
        "propagators": [
            {
                "id": "prop",
                "name": "OrekitProp",
                "force_model": "earth_two_body",
                "propagator_type": "NumericalPropagator",
                "integrator": "RungeKutta89",
                "accuracy": 1e-9,
                "initial_step": 30.0,
                "minimum_step": 0.1,
                "maximum_step": 300.0,
            }
        ],
        "mission_sequence": [
            {
                "phase_id": "coast",
                "name": "Coast",
                "steps": [
                    {
                        "step_id": "coast_10_min",
                        "command": "Propagate",
                        "spacecraft": "sat",
                        "propagator": "prop",
                        "duration": 600.0,
                    }
                ],
            }
        ],
        "outputs": [
            {
                "id": "ephem",
                "type": "EphemerisFile",
                "spacecraft": "sat",
                "frames": ["EarthMJ2000Eq"],
                "state_groups": ["ElapsedTime", "Cartesian"],
                "path_template": "outputs/{spacecraft}_{frame}.eph.csv",
            }
        ],
    }


def test_orekit_backend_compiles_two_body_runner(tmp_path: Path) -> None:
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(_orekit_two_body_spec()), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit", artifact_profile="debug")

    compile_result = result["compile_result"]
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    manifest = json.loads((tmp_path / "simulation" / "artifact_manifest.json").read_text(encoding="utf-8"))

    assert compile_result["status"] == "success"
    assert compile_result["backend_id"] == "orekit"
    compile(script, "generated_mission.py", "exec")
    assert "OREKIT_DATA_PATH" in script
    assert "KeplerianPropagator" in script
    assert f'{{sc_name}}.{{central_body}}.SMA' in script
    assert f'{{sc_name}}.{{frame_name}}.INC' in script
    assert "--no-save-script" in script
    assert '"backend": "orekit"' in json.dumps(manifest)


def test_orekit_backend_runtime_uses_output_step_separately_from_max_step(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["outputs"][0]["step"] = 120.0
    spec["propagators"][0]["maximum_step"] = 300.0
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    assert result["compile_result"]["artifact_profile"] == "standard"
    assert (tmp_path / "simulation" / "mission_spec.backend_ir.json").exists()
    assert not (tmp_path / "simulation" / "mission_spec.canonical.json").exists()
    assert not (tmp_path / "simulation" / "validation_report.json").exists()
    assert not (tmp_path / "simulation" / "artifact_manifest.json").exists()
    assert '"step_s": 120.0' in script
    assert '"max_step_s": 300.0' in script
    assert "_sample_step_for_spacecraft" in script
    assert "amat_output_states" in script


def test_compile_bundle_debug_profile_writes_audit_artifacts(tmp_path: Path) -> None:
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(_orekit_two_body_spec()), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit", artifact_profile="debug")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    assert result["compile_result"]["artifact_profile"] == "debug"
    assert (tmp_path / "simulation" / "mission_spec.backend_ir.json").exists()
    assert (tmp_path / "simulation" / "mission_spec.canonical.json").exists()
    assert (tmp_path / "simulation" / "validation_report.json").exists()
    assert (tmp_path / "simulation" / "artifact_manifest.json").exists()


def test_orekit_backend_accepts_non_vnb_impulsive_burn_frames() -> None:
    spec = _orekit_two_body_spec()
    spec["maneuvers"] = [{"id": "dv", "name": "DV", "maneuver_type": "ImpulsiveBurn", "reference_frame": "EarthMJ2000Eq", "delta_v": [0.001, 0.0, 0.0]}]
    spec["mission_sequence"][0]["steps"].insert(0, {"step_id": "burn", "command": "Maneuver", "spacecraft": "sat", "maneuver": "dv"})

    report = validate_mission(spec, "orekit")

    assert report["status"] == "passed", report


def test_orekit_backend_accepts_finite_burn_steps(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["maneuvers"] = [
        {
            "id": "finite",
            "name": "Finite",
            "maneuver_type": "FiniteBurn",
            "reference_frame": "LVLH",
            "thrust": 20.0,
            "specific_impulse": 300.0,
            "direction": [0.0, 1.0, 0.0],
        }
    ]
    spec["mission_sequence"][0]["steps"] = [
        {
            "step_id": "finite_burn",
            "command": "Maneuver",
            "spacecraft": "sat",
            "propagator": "prop",
            "maneuver": "finite",
            "duration": 120.0,
        }
    ]
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    assert "def execute_maneuver" in script
    assert "_finite_burn_direction" in script


def test_orekit_backend_accepts_gmat_like_output_aliases_and_body_ephemeris() -> None:
    spec = _orekit_two_body_spec()
    spec["outputs"] = [
        {
            "id": "history",
            "type": "StateHistory",
            "spacecraft": "sat",
            "frames": ["EarthMJ2000Eq"],
            "path_template": "outputs/{spacecraft}_{frame}_history.eph.csv",
        },
        {
            "id": "body",
            "type": "BodyEphemeris",
            "body": "Earth",
            "reference_frame": "EarthMJ2000Eq",
            "path": "outputs/Earth_EarthMJ2000Eq.body.eph.csv",
        },
    ]

    report = validate_mission(spec, "orekit")

    assert report["status"] == "passed", report
    assert any("body ephemeris output" in check["message"] for check in report["checks"])


def test_orekit_backend_accepts_periapsis_true_anomaly_and_node_events() -> None:
    spec = _orekit_two_body_spec()
    spec["event_detectors"] = [
        {
            "id": "peri",
            "event_detector_type": "ApsideDetector",
            "event": "periapsis",
            "spacecraft": "sat",
            "propagator": "prop",
            "central_body": "Earth",
            "actions": [],
        },
        {
            "id": "ta",
            "event_detector_type": "ParameterCondition",
            "spacecraft": "sat",
            "propagator": "prop",
            "stop_condition": {"parameter": "Earth.TA", "value": 90.0},
            "actions": [],
        },
        {
            "id": "node",
            "event_detector_type": "NodeDetector",
            "spacecraft": "sat",
            "propagator": "prop",
            "reference_frame": "EarthMJ2000Eq",
            "node": "either",
            "actions": [],
        },
    ]
    spec["mission_sequence"][0]["steps"] = [
        {"step_id": "peri_step", "command": "EventAction", "event_id": "peri"},
        {"step_id": "ta_step", "command": "EventAction", "event_id": "ta"},
        {"step_id": "node_step", "command": "EventAction", "event_id": "node"},
    ]

    report = validate_mission(spec, "orekit")

    assert report["status"] == "passed"


def test_orekit_backend_accepts_general_event_forms() -> None:
    spec = _orekit_two_body_spec()
    spec["event_detectors"] = [
        {
            "id": "date",
            "event_detector_type": "DateDetector",
            "spacecraft": "sat",
            "propagator": "prop",
            "epoch": "2026-01-01T00:30:00Z",
            "actions": [],
        },
        {
            "id": "distance",
            "event_detector_type": "DistanceThresholdDetector",
            "spacecraft": "sat",
            "propagator": "prop",
            "body": "Luna",
            "threshold_km": 400000.0,
            "direction": "either",
            "actions": [],
        },
        {
            "id": "soi",
            "event_detector_type": "SOICrossingDetector",
            "spacecraft": "sat",
            "propagator": "prop",
            "body": "Luna",
            "central_body": "Earth",
            "actions": [],
        },
        {
            "id": "elevation",
            "event_detector_type": "ElevationDetector",
            "spacecraft": "sat",
            "propagator": "prop",
            "station": {"body": "Earth", "latitude_deg": 30.0, "longitude_deg": -90.0, "altitude_km": 0.0},
            "elevation_deg": 10.0,
            "actions": [],
        },
        {
            "id": "eclipse",
            "event_detector_type": "EclipseDetector",
            "spacecraft": "sat",
            "propagator": "prop",
            "occulting_body": "Earth",
            "event": "entry",
            "actions": [],
        },
    ]
    spec["mission_sequence"][0]["steps"] = [
        {"step_id": f"{event['id']}_step", "command": "EventAction", "event_id": event["id"]}
        for event in spec["event_detectors"]
    ]

    report = validate_mission(spec, "orekit")

    assert report["status"] == "passed", report


def test_orekit_backend_accepts_topocentric_output_frame(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["reference_frames"] = [
        {
            "id": "gs",
            "name": "DemoStation",
            "type": "Topocentric",
            "origin": "Earth",
            "axes": "Topocentric",
            "definition": {
                "latitude_deg": 35.0,
                "longitude_deg": -106.0,
                "altitude_km": 1.6,
            },
        }
    ]
    spec["outputs"][0]["frames"] = ["DemoStation"]
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    assert "TopocentricFrame" in script
    assert '"kind": "topocentric"' in script


def test_orekit_compile_writes_visualization_manifest_with_static_body_context(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["reference_frames"] = [
        {
            "id": "earth_mj2000eq",
            "name": "EarthMJ2000Eq",
            "origin": "Earth",
            "axes": "MJ2000Eq",
            "type": "BodyInertial",
        }
    ]
    spec["outputs"][0]["frames"] = ["EarthMJ2000Eq", "EarthFixed"]
    spec["outputs"].append(
        {
            "id": "earth_ground_track",
            "type": "GroundTrack",
            "spacecraft": "sat",
            "body": "Earth",
            "path": "outputs/_GroundTrack_{spacecraft}_{body}.csv",
        }
    )
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    manifest = json.loads((tmp_path / "simulation" / "visualization_manifest.json").read_text(encoding="utf-8"))
    runtime_script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    frames = {entry["name"]: entry for entry in manifest["frames"]}
    ephemeris_frames = {entry["frame"] for entry in manifest["spacecraft_ephemerides"]}
    ground_tracks = manifest["ground_tracks"]

    assert "Earth" in manifest["force_model_bodies"]
    assert frames["EarthMJ2000Eq"]["origin"] == "Earth"
    assert frames["EarthFixed"]["origin"] == "Earth"
    assert frames["EarthFixed"]["axes"] == "BodyFixed"
    assert ephemeris_frames == {"EarthMJ2000Eq", "EarthFixed"}
    assert ground_tracks
    assert ground_tracks[0]["file"] == "outputs/_GroundTrack_OrekitSat_Earth.csv"
    assert "OrekitSat_EarthFixed.eph.csv" in runtime_script
    assert "_GroundTrack_OrekitSat_Earth.csv" in runtime_script
    assert "getITRF" in runtime_script
    assert '"mode": "frame_fallback"' in runtime_script


def test_orekit_backend_accepts_major_body_fixed_output_frames(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["spacecraft"][0]["reference_frame"] = "MarsMJ2000Eq"
    spec["force_models"][0]["central_body"] = "Mars"
    spec["outputs"][0]["frames"] = ["MarsMJ2000Eq", "MarsMJ2000Ec", "MarsFixed"]
    spec["outputs"].append(
        {
            "id": "mars_ground_track",
            "type": "GroundTrack",
            "spacecraft": "sat",
            "body": "Mars",
            "path": "outputs/_GroundTrack_{spacecraft}_{body}.csv",
        }
    )
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    assert "OrekitSat_MarsFixed.eph.csv" in script
    assert "_GroundTrack_OrekitSat_Mars.csv" in script
    assert "getBodyOrientedFrame" in script


def test_orekit_backend_compiles_expanded_force_model_hooks(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["spacecraft"][0]["drag_area"] = 12.0
    spec["spacecraft"][0]["drag_coefficient"] = 2.2
    spec["spacecraft"][0]["srp_area"] = 10.0
    spec["spacecraft"][0]["coefficient_of_reflectivity"] = 1.3
    spec["force_models"][0]["gravity"] = {"model": "SphericalHarmonic", "degree": 4, "order": 4}
    spec["force_models"][0]["point_masses"] = ["Luna", "Sun"]
    spec["force_models"][0]["third_body_gravity"] = {"enabled": True, "bodies": ["Luna", "Sun"]}
    spec["force_models"][0]["drag"] = {"enabled": True, "atmosphere_model": "HarrisPriester"}
    spec["force_models"][0]["solar_radiation_pressure"] = {"enabled": True}
    spec["force_models"][0]["relativity"] = {"enabled": True}
    spec["force_models"][0]["solid_tides"] = {"enabled": True}
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    assert "NumericalPropagator" in script
    assert "HolmesFeatherstoneAttractionModel" in script
    assert "ThirdBodyAttraction" in script
    assert "HarrisPriester" in script
    assert "SolarRadiationPressure" in script
    assert "Relativity" in script
    assert "SolidTides" in script


def test_orekit_compile_writes_spice_requests_for_body_ephemeris_fallback(tmp_path: Path) -> None:
    spec = _orekit_two_body_spec()
    spec["outputs"].append(
        {
            "id": "custom_body",
            "type": "BodyEphemeris",
            "body": "CustomProbe",
            "reference_frame": "EarthMJ2000Eq",
            "source": "SPICE",
            "dependency_id": "dep_custom",
            "path": "outputs/CustomProbe_EarthMJ2000Eq.body.eph.csv",
        }
    )
    spec["external_dependencies"] = [
        {
            "id": "dep_custom",
            "type": "SPICEEphemeris",
            "provider": "SPICE",
            "target": {"name": "CustomProbe"},
            "observer": {"name": "Earth"},
            "time_range": {
                "start": "2026-01-01T00:00:00Z",
                "stop": "2026-01-01T01:00:00Z",
                "step_s": 300,
            },
            "frame": {"name": "J2000"},
        }
    ]
    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    result = compile_bundle(spec_path, tmp_path / "simulation", "orekit")

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    spice_requests = tmp_path / "simulation" / "dependencies" / "spice_requests.json"
    assert spice_requests.exists()
    assert any(item["type"] == "spice_requests" for item in result["compile_result"]["generated_artifacts"])
    script = (tmp_path / "simulation" / "generated_mission.py").read_text(encoding="utf-8")
    assert '"source": "SPICE"' in script
    assert '"skip_runtime": true' in script


def test_orekit_backend_is_registered() -> None:
    assert get_backend("orekit").backend_id == "orekit"
    assert get_backend("OREKIT").backend_id == "orekit"


def test_generated_orekit_runner_executes_when_runtime_is_available(tmp_path: Path) -> None:
    if not os.environ.get("OREKIT_DATA_PATH"):
        pytest.skip("OREKIT_DATA_PATH is not set")
    try:
        import jpype  # noqa: F401
        import orekit_jpype  # noqa: F401
    except Exception as exc:
        pytest.skip(f"Orekit JPype runtime is unavailable: {exc}")

    spec_path = tmp_path / "mission_spec.json"
    spec_path.write_text(json.dumps(_orekit_two_body_spec()), encoding="utf-8")
    out_dir = tmp_path / "simulation"
    compile_bundle(spec_path, out_dir, "orekit")

    proc = subprocess.run(
        [sys.executable, str(out_dir / "generated_mission.py"), "--run"],
        cwd=out_dir,
        text=True,
        capture_output=True,
        timeout=120,
    )

    ephemeris = out_dir / "outputs" / "OrekitSat_EarthMJ2000Eq.eph.csv"
    report = out_dir / "outputs" / "_OrekitBackendReport.json"
    assert proc.returncode == 0, proc.stderr
    assert ephemeris.exists()
    assert report.exists()
    lines = ephemeris.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("OrekitSat.ElapsedSecs,OrekitSat.EarthMJ2000Eq.X")
    assert len(lines) > 2

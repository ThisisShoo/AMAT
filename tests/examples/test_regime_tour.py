import json
import math
from pathlib import Path

import pytest

from compiler.artifacts.bundle import compile_bundle
from compiler.io import read_json
from compiler.ir.backend_spec import to_backend_spec
from compiler.ir.canonicalize import canonicalize
from compiler.validation.validate_bounds import validate_bounds
from compiler.validation.validate_dependencies import validate_dependencies
from compiler.validation.validate_frames import validate_frames
from compiler.validation.validate_schema import validate_schema


REGIME_DIR = Path("examples/regime_tour")
GMAT_SPEC = REGIME_DIR / "mission_spec_gmat.json"
OREKIT_SPEC = REGIME_DIR / "mission_spec_orekit.json"
SETUP_SUMMARY = REGIME_DIR / "setup_summary.json"
G0_M_S2 = 9.80665


def _canonical(path: Path) -> dict:
    validate_schema(read_json(path))
    spec = canonicalize(to_backend_spec(read_json(path)))
    validate_frames(spec)
    validate_dependencies(spec)
    validate_bounds(spec)
    return spec


def _maneuver_steps(spec: dict) -> list[dict]:
    return [step for phase in spec["mission_sequence"] for step in phase["steps"] if step["type"] == "maneuver"]


@pytest.mark.parametrize("path", [GMAT_SPEC, OREKIT_SPEC])
def test_regime_tour_specs_validate(path: Path) -> None:
    _canonical(path)


def test_regime_tour_setup_uses_linear_j2_raan_drift_and_patched_conics() -> None:
    summary = json.loads(SETUP_SUMMARY.read_text(encoding="utf-8"))
    orbit = summary["initial_orbit"]
    seed = summary["patched_conic_tli_seed"]

    assert summary["date_anchor"]["mars_window_anchor_utc"] == "2026-11-12T00:00:00Z"
    assert summary["date_anchor"]["leo_departure_target_utc"] == "2026-11-02T00:00:00Z"
    assert summary["date_anchor"]["starting_orbit_epoch_utc"] == "2026-11-01T00:00:00Z"
    assert orbit["semi_major_axis_km"] == pytest.approx(6378.1363 + 300.0)
    assert orbit["eccentricity"] == 0.0
    assert orbit["true_anomaly_deg"] == 30.0
    assert orbit["starting_raan_deg"] == pytest.approx(
        (orbit["departure_raan_deg"] - orbit["linear_raan_rate_deg_per_day"]) % 360.0
    )
    assert seed["method"].endswith("solve_circular_coplanar_soi_patched_conics")
    assert seed["departure_delta_v_magnitude_km_s"] > 3.0
    assert seed["target_after_lunar_soi_exit"]["geocentric_ecliptic_inclination_deg"] == 0.0
    assert seed["target_after_lunar_soi_exit"]["geocentric_ecliptic_true_anomaly_deg"] == 0.0


@pytest.mark.parametrize("path", [GMAT_SPEC, OREKIT_SPEC])
def test_regime_tour_never_uses_point_mass_gravity(path: Path) -> None:
    spec = read_json(path)

    assert spec["force_models"]
    assert all(fm["gravity"]["model"] != "PointMass" for fm in spec["force_models"])
    assert {fm["gravity"]["model"] for fm in spec["force_models"]} == {"SphericalHarmonic"}


@pytest.mark.parametrize("path", [GMAT_SPEC, OREKIT_SPEC])
def test_regime_tour_burns_respect_twr_and_finite_duration_cap(path: Path) -> None:
    raw = read_json(path)
    spec = _canonical(path)
    mass = raw["metadata"]["provenance"]["setup_summary"]["burn_policy"]["spacecraft_mass_kg"]
    twr = raw["metadata"]["provenance"]["setup_summary"]["burn_policy"]["twr"]
    expected_thrust = mass * twr * G0_M_S2
    finite_cap = raw["metadata"]["provenance"]["setup_summary"]["burn_policy"]["finite_burn_cap_s"]
    steps_by_burn = {step["burn"]: step for step in _maneuver_steps(spec)}

    for burn in spec["burns"]:
        step = steps_by_burn.get(burn["id"])
        if burn["type"] == "finite":
            assert burn["thrust_N"] == pytest.approx(expected_thrust)
            assert step is not None
            assert 0.0 < step["duration_s"] <= finite_cap
        else:
            dv_mag = math.sqrt(sum(component * component for component in burn["delta_v_km_s"]))
            equivalent_duration = dv_mag * 1000.0 / (twr * G0_M_S2)
            assert equivalent_duration > finite_cap


def test_regime_tour_backend_variants_play_to_backend_strengths() -> None:
    gmat = read_json(GMAT_SPEC)
    orekit = read_json(OREKIT_SPEC)

    gmat_frames = set(gmat["outputs"][0]["frames"])
    orekit_frames = set(orekit["outputs"][0]["frames"])
    assert "EarthLunaRotating" in gmat_frames
    assert "EarthLunaRotating" not in orekit_frames
    assert any(event["id"] == "event_departure_raan" for event in gmat["event_detectors"])
    assert orekit["event_detectors"] == []
    assert "propagate_one_day_raan_drift" in {
        step["step_id"] for phase in orekit["mission_sequence"] for step in phase["steps"]
    }


@pytest.mark.parametrize(("path", "backend"), [(GMAT_SPEC, "gmat"), (OREKIT_SPEC, "orekit")])
def test_regime_tour_compiles_for_backend(path: Path, backend: str, tmp_path: Path) -> None:
    result = compile_bundle(path, tmp_path / backend, backend)

    assert result["compile_result"]["status"] == "success", result["compile_result"]
    assert (tmp_path / backend / "generated_mission.py").exists()
    assert (tmp_path / backend / "visualization_manifest.json").exists()
    if backend == "gmat":
        script = (tmp_path / backend / "generated_mission.script").read_text(encoding="utf-8")
        assert "EarthHighFidelity.GravityField.Earth.Degree = 8;" in script
        assert "Create CoordinateSystem EarthLunaRotating;" in script
    else:
        script = (tmp_path / backend / "generated_mission.py").read_text(encoding="utf-8")
        assert "HolmesFeatherstoneAttractionModel" in script

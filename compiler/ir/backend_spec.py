from __future__ import annotations

from copy import deepcopy
from typing import Any


PUBLIC_MISSION_SPEC_SCHEMA_VERSION = "2.0.0"
BACKEND_IR_SCHEMA_VERSION = "1.0.0"


STATE_GROUPS_TO_INTERNAL = {
    "Cartesian": "cartesian",
    "Keplerian": "keplerian",
    "Mass": "mass",
    "ElapsedTime": "elapsed_time",
    "Equinoctial": "equinoctial",
    "Attitude": "attitude",
    "Covariance": "covariance",
    "STM": "stm",
}

OUTPUT_TYPES_TO_INTERNAL = {
    "EphemerisFile": "spacecraft_ephemeris",
    "StateHistory": "state_history",
    "FinalState": "final_state",
    "GroundTrack": "ground_track",
    "BodyEphemeris": "body_ephemeris",
    "BodyEphemerisGroup": "body_ephemeris_group",
    "ReportFile": "full_ephemeris",
}

GRAVITY_MODELS_TO_INTERNAL = {
    "None": "none",
    "PointMass": "point_mass",
    "NewtonianAttraction": "point_mass",
    "SphericalHarmonic": "spherical_harmonic",
    "HolmesFeatherstone": "spherical_harmonic",
    "EGM96": "spherical_harmonic",
    "EGM2008": "spherical_harmonic",
    "Custom": "custom",
}

MANEUVER_TYPES_TO_INTERNAL = {
    "ImpulsiveBurn": "impulsive",
    "ImpulseManeuver": "impulsive",
    "FiniteBurn": "finite",
    "ContinuousThrustManeuver": "finite",
    "Custom": "custom",
}

STEP_COMMANDS_TO_INTERNAL = {
    "Propagate": "propagate",
    "Maneuver": "maneuver",
    "EventAction": "event_action",
    "Checkpoint": "checkpoint",
    "Report": "report",
    "Target": "target",
    "Optimize": "optimize",
    "Vary": "vary",
    "Achieve": "achieve",
    "Save": "save",
    "If": "if",
    "While": "while",
    "BeginFiniteBurn": "begin_finite_burn",
    "EndFiniteBurn": "end_finite_burn",
    "Custom": "custom",
}


def to_backend_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Lower the public MissionSpec v2 contract into AMAT's backend-internal IR."""
    if spec.get("schema_version") != PUBLIC_MISSION_SPEC_SCHEMA_VERSION:
        return deepcopy(spec)
    lowered = deepcopy(spec)
    lowered["schema_version"] = BACKEND_IR_SCHEMA_VERSION
    lowered["conventions"] = _lower_conventions(lowered.get("conventions", {}))
    lowered["spacecraft"] = [_lower_spacecraft(sc) for sc in lowered.get("spacecraft", [])]
    lowered["force_models"] = [_lower_force_model(fm) for fm in lowered.get("force_models", [])]
    lowered["propagators"] = [_lower_propagator(prop) for prop in lowered.get("propagators", [])]
    lowered["burns"] = [_lower_maneuver(maneuver) for maneuver in lowered.pop("maneuvers", [])]
    lowered["mission_sequence"] = [_lower_phase_or_step(item) for item in lowered.get("mission_sequence", [])]
    lowered["outputs"] = [_lower_output(output) for output in lowered.get("outputs", [])]
    lowered["checkpoints"] = [_lower_checkpoint(checkpoint) for checkpoint in lowered.get("checkpoints", [])]
    lowered["events"] = [_lower_event_detector(event) for event in lowered.pop("event_detectors", [])]
    lowered["external_dependencies"] = [_lower_external_dependency(dep) for dep in lowered.get("external_dependencies", [])]
    return lowered


def _lower_conventions(conventions: dict[str, Any]) -> dict[str, Any]:
    out = dict(conventions)
    if "epoch_format" in out and "time_format" not in out:
        out["time_format"] = out["epoch_format"]
    return out


def _lower_spacecraft(sc: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": sc["id"],
        "name": sc["name"],
        "epoch": sc["epoch"],
        "frame": sc["reference_frame"],
        "dry_mass_kg": sc["dry_mass"],
    }
    for src, dst in (
        ("drag_area", "drag_area_m2"),
        ("srp_area", "srp_area_m2"),
        ("drag_coefficient", "cd"),
        ("coefficient_of_reflectivity", "cr"),
    ):
        if src in sc:
            out[dst] = sc[src]
    state = sc["orbit_state"]
    representation = state["representation"]
    if representation == "Cartesian":
        out["state_type"] = "cartesian"
        out["position_km"] = state["cartesian"]["position"]
        out["velocity_km_s"] = state["cartesian"]["velocity"]
    elif representation == "Keplerian":
        kep = state["keplerian"]
        out.update(
            {
                "state_type": "keplerian",
                "sma_km": kep["semi_major_axis"],
                "ecc": kep["eccentricity"],
                "inc_deg": kep["inclination"],
                "raan_deg": kep["right_ascension_of_ascending_node"],
                "aop_deg": kep["argument_of_periapsis"],
                "ta_deg": kep["anomaly"],
            }
        )
    else:
        out["state_type"] = representation.lower()
    return out


def _lower_force_model(fm: dict[str, Any]) -> dict[str, Any]:
    out = dict(fm)
    gravity = dict(out.get("gravity", {}))
    if "model" in gravity:
        gravity["type"] = GRAVITY_MODELS_TO_INTERNAL.get(gravity["model"], str(gravity["model"]).lower())
    out["gravity"] = gravity
    return out


def _lower_propagator(prop: dict[str, Any]) -> dict[str, Any]:
    out = dict(prop)
    out["type"] = out.pop("propagator_type", out.get("type", "NumericalPropagator"))
    for src, dst in (("initial_step", "initial_step_s"), ("minimum_step", "min_step_s"), ("maximum_step", "max_step_s")):
        if src in out:
            out[dst] = out[src]
    return out


def _lower_maneuver(maneuver: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": maneuver["id"],
        "name": maneuver["name"],
        "type": MANEUVER_TYPES_TO_INTERNAL.get(maneuver["maneuver_type"], str(maneuver["maneuver_type"]).lower()),
        "frame": maneuver["reference_frame"],
    }
    if "origin" in maneuver:
        out["origin"] = maneuver["origin"]
    if "delta_v" in maneuver:
        out["delta_v_km_s"] = maneuver["delta_v"]
    if "thrust" in maneuver:
        out["thrust_N"] = maneuver["thrust"]
    if "specific_impulse" in maneuver:
        out["isp_s"] = maneuver["specific_impulse"]
    for key in ("direction", "decrement_mass", "duty_cycle"):
        if key in maneuver:
            out[key] = maneuver[key]
    return out


def _lower_phase_or_step(item: dict[str, Any]) -> dict[str, Any]:
    if "steps" not in item:
        return _lower_step(item)
    out = dict(item)
    out["steps"] = [_lower_step(step) for step in item.get("steps", [])]
    return out


def _lower_step(step: dict[str, Any]) -> dict[str, Any]:
    out = dict(step)
    command = out.pop("command", None)
    if command is not None:
        out["type"] = STEP_COMMANDS_TO_INTERNAL.get(command, str(command).lower())
    if "maneuver" in out:
        out["burn"] = out.pop("maneuver")
    if "duration" in out:
        out["duration_s"] = out.pop("duration")
    return out


def _lower_event_detector(event: dict[str, Any]) -> dict[str, Any]:
    out = dict(event)
    detector_type = out.pop("event_detector_type")
    if detector_type == "ParameterCondition":
        out["type"] = "parameter_reaches"
    elif detector_type in {"ApsideDetector", "Periapsis", "Apoapsis"}:
        out["type"] = "orbital_event"
        if detector_type == "Periapsis":
            out.setdefault("event", "periapsis")
        elif detector_type == "Apoapsis":
            out.setdefault("event", "apoapsis")
    elif detector_type == "NodeDetector":
        out["type"] = "node_crossing"
    elif detector_type in {"DateDetector", "DateEvent", "ElapsedDate"}:
        out["type"] = "date"
    elif detector_type in {"DistanceDetector", "DistanceThresholdDetector"}:
        out["type"] = "distance_threshold"
    elif detector_type in {"SOICrossingDetector", "SphereOfInfluenceDetector"}:
        out["type"] = "soi_crossing"
    elif detector_type in {"ElevationDetector", "GroundStationElevationDetector"}:
        out["type"] = "elevation"
    elif detector_type in {"EclipseDetector", "OccultationDetector"}:
        out["type"] = "eclipse"
    else:
        out["type"] = str(detector_type).lower()
    if "threshold" in out and "stop_condition" not in out:
        out["stop_condition"] = {
            "parameter": out.get("parameter"),
            "value": out.pop("threshold"),
        }
    for src, dst in (
        ("slope_selection", "direction"),
        ("max_check_interval", "max_check_s"),
        ("convergence_threshold", "threshold_s"),
        ("max_iteration_count", "max_iterations"),
    ):
        if src in out and dst not in out:
            out[dst] = out.pop(src)
    out["actions"] = [_lower_event_action(action) for action in out.get("actions", [])]
    return out


def _lower_event_action(action: dict[str, Any]) -> dict[str, Any]:
    out = dict(action)
    command = out.pop("command", None)
    if command is not None:
        out["type"] = STEP_COMMANDS_TO_INTERNAL.get(command, str(command).lower())
    if "maneuver" in out:
        out["burn"] = out.pop("maneuver")
    if "duration" in out:
        out["duration_s"] = out.pop("duration")
    return out


def _lower_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output)
    out["type"] = OUTPUT_TYPES_TO_INTERNAL.get(out["type"], str(out["type"]).lower())
    if "reference_frame" in out:
        out["frame"] = out.pop("reference_frame")
    if "source" in out:
        out["source"] = str(out["source"]).lower()
    if "step" in out:
        out["step_s"] = out.pop("step")
    if "state_groups" in out:
        out["state_groups"] = [STATE_GROUPS_TO_INTERNAL.get(group, str(group).lower()) for group in out["state_groups"]]
    return out


def _lower_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    out = dict(checkpoint)
    if "reference_frame" in out:
        out["frame"] = out.pop("reference_frame")
    if "state_groups" in out:
        out["state_groups"] = [STATE_GROUPS_TO_INTERNAL.get(group, str(group).lower()) for group in out["state_groups"]]
    return out


def _lower_external_dependency(dep: dict[str, Any]) -> dict[str, Any]:
    out = dict(dep)
    dep_types = {
        "SPICEEphemeris": "spice_ephemeris",
        "SPICEKernelSet": "spice_kernel_set",
        "Custom": "custom",
    }
    providers = {
        "SPICE": "spice",
        "Orekit": "orekit",
        "GMAT": "gmat",
        "Custom": "custom",
    }
    if "type" in out:
        out["type"] = dep_types.get(out["type"], str(out["type"]).lower())
    if "provider" in out:
        out["provider"] = providers.get(out["provider"], str(out["provider"]).lower())
    return out

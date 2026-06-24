from __future__ import annotations
from typing import Any

from compiler.ir.sequence import append_mission_sequence_phase

TWO_DAYS_S = 172800.0
ZERO_MANEUVER_TOLERANCE_KM_S = 1.0e-12


def _burn_name(maneuver_id: str) -> str:
    return "".join(part.capitalize() for part in maneuver_id.split("_"))


def _event_name(maneuver: dict[str, Any]) -> str:
    event = maneuver.get("event", maneuver["maneuver_id"])
    return str(event).replace("_", " ")


def _object_id(prefix: str, body: str) -> str:
    return f"{body[:1].lower()}{body[1:]}_{prefix}"


def _maneuver_magnitude_km_s(maneuver: dict[str, Any]) -> float:
    return sum(float(component) ** 2 for component in maneuver.get("components_km_s", [])) ** 0.5


def _maneuver_stop_condition(maneuver: dict[str, Any], central_body: str) -> dict[str, Any]:
    if maneuver.get("angle_kind") == "argument_of_latitude":
        return {
            "parameter": f"{central_body}.ArgumentOfLatitude",
            "value": maneuver["argument_of_latitude_deg"],
            "angle_kind": "argument_of_latitude",
            "true_anomaly_reference_deg": maneuver.get("true_anomaly_reference_deg", maneuver.get("true_anomaly_deg")),
        }
    return {
        "parameter": f"{central_body}.TA",
        "value": maneuver["true_anomaly_deg"],
        "angle_kind": "true_anomaly",
    }


def materialize_mission_spec(problem: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    state = problem["initial_state"]
    strategy = problem["transfer_strategy"]
    execution = problem.get("execution", {})
    central_body = strategy["central_body"]
    force_model_id = _object_id("fm", central_body)
    propagator_id = _object_id("prop", central_body)
    fixed_frame = f"{central_body}Fixed"
    frame = state["frame"]
    sc_id = "sat"
    sc_name = "TargetSat"
    maneuvers = [
        maneuver
        for maneuver in candidate["maneuvers"]
        if _maneuver_magnitude_km_s(maneuver) > ZERO_MANEUVER_TOLERANCE_KM_S
    ]
    burns = [
        {
            "id": maneuver["maneuver_id"],
            "name": _burn_name(maneuver["maneuver_id"]),
            "type": "impulsive",
            "frame": maneuver.get("frame", "VNB"),
            "origin": strategy["central_body"],
            "delta_v_km_s": maneuver["components_km_s"],
        }
        for maneuver in maneuvers
    ]
    if state.get("representation") == "cartesian":
        spacecraft_state = {
            "state_type": "cartesian",
            "position_km": state["position_km"],
            "velocity_km_s": state["velocity_km_s"],
        }
    else:
        spacecraft_state = {
            "state_type": "keplerian",
            "sma_km": state["sma"]["value"],
            "ecc": state["eccentricity"],
            "inc_deg": state["inclination"]["value"],
            "raan_deg": state["raan"]["value"],
            "aop_deg": state["aop"]["value"],
            "ta_deg": state["true_anomaly"]["value"],
        }
    checkpoints = [
        {"id": "initial_state", "spacecraft": sc_id, "frame": frame, "state_groups": ["keplerian", "cartesian", "elapsed_time"], "parameters": ["ElapsedSecs"], "path": "outputs/initial_state.csv", "include_header": True},
    ]
    events = []
    phase_counter = 1
    phases = [
        {"phase_id": "phase_001_initial", "name": "Initial state", "steps": [{"step_id": "checkpoint_initial", "type": "checkpoint", "checkpoint_id": "initial_state"}]},
    ]
    initial_coast_s = float(execution.get("initial_coast_s", 0.0) or 0.0)
    post_insertion_coast_s = float(execution.get("post_insertion_coast_s", TWO_DAYS_S) or TWO_DAYS_S)
    phase_index_offset = 0
    if initial_coast_s > 0.0:
        checkpoint_id = "post_initial_coast"
        event_id = "event_initial_coast"
        checkpoints.append(
            {
                "id": checkpoint_id,
                "spacecraft": sc_id,
                "frame": frame,
                "state_groups": ["keplerian", "cartesian", "elapsed_time"],
                "parameters": ["ElapsedSecs"],
                "path": f"outputs/{checkpoint_id}.csv",
                "include_header": True,
            }
        )
        events.append(
            {
                "id": event_id,
                "type": "parameter_reaches",
                "description": "Event-driven initial parking-orbit coast before transfer targeting events.",
                "spacecraft": sc_id,
                "propagator": propagator_id,
                "stop_condition": {
                    "parameter": "ElapsedSecs",
                    "value": initial_coast_s,
                },
                "actions": [
                    {"action_id": f"report_{checkpoint_id}", "type": "checkpoint", "checkpoint_id": checkpoint_id},
                ],
            }
        )
        phases.append(
            {
                "phase_id": "phase_002_initial_coast",
                "name": "Initial parking-orbit coast",
                "steps": [{"step_id": "step_initial_coast", "type": "event_action", "event_id": event_id}],
            }
        )
        phase_index_offset = 1
        phase_counter = 2
    for index, maneuver in enumerate(maneuvers, start=1):
        maneuver_id = maneuver["maneuver_id"]
        checkpoint_id = f"post_{maneuver_id}"
        event_id = f"event_{maneuver_id}"
        checkpoints.append(
            {
                "id": checkpoint_id,
                "spacecraft": sc_id,
                "frame": frame,
                "state_groups": ["keplerian", "cartesian", "elapsed_time"],
                "parameters": ["ElapsedSecs"],
                "path": f"outputs/{checkpoint_id}.csv",
                "include_header": True,
            }
        )
        if maneuver.get("event_type") == "immediate":
            phase_counter += 1
            phases.append(
                {
                    "phase_id": f"phase_{phase_counter:03d}_{maneuver_id}",
                    "name": f"{_event_name(maneuver).capitalize()} maneuver",
                    "steps": [
                        {"step_id": f"burn_{maneuver_id}", "type": "maneuver", "spacecraft": sc_id, "burn": maneuver_id},
                        {"step_id": f"report_{checkpoint_id}", "type": "checkpoint", "checkpoint_id": checkpoint_id},
                    ],
                }
            )
            if maneuver.get("post_maneuver_coast_s"):
                phase_counter += 1
                phases.append(
                    {
                        "phase_id": f"phase_{phase_counter:03d}_{maneuver_id}_coast",
                        "name": f"{_event_name(maneuver).capitalize()} coast",
                        "steps": [
                            {
                                "step_id": f"coast_after_{maneuver_id}",
                                "type": "propagate",
                                "spacecraft": sc_id,
                                "propagator": propagator_id,
                                "duration_s": float(maneuver["post_maneuver_coast_s"]),
                            }
                        ],
                    }
                )
            continue
        if maneuver.get("event_type") == "parameter_reaches":
            event = {
                "id": event_id,
                "type": "parameter_reaches",
                "description": f"Seeded {_event_name(maneuver)} for {maneuver_id}",
                "spacecraft": sc_id,
                "propagator": propagator_id,
                "stop_condition": _maneuver_stop_condition(maneuver, strategy["central_body"]),
                "actions": [
                    {"action_id": f"burn_{maneuver_id}", "type": "maneuver", "spacecraft": sc_id, "burn": maneuver_id},
                    {"action_id": f"report_{checkpoint_id}", "type": "checkpoint", "checkpoint_id": checkpoint_id},
                ],
            }
        else:
            event = {
                "id": event_id,
                "type": "orbital_event",
                "event": maneuver["event"],
                "central_body": strategy["central_body"],
                "spacecraft": sc_id,
                "propagator": propagator_id,
                "actions": [
                    {"action_id": f"burn_{maneuver_id}", "type": "maneuver", "spacecraft": sc_id, "burn": maneuver_id},
                    {"action_id": f"report_{checkpoint_id}", "type": "checkpoint", "checkpoint_id": checkpoint_id},
                ],
            }
        events.append(event)
        phase_counter += 1
        phases.append(
            {
                "phase_id": f"phase_{phase_counter:03d}_{maneuver_id}",
                "name": f"{_event_name(maneuver).capitalize()} maneuver",
                "steps": [{"step_id": f"step_{maneuver_id}", "type": "event_action", "event_id": event_id}],
            }
        )
        if maneuver.get("post_maneuver_coast_s"):
            phase_counter += 1
            phases.append(
                {
                    "phase_id": f"phase_{phase_counter:03d}_{maneuver_id}_coast",
                    "name": f"{_event_name(maneuver).capitalize()} coast",
                    "steps": [
                        {
                            "step_id": f"coast_after_{maneuver_id}",
                            "type": "propagate",
                            "spacecraft": sc_id,
                            "propagator": propagator_id,
                            "duration_s": float(maneuver["post_maneuver_coast_s"]),
                        }
                    ],
                }
            )
    spec = {
        "schema_version": "0.2.0",
        "mission_id": problem["mission_id"],
        "mission_name": f"{problem['mission_id']} node-aware targeting candidate",
        "description": "Materialized by AMAT targeting from a semantic TargetProblem and Candidate.",
        "conventions": {
            "time_scale": "UTC",
            "time_format": "ISO-8601",
            "distance_unit": "km",
            "velocity_unit": "km/s",
            "angle_unit": "deg",
            "mass_unit": "kg",
        },
        "spacecraft": [{
            "id": sc_id,
            "name": sc_name,
            "epoch": state["epoch"],
            "frame": frame,
            "dry_mass_kg": 1000.0,
            **spacecraft_state,
        }],
        "force_models": [{"id": force_model_id, "name": f"{central_body}FM", "central_body": central_body, "gravity": {"type": "point_mass"}}],
        "propagators": [{"id": propagator_id, "name": f"{central_body}Prop", "force_model": force_model_id, "integrator": "RungeKutta89", "accuracy": 1e-11, "initial_step_s": 60.0, "min_step_s": 0.1, "max_step_s": 300.0}],
        "burns": burns,
        "checkpoints": checkpoints,
        "events": events,
        "mission_sequence": phases,
        "outputs": [
            {"id": "targeted_ephemeris", "type": "spacecraft_ephemeris", "spacecraft": sc_id, "path_template": "outputs/_Ephemeris_{spacecraft}_{frame}.csv", "step_s": 300.0, "frames": [frame, fixed_frame], "state_groups": ["cartesian", "keplerian", "elapsed_time"]},
            {"id": "targeted_final_state", "type": "final_state", "spacecraft": sc_id, "path": "outputs/final_state.csv", "state_groups": ["cartesian", "keplerian", "elapsed_time"]},
            {"id": f"{central_body.lower()}_ground_track", "type": "ground_track", "spacecraft": sc_id, "body": central_body, "path": "outputs/_GroundTrack_{spacecraft}_{body}.csv"},
        ],
        "visualization": {"enabled": True, "auto_export_after_run": True, "clean_csv": True, "write_manifest": True, "include_spice_body_ephemerides": False},
    }
    phase_coast_s = float(candidate.get("phase_coast_s", 0.0) or 0.0)
    if phase_coast_s > 0.0:
        append_mission_sequence_phase(
            spec,
            phase_id=f"phase_{phase_counter + 1:03d}_phase_coast",
            name="Target-orbit phase coast",
            steps=[
                {
                    "step_id": "coast_to_phase",
                    "type": "propagate",
                    "spacecraft": sc_id,
                    "propagator": propagator_id,
                    "duration_s": phase_coast_s,
                }
            ],
        )
        phase_counter += 1
    append_mission_sequence_phase(
        spec,
        phase_id=f"phase_{phase_counter + 1:03d}_post_insertion_coast",
        name="Post-insertion two-day propagation",
        steps=[
            {
                "step_id": "propagate_post_insertion_two_days",
                "type": "propagate",
                "spacecraft": sc_id,
                "propagator": propagator_id,
                "duration_s": post_insertion_coast_s,
            }
        ],
    )
    phase_counter += 1
    checkpoints.append(
        {
            "id": "final_state_checkpoint",
            "spacecraft": sc_id,
            "frame": frame,
            "state_groups": ["keplerian", "cartesian", "elapsed_time"],
            "parameters": ["ElapsedSecs"],
            "path": "outputs/final_state_checkpoint.csv",
            "include_header": True,
        }
    )
    append_mission_sequence_phase(
        spec,
        phase_id=f"phase_{phase_counter + 1:03d}_final_state",
        name="Final state",
        steps=[{"step_id": "checkpoint_final_state", "type": "checkpoint", "checkpoint_id": "final_state_checkpoint"}],
    )
    return spec


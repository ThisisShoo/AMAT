from __future__ import annotations
from typing import Any

from compiler.ir.sequence import append_mission_sequence_phase

TWO_DAYS_S = 172800.0


def _burn_name(maneuver_id: str) -> str:
    return "".join(part.capitalize() for part in maneuver_id.split("_"))


def _event_name(maneuver: dict[str, Any]) -> str:
    event = maneuver.get("event", maneuver["maneuver_id"])
    return str(event).replace("_", " ")


def materialize_mission_spec(problem: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    state = problem["initial_state"]
    strategy = problem["transfer_strategy"]
    execution = problem.get("execution", {})
    frame = state["frame"]
    sc_id = "sat"
    sc_name = "TargetSat"
    maneuvers = candidate["maneuvers"]
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
    checkpoints = [
        {"id": "initial_state", "spacecraft": sc_id, "frame": frame, "state_groups": ["keplerian", "cartesian", "elapsed_time"], "parameters": ["ElapsedSecs"], "path": "outputs/initial_state.csv", "include_header": True},
    ]
    events = []
    phases = [
        {"phase_id": "phase_001_initial", "name": "Initial state", "steps": [{"step_id": "checkpoint_initial", "type": "checkpoint", "checkpoint_id": "initial_state"}]},
    ]
    initial_coast_s = float(execution.get("initial_coast_s", 0.0) or 0.0)
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
                "propagator": "earth_prop",
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
        if maneuver.get("event_type") == "parameter_reaches":
            event = {
                "id": event_id,
                "type": "parameter_reaches",
                "description": f"Seeded {_event_name(maneuver)} for {maneuver_id}",
                "spacecraft": sc_id,
                "propagator": "earth_prop",
                "stop_condition": {
                    "parameter": f"{strategy['central_body']}.TA",
                    "value": maneuver["true_anomaly_deg"],
                },
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
                "propagator": "earth_prop",
                "actions": [
                    {"action_id": f"burn_{maneuver_id}", "type": "maneuver", "spacecraft": sc_id, "burn": maneuver_id},
                    {"action_id": f"report_{checkpoint_id}", "type": "checkpoint", "checkpoint_id": checkpoint_id},
                ],
            }
        events.append(event)
        phases.append(
            {
                "phase_id": f"phase_{index + 1 + phase_index_offset:03d}_{maneuver_id}",
                "name": f"{_event_name(maneuver).capitalize()} maneuver",
                "steps": [{"step_id": f"step_{maneuver_id}", "type": "event_action", "event_id": event_id}],
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
            "state_type": "keplerian",
            "sma_km": state["sma"]["value"],
            "ecc": state["eccentricity"],
            "inc_deg": state["inclination"]["value"],
            "raan_deg": state["raan"]["value"],
            "aop_deg": state["aop"]["value"],
            "ta_deg": state["true_anomaly"]["value"],
            "dry_mass_kg": 1000.0,
        }],
        "force_models": [{"id": "earth_fm", "name": "EarthFM", "central_body": "Earth", "gravity": {"type": "point_mass"}}],
        "propagators": [{"id": "earth_prop", "name": "EarthProp", "force_model": "earth_fm", "integrator": "RungeKutta89", "accuracy": 1e-11, "initial_step_s": 60.0, "min_step_s": 0.1, "max_step_s": 300.0}],
        "burns": burns,
        "checkpoints": checkpoints,
        "events": events,
        "mission_sequence": phases,
        "outputs": [
            {"id": "targeted_ephemeris", "type": "spacecraft_ephemeris", "spacecraft": sc_id, "path_template": "outputs/_Ephemeris_{spacecraft}_{frame}.csv", "step_s": 300.0, "frames": [frame, "EarthFixed"], "state_groups": ["cartesian", "keplerian", "elapsed_time"]},
            {"id": "targeted_final_state", "type": "final_state", "spacecraft": sc_id, "path": "outputs/final_state.csv", "state_groups": ["cartesian", "keplerian", "elapsed_time"]},
            {"id": "earth_ground_track", "type": "ground_track", "spacecraft": sc_id, "body": "Earth", "path": "outputs/_GroundTrack_{spacecraft}_{body}.csv"},
        ],
        "visualization": {"enabled": True, "auto_export_after_run": True, "clean_csv": True, "write_manifest": True, "include_spice_body_ephemerides": False},
    }
    append_mission_sequence_phase(
        spec,
        phase_id=f"phase_{len(maneuvers) + 2 + phase_index_offset:03d}_post_insertion_coast",
        name="Post-insertion two-day propagation",
        steps=[
            {
                "step_id": "propagate_post_insertion_two_days",
                "type": "propagate",
                "spacecraft": sc_id,
                "propagator": "earth_prop",
                "duration_s": TWO_DAYS_S,
            }
        ],
    )
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
        phase_id=f"phase_{len(maneuvers) + 3 + phase_index_offset:03d}_final_state",
        name="Final state",
        steps=[{"step_id": "checkpoint_final_state", "type": "checkpoint", "checkpoint_id": "final_state_checkpoint"}],
    )
    return spec


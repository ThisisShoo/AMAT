from __future__ import annotations

from mission_compiler.errors import MissionValidationError
from mission_compiler.ir.sequence import iter_steps


def validate_dependencies(spec: dict) -> list[dict]:
    spacecraft = {x["id"] for x in spec.get("spacecraft", [])}
    force_models = {x["id"] for x in spec.get("force_models", [])}
    propagators = {x["id"] for x in spec.get("propagators", [])}
    burns = {x["id"] for x in spec.get("burns", [])}
    burns_by_id = {x["id"]: x for x in spec.get("burns", [])}
    checkpoints = {x["id"] for x in spec.get("checkpoints", [])}
    events = {x["id"] for x in spec.get("events", [])}
    step_count = sum(1 for _ in iter_steps(spec))

    problems: list[str] = []
    phase_ids: set[str] = set()
    step_ids: set[str] = set()

    for prop in spec.get("propagators", []):
        if prop["force_model"] not in force_models:
            problems.append(f"propagator {prop['id']} references missing force model {prop['force_model']}")

    for phase in spec.get("mission_sequence", []):
        phase_id = phase.get("phase_id")
        if phase_id in phase_ids:
            problems.append(f"duplicate phase_id {phase_id}")
        phase_ids.add(phase_id)


    # Validate event definitions and their ordered actions.
    for event in spec.get("events", []):
        event_id = event.get("id")
        if event.get("spacecraft") not in spacecraft:
            problems.append(f"event {event_id} references missing spacecraft {event.get('spacecraft')}")
        if event.get("propagator") not in propagators:
            problems.append(f"event {event_id} references missing propagator {event.get('propagator')}")
        etype = event.get("type")
        if etype == "parameter_reaches":
            if not event.get("stop_condition"):
                problems.append(f"event {event_id} parameter_reaches requires stop_condition")
        elif etype == "orbital_event":
            if event.get("event") not in {"periapsis", "apoapsis"}:
                problems.append(f"event {event_id} orbital_event must be periapsis or apoapsis")
            if not event.get("central_body"):
                problems.append(f"event {event_id} orbital_event requires central_body")
        elif etype == "node_crossing":
            if event.get("node") not in {"ascending", "descending", "either", "both"}:
                problems.append(f"event {event_id} node_crossing requires node = ascending, descending, either, or both")
            if not event.get("reference_frame"):
                problems.append(f"event {event_id} node_crossing requires reference_frame")
        else:
            problems.append(f"event {event_id} has unsupported type {etype}")
        for idx, action in enumerate(event.get("actions", []), start=1):
            atype = action.get("type")
            action_id = action.get("action_id", f"action_{idx}")
            if atype == "maneuver":
                if action.get("spacecraft") not in spacecraft:
                    problems.append(f"event {event_id} action {action_id} references missing spacecraft {action.get('spacecraft')}")
                if action.get("burn") not in burns:
                    problems.append(f"event {event_id} action {action_id} references missing burn {action.get('burn')}")
                elif burns_by_id[action.get("burn")].get("type") == "finite":
                    action_propagator = action.get("propagator") or event.get("propagator")
                    if action_propagator not in propagators:
                        problems.append(f"event {event_id} action {action_id} finite burn requires propagator")
                    if action.get("duration_s") is None:
                        problems.append(f"event {event_id} action {action_id} finite burn requires duration_s")
            elif atype == "checkpoint":
                if action.get("checkpoint_id") not in checkpoints:
                    problems.append(f"event {event_id} action {action_id} references missing checkpoint {action.get('checkpoint_id')}")
            elif atype == "report":
                if action.get("spacecraft") not in spacecraft:
                    problems.append(f"event {event_id} action {action_id} references missing spacecraft {action.get('spacecraft')}")
            elif atype == "custom_gmat":
                if not action.get("commands"):
                    problems.append(f"event {event_id} action {action_id} custom_gmat requires non-empty lines")
            else:
                problems.append(f"event {event_id} action {action_id} has unsupported type {atype}")

    for phase, step, index in iter_steps(spec):
        step_id = step.get("step_id", f"step_{index}")
        if step_id in step_ids:
            problems.append(f"duplicate step_id {step_id}")
        step_ids.add(step_id)
        stype = step.get("type")
        if stype == "propagate":
            if step["spacecraft"] not in spacecraft:
                problems.append(f"step {step_id} references missing spacecraft {step['spacecraft']}")
            if step["propagator"] not in propagators:
                problems.append(f"step {step_id} references missing propagator {step['propagator']}")
        elif stype == "maneuver":
            if step["spacecraft"] not in spacecraft:
                problems.append(f"step {step_id} references missing spacecraft {step['spacecraft']}")
            if step["burn"] not in burns:
                problems.append(f"step {step_id} references missing burn {step['burn']}")
            elif burns_by_id[step["burn"]].get("type") == "finite":
                if step.get("propagator") not in propagators:
                    problems.append(f"step {step_id} finite burn requires propagator")
                if step.get("duration_s") is None:
                    problems.append(f"step {step_id} finite burn requires duration_s")
        elif stype == "checkpoint":
            if step["checkpoint_id"] not in checkpoints:
                problems.append(f"step {step_id} references missing checkpoint {step['checkpoint_id']}")
        elif stype == "event_action":
            if step["event_id"] not in events:
                problems.append(f"step {step_id} references missing event {step['event_id']}")
        else:
            problems.append(f"step {step_id} has unsupported type {stype}")

    for out in spec.get("outputs", []):
        otype = out.get("type")
        if otype in {"final_state", "state_history", "spacecraft_ephemeris", "full_ephemeris", "ground_track"}:
            if out.get("spacecraft") not in spacecraft:
                problems.append(f"output {out.get('id', otype)} references missing spacecraft {out.get('spacecraft')}")
        elif otype == "body_ephemeris":
            if not out.get("body"):
                problems.append(f"body_ephemeris output {out.get('id')} requires body")
        elif otype == "body_ephemeris_group":
            if not out.get("bodies"):
                problems.append(f"body_ephemeris_group output {out.get('id')} requires bodies")
    for cp in spec.get("checkpoints", []):
        if cp["spacecraft"] not in spacecraft:
            problems.append(f"checkpoint {cp.get('id')} references missing spacecraft {cp['spacecraft']}")
        if "after_command_index" in cp and cp["after_command_index"] > step_count:
            problems.append(f"checkpoint {cp.get('id')} references after_command_index {cp['after_command_index']} but only {step_count} steps exist")

    dependency_ids = {d.get("id") for d in spec.get("external_dependencies", [])}
    for body in spec.get("bodies", []):
        ephem = body.get("ephemeris", {}) or {}
        dep_id = ephem.get("dependency_id")
        if ephem.get("source") == "spice" and dep_id and dep_id not in dependency_ids:
            problems.append(f"body {body.get('id')} references missing SPICE dependency {dep_id}")
    for dep in spec.get("external_dependencies", []):
        if dep.get("provider") == "spice" and dep.get("type") == "spice_ephemeris":
            tr = dep.get("time_range", {})
            if not tr.get("start") or not tr.get("stop"):
                problems.append(f"SPICE dependency {dep.get('id')} requires time_range.start and time_range.stop")

    if problems:
        raise MissionValidationError("; ".join(problems))
    return [{"check_id": "dependencies", "status": "passed", "severity": "error", "message": "All object, phase, step, burn, checkpoint, and event references resolve."}]

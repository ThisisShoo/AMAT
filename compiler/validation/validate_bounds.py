from __future__ import annotations

from pathlib import Path

from compiler.errors import MissionValidationError
from compiler.ir.sequence import iter_steps

MAX_DURATION_S = 31_536_000  # one year
MAX_RADIUS_KM = 1_000_000
MAX_SPEED_KM_S = 20
MIN_ORBIT_SMA_KM = 1.0
MAX_ORBIT_SMA_KM = 10_000_000
MAX_IMPULSIVE_DV_KM_S = 20.0
MAX_FINITE_BURN_DURATION_S = 7 * 24 * 3600
MAX_FINITE_THRUST_N = 1_000_000.0
MAX_GRAVITY_DEGREE = 120
MAX_GRAVITY_ORDER = 120
GMAT_BUILTIN_MAJOR_BODIES = {
    "Sun", "Mercury", "Venus", "Earth", "Luna", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"
}


def validate_bounds(spec: dict) -> list[dict]:
    problems: list[str] = []
    declared_bodies = {b.get("name") for b in spec.get("bodies", [])} | {b.get("id") for b in spec.get("bodies", [])}
    declared_bodies = {b for b in declared_bodies if b}

    for sc in spec.get("spacecraft", []):
        if sc["dry_mass_kg"] <= 0:
            problems.append(f"spacecraft {sc['id']} dry_mass_kg must be positive")
        if sc.get("state_type") == "cartesian":
            if max(abs(x) for x in sc["position_km"]) > MAX_RADIUS_KM:
                problems.append(f"spacecraft {sc['id']} position exceeds MVP bound")
            if max(abs(x) for x in sc["velocity_km_s"]) > MAX_SPEED_KM_S:
                problems.append(f"spacecraft {sc['id']} velocity exceeds MVP bound")
        elif sc.get("state_type") == "keplerian":
            if not (MIN_ORBIT_SMA_KM < sc["sma_km"] < MAX_ORBIT_SMA_KM):
                problems.append(f"spacecraft {sc['id']} sma_km is outside MVP orbit bounds")
            if sc["ecc"] < 0 or sc["ecc"] >= 1:
                problems.append(f"spacecraft {sc['id']} ecc must be in [0, 1)")

    for burn in spec.get("burns", []):
        if burn.get("type") == "finite":
            direction = burn.get("direction", [0, 0, 0])
            direction_mag = sum(float(x) * float(x) for x in direction) ** 0.5
            if direction_mag <= 0:
                problems.append(f"burn {burn['id']} direction magnitude must be positive")
            if burn.get("thrust_N", 0) <= 0:
                problems.append(f"burn {burn['id']} thrust_N must be positive")
            if burn.get("thrust_N", 0) > MAX_FINITE_THRUST_N:
                problems.append(f"burn {burn['id']} thrust_N exceeds MVP bound")
            if burn.get("isp_s", 0) <= 0:
                problems.append(f"burn {burn['id']} isp_s must be positive")
        else:
            dv = burn.get("delta_v_km_s", [0, 0, 0])
            mag = sum(x * x for x in dv) ** 0.5
            if mag <= 0:
                problems.append(f"burn {burn['id']} delta_v_km_s magnitude must be positive")
            if mag > MAX_IMPULSIVE_DV_KM_S:
                problems.append(f"burn {burn['id']} delta_v_km_s exceeds MVP bound")

    for fm in spec.get("force_models", []):
        gravity = fm.get("gravity", {})
        gtype = gravity.get("type")
        central = fm.get("central_body", "Earth")
        point_masses = list(dict.fromkeys((fm.get("point_masses") or []) + fm.get("third_body_gravity", {}).get("bodies", [])))
        for body in point_masses:
            if body == central:
                problems.append(f"force model {fm.get('id')} cannot include central body as point mass")
            # Unknown/custom bodies are allowed if declared, or if the user intends
            # the target backend to already know them. GMAT will be the source of
            # truth at LoadScript time for undeclared non-builtins.
            if body not in GMAT_BUILTIN_MAJOR_BODIES and body not in declared_bodies:
                problems.append(
                    f"force model {fm.get('id')} third-body {body} is not a GMAT built-in major body and is not declared in bodies[]"
                )
        if gtype in {"spherical_harmonic", "basic_earth_gravity"}:
            degree = int(gravity.get("degree", 4))
            order = int(gravity.get("order", 4))

            if degree < 0 or order < 0:
                problems.append(f"force model {fm.get('id')} gravity degree/order must be nonnegative")

            if order > degree:
                problems.append(f"force model {fm.get('id')} gravity order must be <= degree")

            if degree > MAX_GRAVITY_DEGREE or order > MAX_GRAVITY_ORDER:
                problems.append(
                    f"force model {fm.get('id')} gravity degree/order exceeds configured safety bound "
                    f"({MAX_GRAVITY_DEGREE}/{MAX_GRAVITY_ORDER})"
                )

            if central != "Earth" and not gravity.get("potential_file"):
                problems.append(
                    f"force model {fm.get('id')} spherical_harmonic gravity for {central} requires gravity.potential_file"
                )
        elif gtype != "point_mass":
            problems.append(f"force model {fm.get('id')} unsupported gravity type {gtype}")


    for i, out in enumerate(spec.get("outputs", [])):
        if out.get("enabled", True) is False:
            continue
        otype = out.get("type")
        output_path = out.get("path") or out.get("path_template") or ""
        filename = Path(str(output_path)).name
        if otype == "full_ephemeris":
            if not filename.startswith("_Ephemeris"):
                problems.append(
                    f"outputs.{i}: full_ephemeris filename must start with '_Ephemeris' before any mission/spacecraft/frame text"
                )
        elif otype == "body_ephemeris":
            if output_path and not filename.startswith("_BodyEphemeris"):
                problems.append(
                    f"outputs.{i}: body_ephemeris filename must start with '_BodyEphemeris'"
                )
        elif otype == "body_ephemeris_group":
            template = out.get("path_template") or "outputs/_BodyEphemeris_{body}_{frame}.csv"
            if not Path(str(template).format(body="Body", frame="Frame")).name.startswith("_BodyEphemeris"):
                problems.append(
                    f"outputs.{i}: body_ephemeris_group path_template filename must start with '_BodyEphemeris'"
                )
        elif otype == "ground_track":
            path = output_path or "outputs/_GroundTrack_{spacecraft}_{body}.csv"
            filename = Path(str(path).format(spacecraft="Spacecraft", spacecraft_id="sc", body="Earth", mission_id="mission", output_id="ground_track")).name
            if not filename.startswith("_GroundTrack"):
                problems.append(
                    f"outputs.{i}: ground_track filename must start with '_GroundTrack'"
                )

    for p in spec.get("propagators", []):
        if p["min_step_s"] > p["max_step_s"]:
            problems.append(f"propagator {p['id']} min_step_s exceeds max_step_s")
        if p["initial_step_s"] > p["max_step_s"]:
            problems.append(f"propagator {p['id']} initial_step_s exceeds max_step_s")

    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    for event in spec.get("events", []):
        if event.get("max_duration_s") is not None and event["max_duration_s"] > MAX_DURATION_S:
            problems.append(f"event {event.get('id')} max_duration_s exceeds MVP bound")
        if event.get("type") == "orbital_event" and event.get("event") == "apoapsis":
            sc = spacecraft_by_id.get(event.get("spacecraft"))
            if sc and sc.get("state_type") == "keplerian" and sc.get("ecc", 0) >= 1:
                problems.append(f"event {event.get('id')} apoapsis is invalid for hyperbolic/parabolic orbit")
        for action in event.get("actions", []) or []:
            if action.get("type") == "maneuver" and action.get("duration_s", 0) > MAX_FINITE_BURN_DURATION_S:
                problems.append(f"event {event.get('id')} action {action.get('action_id')} finite burn duration exceeds MVP bound: {action['duration_s']}")

    for _, step, _ in iter_steps(spec):
        if step.get("type") == "propagate" and step["duration_s"] > MAX_DURATION_S:
            problems.append(f"propagation step {step.get('step_id')} duration exceeds MVP bound: {step['duration_s']}")
        if step.get("type") == "maneuver" and step.get("duration_s", 0) > MAX_FINITE_BURN_DURATION_S:
            problems.append(f"finite burn step {step.get('step_id')} duration exceeds MVP bound: {step['duration_s']}")

    if problems:
        raise MissionValidationError("; ".join(problems))
    return [{"check_id": "bounds", "status": "passed", "severity": "error", "message": "All MVP physical/runtime bounds pass."}]


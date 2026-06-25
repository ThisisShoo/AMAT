from __future__ import annotations

import math
from typing import Any

DEFAULT_MERGE_ANGLE_TOLERANCE_DEG = 2.0
PHASED_DEPARTURE_ECCENTRICITY_TOLERANCE = 1e-8


def _apsis_radius(sma: float, ecc: float, apsis: str) -> float:
    return sma * (1.0 - ecc) if apsis == "periapsis" else sma * (1.0 + ecc)


def _speed(mu: float, radius: float, sma: float) -> float:
    return math.sqrt(mu * (2.0 / radius - 1.0 / sma))


def _plane_angle_deg(i1: float, i2: float, raan1: float, raan2: float) -> float:
    i1r, i2r = math.radians(i1), math.radians(i2)
    draan = math.radians(raan2 - raan1)
    cosine = math.cos(i1r) * math.cos(i2r) + math.sin(i1r) * math.sin(i2r) * math.cos(draan)
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def _combined_components(v_before: float, v_after: float, angle_deg: float) -> tuple[float, float, float]:
    angle = math.radians(angle_deg)
    dv_v = v_after * math.cos(angle) - v_before
    dv_n = v_after * math.sin(angle)
    return dv_v, dv_n, math.hypot(dv_v, dv_n)


def _dot(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(a: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(a, a))


def _unit(a: tuple[float, float, float]) -> tuple[float, float, float]:
    mag = _norm(a)
    if mag <= 1e-15:
        return (0.0, 0.0, 0.0)
    return (a[0] / mag, a[1] / mag, a[2] / mag)


def _orbit_basis(inc_deg: float, raan_deg: float, aop_deg: float) -> dict[str, tuple[float, float, float]]:
    inc = math.radians(inc_deg)
    raan = math.radians(raan_deg)
    aop = math.radians(aop_deg)
    cos_o, sin_o = math.cos(raan), math.sin(raan)
    cos_i, sin_i = math.cos(inc), math.sin(inc)
    cos_w, sin_w = math.cos(aop), math.sin(aop)

    p = (
        cos_o * cos_w - sin_o * sin_w * cos_i,
        sin_o * cos_w + cos_o * sin_w * cos_i,
        sin_w * sin_i,
    )
    q = (
        -cos_o * sin_w - sin_o * cos_w * cos_i,
        -sin_o * sin_w + cos_o * cos_w * cos_i,
        cos_w * sin_i,
    )
    h = _unit(_cross(p, q))
    return {"p": _unit(p), "q": _unit(q), "h": h}


def _rotate_basis_to_true_anomaly(
    basis: dict[str, tuple[float, float, float]],
    ta_deg: float,
) -> dict[str, tuple[float, float, float]]:
    ta = math.radians(ta_deg)
    p = basis["p"]
    q = basis["q"]
    rhat = (
        math.cos(ta) * p[0] + math.sin(ta) * q[0],
        math.cos(ta) * p[1] + math.sin(ta) * q[1],
        math.cos(ta) * p[2] + math.sin(ta) * q[2],
    )
    qhat = (
        -math.sin(ta) * p[0] + math.cos(ta) * q[0],
        -math.sin(ta) * p[1] + math.cos(ta) * q[1],
        -math.sin(ta) * p[2] + math.cos(ta) * q[2],
    )
    return {"p": _unit(rhat), "q": _unit(qhat), "h": basis["h"]}


def _position_unit_vector(
    basis: dict[str, tuple[float, float, float]],
    ta_deg: float,
) -> tuple[float, float, float]:
    ta = math.radians(ta_deg)
    p = basis["p"]
    q = basis["q"]
    return _unit(
        (
            math.cos(ta) * p[0] + math.sin(ta) * q[0],
            math.cos(ta) * p[1] + math.sin(ta) * q[1],
            math.cos(ta) * p[2] + math.sin(ta) * q[2],
        )
    )


def _normalize_angle_deg(value: float) -> float:
    return value % 360.0


def _angle_delta_deg(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def _angle_distance_deg(a: float, b: float) -> float:
    return abs(_angle_delta_deg(a, b))


def _forward_arc_deg(start: float, end: float) -> float:
    return (end - start) % 360.0


def _true_anomaly_to_argument_of_latitude(state: dict[str, Any], ta_deg: float) -> float:
    return _normalize_angle_deg(float(state["aop"]["value"]) + ta_deg)


def _inertial_longitude_from_rhat(rhat: tuple[float, float, float]) -> float:
    return _normalize_angle_deg(math.degrees(math.atan2(rhat[1], rhat[0])))


def _arrival_phase_deg(target: dict[str, Any], arrival_ta: float, arrival_rhat: tuple[float, float, float]) -> float:
    if abs(float(target["inclination"]["value"])) <= 1.0e-8:
        return _inertial_longitude_from_rhat(arrival_rhat)
    return _true_anomaly_to_argument_of_latitude(target, arrival_ta)


def _is_on_forward_arc(angle: float, start: float, end: float, tolerance: float = 1e-8) -> bool:
    span = _forward_arc_deg(start, end)
    progress = _forward_arc_deg(start, angle)
    return progress <= span + tolerance


def _radius_at_true_anomaly(sma: float, ecc: float, ta_deg: float) -> float:
    return sma * (1.0 - ecc * ecc) / (1.0 + ecc * math.cos(math.radians(ta_deg)))


def _scale(a: tuple[float, float, float], scalar: float) -> tuple[float, float, float]:
    return (a[0] * scalar, a[1] * scalar, a[2] * scalar)


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _transfer_velocity_vector(
    basis: dict[str, tuple[float, float, float]],
    mu: float,
    sma: float,
    ecc: float,
    ta_deg: float,
) -> tuple[float, float, float]:
    ta = math.radians(ta_deg)
    factor = math.sqrt(mu / (sma * (1.0 - ecc * ecc)))
    p = basis["p"]
    q = basis["q"]
    return (
        factor * (-math.sin(ta) * p[0] + (ecc + math.cos(ta)) * q[0]),
        factor * (-math.sin(ta) * p[1] + (ecc + math.cos(ta)) * q[1]),
        factor * (-math.sin(ta) * p[2] + (ecc + math.cos(ta)) * q[2]),
    )


def _target_plane_velocity_vector_at_node(
    transfer_basis: dict[str, tuple[float, float, float]],
    target_basis: dict[str, tuple[float, float, float]],
    v_before: tuple[float, float, float],
    rhat: tuple[float, float, float],
) -> tuple[float, float, float]:
    radial_speed = _dot(v_before, rhat)
    transfer_transverse = _unit(_cross(transfer_basis["h"], rhat))
    target_transverse = _unit(_cross(target_basis["h"], rhat))
    if _dot(transfer_transverse, v_before) < 0.0:
        transfer_transverse = _scale(transfer_transverse, -1.0)
        target_transverse = _scale(target_transverse, -1.0)
    transverse_speed = _dot(v_before, transfer_transverse)
    return (
        radial_speed * rhat[0] + transverse_speed * target_transverse[0],
        radial_speed * rhat[1] + transverse_speed * target_transverse[1],
        radial_speed * rhat[2] + transverse_speed * target_transverse[2],
    )


def _vnb_components(
    velocity: tuple[float, float, float],
    orbit_normal: tuple[float, float, float],
    delta_v: tuple[float, float, float],
) -> tuple[float, float, float, float]:
    v_axis = _unit(velocity)
    n_axis = _unit(orbit_normal)
    b_axis = _unit(_cross(v_axis, n_axis))
    dv_v = _dot(delta_v, v_axis)
    dv_n = _dot(delta_v, n_axis)
    dv_b = _dot(delta_v, b_axis)
    return dv_v, dv_n, dv_b, math.sqrt(dv_v * dv_v + dv_n * dv_n + dv_b * dv_b)


def _plane_intersection_true_anomalies(
    state: dict[str, Any],
    target: dict[str, Any],
) -> list[dict[str, float | tuple[float, float, float]]]:
    initial_basis = _orbit_basis(
        state["inclination"]["value"],
        state["raan"]["value"],
        state["aop"]["value"],
    )
    target_basis = _orbit_basis(
        target["inclination"]["value"],
        target["raan"]["value"],
        target["aop"]["value"],
    )
    line = _cross(initial_basis["h"], target_basis["h"])
    if _norm(line) <= 1e-12:
        return []

    nodes = []
    for direction in (_unit(line), _unit((-line[0], -line[1], -line[2]))):
        ta = _normalize_angle_deg(
            math.degrees(math.atan2(_dot(direction, initial_basis["q"]), _dot(direction, initial_basis["p"])))
        )
        nodes.append(
            {
                "ta_deg": ta,
                "argument_of_latitude_deg": _true_anomaly_to_argument_of_latitude(state, ta),
                "rhat": direction,
            }
        )
    return nodes


def _plane_change_sign(
    state: dict[str, Any],
    target: dict[str, Any],
    rhat: tuple[float, float, float],
) -> float:
    initial_basis = _orbit_basis(
        state["inclination"]["value"],
        state["raan"]["value"],
        state["aop"]["value"],
    )
    target_basis = _orbit_basis(
        target["inclination"]["value"],
        target["raan"]["value"],
        target["aop"]["value"],
    )
    tangent = _unit(_cross(initial_basis["h"], rhat))
    target_tangent_component = _dot(target_basis["h"], tangent)
    if abs(target_tangent_component) <= 1e-12:
        return 1.0
    return -1.0 if target_tangent_component > 0.0 else 1.0


def _select_plane_change_node(
    state: dict[str, Any],
    target: dict[str, Any],
    departure_ta: float,
    arrival_ta: float,
    *,
    low_speed_reference_ta: float | None = None,
) -> dict[str, Any] | None:
    nodes = _plane_intersection_true_anomalies(state, target)
    if not nodes:
        return None

    reference_ta = arrival_ta if low_speed_reference_ta is None else low_speed_reference_ta
    for node in nodes:
        ta = float(node["ta_deg"])
        node["distance_to_low_speed_apsis_deg"] = _angle_distance_deg(ta, reference_ta)
        node["distance_to_apoapsis_deg"] = node["distance_to_low_speed_apsis_deg"]
        node["forward_progress_deg"] = _forward_arc_deg(departure_ta, ta)
        node["on_transfer_arc"] = _is_on_forward_arc(ta, departure_ta, arrival_ta)

    candidates = [node for node in nodes if node["on_transfer_arc"]]
    if not candidates:
        candidates = nodes
    return min(candidates, key=lambda node: (float(node["distance_to_low_speed_apsis_deg"]), float(node["forward_progress_deg"])))


def _select_arrival_aligned_departure(
    state: dict[str, Any],
    target: dict[str, Any],
) -> dict[str, Any] | None:
    nodes = _plane_intersection_true_anomalies(state, target)
    if not nodes:
        return None
    for node in nodes:
        arrival_ta = float(node["ta_deg"])
        departure_ta = _normalize_angle_deg(arrival_ta - 180.0)
        node["arrival_true_anomaly_deg"] = arrival_ta
        node["departure_true_anomaly_deg"] = departure_ta
        node["arrival_argument_of_latitude_deg"] = _true_anomaly_to_argument_of_latitude(state, arrival_ta)
        node["departure_argument_of_latitude_deg"] = _true_anomaly_to_argument_of_latitude(state, departure_ta)
        node["departure_phase_wait_deg"] = _forward_arc_deg(float(state["true_anomaly"]["value"]), departure_ta)
    return min(nodes, key=lambda node: float(node["departure_phase_wait_deg"]))


def _can_phase_departure_to_node(state: dict[str, Any], strategy: dict[str, Any]) -> bool:
    policy = strategy.get("maneuver_policy_config", {})
    return (
        strategy.get("maneuver_policy") == "valid_node_low_speed"
        and bool(policy.get("allow_departure_phasing"))
        and bool(policy.get("prefer_apsis_alignment"))
        and strategy.get("departure_event", {}).get("type") in {"initial_state", "periapsis", "apoapsis"}
        and abs(float(state.get("eccentricity", 0.0))) <= PHASED_DEPARTURE_ECCENTRICITY_TOLERANCE
    )


def _event_label(event: dict[str, Any]) -> str:
    return str(event.get("resolved_specific_type", event["type"]))


def _event_uses_argument_of_latitude(event: dict[str, Any]) -> bool:
    event_type = event.get("resolved_specific_type", event["type"])
    return event_type in {"argument_of_latitude", "ascending_node", "descending_node"}


def _event_is_node(event: dict[str, Any]) -> bool:
    return event.get("resolved_specific_type", event["type"]) in {"ascending_node", "descending_node"}


def _event_argument_of_latitude(event: dict[str, Any], orbit: dict[str, Any], ta_deg: float) -> float:
    if "resolved_argument_of_latitude" in event:
        return float(event["resolved_argument_of_latitude"]["value"])
    if event.get("type") == "argument_of_latitude":
        return float(event["value"]["value"])
    return _true_anomaly_to_argument_of_latitude(orbit, ta_deg)


def _pure_plane_change_components(speed: float, signed_angle_deg: float) -> tuple[float, float, float]:
    angle = math.radians(signed_angle_deg)
    dv_v = speed * (math.cos(angle) - 1.0)
    dv_n = speed * math.sin(angle)
    return dv_v, dv_n, math.hypot(dv_v, dv_n)


def _node_plane_change_components(
    state: dict[str, Any],
    target: dict[str, Any],
    mu: float,
    transfer_sma: float,
    transfer_ecc: float,
    node: dict[str, Any],
    *,
    transfer_basis: dict[str, tuple[float, float, float]] | None = None,
) -> tuple[float, float, float, float]:
    transfer_basis = transfer_basis or _orbit_basis(
        state["inclination"]["value"],
        state["raan"]["value"],
        state["aop"]["value"],
    )
    target_basis = _orbit_basis(
        target["inclination"]["value"],
        target["raan"]["value"],
        target["aop"]["value"],
    )
    ta = float(node["ta_deg"])
    rhat = node["rhat"]
    v_before = _transfer_velocity_vector(transfer_basis, mu, transfer_sma, transfer_ecc, ta)
    v_after = _target_plane_velocity_vector_at_node(transfer_basis, target_basis, v_before, rhat)
    return _vnb_components(v_before, transfer_basis["h"], _sub(v_after, v_before))


def _target_plane_velocity_at_node(
    transfer_basis: dict[str, tuple[float, float, float]],
    target_basis: dict[str, tuple[float, float, float]],
    v_before: tuple[float, float, float],
    rhat: tuple[float, float, float],
    speed: float,
) -> tuple[float, float, float]:
    transfer_transverse = _unit(_cross(transfer_basis["h"], rhat))
    target_transverse = _unit(_cross(target_basis["h"], rhat))
    if _dot(transfer_transverse, v_before) < 0.0:
        target_transverse = _scale(target_transverse, -1.0)
    return _scale(target_transverse, speed)


def _node_speed_change_components(
    state: dict[str, Any],
    target: dict[str, Any],
    mu: float,
    before_sma: float,
    before_ecc: float,
    after_speed: float,
    node: dict[str, Any],
    *,
    transfer_basis: dict[str, tuple[float, float, float]] | None = None,
) -> tuple[float, float, float, float]:
    transfer_basis = transfer_basis or _orbit_basis(
        state["inclination"]["value"],
        state["raan"]["value"],
        state["aop"]["value"],
    )
    target_basis = _orbit_basis(
        target["inclination"]["value"],
        target["raan"]["value"],
        target["aop"]["value"],
    )
    ta = float(node["ta_deg"])
    rhat = node["rhat"]
    v_before = _transfer_velocity_vector(transfer_basis, mu, before_sma, before_ecc, ta)
    v_after = _target_plane_velocity_at_node(transfer_basis, target_basis, v_before, rhat, after_speed)
    return _vnb_components(v_before, transfer_basis["h"], _sub(v_after, v_before))


def _merge_target(node_ta: float, departure_ta: float, arrival_ta: float, tolerance_deg: float) -> str | None:
    if _angle_distance_deg(node_ta, departure_ta) <= tolerance_deg:
        return "departure"
    if _angle_distance_deg(node_ta, arrival_ta) <= tolerance_deg:
        return "arrival"
    return None


def generate_hohmann_candidate(problem: dict[str, Any]) -> dict[str, Any]:
    """Generate a node-aware impulsive apsidal-transfer candidate.

    The strict circular/coplanar case reduces to the standard Hohmann result.
    Elliptical endpoint orbits are supported when the impulses occur at the
    selected apsides. For impulsive non-coplanar transfers, the plane change is
    placed at the orbital-plane intersection closest to apoapsis on the transfer
    arc. If that event is close to an energy burn, the impulses are merged.
    """
    state = problem["initial_state"]
    target = problem["target"]
    strategy = problem["transfer_strategy"]
    mu = float(strategy["central_body_mu"]["value"])

    a_initial = state["sma"]["value"]
    e_initial = state["eccentricity"]
    a_target = target["sma"]["value"]
    e_target = target["eccentricity"]
    departure_event = strategy["departure_event"]
    arrival_event = strategy["arrival_event"]
    departure_ta = (
        float(state["true_anomaly"]["value"])
        if departure_event["type"] == "initial_state"
        else float(strategy["departure_true_anomaly"])
    )
    r_depart = _radius_at_true_anomaly(a_initial, e_initial, departure_ta)
    r_arrive = _radius_at_true_anomaly(a_target, e_target, float(strategy["arrival_true_anomaly"]))
    a_transfer = (r_depart + r_arrive) / 2.0

    v_initial = _speed(mu, r_depart, a_initial)
    v_transfer_depart = _speed(mu, r_depart, a_transfer)
    v_transfer_arrive = _speed(mu, r_arrive, a_transfer)
    v_target = _speed(mu, r_arrive, a_target)
    plane_change = _plane_angle_deg(
        state["inclination"]["value"],
        target["inclination"]["value"],
        state["raan"]["value"],
        target["raan"]["value"],
    )
    initial_basis = _orbit_basis(
        state["inclination"]["value"],
        state["raan"]["value"],
        state["aop"]["value"],
    )
    phased_departure_node = (
        _select_arrival_aligned_departure(state, target) if plane_change > 1e-10 and _can_phase_departure_to_node(state, strategy) else None
    )
    explicit_departure_node = (
        plane_change > 1e-10
        and phased_departure_node is None
        and _event_is_node(departure_event)
        and bool(strategy.get("maneuver_policy_config", {}).get("prefer_apsis_alignment"))
    )
    if phased_departure_node is not None:
        departure_ta = float(phased_departure_node["departure_true_anomaly_deg"])
        transfer_basis = _rotate_basis_to_true_anomaly(initial_basis, departure_ta)
        arrival_ta = 180.0
    elif explicit_departure_node:
        transfer_basis = _rotate_basis_to_true_anomaly(initial_basis, departure_ta)
        arrival_ta = 180.0
    else:
        transfer_basis = initial_basis
        arrival_ta = float(strategy["arrival_true_anomaly"])

    merge_tolerance = float(strategy.get("merge_maneuver_angle_tolerance_deg", DEFAULT_MERGE_ANGLE_TOLERANCE_DEG))
    if plane_change > 1e-10 and (phased_departure_node is not None or explicit_departure_node):
        plane_node = {
            "ta_deg": arrival_ta,
            "rhat": _scale(transfer_basis["p"], -1.0),
            "distance_to_low_speed_apsis_deg": 0.0,
            "distance_to_apoapsis_deg": 0.0,
            "forward_progress_deg": 180.0,
            "on_transfer_arc": True,
        }
    else:
        plane_node = (
            _select_plane_change_node(state, target, departure_ta, arrival_ta, low_speed_reference_ta=arrival_ta)
            if plane_change > 1e-10
            else None
        )
    arrival_rhat = _scale(transfer_basis["p"], -1.0) if abs(_angle_delta_deg(arrival_ta, 180.0)) <= 1e-8 else _position_unit_vector(transfer_basis, arrival_ta)
    plane_node_ta = float(plane_node["ta_deg"]) if plane_node else None
    plane_merge = _merge_target(plane_node_ta, departure_ta, arrival_ta, merge_tolerance) if plane_node else None
    plane_sign = _plane_change_sign(state, target, plane_node["rhat"]) if plane_node else 1.0
    signed_plane_change = plane_sign * plane_change

    departure_normal_angle = signed_plane_change if plane_merge == "departure" else 0.0
    arrival_normal_angle = signed_plane_change if plane_merge == "arrival" else 0.0
    transfer_ecc = abs(r_arrive - r_depart) / (r_arrive + r_depart)
    if plane_merge == "departure" and plane_node is not None:
        dv1_v, dv1_n, dv1_b, dv1 = _node_speed_change_components(
            state,
            target,
            mu,
            a_initial,
            e_initial,
            v_transfer_depart,
            plane_node,
            transfer_basis=transfer_basis,
        )
    else:
        dv1_v, dv1_n, dv1 = _combined_components(v_initial, v_transfer_depart, departure_normal_angle)
        dv1_b = 0.0
    if plane_merge == "arrival" and plane_node is not None:
        dv2_v, dv2_n, dv2_b, dv2 = _node_speed_change_components(
            state,
            target,
            mu,
            a_transfer,
            transfer_ecc,
            v_target,
            plane_node,
            transfer_basis=transfer_basis,
        )
    else:
        dv2_v, dv2_n, dv2 = _combined_components(v_transfer_arrive, v_target, arrival_normal_angle)
        dv2_b = 0.0
    tof = math.pi * math.sqrt(a_transfer**3 / mu)

    immediate_departure = phased_departure_node is None and departure_event["type"] == "initial_state"
    if phased_departure_node is not None:
        departure_event_type = "parameter_reaches"
    elif immediate_departure:
        departure_event_type = "immediate"
    elif departure_event.get("resolved_specific_type", departure_event["type"]) in {"periapsis", "apoapsis"}:
        departure_event_type = "orbital_event"
    else:
        departure_event_type = "parameter_reaches"
    transfer_maneuver = {
        "maneuver_id": "transfer_injection",
        "maneuver_type": "combined_impulsive" if plane_merge == "departure" else "tangential_impulsive",
        "event": "phased_departure_node" if phased_departure_node is not None else ("initial_state" if immediate_departure else _event_label(departure_event)),
        "event_type": departure_event_type,
        "true_anomaly_deg": departure_ta,
        "frame": "VNB",
        "components_km_s": [dv1_v, dv1_n, dv1_b],
        "magnitude_km_s": dv1,
        "concurrent_effects": ["energy_change"] + (["plane_change"] if plane_merge == "departure" else []),
        "plane_change_deg": plane_change if plane_merge == "departure" else 0.0,
        "signed_vnb_normal_rotation_deg": departure_normal_angle,
        "departure_phase_wait_deg": float(phased_departure_node["departure_phase_wait_deg"]) if phased_departure_node else 0.0,
    }
    if phased_departure_node is not None:
        transfer_maneuver["angle_kind"] = "argument_of_latitude"
        transfer_maneuver["argument_of_latitude_deg"] = float(phased_departure_node["departure_argument_of_latitude_deg"])
        transfer_maneuver["true_anomaly_reference_deg"] = departure_ta
    elif _event_uses_argument_of_latitude(departure_event):
        transfer_maneuver["angle_kind"] = "argument_of_latitude"
        transfer_maneuver["argument_of_latitude_deg"] = _event_argument_of_latitude(departure_event, state, departure_ta)
        transfer_maneuver["true_anomaly_reference_deg"] = departure_ta
    else:
        transfer_maneuver["angle_kind"] = "true_anomaly"
    maneuvers: list[dict[str, Any]] = [transfer_maneuver]
    plane_change_dv = 0.0
    if plane_node and plane_merge is None:
        plane_dv_v, plane_dv_n, plane_dv_b, plane_change_dv = _node_plane_change_components(
            state,
            target,
            mu,
            a_transfer,
            transfer_ecc,
            plane_node,
        )
        maneuvers.append(
            {
                "maneuver_id": "plane_change_at_node",
                "maneuver_type": "plane_change_impulsive",
                "event": "plane_intersection_near_apoapsis",
                "event_type": "parameter_reaches",
                "true_anomaly_deg": plane_node_ta,
                "angle_kind": "true_anomaly",
                "frame": "VNB",
                "components_km_s": [plane_dv_v, plane_dv_n, plane_dv_b],
                "magnitude_km_s": plane_change_dv,
                "concurrent_effects": ["plane_change"],
                "plane_change_deg": plane_change,
                "signed_vnb_normal_rotation_deg": signed_plane_change,
                "node_selection": {
                    "criterion": "orbital_plane_intersection_closest_to_apoapsis_on_transfer_arc",
                    "distance_to_apoapsis_deg": plane_node["distance_to_apoapsis_deg"],
                    "on_transfer_arc": plane_node["on_transfer_arc"],
                },
            }
        )
    arrival_maneuver = {
        "maneuver_id": "orbit_insertion",
        "maneuver_type": "combined_impulsive" if plane_merge == "arrival" else "tangential_impulsive",
        "event": _event_label(arrival_event),
        "event_type": (
            "orbital_event"
            if arrival_event.get("resolved_specific_type", arrival_event["type"]) in {"periapsis", "apoapsis"}
            else "parameter_reaches"
        ),
        "true_anomaly_deg": arrival_ta,
        "frame": "VNB",
        "components_km_s": [dv2_v, dv2_n, dv2_b],
        "magnitude_km_s": dv2,
        "concurrent_effects": ["energy_change"] + (["plane_change"] if plane_merge == "arrival" else []),
        "plane_change_deg": plane_change if plane_merge == "arrival" else 0.0,
        "signed_vnb_normal_rotation_deg": arrival_normal_angle,
    }
    if _event_uses_argument_of_latitude(arrival_event):
        arrival_maneuver["angle_kind"] = "argument_of_latitude"
        arrival_maneuver["argument_of_latitude_deg"] = _event_argument_of_latitude(arrival_event, target, arrival_ta)
        arrival_maneuver["true_anomaly_reference_deg"] = arrival_ta
    else:
        arrival_maneuver["angle_kind"] = "true_anomaly"
    maneuvers.append(arrival_maneuver)

    strict_hohmann = e_initial == 0.0 and e_target == 0.0 and plane_change == 0.0
    model = "two_body_impulsive_coplanar_hohmann" if strict_hohmann else "two_body_impulsive_node_aware_plane_change"
    return {
        "schema_version": "1.1.0",
        "candidate_id": "analytic_node_aware_impulsive_001",
        "problem_id": problem["problem_id"],
        "generation_backend": "analytic_node_aware_apsidal",
        "generation_status": "candidate_generated",
        "maneuvers": maneuvers,
        "variable_values": {
            "transfer_injection.delta_v_v": {"value": dv1_v, "unit": "km/s"},
            "transfer_injection.delta_v_n": {"value": dv1_n, "unit": "km/s"},
            "orbit_insertion.delta_v_v": {"value": dv2_v, "unit": "km/s"},
            "orbit_insertion.delta_v_n": {"value": dv2_n, "unit": "km/s"},
            "transfer.coast_time": {"value": tof, "unit": "s"},
        },
        "analytic_assessment": {
            "status": "analytically_feasible",
            "model": model,
            "departure_radius_km": r_depart,
            "arrival_radius_km": r_arrive,
            "transfer_sma_km": a_transfer,
            "transfer_eccentricity": abs(r_arrive - r_depart) / (r_arrive + r_depart),
            "plane_change_total_deg": plane_change,
            "plane_change_departure_deg": plane_change if plane_merge == "departure" else 0.0,
            "plane_change_node_deg": plane_change if plane_node and plane_merge is None else 0.0,
            "plane_change_arrival_deg": plane_change if plane_merge == "arrival" else 0.0,
            "plane_change_node_true_anomaly_deg": plane_node_ta,
            "plane_change_merge_target": plane_merge,
            "merge_maneuver_angle_tolerance_deg": merge_tolerance,
            "departure_phasing_applied": phased_departure_node is not None,
            "departure_true_anomaly_deg": departure_ta,
            "departure_argument_of_latitude_deg": (
                float(phased_departure_node["departure_argument_of_latitude_deg"])
                if phased_departure_node
                else _true_anomaly_to_argument_of_latitude(state, departure_ta)
            ),
            "arrival_true_anomaly_deg": arrival_ta,
            "arrival_argument_of_latitude_deg": (
                float(arrival_event["value"]["value"])
                if arrival_event.get("type") == "argument_of_latitude"
                else _arrival_phase_deg(target, arrival_ta, arrival_rhat)
            ),
            "departure_phase_wait_deg": float(phased_departure_node["departure_phase_wait_deg"]) if phased_departure_node else 0.0,
            "total_delta_v_km_s": sum(float(m["magnitude_km_s"]) for m in maneuvers),
        },
    }


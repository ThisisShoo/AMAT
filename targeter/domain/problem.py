from __future__ import annotations

import math
from copy import deepcopy
from typing import Any

from compiler.time_formats import canonicalize_epoch
from targeter.constants import EARTH_GEO_RADIUS_KM, EARTH_RADIUS_KM
from targeter.errors import TargetingError

SUPPORTED_TRANSFER_STRATEGIES = {
    "hohmann_transfer",
    "two_impulse_apsidal_transfer",
}
SUPPORTED_TARGETS = {"geostationary_orbit", "circular_orbit", "keplerian_orbit"}
SUPPORTED_INITIAL_STATES = {"circular_orbit", "keplerian"}
SUPPORTED_APSIDES = {"periapsis", "apoapsis"}
SUPPORTED_PLANE_CHANGE_POLICIES = {
    "valid_node_low_speed",
    "node_near_apoapsis",
    "concurrent_minimum_delta_v",
    "arrival_only",
    "departure_only",
}


def _number(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TargetingError(f"{path} must be numeric")
    return float(value)


def _quantity(obj: Any, path: str, expected_unit: str | None = None) -> dict[str, Any]:
    if not isinstance(obj, dict) or "value" not in obj or "unit" not in obj:
        raise TargetingError(f"{path} must contain value and unit")
    result = {"value": _number(obj["value"], f"{path}.value"), "unit": str(obj["unit"])}
    if expected_unit and result["unit"] != expected_unit:
        raise TargetingError(f"{path}.unit must be {expected_unit!r}")
    return result


def _angle(obj: Any, path: str, default: float = 0.0) -> dict[str, Any]:
    return _quantity(obj if obj is not None else {"value": default, "unit": "deg"}, path, "deg")


def _canonical_strategy(p: dict[str, Any]) -> dict[str, Any]:
    # Migration-only alias. Canonical output always uses transfer_strategy.
    if "transfer_strategy" not in p and "architecture" in p:
        p["transfer_strategy"] = p.pop("architecture")
    strategy = p.get("transfer_strategy")
    if not isinstance(strategy, dict):
        raise TargetingError("transfer_strategy must be an object")
    strategy.setdefault("central_body", "Earth")
    strategy.setdefault("maneuver_model", "impulsive")
    strategy.setdefault("departure_apsis", "periapsis")
    strategy.setdefault("arrival_apsis", "apoapsis")
    raw_policy = strategy.get("plane_change_policy", "valid_node_low_speed")
    if isinstance(raw_policy, str):
        policy_config = {"type": raw_policy}
    elif isinstance(raw_policy, dict):
        policy_config = deepcopy(raw_policy)
        if not isinstance(policy_config.get("type"), str):
            raise TargetingError("transfer_strategy.plane_change_policy.type must be a string")
    else:
        raise TargetingError("transfer_strategy.plane_change_policy must be a string or object")
    policy_type = policy_config["type"]
    if policy_type not in SUPPORTED_PLANE_CHANGE_POLICIES:
        raise TargetingError("Unsupported plane_change_policy")
    policy_config.setdefault("allow_departure_phasing", policy_type == "valid_node_low_speed")
    policy_config.setdefault("prefer_apsis_alignment", policy_type == "valid_node_low_speed")
    policy_config.setdefault("fallback", "split_at_nearest_valid_node")
    strategy["plane_change_policy"] = policy_type
    strategy["plane_change_policy_config"] = policy_config
    strategy_type = strategy.get("type")
    if strategy_type not in SUPPORTED_TRANSFER_STRATEGIES:
        raise TargetingError(f"Unsupported transfer_strategy.type={strategy_type!r}")
    if strategy["central_body"] != "Earth":
        raise TargetingError("The first implementation supports Earth only")
    if strategy["maneuver_model"] not in {"impulsive", "finite"}:
        raise TargetingError("maneuver_model must be impulsive or finite")
    if strategy["departure_apsis"] not in SUPPORTED_APSIDES:
        raise TargetingError("transfer_strategy.departure_apsis must be periapsis or apoapsis")
    if strategy["arrival_apsis"] not in SUPPORTED_APSIDES:
        raise TargetingError("transfer_strategy.arrival_apsis must be periapsis or apoapsis")
    strategy.setdefault("merge_maneuver_angle_tolerance_deg", 2.0)
    return strategy


def _canonical_initial_state(state: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise TargetingError("initial_state must be an object")
    state.setdefault("representation", "circular_orbit")
    state.setdefault("central_body", strategy["central_body"])
    state.setdefault("frame", "EarthMJ2000Eq")
    state["epoch"] = canonicalize_epoch(state.get("epoch", "2026-01-01T00:00:00.000Z"))
    representation = state["representation"]
    if representation not in SUPPORTED_INITIAL_STATES:
        raise TargetingError(f"Unsupported initial_state.representation={representation!r}")

    state["inclination"] = _angle(state.get("inclination"), "initial_state.inclination")
    state["raan"] = _angle(state.get("raan"), "initial_state.raan")
    state["aop"] = _angle(state.get("aop"), "initial_state.aop")

    if representation == "circular_orbit":
        state["altitude"] = _quantity(state.get("altitude"), "initial_state.altitude", "km")
        if state["altitude"]["value"] <= 0:
            raise TargetingError("initial_state.altitude must be positive")
        state["sma"] = {"value": EARTH_RADIUS_KM + state["altitude"]["value"], "unit": "km"}
        state["eccentricity"] = 0.0
        default_ta = 0.0 if strategy["departure_apsis"] == "periapsis" else 180.0
        state["true_anomaly"] = _angle(state.get("true_anomaly"), "initial_state.true_anomaly", default_ta)
    else:
        state["sma"] = _quantity(state.get("sma"), "initial_state.sma", "km")
        state["eccentricity"] = _number(state.get("eccentricity"), "initial_state.eccentricity")
        if state["sma"]["value"] <= EARTH_RADIUS_KM:
            raise TargetingError("initial_state.sma must exceed Earth radius")
        if not 0 <= state["eccentricity"] < 1:
            raise TargetingError("initial_state.eccentricity must be in [0, 1)")
        default_ta = 0.0 if strategy["departure_apsis"] == "periapsis" else 180.0
        state["true_anomaly"] = _angle(state.get("true_anomaly"), "initial_state.true_anomaly", default_ta)
        expected_ta = default_ta
        delta = abs(((state["true_anomaly"]["value"] - expected_ta + 180.0) % 360.0) - 180.0)
        if delta > 1e-8:
            raise TargetingError(
                "The analytic apsidal initial-guess backend requires the initial state at the selected departure apsis"
            )
    return state


def _canonical_target(target: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(target, dict):
        raise TargetingError("target must be an object")
    if target.get("type") not in SUPPORTED_TARGETS:
        raise TargetingError(f"Unsupported target.type={target.get('type')!r}")

    target["inclination"] = _angle(target.get("inclination"), "target.inclination")
    target["raan"] = _angle(target.get("raan"), "target.raan")
    target["aop"] = _angle(target.get("aop"), "target.aop")

    if target["type"] == "geostationary_orbit":
        target.setdefault("sma", {"value": EARTH_GEO_RADIUS_KM, "unit": "km"})
        target.setdefault("eccentricity", 0.0)
        target.setdefault("eccentricity_max", 1e-4)
        target.setdefault("inclination_max", {"value": 0.05, "unit": "deg"})
    elif target["type"] == "circular_orbit":
        if "radius" in target and "sma" not in target:
            target["sma"] = target.pop("radius")
        if "altitude" in target and "sma" not in target:
            altitude = _quantity(target["altitude"], "target.altitude", "km")
            if altitude["value"] <= 0:
                raise TargetingError("target.altitude must be positive")
            target["altitude"] = altitude
            target["sma"] = {"value": EARTH_RADIUS_KM + altitude["value"], "unit": "km"}
        target.setdefault("eccentricity", 0.0)
        target.setdefault("eccentricity_max", 1e-4)
        target.setdefault("inclination_max", {"value": 0.05, "unit": "deg"})
    else:
        target.setdefault("eccentricity_max", max(1e-6, abs(float(target.get("eccentricity", 0.0))) * 1e-3))
        target.setdefault("inclination_max", {"value": 0.05, "unit": "deg"})

    target["sma"] = _quantity(target.get("sma"), "target.sma", "km")
    target["eccentricity"] = _number(target.get("eccentricity", 0.0), "target.eccentricity")
    target["eccentricity_max"] = _number(target.get("eccentricity_max", 1e-4), "target.eccentricity_max")
    target["inclination_max"] = _quantity(target["inclination_max"], "target.inclination_max", "deg")
    if target["sma"]["value"] <= EARTH_RADIUS_KM:
        raise TargetingError("target.sma must exceed Earth radius")
    if not 0 <= target["eccentricity"] < 1:
        raise TargetingError("target.eccentricity must be in [0, 1)")
    return target


def canonicalize_target_problem(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TargetingError("TargetProblem must be a JSON object")
    p = deepcopy(raw)
    for key in ("schema_version", "problem_id", "initial_state", "target"):
        if key not in p:
            raise TargetingError(f"Missing required field {key}")
    p.setdefault("mission_id", p["problem_id"])
    p.setdefault("metadata", {})
    p.setdefault("limits", {})
    p.setdefault("execution", {})
    p.setdefault("verification", {})

    strategy = _canonical_strategy(p)
    state = _canonical_initial_state(p["initial_state"], strategy)
    target = _canonical_target(p["target"], strategy)

    limits = p["limits"]
    if "maximum_total_delta_v" in limits:
        limits["maximum_total_delta_v"] = _quantity(limits["maximum_total_delta_v"], "limits.maximum_total_delta_v", "km/s")
    if "minimum_altitude" in limits:
        limits["minimum_altitude"] = _quantity(limits["minimum_altitude"], "limits.minimum_altitude", "km")

    execution = p["execution"]
    execution.setdefault("backend", "gmat")
    execution.setdefault("targeting_fidelity", "two_body")
    execution.setdefault("acceptance_fidelity", "operational")
    execution.setdefault("artifact_persistence", "accepted_iterations")
    if "initial_coast_s" in execution:
        execution["initial_coast_s"] = _number(execution["initial_coast_s"], "execution.initial_coast_s")
        if execution["initial_coast_s"] < 0.0:
            raise TargetingError("execution.initial_coast_s must be non-negative")
    verification = p["verification"]
    verification.setdefault("required_level", "L1")
    verification.setdefault("run_acceptance_simulation", False)
    return p


def _apsis_radius(sma: float, ecc: float, apsis: str) -> float:
    return sma * (1.0 - ecc) if apsis == "periapsis" else sma * (1.0 + ecc)


def validate_target_problem(raw: dict[str, Any]) -> list[str]:
    p = canonicalize_target_problem(raw)
    warnings: list[str] = []
    strategy = p["transfer_strategy"]
    state = p["initial_state"]
    target = p["target"]

    r1 = _apsis_radius(state["sma"]["value"], state["eccentricity"], strategy["departure_apsis"])
    r2 = _apsis_radius(target["sma"]["value"], target["eccentricity"], strategy["arrival_apsis"])
    if math.isclose(r1, r2, rel_tol=0.0, abs_tol=1e-9):
        warnings.append("Departure and arrival apsis radii are equal; the energy-change portion may be zero")
    if min(r1, r2) <= EARTH_RADIUS_KM:
        raise TargetingError("The selected apsis radius intersects Earth")

    plane_change = abs(target["inclination"]["value"] - state["inclination"]["value"])
    if plane_change > 1e-8:
        warnings.append(
            "Impulsive plane change will be seeded at the orbital-plane intersection nearest apoapsis; "
            "STM/high-fidelity correction should refine the final state."
        )
    if p["execution"]["targeting_fidelity"] != "two_body":
        warnings.append("The analytic initial guess still uses a two-body model")
    if strategy["maneuver_model"] == "finite":
        warnings.append("Finite-burn target problems are supported for simulation evaluation; analytic solve still emits impulsive initial guesses")
    if strategy["type"] == "hohmann_transfer" and (
        state["eccentricity"] != 0.0 or target["eccentricity"] != 0.0
    ):
        warnings.append("Elliptical endpoint detected; canonical behavior is a generalized two-impulse apsidal transfer, not a strict Hohmann transfer")
    return warnings


from __future__ import annotations
from typing import Any

AVAILABLE_MANEUVER_TYPES = [
    "tangential_impulsive",
    "radial_impulsive",
    "normal_impulsive",
    "combined_impulsive",
    "plane_change_impulsive",
    "apsidal_raise_lower",
    "circularization",
    "phasing",
    "deep_space_impulsive",
    "finite_burn",
]


def build_targeting_formulation(problem: dict[str, Any]) -> dict[str, Any]:
    target = problem["target"]
    strategy = problem["transfer_strategy"]
    metric_requests = [
        {"metric_id": "spacecraft.final.orbit.sma", "unit": "km", "frame": problem["initial_state"]["frame"], "evaluation_event": "post_insertion"},
        {"metric_id": "spacecraft.final.orbit.eccentricity", "unit": "1", "frame": problem["initial_state"]["frame"], "evaluation_event": "post_insertion"},
        {"metric_id": "spacecraft.final.orbit.inclination", "unit": "deg", "frame": problem["initial_state"]["frame"], "evaluation_event": "post_insertion"},
        {"metric_id": "spacecraft.final.orbit.raan", "unit": "deg", "frame": problem["initial_state"]["frame"], "evaluation_event": "post_insertion"},
        {"metric_id": "spacecraft.final.orbit.aop", "unit": "deg", "frame": problem["initial_state"]["frame"], "evaluation_event": "post_insertion"},
        {"metric_id": "spacecraft.final.orbit.ta", "unit": "deg", "frame": problem["initial_state"]["frame"], "evaluation_event": "post_insertion"},
        {"metric_id": "mission.total_delta_v", "unit": "km/s", "evaluation_event": "mission_end"},
        {"metric_id": "trajectory.minimum_altitude", "unit": "km", "frame": problem["initial_state"]["frame"], "evaluation_event": "entire_trajectory"},
    ]
    constraints = [
        {"constraint_id": "final_sma", "kind": "equality", "metric_id": "spacecraft.final.orbit.sma", "relation": "eq", "target": target["sma"], "tolerance": {"value": 1.0, "unit": "km"}, "scale": {"value": 1.0, "unit": "km"}, "hard": True},
        {"constraint_id": "final_eccentricity", "kind": "equality", "metric_id": "spacecraft.final.orbit.eccentricity", "relation": "eq", "target": {"value": target["eccentricity"], "unit": "1"}, "tolerance": {"value": target["eccentricity_max"], "unit": "1"}, "scale": {"value": max(target["eccentricity_max"], 1e-8), "unit": "1"}, "hard": True},
        {"constraint_id": "final_inclination", "kind": "equality", "metric_id": "spacecraft.final.orbit.inclination", "relation": "eq", "target": target["inclination"], "tolerance": target["inclination_max"], "scale": target["inclination_max"], "hard": True},
        {"constraint_id": "final_raan", "kind": "equality", "metric_id": "spacecraft.final.orbit.raan", "relation": "eq", "target": target["raan"], "tolerance": target["inclination_max"], "scale": target["inclination_max"], "hard": True},
        {"constraint_id": "final_aop", "kind": "equality", "metric_id": "spacecraft.final.orbit.aop", "relation": "eq", "target": target["aop"], "tolerance": target["inclination_max"], "scale": target["inclination_max"], "hard": True},
    ]
    if "argument_of_latitude" in target:
        metric_requests.append({
            "metric_id": "spacecraft.final.orbit.argument_of_latitude",
            "unit": "deg",
            "frame": problem["initial_state"]["frame"],
            "evaluation_event": "post_insertion",
            "derived_from": ["spacecraft.final.orbit.aop", "spacecraft.final.orbit.ta"],
        })
        constraints.append({
            "constraint_id": "final_argument_of_latitude",
            "kind": "equality",
            "metric_id": "spacecraft.final.orbit.argument_of_latitude",
            "relation": "eq",
            "target": target["argument_of_latitude"],
            "tolerance": target["argument_of_latitude_max"],
            "scale": target["argument_of_latitude_max"],
            "hard": True,
        })
    return {
        "schema_version": "1.1.0",
        "problem_id": problem["problem_id"],
        "transfer_strategy_type": strategy["type"],
        "available_maneuver_types": AVAILABLE_MANEUVER_TYPES,
        "maneuver_plan": {
            "impulse_count": 2,
            "prefer_concurrent_effects": False,
            "plane_change_policy": strategy["plane_change_policy"],
            "plane_change_policy_config": strategy.get("plane_change_policy_config", {"type": strategy["plane_change_policy"]}),
            "departure_event": strategy["departure_apsis"],
            "arrival_event": strategy["arrival_apsis"],
            "placement_rule": "plane changes must occur on a valid plane-intersection line unless explicitly delegated to a later high-fidelity correction layer",
        },
        "decision_variables": [
            {"variable_id": "transfer_injection.delta_v_v", "unit": "km/s", "scale": 1.0, "bounds": [-10.0, 10.0]},
            {"variable_id": "transfer_injection.delta_v_n", "unit": "km/s", "scale": 1.0, "bounds": [-10.0, 10.0]},
            {"variable_id": "orbit_insertion.delta_v_v", "unit": "km/s", "scale": 1.0, "bounds": [-10.0, 10.0]},
            {"variable_id": "orbit_insertion.delta_v_n", "unit": "km/s", "scale": 1.0, "bounds": [-10.0, 10.0]},
            {"variable_id": "transfer.coast_time", "unit": "s", "scale": 10000.0, "bounds": [1.0, 604800.0]},
        ],
        "metric_requests": metric_requests,
        "constraints": constraints,
        "solver_policy": {
            "initial_guess_backend": "analytic_two_impulse_apsidal",
            "pre_correction_refinement": "soi_hyperbola_bplane_matching",
            "target_solver": "stm_correction_on_vector_miss",
            "reason": "Use patched conics and hyperbola/B-plane matching as the cheap path; invoke STM correction only when high-fidelity final orbital-state residuals exceed tolerance.",
        },
    }

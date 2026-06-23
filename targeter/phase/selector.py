from __future__ import annotations

import copy
import math
from typing import Any

from targeter.phase.context import PhaseContext, build_phase_context, normalize_angle_deg


PHASE_TOLERANCE_DEG = 1.0e-9


def select_phase_strategy(problem: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    context = build_phase_context(problem, candidate)
    if context is None:
        return {
            "schema_version": "1.0.0",
            "selected": None,
            "status": "disabled",
            "reason": "No enabled phase policy and compatible phase target were found.",
            "rejected": [],
            "controls": [],
        }

    decision = _in_plane_drift_decision(context)
    allowed = context.phase_policy.get("allowed_strategies", [])
    rejected = []
    if "coast_to_phase" in allowed:
        rejected.append({"strategy": "coast_to_phase", "reason": "final_state propagation duration is fixed for this policy"})
    for strategy in allowed:
        if strategy in {"coast_to_phase", "in_plane_drift"}:
            continue
        rejected.append({"strategy": strategy, "reason": "incoming feature"})

    if "in_plane_drift" not in allowed:
        return {
            "schema_version": "1.0.0",
            "selected": None,
            "status": "not_selected",
            "reason": "in_plane_drift is the only implemented phasing strategy and is not allowed by policy.",
            "rejected": rejected,
            "controls": [],
        }
    if abs(context.required_phase_shift_deg) <= PHASE_TOLERANCE_DEG:
        return {
            "schema_version": "1.0.0",
            "selected": "coast_to_phase",
            "status": "already_satisfied",
            "reason": "Nominal trajectory already satisfies the requested phase at final_state.",
            "rejected": rejected,
            "controls": [],
            "phase_assessment": _phase_assessment(context),
        }
    if decision["status"] != "selected":
        rejected.append({"strategy": "in_plane_drift", "reason": decision["reason"]})
        return {
            "schema_version": "1.0.0",
            "selected": None,
            "status": "not_selected",
            "reason": "No allowed phase strategy can satisfy the current context.",
            "rejected": rejected,
            "controls": [],
            "phase_assessment": _phase_assessment(context),
        }
    decision["rejected"] = rejected
    return decision


def apply_phase_strategy(problem: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    decision = select_phase_strategy(problem, candidate)
    if decision.get("selected") != "in_plane_drift" or decision.get("status") != "selected":
        candidate = copy.deepcopy(candidate)
        candidate["phase_strategy_decision"] = decision
        return candidate

    candidate = copy.deepcopy(candidate)
    plan = decision["phase_plan"]
    enter = {
        "maneuver_id": "enter_phase_drift",
        "maneuver_type": "phasing",
        "event": "post_orbit_insertion",
        "event_type": "immediate",
        "angle_kind": "true_anomaly",
        "true_anomaly_deg": plan["entry_true_anomaly_deg"],
        "frame": "VNB",
        "components_km_s": [plan["enter_delta_v_km_s"], 0.0, 0.0],
        "magnitude_km_s": abs(plan["enter_delta_v_km_s"]),
        "concurrent_effects": ["phase_change"],
        "plane_change_deg": 0.0,
        "signed_vnb_normal_rotation_deg": 0.0,
        "post_maneuver_coast_s": plan["drift_duration_s"],
    }
    exit_ = {
        "maneuver_id": "exit_phase_drift",
        "maneuver_type": "phasing",
        "event": "post_phase_drift",
        "event_type": "immediate",
        "angle_kind": "true_anomaly",
        "true_anomaly_deg": plan["exit_true_anomaly_deg"],
        "frame": "VNB",
        "components_km_s": [plan["exit_delta_v_km_s"], 0.0, 0.0],
        "magnitude_km_s": abs(plan["exit_delta_v_km_s"]),
        "concurrent_effects": ["phase_change", "orbit_restore"],
        "plane_change_deg": 0.0,
        "signed_vnb_normal_rotation_deg": 0.0,
    }
    candidate["maneuvers"].extend([enter, exit_])
    candidate.setdefault("variable_values", {})
    candidate["variable_values"]["phase_drift.duration_s"] = {"value": plan["drift_duration_s"], "unit": "s"}
    candidate["variable_values"]["enter_phase_drift.delta_v_v"] = {"value": plan["enter_delta_v_km_s"], "unit": "km/s"}
    candidate["variable_values"]["exit_phase_drift.delta_v_v"] = {"value": plan["exit_delta_v_km_s"], "unit": "km/s"}
    assessment = candidate.setdefault("analytic_assessment", {})
    assessment["phase_strategy"] = decision["selected"]
    assessment["phase_target_deg"] = decision["phase_assessment"]["target_phase_deg"]
    assessment["phase_nominal_final_deg"] = decision["phase_assessment"]["nominal_final_phase_deg"]
    assessment["phase_required_shift_deg"] = decision["phase_assessment"]["required_phase_shift_deg"]
    assessment["phase_drift_sma_km"] = plan["drift_sma_km"]
    assessment["phase_drift_duration_s"] = plan["drift_duration_s"]
    assessment["phase_delta_v_km_s"] = plan["total_delta_v_km_s"]
    assessment["total_delta_v_km_s"] = sum(float(m["magnitude_km_s"]) for m in candidate["maneuvers"])
    candidate["phase_strategy_decision"] = decision
    return candidate


def _phase_assessment(context: PhaseContext) -> dict[str, float | str]:
    nominal_final = normalize_angle_deg(
        context.arrival_phase_deg + math.degrees(context.target_mean_motion_rad_s * context.final_coast_s)
    )
    return {
        "target_parameter": "argument_of_latitude",
        "target_phase_deg": context.target_phase_deg,
        "arrival_phase_deg": context.arrival_phase_deg,
        "nominal_final_phase_deg": nominal_final,
        "desired_restore_phase_deg": context.desired_restore_phase_deg,
        "required_phase_shift_deg": context.required_phase_shift_deg,
        "final_coast_s": context.final_coast_s,
    }


def _in_plane_drift_decision(context: PhaseContext) -> dict[str, Any]:
    if abs(context.target_eccentricity) > 1.0e-3:
        return {"status": "rejected", "reason": "in_plane_drift currently requires a near-circular target orbit"}
    max_revs = int(context.phase_policy.get("max_revolutions", 5))
    max_delta_v = context.phase_policy.get("max_delta_v_km_s")
    plan = _best_drift_plan(context, max_revs)
    if plan is None:
        return {"status": "rejected", "reason": "no positive drift orbit could be found within max_revolutions"}
    if max_delta_v is not None and plan["total_delta_v_km_s"] > float(max_delta_v):
        return {
            "status": "rejected",
            "reason": "estimated phasing delta-v exceeds max_delta_v_km_s",
            "estimated_delta_v_km_s": plan["total_delta_v_km_s"],
        }
    return {
        "schema_version": "1.0.0",
        "selected": "in_plane_drift",
        "status": "selected",
        "reason": "Phase target is enabled, final_state propagation is fixed, target orbit is near-circular, and in-plane burns are allowed.",
        "controls": [
            "enter_phase_drift.delta_v_v",
            "phase_drift.duration_s",
            "exit_phase_drift.delta_v_v",
        ],
        "phase_assessment": _phase_assessment(context),
        "phase_plan": plan,
    }


def _best_drift_plan(context: PhaseContext, max_revs: int) -> dict[str, float] | None:
    required_rad = math.radians(context.required_phase_shift_deg)
    mu = context.mu_km3_s2
    a = context.target_sma_km
    n = context.target_mean_motion_rad_s
    v_circular = math.sqrt(mu / a)
    best: dict[str, float] | None = None
    for revs in range(1, max_revs + 1):
        duration = revs * context.target_period_s
        for wrap in range(-max_revs, max_revs + 1):
            phase_rad = required_rad + 2.0 * math.pi * wrap
            if abs(phase_rad) <= PHASE_TOLERANCE_DEG:
                continue
            drift_n = n + phase_rad / duration
            if drift_n <= 0.0:
                continue
            drift_sma = (mu / (drift_n * drift_n)) ** (1.0 / 3.0)
            if drift_sma <= 0.0:
                continue
            speed_squared = mu * (2.0 / a - 1.0 / drift_sma)
            if speed_squared <= 0.0:
                continue
            drift_speed = math.sqrt(speed_squared)
            enter_dv = drift_speed - v_circular
            total_dv = 2.0 * abs(enter_dv)
            plan = {
                "drift_revolutions": float(revs),
                "drift_duration_s": duration,
                "drift_sma_km": drift_sma,
                "enter_delta_v_km_s": enter_dv,
                "exit_delta_v_km_s": -enter_dv,
                "total_delta_v_km_s": total_dv,
                "entry_true_anomaly_deg": 0.0,
                "exit_true_anomaly_deg": 0.0,
                "achieved_phase_shift_deg": math.degrees(phase_rad),
            }
            if best is None or (total_dv, duration) < (best["total_delta_v_km_s"], best["drift_duration_s"]):
                best = plan
    return best

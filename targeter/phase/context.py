from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


DEFAULT_FINAL_COAST_S = 172800.0


def normalize_angle_deg(value: float) -> float:
    return value % 360.0


def signed_angle_delta_deg(target: float, current: float) -> float:
    return (target - current + 180.0) % 360.0 - 180.0


@dataclass(frozen=True)
class PhaseContext:
    central_body: str
    mu_km3_s2: float
    target_sma_km: float
    target_eccentricity: float
    target_phase_deg: float
    arrival_phase_deg: float
    final_coast_s: float
    target_mean_motion_rad_s: float
    target_period_s: float
    phase_policy: dict[str, Any]

    @property
    def desired_restore_phase_deg(self) -> float:
        drift_deg = math.degrees(self.target_mean_motion_rad_s * self.final_coast_s)
        return normalize_angle_deg(self.target_phase_deg - drift_deg)

    @property
    def required_phase_shift_deg(self) -> float:
        return signed_angle_delta_deg(self.desired_restore_phase_deg, self.arrival_phase_deg)


def build_phase_context(problem: dict[str, Any], candidate: dict[str, Any]) -> PhaseContext | None:
    strategy = problem["transfer_strategy"]
    policy = strategy.get("phase_policy")
    target = problem["target"]
    if not policy or not policy.get("enabled", False):
        return None
    if policy.get("target", "argument_of_latitude") != "argument_of_latitude":
        return None
    if "argument_of_latitude" not in target:
        return None

    mu = float(strategy["central_body_mu"]["value"])
    sma = float(target["sma"]["value"])
    n = math.sqrt(mu / (sma**3))
    period = 2.0 * math.pi / n
    assessment = candidate.get("analytic_assessment", {})
    arrival_phase = float(assessment.get("arrival_argument_of_latitude_deg", assessment.get("arrival_true_anomaly_deg", 0.0)))
    final_coast_s = float(problem.get("execution", {}).get("post_insertion_coast_s", DEFAULT_FINAL_COAST_S))
    return PhaseContext(
        central_body=strategy["central_body"],
        mu_km3_s2=mu,
        target_sma_km=sma,
        target_eccentricity=float(target.get("eccentricity", 0.0)),
        target_phase_deg=float(target["argument_of_latitude"]["value"]),
        arrival_phase_deg=arrival_phase,
        final_coast_s=final_coast_s,
        target_mean_motion_rad_s=n,
        target_period_s=period,
        phase_policy=policy,
    )

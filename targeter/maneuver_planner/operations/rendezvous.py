from __future__ import annotations

from collections.abc import Sequence

from targeter.lambert import LambertSolution, solve_lambert


RENDEZVOUS_OPERATION_TYPES = {
    "hohmann_rendezvous",
    "two_impulse_intercept",
    "lambert_intercept",
    "fine_tune_closest_approach",
    "match_velocity",
}


def plan_lambert_intercept(
    r1_km: Sequence[float],
    r2_km: Sequence[float],
    mu_km3_s2: float,
    tof_s: float,
    *,
    prograde: bool = True,
) -> LambertSolution:
    return solve_lambert(r1_km, r2_km, mu_km3_s2, tof_s, prograde=prograde)

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


@dataclass(frozen=True)
class LambertSolution:
    r1_km: tuple[float, float, float]
    r2_km: tuple[float, float, float]
    tof_s: float
    mu_km3_s2: float
    v1_km_s: tuple[float, float, float]
    v2_km_s: tuple[float, float, float]
    transfer_angle_rad: float
    prograde: bool
    iterations: int


def _vec(value: Sequence[float], name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.shape != (3,):
        raise ValueError(f"{name} must be a 3-vector")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain finite values")
    return arr


def _stumpff_c(z: float) -> float:
    if z > 1e-8:
        s = math.sqrt(z)
        return (1.0 - math.cos(s)) / z
    if z < -1e-8:
        s = math.sqrt(-z)
        return (math.cosh(s) - 1.0) / -z
    return 0.5 - z / 24.0 + z * z / 720.0 - z * z * z / 40320.0


def _stumpff_s(z: float) -> float:
    if z > 1e-8:
        s = math.sqrt(z)
        return (s - math.sin(s)) / (s**3)
    if z < -1e-8:
        s = math.sqrt(-z)
        return (math.sinh(s) - s) / (s**3)
    return 1.0 / 6.0 - z / 120.0 + z * z / 5040.0 - z * z * z / 362880.0


def hohmann_transfer_time_s(mu_km3_s2: float, departure_radius_km: float, arrival_radius_km: float) -> float:
    """Return the half-period Hohmann transfer time between circular coplanar radii."""
    if mu_km3_s2 <= 0:
        raise ValueError("mu_km3_s2 must be positive")
    if departure_radius_km <= 0 or arrival_radius_km <= 0:
        raise ValueError("orbit radii must be positive")
    transfer_sma = 0.5 * (departure_radius_km + arrival_radius_km)
    return math.pi * math.sqrt(transfer_sma**3 / mu_km3_s2)


def default_lambert_tof_s(mu_km3_s2: float, r1_km: Sequence[float], r2_km: Sequence[float]) -> float:
    """Approximate time of flight from the circular-coplanar Hohmann assumption."""
    r1 = float(np.linalg.norm(_vec(r1_km, "r1_km")))
    r2 = float(np.linalg.norm(_vec(r2_km, "r2_km")))
    return hohmann_transfer_time_s(mu_km3_s2, r1, r2)


def transfer_angle_rad(r1_km: Sequence[float], r2_km: Sequence[float], prograde: bool = True) -> float:
    r1 = _vec(r1_km, "r1_km")
    r2 = _vec(r2_km, "r2_km")
    r1_norm = np.linalg.norm(r1)
    r2_norm = np.linalg.norm(r2)
    if r1_norm <= 0 or r2_norm <= 0:
        raise ValueError("position vectors must be nonzero")
    cos_dtheta = float(np.dot(r1, r2) / (r1_norm * r2_norm))
    cos_dtheta = max(-1.0, min(1.0, cos_dtheta))
    dtheta = math.acos(cos_dtheta)
    cross_z = float(np.cross(r1, r2)[2])
    if prograde and cross_z < 0.0:
        dtheta = 2.0 * math.pi - dtheta
    if not prograde and cross_z >= 0.0:
        dtheta = 2.0 * math.pi - dtheta
    return dtheta


def solve_lambert(
    r1_km: Sequence[float],
    r2_km: Sequence[float],
    mu_km3_s2: float,
    tof_s: float | None = None,
    *,
    prograde: bool = True,
    max_iterations: int = 100,
    tolerance_s: float = 1e-7,
) -> LambertSolution:
    """Solve the zero-revolution Lambert problem using universal variables.

    If ``tof_s`` is omitted, AMAT's first guess assumes circular coplanar
    departure/arrival orbits and uses the Hohmann half-period between the two
    position-vector radii.
    """
    if mu_km3_s2 <= 0:
        raise ValueError("mu_km3_s2 must be positive")
    r1 = _vec(r1_km, "r1_km")
    r2 = _vec(r2_km, "r2_km")
    tof = float(tof_s if tof_s is not None else default_lambert_tof_s(mu_km3_s2, r1, r2))
    if tof <= 0:
        raise ValueError("tof_s must be positive")

    r1_norm = float(np.linalg.norm(r1))
    r2_norm = float(np.linalg.norm(r2))
    dtheta = transfer_angle_rad(r1, r2, prograde=prograde)
    sin_dtheta = math.sin(dtheta)
    if abs(sin_dtheta) < 1e-12:
        raise ValueError("Lambert transfer angle is singular for co-linear endpoint vectors")
    a_param = sin_dtheta * math.sqrt(r1_norm * r2_norm / (1.0 - math.cos(dtheta)))
    if abs(a_param) < 1e-12:
        raise ValueError("Lambert geometry produced a singular A parameter")

    def y_for_z(z: float) -> float:
        c = _stumpff_c(z)
        s = _stumpff_s(z)
        if c <= 0:
            return float("nan")
        return r1_norm + r2_norm + a_param * (z * s - 1.0) / math.sqrt(c)

    def time_for_z(z: float) -> float:
        c = _stumpff_c(z)
        s = _stumpff_s(z)
        y = y_for_z(z)
        if not math.isfinite(y) or y < 0.0 or c <= 0.0:
            return float("nan")
        x = math.sqrt(y / c)
        return (x**3 * s + a_param * math.sqrt(y)) / math.sqrt(mu_km3_s2)

    z_low = -4.0 * math.pi**2
    z_high = 4.0 * math.pi**2
    for _ in range(80):
        t_low = time_for_z(z_low)
        if math.isfinite(t_low) and t_low <= tof:
            break
        z_low *= 0.5
    for _ in range(80):
        t_high = time_for_z(z_high)
        if math.isfinite(t_high) and t_high >= tof:
            break
        z_high *= 2.0
    else:
        raise RuntimeError("Could not bracket Lambert time of flight")

    z = 0.0
    iterations = 0
    for iterations in range(1, max_iterations + 1):
        z = 0.5 * (z_low + z_high)
        t_z = time_for_z(z)
        if not math.isfinite(t_z):
            z_low = z
            continue
        if abs(t_z - tof) <= tolerance_s:
            break
        if t_z <= tof:
            z_low = z
        else:
            z_high = z
    else:
        raise RuntimeError("Lambert solver did not converge")

    y = y_for_z(z)
    if y < 0.0:
        raise RuntimeError("Lambert solver converged to invalid negative y")
    f = 1.0 - y / r1_norm
    g = a_param * math.sqrt(y / mu_km3_s2)
    gdot = 1.0 - y / r2_norm
    if abs(g) < 1e-12:
        raise RuntimeError("Lambert solver converged to singular g")
    v1 = (r2 - f * r1) / g
    v2 = (gdot * r2 - r1) / g

    return LambertSolution(
        r1_km=tuple(float(x) for x in r1),
        r2_km=tuple(float(x) for x in r2),
        tof_s=tof,
        mu_km3_s2=mu_km3_s2,
        v1_km_s=tuple(float(x) for x in v1),
        v2_km_s=tuple(float(x) for x in v2),
        transfer_angle_rad=dtheta,
        prograde=prograde,
        iterations=iterations,
    )

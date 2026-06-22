from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Sequence

import numpy as np

from targeter.lambert import LambertSolution, default_lambert_tof_s, solve_lambert


@dataclass(frozen=True)
class CircularOrbitState:
    radius_km: float
    phase_rad: float
    mu_central_km3_s2: float

    def mean_motion_rad_s(self) -> float:
        if self.radius_km <= 0 or self.mu_central_km3_s2 <= 0:
            raise ValueError("Circular orbit radius and central mu must be positive")
        return math.sqrt(self.mu_central_km3_s2 / self.radius_km**3)

    def position_at(self, elapsed_s: float) -> np.ndarray:
        theta = self.phase_rad + self.mean_motion_rad_s() * elapsed_s
        return self.radius_km * np.array([math.cos(theta), math.sin(theta), 0.0], dtype=float)

    def velocity_at(self, elapsed_s: float) -> np.ndarray:
        theta = self.phase_rad + self.mean_motion_rad_s() * elapsed_s
        speed = math.sqrt(self.mu_central_km3_s2 / self.radius_km)
        return speed * np.array([-math.sin(theta), math.cos(theta), 0.0], dtype=float)


@dataclass(frozen=True)
class PatchedConicsCandidate:
    departure_time_s: float
    arrival_time_s: float
    tof_s: float
    departure_position_km: tuple[float, float, float]
    arrival_position_km: tuple[float, float, float]
    departure_velocity_required_km_s: tuple[float, float, float]
    arrival_velocity_required_km_s: tuple[float, float, float]
    departure_orbit_velocity_km_s: tuple[float, float, float]
    arrival_body_velocity_km_s: tuple[float, float, float]
    departure_delta_v_km_s: tuple[float, float, float]
    departure_delta_v_magnitude_km_s: float
    arrival_v_inf_km_s: tuple[float, float, float]
    arrival_v_inf_magnitude_km_s: float
    lambert: LambertSolution

    def to_dict(self) -> dict:
        data = asdict(self)
        data["lambert"] = asdict(self.lambert)
        return data


@dataclass(frozen=True)
class ArrivalHyperbola:
    body_mu_km3_s2: float
    body_radius_km: float
    soi_radius_km: float
    periapsis_radius_km: float
    periapsis_altitude_km: float
    v_inf_km_s: tuple[float, float, float]
    v_inf_magnitude_km_s: float
    semi_major_axis_km: float
    eccentricity: float
    impact_parameter_km: float
    turning_angle_rad: float
    soi_to_periapsis_time_s: float
    soi_entry_position_km: tuple[float, float, float]
    soi_entry_velocity_km_s: tuple[float, float, float]


@dataclass(frozen=True)
class PatchedConicsSoiCandidate(PatchedConicsCandidate):
    periapsis_time_s: float
    soi_entry_time_s: float
    soi_entry_position_km: tuple[float, float, float]
    soi_entry_body_position_km: tuple[float, float, float]
    soi_entry_body_velocity_km_s: tuple[float, float, float]
    soi_entry_relative_position_km: tuple[float, float, float]
    soi_entry_relative_velocity_km_s: tuple[float, float, float]
    soi_entry_relative_speed_km_s: float
    arrival_hyperbola: ArrivalHyperbola

    def to_dict(self) -> dict:
        data = asdict(self)
        data["lambert"] = asdict(self.lambert)
        data["arrival_hyperbola"] = asdict(self.arrival_hyperbola)
        return data


def _norm_tuple(vector: Sequence[float]) -> tuple[tuple[float, float, float], float]:
    arr = np.asarray(vector, dtype=float)
    return tuple(float(x) for x in arr), float(np.linalg.norm(arr))


def _phase_error_rad(value: float) -> float:
    return abs((value + math.pi) % (2.0 * math.pi) - math.pi)


def laplace_soi_radius_km(orbit_radius_km: float, body_mu_km3_s2: float, central_mu_km3_s2: float) -> float:
    """Return the classical Laplace sphere-of-influence radius."""
    if orbit_radius_km <= 0.0:
        raise ValueError("orbit_radius_km must be positive")
    if body_mu_km3_s2 <= 0.0 or central_mu_km3_s2 <= 0.0:
        raise ValueError("gravitational parameters must be positive")
    return float(orbit_radius_km * (body_mu_km3_s2 / central_mu_km3_s2) ** (2.0 / 5.0))


def _unit(vector: Sequence[float], name: str) -> np.ndarray:
    arr = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(arr))
    if arr.shape != (3,) or not np.all(np.isfinite(arr)) or norm <= 0.0:
        raise ValueError(f"{name} must be a finite nonzero 3-vector")
    return arr / norm


def arrival_hyperbola_from_vinf(
    v_inf_km_s: Sequence[float],
    *,
    body_mu_km3_s2: float,
    body_radius_km: float,
    periapsis_altitude_km: float,
    soi_radius_km: float,
    b_plane_direction: Sequence[float] | None = None,
) -> ArrivalHyperbola:
    """Build a body-centered arrival hyperbola and SOI-entry state.

    The SOI-entry state is an asymptotic patched-conics approximation: position
    is placed on the incoming asymptote at the requested SOI radius, while
    velocity is the incoming hyperbolic excess vector. This is intentionally a
    seed model; the n-body correction loop owns the final cleanup.
    """
    v_inf = np.asarray(v_inf_km_s, dtype=float)
    if v_inf.shape != (3,) or not np.all(np.isfinite(v_inf)):
        raise ValueError("v_inf_km_s must be a finite 3-vector")
    v_inf_mag = float(np.linalg.norm(v_inf))
    if v_inf_mag <= 0.0:
        raise ValueError("v_inf_km_s must be nonzero")
    if body_mu_km3_s2 <= 0.0:
        raise ValueError("body_mu_km3_s2 must be positive")
    if body_radius_km < 0.0 or periapsis_altitude_km < 0.0:
        raise ValueError("body radius and periapsis altitude must be non-negative")
    periapsis_radius = body_radius_km + periapsis_altitude_km
    if soi_radius_km <= periapsis_radius:
        raise ValueError("soi_radius_km must exceed periapsis radius")

    incoming_hat = _unit(v_inf, "v_inf_km_s")
    if b_plane_direction is None:
        ref = np.array([0.0, 0.0, 1.0], dtype=float)
        if abs(float(np.dot(ref, incoming_hat))) > 0.95:
            ref = np.array([1.0, 0.0, 0.0], dtype=float)
    else:
        ref = _unit(b_plane_direction, "b_plane_direction")
    b_hat = ref - float(np.dot(ref, incoming_hat)) * incoming_hat
    b_norm = float(np.linalg.norm(b_hat))
    if b_norm <= 1e-12:
        raise ValueError("b_plane_direction must not be parallel to v_inf")
    b_hat /= b_norm

    sma_abs = body_mu_km3_s2 / (v_inf_mag * v_inf_mag)
    eccentricity = 1.0 + periapsis_radius * v_inf_mag * v_inf_mag / body_mu_km3_s2
    impact_parameter = periapsis_radius * math.sqrt(1.0 + 2.0 * body_mu_km3_s2 / (periapsis_radius * v_inf_mag * v_inf_mag))
    turning_angle = 2.0 * math.asin(1.0 / eccentricity)
    along = math.sqrt(max(soi_radius_km * soi_radius_km - impact_parameter * impact_parameter, 0.0))
    rel_position = -along * incoming_hat + impact_parameter * b_hat

    h_arg = (soi_radius_km / sma_abs + 1.0) / eccentricity
    h_arg = max(1.0, h_arg)
    hyperbolic_anomaly = math.acosh(h_arg)
    soi_to_periapsis_time = math.sqrt(sma_abs**3 / body_mu_km3_s2) * (
        eccentricity * math.sinh(hyperbolic_anomaly) - hyperbolic_anomaly
    )

    return ArrivalHyperbola(
        body_mu_km3_s2=float(body_mu_km3_s2),
        body_radius_km=float(body_radius_km),
        soi_radius_km=float(soi_radius_km),
        periapsis_radius_km=float(periapsis_radius),
        periapsis_altitude_km=float(periapsis_altitude_km),
        v_inf_km_s=tuple(float(x) for x in v_inf),
        v_inf_magnitude_km_s=v_inf_mag,
        semi_major_axis_km=float(-sma_abs),
        eccentricity=float(eccentricity),
        impact_parameter_km=float(impact_parameter),
        turning_angle_rad=float(turning_angle),
        soi_to_periapsis_time_s=float(soi_to_periapsis_time),
        soi_entry_position_km=tuple(float(x) for x in rel_position),
        soi_entry_velocity_km_s=tuple(float(x) for x in v_inf),
    )


def hohmann_phase_departure_time_s(
    departure_orbit: CircularOrbitState,
    arrival_orbit: CircularOrbitState,
    tof_s: float,
    *,
    search_window_s: float | None = None,
) -> float:
    """Return the first departure time satisfying the circular Hohmann phase rule.

    The patched-conics layer uses this as the first departure-time estimate
    before evaluating Lambert candidates. For an outward transfer, the target
    should be roughly pi radians ahead of the arrival point after the transfer
    time; for an inward transfer the same anti-alignment rule gives a useful
    first estimate for this MVP.
    """
    n_depart = departure_orbit.mean_motion_rad_s()
    n_arrive = arrival_orbit.mean_motion_rad_s()
    phase_now = arrival_orbit.phase_rad - departure_orbit.phase_rad
    desired_phase = math.pi - n_arrive * tof_s
    relative_rate = n_arrive - n_depart
    if abs(relative_rate) < 1e-15:
        return 0.0
    period = 2.0 * math.pi / abs(relative_rate)
    window = search_window_s if search_window_s is not None else period
    best_t = 0.0
    best_err = float("inf")
    for k in range(-4, 9):
        t = (desired_phase - phase_now + 2.0 * math.pi * k) / relative_rate
        while t < 0.0:
            t += period
        if t <= window:
            err = _phase_error_rad((phase_now + relative_rate * t) - desired_phase)
            if err < best_err:
                best_t = t
                best_err = err
    return best_t


def solve_circular_coplanar_patched_conics(
    departure_orbit: CircularOrbitState,
    arrival_orbit: CircularOrbitState,
    *,
    central_mu_km3_s2: float,
    tof_s: float | None = None,
    search_window_s: float | None = None,
    samples: int = 121,
    prograde: bool = True,
) -> PatchedConicsCandidate:
    """Search departure time and solve Lambert for a circular-coplanar patched-conics seed."""
    if samples < 3:
        raise ValueError("samples must be at least 3")
    first_r1 = departure_orbit.position_at(0.0)
    first_r2 = arrival_orbit.position_at(0.0)
    transfer_tof = float(tof_s if tof_s is not None else default_lambert_tof_s(central_mu_km3_s2, first_r1, first_r2))
    first_departure_s = hohmann_phase_departure_time_s(
        departure_orbit,
        arrival_orbit,
        transfer_tof,
        search_window_s=search_window_s,
    )

    synodic_period = 2.0 * math.pi / abs(arrival_orbit.mean_motion_rad_s() - departure_orbit.mean_motion_rad_s())
    window = float(search_window_s if search_window_s is not None else synodic_period)
    half_width = min(window, synodic_period) / 2.0
    start = max(0.0, first_departure_s - half_width)
    stop = min(window, first_departure_s + half_width)
    if stop <= start:
        start, stop = 0.0, window

    best: PatchedConicsCandidate | None = None
    for departure_time_s in np.linspace(start, stop, samples):
        arrival_time_s = float(departure_time_s + transfer_tof)
        r1 = departure_orbit.position_at(float(departure_time_s))
        r2 = arrival_orbit.position_at(arrival_time_s)
        try:
            lambert = solve_lambert(r1, r2, central_mu_km3_s2, transfer_tof, prograde=prograde)
        except Exception:
            continue
        v_depart_orbit = departure_orbit.velocity_at(float(departure_time_s))
        v_arrival_body = arrival_orbit.velocity_at(arrival_time_s)
        dv_vec = np.asarray(lambert.v1_km_s) - v_depart_orbit
        vinf_vec = np.asarray(lambert.v2_km_s) - v_arrival_body
        dv_tuple, dv_mag = _norm_tuple(dv_vec)
        vinf_tuple, vinf_mag = _norm_tuple(vinf_vec)
        candidate = PatchedConicsCandidate(
            departure_time_s=float(departure_time_s),
            arrival_time_s=arrival_time_s,
            tof_s=transfer_tof,
            departure_position_km=tuple(float(x) for x in r1),
            arrival_position_km=tuple(float(x) for x in r2),
            departure_velocity_required_km_s=lambert.v1_km_s,
            arrival_velocity_required_km_s=lambert.v2_km_s,
            departure_orbit_velocity_km_s=tuple(float(x) for x in v_depart_orbit),
            arrival_body_velocity_km_s=tuple(float(x) for x in v_arrival_body),
            departure_delta_v_km_s=dv_tuple,
            departure_delta_v_magnitude_km_s=dv_mag,
            arrival_v_inf_km_s=vinf_tuple,
            arrival_v_inf_magnitude_km_s=vinf_mag,
            lambert=lambert,
        )
        if best is None or candidate.departure_delta_v_magnitude_km_s < best.departure_delta_v_magnitude_km_s:
            best = candidate
    if best is None:
        raise RuntimeError("No Lambert candidate could be generated in the departure search window")
    return best


def solve_circular_coplanar_soi_patched_conics(
    departure_orbit: CircularOrbitState,
    arrival_orbit: CircularOrbitState,
    *,
    central_mu_km3_s2: float,
    arrival_body_mu_km3_s2: float,
    arrival_body_radius_km: float,
    periapsis_altitude_km: float,
    soi_radius_km: float | None = None,
    tof_s: float | None = None,
    search_window_s: float | None = None,
    samples: int = 121,
    prograde: bool = True,
    b_plane_direction: Sequence[float] | None = None,
) -> PatchedConicsSoiCandidate:
    """Generate a patched-conics seed with SOI entry and arrival hyperbola matching.

    This is still an analytic seed, not a high-fidelity trajectory. The process
    is:

    1. Use the circular-coplanar Hohmann time as the periapsis-arrival guess.
    2. Estimate arrival v-infinity from a body-center Lambert solve.
    3. Build the arrival-body hyperbola for the requested periapsis.
    4. Move the Lambert endpoint back to the SOI-entry state and resolve.

    The resulting candidate is suitable as the first iterate for n-body
    correction, where the evaluator should adjust departure time, TOF, and/or
    burn components against propagated residuals.
    """
    if samples < 3:
        raise ValueError("samples must be at least 3")
    first_r1 = departure_orbit.position_at(0.0)
    first_r2 = arrival_orbit.position_at(0.0)
    transfer_tof = float(tof_s if tof_s is not None else default_lambert_tof_s(central_mu_km3_s2, first_r1, first_r2))
    first_departure_s = hohmann_phase_departure_time_s(
        departure_orbit,
        arrival_orbit,
        transfer_tof,
        search_window_s=search_window_s,
    )
    synodic_period = 2.0 * math.pi / abs(arrival_orbit.mean_motion_rad_s() - departure_orbit.mean_motion_rad_s())
    window = float(search_window_s if search_window_s is not None else synodic_period)
    half_width = min(window, synodic_period) / 2.0
    start = max(0.0, first_departure_s - half_width)
    stop = min(window, first_departure_s + half_width)
    if stop <= start:
        start, stop = 0.0, window

    soi = float(
        soi_radius_km
        if soi_radius_km is not None
        else laplace_soi_radius_km(arrival_orbit.radius_km, arrival_body_mu_km3_s2, central_mu_km3_s2)
    )

    best: PatchedConicsSoiCandidate | None = None
    for departure_time_s in np.linspace(start, stop, samples):
        departure_time_s = float(departure_time_s)
        periapsis_time_s = departure_time_s + transfer_tof
        r_depart = departure_orbit.position_at(departure_time_s)
        v_depart_orbit = departure_orbit.velocity_at(departure_time_s)
        r_body_periapsis = arrival_orbit.position_at(periapsis_time_s)
        v_body_periapsis = arrival_orbit.velocity_at(periapsis_time_s)
        try:
            body_center_lambert = solve_lambert(r_depart, r_body_periapsis, central_mu_km3_s2, transfer_tof, prograde=prograde)
            initial_vinf = np.asarray(body_center_lambert.v2_km_s) - v_body_periapsis
            hyperbola = arrival_hyperbola_from_vinf(
                initial_vinf,
                body_mu_km3_s2=arrival_body_mu_km3_s2,
                body_radius_km=arrival_body_radius_km,
                periapsis_altitude_km=periapsis_altitude_km,
                soi_radius_km=soi,
                b_plane_direction=b_plane_direction,
            )
            soi_entry_time_s = periapsis_time_s - hyperbola.soi_to_periapsis_time_s
            soi_transfer_tof = soi_entry_time_s - departure_time_s
            if soi_transfer_tof <= 0.0:
                continue
            r_body_entry = arrival_orbit.position_at(soi_entry_time_s)
            v_body_entry = arrival_orbit.velocity_at(soi_entry_time_s)
            r_rel_entry = np.asarray(hyperbola.soi_entry_position_km)
            r_soi_entry = r_body_entry + r_rel_entry
            lambert = solve_lambert(r_depart, r_soi_entry, central_mu_km3_s2, soi_transfer_tof, prograde=prograde)
        except Exception:
            continue

        v_required_entry = np.asarray(lambert.v2_km_s)
        vinf_entry = v_required_entry - v_body_entry
        dv_vec = np.asarray(lambert.v1_km_s) - v_depart_orbit
        dv_tuple, dv_mag = _norm_tuple(dv_vec)
        vinf_tuple, vinf_mag = _norm_tuple(vinf_entry)
        matched_hyperbola = arrival_hyperbola_from_vinf(
            vinf_entry,
            body_mu_km3_s2=arrival_body_mu_km3_s2,
            body_radius_km=arrival_body_radius_km,
            periapsis_altitude_km=periapsis_altitude_km,
            soi_radius_km=soi,
            b_plane_direction=hyperbola.soi_entry_position_km,
        )
        candidate = PatchedConicsSoiCandidate(
            departure_time_s=departure_time_s,
            arrival_time_s=float(soi_entry_time_s),
            tof_s=float(soi_transfer_tof),
            departure_position_km=tuple(float(x) for x in r_depart),
            arrival_position_km=tuple(float(x) for x in r_soi_entry),
            departure_velocity_required_km_s=lambert.v1_km_s,
            arrival_velocity_required_km_s=lambert.v2_km_s,
            departure_orbit_velocity_km_s=tuple(float(x) for x in v_depart_orbit),
            arrival_body_velocity_km_s=tuple(float(x) for x in v_body_entry),
            departure_delta_v_km_s=dv_tuple,
            departure_delta_v_magnitude_km_s=dv_mag,
            arrival_v_inf_km_s=vinf_tuple,
            arrival_v_inf_magnitude_km_s=vinf_mag,
            lambert=lambert,
            periapsis_time_s=float(periapsis_time_s),
            soi_entry_time_s=float(soi_entry_time_s),
            soi_entry_position_km=tuple(float(x) for x in r_soi_entry),
            soi_entry_body_position_km=tuple(float(x) for x in r_body_entry),
            soi_entry_body_velocity_km_s=tuple(float(x) for x in v_body_entry),
            soi_entry_relative_position_km=tuple(float(x) for x in r_rel_entry),
            soi_entry_relative_velocity_km_s=vinf_tuple,
            soi_entry_relative_speed_km_s=vinf_mag,
            arrival_hyperbola=matched_hyperbola,
        )
        if best is None or candidate.departure_delta_v_magnitude_km_s < best.departure_delta_v_magnitude_km_s:
            best = candidate

    if best is None:
        raise RuntimeError("No SOI patched-conics candidate could be generated in the departure search window")
    return best


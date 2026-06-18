import math

import numpy as np

from mission_targeting.constants import EARTH_MU_KM3_S2, EARTH_RADIUS_KM, LUNA_MU_KM3_S2, LUNA_RADIUS_KM
from mission_targeting.lambert import default_lambert_tof_s, hohmann_transfer_time_s, solve_lambert
from mission_targeting.patched_conics import (
    CircularOrbitState,
    arrival_hyperbola_from_vinf,
    hohmann_phase_departure_time_s,
    laplace_soi_radius_km,
    solve_circular_coplanar_patched_conics,
    solve_circular_coplanar_soi_patched_conics,
)


def test_default_lambert_time_uses_circular_coplanar_hohmann_guess():
    r1 = [7000.0, 0.0, 0.0]
    r2 = [0.0, 42164.1696, 0.0]

    tof = default_lambert_tof_s(EARTH_MU_KM3_S2, r1, r2)

    assert tof == hohmann_transfer_time_s(EARTH_MU_KM3_S2, 7000.0, 42164.1696)


def test_lambert_solver_returns_finite_velocities():
    r1 = [7000.0, 0.0, 0.0]
    r2 = [0.0, 12000.0, 0.0]
    tof = 3600.0

    solution = solve_lambert(r1, r2, EARTH_MU_KM3_S2, tof)

    assert solution.tof_s == tof
    assert solution.iterations > 0
    assert np.all(np.isfinite(solution.v1_km_s))
    assert np.all(np.isfinite(solution.v2_km_s))
    assert np.linalg.norm(solution.v1_km_s) > 0.0
    assert np.linalg.norm(solution.v2_km_s) > 0.0


def test_patched_conics_searches_departure_time_using_lambert():
    departure = CircularOrbitState(
        radius_km=EARTH_RADIUS_KM + 300.0,
        phase_rad=0.0,
        mu_central_km3_s2=EARTH_MU_KM3_S2,
    )
    arrival = CircularOrbitState(
        radius_km=384400.0,
        phase_rad=math.radians(60.0),
        mu_central_km3_s2=EARTH_MU_KM3_S2,
    )

    candidate = solve_circular_coplanar_patched_conics(
        departure,
        arrival,
        central_mu_km3_s2=EARTH_MU_KM3_S2,
        search_window_s=14.0 * 24.0 * 3600.0,
        samples=61,
    )

    assert candidate.departure_time_s >= 0.0
    assert candidate.arrival_time_s > candidate.departure_time_s
    assert candidate.tof_s == default_lambert_tof_s(
        EARTH_MU_KM3_S2,
        departure.position_at(0.0),
        arrival.position_at(0.0),
    )
    assert candidate.departure_delta_v_magnitude_km_s > 0.0
    assert candidate.arrival_v_inf_magnitude_km_s > 0.0
    assert candidate.lambert.tof_s == candidate.tof_s


def test_patched_conics_waits_for_hohmann_like_lunar_departure_window():
    departure = CircularOrbitState(
        radius_km=EARTH_RADIUS_KM + 300.0,
        phase_rad=0.0,
        mu_central_km3_s2=EARTH_MU_KM3_S2,
    )
    arrival = CircularOrbitState(
        radius_km=384400.0,
        phase_rad=math.radians(60.0),
        mu_central_km3_s2=EARTH_MU_KM3_S2,
    )
    tof_s = default_lambert_tof_s(
        EARTH_MU_KM3_S2,
        departure.position_at(0.0),
        arrival.position_at(0.0),
    )

    phase_departure_s = hohmann_phase_departure_time_s(
        departure,
        arrival,
        tof_s,
        search_window_s=14.0 * 24.0 * 3600.0,
    )
    candidate = solve_circular_coplanar_patched_conics(
        departure,
        arrival,
        central_mu_km3_s2=EARTH_MU_KM3_S2,
        search_window_s=14.0 * 24.0 * 3600.0,
        samples=61,
    )

    assert phase_departure_s > 0.0
    assert abs(candidate.departure_time_s - phase_departure_s) < 120.0
    assert 3.0 < candidate.departure_delta_v_magnitude_km_s < 3.3


def test_arrival_hyperbola_computes_soi_entry_for_requested_periapsis():
    soi_radius = laplace_soi_radius_km(384400.0, LUNA_MU_KM3_S2, EARTH_MU_KM3_S2)
    hyperbola = arrival_hyperbola_from_vinf(
        (0.8, 0.1, 0.0),
        body_mu_km3_s2=LUNA_MU_KM3_S2,
        body_radius_km=LUNA_RADIUS_KM,
        periapsis_altitude_km=200.0,
        soi_radius_km=soi_radius,
    )

    assert hyperbola.periapsis_radius_km == LUNA_RADIUS_KM + 200.0
    assert abs(np.linalg.norm(hyperbola.soi_entry_position_km) - soi_radius) < 1e-6
    assert hyperbola.impact_parameter_km > hyperbola.periapsis_radius_km
    assert 0.0 < hyperbola.turning_angle_rad < math.pi
    assert hyperbola.soi_to_periapsis_time_s > 0.0


def test_soi_patched_conics_targets_arrival_soi_entry_and_hyperbola():
    departure = CircularOrbitState(
        radius_km=EARTH_RADIUS_KM + 300.0,
        phase_rad=0.0,
        mu_central_km3_s2=EARTH_MU_KM3_S2,
    )
    arrival = CircularOrbitState(
        radius_km=384400.0,
        phase_rad=math.radians(60.0),
        mu_central_km3_s2=EARTH_MU_KM3_S2,
    )
    soi_radius = laplace_soi_radius_km(arrival.radius_km, LUNA_MU_KM3_S2, EARTH_MU_KM3_S2)

    candidate = solve_circular_coplanar_soi_patched_conics(
        departure,
        arrival,
        central_mu_km3_s2=EARTH_MU_KM3_S2,
        arrival_body_mu_km3_s2=LUNA_MU_KM3_S2,
        arrival_body_radius_km=LUNA_RADIUS_KM,
        periapsis_altitude_km=200.0,
        search_window_s=14.0 * 24.0 * 3600.0,
        samples=61,
    )

    assert candidate.soi_entry_time_s < candidate.periapsis_time_s
    assert candidate.arrival_hyperbola.periapsis_altitude_km == 200.0
    assert candidate.arrival_hyperbola.soi_radius_km == soi_radius
    assert abs(np.linalg.norm(candidate.soi_entry_relative_position_km) - soi_radius) < 1e-6
    assert 3.0 < candidate.departure_delta_v_magnitude_km_s < 3.5
    assert candidate.arrival_v_inf_magnitude_km_s > 0.0

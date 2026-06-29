from __future__ import annotations

from collections.abc import Sequence

from targeter.conic_chain import BodyEphemerisSample, ConicChainSeed, solve_single_leg_ephemeris_lambert_seed
from targeter.patched_conics import (
    CircularOrbitState,
    PatchedConicsCandidate,
    PatchedConicsSoiCandidate,
    solve_circular_coplanar_patched_conics,
    solve_circular_coplanar_soi_patched_conics,
)


BODY_TRANSFER_OPERATION_TYPES = {
    "transfer_to_planet",
    "transfer_to_moon",
    "return_from_moon",
    "porkchop_search",
    "patched_conics",
    "conic_chain",
}


def plan_conic_chain_seed(
    body_samples: Sequence[BodyEphemerisSample],
    *,
    departure_body: str = "Earth",
    target_body: str = "Luna",
    central_body: str = "Earth",
    leo_altitude_km: float = 300.0,
    central_mu_km3_s2: float,
    central_radius_km: float,
    min_tof_s: float = 2.5 * 86400.0,
    max_tof_s: float = 7.0 * 86400.0,
    departure_phase_samples: int = 96,
) -> ConicChainSeed:
    return solve_single_leg_ephemeris_lambert_seed(
        body_samples,
        departure_body=departure_body,
        target_body=target_body,
        central_body=central_body,
        leo_altitude_km=leo_altitude_km,
        central_mu_km3_s2=central_mu_km3_s2,
        central_radius_km=central_radius_km,
        min_tof_s=min_tof_s,
        max_tof_s=max_tof_s,
        departure_phase_samples=departure_phase_samples,
    )


def plan_circular_coplanar_patched_conics(
    departure_orbit: CircularOrbitState,
    arrival_orbit: CircularOrbitState,
    *,
    central_mu_km3_s2: float,
    tof_s: float | None = None,
    search_window_s: float | None = None,
    samples: int = 121,
    prograde: bool = True,
) -> PatchedConicsCandidate:
    return solve_circular_coplanar_patched_conics(
        departure_orbit,
        arrival_orbit,
        central_mu_km3_s2=central_mu_km3_s2,
        tof_s=tof_s,
        search_window_s=search_window_s,
        samples=samples,
        prograde=prograde,
    )


def plan_circular_coplanar_soi_patched_conics(
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
) -> PatchedConicsSoiCandidate:
    return solve_circular_coplanar_soi_patched_conics(
        departure_orbit,
        arrival_orbit,
        central_mu_km3_s2=central_mu_km3_s2,
        arrival_body_mu_km3_s2=arrival_body_mu_km3_s2,
        arrival_body_radius_km=arrival_body_radius_km,
        periapsis_altitude_km=periapsis_altitude_km,
        soi_radius_km=soi_radius_km,
        tof_s=tof_s,
        search_window_s=search_window_s,
        samples=samples,
        prograde=prograde,
    )

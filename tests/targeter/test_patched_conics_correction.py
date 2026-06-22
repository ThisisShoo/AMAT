import math

import numpy as np

from targeter.patched_conics_correction import (
    EncounterTarget,
    FinalOrbitTarget,
    RelativeState,
    assess_encounter,
    assess_final_orbit,
    circular_insertion_burn,
)


BODY_MU = 4902.800066
BODY_RADIUS = 1000.0
TARGET_ALTITUDE = 500.0
TARGET_RADIUS = BODY_RADIUS + TARGET_ALTITUDE


def _circular_relative_state(radius_km: float, elapsed_s: float = 0.0) -> RelativeState:
    return RelativeState(
        elapsed_s=elapsed_s,
        position_km=(radius_km, 0.0, 0.0),
        velocity_km_s=(0.0, math.sqrt(BODY_MU / radius_km), 0.0),
    )


def _keplerian_relative_state(
    *,
    sma_km: float,
    eccentricity: float,
    inclination_deg: float,
    raan_deg: float,
    aop_deg: float,
    ta_deg: float,
    elapsed_s: float = 0.0,
) -> RelativeState:
    inc = math.radians(inclination_deg)
    raan = math.radians(raan_deg)
    aop = math.radians(aop_deg)
    ta = math.radians(ta_deg)
    p = sma_km * (1.0 - eccentricity**2)
    radius = p / (1.0 + eccentricity * math.cos(ta))
    r_pf = np.array([radius * math.cos(ta), radius * math.sin(ta), 0.0])
    v_pf = math.sqrt(BODY_MU / p) * np.array([-math.sin(ta), eccentricity + math.cos(ta), 0.0])
    r3_raan = np.array(
        [
            [math.cos(raan), -math.sin(raan), 0.0],
            [math.sin(raan), math.cos(raan), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    r1_inc = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, math.cos(inc), -math.sin(inc)],
            [0.0, math.sin(inc), math.cos(inc)],
        ]
    )
    r3_aop = np.array(
        [
            [math.cos(aop), -math.sin(aop), 0.0],
            [math.sin(aop), math.cos(aop), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    transform = r3_raan @ r1_inc @ r3_aop
    r = transform @ r_pf
    v = transform @ v_pf
    return RelativeState(
        elapsed_s=elapsed_s,
        position_km=tuple(float(x) for x in r),
        velocity_km_s=tuple(float(x) for x in v),
    )


def test_encounter_assessment_targets_arrival_body_periapsis_radius():
    target = EncounterTarget(
        body_name="ArrivalBody",
        body_mu_km3_s2=BODY_MU,
        body_radius_km=BODY_RADIUS,
        periapsis_altitude_km=TARGET_ALTITUDE,
        periapsis_tolerance_km=0.01,
    )
    final_assessment = assess_encounter(_circular_relative_state(TARGET_RADIUS), target)

    assert final_assessment.converged
    assert abs(final_assessment.residual_km) < 0.01


def test_circular_insertion_burn_targets_local_circular_speed():
    pre_burn = RelativeState(
        elapsed_s=100.0,
        position_km=(TARGET_RADIUS, 0.0, 0.0),
        velocity_km_s=(0.02, 2.1, 0.0),
    )

    burn = circular_insertion_burn(
        pre_burn,
        body_mu_km3_s2=BODY_MU,
        body_radius_km=BODY_RADIUS,
        frame="ArrivalBodyMJ2000Eq",
    )

    post_velocity = np.asarray(pre_burn.velocity_km_s) + np.asarray(burn.delta_v_km_s)
    post_burn = RelativeState(
        elapsed_s=pre_burn.elapsed_s,
        position_km=pre_burn.position_km,
        velocity_km_s=tuple(float(x) for x in post_velocity),
    )
    orbit = assess_final_orbit(
        post_burn,
        FinalOrbitTarget(
            body_name="ArrivalBody",
            body_mu_km3_s2=BODY_MU,
            body_radius_km=BODY_RADIUS,
            periapsis_altitude_km=TARGET_ALTITUDE,
        ),
    )

    assert burn.frame == "ArrivalBodyMJ2000Eq"
    assert burn.delta_v_magnitude_km_s > 0.0
    assert orbit.achieved.eccentricity < 1e-12
    assert abs(orbit.achieved.speed_km_s - orbit.achieved.circular_speed_km_s) < 1e-12


def test_final_orbit_assessment_targets_orbital_state_vector_not_altitude():
    state = _keplerian_relative_state(
        sma_km=2400.0,
        eccentricity=0.2,
        inclination_deg=35.0,
        raan_deg=40.0,
        aop_deg=25.0,
        ta_deg=80.0,
    )
    target = FinalOrbitTarget(
        body_name="ArrivalBody",
        body_mu_km3_s2=BODY_MU,
        body_radius_km=BODY_RADIUS,
        sma_km=2400.0,
        eccentricity=0.2,
        inclination_deg=35.0,
        raan_deg=40.0,
        aop_deg=25.0,
        ta_deg=80.0,
        sma_tolerance_km=1e-6,
        eccentricity_tolerance=1e-10,
        angle_tolerance_deg=1e-8,
    )

    assessment = assess_final_orbit(state, target)
    missed = assess_final_orbit(
        state,
        FinalOrbitTarget(
            body_name="ArrivalBody",
            body_mu_km3_s2=BODY_MU,
            body_radius_km=BODY_RADIUS,
            sma_km=2400.0,
            eccentricity=0.2,
            inclination_deg=35.0,
            raan_deg=41.0,
            aop_deg=25.0,
            ta_deg=80.0,
            angle_tolerance_deg=0.05,
        ),
    )

    assert assessment.converged
    assert "altitude_km" not in assessment.residuals
    assert abs(target.target_altitude_km - (2400.0 * (1.0 - 0.2) - BODY_RADIUS)) < 1e-12
    assert not missed.converged
    assert missed.residuals["raan_deg"] == -1.0


def test_final_orbit_assessment_flags_off_nominal_insertion_burn():
    pre_burn = RelativeState(
        elapsed_s=100.0,
        position_km=(TARGET_RADIUS, 0.0, 0.0),
        velocity_km_s=(0.0, 2.2, 0.0),
    )
    nominal_burn = circular_insertion_burn(
        pre_burn,
        body_mu_km3_s2=BODY_MU,
        body_radius_km=BODY_RADIUS,
        frame="ArrivalBodyMJ2000Eq",
    )
    target = FinalOrbitTarget(
        body_name="ArrivalBody",
        body_mu_km3_s2=BODY_MU,
        body_radius_km=BODY_RADIUS,
        periapsis_altitude_km=TARGET_ALTITUDE,
        eccentricity_tolerance=1e-8,
        altitude_tolerance_km=1e-6,
    )

    burn_vec = 0.75 * np.asarray(nominal_burn.delta_v_km_s)
    post_velocity = np.asarray(pre_burn.velocity_km_s) + burn_vec
    off_nominal = RelativeState(
        elapsed_s=pre_burn.elapsed_s,
        position_km=pre_burn.position_km,
        velocity_km_s=tuple(float(x) for x in post_velocity),
    )
    final_assessment = assess_final_orbit(off_nominal, target)

    assert not final_assessment.converged
    assert final_assessment.scaled_residual_vector


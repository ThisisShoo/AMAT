import csv
import math
from pathlib import Path

import numpy as np
import pytest

from targeter.conic_chain import (
    BodyEphemerisSample,
    ConicChainLeg,
    ConicChainNode,
    ConicChainSeed,
    load_body_ephemeris_csv,
    solve_conic_chain_seed,
    solve_ephemeris_lambert_seed,
)
from targeter.constants import EARTH_MU_KM3_S2


def _sample_lunar_ephemeris() -> list[BodyEphemerisSample]:
    radius = 384400.0
    n = math.sqrt(EARTH_MU_KM3_S2 / radius**3)
    samples = []
    for elapsed in range(3 * 86400, 8 * 86400, 12 * 3600):
        theta = math.radians(35.0) + n * elapsed
        position = (radius * math.cos(theta), radius * math.sin(theta), 25000.0 * math.sin(theta * 0.7))
        velocity = (-radius * n * math.sin(theta), radius * n * math.cos(theta), 25000.0 * 0.7 * n * math.cos(theta * 0.7))
        samples.append(BodyEphemerisSample(float(elapsed), position, velocity))
    return samples


def _leg(index: int) -> ConicChainLeg:
    origin = ConicChainNode(
        body=f"Origin{index}",
        elapsed_s=float(index),
        position_km=(float(index), 0.0, 0.0),
        velocity_km_s=(0.0, 1.0, 0.0),
    )
    target = ConicChainNode(
        body=f"Target{index}",
        elapsed_s=float(index + 1),
        position_km=(float(index + 1), 0.0, 0.0),
        velocity_km_s=(0.0, 1.0, 0.0),
    )
    return ConicChainLeg(
        origin=origin,
        target=target,
        central_body="Sun",
        central_mu_km3_s2=132712440041.93938,
        transfer_velocity_km_s=(0.0, 1.0, 0.0),
        arrival_velocity_km_s=(0.0, 1.0, 0.0),
        departure_delta_v_km_s=(0.1, 0.0, 0.0),
        arrival_v_inf_km_s=(0.0, 0.1, 0.0),
        transfer_angle_deg=10.0,
    )


def test_conic_chain_combines_up_to_three_seeded_legs() -> None:
    legs = [ConicChainSeed((_leg(i),)) for i in range(3)]

    chain = solve_conic_chain_seed(legs)

    assert len(chain.legs) == 3
    assert chain.first_leg.origin.body == "Origin0"
    assert chain.total_departure_delta_v_km_s == pytest.approx(0.3)


def test_conic_chain_rejects_more_than_three_connecting_conics() -> None:
    legs = [ConicChainSeed((_leg(i),)) for i in range(4)]

    with pytest.raises(ValueError, match="at most 3"):
        solve_conic_chain_seed(legs)


def test_ephemeris_lambert_seed_targets_supplied_body_ephemeris_phase() -> None:
    samples = _sample_lunar_ephemeris()

    seed = solve_ephemeris_lambert_seed(samples, departure_phase_samples=32)

    target = np.asarray(seed.target_body_position_km)
    assert seed.target_elapsed_s in {s.elapsed_s for s in samples}
    assert 2.6 < seed.tli_delta_v_magnitude_km_s < 3.8
    assert seed.arrival_v_inf_magnitude_km_s > 0.0
    assert np.dot(np.asarray(seed.target_body_position_km), target) > 0.0
    assert np.linalg.norm(np.asarray(seed.departure_position_km)) == np.linalg.norm(seed.departure_position_km)


def test_load_body_ephemeris_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "moon.csv"
    samples = _sample_lunar_ephemeris()
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "TransferSat.ElapsedSecs",
                "Luna.EarthMJ2000Eq.X",
                "Luna.EarthMJ2000Eq.Y",
                "Luna.EarthMJ2000Eq.Z",
                "Luna.EarthMJ2000Eq.VX",
                "Luna.EarthMJ2000Eq.VY",
                "Luna.EarthMJ2000Eq.VZ",
            ]
        )
        for sample in samples:
            writer.writerow([sample.elapsed_s, *sample.position_km, *sample.velocity_km_s])

    loaded = load_body_ephemeris_csv(csv_path)
    seed = solve_ephemeris_lambert_seed(loaded, departure_phase_samples=32)

    assert loaded == samples
    assert seed.target_elapsed_s in {s.elapsed_s for s in samples}


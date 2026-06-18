from __future__ import annotations

import csv
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .constants import EARTH_MU_KM3_S2, EARTH_RADIUS_KM
from .lambert import solve_lambert


@dataclass(frozen=True)
class BodyEphemerisSample:
    elapsed_s: float
    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]


@dataclass(frozen=True)
class ConicChainNode:
    body: str
    elapsed_s: float
    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConicChainLeg:
    origin: ConicChainNode
    target: ConicChainNode
    central_body: str
    central_mu_km3_s2: float
    transfer_velocity_km_s: tuple[float, float, float]
    arrival_velocity_km_s: tuple[float, float, float]
    departure_delta_v_km_s: tuple[float, float, float]
    arrival_v_inf_km_s: tuple[float, float, float]
    transfer_angle_deg: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ConicChainSeed:
    legs: tuple[ConicChainLeg, ...]

    @property
    def first_leg(self) -> ConicChainLeg:
        return self.legs[0]

    @property
    def total_departure_delta_v_km_s(self) -> float:
        return float(sum(_norm(leg.departure_delta_v_km_s) for leg in self.legs))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EphemerisLambertSeed:
    departure_position_km: tuple[float, float, float]
    departure_velocity_km_s: tuple[float, float, float]
    target_elapsed_s: float
    target_body_position_km: tuple[float, float, float]
    target_body_velocity_km_s: tuple[float, float, float]
    transfer_velocity_km_s: tuple[float, float, float]
    tli_delta_v_vnb_km_s: tuple[float, float, float]
    tli_delta_v_magnitude_km_s: float
    arrival_v_inf_km_s: tuple[float, float, float]
    arrival_v_inf_magnitude_km_s: float
    transfer_angle_deg: float

    def to_dict(self) -> dict:
        return asdict(self)


CislunarLambertSeed = EphemerisLambertSeed


def _norm(vector: Sequence[float]) -> float:
    return float(np.linalg.norm(np.asarray(vector, dtype=float)))


def _unit(vector: Sequence[float], name: str) -> np.ndarray:
    arr = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(arr))
    if arr.shape != (3,) or not np.all(np.isfinite(arr)) or norm <= 0.0:
        raise ValueError(f"{name} must be a finite nonzero 3-vector")
    return arr / norm


def _body_column_prefix(fieldnames: Sequence[str], body: str, frame: str) -> str:
    prefix = f"{body}.{frame}."
    if all(f"{prefix}{axis}" in fieldnames for axis in ("X", "Y", "Z", "VX", "VY", "VZ")):
        return prefix
    matches = sorted({name.rsplit(".", 1)[0] + "." for name in fieldnames if name.startswith(f"{body}.")})
    raise ValueError(f"Could not find {body} {frame} Cartesian columns. Available body prefixes: {matches}")


def load_gmat_body_ephemeris_csv(path: str | Path, *, body: str = "Luna", frame: str = "EarthMJ2000Eq") -> list[BodyEphemerisSample]:
    p = Path(path)
    samples: list[BodyEphemerisSample] = []
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError(f"{p} has no CSV header")
        prefix = _body_column_prefix(reader.fieldnames, body, frame)
        time_col = next((c for c in reader.fieldnames if c.endswith(".ElapsedSecs")), None)
        if time_col is None:
            raise ValueError(f"{p} has no ElapsedSecs column")
        for row in reader:
            try:
                sample = BodyEphemerisSample(
                    elapsed_s=float(row[time_col]),
                    position_km=tuple(float(row[f"{prefix}{axis}"]) for axis in ("X", "Y", "Z")),
                    velocity_km_s=tuple(float(row[f"{prefix}{axis}"]) for axis in ("VX", "VY", "VZ")),
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numeric body ephemeris row in {p}") from exc
            samples.append(sample)
    if not samples:
        raise ValueError(f"{p} contained no body ephemeris samples")
    return samples


def _plane_basis(r_body: Sequence[float], v_body: Sequence[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    h_hat = _unit(np.cross(np.asarray(r_body, dtype=float), np.asarray(v_body, dtype=float)), "body orbital angular momentum")
    p_hat = _unit(r_body, "body position")
    q_hat = _unit(np.cross(h_hat, p_hat), "body transverse direction")
    return p_hat, q_hat, h_hat


def _vnb_components(velocity: np.ndarray, orbit_normal: np.ndarray, delta_v: np.ndarray) -> tuple[float, float, float]:
    v_axis = _unit(velocity, "departure velocity")
    n_axis = _unit(orbit_normal, "departure orbit normal")
    b_axis = _unit(np.cross(v_axis, n_axis), "departure binormal")
    return (
        float(np.dot(delta_v, v_axis)),
        float(np.dot(delta_v, n_axis)),
        float(np.dot(delta_v, b_axis)),
    )


def _circular_departure_node(
    sample: BodyEphemerisSample,
    *,
    body: str,
    leo_altitude_km: float,
    central_mu_km3_s2: float,
    elapsed_s: float = 0.0,
) -> tuple[ConicChainNode, np.ndarray]:
    radius = EARTH_RADIUS_KM + float(leo_altitude_km)
    circular_speed = math.sqrt(central_mu_km3_s2 / radius)
    r2 = np.asarray(sample.position_km, dtype=float)
    v_body = np.asarray(sample.velocity_km_s, dtype=float)
    p_hat, q_hat, h_hat = _plane_basis(r2, v_body)
    r1 = radius * p_hat
    v1 = circular_speed * q_hat
    return (
        ConicChainNode(
            body=body,
            elapsed_s=float(elapsed_s),
            position_km=tuple(float(x) for x in r1),
            velocity_km_s=tuple(float(x) for x in v1),
        ),
        h_hat,
    )


def solve_single_leg_ephemeris_lambert_seed(
    body_samples: Sequence[BodyEphemerisSample],
    *,
    departure_body: str = "Earth",
    target_body: str = "Luna",
    central_body: str = "Earth",
    leo_altitude_km: float = 300.0,
    central_mu_km3_s2: float = EARTH_MU_KM3_S2,
    min_tof_s: float = 2.5 * 86400.0,
    max_tof_s: float = 7.0 * 86400.0,
    departure_phase_samples: int = 96,
    prograde: bool = True,
) -> ConicChainSeed:
    """Generate one cross-SOI Lambert leg from a sampled target-body ephemeris."""

    seed = solve_ephemeris_lambert_seed(
        body_samples,
        leo_altitude_km=leo_altitude_km,
        central_mu_km3_s2=central_mu_km3_s2,
        min_tof_s=min_tof_s,
        max_tof_s=max_tof_s,
        departure_phase_samples=departure_phase_samples,
        prograde=prograde,
    )
    target = ConicChainNode(
        body=target_body,
        elapsed_s=seed.target_elapsed_s,
        position_km=seed.target_body_position_km,
        velocity_km_s=seed.target_body_velocity_km_s,
    )
    origin = ConicChainNode(
        body=departure_body,
        elapsed_s=0.0,
        position_km=seed.departure_position_km,
        velocity_km_s=seed.departure_velocity_km_s,
    )
    leg = ConicChainLeg(
        origin=origin,
        target=target,
        central_body=central_body,
        central_mu_km3_s2=float(central_mu_km3_s2),
        transfer_velocity_km_s=seed.transfer_velocity_km_s,
        arrival_velocity_km_s=tuple(float(a + b) for a, b in zip(seed.arrival_v_inf_km_s, seed.target_body_velocity_km_s)),
        departure_delta_v_km_s=tuple(float(x) for x in np.asarray(seed.transfer_velocity_km_s) - np.asarray(seed.departure_velocity_km_s)),
        arrival_v_inf_km_s=seed.arrival_v_inf_km_s,
        transfer_angle_deg=seed.transfer_angle_deg,
    )
    return ConicChainSeed((leg,))


def solve_conic_chain_seed(legs: Sequence[ConicChainSeed]) -> ConicChainSeed:
    """Combine up to three independently seeded connecting conics.

    The nested-conic solve remains deliberately separate from the later STM
    loop.  Each leg supplies a patched-conic seed; the returned chain is the
    ordered handoff for high-fidelity correction.
    """

    if not legs:
        raise ValueError("at least one conic leg seed is required")
    flattened: list[ConicChainLeg] = []
    for seed in legs:
        flattened.extend(seed.legs)
    if len(flattened) > 3:
        raise ValueError("conic chains currently support at most 3 connecting conics")
    return ConicChainSeed(tuple(flattened))


def solve_ephemeris_lambert_seed(
    body_samples: Sequence[BodyEphemerisSample],
    *,
    leo_altitude_km: float = 300.0,
    central_mu_km3_s2: float = EARTH_MU_KM3_S2,
    min_tof_s: float = 2.5 * 86400.0,
    max_tof_s: float = 7.0 * 86400.0,
    departure_phase_samples: int = 96,
    prograde: bool = True,
) -> EphemerisLambertSeed:
    """Target a fixed-epoch circular departure to a sampled body ephemeris."""

    if departure_phase_samples < 8:
        raise ValueError("departure_phase_samples must be at least 8")
    radius = EARTH_RADIUS_KM + float(leo_altitude_km)
    circular_speed = math.sqrt(central_mu_km3_s2 / radius)

    best: EphemerisLambertSeed | None = None
    best_score = float("inf")
    phases = np.linspace(0.0, 2.0 * math.pi, departure_phase_samples, endpoint=False)
    for sample in body_samples:
        tof = float(sample.elapsed_s)
        if tof < min_tof_s or tof > max_tof_s:
            continue
        r2 = np.asarray(sample.position_km, dtype=float)
        v_body = np.asarray(sample.velocity_km_s, dtype=float)
        try:
            p_hat, q_hat, h_hat = _plane_basis(r2, v_body)
        except ValueError:
            continue
        for theta in phases:
            r_hat = math.cos(theta) * p_hat + math.sin(theta) * q_hat
            v_hat = -math.sin(theta) * p_hat + math.cos(theta) * q_hat
            r1 = radius * r_hat
            v_circ = circular_speed * v_hat
            try:
                lambert = solve_lambert(r1, r2, central_mu_km3_s2, tof, prograde=prograde)
            except Exception:
                continue
            v_transfer = np.asarray(lambert.v1_km_s, dtype=float)
            dv = v_transfer - v_circ
            vinf = np.asarray(lambert.v2_km_s, dtype=float) - v_body
            dv_mag = _norm(dv)
            vinf_mag = _norm(vinf)
            score = abs(dv_mag - 3.15) + 0.08 * vinf_mag
            if score < best_score:
                best_score = score
                best = EphemerisLambertSeed(
                    departure_position_km=tuple(float(x) for x in r1),
                    departure_velocity_km_s=tuple(float(x) for x in v_circ),
                    target_elapsed_s=tof,
                    target_body_position_km=sample.position_km,
                    target_body_velocity_km_s=sample.velocity_km_s,
                    transfer_velocity_km_s=tuple(float(x) for x in v_transfer),
                    tli_delta_v_vnb_km_s=_vnb_components(v_circ, h_hat, dv),
                    tli_delta_v_magnitude_km_s=dv_mag,
                    arrival_v_inf_km_s=tuple(float(x) for x in vinf),
                    arrival_v_inf_magnitude_km_s=vinf_mag,
                    transfer_angle_deg=math.degrees(lambert.transfer_angle_rad),
                )
    if best is None:
        raise RuntimeError("No ephemeris Lambert seed could be generated from the supplied body ephemeris")
    return best

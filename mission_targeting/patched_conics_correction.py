from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


Vector = Sequence[float]


def _vec(value: Vector, name: str) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.shape != (3,):
        raise ValueError(f"{name} must be a 3-vector")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} must contain finite values")
    return arr


def _unit(value: Vector, name: str) -> np.ndarray:
    arr = _vec(value, name)
    norm = float(np.linalg.norm(arr))
    if norm <= 0.0:
        raise ValueError(f"{name} must be nonzero")
    return arr / norm


@dataclass(frozen=True)
class BodyState:
    """Cartesian state of a target body in a common inertial frame."""

    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]


@dataclass(frozen=True)
class SpacecraftState:
    """Cartesian spacecraft state in the same inertial frame as its target body."""

    elapsed_s: float
    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]


@dataclass(frozen=True)
class RelativeState:
    """Spacecraft state relative to an encounter or insertion body."""

    elapsed_s: float
    position_km: tuple[float, float, float]
    velocity_km_s: tuple[float, float, float]

    @classmethod
    def from_inertial(cls, spacecraft: SpacecraftState, body: BodyState) -> "RelativeState":
        r = _vec(spacecraft.position_km, "spacecraft.position_km") - _vec(body.position_km, "body.position_km")
        v = _vec(spacecraft.velocity_km_s, "spacecraft.velocity_km_s") - _vec(body.velocity_km_s, "body.velocity_km_s")
        return cls(
            elapsed_s=float(spacecraft.elapsed_s),
            position_km=tuple(float(x) for x in r),
            velocity_km_s=tuple(float(x) for x in v),
        )


@dataclass(frozen=True)
class OrbitElements:
    """Two-body osculating elements around the encounter body."""

    radius_km: float
    altitude_km: float
    speed_km_s: float
    radial_speed_km_s: float
    circular_speed_km_s: float
    sma_km: float
    eccentricity: float
    inclination_deg: float
    raan_deg: float
    aop_deg: float
    ta_deg: float
    periapsis_radius_km: float
    apoapsis_radius_km: float
    periapsis_altitude_km: float
    apoapsis_altitude_km: float


def _angle_deg(value_rad: float) -> float:
    return math.degrees(value_rad) % 360.0


def _safe_acos(value: float) -> float:
    return math.acos(float(np.clip(value, -1.0, 1.0)))


def _angle_residual_deg(achieved: float, target: float) -> float:
    return (achieved - target + 180.0) % 360.0 - 180.0


def osculating_orbit(relative_state: RelativeState, body_mu_km3_s2: float, body_radius_km: float) -> OrbitElements:
    """Return two-body osculating elements for a relative state."""

    if body_mu_km3_s2 <= 0.0:
        raise ValueError("body_mu_km3_s2 must be positive")
    if body_radius_km < 0.0:
        raise ValueError("body_radius_km must be non-negative")
    r = _vec(relative_state.position_km, "relative_state.position_km")
    v = _vec(relative_state.velocity_km_s, "relative_state.velocity_km_s")
    radius = float(np.linalg.norm(r))
    speed = float(np.linalg.norm(v))
    if radius <= 0.0:
        raise ValueError("relative position must be nonzero")
    h = np.cross(r, v)
    h_norm = float(np.linalg.norm(h))
    if h_norm <= 0.0:
        raise ValueError("relative state must have nonzero angular momentum")
    k_hat = np.array([0.0, 0.0, 1.0])
    n = np.cross(k_hat, h)
    n_norm = float(np.linalg.norm(n))
    energy = 0.5 * speed**2 - body_mu_km3_s2 / radius
    sma = -body_mu_km3_s2 / (2.0 * energy) if abs(energy) > 1e-15 else float("inf")
    e_vec = np.cross(v, h) / body_mu_km3_s2 - r / radius
    ecc = float(np.linalg.norm(e_vec))
    inc = _angle_deg(_safe_acos(h[2] / h_norm))
    raan = _angle_deg(math.atan2(n[1], n[0])) if n_norm > 1e-12 else 0.0
    if ecc > 1e-12 and n_norm > 1e-12:
        aop_rad = _safe_acos(float(np.dot(n, e_vec) / (n_norm * ecc)))
        if e_vec[2] < 0.0:
            aop_rad = 2.0 * math.pi - aop_rad
        aop = _angle_deg(aop_rad)
    else:
        aop = 0.0
    if ecc > 1e-12:
        ta_rad = _safe_acos(float(np.dot(e_vec, r) / (ecc * radius)))
        if np.dot(r, v) < 0.0:
            ta_rad = 2.0 * math.pi - ta_rad
        ta = _angle_deg(ta_rad)
    elif n_norm > 1e-12:
        ta_rad = _safe_acos(float(np.dot(n, r) / (n_norm * radius)))
        if r[2] < 0.0:
            ta_rad = 2.0 * math.pi - ta_rad
        ta = _angle_deg(ta_rad)
    else:
        ta = _angle_deg(math.atan2(r[1], r[0]))
    if math.isfinite(sma) and sma > 0.0:
        rp = sma * (1.0 - ecc)
        ra = sma * (1.0 + ecc)
    else:
        rp = radius
        ra = float("inf")
    return OrbitElements(
        radius_km=radius,
        altitude_km=radius - body_radius_km,
        speed_km_s=speed,
        radial_speed_km_s=float(np.dot(r, v) / radius),
        circular_speed_km_s=math.sqrt(body_mu_km3_s2 / radius),
        sma_km=float(sma),
        eccentricity=ecc,
        inclination_deg=inc,
        raan_deg=raan,
        aop_deg=aop,
        ta_deg=ta,
        periapsis_radius_km=float(rp),
        apoapsis_radius_km=float(ra),
        periapsis_altitude_km=float(rp - body_radius_km),
        apoapsis_altitude_km=float(ra - body_radius_km) if math.isfinite(ra) else float("inf"),
    )


@dataclass(frozen=True)
class EncounterTarget:
    """Desired arrival-body encounter geometry."""

    body_name: str
    body_mu_km3_s2: float
    body_radius_km: float
    periapsis_altitude_km: float
    periapsis_tolerance_km: float = 10.0

    @property
    def periapsis_radius_km(self) -> float:
        return self.body_radius_km + self.periapsis_altitude_km


@dataclass(frozen=True)
class FinalOrbitTarget:
    """Desired post-insertion orbit around a body."""

    body_name: str
    body_mu_km3_s2: float
    body_radius_km: float
    periapsis_altitude_km: float | None = None
    apoapsis_altitude_km: float | None = None
    sma_km: float | None = None
    eccentricity: float | None = None
    inclination_deg: float | None = None
    raan_deg: float | None = None
    aop_deg: float | None = None
    ta_deg: float | None = None
    eccentricity_tolerance: float = 1e-3
    altitude_tolerance_km: float = 10.0
    sma_tolerance_km: float = 10.0
    angle_tolerance_deg: float = 0.05

    @property
    def is_circular(self) -> bool:
        return self.apoapsis_altitude_km is None

    @property
    def target_radius_km(self) -> float:
        if self.sma_km is not None:
            eccentricity = float(self.eccentricity or 0.0)
            return float(self.sma_km) * (1.0 - eccentricity)
        if self.periapsis_altitude_km is None:
            raise ValueError("FinalOrbitTarget needs sma_km or periapsis_altitude_km")
        return self.body_radius_km + self.periapsis_altitude_km

    @property
    def target_altitude_km(self) -> float:
        return self.target_radius_km - self.body_radius_km


@dataclass(frozen=True)
class EncounterAssessment:
    target: EncounterTarget
    achieved: OrbitElements
    elapsed_s: float
    residual_km: float

    @property
    def converged(self) -> bool:
        return abs(self.residual_km) <= self.target.periapsis_tolerance_km


def assess_encounter(relative_state: RelativeState, target: EncounterTarget) -> EncounterAssessment:
    orbit = osculating_orbit(relative_state, target.body_mu_km3_s2, target.body_radius_km)
    return EncounterAssessment(
        target=target,
        achieved=orbit,
        elapsed_s=relative_state.elapsed_s,
        residual_km=orbit.periapsis_radius_km - target.periapsis_radius_km,
    )


@dataclass(frozen=True)
class FinalOrbitAssessment:
    target: FinalOrbitTarget
    achieved: OrbitElements
    elapsed_s: float
    altitude_residual_km: float
    eccentricity_residual: float
    residuals: dict[str, float]
    tolerances: dict[str, float]
    scaled_residual_vector: tuple[float, ...]

    @property
    def converged(self) -> bool:
        return all(abs(self.residuals[name]) <= self.tolerances[name] for name in self.residuals)


def assess_final_orbit(relative_state: RelativeState, target: FinalOrbitTarget) -> FinalOrbitAssessment:
    orbit = osculating_orbit(relative_state, target.body_mu_km3_s2, target.body_radius_km)
    residuals: dict[str, float] = {}
    tolerances: dict[str, float] = {}
    has_vector_target = any(
        value is not None
        for value in (
            target.sma_km,
            target.eccentricity,
            target.inclination_deg,
            target.raan_deg,
            target.aop_deg,
            target.ta_deg,
        )
    )

    def add(name: str, residual: float, tolerance: float) -> None:
        residuals[name] = float(residual)
        tolerances[name] = float(tolerance)

    if target.is_circular:
        altitude_residual = orbit.radius_km - target.target_radius_km
        ecc_residual = orbit.eccentricity
    else:
        target_apo = target.body_radius_km + float(target.apoapsis_altitude_km)
        altitude_residual = 0.5 * (
            (orbit.periapsis_radius_km - target.target_radius_km)
            + (orbit.apoapsis_radius_km - target_apo)
        )
        target_ecc = (target_apo - target.target_radius_km) / (target_apo + target.target_radius_km)
        ecc_residual = orbit.eccentricity - target_ecc
    if not has_vector_target:
        add("altitude_km", altitude_residual, target.altitude_tolerance_km)
        add("eccentricity", ecc_residual, target.eccentricity_tolerance)
    if target.sma_km is not None:
        add("sma_km", orbit.sma_km - target.sma_km, target.sma_tolerance_km)
    if target.eccentricity is not None:
        add("eccentricity", orbit.eccentricity - target.eccentricity, target.eccentricity_tolerance)
    if target.inclination_deg is not None:
        add("inclination_deg", _angle_residual_deg(orbit.inclination_deg, target.inclination_deg), target.angle_tolerance_deg)
    if target.raan_deg is not None:
        add("raan_deg", _angle_residual_deg(orbit.raan_deg, target.raan_deg), target.angle_tolerance_deg)
    if target.aop_deg is not None:
        add("aop_deg", _angle_residual_deg(orbit.aop_deg, target.aop_deg), target.angle_tolerance_deg)
    if target.ta_deg is not None:
        add("ta_deg", _angle_residual_deg(orbit.ta_deg, target.ta_deg), target.angle_tolerance_deg)

    scaled: list[float] = []
    for name, residual in residuals.items():
        if name == "eccentricity":
            scale = max(target.target_radius_km, 1.0)
        elif name.endswith("_deg"):
            scale = max(target.target_radius_km * math.pi / 180.0, 1.0)
        else:
            scale = 1.0
        scaled.append(float(residual) * scale)
    return FinalOrbitAssessment(
        target=target,
        achieved=orbit,
        elapsed_s=relative_state.elapsed_s,
        altitude_residual_km=float(altitude_residual),
        eccentricity_residual=float(ecc_residual),
        residuals=residuals,
        tolerances=tolerances,
        scaled_residual_vector=tuple(scaled),
    )


@dataclass(frozen=True)
class CircularInsertionBurn:
    """Impulsive burn that circularizes at the current relative-state radius."""

    frame: str
    delta_v_km_s: tuple[float, float, float]
    delta_v_magnitude_km_s: float
    pre_burn_speed_km_s: float
    target_circular_speed_km_s: float
    radius_km: float
    altitude_km: float


def circular_insertion_burn(
    relative_state: RelativeState,
    *,
    body_mu_km3_s2: float,
    body_radius_km: float,
    frame: str,
) -> CircularInsertionBurn:
    """Return a tangential impulse that circularizes around the encounter body.

    The burn removes radial velocity and adjusts tangential speed to the local
    circular speed. Hyperbolic arrivals naturally produce a mostly retrograde
    burn, but the function also works for slower or off-nominal cases.
    """

    r = _vec(relative_state.position_km, "relative_state.position_km")
    v = _vec(relative_state.velocity_km_s, "relative_state.velocity_km_s")
    radius = float(np.linalg.norm(r))
    if radius <= 0.0:
        raise ValueError("relative position must be nonzero")
    r_hat = r / radius
    radial_v = float(np.dot(v, r_hat))
    tangential = v - radial_v * r_hat
    tangential_norm = float(np.linalg.norm(tangential))
    if tangential_norm <= 0.0:
        raise ValueError("relative velocity has no tangential component to circularize")
    tangential_hat = tangential / tangential_norm
    circular_speed = math.sqrt(body_mu_km3_s2 / radius)
    desired_v = circular_speed * tangential_hat
    delta_v = desired_v - v
    return CircularInsertionBurn(
        frame=frame,
        delta_v_km_s=tuple(float(x) for x in delta_v),
        delta_v_magnitude_km_s=float(np.linalg.norm(delta_v)),
        pre_burn_speed_km_s=float(np.linalg.norm(v)),
        target_circular_speed_km_s=float(circular_speed),
        radius_km=radius,
        altitude_km=radius - body_radius_km,
    )


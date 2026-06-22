from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BodyConstants:
    name: str
    radius_km: float
    mu_km3_s2: float
    stationary_orbit_radius_km: float | None = None


SUN_RADIUS_KM = 695700.0
SUN_MU_KM3_S2 = 132712440041.27942
MERCURY_RADIUS_KM = 2440.53
MERCURY_MU_KM3_S2 = 22031.868551
VENUS_RADIUS_KM = 6051.8
VENUS_MU_KM3_S2 = 324858.592
EARTH_RADIUS_KM = 6378.1363
EARTH_MU_KM3_S2 = 398600.435507
EARTH_GEO_RADIUS_KM = 42164.1696
MOON_RADIUS_KM = 1737.4
MOON_MU_KM3_S2 = 4902.800118
LUNA_RADIUS_KM = 1737.4
LUNA_MU_KM3_S2 = MOON_MU_KM3_S2
MARS_RADIUS_KM = 3396.19
MARS_SYSTEM_MU_KM3_S2 = 42828.375816
JUPITER_RADIUS_KM = 71492.0
JUPITER_SYSTEM_MU_KM3_S2 = 126712764.1
SATURN_RADIUS_KM = 60268.0
SATURN_SYSTEM_MU_KM3_S2 = 37940584.8418
URANUS_RADIUS_KM = 25559.0
URANUS_SYSTEM_MU_KM3_S2 = 5794556.4
NEPTUNE_RADIUS_KM = 24764.0
NEPTUNE_SYSTEM_MU_KM3_S2 = 6836527.10058
PLUTO_RADIUS_KM = 1188.3
PLUTO_SYSTEM_MU_KM3_S2 = 975.5

BODY_CONSTANTS = {
    "Sun": BodyConstants("Sun", SUN_RADIUS_KM, SUN_MU_KM3_S2),
    "Mercury": BodyConstants("Mercury", MERCURY_RADIUS_KM, MERCURY_MU_KM3_S2),
    "Venus": BodyConstants("Venus", VENUS_RADIUS_KM, VENUS_MU_KM3_S2),
    "Earth": BodyConstants("Earth", EARTH_RADIUS_KM, EARTH_MU_KM3_S2, EARTH_GEO_RADIUS_KM),
    "Luna": BodyConstants("Luna", LUNA_RADIUS_KM, LUNA_MU_KM3_S2),
    "Moon": BodyConstants("Moon", MOON_RADIUS_KM, MOON_MU_KM3_S2),
    "Mars": BodyConstants("Mars", MARS_RADIUS_KM, MARS_SYSTEM_MU_KM3_S2),
    "Jupiter": BodyConstants("Jupiter", JUPITER_RADIUS_KM, JUPITER_SYSTEM_MU_KM3_S2),
    "Saturn": BodyConstants("Saturn", SATURN_RADIUS_KM, SATURN_SYSTEM_MU_KM3_S2),
    "Uranus": BodyConstants("Uranus", URANUS_RADIUS_KM, URANUS_SYSTEM_MU_KM3_S2),
    "Neptune": BodyConstants("Neptune", NEPTUNE_RADIUS_KM, NEPTUNE_SYSTEM_MU_KM3_S2),
    "Pluto": BodyConstants("Pluto", PLUTO_RADIUS_KM, PLUTO_SYSTEM_MU_KM3_S2),
}


def get_body_constants(name: str) -> BodyConstants | None:
    return BODY_CONSTANTS.get(str(name))

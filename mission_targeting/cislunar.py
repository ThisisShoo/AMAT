from __future__ import annotations

import copy

from .conic_chain import (
    BodyEphemerisSample,
    CislunarLambertSeed,
    ConicChainLeg,
    ConicChainNode,
    ConicChainSeed,
    EphemerisLambertSeed,
    load_gmat_body_ephemeris_csv,
    solve_conic_chain_seed,
    solve_ephemeris_lambert_seed,
    solve_single_leg_ephemeris_lambert_seed,
)


def retarget_cislunar_mission_spec(spec: dict, seed: CislunarLambertSeed) -> dict:
    out = copy.deepcopy(spec)
    if not out.get("spacecraft"):
        raise ValueError("MissionSpec has no spacecraft to retarget")
    sc = out["spacecraft"][0]
    sc["state_type"] = "cartesian"
    sc["frame"] = "EarthMJ2000Eq"
    sc["position_km"] = [float(x) for x in seed.departure_position_km]
    sc["velocity_km_s"] = [float(x) for x in seed.departure_velocity_km_s]
    for key in ("sma_km", "ecc", "inc_deg", "raan_deg", "aop_deg", "ta_deg"):
        sc.pop(key, None)

    for burn in out.get("burns", []):
        if burn.get("id") == "tli_seed":
            burn["frame"] = "VNB"
            burn["origin"] = "Earth"
            burn["delta_v_km_s"] = [float(x) for x in seed.tli_delta_v_vnb_km_s]
            burn.pop("targeting", None)
            break
    else:
        raise ValueError("MissionSpec has no tli_seed burn to retarget")

    out["description"] = (
        "Demonstrative impulsive cislunar transfer retargeted from GMAT Luna ephemeris. "
        "The initial Cartesian state and TLI VNB burn are produced by AMAT's conic-chain Lambert targeting layer."
    )
    return out


__all__ = [
    "BodyEphemerisSample",
    "CislunarLambertSeed",
    "ConicChainLeg",
    "ConicChainNode",
    "ConicChainSeed",
    "EphemerisLambertSeed",
    "load_gmat_body_ephemeris_csv",
    "retarget_cislunar_mission_spec",
    "solve_conic_chain_seed",
    "solve_ephemeris_lambert_seed",
    "solve_single_leg_ephemeris_lambert_seed",
]

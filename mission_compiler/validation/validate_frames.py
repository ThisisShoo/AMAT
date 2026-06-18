from __future__ import annotations

import re
from mission_compiler.errors import MissionValidationError
from mission_compiler.reference_frames import normalize_reference_frame_declarations, frame_gmat_name, AXIS_SUFFIX

GMAT_MAJOR_BODIES = {
    "Sun", "Mercury", "Venus", "Earth", "Luna", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"
}
BODY_ALIASES = {
    "Moon": "Luna",
    "moon": "Luna",
    "luna": "Luna",
    "earth": "Earth",
    "mars": "Mars",
    "sun": "Sun",
}
FRAME_ALIASES = {
    "earth_icrf": "EarthMJ2000Eq",
    "earth_j2000": "EarthMJ2000Eq",
    "earth_inertial": "EarthMJ2000Eq",
    "earth_ecliptic": "EarthMJ2000Ec",
    "luna_icrf": "LunaMJ2000Eq",
    "moon_icrf": "LunaMJ2000Eq",
    "luna_j2000": "LunaMJ2000Eq",
    "moon_j2000": "LunaMJ2000Eq",
    "luna_inertial": "LunaMJ2000Eq",
    "moon_inertial": "LunaMJ2000Eq",
    "luna_fixed": "LunaFixed",
    "moon_fixed": "LunaFixed",
    "mars_icrf": "MarsMJ2000Eq",
    "mars_j2000": "MarsMJ2000Eq",
    "sun_icrf": "SunMJ2000Eq",
    "solar_system_barycenter_icrf": "SolarSystemBarycenterMJ2000Eq",
    "ssb_icrf": "SolarSystemBarycenterMJ2000Eq",
}


def _canonical_body_name(body: str) -> str:
    return BODY_ALIASES.get(body, body)


def _frame_from_declared(frame: str, declared_frames: dict[str, dict] | None = None) -> str | None:
    if not declared_frames or frame not in declared_frames:
        return None
    f = declared_frames[frame]
    gmat = (f.get("backend_overrides", {}) or {}).get("gmat", {}) or {}
    if gmat.get("name"):
        return gmat["name"]
    ftype = f.get("type")
    origin = _canonical_body_name(str(f.get("origin", "")))
    if ftype == "body_inertial_equatorial":
        return f"{origin}MJ2000Eq"
    if ftype == "body_inertial_ecliptic":
        return f"{origin}MJ2000Ec"
    if ftype == "body_fixed":
        return f"{origin}Fixed"
    if ftype == "barycentric_inertial" and origin in {"SolarSystemBarycenter", "SSB"}:
        return "SolarSystemBarycenterMJ2000Eq"
    # Barycentric rotating/two-body rotating frames generally require an
    # explicit GMAT coordinate-system override.  Keep the IR portable but do
    # not invent a GMAT name.
    return None


def gmat_frame(frame: str, declared_frames: dict[str, dict] | None = None) -> str:
    if frame in FRAME_ALIASES:
        return FRAME_ALIASES[frame]
    declared = _frame_from_declared(frame, declared_frames)
    if declared:
        return declared
    # Already looks like a project/GMAT conventional body-centered frame.
    suffixes = sorted(set(AXIS_SUFFIX.values()), key=len, reverse=True)
    if any(re.match(rf"^[A-Za-z][A-Za-z0-9_]*{re.escape(suffix)}$", frame) for suffix in suffixes):
        return frame
    return frame


def validate_frames(spec: dict) -> list[dict]:
    bad = []
    resolved_frames = normalize_reference_frame_declarations(spec)
    declared_frames = {f["id"]: f for f in resolved_frames if f.get("id")}
    for sc in spec.get("spacecraft", []):
        gf = gmat_frame(sc.get("frame"), declared_frames)
        if gf == sc.get("frame") and sc.get("frame") in declared_frames:
            bad.append(f"spacecraft {sc.get('id')} frame {sc.get('frame')} needs backend_overrides.gmat.name or a mappable frame type")
    for out in spec.get("outputs", []):
        for frame in out.get("frames", []):
            gf = gmat_frame(frame, declared_frames)
            if gf == frame and frame in declared_frames:
                bad.append(f"output for spacecraft {out.get('spacecraft')} frame {frame} needs backend_overrides.gmat.name or a mappable frame type")
    for f in resolved_frames:
        gmat = (f.get("backend_overrides", {}) or {}).get("gmat", {}) or {}
        if gmat.get("create_coordinate_system") and not frame_gmat_name(f):
            bad.append(f"frame {f.get('id')} requests GMAT coordinate creation but has no GMAT name")
        if f.get("type") in {"object_referenced", "barycentric_rotating", "two_body_rotating", "body_orbit_referenced", "spacecraft_orbit_referenced"}:
            if not (gmat.get("primary") or f.get("primary")) or not (gmat.get("secondary") or f.get("secondary")):
                bad.append(f"frame {f.get('id')} needs primary and secondary objects for GMAT ObjectReferenced axes")
    if bad:
        raise MissionValidationError("; ".join(bad))
    return [{"check_id": "frames", "status": "passed", "severity": "error", "message": "Frames are explicit in MissionSpec/catalog and mappable to GMAT coordinate systems where required."}]

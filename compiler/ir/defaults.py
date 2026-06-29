from __future__ import annotations

from copy import deepcopy
from compiler.time_formats import canonicalize_epoch

from compiler.validation.validate_frames import gmat_frame
from compiler.reference_frames import normalize_reference_frame_declarations

GMAT_BUILTIN_MAJOR_BODIES = [
    "Sun", "Mercury", "Venus", "Earth", "Luna", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"
]
THIRD_BODY_PRESETS = {
    "none": [],
    "earth_near_space": ["Sun", "Luna"],
    "inner_solar_system": ["Sun", "Luna", "Mercury", "Venus", "Mars", "Jupiter"],
    "all_major_bodies": ["Sun", "Luna", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"],
}


def _stable_body_order(bodies: list[str], central_body: str | None = None) -> list[str]:
    seen = set()
    cleaned = []
    for body in bodies:
        if not body or body == central_body or body in seen:
            continue
        seen.add(body)
        cleaned.append(body)
    builtins = [b for b in GMAT_BUILTIN_MAJOR_BODIES if b in seen]
    custom = sorted([b for b in cleaned if b not in GMAT_BUILTIN_MAJOR_BODIES])
    return builtins + custom


def apply_defaults(spec: dict) -> dict:
    """Return a copy with explicit MVP defaults filled in.

    Defaults remain geocentric, but force models are no longer Earth-only.  A
    force model without an explicit central body uses Earth.  Third-body lists
    are portable MissionSpec intent; the GMAT backend maps them to PointMasses.
    """
    spec = deepcopy(spec)
    is_public_v2 = spec.get("schema_version") == "2.0.0"
    spec.setdefault("bodies", [])
    spec.setdefault("external_dependencies", [])
    if not is_public_v2:
        spec.setdefault("frames", [])
    spec.setdefault("reference_frames", [])
    spec.setdefault("reference_frame_sets", [])
    resolved_frames = normalize_reference_frame_declarations(spec)
    # Store expanded frame declarations in canonical MissionSpec so scripts are reproducible.
    spec["reference_frames"] = resolved_frames
    declared_frames = {f["id"]: f for f in resolved_frames if f.get("id")}
    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    spec.setdefault("execution", {"mode": "auto"})
    spec["execution"].setdefault("mode", "auto")
    spec.setdefault("checkpoints", [])
    if not is_public_v2:
        spec.setdefault("burns", [])
        spec.setdefault("events", [])
    for sc in spec.get("spacecraft", []):
        if sc.get("epoch"):
            sc["epoch"] = canonicalize_epoch(sc["epoch"])
        frame = sc.get("reference_frame", sc.get("frame"))
        if frame:
            normalized_frame = gmat_frame(frame, declared_frames)
            if is_public_v2:
                sc["reference_frame"] = normalized_frame
            else:
                sc["frame"] = normalized_frame
        if is_public_v2:
            sc.setdefault("drag_area", 15.0)
            sc.setdefault("srp_area", 1.0)
            sc.setdefault("drag_coefficient", 2.2)
            sc.setdefault("coefficient_of_reflectivity", 1.8)
        else:
            sc.setdefault("drag_area_m2", 15.0)
            sc.setdefault("srp_area_m2", 1.0)
            sc.setdefault("cd", 2.2)
            sc.setdefault("cr", 1.8)

    body_name_map = {}
    for body in spec.get("bodies", []):
        gmat = body.get("backend_overrides", {}).get("gmat", {})
        if gmat.get("name"):
            body_name_map[body["name"]] = gmat["name"]
            body_name_map[body["id"]] = gmat["name"]

    for burn in spec.get("burns", []):
        burn.setdefault("origin", "Earth")
        burn["origin"] = body_name_map.get(burn["origin"], burn["origin"])
        if burn.get("frame"):
            burn["frame"] = gmat_frame(burn["frame"], declared_frames)
    for maneuver in spec.get("maneuvers", []):
        maneuver.setdefault("origin", "Earth")
        maneuver["origin"] = body_name_map.get(maneuver["origin"], maneuver["origin"])
        if maneuver.get("reference_frame"):
            maneuver["reference_frame"] = gmat_frame(maneuver["reference_frame"], declared_frames)
    for fm in spec.get("force_models", []):
        fm.setdefault("central_body", "Earth")
        fm["central_body"] = body_name_map.get(fm["central_body"], fm["central_body"])
        central = fm["central_body"]

        fm.setdefault("point_masses", [])
        tbg = fm.setdefault("third_body_gravity", {"enabled": bool(fm.get("point_masses"))})
        tbg.setdefault("enabled", bool(fm.get("point_masses")))
        preset = tbg.get("preset")
        preset_bodies = THIRD_BODY_PRESETS.get(preset, []) if preset else []
        bodies = list(fm.get("point_masses") or []) + list(tbg.get("bodies") or []) + list(preset_bodies)
        bodies = [body_name_map.get(body, body) for body in bodies]
        bodies = _stable_body_order(bodies, central)
        if tbg.get("enabled"):
            tbg["bodies"] = bodies
            fm["point_masses"] = bodies
        else:
            tbg["bodies"] = []
            fm["point_masses"] = []

        gravity = fm.setdefault("gravity", {})
        gtype = gravity.get("type") or gravity.get("model")
        if gtype is None:
            gravity["model" if is_public_v2 else "type"] = "PointMass" if is_public_v2 else "point_mass"
            gtype = gravity["model" if is_public_v2 else "type"]
        if gtype == "basic_earth_gravity":
            # Backward-compatible alias for spherical harmonic Earth gravity.
            gravity["type"] = "spherical_harmonic"
            gtype = "spherical_harmonic"
        gravity.setdefault("body", central)
        if str(gtype) in {"spherical_harmonic", "SphericalHarmonic", "HolmesFeatherstone", "EGM96", "EGM2008"}:
            gravity.setdefault("degree", 4)
            gravity.setdefault("order", 4)
            if central == "Earth":
                gravity.setdefault("potential_file", "JGM2.cof")
        else:
            gravity.setdefault("degree", 0)
            gravity.setdefault("order", 0)
        fm.setdefault("backend_overrides", {})
        fm["backend_overrides"].setdefault("gmat", {})
        if "potential_file" not in fm["backend_overrides"]["gmat"] and gravity.get("potential_file"):
            fm["backend_overrides"]["gmat"]["potential_file"] = gravity.get("potential_file")
        fm["backend_overrides"]["gmat"].setdefault("tide_model", "None")
        fm["backend_overrides"]["gmat"].setdefault("stm_limit", 100)
        fm["backend_overrides"]["gmat"].setdefault("error_control", "RSSStep")
        existing_map = fm["backend_overrides"]["gmat"].setdefault("body_name_map", {})
        existing_map.update({k: v for k, v in body_name_map.items() if k not in existing_map})
    for out in spec.get("outputs", []):
        out.setdefault("enabled", True)
        out.setdefault("include_header", True)
        otype = out["type"]
        sc = spacecraft_by_id.get(out.get("spacecraft"), {})
        sc_frame = sc.get("reference_frame", sc.get("frame", "EarthMJ2000Eq"))
        if otype in {"state_history", "StateHistory"}:
            out.setdefault("path", f"outputs/{spec['mission_id']}_state_history.csv")
            out.setdefault("step" if is_public_v2 else "step_s", 60.0)
            out.setdefault("frames", [sc_frame])
            out["frames"] = [gmat_frame(f, declared_frames) for f in out.get("frames", [])]
            out.setdefault("state_groups", ["Cartesian", "ElapsedTime"] if is_public_v2 else ["cartesian", "elapsed_time"])
            out.setdefault("parameters", [])
            out.setdefault("fields", [])
        elif otype in {"spacecraft_ephemeris", "full_ephemeris", "EphemerisFile", "ReportFile"}:
            out.setdefault("frames", [sc_frame])
            out["frames"] = [gmat_frame(f, declared_frames) for f in out.get("frames", [])]
            full_type = otype in {"full_ephemeris", "ReportFile"}
            default_groups = [] if full_type else (["Cartesian", "ElapsedTime"] if is_public_v2 else ["cartesian", "elapsed_time"])
            out.setdefault("state_groups", default_groups)
            out.setdefault("parameters", [])
            out.setdefault("fields", [])
            out.setdefault("path_template", "outputs/{spacecraft}_{frame}.eph.csv")
        elif otype in {"ground_track", "GroundTrack"}:
            out.setdefault("body", "Earth")
            out.setdefault("step" if is_public_v2 else "step_s", 60.0)
            out.setdefault("parameters", [])
            out.setdefault("fields", [])
            out.setdefault("path", "outputs/_GroundTrack_{spacecraft}_{body}.csv")
    for cp in spec.get("checkpoints", []):
        cp.setdefault("enabled", True)
        cp.setdefault("include_header", True)
        sc = spacecraft_by_id.get(cp.get("spacecraft"), {})
        sc_frame = sc.get("reference_frame", sc.get("frame", "EarthMJ2000Eq"))
        frame_key = "reference_frame" if is_public_v2 else "frame"
        cp.setdefault(frame_key, sc_frame)
        cp[frame_key] = gmat_frame(cp[frame_key], declared_frames)
        cp.setdefault("state_groups", [] if not is_public_v2 else [])
        cp.setdefault("fields", [])
        cp.setdefault("path", "outputs/{checkpoint_id}.csv")
    return spec


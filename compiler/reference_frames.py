from __future__ import annotations

from copy import deepcopy
from typing import Iterable

GMAT_MAJOR_BODIES = [
    "Sun", "Mercury", "Venus", "Earth", "Luna", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"
]

DEFAULT_PARENTS = {
    "Mercury": "Sun", "Venus": "Sun", "Earth": "Sun", "Luna": "Earth", "Mars": "Sun",
    "Jupiter": "Sun", "Saturn": "Sun", "Uranus": "Sun", "Neptune": "Sun", "Pluto": "Sun",
}

# Axis types shown in GMAT's CoordinateSystem Type drop-down.
GMAT_AXIS_TYPES = [
    "MJ2000Eq", "MJ2000Ec",
    "TOEEq", "TOEEc", "MOEEq", "MOEEc", "TODEq", "TODEc", "MODEq", "MODEc",
    "ObjectReferenced", "Equator", "BodyFixed", "BodyInertial", "GSE", "GSM", "Topocentric",
    "LocalAlignedConstrained", "SPICE", "ICRF", "BodySpinSun", "TEME",
]

BODY_CENTERED_AXIS_TYPES = [
    "MJ2000Eq", "MJ2000Ec",
    "TOEEq", "TOEEc", "MOEEq", "MOEEc", "TODEq", "TODEc", "MODEq", "MODEc",
    "Equator", "BodyFixed", "BodyInertial", "ICRF", "BodySpinSun",
]

EARTH_SPECIAL_AXIS_TYPES = ["GSE", "GSM", "TEME"]

FRAME_TYPE_BY_AXIS = {
    "MJ2000Eq": "body_inertial_equatorial",
    "MJ2000Ec": "body_inertial_ecliptic",
    "BodyFixed": "body_fixed",
    "BodyInertial": "body_inertial",
    "ObjectReferenced": "object_referenced",
    "Topocentric": "topocentric",
    "LocalAlignedConstrained": "local_aligned_constrained",
    "SPICE": "spice",
    "ICRF": "icrf",
    "GSE": "gse",
    "GSM": "gsm",
    "TEME": "teme",
    "BodySpinSun": "body_spin_sun",
    "Equator": "equator",
}

# Conventional name suffix. GMAT names are user-defined, so these are project conventions.
AXIS_SUFFIX = {
    "MJ2000Eq": "MJ2000Eq",
    "MJ2000Ec": "MJ2000Ec",
    "TOEEq": "TOEEq",
    "TOEEc": "TOEEc",
    "MOEEq": "MOEEq",
    "MOEEc": "MOEEc",
    "TODEq": "TODEq",
    "TODEc": "TODEc",
    "MODEq": "MODEq",
    "MODEc": "MODEc",
    "Equator": "Equator",
    "BodyFixed": "Fixed",
    "BodyInertial": "BodyInertial",
    "ICRF": "ICRF",
    "BodySpinSun": "BodySpinSun",
    "GSE": "GSE",
    "GSM": "GSM",
    "TEME": "TEME",
}


def safe_frame_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in value)


def _frame_id(body: str, axes: str) -> str:
    return f"{safe_frame_name(body)}_{safe_frame_name(axes).lower()}"


def body_axis_frame(body: str, axes: str) -> dict:
    """Return a conventional body-centered GMAT CoordinateSystem declaration."""
    body = safe_frame_name(body)
    suffix = AXIS_SUFFIX.get(axes, safe_frame_name(axes))
    name = f"{body}{suffix}"
    ftype = FRAME_TYPE_BY_AXIS.get(axes, "gmat_builtin")
    return {
        "id": _frame_id(body, axes),
        "name": name,
        "type": ftype,
        "origin": body,
        "orientation": axes,
        "axes": axes,
        "description": f"{body}-centered frame using GMAT {axes} axes.",
        "backend_overrides": {
            "gmat": {
                "name": name,
                "create_coordinate_system": True,
                "origin": body,
                "axes": axes,
            }
        },
    }


def body_standard_frames(body: str) -> list[dict]:
    """Return all common GMAT-style body-centered frame declarations."""
    return [body_axis_frame(body, axes) for axes in BODY_CENTERED_AXIS_TYPES]


def earth_special_frames() -> list[dict]:
    return [body_axis_frame("Earth", axes) for axes in EARTH_SPECIAL_AXIS_TYPES]


def object_referenced_frame(*, name: str, origin: str, primary: str, secondary: str, x_axis: str = "R", y_axis: str | None = None, z_axis: str = "N", description: str = "") -> dict:
    name = safe_frame_name(name)
    gmat = {"name": name, "create_coordinate_system": True, "origin": origin, "axes": "ObjectReferenced", "primary": primary, "secondary": secondary, "x_axis": x_axis, "z_axis": z_axis}
    if y_axis:
        gmat["y_axis"] = y_axis
    return {
        "id": name,
        "name": name,
        "type": "object_referenced",
        "origin": origin,
        "primary": primary,
        "secondary": secondary,
        "orientation": "ObjectReferenced",
        "axes": "ObjectReferenced",
        "plane": z_axis,
        "x_axis": x_axis,
        "y_axis": y_axis,
        "z_axis": z_axis,
        "description": description or f"Object-referenced frame: origin={origin}, primary={primary}, secondary={secondary}, X={x_axis}, Z={z_axis}.",
        "backend_overrides": {"gmat": gmat},
    }


def body_parent_orbit_frame(body: str, parent: str | None = None) -> dict | None:
    parent = parent or DEFAULT_PARENTS.get(body)
    if not parent:
        return None
    return object_referenced_frame(
        name=f"{body}{parent}Rotating",
        origin=body,
        primary=body,
        secondary=parent,
        x_axis="R",
        z_axis="N",
        description=f"{body}-centered frame using the {body}-{parent} line and the {body} orbit plane about {parent}.",
    )


def spacecraft_orbit_frame(spacecraft: str, central_body: str, name: str | None = None) -> dict:
    name = name or f"{spacecraft}{central_body}OrbitFrame"
    return object_referenced_frame(
        name=name,
        origin=spacecraft,
        primary=spacecraft,
        secondary=central_body,
        x_axis="R",
        z_axis="N",
        description=f"{spacecraft}-centered frame using the {spacecraft}-{central_body} line and orbit plane.",
    )


def topocentric_frame(*, name: str, origin: str, description: str = "") -> dict:
    name = safe_frame_name(name)
    return {
        "id": name,
        "name": name,
        "type": "topocentric",
        "origin": origin,
        "orientation": "Topocentric",
        "axes": "Topocentric",
        "description": description or f"Topocentric frame centered on {origin}.",
        "backend_overrides": {"gmat": {"name": name, "create_coordinate_system": True, "origin": origin, "axes": "Topocentric"}},
    }


def spice_frame(*, name: str, origin: str, spice_frame_name: str, description: str = "", kernel_set: str | None = None) -> dict:
    name = safe_frame_name(name)
    gmat = {"name": name, "create_coordinate_system": True, "origin": origin, "axes": "SPICE", "spice_frame_name": spice_frame_name}
    if kernel_set:
        gmat["kernel_set"] = kernel_set
    return {
        "id": name,
        "name": name,
        "type": "spice",
        "origin": origin,
        "orientation": "SPICE",
        "axes": "SPICE",
        "spice": {"frame_name": spice_frame_name, "kernel_set": kernel_set},
        "description": description or f"SPICE frame {spice_frame_name} centered on {origin}.",
        "backend_overrides": {"gmat": gmat},
    }


def local_aligned_constrained_frame(*, name: str, origin: str, description: str = "", **options) -> dict:
    name = safe_frame_name(name)
    gmat = {"name": name, "create_coordinate_system": True, "origin": origin, "axes": "LocalAlignedConstrained"}
    gmat.update({k: v for k, v in options.items() if v is not None})
    return {
        "id": name,
        "name": name,
        "type": "local_aligned_constrained",
        "origin": origin,
        "orientation": "LocalAlignedConstrained",
        "axes": "LocalAlignedConstrained",
        "description": description or f"LocalAlignedConstrained frame centered on {origin}.",
        "backend_overrides": {"gmat": gmat},
    }


def expand_reference_frame_sets(spec: dict) -> list[dict]:
    frames: list[dict] = []
    sets = spec.get("reference_frame_sets", []) or []
    bodies = [b.get("name") for b in spec.get("bodies", []) if b.get("name")] or []
    major = GMAT_MAJOR_BODIES

    def add_standard(body_list: Iterable[str]) -> None:
        for body in body_list:
            frames.extend(body_standard_frames(body))

    def add_basic(body_list: Iterable[str]) -> None:
        for body in body_list:
            for axes in ["MJ2000Eq", "MJ2000Ec", "BodyFixed", "BodyInertial"]:
                frames.append(body_axis_frame(body, axes))

    def add_parent(body_list: Iterable[str]) -> None:
        for body in body_list:
            f = body_parent_orbit_frame(body)
            if f:
                frames.append(f)

    for item in sets:
        if isinstance(item, str):
            preset = item
            item_bodies = major
            pairs = []
        else:
            preset = item.get("preset")
            item_bodies = item.get("bodies") or bodies or major
            pairs = item.get("pairs") or []
        if preset in {"major_body_standard", "major_body_full_gmat_axes"}:
            add_standard(item_bodies)
            if "Earth" in item_bodies:
                frames.extend(earth_special_frames())
        elif preset == "major_body_basic":
            add_basic(item_bodies)
        elif preset == "earth_special":
            frames.extend(earth_special_frames())
        elif preset == "major_body_parent_orbit":
            add_parent(item_bodies)
        elif preset == "earth_luna_rotating":
            frames.append(object_referenced_frame(name="EarthLunaRotating", origin="Earth", primary="Earth", secondary="Luna", x_axis="R", z_axis="N", description="Earth-centered Earth-Luna rotating frame."))
            frames.append(object_referenced_frame(name="LunaEarthRotating", origin="Luna", primary="Luna", secondary="Earth", x_axis="R", z_axis="N", description="Luna-centered Luna-Earth rotating frame."))
        elif preset == "sun_earth_rotating":
            frames.append(object_referenced_frame(name="SunEarthRotating", origin="Sun", primary="Sun", secondary="Earth", x_axis="R", z_axis="N", description="Sun-centered Sun-Earth rotating frame."))
            frames.append(object_referenced_frame(name="EarthSunRotating", origin="Earth", primary="Earth", secondary="Sun", x_axis="R", z_axis="N", description="Earth-centered Earth-Sun rotating frame."))
        elif preset in {"all_common_gmat", "all_gmat_axis_types"}:
            add_standard(major)
            frames.extend(earth_special_frames())
            add_parent([b for b in major if b != "Sun"])
            frames.append(object_referenced_frame(name="EarthLunaRotating", origin="Earth", primary="Earth", secondary="Luna", x_axis="R", z_axis="N"))
            frames.append(object_referenced_frame(name="LunaEarthRotating", origin="Luna", primary="Luna", secondary="Earth", x_axis="R", z_axis="N"))
        elif preset == "custom":
            for pair in pairs:
                primary = pair["primary"]
                secondary = pair["secondary"]
                origin = pair.get("origin") or primary
                frames.append(object_referenced_frame(name=f"{primary}{secondary}Rotating", origin=origin, primary=primary, secondary=secondary, x_axis=pair.get("x_axis", "R"), z_axis=pair.get("z_axis", "N")))
    return frames


def normalize_reference_frame_declarations(spec: dict) -> list[dict]:
    """Return explicit reference-frame declarations from catalog plus MissionSpec."""
    frames = []
    frames.extend(deepcopy(spec.get("frames", []) or []))
    frames.extend(deepcopy(spec.get("reference_frames", []) or []))
    frames.extend(expand_reference_frame_sets(spec))

    # Auto-declare GMAT-style frames that are actually referenced by spacecraft/outputs/checkpoints.
    gmat_suffixes = tuple(AXIS_SUFFIX.values())
    # Prefer deterministic/longer suffix matching.
    suffixes_by_len = sorted(set(gmat_suffixes), key=len, reverse=True)
    referenced_frames: list[str] = []
    for sc in spec.get("spacecraft", []):
        frame = sc.get("frame")
        if isinstance(frame, str):
            referenced_frames.append(frame)
    for out_spec in spec.get("outputs", []) or []:
        for frame in out_spec.get("frames", []) or []:
            if isinstance(frame, str):
                referenced_frames.append(frame)
        frame = out_spec.get("frame")
        if isinstance(frame, str):
            referenced_frames.append(frame)
    for cp in spec.get("checkpoints", []) or []:
        frame = cp.get("frame")
        if isinstance(frame, str):
            referenced_frames.append(frame)

    for frame in referenced_frames:
        for suffix in suffixes_by_len:
            if frame.endswith(suffix):
                body = frame[: -len(suffix)]
                axes = next((a for a, s in AXIS_SUFFIX.items() if s == suffix), None)
                if body and axes:
                    frames.append(body_axis_frame(body, axes))
                break

    seen: set[str] = set()
    out: list[dict] = []
    for f in frames:
        key = f.get("id") or f.get("name") or str(f)
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def frame_gmat_name(frame: dict) -> str | None:
    gmat = (frame.get("backend_overrides", {}) or {}).get("gmat", {}) or {}
    if gmat.get("name"):
        return gmat["name"]
    if frame.get("name"):
        return frame["name"]
    origin = frame.get("origin")
    axes = frame.get("axes") or frame.get("orientation")
    if origin and axes in AXIS_SUFFIX:
        return f"{origin}{AXIS_SUFFIX[axes]}"
    return None


def _gmat_field_items(gmat: dict) -> list[dict]:
    """Return generic GMAT CoordinateSystem property assignments.

    Known keys are emitted by the template directly. Remaining keys are emitted
    as best-effort raw GMAT field assignments, allowing MissionSpec to access
    specialized axes options such as SPICE/Topocentric/LAC without blocking the IR.
    """
    reserved = {"name", "create_coordinate_system", "origin", "axes", "primary", "secondary", "x_axis", "y_axis", "z_axis"}
    rename = {
        "spice_frame_name": "SPICEFrameName",
        "kernel_set": "KernelSet",
        "align_vector": "AlignVector",
        "constraint_vector": "ConstraintVector",
        "reference_object": "ReferenceObject",
    }
    items = []
    for key, value in gmat.items():
        if key in reserved or value is None:
            continue
        field = rename.get(key, key)
        # Field names in explicit overrides can already be GMAT-cased.
        if field and field[0].islower():
            field = field[0].upper() + field[1:]
        if isinstance(value, bool):
            raw = "true" if value else "false"
        elif isinstance(value, (int, float)):
            raw = str(value)
        elif isinstance(value, list):
            raw = "{ " + ", ".join(str(v) for v in value) + " }"
        else:
            raw = str(value)
        items.append({"field": field, "value": raw})
    return items


def frame_to_gmat_coordinate_system(frame: dict) -> dict | None:
    gmat = (frame.get("backend_overrides", {}) or {}).get("gmat", {}) or {}
    name = frame_gmat_name(frame)
    if not name:
        return None
    if gmat.get("create_coordinate_system") is False:
        return None
    axes = gmat.get("axes") or frame.get("axes") or frame.get("orientation")
    origin = gmat.get("origin") or frame.get("origin")
    if not axes or not origin:
        return None
    descriptor = {
        "name": name,
        "origin": origin,
        "axes": axes,
        "primary": gmat.get("primary") or frame.get("primary"),
        "secondary": gmat.get("secondary") or frame.get("secondary"),
        "x_axis": gmat.get("x_axis") or frame.get("x_axis"),
        "y_axis": gmat.get("y_axis") or frame.get("y_axis"),
        "z_axis": gmat.get("z_axis") or frame.get("z_axis"),
        "fields": _gmat_field_items(gmat),
    }
    return descriptor

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from compiler.hashing import hash_file
from compiler.io import write_text
from compiler.dependencies.spice import write_spice_requests
from compiler.ir.sequence import iter_steps
from compiler.reference_frames import AXIS_SUFFIX, normalize_reference_frame_declarations
from compiler.time_formats import format_epoch_for_backend
from compiler.visualization import write_visualization_manifest


MU_KM3_S2 = {
    "Sun": 132712440041.27942,
    "Mercury": 22031.868551,
    "Venus": 324858.592,
    "Earth": 398600.435507,
    "Luna": 4902.800118,
    "Moon": 4902.800118,
    "Mars": 42828.375816,
    "Jupiter": 126712764.1,
    "Saturn": 37940584.8418,
    "Uranus": 5794556.4,
    "Neptune": 6836527.10058,
    "Pluto": 975.5,
}

BODY_RADII_KM = {
    "Sun": 695700.0,
    "Mercury": 2439.7,
    "Venus": 6051.8,
    "Earth": 6378.1363,
    "Luna": 1737.4,
    "Moon": 1737.4,
    "Mars": 3389.5,
    "Jupiter": 69911.0,
    "Saturn": 58232.0,
    "Uranus": 25362.0,
    "Neptune": 24622.0,
    "Pluto": 1188.3,
}

SUPPORTED_FRAMES = {
    "EarthMJ2000Eq",
    "MJ2000Eq",
    "EME2000",
    "LunaMJ2000Eq",
    "MoonMJ2000Eq",
}

LOCAL_ORBITAL_FRAMES = {"VNB", "LVLH", "TNW", "QSW", "RSW", "SpacecraftBody"}

OREKIT_EVENT_TYPES = {
    "parameter_reaches",
    "orbital_event",
    "node_crossing",
    "date",
    "distance_threshold",
    "soi_crossing",
    "elevation",
    "eclipse",
}

BODY_ALIASES = {
    "Moon": "Luna",
}

OREKIT_INERTIAL_AXES = {
    "MJ2000Eq",
    "MJ2000Ec",
    "TOEEq",
    "TOEEc",
    "MOEEq",
    "MOEEc",
    "TODEq",
    "TODEc",
    "MODEq",
    "MODEc",
    "Equator",
    "BodyInertial",
    "ICRF",
    "BodySpinSun",
    "GSE",
    "GSM",
    "TEME",
}

OREKIT_FIXED_AXES = {"BodyFixed", "Fixed"}


def _canonical_body(body: str | None) -> str | None:
    if not body:
        return None
    return BODY_ALIASES.get(str(body), str(body))


def _frame_declarations(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    frames: dict[str, dict[str, Any]] = {}
    for frame in normalize_reference_frame_declarations(spec):
        name = frame.get("name")
        if name:
            frames[str(name)] = frame
        frame_id = frame.get("id")
        if frame_id:
            frames.setdefault(str(frame_id), frame)
    return frames


def _conventional_frame(frame: str) -> dict[str, Any] | None:
    if frame in {"MJ2000Eq", "MJ2000Ec", "EME2000"}:
        return {"name": frame, "body": "Earth", "axes": "MJ2000Eq", "kind": "inertial"}
    suffix_to_axes = {v: k for k, v in AXIS_SUFFIX.items()}
    for suffix in sorted(suffix_to_axes, key=len, reverse=True):
        if not frame.endswith(suffix):
            continue
        body = _canonical_body(frame[: -len(suffix)])
        axes = suffix_to_axes[suffix]
        if body in MU_KM3_S2:
            kind = "fixed" if axes in OREKIT_FIXED_AXES else "inertial"
            return {"name": frame, "body": body, "axes": axes, "kind": kind}
    return None


def _declared_frame_info(spec: dict[str, Any], frame: str) -> dict[str, Any] | None:
    declared = _frame_declarations(spec).get(frame)
    if not declared:
        return None
    body = _canonical_body(declared.get("origin"))
    axes = declared.get("axes") or declared.get("orientation")
    frame_type = declared.get("type")
    if frame_type in {"topocentric", "topocentric_station", "Topocentric"}:
        body = _canonical_body(declared.get("body") or declared.get("central_body") or declared.get("origin"))
        if body not in MU_KM3_S2:
            return None
        site = declared.get("site") or declared.get("station") or declared.get("definition") or declared
        latitude = site.get("latitude_deg", site.get("latitude"))
        longitude = site.get("longitude_deg", site.get("longitude"))
        altitude = site.get("altitude_km", site.get("altitude", site.get("altitude_m", 0.0)))
        if latitude is None or longitude is None:
            return None
        altitude_km = float(altitude)
        if "altitude_m" in site and "altitude_km" not in site and "altitude" not in site:
            altitude_km /= 1000.0
        return {
            "name": frame,
            "body": body,
            "kind": "topocentric",
            "latitude_deg": float(latitude),
            "longitude_deg": float(longitude),
            "altitude_km": altitude_km,
        }
    if frame in LOCAL_ORBITAL_FRAMES or frame_type in {"local_orbital", "local_orbital_frame", "LocalOrbital"}:
        return {"name": frame, "body": body or "Earth", "axes": frame, "kind": "local_orbital"}
    if body not in MU_KM3_S2:
        return None
    if frame_type == "body_fixed" or axes in OREKIT_FIXED_AXES:
        return {"name": frame, "body": body, "axes": "BodyFixed", "kind": "fixed"}
    if axes in OREKIT_INERTIAL_AXES or frame_type in {"body_inertial", "body_inertial_equatorial", "body_inertial_ecliptic", "icrf", "gse", "gsm", "teme", "equator"}:
        return {"name": frame, "body": body, "axes": axes or "MJ2000Eq", "kind": "inertial"}
    return None


def _frame_info(spec: dict[str, Any], frame: str) -> dict[str, Any] | None:
    return _declared_frame_info(spec, frame) or _conventional_frame(frame)


def _is_supported_frame(spec: dict[str, Any], frame: str) -> bool:
    return _frame_info(spec, frame) is not None


class OrekitFrameResolver:
    """MissionSpec frame capability resolver for the Orekit adapter."""

    def __init__(self, spec: dict[str, Any]) -> None:
        self.spec = spec

    def resolve(self, frame: str) -> dict[str, Any] | None:
        return _frame_info(self.spec, frame)

    def output_fallback(self, frame: str) -> dict[str, Any] | None:
        return _frame_output_fallback(self.spec, frame)

    def supports_output(self, frame: str) -> bool:
        info = self.resolve(frame)
        return bool(info and info.get("kind") != "local_orbital") or self.output_fallback(frame) is not None

    def supports_maneuver_frame(self, frame: str) -> bool:
        return frame in LOCAL_ORBITAL_FRAMES or self.supports_output(frame)


def _body_from_fixed_frame_name(frame: str) -> str | None:
    suffix = "Fixed"
    if not frame.endswith(suffix):
        return None
    body = frame[: -len(suffix)]
    return _canonical_body(body) or None


def _frame_output_fallback(spec: dict[str, Any], frame: str) -> dict[str, Any] | None:
    info = _frame_info(spec, frame)
    if info and info["kind"] == "inertial":
        return None
    if info and info["kind"] == "topocentric":
        return {
            "mode": "frame_fallback",
            "kind": "topocentric",
            "body": info["body"],
            "target_frame": frame,
            "latitude_deg": info["latitude_deg"],
            "longitude_deg": info["longitude_deg"],
            "altitude_km": info.get("altitude_km", 0.0),
        }
    if info and info["kind"] == "local_orbital":
        return None
    body = (info or {}).get("body") or _body_from_fixed_frame_name(frame)
    if not body or body not in MU_KM3_S2:
        return None
    return {
        "mode": "frame_fallback",
        "kind": "body_fixed",
        "body": body,
        "radius_km": BODY_RADII_KM.get(body),
        "target_frame": frame,
        "axes": "BodyFixed",
    }


def _output_frame_entry(
    spec: dict[str, Any],
    sc: dict[str, Any],
    sc_id: str,
    frame: str,
    template: str,
    *,
    step_s: float | None = None,
) -> dict[str, Any] | None:
    path = str(template).format(spacecraft=sc.get("name") or sc_id, frame=frame)
    entry: dict[str, Any] = {"spacecraft": sc_id, "frame": frame, "path": path.replace("\\", "/")}
    if step_s is not None:
        entry["step_s"] = float(step_s)
    fallback = _frame_output_fallback(spec, frame)
    if _is_supported_frame(spec, frame) and not fallback:
        entry["mode"] = "native"
        return entry
    if fallback:
        entry["mode"] = "frame_fallback"
        entry["fallback"] = fallback
        return entry
    return None


def _propagator_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in spec.get("propagators", []) or []}


def _force_model_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in spec.get("force_models", []) or []}


def _spacecraft_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in spec.get("spacecraft", []) or []}


def _central_body_for_spacecraft(spec: dict[str, Any], spacecraft_id: str) -> str:
    propagators = _propagator_by_id(spec)
    force_models = _force_model_by_id(spec)
    for _, step, _ in iter_steps(spec):
        if step.get("spacecraft") != spacecraft_id:
            continue
        prop = propagators.get(step.get("propagator", ""))
        fm = force_models.get(prop.get("force_model", "")) if prop else None
        if fm and fm.get("central_body"):
            return str(fm["central_body"])
    first_fm = next(iter(force_models.values()), {})
    return str(first_fm.get("central_body") or "Earth")


def _force_model_for_spacecraft(spec: dict[str, Any], spacecraft_id: str) -> dict[str, Any]:
    propagators = _propagator_by_id(spec)
    force_models = _force_model_by_id(spec)
    for _, step, _ in iter_steps(spec):
        if step.get("spacecraft") != spacecraft_id:
            continue
        prop = propagators.get(step.get("propagator", ""))
        fm = force_models.get(prop.get("force_model", "")) if prop else None
        if fm:
            return fm
    return next(iter(force_models.values()), {})


def _output_paths(spec: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    spacecraft = _spacecraft_by_id(spec)
    for out in spec.get("outputs", []) or []:
        if out.get("type") not in {"spacecraft_ephemeris", "state_history", "full_ephemeris"}:
            continue
        sc_id = out.get("spacecraft")
        sc = spacecraft.get(sc_id or "")
        if not sc:
            continue
        frames = out.get("frames") or [sc.get("frame", "EarthMJ2000Eq")]
        template = out.get("path_template") or "outputs/{spacecraft}_{frame}.eph.csv"
        step_s = float(out.get("step_s") or 60.0)
        for frame in frames:
            entry = _output_frame_entry(spec, sc, str(sc_id), str(frame), str(template), step_s=step_s)
            if entry:
                outputs.append(entry)
    return outputs


def _ground_track_paths(spec: dict[str, Any]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    spacecraft = _spacecraft_by_id(spec)

    def add_track(sc_id: str, sc: dict[str, Any], body: str, fallback: dict[str, Any] | None, step_s: float | None) -> None:
        key = (sc_id, body)
        if key in seen:
            return
        seen.add(key)
        sc_name = str(sc.get("name") or sc_id)
        tracks.append(
            {
                "spacecraft": sc_id,
                "body": body,
                "frame": f"{body}Fixed",
                "path": f"outputs/_GroundTrack_{sc_name}_{body}.csv",
                "fallback": fallback,
                "radius_km": BODY_RADII_KM.get(body),
                "step_s": float(step_s or 60.0),
            }
        )

    for out in spec.get("outputs", []) or []:
        sc_id = str(out.get("spacecraft") or "")
        sc = spacecraft.get(sc_id)
        if not sc:
            continue
        if out.get("type") == "ground_track":
            body = _canonical_body(str(out.get("body") or "Earth")) or "Earth"
            fallback = _frame_output_fallback(spec, f"{body}Fixed")
            add_track(sc_id, sc, body, fallback, out.get("step_s"))
            continue
        if out.get("type") != "spacecraft_ephemeris":
            continue
        for frame in out.get("frames") or [sc.get("frame", "EarthMJ2000Eq")]:
            fallback = _frame_output_fallback(spec, str(frame))
            if fallback and fallback.get("kind") == "body_fixed":
                add_track(sc_id, sc, str(fallback["body"]), fallback, out.get("step_s"))
    return tracks


def _final_state_paths(spec: dict[str, Any]) -> list[dict[str, str]]:
    outputs: list[dict[str, Any]] = []
    spacecraft = _spacecraft_by_id(spec)
    for out in spec.get("outputs", []) or []:
        if out.get("type") != "final_state":
            continue
        sc_id = out.get("spacecraft")
        sc = spacecraft.get(sc_id or "")
        if not sc:
            continue
        frame = str(out.get("frame") or sc.get("frame") or "EarthMJ2000Eq")
        path = str(out.get("path") or f"outputs/final_state_{sc.get('name') or sc_id}.csv")
        entry = _output_frame_entry(spec, sc, str(sc_id), frame, path)
        if entry:
            outputs.append(entry)
    return outputs


def _body_ephemeris_paths(spec: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    spacecraft = _spacecraft_by_id(spec)
    default_sc = next(iter(spacecraft.values()), {})

    def add_entry(out: dict[str, Any], body: str, path: str) -> None:
        frame = str(out.get("frame") or default_sc.get("frame") or "EarthMJ2000Eq")
        fallback = _frame_output_fallback(spec, frame)
        source = str(out.get("source") or "").lower()
        body = _canonical_body(body) or body
        if body not in MU_KM3_S2 and source == "spice" and out.get("dependency_id"):
            outputs.append(
                {
                    "body": body,
                    "frame": frame,
                    "path": path.replace("\\", "/"),
                    "radius_km": BODY_RADII_KM.get(body),
                    "mode": "spice_fallback",
                    "source": "SPICE",
                    "dependency_id": out.get("dependency_id"),
                    "step_s": float(out.get("step_s") or 60.0),
                    "skip_runtime": True,
                }
            )
            return
        if not _is_supported_frame(spec, frame) and not fallback:
            return
        entry: dict[str, Any] = {
            "body": body,
            "frame": frame,
            "path": path.replace("\\", "/"),
            "radius_km": BODY_RADII_KM.get(body),
            "mode": "native" if _is_supported_frame(spec, frame) and not fallback else "frame_fallback",
            "source": "Orekit",
            "step_s": float(out.get("step_s") or 60.0),
        }
        if fallback:
            entry["fallback"] = fallback
        outputs.append(entry)

    for out in spec.get("outputs", []) or []:
        if out.get("type") == "body_ephemeris":
            body = str(out.get("body") or out.get("target") or "")
            if not body:
                continue
            path = str(out.get("path") or f"outputs/{body}_{out.get('frame') or default_sc.get('frame') or 'EarthMJ2000Eq'}.body.eph.csv")
            add_entry(out, body, path)
        elif out.get("type") == "body_ephemeris_group":
            template = str(out.get("path_template") or "outputs/{body}_{frame}.body.eph.csv")
            frame = str(out.get("frame") or default_sc.get("frame") or "EarthMJ2000Eq")
            for body in out.get("bodies", []) or []:
                add_entry(out, str(body), template.format(body=body, frame=frame))
    return outputs


def _checkpoint_paths(spec: dict[str, Any]) -> list[dict[str, str]]:
    checkpoints: list[dict[str, str]] = []
    for cp in spec.get("checkpoints", []) or []:
        if cp.get("spacecraft") and cp.get("path"):
            checkpoints.append(
                {
                    "id": str(cp.get("id") or Path(str(cp["path"])).stem),
                    "spacecraft": str(cp["spacecraft"]),
                    "frame": str(cp.get("frame") or "EarthMJ2000Eq"),
                    "path": str(cp["path"]).replace("\\", "/"),
                }
            )
    return checkpoints


def _spacecraft_name(spec: dict[str, Any], spacecraft_id: str | None) -> str | None:
    sc = _spacecraft_by_id(spec).get(spacecraft_id or "")
    if not sc:
        return spacecraft_id
    return str(sc.get("name") or spacecraft_id)


def _output_reports(spec: dict[str, Any]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for item in _output_paths(spec):
        sc_id = item.get("spacecraft")
        sc_name = _spacecraft_name(spec, sc_id)
        frame = item.get("frame")
        reports.append(
            {
                "kind": "spacecraft_ephemeris",
                "spacecraft_id": sc_id,
                "spacecraft_name": sc_name,
                "frame": frame,
                "path": item.get("path"),
                "parameters": [
                    f"{sc_name}.ElapsedSecs",
                    f"{sc_name}.{frame}.X",
                    f"{sc_name}.{frame}.Y",
                    f"{sc_name}.{frame}.Z",
                    f"{sc_name}.{frame}.VX",
                    f"{sc_name}.{frame}.VY",
                    f"{sc_name}.{frame}.VZ",
                ],
            }
        )
    return reports


def _ground_track_reports(spec: dict[str, Any]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for item in _ground_track_paths(spec):
        sc_id = item.get("spacecraft")
        sc_name = _spacecraft_name(spec, sc_id)
        body = item.get("body", "Earth")
        reports.append(
            {
                "kind": "ground_track",
                "spacecraft_id": sc_id,
                "spacecraft_name": sc_name,
                "body": body,
                "frame": item.get("frame"),
                "path": item.get("path"),
                "parameters": [
                    f"{sc_name}.ElapsedSecs",
                    f"{sc_name}.{body}.Latitude",
                    f"{sc_name}.{body}.Longitude",
                    f"{sc_name}.{body}.Altitude",
                ],
            }
        )
    return reports


def _checkpoint_reports(spec: dict[str, Any]) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for item in _checkpoint_paths(spec):
        sc_id = item.get("spacecraft")
        sc_name = _spacecraft_name(spec, sc_id)
        frame = item.get("frame")
        reports.append(
            {
                "id": item.get("id"),
                "spacecraft_id": sc_id,
                "spacecraft_name": sc_name,
                "frame": frame,
                "path": item.get("path"),
                "parameters": [
                    f"{sc_name}.ElapsedSecs",
                    f"{sc_name}.{frame}.X",
                    f"{sc_name}.{frame}.Y",
                    f"{sc_name}.{frame}.Z",
                    f"{sc_name}.{frame}.VX",
                    f"{sc_name}.{frame}.VY",
                    f"{sc_name}.{frame}.VZ",
                ],
            }
        )
    return reports


def _sequence_plan(spec: dict[str, Any]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    propagators = _propagator_by_id(spec)
    force_models = _force_model_by_id(spec)
    for _, step, _ in iter_steps(spec):
        typ = step.get("type")
        if typ == "propagate":
            prop = propagators.get(step.get("propagator", ""))
            fm = force_models.get(prop.get("force_model", "")) if prop else None
            plan.append(
                {
                    "type": "propagate",
                    "spacecraft": step["spacecraft"],
                    "propagator": step.get("propagator"),
                    "duration_s": float(step.get("duration_s", 0.0)),
                    "central_body": (fm or {}).get("central_body", "Earth"),
                    "max_step_s": float((prop or {}).get("max_step_s") or 300.0),
                }
            )
        elif typ == "checkpoint":
            plan.append({"type": "checkpoint", "checkpoint_id": step.get("checkpoint_id")})
        elif typ == "maneuver":
            prop = propagators.get(step.get("propagator", ""))
            plan.append(
                {
                    "type": "maneuver",
                    "spacecraft": step.get("spacecraft"),
                    "burn": step.get("burn"),
                    "propagator": step.get("propagator"),
                    "duration_s": float(step.get("duration_s", 0.0) or 0.0),
                    "max_step_s": float((prop or {}).get("max_step_s") or 300.0),
                }
            )
        elif typ == "event_action":
            plan.append({"type": "event_action", "event_id": step.get("event_id")})
    return plan


def _burns_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in spec.get("burns", []) or []}


def _events_by_id(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in spec.get("events", []) or []}


def _runtime_spec(spec: dict[str, Any]) -> dict[str, Any]:
    spacecraft = []
    for sc in spec.get("spacecraft", []) or []:
        item = dict(sc)
        item["central_body"] = _central_body_for_spacecraft(spec, sc["id"])
        item["force_model_id"] = _force_model_for_spacecraft(spec, sc["id"]).get("id")
        item["mu_km3_s2"] = MU_KM3_S2.get(item["central_body"], MU_KM3_S2["Earth"])
        spacecraft.append(item)
    return {
        "mission_id": spec["mission_id"],
        "spacecraft": spacecraft,
        "sequence": _sequence_plan(spec),
        "outputs": _output_paths(spec),
        "body_ephemerides": _body_ephemeris_paths(spec),
        "ground_tracks": _ground_track_paths(spec),
        "final_outputs": _final_state_paths(spec),
        "checkpoints": _checkpoint_paths(spec),
        "burns": _burns_by_id(spec),
        "events": _events_by_id(spec),
        "force_models": _force_model_by_id(spec),
        "propagators": _propagator_by_id(spec),
        "body_mu_km3_s2": MU_KM3_S2,
        "body_radii_km": BODY_RADII_KM,
        "visualization": spec.get("visualization", {}),
    }


class OrekitCompiler:
    backend_id = "orekit"

    def __init__(self) -> None:
        base = Path(files("compiler.backends.orekit"))
        self.env = Environment(
            loader=FileSystemLoader(str(base / "templates")),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals["orekit_epoch"] = lambda value: format_epoch_for_backend(value, "orekit")

    def validate_capability(self, spec: dict[str, Any]) -> list[dict[str, Any]]:
        errors: list[str] = []
        warnings: list[str] = []
        frame_resolver = OrekitFrameResolver(spec)
        force_models = _force_model_by_id(spec)
        propagators = _propagator_by_id(spec)

        for sc in spec.get("spacecraft", []) or []:
            if not _is_supported_frame(spec, str(sc.get("frame"))):
                errors.append(f"Orekit backend cannot resolve spacecraft frame {sc.get('frame')!r} for {sc.get('id')}.")
            if sc.get("state_type") not in {"cartesian", "keplerian"}:
                errors.append(f"Orekit backend does not support state_type {sc.get('state_type')!r}.")

        for fm in force_models.values():
            gravity = fm.get("gravity", {}) or {}
            if gravity.get("type") not in {None, "point_mass", "two_body", "spherical_harmonic", "basic_earth_gravity"}:
                errors.append(f"Orekit backend does not support gravity type {gravity.get('type')} in force model {fm.get('id')}.")
            third_body = fm.get("third_body_gravity", {}) or {}
            point_masses = list(dict.fromkeys((fm.get("point_masses") or []) + (third_body.get("bodies") or [])))
            unsupported_point_masses = [body for body in point_masses if body not in MU_KM3_S2]
            if unsupported_point_masses:
                errors.append(f"Orekit backend has no built-in body mapping for third-body gravity in force model {fm.get('id')}: {', '.join(unsupported_point_masses)}.")
            if fm.get("central_body") not in MU_KM3_S2:
                errors.append(f"Orekit backend has no built-in mu for central body {fm.get('central_body')!r}.")
            if fm.get("atmospheric_drag", {}).get("enabled") or fm.get("drag", {}).get("enabled"):
                warnings.append(f"Orekit backend will configure Harris-Priester drag for force model {fm.get('id')}; spacecraft must provide dry_mass, drag_area, and drag_coefficient.")
            if fm.get("solar_radiation_pressure", {}).get("enabled") or fm.get("srp", {}).get("enabled"):
                warnings.append(f"Orekit backend will configure isotropic SRP for force model {fm.get('id')}; spacecraft must provide dry_mass, srp_area, and coefficient_of_reflectivity.")
            if fm.get("relativity", {}).get("enabled"):
                warnings.append(f"Orekit backend will configure central-body relativity for force model {fm.get('id')}.")
            if fm.get("solid_tides", {}).get("enabled") or fm.get("ocean_tides", {}).get("enabled"):
                warnings.append(f"Orekit backend will attempt tide force models for {fm.get('id')} when the installed Orekit data supports them.")

        for prop in propagators.values():
            fm = force_models.get(prop.get("force_model", ""))
            if fm is None:
                errors.append(f"Orekit backend cannot resolve force model {prop.get('force_model')!r} for propagator {prop.get('id')}.")

        for burn in spec.get("burns", []) or []:
            if burn.get("type") not in {"impulsive", "finite"}:
                errors.append(f"Orekit backend does not support burn {burn.get('id')!r} of type {burn.get('type')!r}.")
            frame = str(burn.get("frame") or "VNB")
            if not frame_resolver.supports_maneuver_frame(frame):
                errors.append(f"Orekit backend cannot resolve burn frame {frame!r} for burn {burn.get('id')!r}.")
        for event in spec.get("events", []) or []:
            if event.get("type") == "parameter_reaches":
                parameter = (event.get("stop_condition", {}) or {}).get("parameter")
                if parameter != "ElapsedSecs" and not str(parameter).endswith((".ArgumentOfLatitude", ".TA")):
                    errors.append(f"Orekit backend does not yet support parameter event {event.get('id')!r} with parameter {parameter!r}.")
            elif event.get("type") == "orbital_event":
                if event.get("event") not in {"periapsis", "apoapsis"}:
                    errors.append(f"Orekit backend does not yet support orbital event {event.get('id')!r} with event {event.get('event')!r}.")
            elif event.get("type") == "node_crossing":
                if event.get("node") not in {"ascending", "descending", "either", "both"}:
                    errors.append(f"Orekit backend does not support node value {event.get('node')!r} for event {event.get('id')!r}.")
                reference_frame = str(event.get("reference_frame") or "")
                info = _frame_info(spec, reference_frame) if reference_frame else None
                if reference_frame and (not info or info.get("kind") != "inertial"):
                    errors.append(f"Orekit backend node-crossing events require a supported inertial reference frame; event {event.get('id')!r} requested {reference_frame!r}.")
            elif event.get("type") == "date":
                if not (event.get("epoch") or event.get("date") or event.get("target_epoch")):
                    errors.append(f"Orekit backend date event {event.get('id')!r} requires epoch, date, or target_epoch.")
            elif event.get("type") in {"distance_threshold", "soi_crossing"}:
                body = _canonical_body(event.get("body") or event.get("target_body") or event.get("target"))
                if body not in MU_KM3_S2:
                    errors.append(f"Orekit backend event {event.get('id')!r} requires a supported body for distance/SOI targeting.")
                if event.get("type") == "distance_threshold" and event.get("threshold_km", event.get("radius_km")) is None:
                    errors.append(f"Orekit backend distance event {event.get('id')!r} requires threshold_km or radius_km.")
            elif event.get("type") == "elevation":
                station = event.get("station") or event.get("site") or {}
                frame = event.get("station_frame") or event.get("frame")
                if frame and not frame_resolver.output_fallback(str(frame)):
                    errors.append(f"Orekit backend elevation event {event.get('id')!r} requires a supported topocentric station frame.")
                elif not frame and not {"latitude_deg", "latitude", "longitude_deg", "longitude"} & set(station):
                    errors.append(f"Orekit backend elevation event {event.get('id')!r} requires station coordinates or station_frame.")
            elif event.get("type") == "eclipse":
                occulting = _canonical_body(event.get("occulting_body") or event.get("body") or "Earth")
                if occulting not in MU_KM3_S2:
                    errors.append(f"Orekit backend eclipse event {event.get('id')!r} uses unsupported occulting body {occulting!r}.")
            else:
                errors.append(f"Orekit backend does not yet support event {event.get('id')!r} of type {event.get('type')!r}.")
        for _, step, _ in iter_steps(spec):
            if step.get("type") not in {"propagate", "checkpoint", "report", "event_action", "maneuver"}:
                errors.append(f"Orekit backend does not yet support mission sequence step {step.get('step_id') or step.get('type')!r} of type {step.get('type')!r}.")

        for out in spec.get("outputs", []) or []:
            if out.get("type") == "ground_track":
                warnings.append(f"Orekit backend will generate ground-track output {out.get('id')!r} from surface-fixed spacecraft states when available.")
            elif out.get("type") in {"spacecraft_ephemeris", "state_history", "full_ephemeris"}:
                sc = _spacecraft_by_id(spec).get(out.get("spacecraft") or "")
                frames = out.get("frames", []) or ([sc.get("frame")] if sc else [])
                fallback_frames = [str(frame) for frame in frames if not (_is_supported_frame(spec, str(frame)) and not _frame_output_fallback(spec, str(frame))) and _frame_output_fallback(spec, str(frame))]
                unsupported = [str(frame) for frame in frames if not frame_resolver.supports_output(str(frame))]
                if fallback_frames:
                    warnings.append(f"Orekit backend will synthesize spacecraft ephemeris frames through validated output fallback for output {out.get('id')!r}: {', '.join(fallback_frames)}.")
                if unsupported:
                    errors.append(f"Orekit backend cannot natively output spacecraft ephemeris frames and no validated fallback is available for output {out.get('id')!r}: {', '.join(unsupported)}.")
            elif out.get("type") == "final_state":
                sc = _spacecraft_by_id(spec).get(out.get("spacecraft") or "")
                frame = str(out.get("frame") or (sc or {}).get("frame") or "EarthMJ2000Eq")
                if not _is_supported_frame(spec, frame) and not _frame_output_fallback(spec, frame):
                    errors.append(f"Orekit backend cannot output final-state frame and no validated fallback is available for output {out.get('id')!r}: {frame}.")
            elif out.get("type") in {"body_ephemeris", "body_ephemeris_group"}:
                body_outputs = _body_ephemeris_paths({"spacecraft": spec.get("spacecraft", []), "outputs": [out], "reference_frames": spec.get("reference_frames", [])})
                requested_bodies = [str(out.get("body") or out.get("target"))] if out.get("type") == "body_ephemeris" else [str(body) for body in out.get("bodies", []) or []]
                unsupported_bodies = [body for body in requested_bodies if body not in MU_KM3_S2]
                source = str(out.get("source") or "").lower()
                if unsupported_bodies:
                    if source == "spice" and out.get("dependency_id"):
                        warnings.append(f"Orekit backend will leave body ephemeris output {out.get('id')!r} to SPICE fallback resolution: {', '.join(unsupported_bodies)}.")
                    else:
                        errors.append(f"Orekit backend has no built-in ephemeris mapping for body ephemeris output {out.get('id')!r}: {', '.join(unsupported_bodies)}.")
                if requested_bodies and not body_outputs:
                    if source == "spice" and out.get("dependency_id"):
                        warnings.append(f"Orekit backend will leave body ephemeris frame for output {out.get('id')!r} to SPICE fallback resolution.")
                    else:
                        errors.append(f"Orekit backend cannot output body ephemeris frame and no validated fallback is available for output {out.get('id')!r}.")
                if body_outputs:
                    warnings.append(f"Orekit backend will generate body ephemeris output {out.get('id')!r} from Orekit celestial body data when available.")
            else:
                errors.append(f"Orekit backend does not support output {out.get('id')!r} of type {out.get('type')!r}.")

        checks = [
            {
                "check_id": "backend_capability",
                "status": "failed" if errors else "passed",
                "severity": "error",
                "message": "MissionSpec fits selected Orekit backend capability." if not errors else "; ".join(errors),
            }
        ]
        checks.extend(
            {
                "check_id": "backend_capability_warning",
                "status": "warning",
                "severity": "warning",
                "message": item,
            }
            for item in warnings
        )
        if errors:
            raise ValueError("; ".join(errors))
        return checks

    def render_python(self, spec: dict[str, Any]) -> str:
        return self.env.get_template("orekit_mission.py.j2").render(runtime_spec=_runtime_spec(spec))

    def compile(self, spec: dict[str, Any], out_dir: str | Path) -> dict[str, Any]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        py_path = out_dir / "generated_mission.py"
        write_text(py_path, self.render_python(spec))
        spice_requests = write_spice_requests(spec, out_dir)
        spice_request_path = out_dir / "dependencies" / "spice_requests.json"
        viz_manifest = write_visualization_manifest(spec, out_dir, reports=_output_reports(spec) + _ground_track_reports(spec), checkpoints=_checkpoint_reports(spec))
        viz_path = out_dir / "visualization_manifest.json"
        generated_artifacts = [
            {
                "artifact_id": "PYTHON_SCRIPT",
                "type": "python_script",
                "path": py_path.name,
                "hash": hash_file(py_path),
                "language": "python",
                "backend": self.backend_id,
            },
            {
                "artifact_id": "VISUALIZATION_MANIFEST",
                "type": "visualization_manifest",
                "path": viz_path.name,
                "hash": hash_file(viz_path),
                "backend": self.backend_id,
            },
        ]
        if spice_requests and spice_request_path.exists():
            generated_artifacts.append(
                {
                    "artifact_id": "SPICE_REQUESTS",
                    "type": "spice_requests",
                    "path": "dependencies/spice_requests.json",
                    "hash": hash_file(spice_request_path),
                    "backend": "spice",
                }
            )
        return {
            "schema_version": "1.0.0",
            "mission_id": spec.get("mission_id", "UNKNOWN"),
            "backend_id": self.backend_id,
            "status": "success",
            "generated_artifacts": generated_artifacts,
            "manifest_counts": {
                "spacecraft_ephemerides": len(viz_manifest.get("spacecraft_ephemerides", [])),
                "body_ephemerides": len(viz_manifest.get("body_ephemerides", [])),
                "checkpoints": len(viz_manifest.get("checkpoints", [])),
                "frames": len(viz_manifest.get("frames", [])),
            },
            "warnings": [
                "Orekit backend supports two-body and numerical propagation, per-segment propagator context, checkpoints, final-state output, impulsive and segmented finite burns in supported frames, date/apsis/node/anomaly/distance/SOI/elevation/eclipse event timing, GMAT-style body-centered inertial/fixed frame names through Orekit frame mapping or validated fallback, body ephemeris output from Orekit celestial body data or SPICE fallback prerequisites, spherical-harmonic and third-body gravity, selected drag/SRP/relativity/tide force models when Orekit data and spacecraft properties are available, ground-track generation from surface-fixed ephemerides, and finite-difference correction artifacts for targeting. Object-referenced rotating frames, native Orekit variational-equation STM, and fully coupled finite-burn force-model dynamics remain unavailable."
            ] + (["SPICE dependency requests were generated for Orekit visualization/body-ephemeris fallback."] if spice_requests else []),
            "errors": [],
        }

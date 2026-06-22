from __future__ import annotations

import re
from pathlib import Path
from importlib.resources import files

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from compiler.backends.capabilities import check_capability
from compiler.hashing import hash_file
from compiler.io import read_json, write_json, write_text
from compiler.validation.validate_frames import gmat_frame
from compiler.ir.sequence import normalize_mission_sequence, iter_steps
from compiler.dependencies.spice import write_spice_requests, build_spice_requests, build_spice_kernel_sets
from compiler.reference_frames import normalize_reference_frame_declarations, frame_to_gmat_coordinate_system, AXIS_SUFFIX
from compiler.visualization import write_visualization_manifest
from compiler.time_formats import format_epoch_for_backend

CARTESIAN_FIELDS = ["X", "Y", "Z", "VX", "VY", "VZ"]
KEPLERIAN_FIELDS = ["SMA", "ECC", "INC", "RAAN", "AOP", "TA"]
MASS_FIELDS = ["DryMass"]
ELAPSED_TIME_FIELDS = ["UTCGregorian", "ElapsedSecs"]


GMAT_DEFAULT_COORDINATE_SYSTEMS = {
    "EarthMJ2000Eq",
    "EarthMJ2000Ec",
    "EarthFixed",
    "MJ2000Eq",
    "MJ2000Ec",
}


def _coordinate_system_from_name(name: str) -> dict | None:
    """Return a GMAT CoordinateSystem creation descriptor when needed.

    GMAT usually provides EarthMJ2000Eq/Ec by default, but body-centered
    coordinate systems such as LunaMJ2000Eq often must be created explicitly
    before they can be used by Spacecraft.CoordinateSystem or ReportFile
    parameters.  This keeps non-Earth propagation body-neutral while still
    compiling to plain GMAT script.
    """
    if not name or name in GMAT_DEFAULT_COORDINATE_SYSTEMS:
        return None
    # Match project GMAT-style names such as MarsMJ2000Eq, LunaTODEq, EarthGSE, EarthTEME.
    suffix_to_axes = {v: k for k, v in AXIS_SUFFIX.items()}
    for suffix in sorted(suffix_to_axes, key=len, reverse=True):
        if not name.endswith(suffix):
            continue
        origin = name[: -len(suffix)]
        if not origin:
            continue
        if origin == "Earth" and suffix in {"MJ2000Eq", "MJ2000Ec", "Fixed"}:
            return None
        if origin in {"SolarSystemBarycenter", "SSB"}:
            return None
        return {
            "name": name,
            "origin": origin,
            "axes": suffix_to_axes[suffix],
            "primary": None,
            "secondary": None,
            "x_axis": None,
            "y_axis": None,
            "z_axis": None,
            "fields": [],
        }
    return None


def _frames_from_parameters(parameters: list[str]) -> set[str]:
    frames: set[str] = set()
    for param in parameters or []:
        parts = param.split(".")
        if len(parts) >= 3:
            qualifier = parts[1]
            suffixes = sorted(set(AXIS_SUFFIX.values()), key=len, reverse=True)
            if any(re.match(rf"^[A-Za-z][A-Za-z0-9_]*{re.escape(suffix)}$", qualifier) for suffix in suffixes):
                frames.add(qualifier)
    return frames


def coordinate_systems_for_gmat(spec: dict, reports: list[dict] | None = None, checkpoints: list[dict] | None = None) -> list[dict]:
    """Collect GMAT coordinate systems that must be explicitly created.

    MissionSpec can declare frames directly through `reference_frames`/`frames`
    or by calling catalog presets through `reference_frame_sets`.  Any frame
    used by spacecraft, outputs, or checkpoints is also auto-declared using
    GMAT naming conventions when possible.  GMAT's built-in default Earth
    frames are treated as system-defined and are not re-created to avoid
    duplicate-resource load failures.
    """
    names: set[str] = set()

    for sc in spec.get("spacecraft", []):
        names.add(gmat_frame(sc.get("frame")))

    for out in spec.get("outputs", []):
        sc = next((s for s in spec.get("spacecraft", []) if s.get("id") == out.get("spacecraft")), None)
        default_frame = sc.get("frame") if sc else None
        for frame in out.get("frames") or ([default_frame] if default_frame else []):
            if frame:
                names.add(gmat_frame(frame))

    for cp in spec.get("checkpoints", []):
        sc = next((s for s in spec.get("spacecraft", []) if s.get("id") == cp.get("spacecraft")), None)
        frame = cp.get("frame") or (sc.get("frame") if sc else None)
        if frame:
            names.add(gmat_frame(frame))

    for burn in spec.get("burns", []):
        frame = burn.get("coordinate_system") or burn.get("frame")
        if frame and frame not in {"VNB", "LVLH", "MJ2000Eq", "SpacecraftBody"}:
            names.add(gmat_frame(frame))

    for report in (reports or []) + (checkpoints or []):
        if report.get("frame"):
            names.add(report["frame"])
        names.update(_frames_from_parameters(report.get("parameters", [])))

    # Start with explicit/catalog frame declarations, then synthesize simple
    # body-centered frames referenced by GMAT-style names.
    systems: list[dict] = []
    seen: set[str] = set()

    for frame_decl in normalize_reference_frame_declarations(spec):
        cs = frame_to_gmat_coordinate_system(frame_decl)
        if not cs:
            continue
        if cs["name"] in GMAT_DEFAULT_COORDINATE_SYSTEMS:
            continue
        if cs["name"] not in seen:
            systems.append(cs)
            seen.add(cs["name"])

    for name in sorted(names):
        cs = _coordinate_system_from_name(name)
        if cs and cs["name"] not in seen:
            systems.append(cs)
            seen.add(cs["name"])
    return systems


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def _script_report_path(report_path: Path, relative_path: str) -> str:
    # GMAT resolves ReportFile.Filename relative to its configured runtime
    # output locations. Use a plain source filename here and let the generated
    # Python runner copy it into the mission-local desired_path after RunScript.
    return Path(relative_path).name


def _unit_vector(values: list[float] | tuple[float, ...]) -> list[float]:
    mag = sum(float(x) * float(x) for x in values) ** 0.5
    if mag <= 0:
        return [1.0, 0.0, 0.0]
    return [float(x) / mag for x in values]


def burn_descriptors(spec: dict) -> list[dict]:
    """Return GMAT-ready burn descriptors with finite-burn helper objects."""
    burns: list[dict] = []
    for burn in spec.get("burns", []) or []:
        item = dict(burn)
        item.setdefault("origin", "Earth")
        if item.get("type") == "finite":
            item["direction_unit"] = _unit_vector(item.get("direction", [1.0, 0.0, 0.0]))
            item["thruster_name"] = _safe_name(f"{item['name']}Thruster")
            item["tank_name"] = _safe_name(f"{item['name']}Tank")
            item.setdefault("decrement_mass", False)
            item.setdefault("duty_cycle", 1.0)
            item.setdefault("fuel_mass_kg", 1000.0)
        burns.append(item)
    return burns


def spacecraft_thrusters(spec: dict) -> dict[str, list[str]]:
    burns = {burn["id"]: burn for burn in burn_descriptors(spec)}
    by_sc: dict[str, list[str]] = {}
    for phase, step, _ in iter_steps(spec):
        if step.get("type") != "maneuver":
            continue
        burn = burns.get(step.get("burn"))
        if not burn or burn.get("type") != "finite":
            continue
        by_sc.setdefault(step["spacecraft"], [])
        if burn["thruster_name"] not in by_sc[step["spacecraft"]]:
            by_sc[step["spacecraft"]].append(burn["thruster_name"])
    for event in spec.get("events", []) or []:
        for action in event.get("actions", []) or []:
            if action.get("type") != "maneuver":
                continue
            burn = burns.get(action.get("burn"))
            if not burn or burn.get("type") != "finite":
                continue
            by_sc.setdefault(action["spacecraft"], [])
            if burn["thruster_name"] not in by_sc[action["spacecraft"]]:
                by_sc[action["spacecraft"]].append(burn["thruster_name"])
    return by_sc


def spacecraft_tanks(spec: dict) -> dict[str, list[str]]:
    burns = {burn["id"]: burn for burn in burn_descriptors(spec)}
    by_sc: dict[str, list[str]] = {}
    for phase, step, _ in iter_steps(spec):
        if step.get("type") != "maneuver":
            continue
        burn = burns.get(step.get("burn"))
        if not burn or burn.get("type") != "finite":
            continue
        by_sc.setdefault(step["spacecraft"], [])
        if burn["tank_name"] not in by_sc[step["spacecraft"]]:
            by_sc[step["spacecraft"]].append(burn["tank_name"])
    for event in spec.get("events", []) or []:
        for action in event.get("actions", []) or []:
            if action.get("type") != "maneuver":
                continue
            burn = burns.get(action.get("burn"))
            if not burn or burn.get("type") != "finite":
                continue
            by_sc.setdefault(action["spacecraft"], [])
            if burn["tank_name"] not in by_sc[action["spacecraft"]]:
                by_sc[action["spacecraft"]].append(burn["tank_name"])
    return by_sc


def _origin_from_gmat_frame(frame: str) -> str:
    """Best-effort GMAT origin from a GMAT coordinate-system name.

    GMAT orbit-element report parameters are not all qualified the same way:
    SMA/ECC/TA are Origin-qualified (e.g. Sat.Earth.SMA), while
    INC/RAAN/AOP are CoordinateSystem-qualified (e.g. Sat.EarthMJ2000Eq.INC).
    The MVP only guarantees Earth-centered GMAT demos, but this helper keeps
    the mapping readable and extensible.
    """
    if frame.endswith("MJ2000Eq"):
        return frame[: -len("MJ2000Eq")] or "Earth"
    if frame.startswith("Earth"):
        return "Earth"
    if frame.startswith("Luna"):
        return "Luna"
    if frame.startswith("Mars"):
        return "Mars"
    if frame.startswith("Sun") or frame.startswith("Heliocentric"):
        return "Sun"
    return "Earth"


def _keplerian_angle_frame(frame: str) -> str:
    """Return a GMAT coordinate system valid for INC/RAAN/AOP reports."""
    gf = gmat_frame(frame)
    if gf.endswith("MJ2000Eq") or gf.endswith("MJ2000Ec"):
        return gf
    return f"{_origin_from_gmat_frame(gf)}MJ2000Eq"


def _normalize_spacecraft_parameter(spacecraft_name: str, parameter: str, default_frame: str | None = None) -> str:
    """Normalize a spacecraft-relative GMAT parameter expression.

    Users may provide arbitrary GMAT parameters in mission_spec.json.  We pass
    unknown parameters through after prefixing the spacecraft name.  For the
    common Keplerian shorthand, fix the origin/frame qualifier split that GMAT
    requires for script parsing.
    """
    parameter = parameter.strip()
    if parameter.startswith(f"{spacecraft_name}."):
        suffix = parameter[len(spacecraft_name) + 1:]
    else:
        suffix = parameter

    parts = suffix.split(".")
    if len(parts) == 2:
        qualifier, field = parts
        field_u = field.upper()
        origin = _origin_from_gmat_frame(qualifier)
        if field_u in {"SMA", "ECC", "TA", "C3ENERGY", "ALTITUDE"}:
            return f"{spacecraft_name}.{origin}.{field}"
        if field_u in {"INC", "RAAN", "AOP"}:
            return f"{spacecraft_name}.{qualifier}.{field}"
        return f"{spacecraft_name}.{qualifier}.{field}"

    if len(parts) == 1:
        field = parts[0]
        field_u = field.upper()
        if default_frame and field_u in {"X", "Y", "Z", "VX", "VY", "VZ", "INC", "RAAN", "AOP"}:
            return f"{spacecraft_name}.{default_frame}.{field}"
        if default_frame and field_u in {"SMA", "ECC", "TA", "C3ENERGY", "ALTITUDE"}:
            return f"{spacecraft_name}.{_origin_from_gmat_frame(default_frame)}.{field}"
        return f"{spacecraft_name}.{field}"

    return f"{spacecraft_name}.{suffix}"

def _resolve_param(spacecraft_name: str, parameter: str, default_frame: str | None = None) -> str:
    """Return a GMAT parameter expression.

    MissionSpec accepts fully-qualified GMAT parameter names such as
    ``SSOSat.EarthMJ2000Eq.X`` and spacecraft-relative names such as
    ``EarthMJ2000Eq.X`` / ``ElapsedSecs``. Unknown fields are still forwarded
    so GMAT remains the source of truth, but common Keplerian shorthand is
    normalized into GMAT's required Origin-vs-CoordinateSystem qualifiers.
    """
    return _normalize_spacecraft_parameter(spacecraft_name, parameter, default_frame)


def _expand_parameters(sc: dict, frame: str, groups: list[str], parameters: list[str] | None, fields: list[str] | None) -> list[str]:
    gf = gmat_frame(frame)
    params: list[str] = []
    if "elapsed_time" in groups:
        params.extend(f"{sc['name']}.{field}" for field in ELAPSED_TIME_FIELDS)
    origin = _origin_from_gmat_frame(gf)
    if "cartesian" in groups:
        params.extend(f"{sc['name']}.{gf}.{field}" for field in CARTESIAN_FIELDS)
    if "keplerian" in groups:
        # GMAT's report parameter qualifiers are mixed for Keplerian elements.
        # See GMAT API ParameterInfo: SMA/ECC/TA use Origin; INC/RAAN/AOP use CoordinateSystem.
        angle_frame = _keplerian_angle_frame(gf)
        params.extend([
            f"{sc['name']}.{origin}.SMA",
            f"{sc['name']}.{origin}.ECC",
            f"{sc['name']}.{angle_frame}.INC",
            f"{sc['name']}.{angle_frame}.RAAN",
            f"{sc['name']}.{angle_frame}.AOP",
            f"{sc['name']}.{origin}.TA",
        ])
    if "mass" in groups:
        params.extend(f"{sc['name']}.{field}" for field in MASS_FIELDS)
    for item in (parameters or []) + (fields or []):
        params.append(_resolve_param(sc["name"], item, gf))
    return list(dict.fromkeys(params))


def output_reports(spec: dict, out_dir: str | Path | None = None) -> list[dict]:
    """Expand MissionSpec continuous/full-output requests into GMAT ReportFiles."""
    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    reports: list[dict] = []
    base = Path(out_dir).resolve() if out_dir is not None else None
    for out in spec.get("outputs", []):
        if out.get("type") == "final_state" or out.get("enabled", True) is False:
            continue
        if out.get("type") not in {"state_history", "spacecraft_ephemeris", "full_ephemeris", "ground_track"}:
            continue
        sc = spacecraft_by_id[out["spacecraft"]]
        if out.get("type") == "ground_track":
            body = out.get("body", "Earth")
            params = [
                f"{sc['name']}.UTCGregorian",
                f"{sc['name']}.ElapsedSecs",
                f"{sc['name']}.{body}.Latitude",
                f"{sc['name']}.{body}.Longitude",
                f"{sc['name']}.{body}.Altitude",
            ]
            for item in (out.get("parameters") or []) + (out.get("fields") or []):
                params.append(_resolve_param(sc["name"], item, gmat_frame(sc["frame"])))
            relative_path = (out.get("path") or "outputs/_GroundTrack_{spacecraft}_{body}.csv").format(
                mission_id=spec["mission_id"],
                spacecraft=sc["name"],
                spacecraft_id=sc["id"],
                body=_safe_name(str(body)),
                output_id=_safe_name(out.get("id", "ground_track")),
            )
            reports.append({
                "name": _safe_name(f"RF_{sc['name']}_{body}_{out.get('id', 'ground_track')}_{len(reports)+1}"),
                "kind": "ground_track",
                "spacecraft_id": sc["id"],
                "spacecraft_name": sc["name"],
                "frame": f"{body}Fixed",
                "body": body,
                "path": relative_path,
                "script_path": _script_report_path(Path(relative_path), relative_path),
                "source_filename": Path(relative_path).name,
                "desired_path": str(Path(relative_path)).replace("\\", "/"),
                "parameters": list(dict.fromkeys(params)),
                "include_header": out.get("include_header", True),
                "output_id": _safe_name(out.get("id", out.get("type", "output"))),
                "segment_by_step": False,
                "segment_path_template": out.get("segment_path_template", ""),
            })
            continue
        frames = out.get("frames") or [sc["frame"]]
        groups = out.get("state_groups") or []
        if out.get("type") in {"state_history", "spacecraft_ephemeris"} and not groups and not out.get("parameters"):
            groups = ["elapsed_time", "cartesian"]
        # Honor explicit path for every continuous output type. If omitted,
        # use a template so one output can expand across multiple frames.
        path_template = out.get("path") or out.get(
            "path_template", "outputs/_Ephemeris_{spacecraft}_{frame}.csv"
        )
        for frame in frames:
            gf = gmat_frame(frame)
            params = _expand_parameters(sc, gf, groups, out.get("parameters"), out.get("fields"))
            if not params:
                continue
            relative_path = path_template.format(
                mission_id=spec["mission_id"],
                spacecraft=sc["name"],
                spacecraft_id=sc["id"],
                frame=gf,
                frame_id=_safe_name(frame),
                output_id=_safe_name(out.get("id", out.get("type", "output"))),
            )
            reports.append({
                "name": _safe_name(f"RF_{sc['name']}_{gf}_{out.get('id', out.get('type'))}_{len(reports)+1}"),
                "kind": "continuous",
                "spacecraft_id": sc["id"],
                "spacecraft_name": sc["name"],
                "frame": gf,
                "path": relative_path,
                "script_path": _script_report_path(Path(relative_path), relative_path),
                "source_filename": Path(relative_path).name,
                "desired_path": str(Path(relative_path)).replace("\\", "/"),
                "parameters": params,
                "include_header": out.get("include_header", True),
                "output_id": _safe_name(out.get("id", out.get("type", "output"))),
                "segment_by_step": bool(out.get("segment_by_step", False)),
                "segment_path_template": out.get(
                    "segment_path_template",
                    "outputs/segments/{phase_id}_{step_id}_{spacecraft}_{frame}.csv",
                ),
            })
    return reports


def _force_model_bodies(spec: dict) -> list[str]:
    bodies: list[str] = []
    for fm in spec.get("force_models", []) or []:
        candidates = [fm.get("central_body")]
        candidates.extend(fm.get("point_masses") or [])
        candidates.extend((fm.get("third_body_gravity", {}) or {}).get("bodies") or [])
        for body in candidates:
            if body and body not in bodies:
                bodies.append(body)
    return bodies


def _visualization_frames(spec: dict) -> list[str]:
    frames: list[str] = []
    for out in spec.get("outputs", []) or []:
        if out.get("enabled", True) is False:
            continue
        if out.get("type") in {"spacecraft_ephemeris", "state_history", "full_ephemeris"}:
            for frame in out.get("frames", []) or []:
                resolved = gmat_frame(frame)
                if resolved and resolved not in frames:
                    frames.append(resolved)
    for sc in spec.get("spacecraft", []) or []:
        frame = gmat_frame(sc.get("frame"))
        if frame and frame not in frames:
            frames.append(frame)
    return frames


def _frame_origin(spec: dict, frame: str | None) -> str | None:
    if not frame:
        return None
    for declared in spec.get("reference_frames", []) or []:
        if declared.get("name") == frame or declared.get("id") == frame:
            return declared.get("origin")
    return _origin_from_gmat_frame(str(frame))


def _body_ephemeris_entries(spec: dict) -> list[dict]:
    entries: list[dict] = []
    for out in spec.get("outputs", []) or []:
        if out.get("enabled", True) is False:
            continue
        if out.get("type") == "body_ephemeris":
            entries.append(out)
        elif out.get("type") == "body_ephemeris_group":
            template = out.get("path_template") or "outputs/_BodyEphemeris_{body}_{frame}.csv"
            for body in out.get("bodies", []) or []:
                item = dict(out)
                item["body"] = body
                item["path"] = template.format(body=_safe_name(str(body)), frame=_safe_name(str(out.get("frame", "J2000"))))
                entries.append(item)

    for frame in _visualization_frames(spec):
        origin = _frame_origin(spec, frame)
        for body in _force_model_bodies(spec):
            if body == origin:
                continue
            entries.append({
                "id": f"force_model_{_safe_name(str(body))}_{_safe_name(str(frame))}_ephemeris",
                "type": "body_ephemeris",
                "body": body,
                "frame": frame,
                "source": "gmat",
                "path": f"outputs/_BodyEphemeris_{_safe_name(str(body))}_{_safe_name(str(frame))}.csv",
                "auto_generated": True,
                "reason": "force_model_body",
            })
    return entries


def body_ephemeris_reports(spec: dict, out_dir: str | Path | None = None) -> list[dict]:
    """Build GMAT ReportFile fallback outputs for body ephemerides.

    SPICE remains the preferred source when resolved dependency JSON is
    available.  This fallback asks GMAT to emit body states on the same runtime
    report grid so the viewer still receives _BodyEphemeris files when spiceypy
    or local kernels are unavailable.  The timestamp columns come from the
    first spacecraft because GMAT ReportFile publication is mission-command
    driven.
    """
    spacecraft = spec.get("spacecraft", []) or []
    if not spacecraft:
        return []
    time_sc = spacecraft[0]
    base = Path(out_dir).resolve() if out_dir is not None else None
    reports: list[dict] = []
    entries = _body_ephemeris_entries(spec)
    seen: set[tuple[str, str]] = set()
    deduped_entries: list[dict] = []
    for entry in entries:
        body = str(entry.get("body") or entry.get("target") or "")
        frame = gmat_frame(entry.get("frame") or time_sc.get("frame") or "EarthMJ2000Eq")
        key = (body, frame)
        if key in seen:
            continue
        seen.add(key)
        deduped_entries.append(entry)
    for entry in deduped_entries:
        body = entry.get("body") or entry.get("target")
        frame = gmat_frame(entry.get("frame") or time_sc.get("frame") or "EarthMJ2000Eq")
        if not body:
            continue
        relative_path = entry.get("path") or f"outputs/_BodyEphemeris_{_safe_name(str(body))}_{_safe_name(frame)}.csv"
        # Time columns are spacecraft-based; body columns are GMAT SpacePoint state parameters.
        params = [
            f"{time_sc['name']}.UTCGregorian",
            f"{time_sc['name']}.ElapsedSecs",
            f"{time_sc['name']}.A1ModJulian",
            f"{body}.{frame}.X",
            f"{body}.{frame}.Y",
            f"{body}.{frame}.Z",
            f"{body}.{frame}.VX",
            f"{body}.{frame}.VY",
            f"{body}.{frame}.VZ",
        ]
        source = "gmat_reportfile" if entry.get("source") == "gmat" else "gmat_reportfile_fallback"
        reports.append({
            "name": _safe_name(f"BRF_{body}_{frame}_{entry.get('id', 'body_ephemeris')}_{len(reports)+1}"),
            "kind": "body_ephemeris",
            "body": body,
            "frame": frame,
            "path": relative_path,
            "script_path": _script_report_path(Path(relative_path), relative_path),
            "source_filename": Path(relative_path).name,
            "desired_path": str(Path(relative_path)).replace("\\", "/"),
            "parameters": params,
            "include_header": entry.get("include_header", True),
            "source": source,
            "dependency_id": entry.get("dependency_id"),
            "auto_generated": entry.get("auto_generated", False),
        })
    return reports


def stm_artifacts(spec: dict, out_dir: str | Path | None = None) -> list[dict]:
    """Return STM artifact requests declared by MissionSpec targeting policy.

    GMAT STM parameter names vary by build/plugin configuration, so AMAT keeps
    the default as an explicit artifact contract. If a MissionSpec supplies
    backend-validated ``parameters``, the native script emits a ReportFile for
    those parameters; otherwise the generated artifacts record what the STM
    correction loop expects a GMAT-side integration to provide.
    """
    targeting = spec.get("targeting", {}) or {}
    stm = targeting.get("stm", {}) or {}
    if not stm.get("enabled", False):
        return []

    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    sc_id = stm.get("spacecraft") or (spec.get("spacecraft", [{}])[0].get("id") if spec.get("spacecraft") else None)
    if not sc_id or sc_id not in spacecraft_by_id:
        raise ValueError("targeting.stm.spacecraft must reference a spacecraft id")
    sc = spacecraft_by_id[sc_id]
    frame = gmat_frame(stm.get("frame") or sc.get("frame", "EarthMJ2000Eq"))
    relative_path = stm.get("path", "outputs/stm_state_transition_matrix.csv")
    parameters = [_resolve_param(sc["name"], item, frame) for item in stm.get("parameters", []) or []]
    return [{
        "id": _safe_name(stm.get("id", "stm")),
        "name": _safe_name(f"RF_{sc['name']}_STM"),
        "kind": "stm",
        "mode": stm.get("mode", "artifact_contract"),
        "spacecraft_id": sc_id,
        "spacecraft_name": sc["name"],
        "frame": frame,
        "path": relative_path,
        "script_path": _script_report_path(Path(relative_path), relative_path),
        "source_filename": Path(relative_path).name,
        "desired_path": str(Path(relative_path)).replace("\\", "/"),
        "parameters": parameters,
        "include_header": stm.get("include_header", True),
        "state_vector": stm.get("state_vector", ["X", "Y", "Z", "VX", "VY", "VZ"]),
        "decision_variables": stm.get("decision_variables", []),
        "notes": stm.get("notes", []),
        "has_native_report": bool(parameters),
    }]


def propagation_segments(spec: dict) -> list[dict]:
    """Return deterministic elapsed-time intervals for propagate steps.

    GMAT ReportFile subscribers are active for the whole mission.  Per-step
    trajectory files are therefore derived after the run by slicing the native
    full-history report using the elapsed-time intervals of propagate steps.
    Maneuvers/checkpoints are instantaneous for this MVP and do not create
    trajectory segments.
    """
    elapsed_by_sc: dict[str, float] = {sc["id"]: 0.0 for sc in spec.get("spacecraft", [])}
    segments: list[dict] = []
    for phase, step, step_index in iter_steps(spec):
        if step.get("type") != "propagate":
            continue
        sc_id = step["spacecraft"]
        start_s = float(elapsed_by_sc.get(sc_id, 0.0))
        duration_s = float(step["duration_s"])
        end_s = start_s + duration_s
        elapsed_by_sc[sc_id] = end_s
        segments.append({
            "phase_id": _safe_name(phase.get("phase_id", f"phase_{step_index}")),
            "phase_name": phase.get("name", ""),
            "step_id": _safe_name(step.get("step_id", f"step_{step_index}")),
            "step_index": step_index,
            "spacecraft_id": sc_id,
            "propagator": step.get("propagator"),
            "start_elapsed_s": start_s,
            "end_elapsed_s": end_s,
            "duration_s": duration_s,
        })
    return segments


def derived_segment_reports(spec: dict, reports: list[dict], out_dir: str | Path | None = None) -> list[dict]:
    """Build derived per-propagate-step trajectory output descriptors.

    These are not GMAT ReportFiles.  They are created after GMAT finishes by
    slicing the copied mission-wide report.
    """
    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    base = Path(out_dir).resolve() if out_dir is not None else None
    derived: list[dict] = []
    segments = propagation_segments(spec)
    for report in reports:
        if not report.get("segment_by_step"):
            continue
        for segment in segments:
            if segment["spacecraft_id"] != report["spacecraft_id"]:
                continue
            sc = spacecraft_by_id[segment["spacecraft_id"]]
            rel = report["segment_path_template"].format(
                mission_id=spec["mission_id"],
                output_id=report.get("output_id", "output"),
                phase_id=segment["phase_id"],
                step_id=segment["step_id"],
                step_index=segment["step_index"],
                spacecraft=sc["name"],
                spacecraft_id=sc["id"],
                frame=report["frame"],
                frame_id=_safe_name(report["frame"]),
            )
            derived.append({
                "name": _safe_name(f"SEG_{report['name']}_{segment['step_id']}"),
                "kind": "derived_segment",
                "path": rel,
                "desired_path": str(Path(rel)).replace("\\", "/"),
                "source_path": report["desired_path"],
                "source_filename": report["source_filename"],
                "spacecraft_id": report["spacecraft_id"],
                "spacecraft_name": report["spacecraft_name"],
                "frame": report["frame"],
                **segment,
            })
    return derived


def event_descriptors(spec: dict) -> list[dict]:
    """Return GMAT-ready event definitions.

    Event-based actions are represented as a Propagate-to-event command
    followed by an ordered action list. Supported event types:

    - parameter_reaches: explicit GMAT parameter/value stop condition.
    - orbital_event: periapsis or apoapsis alias, compiled to body true anomaly.
      Periapsis is valid for elliptic and hyperbolic trajectories; apoapsis is
      validated as elliptic-only when the current orbit regime is known.
    - node_crossing: stop at Z=0 in the requested reference frame. Direction
      filtering for ascending/descending/both is marked in metadata but is not
      enforced by the GMAT script backend yet.

    SOI/distance-threshold events are intentionally deferred.
    """
    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    out: list[dict] = []
    for ev in spec.get("events", []):
        sc = spacecraft_by_id[ev["spacecraft"]]
        sc_name = sc["name"]
        default_frame = gmat_frame(sc.get("frame", "EarthMJ2000Eq"))
        event_type = ev.get("type")
        notes: list[str] = []

        if event_type == "parameter_reaches":
            stop = ev.get("stop_condition", {})
            stop_parameter = _resolve_param(sc_name, stop.get("parameter", "ElapsedSecs"), default_frame)
            stop_value = stop.get("value")

        elif event_type == "orbital_event":
            central_body = ev.get("central_body") or _origin_from_gmat_frame(default_frame)
            orbital_event = ev.get("event")
            if orbital_event == "periapsis":
                stop_parameter = f"{sc_name}.{central_body}.TA"
                stop_value = 0
            elif orbital_event == "apoapsis":
                stop_parameter = f"{sc_name}.{central_body}.TA"
                stop_value = 180
            else:
                raise ValueError(f"Unsupported orbital_event alias: {orbital_event!r}")
            notes.append(f"orbital_event:{orbital_event}; compiled_as:true_anomaly")

        elif event_type == "node_crossing":
            reference_frame = gmat_frame(ev.get("reference_frame") or default_frame)
            stop_parameter = f"{sc_name}.{reference_frame}.Z"
            stop_value = 0
            node = ev.get("node", "either")
            if node in {"ascending", "descending", "both"}:
                notes.append("node_direction_not_enforced_by_gmat_backend")
            notes.append(f"node:{node}; compiled_as:Z_equals_zero")

        else:
            raise ValueError(f"Unsupported event type: {event_type!r}")

        out.append({
            **ev,
            "spacecraft_name": sc_name,
            "stop_parameter": stop_parameter,
            "stop_value": stop_value,
            "compile_notes": notes,
        })
    return out


def _angle_close_deg(a: float | int | None, b: float | int | None, tolerance: float = 1.0e-9) -> bool:
    if a is None or b is None:
        return False
    delta = (float(a) - float(b) + 180.0) % 360.0 - 180.0
    return abs(delta) <= tolerance


def zero_distance_event_action_steps(spec: dict) -> set[int]:
    """Return event-action step indices whose GMAT Propagate would have zero distance.

    GMAT can fail on a Propagate-to-event command when the stop condition is
    already satisfied at the start of the command, for example TA=0 at an
    initial periapsis.  AMAT treats those as immediate event hits: the event
    actions are still emitted, but the zero-distance Propagate command is not.

    This is intentionally conservative.  It only skips events whose current
    state is known from the MissionSpec sequence model.
    """
    events = {event["id"]: event for event in event_descriptors(spec)}
    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    state: dict[str, dict[str, float | None]] = {}
    for sc_id, sc in spacecraft_by_id.items():
        state[sc_id] = {
            "ta_deg": float(sc["ta_deg"]) if sc.get("state_type") == "keplerian" and sc.get("ta_deg") is not None else None,
            "elapsed_s": 0.0,
        }

    zero_steps: set[int] = set()
    for _, step, step_index in iter_steps(spec):
        stype = step.get("type")
        if stype == "propagate":
            sc_state = state.get(step.get("spacecraft"))
            if sc_state is not None:
                if sc_state.get("elapsed_s") is not None:
                    sc_state["elapsed_s"] = float(sc_state["elapsed_s"]) + float(step.get("duration_s", 0.0))
                sc_state["ta_deg"] = None
            continue

        if stype == "maneuver":
            sc_state = state.get(step.get("spacecraft"))
            if sc_state is not None:
                sc_state["ta_deg"] = None
            continue

        if stype != "event_action":
            continue

        event = events.get(step.get("event_id"))
        if not event:
            continue
        sc_state = state.get(event.get("spacecraft"))
        if sc_state is None:
            continue

        event_type = event.get("type")
        is_zero_distance = False
        if event_type == "orbital_event":
            is_zero_distance = _angle_close_deg(sc_state.get("ta_deg"), event.get("stop_value"))
            if not is_zero_distance:
                sc_state["ta_deg"] = float(event["stop_value"])
        elif event_type == "parameter_reaches":
            stop_parameter = str(event.get("stop_parameter", ""))
            if stop_parameter.endswith(".ElapsedSecs") and sc_state.get("elapsed_s") is not None:
                is_zero_distance = abs(float(sc_state["elapsed_s"]) - float(event.get("stop_value", 0.0))) <= 1.0e-9
                if not is_zero_distance:
                    sc_state["elapsed_s"] = float(event.get("stop_value", sc_state["elapsed_s"]))
                    sc_state["ta_deg"] = None

        if is_zero_distance:
            zero_steps.add(step_index)

        for action in event.get("actions", []) or []:
            if action.get("type") != "maneuver":
                continue
            action_state = state.get(action.get("spacecraft"))
            if action_state is None:
                continue
            action_state["ta_deg"] = None
            if action.get("duration_s") is not None and action_state.get("elapsed_s") is not None:
                action_state["elapsed_s"] = float(action_state["elapsed_s"]) + float(action.get("duration_s", 0.0))

    return zero_steps


def checkpoint_reports(spec: dict, out_dir: str | Path | None = None) -> list[dict]:
    """Expand sparse checkpoint and event report requests into ReportFile descriptors.

    Checkpoint ReportFiles are not active subscribers. They are written by
    explicit GMAT Report commands placed either as checkpoint steps or as
    event actions immediately after a Propagate-to-event command.
    """
    spacecraft_by_id = {sc["id"]: sc for sc in spec.get("spacecraft", [])}
    cp_defs = {cp["id"]: cp for cp in spec.get("checkpoints", []) if cp.get("enabled", True) is not False}
    base = Path(out_dir).resolve() if out_dir is not None else None
    checkpoints: list[dict] = []
    added: set[tuple[str, int, str | None]] = set()

    def build(cp: dict, step_index: int, placement_id: str, *, event_id: str | None = None, action_id: str | None = None) -> None:
        sc = spacecraft_by_id[cp["spacecraft"]]
        frame = gmat_frame(cp.get("frame") or sc["frame"])
        groups = cp.get("state_groups") or []
        params = _expand_parameters(sc, frame, groups, cp.get("parameters"), cp.get("fields"))
        timestamp_params = [
            f"{sc['name']}.UTCGregorian",
            f"{sc['name']}.ElapsedSecs",
        ]
        params = timestamp_params + [p for p in params if p not in timestamp_params]
        if not params:
            return
        cp_id = _safe_name(cp.get("id", placement_id))
        relative_path = cp.get("path", f"outputs/{cp_id}.csv").format(
            mission_id=spec["mission_id"],
            spacecraft=sc["name"],
            spacecraft_id=sc["id"],
            checkpoint_id=cp_id,
            event_id=_safe_name(event_id or ""),
            action_id=_safe_name(action_id or ""),
            frame=frame,
        )
        checkpoints.append({
            "id": cp_id,
            "name": _safe_name(f"RF_{cp_id}_{action_id}" if action_id else f"RF_{cp_id}"),
            "kind": "checkpoint",
            "after_step_index": step_index,
            "event_id": event_id,
            "action_id": action_id,
            "spacecraft_id": sc["id"],
            "spacecraft_name": sc["name"],
            "frame": frame,
            "path": relative_path,
            "script_path": _script_report_path(Path(relative_path), relative_path),
            "source_filename": Path(relative_path).name,
            "desired_path": str(Path(relative_path)).replace("\\", "/"),
            "parameters": params,
            "include_header": cp.get("include_header", True),
        })

    # Explicit checkpoint steps.
    for phase, step, step_index in iter_steps(spec):
        if step.get("type") == "checkpoint":
            cp_id = step["checkpoint_id"]
            cp = cp_defs.get(cp_id)
            if cp is None:
                continue
            key = (cp_id, step_index, None)
            if key not in added:
                added.add(key)
                build(cp, step_index, step.get("step_id", cp_id))
        elif step.get("type") == "event_action":
            ev = next((x for x in spec.get("events", []) if x.get("id") == step["event_id"]), None)
            if not ev:
                continue
            for action in ev.get("actions", []):
                atype = action.get("type")
                action_id = action.get("action_id")
                if atype == "checkpoint":
                    cp_id = action["checkpoint_id"]
                    cp = cp_defs.get(cp_id)
                    if cp is None:
                        continue
                    key = (cp_id, step_index, action_id)
                    if key not in added:
                        added.add(key)
                        build(cp, step_index, action_id or cp_id, event_id=ev["id"], action_id=action_id)
                elif atype == "report":
                    report_cp = {
                        "id": action_id,
                        "enabled": True,
                        "spacecraft": action["spacecraft"],
                        "frame": action.get("frame"),
                        "path": action["path"],
                        "parameters": action.get("parameters", []),
                        "fields": action.get("fields", []),
                        "state_groups": action.get("state_groups", []),
                        "include_header": action.get("include_header", True),
                    }
                    key = (action_id, step_index, action_id)
                    if key not in added:
                        added.add(key)
                        build(report_cp, step_index, action_id, event_id=ev["id"], action_id=action_id)

    # Backward compatibility: old checkpoints with after_command_index still work.
    for cp_id, cp in cp_defs.items():
        if "after_command_index" in cp:
            key = (cp_id, int(cp["after_command_index"]), None)
            if key not in added:
                added.add(key)
                build(cp, int(cp["after_command_index"]), cp_id)
    return checkpoints


class GmatCompiler:
    backend_id = "gmat"

    def __init__(self) -> None:
        base = Path(files("compiler.backends.gmat"))
        self.capability = read_json(base / "capability.json")
        self.env = Environment(
            loader=FileSystemLoader(base / "templates"),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["gmat_frame"] = gmat_frame
        self.env.globals["output_reports"] = output_reports
        self.env.globals["checkpoint_reports"] = checkpoint_reports
        self.env.globals["derived_segment_reports"] = derived_segment_reports
        self.env.globals["coordinate_systems_for_gmat"] = coordinate_systems_for_gmat
        self.env.globals["event_descriptors"] = event_descriptors
        self.env.globals["body_ephemeris_reports"] = body_ephemeris_reports
        self.env.globals["stm_artifacts"] = stm_artifacts
        self.env.globals["burn_descriptors"] = burn_descriptors
        self.env.globals["zero_distance_event_action_steps"] = zero_distance_event_action_steps
        self.env.globals["spacecraft_thrusters"] = spacecraft_thrusters
        self.env.globals["spacecraft_tanks"] = spacecraft_tanks
        self.env.globals["gmat_epoch"] = lambda value: format_epoch_for_backend(value, "gmat")

    def validate_capability(self, spec: dict) -> list[dict]:
        return check_capability(spec, self.capability)

    def _context(self, spec: dict, out_dir: str | Path | None = None) -> dict:
        reports = output_reports(spec, out_dir)
        body_reports = body_ephemeris_reports(spec, out_dir)
        checkpoints = checkpoint_reports(spec, out_dir)
        stm_outputs = stm_artifacts(spec, out_dir)
        events = event_descriptors(spec)
        # Per-step trajectory slicing is intentionally disabled. GMAT native
        # ReportFile subscribers are mission-wide; checkpoint snapshots are the
        # supported way to inspect state at exact mission-sequence moments.
        derived_segments: list[dict] = []
        spice_requests = build_spice_requests(spec, out_dir)
        spice_kernel_sets = build_spice_kernel_sets(spec)
        return {
            "spec": spec,
            "burns": burn_descriptors(spec),
            "burns_by_id": {burn["id"]: burn for burn in burn_descriptors(spec)},
            "spacecraft_thrusters_by_id": spacecraft_thrusters(spec),
            "spacecraft_tanks_by_id": spacecraft_tanks(spec),
            "spice_requests": spice_requests,
            "spice_kernel_sets": spice_kernel_sets,
            "coordinate_systems": coordinate_systems_for_gmat(spec, reports + stm_outputs, checkpoints),
            "phases": normalize_mission_sequence(spec),
            "events": events,
            "events_by_id": {event["id"]: event for event in events},
            "zero_distance_event_steps": zero_distance_event_action_steps(spec),
            "reports": reports,
            "body_reports": body_reports,
            "checkpoints": checkpoints,
            "stm_outputs": stm_outputs,
            "derived_segments": derived_segments,
            "expected_outputs": reports + body_reports + checkpoints + stm_outputs,
            "report_copies": reports + body_reports + checkpoints + [item for item in stm_outputs if item.get("has_native_report")],
            "requires_script_replay": bool(
                reports
                or body_reports
                or checkpoints
                or stm_outputs
                or spec.get("burns", [])
                or spec.get("events", [])
                or spice_kernel_sets
                or any(fm.get("point_masses") or fm.get("gravity", {}).get("type") == "spherical_harmonic" for fm in spec.get("force_models", []))
            ),
        }

    def render_python(self, spec: dict, out_dir: str | Path | None = None) -> str:
        return self.env.get_template("gmatpyplus_mission.py.j2").render(**self._context(spec, out_dir))

    def render_gmat_script(self, spec: dict, out_dir: str | Path | None = None) -> str:
        return self.env.get_template("gmat_native.script.j2").render(**self._context(spec, out_dir))

    def compile(self, spec: dict, out_dir: str | Path) -> dict:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "outputs").mkdir(exist_ok=True)
        py_path = out_dir / "generated_mission.py"
        script_path = out_dir / "generated_mission.script"
        write_text(py_path, self.render_python(spec, out_dir))
        write_text(script_path, self.render_gmat_script(spec, out_dir))
        artifacts = [
            {"artifact_id": "PYTHON_SCRIPT", "type": "python_script", "path": py_path.name, "hash": hash_file(py_path), "language": "python", "backend": "gmat"},
            {"artifact_id": "GMAT_SCRIPT", "type": "native_script", "path": script_path.name, "hash": hash_file(script_path), "language": "gmat_script", "backend": "gmat"},
        ]
        spice_requests = write_spice_requests(spec, out_dir)
        spice_request_path = out_dir / "dependencies" / "spice_requests.json"
        if spice_requests and spice_request_path.exists():
            artifacts.append({
                "artifact_id": "SPICE_REQUESTS",
                "type": "spice_requests",
                "path": "dependencies/spice_requests.json",
                "hash": hash_file(spice_request_path),
                "language": "json",
                "backend": "spice",
            })
        reports = output_reports(spec, out_dir)
        body_reports = body_ephemeris_reports(spec, out_dir)
        checkpoints = checkpoint_reports(spec, out_dir)
        stm_outputs = stm_artifacts(spec, out_dir)
        derived_segments: list[dict] = []
        for report in reports + body_reports + checkpoints + [item for item in stm_outputs if item.get("has_native_report")]:
            artifacts.append({
                "artifact_id": f"REPORT_{report['name']}",
                "type": "expected_output",
                "path": report["path"],
                "language": "csv",
                "backend": "gmat",
            })
        if stm_outputs:
            contract_path = out_dir / "targeting" / "stm_artifact_contract.json"
            contract_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(contract_path, {
                "schema_version": "1.0.0",
                "mission_id": spec["mission_id"],
                "artifacts": stm_outputs,
                "consumer": "targeter.solve_stm_target_state_correction",
            })
            artifacts.append({
                "artifact_id": "STM_ARTIFACT_CONTRACT",
                "type": "stm_artifact_contract",
                "path": "targeting/stm_artifact_contract.json",
                "hash": hash_file(contract_path),
                "language": "json",
                "backend": "gmat",
            })
        # Viewer-facing metadata is generated at compile time. Runtime can later
        # normalize CSVs and export SPICE-derived body ephemerides into the same
        # manifest shape.
        visualization_manifest = write_visualization_manifest(spec, out_dir, reports, checkpoints)
        viz_path = out_dir / "visualization_manifest.json"
        artifacts.append({
            "artifact_id": "VISUALIZATION_MANIFEST",
            "type": "visualization_manifest",
            "path": "visualization_manifest.json",
            "hash": hash_file(viz_path),
            "language": "json",
            "backend": "simulation_layer",
        })
        for body_out in visualization_manifest.get("body_ephemerides", []):
            artifacts.append({
                "artifact_id": f"BODY_EPHEMERIS_{_safe_name(str(body_out.get('body')))}_{_safe_name(str(body_out.get('frame')))}",
                "type": "expected_body_ephemeris",
                "path": body_out.get("file"),
                "language": "csv",
                "backend": body_out.get("source", "spice"),
            })
        return {
            "schema_version": "1.0.0",
            "mission_id": spec["mission_id"],
            "backend_id": self.backend_id,
            "status": "success",
            "generated_artifacts": artifacts,
            "warnings": (["SPICE dependency requests were generated. Kernel metadata is included in generated GMAT scripts as reproducibility comments; GMAT execution consumes built-in GMAT bodies directly unless explicit backend overrides are validated."] if spice_requests else []),
            "errors": [],
        }


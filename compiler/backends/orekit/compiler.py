from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from compiler.hashing import hash_file
from compiler.io import write_text
from compiler.ir.sequence import iter_steps
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


def _frame_declarations(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    frames: dict[str, dict[str, Any]] = {}
    for frame in spec.get("reference_frames", []) or []:
        name = frame.get("name")
        if name:
            frames[str(name)] = frame
        frame_id = frame.get("id")
        if frame_id:
            frames.setdefault(str(frame_id), frame)
    return frames


def _body_from_fixed_frame_name(frame: str) -> str | None:
    suffix = "Fixed"
    if not frame.endswith(suffix):
        return None
    body = frame[: -len(suffix)]
    return body or None


def _frame_output_fallback(spec: dict[str, Any], frame: str) -> dict[str, Any] | None:
    if frame in SUPPORTED_FRAMES:
        return None
    declared = _frame_declarations(spec).get(frame)
    body = None
    axes = None
    frame_type = None
    if declared:
        frame_type = declared.get("type")
        axes = declared.get("axes") or declared.get("orientation")
        body = declared.get("origin")
    body = body or _body_from_fixed_frame_name(frame)
    axes = axes or ("BodyFixed" if body else None)
    frame_type = frame_type or ("body_fixed" if body and axes in {"BodyFixed", "Fixed"} else None)
    if frame_type != "body_fixed" and axes not in {"BodyFixed", "Fixed"}:
        return None
    if body != "Earth":
        return None
    return {
        "mode": "frame_fallback",
        "kind": "body_fixed",
        "body": body,
        "radius_km": BODY_RADII_KM.get(body),
        "target_frame": frame,
        "axes": "BodyFixed",
    }


def _output_frame_entry(spec: dict[str, Any], sc: dict[str, Any], sc_id: str, frame: str, template: str) -> dict[str, Any] | None:
    path = str(template).format(spacecraft=sc.get("name") or sc_id, frame=frame)
    entry: dict[str, Any] = {"spacecraft": sc_id, "frame": frame, "path": path.replace("\\", "/")}
    fallback = _frame_output_fallback(spec, frame)
    if frame in SUPPORTED_FRAMES:
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


def _output_paths(spec: dict[str, Any]) -> list[dict[str, Any]]:
    outputs: list[dict[str, Any]] = []
    spacecraft = _spacecraft_by_id(spec)
    for out in spec.get("outputs", []) or []:
        if out.get("type") != "spacecraft_ephemeris":
            continue
        sc_id = out.get("spacecraft")
        sc = spacecraft.get(sc_id or "")
        if not sc:
            continue
        frames = out.get("frames") or [sc.get("frame", "EarthMJ2000Eq")]
        template = out.get("path_template") or "outputs/_Ephemeris_{spacecraft}_{frame}.csv"
        for frame in frames:
            entry = _output_frame_entry(spec, sc, str(sc_id), str(frame), str(template))
            if entry:
                outputs.append(entry)
    return outputs


def _ground_track_paths(spec: dict[str, Any]) -> list[dict[str, Any]]:
    tracks: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    spacecraft = _spacecraft_by_id(spec)

    def add_track(sc_id: str, sc: dict[str, Any], body: str, fallback: dict[str, Any] | None) -> None:
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
            }
        )

    for out in spec.get("outputs", []) or []:
        sc_id = str(out.get("spacecraft") or "")
        sc = spacecraft.get(sc_id)
        if not sc:
            continue
        if out.get("type") == "ground_track":
            add_track(sc_id, sc, str(out.get("body") or "Earth"), None)
            continue
        if out.get("type") != "spacecraft_ephemeris":
            continue
        for frame in out.get("frames") or [sc.get("frame", "EarthMJ2000Eq")]:
            fallback = _frame_output_fallback(spec, str(frame))
            if fallback and fallback.get("kind") == "body_fixed":
                add_track(sc_id, sc, str(fallback["body"]), fallback)
    return tracks


def _final_state_paths(spec: dict[str, Any]) -> list[dict[str, str]]:
    outputs: list[dict[str, str]] = []
    spacecraft = _spacecraft_by_id(spec)
    for out in spec.get("outputs", []) or []:
        if out.get("type") != "final_state":
            continue
        sc_id = out.get("spacecraft")
        sc = spacecraft.get(sc_id or "")
        if not sc:
            continue
        frame = str(out.get("frame") or sc.get("frame") or "EarthMJ2000Eq")
        if frame not in SUPPORTED_FRAMES:
            continue
        path = str(out.get("path") or f"outputs/final_state_{sc.get('name') or sc_id}.csv")
        outputs.append({"spacecraft": sc_id, "frame": frame, "path": path.replace("\\", "/")})
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
                    "duration_s": float(step.get("duration_s", 0.0)),
                    "central_body": (fm or {}).get("central_body", "Earth"),
                    "max_step_s": float((prop or {}).get("max_step_s") or 300.0),
                }
            )
        elif typ == "checkpoint":
            plan.append({"type": "checkpoint", "checkpoint_id": step.get("checkpoint_id")})
        elif typ == "maneuver":
            plan.append({"type": "maneuver", "spacecraft": step.get("spacecraft"), "burn": step.get("burn")})
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
        item["mu_km3_s2"] = MU_KM3_S2.get(item["central_body"], MU_KM3_S2["Earth"])
        spacecraft.append(item)
    return {
        "mission_id": spec["mission_id"],
        "spacecraft": spacecraft,
        "sequence": _sequence_plan(spec),
        "outputs": _output_paths(spec),
        "ground_tracks": _ground_track_paths(spec),
        "final_outputs": _final_state_paths(spec),
        "checkpoints": _checkpoint_paths(spec),
        "burns": _burns_by_id(spec),
        "events": _events_by_id(spec),
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
        force_models = _force_model_by_id(spec)
        propagators = _propagator_by_id(spec)

        for sc in spec.get("spacecraft", []) or []:
            if sc.get("frame") not in SUPPORTED_FRAMES:
                errors.append(f"Orekit backend currently supports inertial MJ2000/EME2000-like frames; got {sc.get('frame')} for {sc.get('id')}.")
            if sc.get("state_type") not in {"cartesian", "keplerian"}:
                errors.append(f"Orekit backend does not support state_type {sc.get('state_type')!r}.")

        for fm in force_models.values():
            gravity = fm.get("gravity", {}) or {}
            if gravity.get("type") not in {None, "point_mass", "two_body"}:
                errors.append(f"Orekit backend currently supports two-body point-mass gravity only; force model {fm.get('id')} requested {gravity.get('type')}.")
            third_body = fm.get("third_body_gravity", {}) or {}
            if third_body.get("enabled"):
                errors.append(f"Orekit backend does not yet support third-body gravity in force model {fm.get('id')}.")
            if fm.get("central_body") not in MU_KM3_S2:
                errors.append(f"Orekit backend has no built-in mu for central body {fm.get('central_body')!r}.")

        for prop in propagators.values():
            fm = force_models.get(prop.get("force_model", ""))
            if fm is None:
                errors.append(f"Orekit backend cannot resolve force model {prop.get('force_model')!r} for propagator {prop.get('id')}.")

        for burn in spec.get("burns", []) or []:
            if burn.get("type") != "impulsive":
                errors.append(f"Orekit backend does not yet support burn {burn.get('id')!r} of type {burn.get('type')!r}.")
            if burn.get("frame") not in {None, "VNB"}:
                errors.append(f"Orekit backend currently supports impulsive burns in VNB only; burn {burn.get('id')!r} requested {burn.get('frame')!r}.")
        for event in spec.get("events", []) or []:
            if event.get("type") == "parameter_reaches":
                parameter = (event.get("stop_condition", {}) or {}).get("parameter")
                if parameter not in {"ElapsedSecs", "Earth.ArgumentOfLatitude"}:
                    errors.append(f"Orekit backend does not yet support parameter event {event.get('id')!r} with parameter {parameter!r}.")
            elif event.get("type") == "orbital_event":
                if event.get("event") != "apoapsis":
                    errors.append(f"Orekit backend does not yet support orbital event {event.get('id')!r} with event {event.get('event')!r}.")
            else:
                errors.append(f"Orekit backend does not yet support event {event.get('id')!r} of type {event.get('type')!r}.")
        for _, step, _ in iter_steps(spec):
            if step.get("type") not in {"propagate", "checkpoint", "report", "event_action", "maneuver"}:
                errors.append(f"Orekit backend does not yet support mission sequence step {step.get('step_id') or step.get('type')!r} of type {step.get('type')!r}.")

        for out in spec.get("outputs", []) or []:
            if out.get("type") == "ground_track":
                warnings.append(f"Orekit backend will generate ground-track output {out.get('id')!r} from surface-fixed spacecraft states when available.")
            elif out.get("type") == "spacecraft_ephemeris":
                sc = _spacecraft_by_id(spec).get(out.get("spacecraft") or "")
                frames = out.get("frames", []) or ([sc.get("frame")] if sc else [])
                fallback_frames = [str(frame) for frame in frames if frame not in SUPPORTED_FRAMES and _frame_output_fallback(spec, str(frame))]
                unsupported = [str(frame) for frame in frames if frame not in SUPPORTED_FRAMES and not _frame_output_fallback(spec, str(frame))]
                if fallback_frames:
                    warnings.append(f"Orekit backend will synthesize spacecraft ephemeris frames through validated output fallback for output {out.get('id')!r}: {', '.join(fallback_frames)}.")
                if unsupported:
                    errors.append(f"Orekit backend cannot natively output spacecraft ephemeris frames and no validated fallback is available for output {out.get('id')!r}: {', '.join(unsupported)}.")
            elif out.get("type") != "final_state":
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
        viz_manifest = write_visualization_manifest(spec, out_dir, reports=_output_reports(spec) + _ground_track_reports(spec), checkpoints=_checkpoint_reports(spec))
        viz_path = out_dir / "visualization_manifest.json"
        return {
            "schema_version": "1.0.0",
            "mission_id": spec.get("mission_id", "UNKNOWN"),
            "backend_id": self.backend_id,
            "status": "success",
            "generated_artifacts": [
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
                }
            ],
            "manifest_counts": {
                "spacecraft_ephemerides": len(viz_manifest.get("spacecraft_ephemerides", [])),
                "body_ephemerides": len(viz_manifest.get("body_ephemerides", [])),
                "checkpoints": len(viz_manifest.get("checkpoints", [])),
                "frames": len(viz_manifest.get("frames", [])),
            },
            "warnings": [
                "Orekit backend supports two-body propagation, checkpoints, final-state output, impulsive VNB burns, a limited event subset, validated Earth body-fixed output fallback, and ground-track generation from surface-fixed ephemerides; body ephemerides, unsupported frame transforms, and high-fidelity force models are not generated by the runner. Targeting may synthesize finite-difference STM assessments from Orekit perturbation runs."
            ],
            "errors": [],
        }

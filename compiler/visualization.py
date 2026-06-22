from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from compiler.io import read_json, write_json

KNOWN_BODY_RADII_KM = {
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


def clean_csv_file(path: str | Path) -> dict[str, Any]:
    """Remove GMAT ReportFile spacer columns from a CSV-like report in place.

    GMAT fixed-width/comma settings can create rows with repeated empty cells,
    e.g. ``UTCGregorian,,,,ElapsedSecs``.  The viewer-facing files should be
    simple CSVs, so empty cells are removed from each row.  This is conservative:
    it does not modify files that do not exist and preserves non-empty values.
    """
    path = Path(path)
    if not path.exists():
        return {"path": str(path), "exists": False, "changed": False}
    with path.open("r", newline="", encoding="utf-8", errors="replace") as f:
        rows = [[cell.strip() for cell in row if cell is not None and cell.strip() != ""] for row in csv.reader(f)]
    rows = [row for row in rows if row]
    original = path.read_text(encoding="utf-8", errors="replace")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(rows)
    changed = path.read_text(encoding="utf-8", errors="replace") != original
    return {"path": str(path), "exists": True, "changed": changed, "rows": len(rows)}


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in str(value))


def _frame_name(frame: Any) -> str:
    if isinstance(frame, dict):
        return str(frame.get("name") or frame.get("frame") or "J2000")
    return str(frame or "J2000")


def _body_radius(spec: dict, body_name: str) -> float | None:
    for body in spec.get("bodies", []) or []:
        if body.get("name") == body_name or body.get("id") == body_name:
            props = body.get("physical_properties", {}) or {}
            radius = props.get("radius", {}) or {}
            if isinstance(radius, dict):
                for key in ("mean", "equatorial", "value"):
                    if radius.get(key) is not None:
                        return float(radius[key])
            if isinstance(radius, (int, float)):
                return float(radius)
    return KNOWN_BODY_RADII_KM.get(body_name)


def _parse_epoch_seconds(epoch: str) -> float | None:
    if not epoch:
        return None
    text = str(epoch).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        pass
    for fmt in ("%d %b %Y %H:%M:%S.%f", "%d %b %Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(epoch), fmt).replace(tzinfo=timezone.utc).timestamp()
        except Exception:
            continue
    return None


def _state_epoch(state: dict) -> str:
    return str(state.get("epoch") or state.get("epoch_utc") or state.get("utc") or "")


def _state_elapsed_s(states: list[dict], idx: int, request: dict | None = None) -> float:
    state = states[idx]
    if state.get("elapsed_s") is not None:
        return float(state["elapsed_s"])
    if state.get("et_seconds_past_j2000") is not None and states and states[0].get("et_seconds_past_j2000") is not None:
        return float(state["et_seconds_past_j2000"]) - float(states[0]["et_seconds_past_j2000"])
    t0 = _parse_epoch_seconds(_state_epoch(states[0])) if states else None
    ti = _parse_epoch_seconds(_state_epoch(state))
    if t0 is not None and ti is not None:
        return ti - t0
    step_s = None
    if request:
        step_s = request.get("time_range", {}).get("step_s")
    return float(idx) * float(step_s or 0.0)


def _a1_mod_julian_from_epoch(epoch: str) -> float | None:
    # Viewer convenience only.  This is UTC-based MJD, not a GMAT A1 timescale
    # conversion.  If true A1 is required, it should come from GMAT/SPICE later.
    seconds = _parse_epoch_seconds(epoch)
    if seconds is None:
        return None
    return seconds / 86400.0 + 40587.0


def _find_resolved_ephemeris(mission_dir: Path, dependency_id: str | None) -> Path | None:
    candidates: list[Path] = []
    resolved_dir = mission_dir / "dependencies" / "resolved"
    if dependency_id:
        candidates.extend([
            resolved_dir / f"{dependency_id}_ephemeris.json",
            resolved_dir / f"{dependency_id}.json",
            mission_dir / "dependencies" / f"{dependency_id}_ephemeris.json",
            mission_dir / "dependencies" / f"{dependency_id}.json",
        ])
    candidates.extend(sorted(resolved_dir.glob("*.json")) if resolved_dir.exists() else [])
    for path in candidates:
        if path.exists():
            if dependency_id is None:
                return path
            try:
                payload = read_json(path)
                if payload.get("dependency_id") == dependency_id or payload.get("request_id") == dependency_id:
                    return path
            except Exception:
                continue
    return None


def _body_output_entries(spec: dict) -> list[dict]:
    entries: list[dict] = []
    for out in spec.get("outputs", []) or []:
        if out.get("enabled", True) is False:
            continue
        if out.get("type") == "body_ephemeris":
            entries.append(out)
        elif out.get("type") == "body_ephemeris_group":
            for body in out.get("bodies", []) or []:
                entry = dict(out)
                entry["type"] = "body_ephemeris"
                entry["body"] = body
                template = out.get("path_template") or "outputs/_BodyEphemeris_{body}_{frame}.csv"
                entry["path"] = template.format(body=_safe_name(body), frame=_safe_name(out.get("frame", "J2000")))
                entries.append(entry)
    return _dedupe_body_entries(entries + _force_model_body_output_entries(spec))


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
                if frame and frame not in frames:
                    frames.append(_frame_name(frame))
    for sc in spec.get("spacecraft", []) or []:
        frame = sc.get("frame")
        if frame and frame not in frames:
            frames.append(_frame_name(frame))
    return frames


def _frame_origin(spec: dict, frame: str | None) -> str | None:
    if not frame:
        return None
    for declared in spec.get("reference_frames", []) or []:
        if declared.get("name") == frame or declared.get("id") == frame:
            return declared.get("origin")
    for body in KNOWN_BODY_RADII_KM:
        if frame.startswith(body):
            return body
    return None


def _force_model_body_output_entries(spec: dict) -> list[dict]:
    entries: list[dict] = []
    for frame in _visualization_frames(spec):
        origin = _frame_origin(spec, frame)
        for body in _force_model_bodies(spec):
            if body == origin:
                continue
            entries.append({
                "id": f"force_model_{_safe_name(body)}_{_safe_name(frame)}_ephemeris",
                "type": "body_ephemeris",
                "body": body,
                "frame": frame,
                "source": "gmat",
                "path": f"outputs/_BodyEphemeris_{_safe_name(body)}_{_safe_name(frame)}.csv",
                "auto_generated": True,
                "reason": "force_model_body",
            })
    return entries


def _dedupe_body_entries(entries: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        body = str(entry.get("body") or entry.get("target") or "")
        frame = _frame_name(entry.get("frame"))
        key = (body, frame)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def export_body_ephemerides_from_resolved_spice(spec: dict, mission_dir: str | Path) -> list[dict]:
    """Convert resolved SPICE ephemeris JSON into viewer-ready body CSVs.

    This does not run SPICE.  It consumes normalized files created by the
    existing ``resolve-spice`` workflow and writes ``_BodyEphemeris*.csv`` files
    under the mission output directory.
    """
    mission_dir = Path(mission_dir)
    exported: list[dict] = []
    for out in _body_output_entries(spec):
        if out.get("source", "spice") != "spice":
            continue
        body = out.get("body") or out.get("target")
        frame = _frame_name(out.get("frame"))
        dep_id = out.get("dependency_id")
        resolved = _find_resolved_ephemeris(mission_dir, dep_id)
        desired = mission_dir / out.get("path", f"outputs/_BodyEphemeris_{_safe_name(body)}_{_safe_name(frame)}.csv")
        desired.parent.mkdir(parents=True, exist_ok=True)
        if resolved is None:
            if desired.exists():
                exported.append({
                    "body": body,
                    "frame": frame,
                    "file": str(desired),
                    "status": "using_gmat_reportfile_fallback",
                    "dependency_id": dep_id,
                    "source": "gmat_reportfile_fallback",
                })
            else:
                exported.append({"body": body, "frame": frame, "file": str(desired), "status": "missing_resolved_spice", "dependency_id": dep_id})
            continue
        payload = read_json(resolved)
        states = payload.get("states", []) or []
        target = payload.get("target", {}) or {}
        body_name = str(body or target.get("name") or target.get("ids", {}).get("naif") or "UnknownBody")
        radius_km = _body_radius(spec, body_name)
        rows: list[dict] = []
        for idx, state in enumerate(states):
            epoch = _state_epoch(state)
            pos = state.get("position") or state.get("position_km") or [None, None, None]
            vel = state.get("velocity") or state.get("velocity_km_s") or [None, None, None]
            rows.append({
                "body": body_name,
                "frame": frame,
                "UTCGregorian": epoch,
                "ElapsedSecs": _state_elapsed_s(states, idx),
                "A1ModJulian": _a1_mod_julian_from_epoch(epoch),
                "X": pos[0] if len(pos) > 0 else None,
                "Y": pos[1] if len(pos) > 1 else None,
                "Z": pos[2] if len(pos) > 2 else None,
                "VX": vel[0] if len(vel) > 0 else None,
                "VY": vel[1] if len(vel) > 1 else None,
                "VZ": vel[2] if len(vel) > 2 else None,
                "radius_km": radius_km,
            })
        with desired.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["body", "frame", "UTCGregorian", "ElapsedSecs", "A1ModJulian", "X", "Y", "Z", "VX", "VY", "VZ", "radius_km"])
            writer.writeheader()
            writer.writerows(rows)
        exported.append({"body": body_name, "frame": frame, "file": str(desired), "status": "exported", "states": len(rows), "source": str(resolved)})
    return exported


def _time_columns(parameters: list[str]) -> list[str]:
    cols = []
    for p in parameters:
        if p.endswith("UTCGregorian") or p == "UTCGregorian":
            cols.append(p)
        if p.endswith("ElapsedSecs") or p == "ElapsedSecs":
            cols.append(p)
        if p.endswith("A1ModJulian") or p == "A1ModJulian":
            cols.append(p)
    return cols or ["UTCGregorian", "ElapsedSecs"]


def _position_columns(parameters: list[str]) -> list[str]:
    return [p for p in parameters if p.endswith((".X", ".Y", ".Z")) or p in {"X", "Y", "Z"}]


def _velocity_columns(parameters: list[str]) -> list[str]:
    return [p for p in parameters if p.endswith((".VX", ".VY", ".VZ")) or p in {"VX", "VY", "VZ"}]


def _finite_burn_intervals(spec: dict) -> list[dict]:
    burns = {burn.get("id"): burn for burn in spec.get("burns", []) or []}
    events = {event.get("id"): event for event in spec.get("events", []) or []}
    elapsed_by_sc = {sc.get("id"): 0.0 for sc in spec.get("spacecraft", []) or []}
    intervals: list[dict] = []
    for phase in spec.get("mission_sequence", []) or []:
        for step in phase.get("steps", []) or []:
            sc_id = step.get("spacecraft")
            if step.get("type") == "propagate" and sc_id in elapsed_by_sc:
                elapsed_by_sc[sc_id] += float(step.get("duration_s", 0.0))
            elif step.get("type") == "maneuver":
                burn = burns.get(step.get("burn"))
                if burn and burn.get("type") == "finite" and sc_id in elapsed_by_sc:
                    start = float(elapsed_by_sc[sc_id])
                    duration = float(step.get("duration_s", 0.0))
                    end = start + duration
                    intervals.append({
                        "id": step.get("step_id") or burn.get("id"),
                        "name": burn.get("name") or step.get("step_id"),
                        "burn_id": burn.get("id"),
                        "spacecraft_id": sc_id,
                        "start_elapsed_s": start,
                        "end_elapsed_s": end,
                        "duration_s": duration,
                        "phase_id": phase.get("phase_id"),
                        "source": "mission_sequence",
                    })
                    elapsed_by_sc[sc_id] = end
            elif step.get("type") == "event_action":
                event = events.get(step.get("event_id"))
                if not event:
                    continue
                for action in event.get("actions", []) or []:
                    if action.get("type") != "maneuver":
                        continue
                    action_sc_id = action.get("spacecraft")
                    burn = burns.get(action.get("burn"))
                    if not burn or burn.get("type") != "finite" or action_sc_id not in elapsed_by_sc:
                        continue
                    start = float(elapsed_by_sc[action_sc_id])
                    duration = float(action.get("duration_s", 0.0))
                    end = start + duration
                    intervals.append({
                        "id": action.get("action_id") or burn.get("id"),
                        "name": burn.get("name") or action.get("action_id"),
                        "burn_id": burn.get("id"),
                        "spacecraft_id": action_sc_id,
                        "start_elapsed_s": start,
                        "end_elapsed_s": end,
                        "duration_s": duration,
                        "phase_id": phase.get("phase_id"),
                        "event_id": event.get("id"),
                        "source": "event_action",
                        "timing_confidence": "sequence_estimate",
                    })
                    elapsed_by_sc[action_sc_id] = end
    return intervals


def build_visualization_manifest(spec: dict, mission_dir: str | Path, reports: list[dict] | None = None, checkpoints: list[dict] | None = None) -> dict:
    mission_dir = Path(mission_dir)
    if reports is None or checkpoints is None:
        # Late import avoids making the GMAT compiler depend on this module at import time.
        from compiler.backends.gmat.compiler import output_reports, checkpoint_reports
        reports = output_reports(spec, mission_dir)
        checkpoints = checkpoint_reports(spec, mission_dir)

    spacecraft_ephemerides = []
    for report in reports or []:
        if not Path(report.get("path", "")).name.startswith("_Ephemeris"):
            continue
        params = report.get("parameters", [])
        spacecraft_ephemerides.append({
            "spacecraft": report.get("spacecraft_name"),
            "spacecraft_id": report.get("spacecraft_id"),
            "frame": report.get("frame"),
            "file": report.get("path"),
            "time_columns": _time_columns(params),
            "position_columns": _position_columns(params),
            "velocity_columns": _velocity_columns(params),
            "source": "gmat_reportfile",
        })

    checkpoint_entries = []
    for cp in checkpoints or []:
        params = cp.get("parameters", [])
        checkpoint_entries.append({
            "checkpoint_id": cp.get("id"),
            "spacecraft": cp.get("spacecraft_name"),
            "spacecraft_id": cp.get("spacecraft_id"),
            "frame": cp.get("frame"),
            "file": cp.get("path"),
            "time_columns": _time_columns(params),
            "position_columns": _position_columns(params),
            "velocity_columns": _velocity_columns(params),
            "source": "gmat_report_command",
        })

    body_ephemerides = []
    for out in _body_output_entries(spec):
        body = out.get("body") or out.get("target")
        frame = _frame_name(out.get("frame"))
        path = out.get("path") or f"outputs/_BodyEphemeris_{_safe_name(body)}_{_safe_name(frame)}.csv"
        source = out.get("source", "spice")
        # If a SPICE body ephemeris was requested but no resolved SPICE JSON is
        # available and a GMAT-generated fallback body ephemeris file exists,
        # label the provenance honestly for the viewer.
        if source == "spice" and _find_resolved_ephemeris(mission_dir, out.get("dependency_id")) is None:
            if (mission_dir / path).exists():
                source = "gmat_reportfile_fallback"
        body_ephemerides.append({
            "body": body,
            "frame": frame,
            "file": path,
            "source": source,
            "requested_source": out.get("source", "spice"),
            "dependency_id": out.get("dependency_id"),
            "time_columns": ["UTCGregorian", "ElapsedSecs", "A1ModJulian"],
            "position_columns": ["X", "Y", "Z"],
            "velocity_columns": ["VX", "VY", "VZ"],
            "radius_column": "radius_km",
        })

    ground_tracks = []
    for report in reports or []:
        if report.get("kind") != "ground_track":
            continue
        params = report.get("parameters", [])
        ground_tracks.append({
            "spacecraft": report.get("spacecraft_name"),
            "spacecraft_id": report.get("spacecraft_id"),
            "body": report.get("body", "Earth"),
            "frame": report.get("frame"),
            "file": report.get("path"),
            "time_columns": _time_columns(params),
            "latitude_column": next((p for p in params if p.endswith(".Latitude") or p == "Latitude"), None),
            "longitude_column": next((p for p in params if p.endswith(".Longitude") or p == "Longitude"), None),
            "altitude_column": next((p for p in params if p.endswith(".Altitude") or p == "Altitude"), None),
            "source": "gmat_reportfile",
        })

    frames = []
    for frame in spec.get("reference_frames", []) or []:
        gmat = (frame.get("backend_overrides", {}) or {}).get("gmat", {}) or {}
        frames.append({
            "id": frame.get("id"),
            "name": frame.get("name"),
            "origin": frame.get("origin"),
            "primary": frame.get("primary") or gmat.get("primary"),
            "secondary": frame.get("secondary") or gmat.get("secondary"),
            "axes": frame.get("axes") or frame.get("orientation"),
            "x_axis": frame.get("x_axis") or gmat.get("x_axis"),
            "z_axis": frame.get("z_axis") or gmat.get("z_axis"),
            "type": frame.get("type"),
            "source": "mission_spec",
            "backend_overrides": frame.get("backend_overrides"),
        })
    for report in reports or []:
        name = report.get("frame")
        if name and not any(f.get("name") == name for f in frames):
            frames.append({"name": name, "origin": None, "axes": None, "type": "inferred", "source": "output_parameter"})

    sources = {
        "spacecraft_ephemerides": [
            {
                "provider": "gmat",
                "method": entry.get("source", "gmat_reportfile"),
                "artifact": entry.get("file"),
                "spacecraft": entry.get("spacecraft"),
                "frame": entry.get("frame"),
            }
            for entry in spacecraft_ephemerides
        ],
        "body_ephemerides": [
            {
                "provider": entry.get("source", "spice"),
                "method": "resolved_dependency_export" if entry.get("source", "spice") == "spice" else "declared_output",
                "artifact": entry.get("file"),
                "body": entry.get("body"),
                "frame": entry.get("frame"),
                "dependency_id": entry.get("dependency_id"),
            }
            for entry in body_ephemerides
        ],
        "ground_tracks": [
            {
                "provider": "gmat",
                "method": "ground_track_reportfile",
                "artifact": entry.get("file"),
                "spacecraft": entry.get("spacecraft"),
                "body": entry.get("body"),
            }
            for entry in ground_tracks
        ],
        "checkpoints": [
            {
                "provider": "gmat",
                "method": entry.get("source", "gmat_report_command"),
                "artifact": entry.get("file"),
                "checkpoint_id": entry.get("checkpoint_id"),
                "spacecraft": entry.get("spacecraft"),
                "frame": entry.get("frame"),
            }
            for entry in checkpoint_entries
        ],
    }

    assumptions = [
        "Spacecraft ephemeris files are generated by the GMAT backend from spacecraft propagation results.",
        "Checkpoint files are sparse GMAT report-command snapshots at mission-sequence positions and are not full trajectory files.",
        "Body ephemeris files are exported from resolved external dependencies, usually SPICE, when the matching resolved JSON files are available.",
        "Visualization outputs are provenance-labeled only; no GMAT/SPICE physical consistency check is performed for visualization-only artifacts.",
        "The viewer should use this manifest for source, frame, column, and artifact metadata rather than inferring everything from filenames.",
    ]

    viewer_warnings = []
    if body_ephemerides and not spacecraft_ephemerides:
        viewer_warnings.append("Body ephemerides are declared, but no spacecraft _Ephemeris file is listed in the manifest.")
    if spacecraft_ephemerides and body_ephemerides:
        viewer_warnings.append("Spacecraft and body ephemerides may come from different providers; use source metadata when displaying provenance.")
    if any(entry.get("source") == "gmat_reportfile_fallback" for entry in body_ephemerides):
        viewer_warnings.append("At least one body ephemeris was requested from SPICE but exported from GMAT ReportFile fallback because resolved SPICE data was unavailable.")
    finite_burns = _finite_burn_intervals(spec)
    force_model_bodies = []
    for fm in spec.get("force_models", []) or []:
        bodies = [fm.get("central_body")]
        bodies.extend(fm.get("point_masses") or [])
        bodies.extend((fm.get("third_body_gravity", {}) or {}).get("bodies") or [])
        for body in bodies:
            if body and body not in force_model_bodies:
                force_model_bodies.append(body)

    return {
        "schema_version": "1.0.0",
        "mission_id": spec.get("mission_id"),
        "spacecraft_ephemerides": spacecraft_ephemerides,
        "body_ephemerides": body_ephemerides,
        "ground_tracks": ground_tracks,
        "checkpoints": checkpoint_entries,
        "finite_burns": finite_burns,
        "burn_intervals": finite_burns,
        "frames": frames,
        "force_model_bodies": force_model_bodies,
        "sources": sources,
        "assumptions": assumptions,
        "viewer_warnings": viewer_warnings,
        "artifact_layout": {
            "mission_dir": ".",
            "outputs_dir": "outputs",
            "mission_spec": "mission_spec.canonical.json",
            "gmat_script": "generated_mission.script",
        },
    }


def write_visualization_manifest(spec: dict, mission_dir: str | Path, reports: list[dict] | None = None, checkpoints: list[dict] | None = None) -> dict:
    mission_dir = Path(mission_dir)
    manifest = build_visualization_manifest(spec, mission_dir, reports, checkpoints)
    write_json(mission_dir / "visualization_manifest.json", manifest)
    return manifest



def _load_spice_request_payload(mission_dir: Path) -> dict | None:
    path = mission_dir / "dependencies" / "spice_requests.json"
    if not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


def auto_resolve_missing_spice_dependencies(spec: dict, mission_dir: str | Path) -> list[dict]:
    """Best-effort SPICE resolution for visualization body ephemerides.

    This enables normal generated_mission.py --run operation to create
    _BodyEphemeris*.csv files when spiceypy and the requested kernels are
    available.  It is intentionally non-fatal: missing spiceypy, missing
    kernels, or invalid requests are reported in the returned status list and
    the visualization manifest still records the expected body ephemeris.
    """
    mission_dir = Path(mission_dir)
    payload = _load_spice_request_payload(mission_dir)
    if not payload:
        return []
    requests = payload.get("requests", []) or []
    requests_by_dep = {r.get("dependency_id"): r for r in requests if r.get("dependency_id")}
    results: list[dict] = []
    for out in _body_output_entries(spec):
        if out.get("source", "spice") != "spice":
            continue
        dep_id = out.get("dependency_id")
        if not dep_id:
            results.append({"dependency_id": None, "status": "skipped", "reason": "body_ephemeris output has no dependency_id"})
            continue
        if _find_resolved_ephemeris(mission_dir, dep_id) is not None:
            results.append({"dependency_id": dep_id, "status": "already_resolved"})
            continue
        request = requests_by_dep.get(dep_id)
        if request is None:
            results.append({"dependency_id": dep_id, "status": "missing_request"})
            continue
        output_rel = request.get("output", {}).get("path") or f"dependencies/resolved/{dep_id}_ephemeris.json"
        output_path = mission_dir / output_rel
        try:
            from compiler.dependencies.spice import resolve_spice_request
            resolve_spice_request(request, output_path)
            results.append({"dependency_id": dep_id, "status": "resolved", "path": str(output_path)})
        except Exception as exc:
            results.append({"dependency_id": dep_id, "status": "resolve_failed", "error": str(exc), "path": str(output_path)})
    return results


def export_visualization_artifacts(mission_dir: str | Path) -> dict:
    mission_dir = Path(mission_dir)
    spec_path = mission_dir / "mission_spec.canonical.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"Missing canonical MissionSpec: {spec_path}")
    spec = read_json(spec_path)
    spice_auto_resolve = auto_resolve_missing_spice_dependencies(spec, mission_dir)
    body_exports = export_body_ephemerides_from_resolved_spice(spec, mission_dir)
    # Normalize any already-created viewer-facing CSVs.
    normalized = []
    outputs_dir = mission_dir / "outputs"
    if outputs_dir.exists():
        for path in sorted(outputs_dir.glob("*.csv")):
            normalized.append(clean_csv_file(path))
    manifest = write_visualization_manifest(spec, mission_dir)
    return {
        "mission_id": spec.get("mission_id"),
        "visualization_manifest": str(mission_dir / "visualization_manifest.json"),
        "spice_auto_resolve": spice_auto_resolve,
        "body_ephemeris_exports": body_exports,
        "normalized_csvs": normalized,
        "manifest_counts": {
            "spacecraft_ephemerides": len(manifest.get("spacecraft_ephemerides", [])),
            "body_ephemerides": len(manifest.get("body_ephemerides", [])),
            "checkpoints": len(manifest.get("checkpoints", [])),
            "frames": len(manifest.get("frames", [])),
        },
    }


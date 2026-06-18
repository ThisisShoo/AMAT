from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import math

from mission_compiler.io import write_json


class SpiceDependencyError(RuntimeError):
    pass


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def build_spice_requests(spec: dict, out_dir: str | Path | None = None) -> list[dict]:
    """Build normalized SPICE request objects from a MissionSpec.

    This function does not require spiceypy.  It only extracts the declared
    dependency contract.  The request files are reproducibility artifacts that
    can be resolved by a trusted SPICE adapter later.
    """
    requests: list[dict] = []
    explicit = spec.get("external_dependencies", []) or []
    for dep in explicit:
        if dep.get("provider") != "spice" and dep.get("type") not in {"spice_ephemeris", "spice_kernel_set"}:
            continue
        if dep.get("type") == "spice_kernel_set":
            # Kernel sets are referenced by ephemeris requests but do not by
            # themselves define target/observer/time samples.
            continue
        requests.append(_request_from_dependency(spec, dep))

    deps_by_id = {d.get("id"): d for d in explicit}
    for body in spec.get("bodies", []) or []:
        ephem = body.get("ephemeris", {}) or {}
        if ephem.get("source") != "spice":
            continue
        dep_id = ephem.get("dependency_id")
        if not dep_id or dep_id in {r.get("dependency_id") for r in requests}:
            continue
        dep = deps_by_id.get(dep_id)
        if dep:
            requests.append(_request_from_dependency(spec, dep))
    return requests


def write_spice_requests(spec: dict, out_dir: str | Path) -> list[dict]:
    out_dir = Path(out_dir)
    deps_dir = out_dir / "dependencies"
    deps_dir.mkdir(parents=True, exist_ok=True)
    requests = build_spice_requests(spec, out_dir)
    if requests:
        write_json(deps_dir / "spice_requests.json", {
            "schema_version": "1.0.0",
            "mission_id": spec["mission_id"],
            "provider": "spice",
            "requests": requests,
        })
    return requests


def _request_from_dependency(spec: dict, dep: dict) -> dict:
    req_id = dep.get("request_id") or f"SPICE_REQ_{dep['id']}"
    time_range = dep.get("time_range", {})
    frame = dep.get("frame", {"name": "J2000"})
    if isinstance(frame, str):
        frame = {"name": frame}
    return {
        "schema_version": "1.0.0",
        "request_id": req_id,
        "dependency_id": dep["id"],
        "provider": "spice",
        "purpose": dep.get("purpose", "ephemeris"),
        "kernels": dep.get("kernels", {}),
        "target": dep.get("target", {}),
        "observer": dep.get("observer", {"name": dep.get("observer_name", "Solar System Barycenter"), "naif_id": 0}),
        "time_range": {
            "start": time_range.get("start"),
            "stop": time_range.get("stop"),
            "step_s": time_range.get("step_s", 3600),
            "input_time_scale": time_range.get("input_time_scale", "UTC"),
            "output_time_scale": time_range.get("output_time_scale", "TDB"),
        },
        "reference": {
            "frame": frame.get("name", "J2000"),
            "aberration_correction": dep.get("aberration_correction", "NONE"),
        },
        "output": {
            "path": dep.get("output", {}).get("path", f"dependencies/resolved/{dep['id']}_ephemeris.json"),
            "format": dep.get("output", {}).get("format", "normalized_json"),
            "position_unit": "km",
            "velocity_unit": "km/s",
        },
        "reproducibility": dep.get("reproducibility", {"store_raw": False, "store_normalized": True, "require_hash": True}),
    }


def resolve_spice_request(request: dict, output_path: str | Path) -> dict:
    """Resolve one SPICE ephemeris request with spiceypy, if installed.

    This is intentionally optional.  The MVP can generate request contracts
    without SPICE installed.  To execute this resolver, install with:

        pip install -e .[spice]

    and provide valid kernels/metakernel paths in the request.
    """
    try:
        import spiceypy as spice  # type: ignore
    except Exception as exc:  # pragma: no cover - optional dependency
        raise SpiceDependencyError("spiceypy is not installed. Install the MVP with the [spice] extra.") from exc

    kernels = request.get("kernels", {})
    loaded: list[str] = []
    try:
        meta = kernels.get("metakernel_path")
        if meta:
            spice.furnsh(str(meta)); loaded.append(str(meta))
        for kernel in kernels.get("kernel_paths", []) or []:
            spice.furnsh(str(kernel)); loaded.append(str(kernel))

        target = _spice_name_or_id(request.get("target", {}))
        observer = _spice_name_or_id(request.get("observer", {}))
        frame = request.get("reference", {}).get("frame", "J2000")
        abcorr = request.get("reference", {}).get("aberration_correction", "NONE")
        tr = request.get("time_range", {})
        start_et = spice.str2et(tr["start"])
        stop_et = spice.str2et(tr["stop"])
        step_s = float(tr.get("step_s", 3600))
        if step_s <= 0:
            raise SpiceDependencyError("SPICE request step_s must be positive")
        n = int(math.floor((stop_et - start_et) / step_s)) + 1
        ets = [start_et + i * step_s for i in range(max(n, 0))]
        if ets and ets[-1] < stop_et:
            ets.append(stop_et)

        states = []
        for et in ets:
            state, lt = spice.spkezr(target, et, frame, abcorr, observer)
            epoch_utc = spice.et2utc(et, "ISOC", 6)
            states.append({
                "epoch": epoch_utc,
                "et_seconds_past_j2000": et,
                "position": [float(state[0]), float(state[1]), float(state[2])],
                "velocity": [float(state[3]), float(state[4]), float(state[5])],
                "light_time_s": float(lt),
                "covariance": None,
                "quality": {"source": "spice", "interpolated": False, "estimated_position_error_km": None, "estimated_velocity_error_km_s": None},
            })

        result = {
            "schema_version": "1.0.0",
            "request_id": request.get("request_id"),
            "dependency_id": request.get("dependency_id"),
            "provider": "spice",
            "status": "ok",
            "source_metadata": {"source_name": "SPICE", "kernels_loaded": loaded},
            "target": request.get("target", {}),
            "observer": request.get("observer", {}),
            "frame": {"name": frame},
            "time": {"scale": "TDB", "format": "iso8601"},
            "units": {"position": "km", "velocity": "km/s"},
            "states": states,
            "coverage": {"start": tr.get("start"), "stop": tr.get("stop")},
            "warnings": [],
            "errors": [],
        }
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        return result
    finally:  # pragma: no cover - optional dependency cleanup
        try:
            spice.kclear()
        except Exception:
            pass


def _spice_name_or_id(obj: dict) -> str:
    if obj.get("name"):
        name = str(obj["name"])
        return {"Luna": "MOON", "luna": "MOON", "Moon": "MOON"}.get(name, name)
    ids = obj.get("ids", {}) or {}
    if ids.get("naif") is not None:
        return str(ids["naif"])
    if obj.get("naif_id") is not None:
        return str(obj["naif_id"])
    raise SpiceDependencyError(f"SPICE object must define name or NAIF id: {obj}")


def build_spice_kernel_sets(spec: dict) -> list[dict]:
    """Return SPICE kernel-set declarations for GMAT/script metadata.

    This is the GMAT-facing side of SPICE integration.  By default the MVP
    writes deterministic comments in the generated GMAT script so humans can
    verify which kernels are required.  If a project later confirms exact GMAT
    SpiceKernel syntax for its GMAT build, set gmat_integration.mode to
    ``spice_kernel_object`` and extend the template hook.
    """
    sets: list[dict] = []
    for dep in spec.get("external_dependencies", []) or []:
        if dep.get("type") != "spice_kernel_set" or dep.get("provider") != "spice":
            continue
        gi = dep.get("gmat_integration", {}) or {}
        kernels = dep.get("kernels", {}) or {}
        all_paths = []
        if kernels.get("metakernel_path"):
            all_paths.append(kernels["metakernel_path"])
        all_paths.extend(kernels.get("kernel_paths", []) or [])
        sets.append({
            "id": dep["id"],
            "name": f"SK_{dep['id'].replace('-', '_')}",
            "enabled": gi.get("enabled", False),
            "mode": gi.get("mode", "comment_only"),
            "script_comments": gi.get("script_comments", True),
            "kernels": kernels,
            "kernel_paths": all_paths,
            "description": dep.get("description", ""),
        })
    return sets

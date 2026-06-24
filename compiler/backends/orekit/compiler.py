from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from compiler.hashing import hash_file
from compiler.io import write_text
from compiler.ir.sequence import iter_steps
from compiler.time_formats import format_epoch_for_backend


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

SUPPORTED_FRAMES = {
    "EarthMJ2000Eq",
    "MJ2000Eq",
    "EME2000",
    "LunaMJ2000Eq",
    "MoonMJ2000Eq",
}


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


def _output_paths(spec: dict[str, Any]) -> list[dict[str, str]]:
    outputs: list[dict[str, str]] = []
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
            path = str(template).format(spacecraft=sc.get("name") or sc_id, frame=frame)
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
    return plan


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
        "checkpoints": _checkpoint_paths(spec),
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
            errors.append(f"Orekit backend does not yet support burn {burn.get('id')!r}.")
        for event in spec.get("events", []) or []:
            errors.append(f"Orekit backend does not yet support event {event.get('id')!r}.")
        for _, step, _ in iter_steps(spec):
            if step.get("type") not in {"propagate", "checkpoint", "report"}:
                errors.append(f"Orekit backend does not yet support mission sequence step {step.get('step_id') or step.get('type')!r} of type {step.get('type')!r}.")

        for out in spec.get("outputs", []) or []:
            if out.get("type") == "ground_track":
                warnings.append(f"Orekit backend compile accepts mission, but ground-track output {out.get('id')!r} is not generated yet.")
            elif out.get("type") != "spacecraft_ephemeris":
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
                }
            ],
            "warnings": [
                "Orekit backend is an initial two-body propagation backend. Maneuvers, events, ground tracks, and high-fidelity force models are not implemented yet."
            ],
            "errors": [],
        }


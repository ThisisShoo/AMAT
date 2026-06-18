from __future__ import annotations

from pathlib import Path

from mission_compiler.artifacts.manifest import build_manifest
from mission_compiler.backends.registry import get_backend
from mission_compiler.io import read_json, write_json
from mission_compiler.ir.canonicalize import canonicalize
from mission_compiler.validation.validate_bounds import validate_bounds
from mission_compiler.validation.validate_dependencies import validate_dependencies
from mission_compiler.validation.validate_frames import validate_frames
from mission_compiler.validation.validate_schema import validate_schema
from mission_compiler.validation.validate_units import validate_units


def validate_mission(spec: dict, backend_id: str = "gmat") -> dict:
    checks = []
    errors = []
    try:
        checks += validate_schema(spec)
        canonical = canonicalize(spec)
        checks += validate_units(canonical)
        checks += validate_frames(canonical)
        checks += validate_dependencies(canonical)
        checks += validate_bounds(canonical)
        checks += get_backend(backend_id).validate_capability(canonical)
        status = "passed"
    except Exception as exc:
        status = "failed"
        errors.append(str(exc))
    return {
        "schema_version": "1.0.0",
        "mission_id": spec.get("mission_id", "UNKNOWN"),
        "status": status,
        "checks": checks,
        "warnings": [],
        "errors": errors,
    }


def compile_bundle(spec_path: str | Path, out_dir: str | Path, backend_id: str = "gmat") -> dict:
    spec = read_json(spec_path)
    canonical = canonicalize(spec)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    validation_report = validate_mission(canonical, backend_id)
    write_json(out_dir / "mission_spec.canonical.json", canonical)
    write_json(out_dir / "validation_report.json", validation_report)
    if validation_report["status"] == "failed":
        compile_result = {
            "schema_version": "1.0.0",
            "mission_id": canonical.get("mission_id", "UNKNOWN"),
            "backend_id": backend_id,
            "status": "failed",
            "generated_artifacts": [],
            "warnings": [],
            "errors": validation_report["errors"],
        }
    else:
        compile_result = get_backend(backend_id).compile(canonical, out_dir)
    write_json(out_dir / "compile_result.json", compile_result)

    manifest = build_manifest(canonical["mission_id"], out_dir)
    write_json(out_dir / "artifact_manifest.json", manifest)
    return {"validation_report": validation_report, "compile_result": compile_result, "artifact_manifest": manifest}

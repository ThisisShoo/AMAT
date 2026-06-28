from __future__ import annotations

from pathlib import Path

from compiler.artifacts.manifest import build_manifest
from compiler.backends.registry import get_backend
from compiler.io import read_json, write_json
from compiler.ir.backend_spec import to_backend_spec
from compiler.ir.canonicalize import canonicalize
from compiler.validation.validate_bounds import validate_bounds
from compiler.validation.validate_dependencies import validate_dependencies
from compiler.validation.validate_frames import validate_frames
from compiler.validation.validate_schema import validate_schema
from compiler.validation.validate_units import validate_units


COMPILE_RESULT_SCHEMA_VERSION = "2.0.0"


def _failed_compile_result(
    *,
    mission_id: str,
    backend_id: str,
    mission_spec_schema_version: str | None,
    errors: list[str],
) -> dict:
    return {
        "schema_version": COMPILE_RESULT_SCHEMA_VERSION,
        "artifact_schema_version": COMPILE_RESULT_SCHEMA_VERSION,
        "mission_spec_schema_version": mission_spec_schema_version,
        "backend_ir_schema_version": None,
        "mission_id": mission_id,
        "backend_id": backend_id,
        "status": "failed",
        "generated_artifacts": [],
        "warnings": [],
        "errors": errors,
    }


def _normalize_compile_result(
    result: dict,
    *,
    public_spec: dict,
    backend_ir: dict,
) -> dict:
    normalized = dict(result)
    normalized["schema_version"] = COMPILE_RESULT_SCHEMA_VERSION
    normalized["artifact_schema_version"] = COMPILE_RESULT_SCHEMA_VERSION
    normalized["mission_spec_schema_version"] = public_spec.get("schema_version")
    normalized["backend_ir_schema_version"] = backend_ir.get("schema_version")
    return normalized


def validate_mission(spec: dict, backend_id: str = "gmat") -> dict:
    checks = []
    errors = []
    mission_spec_schema_version = spec.get("schema_version")
    backend_ir_schema_version = None
    try:
        checks += validate_schema(spec)
        backend_ir = canonicalize(to_backend_spec(spec))
        backend_ir_schema_version = backend_ir.get("schema_version")
        checks += validate_units(backend_ir)
        checks += validate_frames(backend_ir)
        checks += validate_dependencies(backend_ir)
        checks += validate_bounds(backend_ir)
        checks += get_backend(backend_id).validate_capability(backend_ir)
        status = "passed"
    except Exception as exc:
        status = "failed"
        errors.append(str(exc))
    return {
        "schema_version": COMPILE_RESULT_SCHEMA_VERSION,
        "artifact_schema_version": COMPILE_RESULT_SCHEMA_VERSION,
        "mission_spec_schema_version": mission_spec_schema_version,
        "backend_ir_schema_version": backend_ir_schema_version,
        "mission_id": spec.get("mission_id", "UNKNOWN"),
        "status": status,
        "checks": checks,
        "warnings": [],
        "errors": errors,
    }


def compile_bundle(spec_path: str | Path, out_dir: str | Path, backend_id: str = "gmat") -> dict:
    spec = read_json(spec_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    validation_report = validate_mission(spec, backend_id)
    write_json(out_dir / "validation_report.json", validation_report)
    if validation_report["status"] == "failed":
        write_json(out_dir / "mission_spec.canonical.json", spec)
        compile_result = _failed_compile_result(
            mission_id=spec.get("mission_id", "UNKNOWN"),
            backend_id=backend_id,
            mission_spec_schema_version=spec.get("schema_version"),
            errors=validation_report["errors"],
        )
    else:
        backend_ir = canonicalize(to_backend_spec(spec))
        write_json(out_dir / "mission_spec.canonical.json", spec)
        write_json(out_dir / "mission_spec.backend_ir.json", backend_ir)
        compile_result = _normalize_compile_result(
            get_backend(backend_id).compile(backend_ir, out_dir),
            public_spec=spec,
            backend_ir=backend_ir,
        )
    write_json(out_dir / "compile_result.json", compile_result)

    manifest = build_manifest(spec.get("mission_id", "UNKNOWN"), out_dir)
    write_json(out_dir / "artifact_manifest.json", manifest)
    return {"validation_report": validation_report, "compile_result": compile_result, "artifact_manifest": manifest}


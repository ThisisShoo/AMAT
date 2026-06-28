from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from compiler import __version__
from compiler.hashing import hash_file


def build_manifest(mission_id: str, out_dir: str | Path, extra_artifacts: list[dict] | None = None) -> dict:
    out_dir = Path(out_dir)
    backend_id = "gmat"
    compile_result_path = out_dir / "compile_result.json"
    if compile_result_path.exists():
        try:
            backend_id = str(json.loads(compile_result_path.read_text(encoding="utf-8")).get("backend_id") or backend_id)
        except Exception:
            backend_id = "gmat"
    artifacts = []
    for artifact_id, typ, filename, required in [
        ("MISSION_SPEC", "mission_spec", "mission_spec.canonical.json", True),
        ("BACKEND_IR", "backend_ir", "mission_spec.backend_ir.json", True),
        ("VALIDATION_REPORT", "validation_report", "validation_report.json", True),
        ("COMPILE_RESULT", "compile_result", "compile_result.json", True),
        ("PYTHON_SCRIPT", "python_script", "generated_mission.py", True),
        ("GMAT_SCRIPT", "native_script", "generated_mission.script", False),
    ]:
        path = out_dir / filename
        if path.exists():
            item = {"artifact_id": artifact_id, "type": typ, "path": filename, "hash": hash_file(path), "required_for_replay": required}
            if typ in {"python_script", "native_script"}:
                item["backend"] = backend_id
            artifacts.append(item)
    if extra_artifacts:
        artifacts.extend(extra_artifacts)
    return {
        "schema_version": "1.0.0",
        "mission_id": mission_id,
        "bundle_id": f"{mission_id}_bundle",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": artifacts,
        "provenance": {"generated_by": "compiler", "compiler_version": __version__},
    }


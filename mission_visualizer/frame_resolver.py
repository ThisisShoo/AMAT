from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import FrameInfo, MissionPaths


def _load_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_manifest(paths: MissionPaths) -> dict[str, Any]:
    return _load_json(paths.visualization_manifest)


def resolve_frames(paths: MissionPaths, manifest: dict[str, Any]) -> list[FrameInfo]:
    frames: dict[str, FrameInfo] = {}

    for f in manifest.get("frames", []) if manifest else []:
        name = f.get("name")
        if name:
            frames[name] = FrameInfo(
                name=name,
                origin=f.get("origin"),
                axes=f.get("axes"),
                source=f.get("source", "visualization_manifest"),
                confidence="high",
                raw=f,
            )

    for spec_path in [paths.canonical_spec, paths.candidate_mission_spec, paths.examples_spec]:
        spec = _load_json(spec_path)
        for f in spec.get("frames", []) if isinstance(spec.get("frames", []), list) else []:
            name = f.get("name")
            if name and name not in frames:
                frames[name] = FrameInfo(name=name, origin=f.get("origin"), axes=f.get("axes"), source=str(spec_path.name), confidence="medium", raw=f)

    if paths.gmat_script and paths.gmat_script.exists():
        text = paths.gmat_script.read_text(encoding="utf-8", errors="replace")
        # Very lightweight GMAT CoordinateSystem parser. This preserves enough for warnings/metadata.
        for m in re.finditer(r"Create\s+CoordinateSystem\s+(\w+)", text):
            name = m.group(1)
            block_pat = re.compile(rf"GMAT\s+{re.escape(name)}\.(\w+)\s*=\s*([^;]+);")
            raw = {k: v.strip().strip("'") for k, v in block_pat.findall(text)}
            if name not in frames:
                frames[name] = FrameInfo(
                    name=name,
                    origin=raw.get("Origin"),
                    axes=raw.get("Axes"),
                    source="generated_mission.script",
                    confidence="medium" if raw else "low",
                    raw=raw,
                )

    return list(frames.values())

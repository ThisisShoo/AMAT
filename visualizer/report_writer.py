from __future__ import annotations

import json
from pathlib import Path

from .models import MissionScene, MissionPaths


def _relative(path: Path | None, base: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path.name)


def write_report(scene: MissionScene, paths: MissionPaths, output: str | Path | None = None) -> Path:
    output_path = Path(output) if output else (paths.visualization_dir or (paths.mission_dir / "visualization")) / "visualization_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "mission_id": scene.mission_id,
        "paths": {
            "mission_root": ".",
            "mission_dir": _relative(paths.mission_dir, paths.mission_root),
            "outputs_dir": _relative(paths.outputs_dir, paths.mission_root),
            "targeting_dir": _relative(paths.targeting_dir, paths.mission_root),
            "target_problem": _relative(paths.target_problem, paths.mission_root),
            "targeting_result": _relative(paths.targeting_result, paths.mission_root),
            "candidate_mission_spec": _relative(paths.candidate_mission_spec, paths.mission_root),
        },
        "spacecraft_ephemerides": [
            {
                "name": t.name,
                "object": t.object_name,
                "frame": t.frame,
                "file": _relative(t.path, paths.mission_dir),
                "time_column": t.time_col,
                "position_columns": [t.x_col, t.y_col, t.z_col],
                "rows": int(len(t.dataframe)),
                "warnings": t.warnings,
            }
            for t in scene.spacecraft_traces
        ],
        "body_ephemerides": [
            {
                "name": t.name,
                "object": t.object_name,
                "frame": t.frame,
                "file": _relative(t.path, paths.mission_dir),
                "time_column": t.time_col,
                "position_columns": [t.x_col, t.y_col, t.z_col],
                "rows": int(len(t.dataframe)),
                "warnings": t.warnings,
            }
            for t in scene.body_traces
        ],
        "checkpoints": [
            {
                "name": cp.name,
                "file": _relative(cp.path, paths.mission_dir),
                "spacecraft": cp.spacecraft,
                "frame": cp.frame,
                "time_column": cp.time_col,
                "elapsed_secs": cp.elapsed_secs,
                "utc_gregorian": cp.utc_gregorian,
                "plotted": cp.plotted,
                "matched_trace": cp.matched_trace,
                "interpolated_xyz": cp.interpolated_xyz,
                "warnings": cp.warnings,
            }
            for cp in scene.checkpoints
        ],
        "ground_tracks": [
            {
                "name": gt.name,
                "spacecraft": gt.spacecraft,
                "body": gt.body,
                "file": _relative(gt.path, paths.mission_dir),
                "time_column": gt.time_col,
                "latitude_column": gt.latitude_col,
                "longitude_column": gt.longitude_col,
                "altitude_column": gt.altitude_col,
                "rows": int(len(gt.dataframe)),
                "warnings": gt.warnings,
            }
            for gt in scene.ground_tracks
        ],
        "frames": [f.__dict__ for f in scene.frames],
        "warnings": scene.warnings,
    }
    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return output_path

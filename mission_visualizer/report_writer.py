from __future__ import annotations

import json
from pathlib import Path

from .models import MissionScene, MissionPaths


def write_report(scene: MissionScene, paths: MissionPaths, output: str | Path | None = None) -> Path:
    output_path = Path(output) if output else (paths.visualization_dir or (paths.mission_dir / "visualization")) / "visualization_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "mission_id": scene.mission_id,
        "paths": {
            "mission_root": str(paths.mission_root),
            "mission_dir": str(paths.mission_dir),
            "outputs_dir": str(paths.outputs_dir),
            "targeting_dir": str(paths.targeting_dir) if paths.targeting_dir else None,
            "target_problem": str(paths.target_problem) if paths.target_problem else None,
            "targeting_result": str(paths.targeting_result) if paths.targeting_result else None,
            "candidate_mission_spec": str(paths.candidate_mission_spec) if paths.candidate_mission_spec else None,
        },
        "spacecraft_ephemerides": [
            {
                "name": t.name,
                "object": t.object_name,
                "frame": t.frame,
                "file": str(t.path.relative_to(paths.mission_dir) if t.path.is_relative_to(paths.mission_dir) else t.path),
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
                "file": str(t.path.relative_to(paths.mission_dir) if t.path.is_relative_to(paths.mission_dir) else t.path),
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
                "file": str(cp.path.relative_to(paths.mission_dir) if cp.path.is_relative_to(paths.mission_dir) else cp.path),
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
                "file": str(gt.path.relative_to(paths.mission_dir) if gt.path.is_relative_to(paths.mission_dir) else gt.path),
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

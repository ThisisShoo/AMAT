from __future__ import annotations

from pathlib import Path

from .checkpoint_loader import interpolate_checkpoints, load_checkpoints
from .discovery import body_ephemeris_files, checkpoint_files, discover_mission, ground_track_files, spacecraft_ephemeris_files
from .ephemeris_loader import load_body_ephemerides, load_spacecraft_ephemerides
from .frame_resolver import load_manifest, resolve_frames
from .ground_track_loader import load_ground_tracks
from .models import FrameInfo, MissionScene


def _apply_ground_track_frames(frames: list[FrameInfo], ground_tracks: list[object]) -> list[FrameInfo]:
    by_name = {frame.name: frame for frame in frames if frame.name}
    for track in ground_tracks:
        body = getattr(track, "body", None) or "Earth"
        name = f"{body}Fixed"
        existing = by_name.get(name)
        if existing:
            if not existing.origin:
                existing.origin = body
            if not existing.axes:
                existing.axes = "Fixed"
            if existing.source in {"unknown", "output_parameter"}:
                existing.source = "ground_track"
                existing.confidence = "high"
        else:
            frame = FrameInfo(name=name, origin=body, axes="Fixed", source="ground_track", confidence="high")
            frames.append(frame)
            by_name[name] = frame
    return frames


def build_scene(
    project_root: str | Path,
    mission_id: str | None = None,
    mission_dir: str | Path | None = None,
) -> tuple[MissionScene, object]:
    paths = discover_mission(project_root, mission_id=mission_id, mission_dir=mission_dir)
    manifest = load_manifest(paths)
    warnings: list[str] = []
    warnings.extend(str(w) for w in manifest.get("warnings", []) if manifest)

    sc_files = spacecraft_ephemeris_files(paths.outputs_dir)
    body_files = body_ephemeris_files(paths.outputs_dir)
    cp_files = checkpoint_files(paths.outputs_dir)
    gt_files = ground_track_files(paths.outputs_dir)

    if not sc_files:
        warnings.append(f"No spacecraft ephemeris files found using {paths.outputs_dir / '*.eph.csv'}")

    sc_traces = load_spacecraft_ephemerides(sc_files, manifest)
    body_traces = load_body_ephemerides(body_files, manifest)
    checkpoints = load_checkpoints(cp_files, manifest)
    ground_tracks = load_ground_tracks(gt_files, manifest)
    interpolate_checkpoints(checkpoints, sc_traces)
    frames = _apply_ground_track_frames(resolve_frames(paths, manifest), ground_tracks)

    for trace in sc_traces + body_traces:
        warnings.extend(trace.warnings)
    for checkpoint in checkpoints:
        warnings.extend([f"{checkpoint.name}: {warning}" for warning in checkpoint.warnings])
    for ground_track in ground_tracks:
        warnings.extend([f"{ground_track.name}: {warning}" for warning in ground_track.warnings])

    scene = MissionScene(
        mission_id=paths.mission_id,
        spacecraft_traces=sc_traces,
        body_traces=body_traces,
        checkpoints=checkpoints,
        frames=frames,
        warnings=warnings,
        ground_tracks=ground_tracks,
        manifest=manifest,
    )
    return scene, paths

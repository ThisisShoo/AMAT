from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MissionPaths:
    project_root: Path
    mission_id: str
    generated_dir: Path
    mission_root: Path
    mission_dir: Path
    outputs_dir: Path
    targeting_dir: Path | None = None
    target_problem: Path | None = None
    targeting_result: Path | None = None
    candidate_mission_spec: Path | None = None
    examples_spec: Path | None = None
    canonical_spec: Path | None = None
    gmat_script: Path | None = None
    visualization_manifest: Path | None = None
    visualization_dir: Path | None = None


@dataclass
class FrameInfo:
    name: str
    origin: str | None = None
    axes: str | None = None
    source: str = "unknown"
    confidence: str = "low"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class EphemerisTrace:
    name: str
    kind: str  # spacecraft or body
    object_name: str
    frame: str | None
    path: Path
    time_col: str
    x_col: str
    y_col: str
    z_col: str
    dataframe: Any
    warnings: list[str] = field(default_factory=list)


@dataclass
class Checkpoint:
    name: str
    path: Path
    row: dict[str, Any]
    time_col: str | None
    elapsed_secs: float | None
    utc_gregorian: str | None
    spacecraft: str | None = None
    frame: str | None = None
    plotted: bool = False
    interpolated_xyz: tuple[float, float, float] | None = None
    matched_trace: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class GroundTrack:
    name: str
    spacecraft: str | None
    body: str | None
    path: Path
    time_col: str | None
    latitude_col: str | None
    longitude_col: str | None
    altitude_col: str | None
    dataframe: Any
    warnings: list[str] = field(default_factory=list)


@dataclass
class MissionScene:
    mission_id: str
    spacecraft_traces: list[EphemerisTrace]
    body_traces: list[EphemerisTrace]
    checkpoints: list[Checkpoint]
    frames: list[FrameInfo]
    warnings: list[str]
    ground_tracks: list[GroundTrack] = field(default_factory=list)
    manifest: dict[str, Any] = field(default_factory=dict)

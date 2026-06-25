from __future__ import annotations

from pathlib import Path

from .models import MissionPaths


def _is_mission_dir(path: Path) -> bool:
    return path.is_dir() and (path / "outputs").is_dir()


def _is_targeting_dir(path: Path) -> bool:
    return path.is_dir() and (
        (path / "candidate_mission_spec.json").is_file()
        or (path / "targeting_result.json").is_file()
        or (path / "target_problem.canonical.json").is_file()
    )


def _infer_project_root(mission_dir: Path, fallback: Path) -> Path:
    """Best-effort project-root inference without requiring a fixed nesting depth."""
    for parent in (mission_dir, *mission_dir.parents):
        if (parent / "generated").is_dir() or (parent / "pyproject.toml").is_file():
            return parent
    return fallback


def _mission_id_from_dir(mission_dir: Path) -> str:
    if mission_dir.name in {"simulation", "targeting"}:
        return mission_dir.parent.name
    return mission_dir.name


def _mission_root_from_dir(mission_dir: Path) -> Path:
    if mission_dir.name in {"simulation", "targeting"}:
        return mission_dir.parent
    return mission_dir


def _candidate_mission_dirs(base: Path) -> list[Path]:
    """Return renderable mission directories in preference order."""
    candidates = [
        base / "simulation",
        base,
    ]
    if base.name == "simulation":
        candidates.insert(0, base)
    if base.name == "targeting":
        candidates.insert(0, base.parent / "simulation")
        candidates.append(base.parent)
    return list(dict.fromkeys(candidates))


def _resolve_explicit_mission_dir(project_root: Path, mission_dir: str | Path) -> Path:
    candidate = Path(mission_dir).expanduser()
    if not candidate.is_absolute():
        candidate = project_root / candidate
    candidate = candidate.resolve()

    for path in _candidate_mission_dirs(candidate):
        if _is_mission_dir(path):
            return path.resolve()

    searched = "\n  - ".join(str(path / "outputs") for path in _candidate_mission_dirs(candidate))
    raise FileNotFoundError(
        "Mission outputs folder not found. Searched:\n  - "
        f"{searched}"
    )


def discover_mission(
    project_root: str | Path,
    mission_id: str | None = None,
    mission_dir: str | Path | None = None,
) -> MissionPaths:
    """Discover a visualizable mission artifact directory.

    Supported layouts include:

    * ``<root>/generated/<mission_id>/outputs``
    * ``<root>/generated/<mission_id>/targeting``
    * ``<root>/generated/<mission_id>/simulation/outputs``
    * ``<root>/<mission_id>/outputs``
    * ``<root>/<mission_id>/targeting``
    * ``<root>/<mission_id>/simulation/outputs``
    * an explicit ``--mission-dir`` pointing at either the mission directory
      or its parent/sibling ``targeting/`` or ``simulation/`` directory.
    """
    requested_root = Path(project_root).expanduser().resolve()

    if mission_dir is not None:
        resolved_mission_dir = _resolve_explicit_mission_dir(requested_root, mission_dir)
        resolved_mission_id = mission_id or _mission_id_from_dir(resolved_mission_dir)
    else:
        if not mission_id:
            raise ValueError("mission_id is required unless mission_dir is provided")

        candidates = [
            requested_root / "generated" / mission_id / "simulation",
            requested_root / "generated" / mission_id,
            requested_root / mission_id / "simulation",
            requested_root / mission_id,
        ]

        # Also support invoking from a mission bundle, its simulation dir, or its targeting dir.
        if requested_root.name == mission_id:
            candidates.extend([requested_root / "simulation", requested_root])
        if requested_root.name == "simulation" and requested_root.parent.name == mission_id:
            candidates.append(requested_root)
        if requested_root.name == "targeting" and requested_root.parent.name == mission_id:
            candidates.extend([requested_root.parent / "simulation", requested_root.parent])

        resolved_mission_dir = next((path.resolve() for path in candidates if _is_mission_dir(path)), None)
        if resolved_mission_dir is None:
            searched = "\n  - ".join(str(path / "outputs") for path in candidates)
            raise FileNotFoundError(f"Mission outputs folder not found. Searched:\n  - {searched}")
        resolved_mission_id = mission_id

    root = _infer_project_root(resolved_mission_dir, requested_root)
    mission_root = _mission_root_from_dir(resolved_mission_dir)
    generated_dir = mission_root.parent
    outputs_dir = resolved_mission_dir / "outputs"
    targeting_dir = mission_root / "targeting"

    examples_spec = root / "examples" / resolved_mission_id / "mission_spec.json"
    canonical_spec = resolved_mission_dir / "mission_spec.canonical.json"
    gmat_script = resolved_mission_dir / "generated_mission.script"
    manifest = resolved_mission_dir / "visualization_manifest.json"
    visualization_dir = resolved_mission_dir / "visualization"
    target_problem = targeting_dir / "target_problem.canonical.json"
    targeting_result = targeting_dir / "targeting_result.json"
    candidate_mission_spec = targeting_dir / "candidate_mission_spec.json"

    return MissionPaths(
        project_root=root,
        mission_id=resolved_mission_id,
        generated_dir=generated_dir,
        mission_root=mission_root,
        mission_dir=resolved_mission_dir,
        outputs_dir=outputs_dir,
        targeting_dir=targeting_dir if _is_targeting_dir(targeting_dir) else None,
        target_problem=target_problem if target_problem.exists() else None,
        targeting_result=targeting_result if targeting_result.exists() else None,
        candidate_mission_spec=candidate_mission_spec if candidate_mission_spec.exists() else None,
        examples_spec=examples_spec if examples_spec.exists() else None,
        canonical_spec=canonical_spec if canonical_spec.exists() else None,
        gmat_script=gmat_script if gmat_script.exists() else None,
        visualization_manifest=manifest if manifest.exists() else None,
        visualization_dir=visualization_dir,
    )


def spacecraft_ephemeris_files(outputs_dir: Path) -> list[Path]:
    return sorted(outputs_dir.glob("_Ephemeris*.csv"))


def body_ephemeris_files(outputs_dir: Path) -> list[Path]:
    return sorted(outputs_dir.glob("_BodyEphemeris*.csv"))


def checkpoint_files(outputs_dir: Path) -> list[Path]:
    excluded_prefixes = ("_Ephemeris", "_BodyEphemeris", "_GroundTrack")
    excluded_names = {"final_state.csv"}
    return sorted(p for p in outputs_dir.glob("*.csv") if not p.name.startswith(excluded_prefixes) and p.name not in excluded_names)


def ground_track_files(outputs_dir: Path) -> list[Path]:
    return sorted(outputs_dir.glob("_GroundTrack*.csv"))

from pathlib import Path

import pytest

from visualizer.discovery import checkpoint_files, discover_mission


def _make_outputs(path: Path) -> Path:
    outputs = path / "outputs"
    outputs.mkdir(parents=True)
    return outputs


def test_discovers_classic_generated_layout(tmp_path: Path) -> None:
    mission_dir = tmp_path / "generated" / "demo"
    _make_outputs(mission_dir)

    paths = discover_mission(tmp_path, mission_id="demo")

    assert paths.mission_dir == mission_dir.resolve()
    assert paths.mission_id == "demo"


def test_auto_discovers_nested_simulation_layout(tmp_path: Path) -> None:
    mission_dir = tmp_path / "generated" / "demo" / "simulation"
    _make_outputs(mission_dir)

    paths = discover_mission(tmp_path, mission_id="demo")

    assert paths.mission_dir == mission_dir.resolve()
    assert paths.outputs_dir == (mission_dir / "outputs").resolve()
    assert paths.mission_root == (tmp_path / "generated" / "demo").resolve()


def test_discovers_targeting_simulation_bundle(tmp_path: Path) -> None:
    mission_root = tmp_path / "generated" / "demo"
    targeting_dir = mission_root / "targeting"
    simulation_dir = mission_root / "simulation"
    _make_outputs(simulation_dir)
    targeting_dir.mkdir(parents=True)
    target_result = targeting_dir / "targeting_result.json"
    target_result.write_text("{}", encoding="utf-8")
    candidate_spec = targeting_dir / "candidate_mission_spec.json"
    candidate_spec.write_text('{"frames": [{"name": "EarthMJ2000Eq"}]}', encoding="utf-8")

    paths = discover_mission(tmp_path, mission_id="demo")

    assert paths.mission_root == mission_root.resolve()
    assert paths.mission_dir == simulation_dir.resolve()
    assert paths.targeting_dir == targeting_dir.resolve()
    assert paths.targeting_result == target_result.resolve()
    assert paths.candidate_mission_spec == candidate_spec.resolve()


def test_nested_simulation_is_preferred_over_parent_outputs(tmp_path: Path) -> None:
    mission_root = tmp_path / "generated" / "demo"
    _make_outputs(mission_root)
    simulation_dir = mission_root / "simulation"
    _make_outputs(simulation_dir)

    paths = discover_mission(tmp_path, mission_id="demo")

    assert paths.mission_dir == simulation_dir.resolve()


def test_explicit_mission_dir_accepts_simulation_directory(tmp_path: Path) -> None:
    mission_dir = tmp_path / "generated" / "demo" / "simulation"
    _make_outputs(mission_dir)

    paths = discover_mission(tmp_path, mission_dir=mission_dir)

    assert paths.mission_id == "demo"
    assert paths.mission_dir == mission_dir.resolve()


def test_explicit_mission_dir_accepts_parent_containing_simulation(tmp_path: Path) -> None:
    parent = tmp_path / "generated" / "demo"
    mission_dir = parent / "simulation"
    _make_outputs(mission_dir)

    paths = discover_mission(tmp_path, mission_dir=parent)

    assert paths.mission_id == "demo"
    assert paths.mission_dir == mission_dir.resolve()


def test_explicit_mission_dir_accepts_targeting_directory(tmp_path: Path) -> None:
    parent = tmp_path / "generated" / "demo"
    mission_dir = parent / "simulation"
    targeting_dir = parent / "targeting"
    _make_outputs(mission_dir)
    targeting_dir.mkdir(parents=True)
    (targeting_dir / "target_problem.canonical.json").write_text("{}", encoding="utf-8")

    paths = discover_mission(tmp_path, mission_dir=targeting_dir)

    assert paths.mission_id == "demo"
    assert paths.mission_dir == mission_dir.resolve()
    assert paths.target_problem == (targeting_dir / "target_problem.canonical.json").resolve()


def test_missing_outputs_reports_search_locations(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Searched"):
        discover_mission(tmp_path, mission_id="missing")


def test_checkpoint_discovery_ignores_final_state_output(tmp_path: Path) -> None:
    outputs = _make_outputs(tmp_path / "mission")
    (outputs / "initial_state.csv").write_text("x\n", encoding="utf-8")
    (outputs / "final_state.csv").write_text("x\n", encoding="utf-8")
    (outputs / "final_state_checkpoint.csv").write_text("x\n", encoding="utf-8")

    assert [path.name for path in checkpoint_files(outputs)] == ["final_state_checkpoint.csv", "initial_state.csv"]


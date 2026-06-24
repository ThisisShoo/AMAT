from pathlib import Path

import pandas as pd

from visualizer.checkpoint_loader import interpolate_checkpoints, load_checkpoints
from visualizer.models import Checkpoint, EphemerisTrace, FrameInfo, GroundTrack, MissionPaths, MissionScene
from visualizer.report_writer import write_report
from visualizer.three_renderer import render_three_html


def test_three_renderer_writes_viewer_with_finite_burns(tmp_path: Path) -> None:
    outputs = tmp_path / "generated" / "demo" / "simulation" / "outputs"
    outputs.mkdir(parents=True)
    visualization = outputs.parent / "visualization"
    trace_path = outputs / "_Ephemeris_DemoSat_EarthMJ2000Eq.csv"
    df = pd.DataFrame(
        {
            "DemoSat.ElapsedSecs": [0.0, 10.0, 20.0],
            "DemoSat.EarthMJ2000Eq.X": [7000.0, 7010.0, 7020.0],
            "DemoSat.EarthMJ2000Eq.Y": [0.0, 10.0, 20.0],
            "DemoSat.EarthMJ2000Eq.Z": [0.0, 0.0, 0.0],
        }
    )
    trace = EphemerisTrace(
        name="DemoSat (EarthMJ2000Eq)",
        kind="spacecraft",
        object_name="DemoSat",
        frame="EarthMJ2000Eq",
        path=trace_path,
        time_col="DemoSat.ElapsedSecs",
        x_col="DemoSat.EarthMJ2000Eq.X",
        y_col="DemoSat.EarthMJ2000Eq.Y",
        z_col="DemoSat.EarthMJ2000Eq.Z",
        dataframe=df,
    )
    ground_df = pd.DataFrame(
        {
            "DemoSat.ElapsedSecs": [0.0, 10.0, 20.0],
            "DemoSat.Earth.Latitude": [0.0, 1.0, 2.0],
            "DemoSat.Earth.Longitude": [10.0, 11.0, 12.0],
            "DemoSat.Earth.Altitude": [400.0, 410.0, 420.0],
        }
    )
    ground_track = GroundTrack(
        name="DemoSat ground track (Earth)",
        spacecraft="DemoSat",
        body="Earth",
        path=outputs / "_GroundTrack_DemoSat_Earth.csv",
        time_col="DemoSat.ElapsedSecs",
        latitude_col="DemoSat.Earth.Latitude",
        longitude_col="DemoSat.Earth.Longitude",
        altitude_col="DemoSat.Earth.Altitude",
        dataframe=ground_df,
    )
    scene = MissionScene(
        mission_id="demo",
        spacecraft_traces=[trace],
        body_traces=[],
        checkpoints=[],
        frames=[FrameInfo(name="EarthMJ2000Eq", origin="Earth", axes="MJ2000Eq")],
        warnings=[],
        ground_tracks=[ground_track],
        manifest={
            "finite_burns": [
                {
                    "name": "Demo finite burn",
                    "spacecraft": "DemoSat",
                    "start_elapsed_s": 5.0,
                    "end_elapsed_s": 15.0,
                }
            ]
        },
    )
    paths = MissionPaths(
        project_root=tmp_path,
        mission_id="demo",
        generated_dir=tmp_path / "generated",
        mission_root=tmp_path / "generated" / "demo",
        mission_dir=outputs.parent,
        outputs_dir=outputs,
        visualization_dir=visualization,
    )

    html_path = render_three_html(scene, paths)

    html = html_path.read_text(encoding="utf-8")
    assert "three@0.160.0" in html
    assert "requestFullscreen" in html
    assert "Demo finite burn" in html
    assert '"origin": "Earth"' in html
    assert "addReferenceVectors" in html
    assert "addXYPlaneRings" in html
    assert "camera.up.set(0, 0, 1)" in html
    assert "mesh.rotation.x = Math.PI / 2" in html
    assert "land_ocean_ice_2048.jpg" in html
    assert "TextureLoader" in html
    assert "dragMode" in html
    assert "activeDragMode === 'move'" in html
    assert "WebGLRenderer" in html
    assert "getBoundingClientRect" in html
    assert "getWorldPosition" in html
    assert '"frame": "EarthFixed"' in html
    assert '"source": "ground_track"' in html
    assert "latLonToWorld" in html
    assert "interpolateGroundTrack" in html
    assert "groundTrackAltitude" in html
    assert "3D Earth-fixed path" in html
    assert "surface projection" in html
    assert "altitude above surface" in html
    assert "sceneMarkerRadius('checkpoint')" in html
    assert "bodyLimit * 0.35" in html
    assert "return (meta.radius_km || extentKm * 0.01) * scale;" in html
    assert "Math.max(bodyRadiusFloor" not in html
    assert "const DATA =" in html
    assert '"points": [[7000.0, 0.0, 0.0]' in html
    assert '"latitude": [0.0, 1.0, 2.0]' in html
    assert '"path": "outputs/_Ephemeris_DemoSat_EarthMJ2000Eq.csv"' in html
    assert "outputs\\\\" not in html
    assert str(tmp_path) not in html
    assert "fetch(" not in html


def test_visualization_report_uses_portable_paths(tmp_path: Path) -> None:
    mission_root = tmp_path / "generated" / "demo"
    outputs = mission_root / "simulation" / "outputs"
    visualization = mission_root / "simulation" / "visualization"
    outputs.mkdir(parents=True)
    trace_path = outputs / "_Ephemeris_DemoSat_EarthMJ2000Eq.csv"
    df = pd.DataFrame(
        {
            "DemoSat.ElapsedSecs": [0.0],
            "DemoSat.EarthMJ2000Eq.X": [7000.0],
            "DemoSat.EarthMJ2000Eq.Y": [0.0],
            "DemoSat.EarthMJ2000Eq.Z": [0.0],
        }
    )
    trace = EphemerisTrace(
        name="DemoSat (EarthMJ2000Eq)",
        kind="spacecraft",
        object_name="DemoSat",
        frame="EarthMJ2000Eq",
        path=trace_path,
        time_col="DemoSat.ElapsedSecs",
        x_col="DemoSat.EarthMJ2000Eq.X",
        y_col="DemoSat.EarthMJ2000Eq.Y",
        z_col="DemoSat.EarthMJ2000Eq.Z",
        dataframe=df,
    )
    scene = MissionScene(
        mission_id="demo",
        spacecraft_traces=[trace],
        body_traces=[],
        checkpoints=[],
        frames=[FrameInfo(name="EarthMJ2000Eq", origin="Earth", axes="MJ2000Eq")],
        warnings=[],
    )
    paths = MissionPaths(
        project_root=tmp_path,
        mission_id="demo",
        generated_dir=tmp_path / "generated",
        mission_root=mission_root,
        mission_dir=mission_root / "simulation",
        outputs_dir=outputs,
        visualization_dir=visualization,
    )

    report_path = write_report(scene, paths)

    report = report_path.read_text(encoding="utf-8")
    assert '"mission_dir": "simulation"' in report
    assert '"file": "outputs/_Ephemeris_DemoSat_EarthMJ2000Eq.csv"' in report
    assert "outputs\\\\" not in report
    assert str(tmp_path) not in report


from pathlib import Path

from visualizer.discovery import body_ephemeris_files, spacecraft_ephemeris_files
from visualizer.ephemeris_loader import load_body_ephemerides, load_spacecraft_ephemerides


def _write_ephemeris(path: Path, frame: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"Sat.ElapsedSecs,Sat.{frame}.X,Sat.{frame}.Y,Sat.{frame}.Z",
                "0,1,2,3",
            ]
        ),
        encoding="utf-8",
    )


def test_spacecraft_ephemeris_loader_uses_manifest_as_file_allowlist(tmp_path: Path) -> None:
    active = tmp_path / "Sat_EarthMJ2000Eq.eph.csv"
    stale = tmp_path / "Sat_EarthFixed.eph.csv"
    _write_ephemeris(active, "EarthMJ2000Eq")
    _write_ephemeris(stale, "EarthFixed")

    manifest = {
        "spacecraft_ephemerides": [
            {
                "file": "outputs/Sat_EarthMJ2000Eq.eph.csv",
                "spacecraft": "Sat",
                "frame": "EarthMJ2000Eq",
            }
        ]
    }

    traces = load_spacecraft_ephemerides([active, stale], manifest)

    assert [trace.path for trace in traces] == [active]
    assert [trace.frame for trace in traces] == ["EarthMJ2000Eq"]


def test_ephemeris_discovery_uses_modern_suffixes_only(tmp_path: Path) -> None:
    spacecraft = tmp_path / "Sat_EarthMJ2000Eq.eph.csv"
    body = tmp_path / "Luna_EarthMJ2000Eq.body.eph.csv"
    legacy_spacecraft = tmp_path / "_Ephemeris_Sat_EarthMJ2000Eq.csv"
    legacy_body = tmp_path / "_BodyEphemeris_Luna_EarthMJ2000Eq.csv"
    for path in (spacecraft, body, legacy_spacecraft, legacy_body):
        path.write_text("x\n", encoding="utf-8")

    assert spacecraft_ephemeris_files(tmp_path) == [spacecraft]
    assert body_ephemeris_files(tmp_path) == [body]


def test_ephemeris_loader_infers_modern_filename_metadata_without_manifest(tmp_path: Path) -> None:
    spacecraft = tmp_path / "DemoSat_EarthMJ2000Eq.eph.csv"
    body = tmp_path / "Luna_EarthMJ2000Eq.body.eph.csv"
    spacecraft.write_text(
        "\n".join(
            [
                "DemoSat.ElapsedSecs,DemoSat.EarthMJ2000Eq.X,DemoSat.EarthMJ2000Eq.Y,DemoSat.EarthMJ2000Eq.Z",
                "0,1,2,3",
            ]
        ),
        encoding="utf-8",
    )
    body.write_text(
        "\n".join(
            [
                "Luna.ElapsedSecs,Luna.EarthMJ2000Eq.X,Luna.EarthMJ2000Eq.Y,Luna.EarthMJ2000Eq.Z",
                "0,1,2,3",
            ]
        ),
        encoding="utf-8",
    )

    sc_trace = load_spacecraft_ephemerides([spacecraft])[0]
    body_trace = load_body_ephemerides([body])[0]

    assert sc_trace.object_name == "DemoSat"
    assert sc_trace.frame == "EarthMJ2000Eq"
    assert body_trace.object_name == "Luna"
    assert body_trace.frame == "EarthMJ2000Eq"


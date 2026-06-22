from pathlib import Path

from visualzer.ephemeris_loader import load_spacecraft_ephemerides


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
    active = tmp_path / "_Ephemeris_Sat_EarthMJ2000Eq.csv"
    stale = tmp_path / "_Ephemeris_Sat_EarthFixed.csv"
    _write_ephemeris(active, "EarthMJ2000Eq")
    _write_ephemeris(stale, "EarthFixed")

    manifest = {
        "spacecraft_ephemerides": [
            {
                "file": "outputs/_Ephemeris_Sat_EarthMJ2000Eq.csv",
                "spacecraft": "Sat",
                "frame": "EarthMJ2000Eq",
            }
        ]
    }

    traces = load_spacecraft_ephemerides([active, stale], manifest)

    assert [trace.path for trace in traces] == [active]
    assert [trace.frame for trace in traces] == ["EarthMJ2000Eq"]


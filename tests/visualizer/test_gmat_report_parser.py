from __future__ import annotations

import pandas as pd

from visualizer.gmat_report_parser import normalize_gmat_report_csv, parse_gmat_report


def test_normalize_gmat_report_csv_removes_repeated_headers(tmp_path):
    path = tmp_path / "TestSat_EarthMJ2000Eq.eph.csv"
    header = (
        "TestSat.UTCGregorian   TestSat.ElapsedSecs   "
        "TestSat.EarthMJ2000Eq.X   TestSat.EarthMJ2000Eq.Y"
    )
    path.write_text(
        "\n".join(
            [
                header,
                "01 Nov 2026 00:00:00.000,0,1.0,2.0",
                header,
                "01 Nov 2026 00:30:00.000,1800,3.0,4.0",
                header,
                "01 Nov 2026 01:00:00.000,3600,5.0,6.0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = normalize_gmat_report_csv(path)
    df = pd.read_csv(path)

    assert result["rows"] == 3
    assert list(df.columns) == [
        "TestSat.UTCGregorian",
        "TestSat.ElapsedSecs",
        "TestSat.EarthMJ2000Eq.X",
        "TestSat.EarthMJ2000Eq.Y",
    ]
    assert df["TestSat.ElapsedSecs"].tolist() == [0.0, 1800.0, 3600.0]
    assert not df.astype(str).eq(pd.Series(df.columns, index=df.columns), axis=1).any().any()


def test_parse_gmat_report_preserves_fixed_width_gregorian_timestamp(tmp_path):
    path = tmp_path / "checkpoint.csv"
    path.write_text(
        "\n".join(
            [
                "TestSat.UTCGregorian   TestSat.ElapsedSecs   TestSat.EarthMJ2000Eq.X",
                "01 Nov 2026 23:39:34.318     85174.31820456404           2230.807304476155",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    df = parse_gmat_report(path)

    assert list(df.columns) == [
        "TestSat.UTCGregorian",
        "TestSat.ElapsedSecs",
        "TestSat.EarthMJ2000Eq.X",
    ]
    assert df.iloc[0]["TestSat.UTCGregorian"] == "01 Nov 2026 23:39:34.318"
    assert df.iloc[0]["TestSat.ElapsedSecs"] == 85174.31820456404

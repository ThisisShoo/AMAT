from __future__ import annotations

from pathlib import Path
from typing import Any

from .gmat_report_parser import parse_gmat_report, resolve_time_column
from .models import GroundTrack


def _manifest_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    val = manifest.get("ground_tracks", []) if manifest else []
    return val if isinstance(val, list) else []


def _entry_for_path(entries: list[dict[str, Any]], path: Path) -> dict[str, Any] | None:
    for e in entries:
        f = str(e.get("file", ""))
        if f and (f.endswith(path.name) or Path(f).name == path.name):
            return e
    return None


def _resolve_named(cols: list[str], explicit: str | None, suffix: str) -> str | None:
    if explicit and explicit in cols:
        return explicit
    for col in cols:
        if col == suffix or col.endswith(f".{suffix}"):
            return col
    return None


def load_ground_tracks(paths: list[Path], manifest: dict[str, Any] | None = None) -> list[GroundTrack]:
    entries = _manifest_entries(manifest or {})
    tracks: list[GroundTrack] = []
    for path in paths:
        entry = _entry_for_path(entries, path) or {}
        df = parse_gmat_report(path)
        cols = list(df.columns)
        warnings: list[str] = []
        time_col = resolve_time_column(cols, entry.get("time_columns"))
        lat_col = _resolve_named(cols, entry.get("latitude_column"), "Latitude")
        lon_col = _resolve_named(cols, entry.get("longitude_column"), "Longitude")
        alt_col = _resolve_named(cols, entry.get("altitude_column"), "Altitude")
        if not time_col:
            warnings.append("No usable time column found.")
        if not lat_col or not lon_col:
            warnings.append("No complete latitude/longitude column pair found.")
        spacecraft = entry.get("spacecraft")
        body = entry.get("body") or "Earth"
        name = f"{spacecraft or path.stem} ground track ({body})"
        tracks.append(
            GroundTrack(
                name=name,
                spacecraft=spacecraft,
                body=body,
                path=path,
                time_col=time_col,
                latitude_col=lat_col,
                longitude_col=lon_col,
                altitude_col=alt_col,
                dataframe=df,
                warnings=warnings,
            )
        )
    return tracks

from __future__ import annotations

from pathlib import Path
from typing import Any

from .gmat_report_parser import infer_object_frame_from_columns, parse_gmat_report, resolve_column, resolve_time_column
from .models import EphemerisTrace


def _manifest_entries(manifest: dict[str, Any], key: str) -> list[dict[str, Any]]:
    val = manifest.get(key, []) if manifest else []
    return val if isinstance(val, list) else []


def _entry_for_path(entries: list[dict[str, Any]], path: Path) -> dict[str, Any] | None:
    for e in entries:
        f = str(e.get("file", ""))
        if f and (f.endswith(path.name) or Path(f).name == path.name):
            return e
    return None


def _infer_object_frame_from_filename(path: Path, kind: str) -> tuple[str | None, str | None]:
    name = path.name
    if kind == "body" and name.endswith(".body.eph.csv"):
        stem = name[: -len(".body.eph.csv")]
    elif kind == "spacecraft" and name.endswith(".eph.csv") and not name.endswith(".body.eph.csv"):
        stem = name[: -len(".eph.csv")]
    else:
        return None, None

    if "_" not in stem:
        return stem or None, None
    object_name, frame = stem.rsplit("_", 1)
    return object_name or None, frame or None


def _load_trace(path: Path, kind: str, manifest_entry: dict[str, Any] | None = None) -> EphemerisTrace:
    df = parse_gmat_report(path)
    warnings: list[str] = []
    cols = list(df.columns)
    object_name, frame = infer_object_frame_from_columns(cols)
    file_object_name, file_frame = _infer_object_frame_from_filename(path, kind)

    if manifest_entry:
        object_name = manifest_entry.get("spacecraft") or manifest_entry.get("body") or object_name
        frame = manifest_entry.get("frame") or frame
    else:
        object_name = object_name or file_object_name
        frame = frame or file_frame

    time_hints = manifest_entry.get("time_columns") if manifest_entry else None
    time_col = resolve_time_column(cols, time_hints)

    position_hints = manifest_entry.get("position_columns") if manifest_entry else None
    if isinstance(position_hints, list) and len(position_hints) >= 3:
        x_hint, y_hint, z_hint = position_hints[:3]
    else:
        x_hint = y_hint = z_hint = None

    x_col = resolve_column(cols, x_hint, ["X"])
    y_col = resolve_column(cols, y_hint, ["Y"])
    z_col = resolve_column(cols, z_hint, ["Z"])

    if not time_col:
        warnings.append(f"No usable time column found in {path.name}.")
    if not all([x_col, y_col, z_col]):
        warnings.append(f"No complete X/Y/Z column set found in {path.name}.")

    if not object_name:
        object_name = path.name.removesuffix(".csv")

    name = f"{object_name} ({frame or 'unknown frame'})"
    return EphemerisTrace(
        name=name,
        kind=kind,
        object_name=object_name,
        frame=frame,
        path=path,
        time_col=time_col or "",
        x_col=x_col or "",
        y_col=y_col or "",
        z_col=z_col or "",
        dataframe=df,
        warnings=warnings,
    )


def load_spacecraft_ephemerides(paths: list[Path], manifest: dict[str, Any] | None = None) -> list[EphemerisTrace]:
    entries = _manifest_entries(manifest or {}, "spacecraft_ephemerides")
    traces: list[EphemerisTrace] = []
    for path in paths:
        entry = _entry_for_path(entries, path)
        if entries and entry is None:
            continue
        traces.append(_load_trace(path, "spacecraft", entry))
    return traces


def load_body_ephemerides(paths: list[Path], manifest: dict[str, Any] | None = None) -> list[EphemerisTrace]:
    entries = _manifest_entries(manifest or {}, "body_ephemerides")
    traces: list[EphemerisTrace] = []
    for path in paths:
        entry = _entry_for_path(entries, path)
        if entries and entry is None:
            continue
        traces.append(_load_trace(path, "body", entry))
    return traces

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .gmat_report_parser import infer_object_frame_from_columns, parse_gmat_report, resolve_time_column
from .models import Checkpoint, EphemerisTrace


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, float) and np.isnan(value):
            return None
        return float(value)
    except Exception:
        return None


def _checkpoint_manifest_entry(manifest: dict[str, Any], path: Path) -> dict[str, Any] | None:
    for e in manifest.get("checkpoints", []) if manifest else []:
        f = str(e.get("file", ""))
        if f.endswith(path.name) or Path(f).name == path.name:
            return e
    return None


def load_checkpoints(paths: list[Path], manifest: dict[str, Any] | None = None) -> list[Checkpoint]:
    checkpoints: list[Checkpoint] = []
    for p in paths:
        entry = _checkpoint_manifest_entry(manifest or {}, p)
        df = parse_gmat_report(p)
        warnings: list[str] = []
        if df.empty:
            checkpoints.append(Checkpoint(p.stem, p, {}, None, None, None, warnings=["Checkpoint file is empty."]))
            continue
        row = df.iloc[0].to_dict()
        cols = list(df.columns)
        hints = entry.get("time_columns") if entry else None
        time_col = resolve_time_column(cols, hints)
        elapsed_col = None
        for c in cols:
            if c == "ElapsedSecs" or c.endswith(".ElapsedSecs"):
                elapsed_col = c
                break
        utc_col = None
        for c in cols:
            if c == "UTCGregorian" or c.endswith(".UTCGregorian"):
                utc_col = c
                break
        obj, frame = infer_object_frame_from_columns(cols)
        spacecraft = (entry or {}).get("spacecraft") or obj
        frame = (entry or {}).get("frame") or frame
        elapsed = _as_float(row.get(elapsed_col)) if elapsed_col else None
        utc = str(row.get(utc_col)) if utc_col and row.get(utc_col) is not None else None
        if not time_col:
            warnings.append("No usable timestamp found; checkpoint cannot be plotted.")
        checkpoints.append(Checkpoint(p.stem, p, row, time_col, elapsed, utc, spacecraft, frame, warnings=warnings))
    return checkpoints


def interpolate_checkpoints(checkpoints: list[Checkpoint], traces: list[EphemerisTrace]) -> None:
    for cp in checkpoints:
        if cp.elapsed_secs is None:
            continue
        candidates = [t for t in traces if t.kind == "spacecraft" and (not cp.spacecraft or t.object_name == cp.spacecraft)]
        if not candidates:
            candidates = [t for t in traces if t.kind == "spacecraft"]
        for trace in candidates:
            df = trace.dataframe
            if not trace.time_col or trace.time_col not in df or not all(c in df for c in [trace.x_col, trace.y_col, trace.z_col]):
                continue
            try:
                tvals = df[trace.time_col].astype(float).to_numpy()
                xvals = df[trace.x_col].astype(float).to_numpy()
                yvals = df[trace.y_col].astype(float).to_numpy()
                zvals = df[trace.z_col].astype(float).to_numpy()
            except Exception:
                continue
            if len(tvals) < 2:
                continue
            if cp.elapsed_secs < np.nanmin(tvals) or cp.elapsed_secs > np.nanmax(tvals):
                cp.warnings.append(f"Timestamp {cp.elapsed_secs} outside trace range for {trace.name}.")
                continue
            x = float(np.interp(cp.elapsed_secs, tvals, xvals))
            y = float(np.interp(cp.elapsed_secs, tvals, yvals))
            z = float(np.interp(cp.elapsed_secs, tvals, zvals))
            cp.interpolated_xyz = (x, y, z)
            cp.plotted = True
            cp.matched_trace = trace.name
            break
        if not cp.plotted:
            cp.warnings.append("Could not match checkpoint to a spacecraft ephemeris trace.")

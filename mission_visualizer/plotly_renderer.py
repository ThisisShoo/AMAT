from __future__ import annotations

import html
import json
import math
from importlib.resources import files
from pathlib import Path

import numpy as np
import plotly.graph_objects as go

from .models import EphemerisTrace, FrameInfo, MissionScene, MissionPaths


ANIMATION_POINTS = 120
BODY_SPHERE_SEGMENTS = 72
BODY_SURFACE_LIGHTING = {
    "ambient": 0.52,
    "diffuse": 0.82,
    "specular": 0.22,
    "roughness": 0.78,
    "fresnel": 0.08,
}


def _load_body_assets() -> dict:
    try:
        p = files("mission_visualizer.assets").joinpath("bodies.json")
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _sphere_mesh(cx: float, cy: float, cz: float, r: float, n: int = BODY_SPHERE_SEGMENTS):
    u = np.linspace(0, 2 * np.pi, n)
    v = np.linspace(0, np.pi, n // 2)
    x = cx + r * np.outer(np.cos(u), np.sin(v))
    y = cy + r * np.outer(np.sin(u), np.sin(v))
    z = cz + r * np.outer(np.ones_like(u), np.cos(v))
    return x, y, z


def _body_surface_style(body_name: str, body_assets: dict, shape: tuple[int, int]) -> dict:
    meta = body_assets.get(body_name, {})
    texture = meta.get("texture", "plain")
    color = meta.get("color", "#9aa0a6")
    rows, cols = shape
    u = np.linspace(0, 2 * np.pi, rows)
    v = np.linspace(0, np.pi, cols)

    if texture == "earth":
        lon = u[:, None]
        lat = (np.pi / 2.0 - v)[None, :]
        ocean = 0.28 + 0.06 * np.sin(9.0 * lon + 2.0 * np.sin(lat))
        continents = (
            0.46 * np.sin(2.1 * lon + 1.8 * np.sin(3.0 * lat))
            + 0.26 * np.cos(3.8 * lon - 2.2 * np.sin(lat))
            + 0.18 * np.sin(7.0 * lon + 5.0 * lat)
        )
        surface = np.where(continents > 0.18, 0.62 + 0.18 * continents, ocean)
        cloud = 0.08 * np.sin(13.0 * lon + 4.0 * lat) * np.cos(5.0 * lon - 2.0 * lat)
        surface = np.clip(surface + cloud, 0.0, 1.0)
        surface = np.where(np.abs(np.sin(lat)) > 0.91, 1.0, surface)
        return {
            "surfacecolor": surface,
            "colorscale": [
                [0.0, "#0b3d91"],
                [0.35, "#1f78b4"],
                [0.42, "#2e8b57"],
                [0.68, "#7cad52"],
                [0.86, "#d9e5df"],
                [1.0, "#f2f6f8"],
            ],
        }
    if texture in {"moon", "luna"}:
        lon = u[:, None]
        lat = v[None, :]
        maria = 0.10 * np.sin(2.0 * lon + 0.7) + 0.08 * np.cos(3.0 * lon - 1.4 * lat)
        craters = (
            0.06 * np.sin(17.0 * lon) * np.sin(11.0 * lat)
            + 0.045 * np.cos(29.0 * lon + 3.0 * lat)
            + 0.035 * np.sin(41.0 * lon - 7.0 * lat)
        )
        surface = np.clip(0.55 + maria + craters, 0.0, 1.0)
        return {
            "surfacecolor": surface,
            "colorscale": [[0.0, "#3f4145"], [0.38, "#74746f"], [0.72, "#aaa79d"], [1.0, "#dedbd1"]],
        }
    if texture == "sun":
        surface = 0.55 + 0.18 * np.sin(12.0 * u)[:, None] + 0.12 * np.cos(7.0 * v)[None, :]
        return {
            "surfacecolor": surface,
            "colorscale": [[0.0, "#f97316"], [0.55, "#facc15"], [1.0, "#fff7ad"]],
        }
    if texture == "bands":
        surface = np.sin(8.0 * v)[None, :] + np.zeros((rows, cols))
        return {
            "surfacecolor": surface,
            "colorscale": [[0.0, meta.get("band_dark", "#b08968")], [1.0, meta.get("band_light", "#f2d6a2")]],
        }
    return {
        "surfacecolor": np.zeros((rows, cols)),
        "colorscale": [[0.0, color], [1.0, color]],
    }


def _body_line_color(body_name: str, body_assets: dict) -> str:
    return str(body_assets.get(body_name, {}).get("orbit_color", body_assets.get(body_name, {}).get("color", "#777777")))


def _trace_arrays(trace: EphemerisTrace):
    df = trace.dataframe
    return (
        df[trace.x_col].astype(float).to_numpy(),
        df[trace.y_col].astype(float).to_numpy(),
        df[trace.z_col].astype(float).to_numpy(),
    )


def _trace_time_values(trace: EphemerisTrace) -> np.ndarray | None:
    if not trace.time_col or trace.time_col not in trace.dataframe:
        return None
    try:
        return trace.dataframe[trace.time_col].astype(float).to_numpy()
    except Exception:
        return None


def _finite_rows(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> np.ndarray:
    return np.isfinite(x) & np.isfinite(y) & np.isfinite(z)


def _interp_to_times(source_t: np.ndarray | None, values: np.ndarray, target_t: np.ndarray | None) -> np.ndarray:
    if source_t is None or target_t is None:
        n = min(values.size, 0 if target_t is None else target_t.size)
        return values[:n]
    source_t = np.asarray(source_t, dtype=float)
    target_t = np.asarray(target_t, dtype=float)
    mask = np.isfinite(source_t) & np.isfinite(values)
    if not np.any(mask):
        return np.full(target_t.shape, np.nan)
    order = np.argsort(source_t[mask])
    return np.interp(target_t, source_t[mask][order], values[mask][order])


def _resample_indices(length: int, max_points: int = ANIMATION_POINTS) -> np.ndarray:
    if length <= 0:
        return np.array([], dtype=int)
    if length <= max_points:
        return np.arange(length, dtype=int)
    return np.unique(np.linspace(0, length - 1, max_points).astype(int))


def _trace_xyz_at_times(trace: EphemerisTrace, target_t: np.ndarray | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x, y, z = _trace_arrays(trace)
    if target_t is None:
        return x, y, z
    source_t = _trace_time_values(trace)
    return (
        _interp_to_times(source_t, x, target_t),
        _interp_to_times(source_t, y, target_t),
        _interp_to_times(source_t, z, target_t),
    )


def _frame_key(frame: str | None) -> str:
    return frame or "unknown frame"


def _frame_info_by_name(scene: MissionScene) -> dict[str, FrameInfo]:
    return {f.name: f for f in scene.frames if f.name}


def _ordered_frame_names(scene: MissionScene) -> list[str]:
    """Return every frame that should receive its own independent figure."""
    names: list[str] = []

    def add(name: str | None) -> None:
        key = _frame_key(name)
        if key not in names:
            names.append(key)

    # Put frames that actually contain plotted data first.
    for trace in scene.spacecraft_traces:
        add(trace.frame)
    for trace in scene.body_traces:
        add(trace.frame)

    return names or ["unknown frame"]


def _axis_extent(traces: list[EphemerisTrace], body_assets: dict) -> float:
    """Choose a stable extent for reference helpers in a frame."""
    max_abs = 0.0
    for trace in traces:
        if not trace.x_col or not trace.y_col or not trace.z_col:
            continue
        try:
            x, y, z = _trace_arrays(trace)
            finite = np.concatenate([x[np.isfinite(x)], y[np.isfinite(y)], z[np.isfinite(z)]])
            if finite.size:
                max_abs = max(max_abs, float(np.nanmax(np.abs(finite))))
        except Exception:
            continue
        meta = body_assets.get(trace.object_name, {})
        max_abs = max(max_abs, float(meta.get("radius_km", 0.0) or 0.0))

    # Keep the helpers visible even for tiny or empty scenes.
    if max_abs <= 0:
        max_abs = 10_000.0
    return max(max_abs * 1.15, 1.0)


def _axis_extent_arrays(arrays: list[tuple[np.ndarray, np.ndarray, np.ndarray]], minimum: float = 1.0) -> float:
    max_abs = 0.0
    for x, y, z in arrays:
        finite = np.concatenate([x[np.isfinite(x)], y[np.isfinite(y)], z[np.isfinite(z)]])
        if finite.size:
            max_abs = max(max_abs, float(np.nanmax(np.abs(finite))))
    return max(max_abs * 1.15, minimum)


def _equal_axis_ranges(extent: float) -> dict:
    span = max(float(extent), 1.0)
    axis = {"gridcolor": "#263241", "zerolinecolor": "#94a3b8", "range": [-span, span]}
    return {
        "xaxis": {**axis},
        "yaxis": {**axis},
        "zaxis": {**axis},
    }


def _burn_intervals(scene: MissionScene) -> list[dict]:
    manifest = scene.manifest or {}
    raw: list[dict] = []
    for key in ("finite_burns", "burn_intervals", "maneuver_segments"):
        values = manifest.get(key, [])
        if isinstance(values, list):
            raw.extend(v for v in values if isinstance(v, dict))
    return raw


def _interval_bounds(interval: dict) -> tuple[float, float] | None:
    start = (
        interval.get("start_elapsed_s")
        if interval.get("start_elapsed_s") is not None
        else interval.get("elapsed_start_s")
        if interval.get("elapsed_start_s") is not None
        else interval.get("start_time_s")
    )
    end = (
        interval.get("end_elapsed_s")
        if interval.get("end_elapsed_s") is not None
        else interval.get("elapsed_end_s")
        if interval.get("elapsed_end_s") is not None
        else interval.get("end_time_s")
    )
    if end is None and start is not None and interval.get("duration_s") is not None:
        end = float(start) + float(interval["duration_s"])
    if start is None or end is None:
        return None
    start_f = float(start)
    end_f = float(end)
    if end_f < start_f:
        start_f, end_f = end_f, start_f
    return start_f, end_f


def _interval_matches_trace(interval: dict, trace: EphemerisTrace) -> bool:
    spacecraft = interval.get("spacecraft") or interval.get("spacecraft_name") or interval.get("object") or interval.get("object_name")
    frame = interval.get("frame")
    if spacecraft and spacecraft not in {trace.object_name, trace.name}:
        return False
    if frame and frame != trace.frame:
        return False
    return trace.kind == "spacecraft"


def _add_finite_burn_segments(fig: go.Figure, scene: MissionScene, trace: EphemerisTrace, group: str) -> None:
    intervals = [i for i in _burn_intervals(scene) if _interval_matches_trace(i, trace)]
    if not intervals:
        return
    times = _trace_time_values(trace)
    if times is None:
        trace.warnings.append("Finite burn intervals were declared, but the trajectory has no numeric time column.")
        return
    x, y, z = _trace_arrays(trace)
    for index, interval in enumerate(intervals, start=1):
        bounds = _interval_bounds(interval)
        if not bounds:
            trace.warnings.append(f"Finite burn interval {interval.get('id') or index} has no usable elapsed-time bounds.")
            continue
        start_s, end_s = bounds
        mask = (times >= start_s) & (times <= end_s)
        if not np.any(mask):
            trace.warnings.append(
                f"Finite burn interval {interval.get('id') or index} [{start_s}, {end_s}] is outside {trace.name} time coverage."
            )
            continue
        name = interval.get("name") or interval.get("burn_id") or interval.get("id") or f"Finite burn {index}"
        fig.add_trace(go.Scatter3d(
            x=x[mask],
            y=y[mask],
            z=z[mask],
            mode="lines",
            name=f"{name} burn arc",
            legendgroup=group,
            line={"width": 7, "color": interval.get("color", "#d97706")},
            hovertemplate=f"{name}<br>finite burn<br>ElapsedSecs={start_s:.3f} to {end_s:.3f}<extra></extra>",
        ))


def _checkpoint_hover_html(cp) -> str:
    return f"{cp.name}<br>{cp.utc_gregorian or ''}<br>ElapsedSecs={cp.elapsed_secs}"


def _checkpoint_clusters(cps: list, points: list[Sequence[float]], extent: float) -> list[dict]:
    cluster_distance = max(extent * 0.018, 1.0)
    clusters: list[list[int]] = []

    for idx, point_value in enumerate(points):
        point = np.array(point_value, dtype=float)
        placed = False
        for cluster in clusters:
            anchor = np.array(points[cluster[0]], dtype=float)
            if float(np.linalg.norm(point - anchor)) <= cluster_distance:
                cluster.append(idx)
                placed = True
                break
        if not placed:
            clusters.append([idx])

    out: list[dict] = []
    for display_idx, cluster in enumerate(clusters, start=1):
        cluster_points = np.array([points[idx] for idx in cluster], dtype=float)
        center = np.mean(cluster_points, axis=0)
        if len(cluster) > 1:
            label = f"{len(cluster)}"
            hover = (
                f"{len(cluster)} checkpoint cluster:<br>"
                + "<br>".join(f"{ordinal}. {_checkpoint_hover_html(cps[item])}" for ordinal, item in enumerate(cluster, start=1))
            )
        else:
            label = str(display_idx)
            hover = _checkpoint_hover_html(cps[cluster[0]])
        out.append({
            "x": float(center[0]),
            "y": float(center[1]),
            "z": float(center[2]),
            "label": label,
            "hover": hover,
            "count": len(cluster),
        })
    return out


def _add_reference_xy_plane(fig: go.Figure, frame_name: str, extent: float) -> None:
    """Add a toggleable local X-Y plane for the displayed frame."""
    grid = np.linspace(-extent, extent, 2)
    x, y = np.meshgrid(grid, grid)
    z = np.zeros_like(x)
    group = f"reference_xy_{frame_name}"
    fig.add_trace(go.Surface(
        x=x,
        y=y,
        z=z,
        name="X-Y reference plane",
        legendgroup=group,
        showlegend=True,
        showscale=False,
        opacity=0.16,
        hoverinfo="skip",
        visible=True,
    ))
    # A thin outline makes the plane readable when viewed nearly edge-on.
    outline_x = [-extent, extent, extent, -extent, -extent]
    outline_y = [-extent, -extent, extent, extent, -extent]
    outline_z = [0, 0, 0, 0, 0]
    fig.add_trace(go.Scatter3d(
        x=outline_x,
        y=outline_y,
        z=outline_z,
        mode="lines",
        name="X-Y plane outline",
        legendgroup=group,
        showlegend=False,
        hoverinfo="skip",
        visible=True,
    ))


def _add_reference_z_axis(fig: go.Figure, frame_name: str, extent: float) -> None:
    """Add a toggleable +Z arrow for the displayed frame."""
    axis_len = extent * 0.85
    cone_len = max(axis_len * 0.12, 1.0)
    group = f"reference_z_{frame_name}"
    fig.add_trace(go.Scatter3d(
        x=[0, 0],
        y=[0, 0],
        z=[0, axis_len],
        mode="lines+text",
        text=["", "+Z"],
        textposition="top center",
        name="+Z axis",
        legendgroup=group,
        showlegend=True,
        hoverinfo="skip",
        visible=True,
    ))
    fig.add_trace(go.Cone(
        x=[0],
        y=[0],
        z=[axis_len],
        u=[0],
        v=[0],
        w=[cone_len],
        sizemode="absolute",
        sizeref=max(cone_len, 1.0),
        anchor="tip",
        name="+Z arrow head",
        legendgroup=group,
        showlegend=False,
        showscale=False,
        hoverinfo="skip",
        visible=True,
    ))


def _add_origin_body(fig: go.Figure, frame: FrameInfo | None, body_assets: dict) -> None:
    if not frame or not frame.origin:
        return
    meta = body_assets.get(frame.origin, {})
    radius = float(meta.get("radius_km", 1000.0))
    x, y, z = _sphere_mesh(0, 0, 0, radius)
    style = _body_surface_style(frame.origin, body_assets, x.shape)
    fig.add_trace(go.Surface(
        x=x, y=y, z=z,
        name=f"{frame.origin} origin",
        legendgroup=f"body_{frame.origin}",
        showscale=False,
        surfacecolor=style["surfacecolor"],
        colorscale=style["colorscale"],
        lighting=BODY_SURFACE_LIGHTING,
        opacity=0.45,
        hoverinfo="name",
        visible=True,
    ))


def _add_spacecraft_trace(fig: go.Figure, scene: MissionScene, trace: EphemerisTrace) -> None:
    if not trace.x_col or not trace.y_col or not trace.z_col:
        return
    x, y, z = _trace_arrays(trace)
    group = f"traj_{trace.object_name}_{_frame_key(trace.frame)}"
    fig.add_trace(go.Scatter3d(
        x=x, y=y, z=z,
        mode="lines",
        name=trace.name,
        legendgroup=group,
        line={"width": 3, "color": "#2563eb"},
        hovertemplate=f"{trace.name}<br>X=%{{x:.3f}} km<br>Y=%{{y:.3f}} km<br>Z=%{{z:.3f}} km<extra></extra>",
    ))
    _add_finite_burn_segments(fig, scene, trace, group)
    cps = [cp for cp in scene.checkpoints if cp.plotted and cp.matched_trace == trace.name and cp.interpolated_xyz]
    if cps:
        clusters = _checkpoint_clusters(cps, [cp.interpolated_xyz for cp in cps], _axis_extent([trace], {}))
        fig.add_trace(go.Scatter3d(
            x=[item["x"] for item in clusters],
            y=[item["y"] for item in clusters],
            z=[item["z"] for item in clusters],
            mode="markers+text",
            text=[item["label"] for item in clusters],
            textposition="top center",
            customdata=[item["hover"] for item in clusters],
            meta={"amat_kind": "checkpoint"},
            marker={"size": [max(6, min(12, 5 + item["count"])) for item in clusters], "color": "#facc15"},
            name=f"{trace.object_name} checkpoints",
            legendgroup=group,
            hovertemplate="%{customdata}<extra></extra>",
        ))


def _add_body_trace(fig: go.Figure, trace: EphemerisTrace, body_assets: dict) -> None:
    if not trace.x_col or not trace.y_col or not trace.z_col:
        return
    x, y, z = _trace_arrays(trace)
    group = f"body_{trace.object_name}_{_frame_key(trace.frame)}"
    fig.add_trace(go.Scatter3d(
        x=x, y=y, z=z,
        mode="lines",
        name=f"{trace.object_name} path",
        legendgroup=group,
        line={"width": 2, "color": _body_line_color(trace.object_name, body_assets)},
        hovertemplate=f"{trace.object_name}<br>X=%{{x:.3f}} km<br>Y=%{{y:.3f}} km<br>Z=%{{z:.3f}} km<extra></extra>",
    ))
    meta = body_assets.get(trace.object_name, {})
    radius = float(meta.get("radius_km", 1000.0))
    sx, sy, sz = _sphere_mesh(float(x[0]), float(y[0]), float(z[0]), radius)
    style = _body_surface_style(trace.object_name, body_assets, sx.shape)
    fig.add_trace(go.Surface(
        x=sx, y=sy, z=sz,
        name=f"{trace.object_name} at start",
        legendgroup=group,
        showscale=False,
        surfacecolor=style["surfacecolor"],
        colorscale=style["colorscale"],
        lighting=BODY_SURFACE_LIGHTING,
        opacity=0.45,
        hoverinfo="name",
    ))


def _add_animated_markers(fig: go.Figure, traces: list[EphemerisTrace], body_assets: dict) -> None:
    if not traces:
        return
    time_sets = [_trace_time_values(t) for t in traces]
    time_sets = [t for t in time_sets if t is not None and t.size]
    if not time_sets:
        return
    start = max(float(np.nanmin(t)) for t in time_sets)
    end = min(float(np.nanmax(t)) for t in time_sets)
    if not np.isfinite(start) or not np.isfinite(end) or end <= start:
        return
    anim_times = np.linspace(start, end, min(ANIMATION_POINTS, max(2, int(end - start) + 1)))
    marker_indices: list[int] = []
    marker_payloads: list[tuple[EphemerisTrace, tuple[np.ndarray, np.ndarray, np.ndarray]]] = []
    for trace in traces:
        x, y, z = _trace_xyz_at_times(trace, anim_times)
        if not np.any(_finite_rows(x, y, z)):
            continue
        marker_indices.append(len(fig.data))
        marker_payloads.append((trace, (x, y, z)))
        color = _body_line_color(trace.object_name, body_assets) if trace.kind == "body" else "#f8fafc"
        symbol = "circle" if trace.kind == "body" else "diamond"
        fig.add_trace(go.Scatter3d(
            x=[x[0]], y=[y[0]], z=[z[0]],
            mode="markers+text",
            text=[trace.object_name],
            textposition="top center",
            name=f"{trace.object_name} live",
            legendgroup=f"live_{trace.object_name}",
            marker={"size": 6 if trace.kind == "body" else 5, "color": color, "symbol": symbol},
            hovertemplate=f"{trace.object_name}<br>ElapsedSecs=%{{customdata:.3f}}<br>X=%{{x:.3f}} km<br>Y=%{{y:.3f}} km<br>Z=%{{z:.3f}} km<extra></extra>",
            customdata=[float(anim_times[0])],
        ))
    if not marker_indices:
        return
    frames = []
    for idx, elapsed in enumerate(anim_times):
        frames.append(go.Frame(
            name=f"{elapsed:.3f}",
            data=[
                go.Scatter3d(
                    x=[payload[0][idx]],
                    y=[payload[1][idx]],
                    z=[payload[2][idx]],
                    customdata=[float(elapsed)],
                )
                for _, payload in marker_payloads
            ],
            traces=marker_indices,
        ))
    fig.frames = tuple(list(fig.frames) + frames)
    slider_steps = [
        {
            "method": "animate",
            "label": f"{elapsed / 86400.0:.2f} d",
            "args": [[f"{elapsed:.3f}"], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}, "transition": {"duration": 0}}],
        }
        for elapsed in anim_times
    ]
    fig.update_layout(
        updatemenus=[{
            "type": "buttons",
            "direction": "left",
            "x": 0.02,
            "y": 1.08,
            "buttons": [
                {"label": "Play", "method": "animate", "args": [None, {"frame": {"duration": 70, "redraw": True}, "transition": {"duration": 0}, "fromcurrent": True}]},
                {"label": "Pause", "method": "animate", "args": [[None], {"mode": "immediate", "frame": {"duration": 0, "redraw": False}, "transition": {"duration": 0}}]},
            ],
        }],
        sliders=[{
            "active": 0,
            "currentvalue": {"prefix": "Elapsed: ", "suffix": " s"},
            "pad": {"t": 42},
            "steps": slider_steps,
        }],
    )


def _add_animated_arrays(
    fig: go.Figure,
    series: list[dict],
    body_assets: dict,
    anim_times: np.ndarray,
) -> None:
    marker_indices: list[int] = []
    marker_payloads: list[dict] = []
    for item in series:
        x, y, z = item["x"], item["y"], item["z"]
        if not np.any(_finite_rows(x, y, z)):
            continue
        marker_indices.append(len(fig.data))
        marker_payloads.append(item)
        color = _body_line_color(item["object"], body_assets) if item["kind"] == "body" else "#f8fafc"
        fig.add_trace(go.Scatter3d(
            x=[x[0]], y=[y[0]], z=[z[0]],
            mode="markers+text",
            text=[item["object"]],
            textposition="top center",
            name=f"{item['object']} live",
            marker={"size": 6 if item["kind"] == "body" else 5, "color": color},
            hovertemplate=f"{item['object']}<br>ElapsedSecs=%{{customdata:.3f}}<br>X=%{{x:.3f}} km<br>Y=%{{y:.3f}} km<br>Z=%{{z:.3f}} km<extra></extra>",
            customdata=[float(anim_times[0])],
        ))
    if not marker_indices:
        return
    frames = []
    for idx, elapsed in enumerate(anim_times):
        frames.append(go.Frame(
            name=f"{elapsed:.3f}",
            data=[
                go.Scatter3d(x=[item["x"][idx]], y=[item["y"][idx]], z=[item["z"][idx]], customdata=[float(elapsed)])
                for item in marker_payloads
            ],
            traces=marker_indices,
        ))
    fig.frames = tuple(list(fig.frames) + frames)
    fig.update_layout(
        updatemenus=[{
            "type": "buttons",
            "direction": "left",
            "x": 0.02,
            "y": 1.08,
            "buttons": [
                {"label": "Play", "method": "animate", "args": [None, {"frame": {"duration": 70, "redraw": True}, "transition": {"duration": 0}, "fromcurrent": True}]},
                {"label": "Pause", "method": "animate", "args": [[None], {"mode": "immediate", "frame": {"duration": 0, "redraw": False}, "transition": {"duration": 0}}]},
            ],
        }],
        sliders=[{
            "active": 0,
            "currentvalue": {"prefix": "Elapsed: ", "suffix": " s"},
            "pad": {"t": 42},
            "steps": [
                {
                    "method": "animate",
                    "label": f"{elapsed / 86400.0:.2f} d",
                    "args": [[f"{elapsed:.3f}"], {"mode": "immediate", "frame": {"duration": 0, "redraw": True}, "transition": {"duration": 0}}],
                }
                for elapsed in anim_times
            ],
        }],
    )


def _build_frame_figure(scene: MissionScene, frame_name: str, frame: FrameInfo | None, body_assets: dict) -> go.Figure:
    fig = go.Figure()
    spacecraft = [t for t in scene.spacecraft_traces if _frame_key(t.frame) == frame_name]
    bodies = [t for t in scene.body_traces if _frame_key(t.frame) == frame_name]
    traces_for_extent = spacecraft + bodies
    extent = _axis_extent(traces_for_extent, body_assets)

    _add_reference_xy_plane(fig, frame_name, extent)
    _add_reference_z_axis(fig, frame_name, extent)
    _add_origin_body(fig, frame, body_assets)

    for trace in spacecraft:
        _add_spacecraft_trace(fig, scene, trace)

    for trace in bodies:
        _add_body_trace(fig, trace, body_assets)

    _add_animated_markers(fig, spacecraft + bodies, body_assets)

    warn_text = "<br>".join(scene.warnings[:20]) if scene.warnings else "No warnings."
    if frame:
        frame_text = f"{frame.name} origin={frame.origin or '?'} axes={frame.axes or '?'} source={frame.source}"
    else:
        frame_text = f"{frame_name} origin=? axes=?"

    fig.update_layout(
        template="plotly_dark",
        title=f"Mission Trajectory: {scene.mission_id} — {frame_name}",
        paper_bgcolor="#05070b",
        plot_bgcolor="#05070b",
        font={"color": "#e5e7eb"},
        scene={
            "xaxis_title": "X (km)",
            "yaxis_title": "Y (km)",
            "zaxis_title": "Z (km)",
            "aspectmode": "cube",
            "bgcolor": "#05070b",
            **_equal_axis_ranges(extent),
        },
        legend={"groupclick": "togglegroup"},
        margin={"l": 0, "r": 0, "t": 55, "b": 0},
        annotations=[{
            "text": f"Frame: {frame_text}<br>Warnings: {warn_text}",
            "showarrow": False,
            "xref": "paper", "yref": "paper", "x": 0, "y": -0.08,
            "align": "left",
        }],
    )
    return fig


def _layout_derived_figure(fig: go.Figure, scene: MissionScene, title: str, extent: float) -> None:
    fig.update_layout(
        template="plotly_dark",
        title=title,
        paper_bgcolor="#05070b",
        plot_bgcolor="#05070b",
        font={"color": "#e5e7eb"},
        scene={
            "xaxis_title": "X (km)",
            "yaxis_title": "Y (km)",
            "zaxis_title": "Z (km)",
            "aspectmode": "cube",
            "bgcolor": "#05070b",
            **_equal_axis_ranges(extent),
        },
        legend={"groupclick": "togglegroup"},
        margin={"l": 0, "r": 0, "t": 55, "b": 0},
    )


def _common_animation_times(traces: list[EphemerisTrace]) -> np.ndarray:
    time_sets = [_trace_time_values(t) for t in traces]
    time_sets = [t for t in time_sets if t is not None and t.size]
    if not time_sets:
        return np.array([], dtype=float)
    start = max(float(np.nanmin(t)) for t in time_sets)
    end = min(float(np.nanmax(t)) for t in time_sets)
    if not np.isfinite(start) or not np.isfinite(end) or end <= start:
        return np.array([], dtype=float)
    return np.linspace(start, end, ANIMATION_POINTS)


def _build_body_centered_figure(scene: MissionScene, body_trace: EphemerisTrace, body_assets: dict) -> go.Figure | None:
    spacecraft = [t for t in scene.spacecraft_traces if _frame_key(t.frame) == _frame_key(body_trace.frame)]
    if not spacecraft:
        return None
    fig = go.Figure()
    bx, by, bz = _trace_arrays(body_trace)
    bt = _trace_time_values(body_trace)
    arrays_for_extent: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    anim_times = _common_animation_times(spacecraft + [body_trace])
    anim_series: list[dict] = []
    for trace in spacecraft:
        tx, ty, tz = _trace_arrays(trace)
        tt = _trace_time_values(trace)
        cx = _interp_to_times(bt, bx, tt)
        cy = _interp_to_times(bt, by, tt)
        cz = _interp_to_times(bt, bz, tt)
        rx, ry, rz = tx - cx, ty - cy, tz - cz
        arrays_for_extent.append((rx, ry, rz))
        fig.add_trace(go.Scatter3d(
            x=rx, y=ry, z=rz,
            mode="lines",
            name=f"{trace.object_name} relative to {body_trace.object_name}",
            line={"width": 3, "color": "#38bdf8"},
            hovertemplate=f"{trace.object_name}<br>{body_trace.object_name}-centered<br>X=%{{x:.3f}} km<br>Y=%{{y:.3f}} km<br>Z=%{{z:.3f}} km<extra></extra>",
        ))
        if anim_times.size:
            ax, ay, az = _trace_xyz_at_times(trace, anim_times)
            abx, aby, abz = _trace_xyz_at_times(body_trace, anim_times)
            anim_series.append({"object": trace.object_name, "kind": trace.kind, "x": ax - abx, "y": ay - aby, "z": az - abz})
    radius = float(body_assets.get(body_trace.object_name, {}).get("radius_km", 1000.0))
    sx, sy, sz = _sphere_mesh(0, 0, 0, radius)
    style = _body_surface_style(body_trace.object_name, body_assets, sx.shape)
    fig.add_trace(go.Surface(
        x=sx, y=sy, z=sz,
        name=f"{body_trace.object_name} origin",
        showscale=False,
        surfacecolor=style["surfacecolor"],
        colorscale=style["colorscale"],
        lighting=BODY_SURFACE_LIGHTING,
        opacity=0.65,
        hoverinfo="name",
    ))
    checkpoint_items = []
    checkpoint_points = []
    for cp in scene.checkpoints:
        if not cp.plotted or not cp.interpolated_xyz or cp.elapsed_secs is None:
            continue
        if not any(cp.matched_trace == trace.name for trace in spacecraft):
            continue
        cbt = np.array([float(cp.elapsed_secs)])
        cbx, cby, cbz = _trace_xyz_at_times(body_trace, cbt)
        rel = np.array(cp.interpolated_xyz, dtype=float) - np.array([cbx[0], cby[0], cbz[0]], dtype=float)
        checkpoint_items.append(cp)
        checkpoint_points.append((float(rel[0]), float(rel[1]), float(rel[2])))
        arrays_for_extent.append((np.array([rel[0]]), np.array([rel[1]]), np.array([rel[2]])))
    if checkpoint_items:
        radius_extent = _axis_extent_arrays(arrays_for_extent, max(radius * 4.0, 1.0))
        clusters = _checkpoint_clusters(checkpoint_items, checkpoint_points, radius_extent)
        fig.add_trace(go.Scatter3d(
            x=[item["x"] for item in clusters],
            y=[item["y"] for item in clusters],
            z=[item["z"] for item in clusters],
            mode="markers+text",
            text=[item["label"] for item in clusters],
            textposition="top center",
            name=f"{body_trace.object_name}-centered checkpoints",
            meta={"amat_kind": "checkpoint"},
            customdata=[item["hover"] for item in clusters],
            marker={"size": [max(6, min(12, 5 + item["count"])) for item in clusters], "color": "#facc15"},
            hovertemplate="%{customdata}<extra></extra>",
            showlegend=False,
        ))
    if anim_times.size:
        _add_animated_arrays(fig, anim_series, body_assets, anim_times)
    extent = _axis_extent_arrays(arrays_for_extent, max(radius * 4.0, 1.0))
    _add_reference_xy_plane(fig, f"{body_trace.object_name}_centered", extent)
    _add_reference_z_axis(fig, f"{body_trace.object_name}_centered", extent)
    _layout_derived_figure(fig, scene, f"Mission Trajectory: {scene.mission_id} - {body_trace.object_name}-centered", extent)
    return fig


def _rotating_axes(moon_trace: EphemerisTrace, times: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    times = np.asarray(times, dtype=float)
    if times.size == 1:
        t = float(times[0])
        nearby = np.array([t - 60.0, t, t + 60.0], dtype=float)
        xhat, yhat, zhat, r_norm = _rotating_axes(moon_trace, nearby)
        return xhat[1:2], yhat[1:2], zhat[1:2], r_norm[1:2]
    mx, my, mz = _trace_xyz_at_times(moon_trace, times)
    r = np.column_stack([mx, my, mz])
    r_norm = np.linalg.norm(r, axis=1)
    xhat = r / r_norm[:, None]
    dr = np.gradient(r, times, axis=0, edge_order=1)
    h = np.cross(r, dr)
    h_norm = np.linalg.norm(h, axis=1)
    fallback = np.array([0.0, 0.0, 1.0])
    zhat = np.divide(h, h_norm[:, None], out=np.tile(fallback, (len(times), 1)), where=h_norm[:, None] > 0)
    yhat = np.cross(zhat, xhat)
    yhat = yhat / np.linalg.norm(yhat, axis=1)[:, None]
    return xhat, yhat, zhat, r_norm


def _rotating_transform(trace: EphemerisTrace, times: np.ndarray, moon_trace: EphemerisTrace, mean_distance: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    px, py, pz = _trace_xyz_at_times(trace, times)
    p = np.column_stack([px, py, pz])
    xhat, yhat, zhat, r_norm = _rotating_axes(moon_trace, times)
    scale = mean_distance / r_norm
    return (
        np.einsum("ij,ij->i", p, xhat) * scale,
        np.einsum("ij,ij->i", p, yhat) * scale,
        np.einsum("ij,ij->i", p, zhat) * scale,
    )


def _build_earth_moon_rotating_figure(scene: MissionScene, moon_trace: EphemerisTrace, body_assets: dict) -> go.Figure | None:
    spacecraft = [t for t in scene.spacecraft_traces if _frame_key(t.frame) == _frame_key(moon_trace.frame)]
    if not spacecraft:
        return None
    mt = _trace_time_values(moon_trace)
    if mt is None or mt.size < 3:
        return None
    mx, my, mz = _trace_arrays(moon_trace)
    mean_distance = float(np.nanmean(np.linalg.norm(np.column_stack([mx, my, mz]), axis=1)))
    fig = go.Figure()
    arrays_for_extent: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    anim_times = _common_animation_times(spacecraft + [moon_trace])
    anim_series: list[dict] = []
    for trace in spacecraft:
        tt = _trace_time_values(trace)
        if tt is None:
            continue
        rx, ry, rz = _rotating_transform(trace, tt, moon_trace, mean_distance)
        arrays_for_extent.append((rx, ry, rz))
        fig.add_trace(go.Scatter3d(
            x=rx, y=ry, z=rz,
            mode="lines",
            name=f"{trace.object_name} rotating Earth-Moon",
            line={"width": 3, "color": "#38bdf8"},
            hovertemplate=f"{trace.object_name}<br>Earth-Moon rotating<br>X=%{{x:.3f}} km<br>Y=%{{y:.3f}} km<br>Z=%{{z:.3f}} km<extra></extra>",
        ))
        if anim_times.size:
            ax, ay, az = _rotating_transform(trace, anim_times, moon_trace, mean_distance)
            anim_series.append({"object": trace.object_name, "kind": trace.kind, "x": ax, "y": ay, "z": az})
    moon_x = np.full(mt.shape, mean_distance)
    moon_y = np.zeros(mt.shape)
    moon_z = np.zeros(mt.shape)
    arrays_for_extent.append((moon_x, moon_y, moon_z))
    fig.add_trace(go.Scatter3d(
        x=moon_x, y=moon_y, z=moon_z,
        mode="lines",
        name=f"{moon_trace.object_name} fixed",
        line={"width": 2, "color": _body_line_color(moon_trace.object_name, body_assets)},
        hovertemplate=f"{moon_trace.object_name}<br>Fixed in rotating frame<extra></extra>",
    ))
    for body_name, center in [("Earth", (0.0, 0.0, 0.0)), (moon_trace.object_name, (mean_distance, 0.0, 0.0))]:
        radius = float(body_assets.get(body_name, {}).get("radius_km", 1000.0))
        sx, sy, sz = _sphere_mesh(center[0], center[1], center[2], radius)
        style = _body_surface_style(body_name, body_assets, sx.shape)
        fig.add_trace(go.Surface(
            x=sx, y=sy, z=sz,
            name=f"{body_name} fixed",
            showscale=False,
            surfacecolor=style["surfacecolor"],
            colorscale=style["colorscale"],
            lighting=BODY_SURFACE_LIGHTING,
            opacity=0.65,
            hoverinfo="name",
        ))
    checkpoint_items = []
    checkpoint_points = []
    for cp in scene.checkpoints:
        if not cp.plotted or not cp.interpolated_xyz or cp.elapsed_secs is None:
            continue
        if not any(cp.matched_trace == trace.name for trace in spacecraft):
            continue
        t = np.array([float(cp.elapsed_secs)])
        # Avoid constructing a dataframe for one point; transform directly.
        p = np.array(cp.interpolated_xyz, dtype=float)[None, :]
        xhat, yhat, zhat, r_norm = _rotating_axes(moon_trace, t)
        scale = mean_distance / r_norm
        rel = np.array([
            float(np.einsum("ij,ij->i", p, xhat)[0] * scale[0]),
            float(np.einsum("ij,ij->i", p, yhat)[0] * scale[0]),
            float(np.einsum("ij,ij->i", p, zhat)[0] * scale[0]),
        ])
        checkpoint_items.append(cp)
        checkpoint_points.append((float(rel[0]), float(rel[1]), float(rel[2])))
        arrays_for_extent.append((np.array([rel[0]]), np.array([rel[1]]), np.array([rel[2]])))
    if checkpoint_items:
        radius_extent = _axis_extent_arrays(arrays_for_extent, mean_distance * 1.15)
        clusters = _checkpoint_clusters(checkpoint_items, checkpoint_points, radius_extent)
        fig.add_trace(go.Scatter3d(
            x=[item["x"] for item in clusters],
            y=[item["y"] for item in clusters],
            z=[item["z"] for item in clusters],
            mode="markers+text",
            text=[item["label"] for item in clusters],
            textposition="top center",
            name="Rotating-frame checkpoints",
            meta={"amat_kind": "checkpoint"},
            customdata=[item["hover"] for item in clusters],
            marker={"size": [max(6, min(12, 5 + item["count"])) for item in clusters], "color": "#facc15"},
            hovertemplate="%{customdata}<extra></extra>",
            showlegend=False,
        ))
    if anim_times.size:
        anim_series.append({
            "object": moon_trace.object_name,
            "kind": "body",
            "x": np.full(anim_times.shape, mean_distance),
            "y": np.zeros(anim_times.shape),
            "z": np.zeros(anim_times.shape),
        })
        _add_animated_arrays(fig, anim_series, body_assets, anim_times)
    extent = _axis_extent_arrays(arrays_for_extent, mean_distance * 1.15)
    _add_reference_xy_plane(fig, "earth_moon_rotating", extent)
    _add_reference_z_axis(fig, "earth_moon_rotating", extent)
    _layout_derived_figure(fig, scene, f"Mission Trajectory: {scene.mission_id} - Earth-Moon rotating frame", extent)
    return fig


def render_html(scene: MissionScene, paths: MissionPaths, output: str | Path | None = None) -> Path:
    output_path = Path(output) if output else (paths.visualization_dir or (paths.mission_dir / "visualization")) / "trajectory.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    body_assets = _load_body_assets()
    frame_lookup = _frame_info_by_name(scene)
    frame_names = _ordered_frame_names(scene)

    sections: list[str] = []
    hover_pin_script = """
    (function() {
      var plot = document.getElementById('{plot_id}');
      if (!plot || !plot.on) return;

      var card = document.querySelector('.amat-hover-card');
      if (!card) {
        card = document.createElement('div');
        card.className = 'amat-hover-card';
        card.innerHTML = '<div class="amat-hover-body"></div><button type="button">Pin</button>';
        document.body.appendChild(card);
      }
      var body = card.querySelector('.amat-hover-body');
      var button = card.querySelector('button');
      var currentHtml = '';
      var hideTimer = null;

      function ensureFullscreenButton() {
        var section = plot.closest('.frame-figure') || plot.parentElement;
        if (!section || section.querySelector('.amat-fullscreen-btn')) return;
        var fs = document.createElement('button');
        fs.type = 'button';
        fs.className = 'amat-fullscreen-btn';
        fs.textContent = 'Full screen';
        fs.addEventListener('click', function(evt) {
          evt.preventDefault();
          evt.stopPropagation();
          var target = section;
          if (document.fullscreenElement) {
            document.exitFullscreen();
            return;
          }
          if (target.requestFullscreen) target.requestFullscreen();
        });
        section.appendChild(fs);
      }

      function isCheckpointTrace(trace) {
        return trace && trace.meta && trace.meta.amat_kind === 'checkpoint';
      }
      function valueAt(value, pointNumber) {
        if (value === undefined || value === null) return null;
        if (!Array.isArray(value)) return value;
        if (Array.isArray(pointNumber)) {
          var v = value;
          for (var i = 0; i < pointNumber.length; i += 1) {
            if (!Array.isArray(v)) break;
            v = v[pointNumber[i]];
          }
          return v;
        }
        return value[pointNumber];
      }
      function setCardPosition(evt) {
        var x = evt && evt.clientX ? evt.clientX + 14 : 24;
        var y = evt && evt.clientY ? evt.clientY + 14 : 24;
        card.style.left = Math.min(x, window.innerWidth - 340) + 'px';
        card.style.top = Math.min(y, window.innerHeight - 220) + 'px';
      }
      function hideCardSoon() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function() {
          if (!card.matches(':hover')) card.classList.remove('is-visible');
        }, 120);
      }
      function pinCard() {
        if (!currentHtml) return;
        var pin = document.createElement('div');
        pin.className = 'amat-pin-card';
        pin.innerHTML = '<button type="button" aria-label="Close pinned checkpoint">x</button><div>' + currentHtml + '</div>';
        document.body.appendChild(pin);
        var count = document.querySelectorAll('.amat-pin-card').length;
        pin.style.right = '18px';
        pin.style.top = (18 + (count - 1) * 132) + 'px';
        pin.querySelector('button').addEventListener('click', function() {
          pin.remove();
        });
        card.classList.remove('is-visible');
      }
      function pointXYZ(point) {
        if (!point) return null;
        var x = Array.isArray(point.x) ? point.x[0] : point.x;
        var y = Array.isArray(point.y) ? point.y[0] : point.y;
        var z = Array.isArray(point.z) ? point.z[0] : point.z;
        if ([x, y, z].every(function(v) { return Number.isFinite(Number(v)); })) {
          return [Number(x), Number(y), Number(z)];
        }
        if (point.data && point.pointNumber !== undefined) {
          var i = point.pointNumber;
          x = valueAt(point.data.x, i);
          y = valueAt(point.data.y, i);
          z = valueAt(point.data.z, i);
          if ([x, y, z].every(function(v) { return Number.isFinite(Number(v)); })) {
            return [Number(x), Number(y), Number(z)];
          }
        }
        return null;
      }
      function focusPoint(point) {
        var xyz = pointXYZ(point);
        if (!xyz) return;
        var layoutScene = (plot.layout && plot.layout.scene) || {};
        var xr = layoutScene.xaxis && layoutScene.xaxis.range;
        var yr = layoutScene.yaxis && layoutScene.yaxis.range;
        var zr = layoutScene.zaxis && layoutScene.zaxis.range;
        var span = 0;
        [[xr,0],[yr,1],[zr,2]].forEach(function(pair) {
          var r = pair[0];
          if (Array.isArray(r) && r.length === 2) span = Math.max(span, Math.abs(Number(r[1]) - Number(r[0])));
        });
          if (!span) span = Math.max(1, Math.abs(xyz[0]), Math.abs(xyz[1]), Math.abs(xyz[2])) * 0.35;
        var half = Math.max(span * 0.18, 1.0);
        Plotly.relayout(plot, {
          'scene.xaxis.range': [xyz[0] - half, xyz[0] + half],
          'scene.yaxis.range': [xyz[1] - half, xyz[1] + half],
          'scene.zaxis.range': [xyz[2] - half, xyz[2] + half],
          'scene.camera.center': {x: 0, y: 0, z: 0}
        });
      }

      ensureFullscreenButton();

      button.addEventListener('click', function(evt) {
        evt.preventDefault();
        evt.stopPropagation();
        pinCard();
      });
      card.addEventListener('mouseenter', function() { clearTimeout(hideTimer); });
      card.addEventListener('mouseleave', hideCardSoon);
      document.addEventListener('click', function(evt) {
        if (!card.contains(evt.target)) card.classList.remove('is-visible');
      });

      var lastClickAt = 0;
      var lastPointKey = '';
      plot.on('plotly_click', function(eventData) {
        if (!eventData || !eventData.points || !eventData.points.length) return;
        var point = eventData.points[0];
        var key = [point.curveNumber, point.pointNumber, point.x, point.y, point.z].join(':');
        var now = Date.now();
        if (now - lastClickAt < 420 && key === lastPointKey) {
          focusPoint(point);
          if (eventData.event) {
            eventData.event.preventDefault();
            eventData.event.stopPropagation();
          }
        }
        lastClickAt = now;
        lastPointKey = key;
      });

      plot.on('plotly_hover', function(eventData) {
        if (!eventData || !eventData.points || !eventData.points.length) return;
        var point = eventData.points[0];
        var trace = point.data || {};
        if (!trace.customdata || !isCheckpointTrace(trace)) return;
        var label = Array.isArray(trace.customdata) ? trace.customdata[point.pointNumber] : trace.customdata;
        if (!label) return;
        currentHtml = String(label);
        body.innerHTML = currentHtml;
        setCardPosition(eventData.event);
        card.classList.add('is-visible');
      });
      plot.on('plotly_unhover', hideCardSoon);
    })();
    """
    figure_index = 0
    for frame_name in frame_names:
        fig = _build_frame_figure(scene, frame_name, frame_lookup.get(frame_name), body_assets)
        include_plotlyjs = "cdn" if figure_index == 0 else False
        div = fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs, post_script=hover_pin_script, config={"scrollZoom": True, "displaylogo": False, "doubleClick": False})
        sections.append(
            "<section class='frame-figure'>"
            f"<h2>{html.escape(frame_name)}</h2>"
            "<p class='frame-note'>Animated inertial-frame view.</p>"
            f"{div}"
            "</section>"
        )
        figure_index += 1

    for body_trace in scene.body_traces:
        fig = _build_body_centered_figure(scene, body_trace, body_assets)
        if fig is None:
            continue
        include_plotlyjs = "cdn" if figure_index == 0 else False
        div = fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs, post_script=hover_pin_script, config={"scrollZoom": True, "displaylogo": False, "doubleClick": False})
        sections.append(
            "<section class='frame-figure'>"
            f"<h2>{html.escape(body_trace.object_name)}-centered</h2>"
            "<p class='frame-note'>Derived visualization centered on this moving body.</p>"
            f"{div}"
            "</section>"
        )
        figure_index += 1

    moon_trace = next((t for t in scene.body_traces if t.object_name.lower() in {"luna", "moon"}), None)
    if moon_trace is not None:
        fig = _build_earth_moon_rotating_figure(scene, moon_trace, body_assets)
        if fig is not None:
            include_plotlyjs = "cdn" if figure_index == 0 else False
            div = fig.to_html(full_html=False, include_plotlyjs=include_plotlyjs, post_script=hover_pin_script, config={"scrollZoom": True, "displaylogo": False, "doubleClick": False})
            sections.append(
                "<section class='frame-figure'>"
                "<h2>Earth-Moon Rotating</h2>"
                "<p class='frame-note'>Derived rotating-pulsating view with Earth fixed at the origin and Luna fixed on +X.</p>"
                f"{div}"
                "</section>"
            )
            figure_index += 1

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Mission Trajectory: {html.escape(scene.mission_id)}</title>
  <style>
    body {{ margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #05070b; color: #e5e7eb; }}
    header {{ padding: 20px 24px 8px; }}
    h1 {{ margin: 0 0 8px; font-size: 24px; }}
    h2 {{ margin: 0 0 4px; font-size: 18px; }}
    .summary {{ color: #94a3b8; margin: 0; }}
    .frame-figure {{ position: relative; padding: 16px 24px 36px; border-top: 1px solid #1f2937; background: #05070b; }}
    .frame-figure:fullscreen {{ padding: 16px; overflow: auto; }}
    .frame-figure:fullscreen .plotly-graph-div {{ height: calc(100vh - 96px) !important; }}
    .frame-note {{ margin: 0 0 8px; color: #94a3b8; font-size: 14px; }}
    .amat-fullscreen-btn {{
      position: absolute;
      top: 14px;
      right: 24px;
      z-index: 20;
      border: 1px solid #475569;
      border-radius: 4px;
      background: rgba(15, 23, 42, 0.92);
      color: #e5e7eb;
      cursor: pointer;
      font: inherit;
      font-size: 13px;
      padding: 5px 10px;
    }}
    .amat-fullscreen-btn:hover {{ background: #1f2937; }}
    .amat-hover-card,
    .amat-pin-card {{
      position: fixed;
      z-index: 9999;
      width: min(320px, calc(100vw - 32px));
      color: #e5e7eb;
      background: rgba(15, 23, 42, 0.96);
      border: 1px solid #475569;
      border-radius: 6px;
      box-shadow: 0 18px 42px rgba(0, 0, 0, 0.45);
      padding: 10px 12px;
      font-size: 13px;
      line-height: 1.35;
    }}
    .amat-hover-card {{
      display: none;
      pointer-events: auto;
    }}
    .amat-hover-card.is-visible {{ display: block; }}
    .amat-hover-body {{ margin-right: 54px; }}
    .amat-hover-card button,
    .amat-pin-card button {{
      position: absolute;
      top: 8px;
      right: 8px;
      border: 1px solid #64748b;
      border-radius: 4px;
      background: #111827;
      color: #e5e7eb;
      cursor: pointer;
      font: inherit;
      padding: 3px 8px;
    }}
    .amat-hover-card button:hover,
    .amat-pin-card button:hover {{ background: #1f2937; }}
  </style>
</head>
<body>
  <header>
    <h1>Mission Trajectory: {html.escape(scene.mission_id)}</h1>
    <p class="summary">{len(sections)} animated figure{'s' if len(sections) != 1 else ''}, including derived body-centered and rotating-frame views where applicable.</p>
  </header>
  {''.join(sections)}
</body>
</html>
"""
    output_path.write_text(document, encoding="utf-8")
    return output_path

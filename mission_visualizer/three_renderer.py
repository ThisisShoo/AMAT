from __future__ import annotations

import json
import math
from importlib.resources import files
from pathlib import Path
from typing import Any

import numpy as np

from .models import Checkpoint, EphemerisTrace, MissionPaths, MissionScene


def _load_body_assets() -> dict[str, Any]:
    try:
        p = files("mission_visualizer.assets").joinpath("bodies.json")
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _finite(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    return out if math.isfinite(out) else None


def _frame_key(frame: str | None) -> str:
    return frame or "unknown"


def _trace_payload(trace: EphemerisTrace, max_points: int = 6000) -> dict[str, Any] | None:
    df = trace.dataframe
    required = [trace.x_col, trace.y_col, trace.z_col]
    if not all(c and c in df for c in required):
        return None
    try:
        x = df[trace.x_col].astype(float).to_numpy()
        y = df[trace.y_col].astype(float).to_numpy()
        z = df[trace.z_col].astype(float).to_numpy()
        if trace.time_col and trace.time_col in df:
            t = df[trace.time_col].astype(float).to_numpy()
        else:
            t = np.arange(len(x), dtype=float)
    except Exception:
        return None

    mask = np.isfinite(x) & np.isfinite(y) & np.isfinite(z) & np.isfinite(t)
    x = x[mask]
    y = y[mask]
    z = z[mask]
    t = t[mask]
    if not len(x):
        return None

    if len(x) > max_points:
        idx = np.unique(np.linspace(0, len(x) - 1, max_points).astype(int))
        x = x[idx]
        y = y[idx]
        z = z[idx]
        t = t[idx]

    return {
        "name": trace.name,
        "kind": trace.kind,
        "object": trace.object_name,
        "frame": _frame_key(trace.frame),
        "path": str(trace.path),
        "time": [float(v) for v in t],
        "points": [[float(a), float(b), float(c)] for a, b, c in zip(x, y, z)],
    }


def _burn_intervals(scene: MissionScene) -> list[dict[str, Any]]:
    manifest = scene.manifest or {}
    intervals: list[dict[str, Any]] = []
    for key in ("finite_burns", "burn_intervals", "maneuver_segments"):
        raw = manifest.get(key, [])
        if isinstance(raw, list):
            intervals.extend(v for v in raw if isinstance(v, dict))

    normalized: list[dict[str, Any]] = []
    seen: set[tuple[str, str | None, float, float]] = set()
    for item in intervals:
        start = _finite(item.get("start_elapsed_s", item.get("start_s", item.get("start"))))
        stop = _finite(item.get("end_elapsed_s", item.get("stop_s", item.get("end"))))
        if start is None or stop is None:
            center = _finite(item.get("elapsed_s"))
            duration = _finite(item.get("duration_s"))
            if center is not None and duration is not None:
                start = center
                stop = center + duration
        if start is None or stop is None:
            continue
        if stop < start:
            start, stop = stop, start
        name = str(item.get("name") or item.get("burn") or item.get("id") or "Finite burn")
        spacecraft = item.get("spacecraft")
        key = (name, str(spacecraft) if spacecraft is not None else None, round(start, 9), round(stop, 9))
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"name": name, "spacecraft": spacecraft, "start": start, "end": stop})
    return normalized


def _checkpoint_payload(checkpoint: Checkpoint) -> dict[str, Any] | None:
    if not checkpoint.plotted or checkpoint.interpolated_xyz is None:
        return None
    x, y, z = checkpoint.interpolated_xyz
    return {
        "name": checkpoint.name,
        "spacecraft": checkpoint.spacecraft,
        "frame": _frame_key(checkpoint.frame),
        "elapsed": checkpoint.elapsed_secs,
        "utc": checkpoint.utc_gregorian,
        "point": [float(x), float(y), float(z)],
    }


def _ground_track_payload(track: Any, max_points: int = 12000) -> dict[str, Any] | None:
    df = track.dataframe
    if not track.latitude_col or not track.longitude_col:
        return None
    try:
        lat = df[track.latitude_col].astype(float).to_numpy()
        lon = df[track.longitude_col].astype(float).to_numpy()
        if track.altitude_col and track.altitude_col in df:
            alt = df[track.altitude_col].astype(float).to_numpy()
        else:
            alt = np.full(len(lat), np.nan)
        if track.time_col and track.time_col in df:
            t = df[track.time_col].astype(float).to_numpy()
        else:
            t = np.arange(len(lat), dtype=float)
    except Exception:
        return None
    mask = np.isfinite(lat) & np.isfinite(lon) & np.isfinite(t)
    lat = lat[mask]
    lon = lon[mask]
    alt = alt[mask]
    t = t[mask]
    if not len(lat):
        return None
    if len(lat) > max_points:
        idx = np.unique(np.linspace(0, len(lat) - 1, max_points).astype(int))
        lat = lat[idx]
        lon = lon[idx]
        alt = alt[idx]
        t = t[idx]
    return {
        "name": track.name,
        "spacecraft": track.spacecraft,
        "body": track.body,
        "frame": f"{track.body or 'Earth'}Fixed",
        "path": str(track.path),
        "time": [float(v) for v in t],
        "latitude": [float(v) for v in lat],
        "longitude": [float(v) for v in lon],
        "altitude": [None if not math.isfinite(float(v)) else float(v) for v in alt],
    }


def _scene_payload(scene: MissionScene) -> dict[str, Any]:
    body_assets = _load_body_assets()
    traces = [
        item
        for item in (_trace_payload(t) for t in [*scene.spacecraft_traces, *scene.body_traces])
        if item is not None
    ]
    checkpoints = [item for item in (_checkpoint_payload(c) for c in scene.checkpoints) if item is not None]
    ground_tracks = [item for item in (_ground_track_payload(gt) for gt in scene.ground_tracks) if item is not None]
    frames = [
        {
            "name": f.name,
            "origin": f.origin,
            "axes": f.axes,
            "source": f.source,
            "confidence": f.confidence,
            "primary": f.raw.get("primary"),
            "secondary": f.raw.get("secondary"),
            "x_axis": f.raw.get("x_axis"),
            "z_axis": f.raw.get("z_axis"),
        }
        for f in scene.frames
    ]
    frame_names = {f.get("name") for f in frames}
    for track in scene.ground_tracks:
        body = track.body or "Earth"
        name = f"{body}Fixed"
        existing = next((f for f in frames if f.get("name") == name), None)
        if existing:
            if not existing.get("origin"):
                existing["origin"] = body
            if not existing.get("axes"):
                existing["axes"] = "Fixed"
            if existing.get("source") in {None, "unknown", "output_parameter"}:
                existing["source"] = "ground_track"
                existing["confidence"] = "high"
        else:
            frames.append({
                "name": name,
                "origin": body,
                "axes": "Fixed",
                "source": "ground_track",
                "confidence": "high",
                "primary": None,
                "secondary": None,
                "x_axis": None,
                "z_axis": None,
            })
            frame_names.add(name)
    return {
        "missionId": scene.mission_id,
        "traces": traces,
        "checkpoints": checkpoints,
        "groundTracks": ground_tracks,
        "frames": frames,
        "warnings": scene.warnings,
        "bodyAssets": body_assets,
        "forceModelBodies": scene.manifest.get("force_model_bodies", []),
        "finiteBurns": _burn_intervals(scene),
    }


def render_three_html(scene: MissionScene, paths: MissionPaths, output: str | Path | None = None) -> Path:
    output_path = Path(output) if output else (paths.visualization_dir or (paths.mission_dir / "visualization")) / "trajectory.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(_scene_payload(scene), ensure_ascii=False, allow_nan=False)
    html = _HTML_TEMPLATE.replace("__AMAT_SCENE_DATA__", payload)
    output_path.write_text(html, encoding="utf-8")
    return output_path


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AMAT Mission Viewer</title>
<style>
html, body { margin: 0; width: 100%; height: 100%; overflow: hidden; background: #000; color: #e5e7eb; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
#viewer { position: fixed; inset: 0; background: #000; }
#canvas { display: block; width: 100%; height: 100%; }
.toolbar { position: fixed; top: 12px; left: 12px; right: 12px; z-index: 20; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; pointer-events: none; }
.toolbar > * { pointer-events: auto; }
button, select { height: 32px; border: 1px solid #334155; border-radius: 6px; background: rgba(15, 23, 42, 0.92); color: #f8fafc; padding: 0 10px; font-size: 13px; }
button:hover, select:hover { background: rgba(30, 41, 59, 0.96); }
#fullscreen { margin-left: auto; }
#time { flex: 1 1 280px; min-width: 160px; accent-color: #38bdf8; }
#timeLabel { min-width: 148px; color: #cbd5e1; font-size: 13px; text-align: right; }
#labels { position: fixed; inset: 0; z-index: 10; pointer-events: none; overflow: hidden; }
.label { position: absolute; transform: translate(-50%, -120%); padding: 3px 6px; border: 1px solid rgba(148, 163, 184, 0.45); border-radius: 5px; background: rgba(2, 6, 23, 0.82); color: #f8fafc; font-size: 11px; max-width: 180px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.label.checkpoint { color: #fde68a; }
#tooltip { position: fixed; z-index: 30; display: none; max-width: 300px; padding: 8px 10px; border: 1px solid #475569; border-radius: 6px; background: rgba(2, 6, 23, 0.96); color: #f8fafc; font-size: 12px; line-height: 1.35; pointer-events: none; }
#status { position: fixed; left: 12px; bottom: 12px; z-index: 20; color: #94a3b8; font-size: 12px; max-width: min(720px, calc(100vw - 24px)); }
#error { position: fixed; inset: 0; display: none; place-items: center; z-index: 50; background: #000; color: #fecaca; padding: 32px; text-align: center; }
</style>
</head>
<body>
<div id="viewer"><canvas id="canvas"></canvas></div>
<div class="toolbar">
  <select id="frame"></select>
  <button id="play" type="button">Pause</button>
  <input id="time" type="range" min="0" max="1000" value="0">
  <span id="timeLabel"></span>
  <button id="dragMode" type="button">Move</button>
  <button id="home" type="button">Home</button>
  <button id="fullscreen" type="button">Full screen</button>
</div>
<div id="labels"></div>
<div id="tooltip"></div>
<div id="status"></div>
<div id="error"></div>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script>
const DATA = __AMAT_SCENE_DATA__;

function showError(message) {
  const box = document.getElementById('error');
  box.textContent = message;
  box.style.display = 'grid';
}

if (!window.THREE) {
  showError('Three.js could not be loaded. Connect to the network or vendor three.min.js for offline viewing.');
} else {
  initViewer();
}

function initViewer() {
  const THREE = window.THREE;
  const canvas = document.getElementById('canvas');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, logarithmicDepthBuffer: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 1e-9, 1e12);
  camera.up.set(0, 0, 1);
  const labels = document.getElementById('labels');
  const tooltip = document.getElementById('tooltip');
  const frameSelect = document.getElementById('frame');
  const playButton = document.getElementById('play');
  const dragModeButton = document.getElementById('dragMode');
  const timeSlider = document.getElementById('time');
  const timeLabel = document.getElementById('timeLabel');
  const status = document.getElementById('status');

  scene.add(new THREE.AmbientLight(0xffffff, 0.85));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2);
  sun.position.set(2, 1.5, 1);
  scene.add(sun);

  const originRadii = (DATA.frames || [])
    .map(f => f.origin ? ((DATA.bodyAssets[f.origin] || {}).radius_km || 0) : 0)
    .filter(v => Number.isFinite(v));
  const allPoints = DATA.traces.flatMap(t => t.points || []);
  const extentKm = Math.max(1, ...originRadii, ...allPoints.flatMap(p => p.map(v => Math.abs(v))));
  const scale = 1 / extentKm;
  const markerRadiusFloor = 0.00072;
  const frames = Array.from(new Set(
    (DATA.frames || []).map(f => f.name)
      .concat(DATA.traces.map(t => t.frame))
      .concat(DATA.checkpoints.map(c => c.frame))
      .concat((DATA.groundTracks || []).map(g => g.frame))
  )).filter(Boolean);
  if (!frames.length) frames.push('unknown');
  frames.forEach(f => {
    const opt = document.createElement('option');
    opt.value = f;
    opt.textContent = f;
    frameSelect.appendChild(opt);
  });

  const root = new THREE.Group();
  scene.add(root);
  const textureLoader = new THREE.TextureLoader();
  textureLoader.setCrossOrigin('anonymous');
  const pickables = [];
  const animated = [];
  const labelItems = [];
  let currentFrame = frames[0];
  let times = [];
  let timeIndex = 0;
  let playing = true;
  let dragMode = 'orbit';
  let activeDragMode = 'orbit';

  const palette = {
    spacecraft: 0xf8fafc,
    checkpoint: 0xfacc15,
    burn: 0xfb923c,
    path: 0x38bdf8,
    groundProjection: 0x0ea5e9,
    altitudeStem: 0xfacc15,
    bodyPath: 0x64748b,
    xAxis: 0xef4444,
    yAxis: 0x22c55e,
    zAxis: 0x60a5fa,
    grid: 0x334155
  };

  function colorForBody(name) {
    const meta = DATA.bodyAssets[name] || {};
    return new THREE.Color(meta.color || meta.orbit_color || '#9ca3af');
  }

  function makeBodyTexture(name) {
    const meta = DATA.bodyAssets[name] || {};
    const texture = meta.texture || 'plain';
    const base = meta.color || '#9ca3af';
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = base;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (texture === 'earth') {
      const ocean = ctx.createLinearGradient(0, 0, 0, canvas.height);
      ocean.addColorStop(0, '#1d4ed8');
      ocean.addColorStop(0.45, '#0f5ea8');
      ocean.addColorStop(1, '#082f6f');
      ctx.fillStyle = ocean;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = '#15803d';
      for (let i = 0; i < 28; i++) {
        const x = (i * 41) % 270 - 20;
        const y = (i * 23) % 118 + 5;
        ctx.beginPath();
        ctx.ellipse(x, y, 16 + (i % 5) * 7, 5 + (i % 4) * 5, (i % 7) * 0.45, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = '#d9f99d';
      for (let i = 0; i < 12; i++) {
        ctx.beginPath();
        ctx.ellipse((i * 73) % 256, (i * 31) % 128, 12 + (i % 3) * 8, 3 + (i % 2) * 3, 0.2 * i, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = 'rgba(255,255,255,0.58)';
      for (let i = 0; i < 26; i++) {
        ctx.beginPath();
        ctx.ellipse((i * 59) % 256, (i * 17) % 128, 18 + (i % 4) * 8, 1.6 + (i % 3), 0.15 * i, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = 'rgba(255,255,255,0.86)';
      ctx.fillRect(0, 0, 256, 8);
      ctx.fillRect(0, 120, 256, 8);
    } else if (texture === 'luna' || texture === 'moon') {
      const lunar = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
      lunar.addColorStop(0, '#d4d4d4');
      lunar.addColorStop(0.5, '#8b8b8b');
      lunar.addColorStop(1, '#525252');
      ctx.fillStyle = lunar;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = 'rgba(35,35,35,0.30)';
      for (let i = 0; i < 58; i++) {
        ctx.beginPath();
        ctx.arc((i * 37) % 256, (i * 23) % 128, 2 + (i % 9), 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.fillStyle = 'rgba(245,245,245,0.22)';
      for (let i = 0; i < 24; i++) {
        ctx.beginPath();
        ctx.arc((i * 53) % 256, (i * 29) % 128, 2 + (i % 5), 0, Math.PI * 2);
        ctx.fill();
      }
    } else if (texture === 'bands' || texture === 'sun') {
      for (let y = 0; y < 128; y += 10) {
        ctx.fillStyle = y % 20 === 0 ? (meta.band_light || 'rgba(255,255,255,0.18)') : (meta.band_dark || 'rgba(0,0,0,0.18)');
        ctx.fillRect(0, y, 256, 6);
      }
    }
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
  }

  function makeBodyMaterial(name) {
    const meta = DATA.bodyAssets[name] || {};
    const fallback = makeBodyTexture(name);
    const material = new THREE.MeshStandardMaterial({ map: fallback, roughness: 0.92, metalness: 0.0 });
    if (meta.texture_url) {
      textureLoader.load(
        meta.texture_url,
        texture => {
          texture.colorSpace = THREE.SRGBColorSpace;
          texture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy ? renderer.capabilities.getMaxAnisotropy() : 1);
          material.map = texture;
          material.needsUpdate = true;
        },
        undefined,
        () => {
          material.map = fallback;
          material.needsUpdate = true;
        }
      );
    }
    return material;
  }

  function kmToWorld(p) {
    return new THREE.Vector3(p[0] * scale, p[1] * scale, p[2] * scale);
  }

  function makeLine(points, color, opacity = 1) {
    const geometry = new THREE.BufferGeometry().setFromPoints(points.map(kmToWorld));
    const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
    return new THREE.Line(geometry, material);
  }

  function makeWorldLine(points, color, opacity = 1) {
    const geometry = new THREE.BufferGeometry().setFromPoints(points);
    const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
    return new THREE.Line(geometry, material);
  }

  function burnIntervalsFor(trace) {
    return DATA.finiteBurns.filter(b => !b.spacecraft || b.spacecraft === trace.object);
  }

  function timeInBurn(t, burns) {
    return burns.some(b => t >= b.start && t <= b.end);
  }

  function segmentSpacecraftPath(trace) {
    const normal = [];
    const burn = [];
    const burns = burnIntervalsFor(trace);
    const pts = trace.points || [];
    const ts = trace.time || [];
    for (let i = 0; i < pts.length - 1; i++) {
      const a = pts[i];
      const b = pts[i + 1];
      const ta = ts[i];
      const tb = ts[i + 1];
      const midpoint = Number.isFinite(ta) && Number.isFinite(tb) ? (ta + tb) * 0.5 : ta;
      const target = timeInBurn(midpoint, burns) ? burn : normal;
      target.push([a, b]);
    }
    return { normal, burn };
  }

  function addSegmentLines(segments, color, opacity, label) {
    segments.forEach(pair => {
      const line = makeLine(pair, color, opacity);
      if (label) line.userData = { label };
      root.add(line);
    });
  }

  function addVector(name, direction, color) {
    const length = 1.18;
    const dir = direction.clone().normalize();
    const origin = new THREE.Vector3(0, 0, 0);
    const arrow = new THREE.ArrowHelper(dir, origin, length, color, 0.075, 0.035);
    arrow.userData = { label: name + ' vector' };
    root.add(arrow);

    const anchor = new THREE.Object3D();
    anchor.position.copy(dir.multiplyScalar(length * 1.05));
    anchor.userData = { label: name + ' vector', kind: 'axis' };
    root.add(anchor);
    addLabel(anchor, name, 'axis');
  }

  function addReferenceVectors() {
    addVector('X', new THREE.Vector3(1, 0, 0), palette.xAxis);
    addVector('Y', new THREE.Vector3(0, 1, 0), palette.yAxis);
    addVector('Z', new THREE.Vector3(0, 0, 1), palette.zAxis);
  }

  function addXYPlaneRings() {
    const material = new THREE.LineBasicMaterial({ color: palette.grid, transparent: true, opacity: 0.42 });
    const ringCount = 8;
    const segments = 160;
    for (let r = 1; r <= ringCount; r++) {
      const radius = (r / ringCount) * 1.05;
      const pts = [];
      for (let i = 0; i <= segments; i++) {
        const a = (i / segments) * Math.PI * 2;
        pts.push(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0));
      }
      const line = new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), material);
      line.userData = { label: 'X-Y plane radius ' + Math.round(radius * extentKm).toLocaleString() + ' km' };
      root.add(line);
    }
  }

  function makeBodyMesh(name) {
    const meta = DATA.bodyAssets[name] || {};
    const radius = bodyMeshRadius(name);
    const geometry = new THREE.SphereGeometry(radius, 64, 32);
    const material = makeBodyMaterial(name);
    const mesh = new THREE.Mesh(geometry, material);
    // Three.js sphere UV poles are on local Y. Rotate the mesh so body poles align with world Z.
    mesh.rotation.x = Math.PI / 2;
    mesh.userData = { label: name, kind: 'body' };
    return mesh;
  }

  function interpolate(trace, t) {
    const ts = trace.time || [];
    const pts = trace.points || [];
    if (!pts.length) return new THREE.Vector3();
    if (!ts.length || t <= ts[0]) return kmToWorld(pts[0]);
    if (t >= ts[ts.length - 1]) return kmToWorld(pts[pts.length - 1]);
    let hi = 1;
    while (hi < ts.length && ts[hi] < t) hi++;
    const lo = Math.max(0, hi - 1);
    const f = (t - ts[lo]) / Math.max(1e-12, ts[hi] - ts[lo]);
    const a = pts[lo], b = pts[hi];
    return kmToWorld([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]);
  }

  function bodyRadiusKm(name) {
    const meta = DATA.bodyAssets[name] || {};
    return meta.radius_km || extentKm * 0.01;
  }

  function bodyMeshRadius(name) {
    const meta = DATA.bodyAssets[name] || {};
    return (meta.radius_km || extentKm * 0.01) * scale;
  }

  function frameBodyNames(frameName) {
    const names = new Set();
    const frameInfo = (DATA.frames || []).find(f => f.name === frameName);
    if (frameInfo && frameInfo.origin) names.add(frameInfo.origin);
    if (frameInfo && frameInfo.secondary) names.add(frameInfo.secondary);
    DATA.traces
      .filter(t => t.frame === frameName && t.kind === 'body')
      .forEach(t => names.add(t.object));
    return Array.from(names).filter(name => DATA.bodyAssets[name]);
  }

  function frameSmallestBodyRadius(frameName) {
    const radii = frameBodyNames(frameName).map(bodyMeshRadius).filter(v => Number.isFinite(v) && v > 0);
    return radii.length ? Math.min(...radii) : 0.004;
  }

  function sceneMarkerRadius(kind) {
    const bodyLimit = frameSmallestBodyRadius(currentFrame);
    const preferred = kind === 'checkpoint' ? 0.0015 : 0.0018;
    return Math.min(preferred, Math.max(Math.min(markerRadiusFloor, bodyLimit * 0.2), bodyLimit * 0.35));
  }

  function latLonToWorld(bodyName, latDeg, lonDeg, altitudeKm = 0) {
    const lat = latDeg * Math.PI / 180;
    const lon = lonDeg * Math.PI / 180;
    const radius = (bodyRadiusKm(bodyName) + altitudeKm) * scale;
    const cosLat = Math.cos(lat);
    return new THREE.Vector3(
      radius * cosLat * Math.cos(lon),
      radius * cosLat * Math.sin(lon),
      radius * Math.sin(lat)
    );
  }

  function groundTrackAltitude(track, index) {
    const alt = track.altitude || [];
    const value = alt[index];
    return Number.isFinite(value) ? value : 0;
  }

  function groundTrackPoint(track, index, includeAltitude = true) {
    const lat = track.latitude || [];
    const lon = track.longitude || [];
    return latLonToWorld(track.body, lat[index], lon[index], includeAltitude ? groundTrackAltitude(track, index) : 0);
  }

  function interpolateGroundTrack(track, t, includeAltitude = true) {
    const ts = track.time || [];
    const lat = track.latitude || [];
    const lon = track.longitude || [];
    const alt = track.altitude || [];
    if (!lat.length || !lon.length) return new THREE.Vector3();
    if (!ts.length || t <= ts[0]) return groundTrackPoint(track, 0, includeAltitude);
    if (t >= ts[ts.length - 1]) return groundTrackPoint(track, lat.length - 1, includeAltitude);
    let hi = 1;
    while (hi < ts.length && ts[hi] < t) hi++;
    const lo = Math.max(0, hi - 1);
    const f = (t - ts[lo]) / Math.max(1e-12, ts[hi] - ts[lo]);
    const latValue = lat[lo] + (lat[hi] - lat[lo]) * f;
    let lonDelta = lon[hi] - lon[lo];
    if (lonDelta > 180) lonDelta -= 360;
    if (lonDelta < -180) lonDelta += 360;
    const lonValue = lon[lo] + lonDelta * f;
    const altLo = Number.isFinite(alt[lo]) ? alt[lo] : 0;
    const altHi = Number.isFinite(alt[hi]) ? alt[hi] : altLo;
    const altValue = altLo + (altHi - altLo) * f;
    return latLonToWorld(track.body, latValue, lonValue, includeAltitude ? altValue : 0);
  }

  function makeConnector(a, b, color, opacity = 1) {
    const geometry = new THREE.BufferGeometry().setFromPoints([a, b]);
    const material = new THREE.LineBasicMaterial({ color, transparent: opacity < 1, opacity });
    return new THREE.Line(geometry, material);
  }

  function updateConnector(line, a, b) {
    const position = line.geometry.attributes.position;
    position.setXYZ(0, a.x, a.y, a.z);
    position.setXYZ(1, b.x, b.y, b.z);
    position.needsUpdate = true;
    line.geometry.computeBoundingSphere();
  }

  function median(values) {
    const nums = values.filter(v => Number.isFinite(v)).sort((a, b) => a - b);
    if (!nums.length) return null;
    return nums[Math.floor(nums.length / 2)];
  }

  function traceDistanceKm(trace) {
    if (!trace || !trace.points || !trace.points.length) return null;
    return median(trace.points.map(p => Math.hypot(p[0], p[1], p[2])));
  }

  function knownPairDistanceKm(a, b) {
    const pair = [a, b].filter(Boolean).sort().join('-');
    if (pair === 'Earth-Luna' || pair === 'Earth-Moon') return 384400;
    if (pair === 'Earth-Sun') return 149597870.7;
    return null;
  }

  function bodyPairDistanceKm(origin, companion) {
    const directFrame = origin + 'MJ2000Eq';
    const reverseFrame = companion + 'MJ2000Eq';
    const direct = DATA.traces.find(t => t.kind === 'body' && t.object === companion && t.frame === directFrame);
    const reverse = DATA.traces.find(t => t.kind === 'body' && t.object === origin && t.frame === reverseFrame);
    return traceDistanceKm(direct) || traceDistanceKm(reverse) || knownPairDistanceKm(origin, companion) || (extentKm * 0.5);
  }

  function addStaticBody(name, position, labelSuffix = '') {
    if (!name || !DATA.bodyAssets[name]) return null;
    const mesh = makeBodyMesh(name);
    mesh.position.copy(position);
    mesh.userData = { label: name + labelSuffix, kind: 'body' };
    root.add(mesh);
    pickables.push(mesh);
    addLabel(mesh, name, 'body');
    return mesh;
  }

  function staticBodyPosition(origin, bodyName, slot) {
    if (origin && bodyName === origin) return new THREE.Vector3(0, 0, 0);
    const distanceKm = bodyPairDistanceKm(origin, bodyName);
    const directions = [
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(-1, 0, 0),
      new THREE.Vector3(0, -1, 0),
      new THREE.Vector3(0, 0, -1),
    ];
    return directions[slot % directions.length].clone().multiplyScalar(distanceKm * scale);
  }

  function rebuildFrame() {
    root.clear();
    pickables.length = 0;
    animated.length = 0;
    labelItems.length = 0;
    labels.replaceChildren();
    const traces = DATA.traces.filter(t => t.frame === currentFrame);
    const groundTracks = (DATA.groundTracks || []).filter(g => g.frame === currentFrame);
    times = Array.from(new Set(
      traces.flatMap(t => t.time || []).concat(groundTracks.flatMap(g => g.time || []))
    )).sort((a, b) => a - b);
    timeIndex = Math.min(timeIndex, Math.max(0, times.length - 1));
    timeSlider.disabled = times.length < 2;
    addXYPlaneRings();
    addReferenceVectors();

    const frameInfo = (DATA.frames || []).find(f => f.name === currentFrame);
    const originName = frameInfo && frameInfo.origin;
    const staticBodies = new Set();
    const originHasTrace = originName && traces.some(t => t.kind === 'body' && t.object === originName);
    if (originName && !originHasTrace && DATA.bodyAssets[originName]) {
      addStaticBody(originName, new THREE.Vector3(0, 0, 0));
      staticBodies.add(originName);
    }

    const companionName = frameInfo && frameInfo.secondary && frameInfo.secondary !== originName ? frameInfo.secondary : null;
    const companionHasTrace = companionName && traces.some(t => t.kind === 'body' && t.object === companionName);
    if (originName && companionName && !companionHasTrace && DATA.bodyAssets[companionName]) {
      const distanceKm = bodyPairDistanceKm(originName, companionName);
      addStaticBody(companionName, new THREE.Vector3(distanceKm * scale, 0, 0), ' (rotating-frame companion)');
      staticBodies.add(companionName);
    }

    traces.forEach(trace => {
      if (!trace.points || trace.points.length < 1) return;
      if (trace.kind === 'spacecraft' && trace.points.length > 1) {
        const pieces = segmentSpacecraftPath(trace);
        addSegmentLines(pieces.normal, palette.path, 0.95, trace.object + ' coast');
        addSegmentLines(pieces.burn, palette.burn, 1, trace.object + ' finite burn');
      } else if (trace.points.length > 1) {
        root.add(makeLine(trace.points, colorForBody(trace.object), 0.55));
      }

      const start = kmToWorld(trace.points[0]);
      let mesh;
      if (trace.kind === 'body') {
        mesh = makeBodyMesh(trace.object);
      } else {
        const geometry = new THREE.SphereGeometry(sceneMarkerRadius('spacecraft'), 18, 12);
        const material = new THREE.MeshBasicMaterial({ color: palette.spacecraft });
        mesh = new THREE.Mesh(geometry, material);
      }
      mesh.position.copy(start);
      mesh.userData = { label: trace.object, kind: trace.kind, trace };
      root.add(mesh);
      pickables.push(mesh);
      animated.push({ mesh, trace });
      addLabel(mesh, trace.object, trace.kind);
    });

    groundTracks.forEach(track => {
      const lat = track.latitude || [];
      const lon = track.longitude || [];
      if (!lat.length || !lon.length) return;
      const surfacePts = [];
      const spacePts = [];
      for (let i = 0; i < Math.min(lat.length, lon.length); i++) {
        surfacePts.push(groundTrackPoint(track, i, false));
        spacePts.push(groundTrackPoint(track, i, true));
      }
      if (surfacePts.length > 1) {
        const projection = makeWorldLine(surfacePts, palette.groundProjection, 0.42);
        projection.userData = { label: track.name + ' surface projection' };
        root.add(projection);
      }
      if (spacePts.length > 1) {
        const path = makeWorldLine(spacePts, palette.path, 0.95);
        path.userData = { label: track.name + ' 3D Earth-fixed path' };
        root.add(path);
      }
      const geometry = new THREE.SphereGeometry(sceneMarkerRadius('spacecraft'), 18, 12);
      const material = new THREE.MeshBasicMaterial({ color: palette.spacecraft });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(spacePts[0]);
      mesh.userData = { label: track.spacecraft || track.name, kind: 'spacecraft', groundTrack: track };
      root.add(mesh);
      pickables.push(mesh);
      const connector = makeConnector(surfacePts[0], spacePts[0], palette.altitudeStem, 0.62);
      connector.userData = { label: (track.spacecraft || track.name) + ' altitude above surface' };
      root.add(connector);
      animated.push({ mesh, groundTrack: track, connector });
      addLabel(mesh, track.spacecraft || track.name, 'spacecraft');
    });

    DATA.checkpoints.filter(c => c.frame === currentFrame).forEach((cp, index) => {
      const geometry = new THREE.SphereGeometry(sceneMarkerRadius('checkpoint'), 16, 12);
      const material = new THREE.MeshBasicMaterial({ color: palette.checkpoint });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(kmToWorld(cp.point));
      mesh.userData = { label: (index + 1) + '. ' + cp.name, kind: 'checkpoint', checkpoint: cp };
      root.add(mesh);
      pickables.push(mesh);
      addLabel(mesh, String(index + 1), 'checkpoint');
    });

    resetCamera();
    updateTime();
    status.textContent = DATA.missionId + ' | ' + currentFrame + ' | ' + traces.length + ' traces | ' + groundTracks.length + ' ground tracks';
  }

  function addLabel(object, text, kind) {
    const el = document.createElement('div');
    el.className = 'label ' + kind;
    el.textContent = text;
    labels.appendChild(el);
    labelItems.push({ object, el, text });
  }

  const orbit = { target: new THREE.Vector3(), distance: 2.8, yaw: 0.75, pitch: 0.55 };

  function resetCamera() {
    orbit.target.set(0, 0, 0);
    orbit.distance = 2.8;
    orbit.yaw = 0.75;
    orbit.pitch = 0.55;
    updateCamera();
  }

  function focusOn(position) {
    orbit.target.copy(position);
    orbit.distance = Math.max(0.025, orbit.distance * 0.45);
    updateCamera();
  }

  function updateCamera() {
    orbit.pitch = Math.max(-1.54, Math.min(1.54, orbit.pitch));
    orbit.distance = Math.max(1e-9, orbit.distance);
    const cp = Math.cos(orbit.pitch);
    camera.position.set(
      orbit.target.x + orbit.distance * cp * Math.cos(orbit.yaw),
      orbit.target.y + orbit.distance * cp * Math.sin(orbit.yaw),
      orbit.target.z + orbit.distance * Math.sin(orbit.pitch)
    );
    camera.lookAt(orbit.target);
  }

  function resize() {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  }

  function updateTime() {
    if (times.length) {
      const t = times[timeIndex] || times[0];
      animated.forEach(item => {
        if (item.trace) item.mesh.position.copy(interpolate(item.trace, t));
        if (item.groundTrack) {
          const satellite = interpolateGroundTrack(item.groundTrack, t, true);
          item.mesh.position.copy(satellite);
          if (item.connector) {
            const surface = interpolateGroundTrack(item.groundTrack, t, false);
            updateConnector(item.connector, surface, satellite);
          }
        }
      });
      const start = times[0];
      const stop = times[times.length - 1];
      timeSlider.value = stop > start ? String(Math.round(((t - start) / (stop - start)) * 1000)) : '0';
      timeLabel.textContent = 'T+' + Math.round(t).toLocaleString() + ' s';
    } else {
      timeLabel.textContent = '';
    }
  }

  function updateLabels() {
    const rect = renderer.domElement.getBoundingClientRect();
    const width = Math.max(1, rect.width);
    const height = Math.max(1, rect.height);
    const projected = [];
    const worldPosition = new THREE.Vector3();
    labelItems.forEach(item => {
      item.object.getWorldPosition(worldPosition);
      const v = worldPosition.clone().project(camera);
      const visible = v.z > -1 && v.z < 1;
      const x = rect.left + (v.x * 0.5 + 0.5) * width;
      const y = rect.top + (-v.y * 0.5 + 0.5) * height;
      projected.push({ item, x, y, visible });
    });
    projected.sort((a, b) => a.y - b.y);
    const buckets = [];
    projected.forEach(p => {
      if (!p.visible) {
        p.item.el.style.display = 'none';
        return;
      }
      const near = buckets.find(b => Math.hypot(b.x - p.x, b.y - p.y) < 28);
      if (near) {
        near.items.push(p);
      } else {
        buckets.push({ x: p.x, y: p.y, items: [p] });
      }
    });
    buckets.forEach(bucket => {
      bucket.items.forEach((p, i) => {
        p.item.el.style.display = i === 0 ? 'block' : 'none';
        if (i === 0) {
          p.item.el.style.left = bucket.x + 'px';
        p.item.el.style.top = bucket.y + 'px';
          p.item.el.textContent = bucket.items.length > 1 ? bucket.items.map(q => q.item.text).join(', ') : p.item.text;
        }
      });
    });
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  function pick(event) {
    pointer.x = (event.clientX / window.innerWidth) * 2 - 1;
    pointer.y = -(event.clientY / window.innerHeight) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    return raycaster.intersectObjects(pickables, false)[0] || null;
  }

  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  canvas.addEventListener('pointerdown', e => {
    dragging = true;
    activeDragMode = (dragMode === 'move' || e.shiftKey || e.button === 1 || e.button === 2) ? 'move' : 'orbit';
    lastX = e.clientX;
    lastY = e.clientY;
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', e => {
    const hit = pick(e);
    if (hit && !dragging) {
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 12) + 'px';
      tooltip.style.top = (e.clientY + 12) + 'px';
      tooltip.textContent = hit.object.userData.label || '';
    } else if (!hit) {
      tooltip.style.display = 'none';
    }
    if (!dragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    if (activeDragMode === 'move') {
      const panScale = orbit.distance * 0.0018;
      const right = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 0);
      const up = new THREE.Vector3().setFromMatrixColumn(camera.matrix, 1);
      orbit.target.addScaledVector(right, -dx * panScale).addScaledVector(up, dy * panScale);
    } else {
      orbit.yaw -= dx * 0.006;
      orbit.pitch += dy * 0.006;
    }
    updateCamera();
  });
  canvas.addEventListener('pointerup', e => {
    dragging = false;
    try { canvas.releasePointerCapture(e.pointerId); } catch (_) {}
  });
  canvas.addEventListener('contextmenu', e => e.preventDefault());
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    orbit.distance *= Math.exp(e.deltaY * 0.001);
    updateCamera();
  }, { passive: false });
  canvas.addEventListener('dblclick', e => {
    const hit = pick(e);
    if (hit) focusOn(hit.object.position);
  });

  frameSelect.addEventListener('change', () => {
    currentFrame = frameSelect.value;
    rebuildFrame();
  });
  playButton.addEventListener('click', () => {
    playing = !playing;
    playButton.textContent = playing ? 'Pause' : 'Play';
  });
  dragModeButton.addEventListener('click', () => {
    dragMode = dragMode === 'orbit' ? 'move' : 'orbit';
    dragModeButton.textContent = dragMode === 'move' ? 'Orbit' : 'Move';
    canvas.style.cursor = dragMode === 'move' ? 'grab' : 'default';
  });
  timeSlider.addEventListener('input', () => {
    if (times.length < 2) return;
    playing = false;
    playButton.textContent = 'Play';
    timeIndex = Math.round((Number(timeSlider.value) / 1000) * (times.length - 1));
    updateTime();
  });
  document.getElementById('home').addEventListener('click', resetCamera);
  document.getElementById('fullscreen').addEventListener('click', async () => {
    const target = document.getElementById('viewer');
    try {
      if (!document.fullscreenElement) {
        await (target.requestFullscreen ? target.requestFullscreen() : document.documentElement.requestFullscreen());
      } else {
        await document.exitFullscreen();
      }
    } finally {
      setTimeout(resize, 60);
    }
  });
  document.addEventListener('fullscreenchange', resize);
  window.addEventListener('resize', resize);

  let lastStep = performance.now();
  function animate(now) {
    requestAnimationFrame(animate);
    if (playing && times.length > 1 && now - lastStep > 80) {
      timeIndex = (timeIndex + 1) % times.length;
      updateTime();
      lastStep = now;
    }
    updateLabels();
    renderer.render(scene, camera);
  }

  resize();
  rebuildFrame();
  requestAnimationFrame(animate);
}
</script>
</body>
</html>
"""

# AMAT MissionSpec Reference

This document explains how to manually write `mission_spec.json` files for the AMAT simulation layer.

AMAT is designed for users who may not know GMAT scripting. You describe the mission in JSON, and AMAT generates GMAT artifacts, runs the simulation, and writes viewer-ready output files.

## Core idea

A MissionSpec is the source of truth for a mission.

```text
mission_spec.json
  -> AMAT validation
  -> canonical MissionSpec
  -> GMAT script and Python runner
  -> GMAT execution
  -> spacecraft ephemeris, checkpoints, body ephemeris, visualization manifest
```

Normal operation is controlled by editing `mission_spec.json`. Terminal commands are only for compiling, running, and troubleshooting.

## Minimal top-level structure

```json
{
  "schema_version": "0.2.0",
  "mission_id": "MY_MISSION",
  "mission_name": "My mission",
  "description": "Short description.",
  "conventions": {
    "time_scale": "UTC",
    "distance_unit": "km",
    "velocity_unit": "km/s",
    "angle_unit": "deg",
    "mass_unit": "kg"
  },
  "visualization": {
    "enabled": true,
    "auto_export_after_run": true,
    "clean_csv": true,
    "write_manifest": true,
    "include_spice_body_ephemerides": true
  },
  "bodies": [],
  "reference_frames": [],
  "spacecraft": [],
  "force_models": [],
  "propagators": [],
  "burns": [],
  "outputs": [],
  "checkpoints": [],
  "events": [],
  "mission_sequence": [],
  "external_dependencies": []
}
```

## Top-level field summary

| Field | Required | Purpose |
|---|---:|---|
| `schema_version` | Yes | Schema version. Use `0.2.0`. |
| `mission_id` | Yes | Stable artifact ID. Used in generated paths and manifests. |
| `mission_name` | Yes | Human-readable mission name. |
| `description` | No | Mission summary. |
| `conventions` | Yes | Global time and unit conventions. |
| `visualization` | No | Controls automatic viewer artifact generation. |
| `bodies` | No | Declares celestial bodies, including custom/fictitious bodies. |
| `reference_frame_sets` | No | Pulls reusable frame presets from catalog. |
| `reference_frames` | No | Explicit coordinate-system/frame definitions. |
| `spacecraft` | Yes | Spacecraft definitions and initial states. |
| `force_models` | Yes | Gravity and force environments. |
| `propagators` | Yes | Integrator and force-model selection. |
| `burns` | No | Reusable impulsive burn definitions. |
| `outputs` | No | Full ephemeris, body ephemeris, and final-state requests. |
| `checkpoints` | No | Sparse state snapshots written at mission-sequence locations. |
| `events` | No | Event definitions that stop propagation and trigger actions. |
| `mission_sequence` | Yes | Ordered phase/step mission timeline. |
| `external_dependencies` | No | SPICE ephemeris and other external data declarations. |

## Naming rules

IDs such as `mission_id`, spacecraft `id`, propagator `id`, and checkpoint `id` should use letters, numbers, `_`, or `-`.

GMAT object names such as spacecraft `name`, force model `name`, propagator `name`, and burn `name` should start with a letter and then use letters, numbers, or `_` only.

Good:

```text
EventSat
EarthFM
RaiseApogeeTo500km
event_test_spacecraft_ephemeris
```

Avoid:

```text
Event Sat
1Sat
Raise-Apogee
Earth.FM
```

## Conventions

Use this convention block unless there is a specific reason to change it:

```json
{
  "time_scale": "UTC",
  "distance_unit": "km",
  "velocity_unit": "km/s",
  "angle_unit": "deg",
  "mass_unit": "kg"
}
```

Generated GMAT scripts and viewer CSVs assume these conventions.

## Visualization settings

Recommended default:

```json
{
  "visualization": {
    "enabled": true,
    "auto_export_after_run": true,
    "clean_csv": true,
    "write_manifest": true,
    "include_spice_body_ephemerides": true
  }
}
```

Behavior:

- `enabled`: writes visualization artifacts.
- `auto_export_after_run`: refreshes viewer files when `generated_mission.py --run` finishes.
- `clean_csv`: removes GMAT ReportFile spacer columns where possible.
- `write_manifest`: writes `visualization_manifest.json`.
- `include_spice_body_ephemerides`: exports resolved SPICE body ephemerides when available.

## Bodies

Bodies are optional for GMAT built-ins, but declaring them improves portability and viewer metadata.

Example:

```json
{
  "bodies": [
    {
      "id": "earth",
      "name": "Earth",
      "type": "planet",
      "ephemeris": {
        "source": "gmat_builtin",
        "assume_backend_available": true
      }
    },
    {
      "id": "luna",
      "name": "Luna",
      "type": "moon",
      "ephemeris": {
        "source": "spice",
        "dependency_id": "dep_luna_spice",
        "assume_backend_available": true
      }
    }
  ]
}
```

Supported body `type` values include:

```text
star, planet, moon, asteroid, comet, barycenter, custom, fictitious
```

For custom or fictitious bodies, AMAT can preserve the declaration for future backend use. The current GMAT backend assumes any body referenced in a GMAT force model is already known to GMAT or otherwise configured externally.

## Reference frames

Reference frames may be explicitly defined in `reference_frames[]` or loaded from catalog presets in `reference_frame_sets[]`.

Catalog file:

```text
configs/reference_frames/standard_gmat_reference_frames.json
```

Example explicit Earth inertial frame:

```json
{
  "id": "earth_mj2000_eq",
  "name": "EarthMJ2000Eq",
  "type": "body_inertial_equatorial",
  "origin": "Earth",
  "orientation": "MJ2000Eq",
  "axes": "MJ2000Eq",
  "description": "Earth-centered MJ2000 equatorial frame. Treated as GMAT built-in.",
  "backend_overrides": {
    "gmat": {
      "name": "EarthMJ2000Eq",
      "create_coordinate_system": false,
      "origin": "Earth",
      "axes": "MJ2000Eq"
    }
  }
}
```

Example non-Earth body-centered frame:

```json
{
  "id": "luna_mj2000_eq",
  "name": "LunaMJ2000Eq",
  "type": "body_inertial_equatorial",
  "origin": "Luna",
  "orientation": "MJ2000Eq",
  "axes": "MJ2000Eq",
  "backend_overrides": {
    "gmat": {
      "name": "LunaMJ2000Eq",
      "create_coordinate_system": true,
      "origin": "Luna",
      "axes": "MJ2000Eq"
    }
  }
}
```

Supported GMAT axis names include:

```text
MJ2000Eq, MJ2000Ec, TOEEq, TOEEc, MOEEq, MOEEc,
TODEq, TODEc, MODEq, MODEc, ObjectReferenced, Equator,
BodyFixed, BodyInertial, GSE, GSM, Topocentric,
LocalAlignedConstrained, SPICE, ICRF, BodySpinSun, TEME
```

Specialized frames may require extra GMAT fields. Put those fields under `backend_overrides.gmat` so AMAT preserves and emits them.

## Spacecraft

Each spacecraft needs an ID, GMAT object name, epoch, frame, state, and mass.

### Keplerian state

```json
{
  "id": "sat",
  "name": "EventSat",
  "epoch": "01 Jun 2026 00:00:00.000",
  "frame": "EarthMJ2000Eq",
  "state_type": "keplerian",
  "sma_km": 6678.1363,
  "ecc": 0.0,
  "inc_deg": 35.0,
  "raan_deg": 0.0,
  "aop_deg": 0.0,
  "ta_deg": 0.0,
  "dry_mass_kg": 500.0
}
```

Required Keplerian fields:

| Field | Unit | Meaning |
|---|---|---|
| `sma_km` | km | Semi-major axis. |
| `ecc` | unitless | Eccentricity. |
| `inc_deg` | deg | Inclination. |
| `raan_deg` | deg | Right ascension of ascending node. |
| `aop_deg` | deg | Argument of periapsis. |
| `ta_deg` | deg | True anomaly. |

### Cartesian state

```json
{
  "id": "sat",
  "name": "Sat",
  "epoch": "01 Jun 2026 00:00:00.000",
  "frame": "EarthMJ2000Eq",
  "state_type": "cartesian",
  "position_km": [6678.1363, 0, 0],
  "velocity_km_s": [0, 7.7258, 0],
  "dry_mass_kg": 500.0
}
```

## Force models

A force model describes central gravity and optional third-body gravity.

Example geocentric model with lunar gravity:

```json
{
  "id": "earth_fm",
  "name": "EarthFM",
  "central_body": "Earth",
  "gravity": {
    "type": "point_mass"
  },
  "third_body_gravity": {
    "enabled": true,
    "bodies": ["Luna"]
  }
}
```

Earth is the default central body if omitted, but explicit `central_body` is preferred.

### Third-body gravity presets

```json
{
  "third_body_gravity": {
    "enabled": true,
    "preset": "all_major_bodies"
  }
}
```

Common presets:

```text
none, earth_near_space, inner_solar_system, all_major_bodies, custom
```

### Spherical harmonic gravity

```json
{
  "gravity": {
    "type": "spherical_harmonic",
    "degree": 4,
    "order": 4,
    "potential_file": "JGM2.cof"
  }
}
```

The current MVP is conservative: keep degree/order low until runtime behavior is confirmed.

## Propagators

A propagator selects a force model and integrator settings.

```json
{
  "id": "earth_prop",
  "name": "EarthProp",
  "force_model": "earth_fm",
  "integrator": "RungeKutta89",
  "accuracy": 1e-12,
  "initial_step_s": 10,
  "min_step_s": 0.001,
  "max_step_s": 300
}
```

## Burns

AMAT currently supports impulsive burns.

```json
{
  "id": "raise_apogee_to_500km",
  "name": "RaiseApogeeTo500km",
  "type": "impulsive",
  "frame": "VNB",
  "origin": "Earth",
  "delta_v_km_s": [0.056781639, 0.0, 0.0]
}
```

The spacecraft that receives the burn is chosen in the mission-sequence maneuver step.

## Outputs

Outputs are full-run products or viewer artifacts.

### Full spacecraft ephemeris

Full ephemeris files must start with `_Ephemeris`.

```json
{
  "id": "event_test_spacecraft_ephemeris",
  "type": "full_ephemeris",
  "enabled": true,
  "spacecraft": "sat",
  "frames": ["EarthMJ2000Eq"],
  "parameters": [
    "UTCGregorian",
    "ElapsedSecs",
    "A1ModJulian",
    "EarthMJ2000Eq.X",
    "EarthMJ2000Eq.Y",
    "EarthMJ2000Eq.Z",
    "EarthMJ2000Eq.VX",
    "EarthMJ2000Eq.VY",
    "EarthMJ2000Eq.VZ"
  ],
  "path_template": "outputs/_Ephemeris_{spacecraft}_{frame}.csv",
  "include_header": true
}
```

The compiler expands unqualified parameters relative to the selected spacecraft. For example, `EarthMJ2000Eq.X` becomes `EventSat.EarthMJ2000Eq.X` in GMAT.

### Body ephemeris

Body ephemeris files are for visualization of major body locations.

```json
{
  "id": "luna_body_ephemeris",
  "type": "body_ephemeris",
  "enabled": true,
  "body": "Luna",
  "frame": "EarthMJ2000Eq",
  "source": "spice",
  "dependency_id": "dep_luna_spice",
  "path": "outputs/_BodyEphemeris_Luna_EarthMJ2000Eq.csv",
  "include_radius_km": true
}
```

If resolved SPICE JSON exists, AMAT exports a SPICE-derived CSV. If not, the generated GMAT script may attempt a GMAT ReportFile fallback for the body ephemeris.

### Final state

```json
{
  "type": "final_state",
  "spacecraft": "sat"
}
```

This is metadata-oriented in the current MVP. Use checkpoints for reliable state snapshots.

## Checkpoints

Checkpoints are sparse one-row state snapshots, not full trajectories.

```json
{
  "id": "initial_state",
  "enabled": true,
  "spacecraft": "sat",
  "path": "outputs/initial_state.csv",
  "parameters": [
    "UTCGregorian",
    "ElapsedSecs",
    "A1ModJulian",
    "EarthMJ2000Eq.X",
    "EarthMJ2000Eq.Y",
    "EarthMJ2000Eq.Z",
    "EarthMJ2000Eq.VX",
    "EarthMJ2000Eq.VY",
    "EarthMJ2000Eq.VZ"
  ],
  "include_header": true
}
```

Checkpoint files should not start with `_Ephemeris`.

Checkpoint files should include at least one timestamp column. Recommended timestamp columns:

```text
UTCGregorian, ElapsedSecs, A1ModJulian
```

## Events

Events stop propagation and then execute ordered actions.

### Parameter reaches

```json
{
  "id": "event_ta_270",
  "type": "parameter_reaches",
  "spacecraft": "sat",
  "propagator": "earth_prop",
  "stop_condition": {
    "parameter": "EventSat.Earth.TA",
    "value": 270,
    "unit": "deg"
  },
  "actions": [
    {
      "action_id": "checkpoint_final_ta_270",
      "type": "checkpoint",
      "checkpoint_id": "final_ta_270"
    }
  ]
}
```

### Orbital events

```json
{
  "id": "event_apogee",
  "type": "orbital_event",
  "event": "apoapsis",
  "spacecraft": "sat",
  "propagator": "earth_prop",
  "central_body": "Earth",
  "actions": [
    {
      "action_id": "checkpoint_at_apogee",
      "type": "checkpoint",
      "checkpoint_id": "at_apogee"
    }
  ]
}
```

Supported event aliases:

```text
periapsis, apoapsis
```

The current compiler maps these to true-anomaly stop conditions for GMAT. Apoapsis is not valid for hyperbolic trajectories.

### Node crossing

```json
{
  "id": "node_event",
  "type": "node_crossing",
  "node": "either",
  "spacecraft": "sat",
  "propagator": "earth_prop",
  "reference_frame": "EarthMJ2000Eq",
  "actions": []
}
```

Supported node values:

```text
ascending, descending, either, both
```

Direction-specific enforcement is limited in the current GMAT script backend. Use checkpoint `VZ` to inspect crossing direction when needed.

### Event actions

Each action requires `action_id`.

```json
{
  "action_id": "burn_at_event",
  "type": "maneuver",
  "spacecraft": "sat",
  "burn": "my_burn"
}
```

Supported action types:

```text
checkpoint, maneuver, report, custom_gmat
```

## Mission sequence

The mission sequence is top-level and phase-based. Each phase contains ordered steps.

```json
{
  "mission_sequence": [
    {
      "phase_id": "phase_001_initial",
      "name": "Initial state",
      "steps": [
        {
          "step_id": "checkpoint_initial_state",
          "type": "checkpoint",
          "checkpoint_id": "initial_state"
        }
      ]
    },
    {
      "phase_id": "phase_002_coast",
      "name": "Coast one orbit",
      "steps": [
        {
          "step_id": "propagate_one_orbit",
          "type": "propagate",
          "spacecraft": "sat",
          "propagator": "earth_prop",
          "duration_s": 5431.1762752061
        }
      ]
    }
  ]
}
```

Supported step types:

### Propagate

```json
{
  "step_id": "coast_001",
  "type": "propagate",
  "spacecraft": "sat",
  "propagator": "earth_prop",
  "duration_s": 3600
}
```

### Maneuver

```json
{
  "step_id": "burn_001",
  "type": "maneuver",
  "spacecraft": "sat",
  "burn": "raise_apogee_to_500km"
}
```

### Checkpoint

```json
{
  "step_id": "checkpoint_001",
  "type": "checkpoint",
  "checkpoint_id": "initial_state"
}
```

### Event action

```json
{
  "step_id": "event_action_ta_270",
  "type": "event_action",
  "event_id": "event_ta_270"
}
```

## External dependencies and SPICE

SPICE dependencies are declared in `external_dependencies[]`.

```json
{
  "id": "dep_luna_spice",
  "type": "spice_ephemeris",
  "provider": "spice",
  "purpose": "viewer_body_ephemeris",
  "kernels": {
    "metakernel_path": "kernels/mission.tm",
    "kernel_paths": [
      "kernels/de440.bsp",
      "kernels/naif0012.tls",
      "kernels/pck00010.tpc"
    ],
    "required_kernel_types": ["SPK", "LSK", "PCK"]
  },
  "target": {
    "name": "Luna",
    "naif_id": 301
  },
  "observer": {
    "name": "Earth",
    "naif_id": 399
  },
  "time_range": {
    "start": "2026-06-01T00:00:00Z",
    "stop": "2026-06-02T00:00:00Z",
    "step_s": 60,
    "input_time_scale": "UTC",
    "output_time_scale": "TDB"
  },
  "frame": "J2000",
  "aberration_correction": "NONE",
  "output": {
    "path": "dependencies/resolved/dep_luna_spice_ephemeris.json",
    "format": "normalized_json"
  }
}
```

Commands:

```bash
python -m mission_compiler spice-requests examples/event_test/mission_spec.json --out generated/event_test
python -m mission_compiler resolve-spice generated/event_test/dependencies/spice_requests.json --request-id dep_luna_spice --out generated/event_test/dependencies/resolved/dep_luna_spice_ephemeris.json
python -m mission_compiler export-visualization generated/event_test
```

## Visualization manifest

AMAT writes:

```text
generated/<mission_id>/visualization_manifest.json
```

The manifest summarizes:

- `spacecraft_ephemerides`
- `body_ephemerides`
- `checkpoints`
- `frames`
- `sources`
- `assumptions`
- `viewer_warnings`

The viewer should load `_Ephemeris*.csv` as spacecraft trajectories and `_BodyEphemeris*.csv` as body trajectories.

## Complete event-test pattern

A common event-test mission has this shape:

```text
1. Start in circular LEO.
2. Record initial checkpoint.
3. Propagate one orbit to the next ascending node.
4. Burn prograde to raise apogee.
5. Propagate to apoapsis event.
6. Burn prograde to raise perigee.
7. Propagate until TA = 270 deg.
8. Export spacecraft ephemeris and checkpoint snapshots.
9. Export Luna body ephemeris if requested.
```

Use `examples/event_test/mission_spec.json` as the reference implementation.

## Common problems

### SPICE output missing

Read the printed `visualization_export` block. If it says SPICE resolution failed, either install/verify `spiceypy` and kernels or rely on GMAT body ephemeris fallback if available.

### GMAT rejects the script

If `LoadScript returned: False`, inspect `generated_mission.script` and GMAT's message/log output. Common causes are unsupported frame axes, unsupported body-state report parameters, or missing custom body definitions.

### Body ephemeris source is not SPICE

If SPICE resolved JSON is missing, AMAT may use `gmat_reportfile_fallback`. The manifest will label the source so the viewer can display provenance.

## Current limitations

AMAT does not yet provide:

- Automated TLI/free-return targeting.
- Lambert targeting.
- Optimizers and differential correctors as schema-level tools.
- Full SOI switching/detection.
- Finite burn modeling.
- Estimation/covariance workflows.
- Guaranteed visualization transforms for every custom GMAT frame.

These are intended future layers on top of the current MissionSpec/artifact foundation.

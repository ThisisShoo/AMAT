# AMAT MissionSpec Reference

This document explains how to manually write `mission_spec.json` files for the AMAT simulation layer.

AMAT is designed for users who may not know a backend's native scripting language. Describe the mission in JSON, and AMAT validates the intent, generates backend artifacts, runs the selected simulation backend, and writes viewer-ready output files. GMAT is the primary simulation backend. Orekit is available as an initial two-body backend. MissionSpec should be written as backend-neutral mission intent wherever possible.

## Core idea

A MissionSpec is the source of truth for a mission. Normal operation is controlled by editing `mission_spec.json`. Terminal commands are only for compiling, running, and troubleshooting.

## Minimal top-level structure

```json
{
  "schema_version": "1.0.0",
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
| `schema_version` | Yes | Schema version. Use `1.0.0`. |
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
| `burns` | No | Reusable impulsive or finite burn definitions. |
| `outputs` | No | Full ephemeris, body ephemeris, and final-state requests. |
| `checkpoints` | No | Sparse state snapshots written at mission-sequence locations. |
| `events` | No | Event definitions that stop propagation and trigger actions. |
| `mission_sequence` | Yes | Ordered phase/step mission timeline. |
| `external_dependencies` | No | SPICE ephemeris and other external data declarations. |

## Naming rules

IDs such as `mission_id`, spacecraft `id`, propagator `id`, and checkpoint `id` should use letters, numbers, `_`, or `-`.

Backend object names such as spacecraft `name`, force model `name`, propagator `name`, and burn `name` should start with a letter and then use letters, numbers, or `_` only. This keeps generated GMAT artifacts valid and is also a good portable convention for future backends.

Good:

```text
Sat
EarthFM
RaiseApogeeTo500km
spacecraft_ephemeris
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

Generated backend artifacts and viewer CSVs assume these conventions unless a backend-specific adapter explicitly documents otherwise.

## Backend Capability Matrix

MissionSpec is backend-neutral, but each backend supports a different subset today.

| Capability | GMAT backend | Orekit backend |
|---|---|---|
| Initial spacecraft states | Cartesian and Keplerian | Cartesian and Keplerian |
| Built-in central bodies | GMAT built-ins and configured bodies | Sun, Mercury, Venus, Earth, Luna/Moon, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto |
| Propagation model | GMAT propagation with configured force model | Two-body point-mass propagation through Orekit `KeplerianPropagator` |
| Point-mass central gravity | Yes | Yes |
| Spherical-harmonic gravity | Declared and emitted for GMAT | Not supported |
| Third-body gravity | Declared and emitted for GMAT | Not supported |
| Finite burns | Supported by MissionSpec and GMAT compiler | Not supported |
| Impulsive burns | Supported | Supported only in `VNB` |
| Direct maneuver steps | Supported | Supported for impulsive `VNB` burns |
| Event actions | Supported | Limited support |
| Supported Orekit events | N/A | elapsed seconds, `Earth.ArgumentOfLatitude`, apoapsis |
| Spacecraft ephemeris CSV | Supported | Supported for supported inertial frames |
| Checkpoint CSV | Supported | Supported |
| Final-state CSV | Supported as output intent | Supported |
| Keplerian output for target evaluation | Supported | Supported in generated Orekit CSV columns |
| Body ephemeris output | Supported when GMAT report parameters or SPICE fallback are available | Not supported |
| Ground-track CSV | Supported by GMAT-backed reports | Not generated |
| Body-fixed output frames | Supported when backend outputs them | Not supported |
| Targeter closed-loop STM artifact | GMAT can emit configured STM artifacts | Orekit adapter can synthesize finite-difference STM assessments from perturbation runs |
| Visualization | Uses backend outputs and manifests | Uses Orekit spacecraft ephemeris/checkpoint/final-state outputs; body ephemerides and ground tracks must come from another source |

Orekit's current supported frames are:

```text
EarthMJ2000Eq, MJ2000Eq, EME2000, LunaMJ2000Eq, MoonMJ2000Eq
```

Orekit skips unsupported spacecraft ephemeris output frames with a compiler warning. It rejects unsupported spacecraft initial frames, non-impulsive burns, non-`VNB` burns, unsupported force models, and unsupported event types.

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
- `clean_csv`: removes backend report spacer columns where possible. This is most visible for GMAT ReportFile output.
- `write_manifest`: writes `visualization_manifest.json`.
- `include_spice_body_ephemerides`: exports resolved SPICE body ephemerides when available. SPICE is used as a fallback body-ephemeris source when the simulation backend cannot or does not provide the requested body states.

## Bodies

Bodies are optional for backend built-ins, but declaring them improves portability and viewer metadata.

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

For custom or fictitious bodies, AMAT preserves the declaration for backend adapters and visualization metadata. A backend may still require its own external body configuration before it can propagate with that body.

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

Common frame families used by AMAT examples and visualization:

| Family | Examples | Notes |
|---|---|---|
| Body-centered equatorial inertial | `EarthMJ2000Eq`, `LunaMJ2000Eq`, `MarsMJ2000Eq`, `SunMJ2000Eq` | Most common trajectory output frame. |
| Body-centered ecliptic inertial | `EarthMJ2000Ec`, `LunaMJ2000Ec`, `MarsMJ2000Ec`, `SunMJ2000Ec` | Useful for solar-system style views when supported by the backend. |
| Body-fixed / surface-fixed | `EarthFixed`, `LunaFixed` | Useful for ground tracks and surface-relative 3D views. |
| Two-body rotating or object-referenced | `EarthLunaRotating`, `LunaEarthRotating` | Useful for cislunar inspection when the backend outputs ephemerides directly in the rotating frame. |
| Local maneuver frames | `VNB`, `LVLH`, `SpacecraftBody` | Used by burn definitions rather than full trajectory outputs. |

Notes:

- For AMAT's current object-referenced naming convention, the first body in the frame name is the origin/center. `EarthLunaRotating` is Earth-centered with `primary: "Earth"` and `secondary: "Luna"`. `LunaEarthRotating` is Luna-centered with `primary: "Luna"` and `secondary: "Earth"`.
- Object-referenced frames should be declared explicitly in `reference_frames[]`. The visualizer reads `origin`, `primary`, `secondary`, `axes`, `x_axis`, and `z_axis` from this declaration through `visualization_manifest.json`.
- A typical cislunar rotating frame uses `type: "object_referenced"`, `axes: "ObjectReferenced"`, `x_axis: "R"`, and `z_axis: "N"`. For GMAT, mirror those fields under `backend_overrides.gmat`.

Example object-referenced frame:

```json
{
  "id": "earth_luna_rotating",
  "name": "EarthLunaRotating",
  "type": "object_referenced",
  "origin": "Earth",
  "primary": "Earth",
  "secondary": "Luna",
  "orientation": "ObjectReferenced",
  "axes": "ObjectReferenced",
  "x_axis": "R",
  "z_axis": "N",
  "backend_overrides": {
    "gmat": {
      "name": "EarthLunaRotating",
      "create_coordinate_system": true,
      "origin": "Earth",
      "primary": "Earth",
      "secondary": "Luna",
      "axes": "ObjectReferenced",
      "x_axis": "R",
      "z_axis": "N"
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

Specialized frames may require extra backend fields. Put GMAT-specific fields under `backend_overrides.gmat` so AMAT preserves and emits them for the GMAT backend. Future backend adapters should use their own key under `backend_overrides`.

### Visualizer frame contract

The visualizer can load, label, and filter any frame that appears in `visualization_manifest.json`, generated outputs, or a parsed backend script. It does not currently perform general frame transformations. If you want to inspect a trajectory in a frame, the simulation backend must output spacecraft/body ephemeris CSVs already expressed in that frame.

For reliable visualization:

- Output spacecraft ephemeris in every frame you want the viewer to show.
- Output body ephemerides in the same frame when body locations matter for context.
- Declare `origin`, `axes`, `primary`, and `secondary` for custom or rotating frames when possible.
- Use body-fixed frames such as `EarthFixed` for surface-fixed 3D views and ground-track overlays.
- Do not expect the viewer to derive `EarthFixed` from `EarthMJ2000Eq`, or `EarthLunaRotating` from inertial data, unless a future transform layer is added.

## Spacecraft

Each spacecraft needs an ID, backend object name, epoch, frame, state, and mass.

### Keplerian state

```json
{
  "id": "sat",
  "name": "Sat",
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

Cartesian states are ordered as:

```text
position_km = [X, Y, Z]
velocity_km_s = [VX, VY, VZ]
```

Both vectors are expressed in the spacecraft `frame`. For example, if `frame` is `EarthMJ2000Eq`, then `position_km` and `velocity_km_s` are Earth-centered MJ2000 equatorial Cartesian components in kilometers and kilometers per second.

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

Orekit backend note: the current Orekit adapter supports only point-mass/two-body central gravity. It rejects spherical harmonics, third-body gravity, and custom central bodies without a built-in `GM` entry.

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

Keep degree/order low until runtime behavior is confirmed for the selected backend and mission duration.

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

Burn definitions describe reusable maneuver models. A mission-sequence maneuver step or event action chooses which spacecraft receives the burn and when it is executed.

The specifications of impulsive and finite burns are defined in `burns[]`. A maneuver step does not contain the burn vector or thrust model; it references a burn by ID.

### Impulsive burn

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

For an impulsive burn, `delta_v_km_s` is the burn vector in the burn `frame`, ordered as:

```text
delta_v_km_s = [Element1, Element2, Element3]
```

In a local `VNB` burn frame, this corresponds to velocity-axis, normal-axis, and binormal-axis components as interpreted by the backend.

Supported burn frame choices:

| Frame kind | Examples | Use |
|---|---|---|
| Local orbital frames | `VNB`, `LVLH` | Prograde/normal/radial style maneuvers tied to the spacecraft state. |
| Spacecraft body frame | `SpacecraftBody` | Body-axis thrust directions when attitude/body axes are meaningful to the backend. |
| Inertial body-centered frames | `EarthMJ2000Eq`, `EarthMJ2000Ec`, `LunaMJ2000Eq` | Fixed inertial direction burns. |
| Declared custom frames | Any frame in `reference_frames[]` that the backend can emit/use | Specialized object-referenced or mission-specific maneuver directions. |

For the GMAT backend, local frames are emitted as GMAT `Local` burn coordinate systems. Other frame names are emitted as backend coordinate systems, so they must be known to GMAT or declared in `reference_frames[]`.

Orekit backend note: the current Orekit adapter supports impulsive burns in `VNB` only. `delta_v_km_s` is interpreted as velocity-axis, normal-axis, binormal-axis components and applied instantaneously to the current state.

### Finite burn

Finite burns are available in MissionSpec. In the GMAT backend, they compile to `ChemicalTank`, `ChemicalThruster`, and `FiniteBurn` resources. The Orekit backend does not support finite burns yet.

```json
{
  "id": "finite_raise_apogee",
  "name": "FiniteRaiseApogee",
  "type": "finite",
  "frame": "VNB",
  "origin": "Earth",
  "thrust_N": 490.3325,
  "isp_s": 320.0,
  "direction": [1.0, 0.0, 0.0],
  "decrement_mass": false,
  "duty_cycle": 1.0,
  "fuel_mass_kg": 1000.0
}
```

For a finite burn, `direction` is a unit-like thrust direction vector in the burn `frame`, ordered as:

```text
direction = [Direction1, Direction2, Direction3]
```

AMAT normalizes this vector before backend emission. The maneuver step or event action that invokes a finite burn must include both `propagator` and `duration_s`, because the burn is applied while propagating.

## Outputs

Outputs are full-run products or viewer artifacts.

### Full spacecraft ephemeris

Full ephemeris files must start with `_Ephemeris` so the visualizer can discover them.

```json
{
  "id": "spacecraft_ephemeris",
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

The compiler expands unqualified parameters relative to the selected spacecraft. For example, if the output's spacecraft has `"name": "Sat"`, then `EarthMJ2000Eq.X` becomes a backend-specific spacecraft state parameter for `Sat` in the GMAT backend.

Common spacecraft ephemeris presets can be requested through `state_groups` instead of writing every column manually:

```json
{
  "id": "eci_and_fixed_ephemeris",
  "type": "spacecraft_ephemeris",
  "spacecraft": "sat",
  "frames": ["EarthMJ2000Eq", "EarthFixed"],
  "state_groups": ["elapsed_time", "cartesian", "keplerian"],
  "path_template": "outputs/_Ephemeris_{spacecraft}_{frame}.csv"
}
```

Recommended frame/output combinations:

| Need | Frames | State groups |
|---|---|---|
| Earth-centered inertial trajectory | `["EarthMJ2000Eq"]` or `["EarthMJ2000Ec"]` | `["elapsed_time", "cartesian", "keplerian"]` |
| Luna-centered inertial trajectory | `["LunaMJ2000Eq"]` or `["LunaMJ2000Ec"]` | `["elapsed_time", "cartesian", "keplerian"]` |
| Body-centered inertial trajectory | `["<Body>MJ2000Eq"]` or `["<Body>MJ2000Ec"]` | `["elapsed_time", "cartesian"]`, plus `keplerian` when the backend supports element reports for that body |
| Surface-fixed 3D view | `["EarthFixed"]` or another body-fixed frame | `["elapsed_time", "cartesian"]` |
| Orbit-element assessment | Any supported inertial frame | `["elapsed_time", "keplerian"]` |

For GMAT, Keplerian output has a backend quirk: `SMA`, `ECC`, and `TA` are origin-qualified, while `INC`, `RAAN`, and `AOP` are coordinate-system-qualified. AMAT handles this mapping when you use `state_groups`.

Orekit output note: the Orekit runner writes Cartesian columns and Keplerian columns for supported spacecraft ephemeris, checkpoints, and final-state outputs. The Keplerian columns follow the same evaluator-friendly convention: `SMA`, `ECC`, and `TA` are central-body qualified, while `INC`, `RAAN`, and `AOP` are frame qualified.

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

If the simulation backend provides the requested body ephemeris, AMAT uses that backend-resolved output so visualization stays aligned with propagation. If the backend cannot provide it, resolved SPICE data is the fallback source. The manifest records the selected source so the viewer can display provenance.

Orekit backend note: AMAT's current Orekit runner does not generate body ephemeris outputs. Use backend-independent SPICE resolution or another simulation backend when body ephemerides are needed for visualization context.

### Final state

```json
{
  "type": "final_state",
  "spacecraft": "sat"
}
```

`final_state` is a declarative output request: it records that the mission wants a final state product for a spacecraft. It is useful as backend-neutral intent, target evaluation input, and summary/report generation. The Orekit backend writes this product directly; other backends may satisfy it through their native report mechanisms.

In the current pipeline, use an explicit checkpoint at the final mission-sequence location when you need a reliable final state CSV for evaluation, targeting acceptance, or visualization.

## Checkpoints

Checkpoints are sparse one-row state snapshots instead of full trajectories.

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

Checkpoint files should not start with `_Ephemeris`. That prefix is reserved for full spacecraft trajectories, and using it for checkpoints will confuse visualizer discovery.

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
    "parameter": "Sat.Earth.TA",
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

### Event aliases

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

Supported event aliases and event types:

```text
periapsis, apoapsis, node_crossing
```

`periapsis` and `apoapsis` use `"type": "orbital_event"` with `"event": "periapsis"` or `"event": "apoapsis"`. The GMAT backend maps these to true-anomaly stop conditions. Apoapsis is not valid for hyperbolic trajectories.

For orbital-plane crossings, use `"type": "node_crossing"`. This is a clearer name than treating nodes as generic orbital events because the event is defined by crossing a reference plane:

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

Direction-specific enforcement is limited in the GMAT backend. Use checkpoint `VZ` to inspect crossing direction when needed.

Orekit backend event support is intentionally narrow today:

| Event form | Orekit status |
|---|---|
| `parameter_reaches` with `ElapsedSecs` | Supported |
| `parameter_reaches` with `Earth.ArgumentOfLatitude` | Supported |
| `orbital_event` with `event: "apoapsis"` | Supported |
| `periapsis` | Not supported by the Orekit adapter yet |
| true-anomaly parameter events | Not supported by the Orekit adapter yet |
| node-crossing events | Not supported by the Orekit adapter yet |
| direction-filtered crossings | Not supported by the Orekit adapter yet |

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

For finite-burn event actions, include `propagator` and `duration_s`:

```json
{
  "action_id": "finite_burn_at_event",
  "type": "maneuver",
  "spacecraft": "sat",
  "burn": "finite_raise_apogee",
  "propagator": "earth_prop",
  "duration_s": 745.0
}
```

Supported action types:

```text
checkpoint, maneuver, report, custom_gmat
```

`custom_gmat` is backend-specific. Keep it out of backend-neutral examples unless the mission is intentionally GMAT-only.

`custom_gmat` inserts raw GMAT script commands at that event-action location. It is an escape hatch for backend features that AMAT does not model yet. AMAT does not deeply validate the commands, does not translate them to other backends, and cannot guarantee visualization/evaluation metadata for side effects they create. Prefer normal `propagate`, `maneuver`, `checkpoint`, and `report` actions whenever possible.

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

A maneuver step invokes a burn definition from `burns[]`; the burn vector or thrust model lives in the burn definition, not in the step. The step supplies:

- `spacecraft`: the spacecraft receiving the burn.
- `burn`: the burn definition ID to execute.
- `propagator` and `duration_s`: required only for finite burns.

Orekit backend note: direct maneuver steps are supported for impulsive `VNB` burns. This is what allows targeter-generated in-plane phasing sequences to run as burn, coast, restore-burn timelines. Finite-burn maneuver steps are not supported by Orekit yet.

Impulsive example:

```json
{
  "step_id": "impulsive_burn_001",
  "type": "maneuver",
  "spacecraft": "sat",
  "burn": "raise_apogee_to_500km"
}
```

Finite-burn example:

```json
{
  "step_id": "finite_burn_001",
  "type": "maneuver",
  "spacecraft": "sat",
  "burn": "finite_raise_apogee",
  "propagator": "earth_prop",
  "duration_s": 745.0
}
```

If you only want to record state without applying a maneuver, use a `checkpoint` step instead.

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

Use this when the simulation backend cannot provide a requested body ephemeris, or when you explicitly want a SPICE-derived visualization/reference product. For GMAT-backed propagation, backend-reported body ephemerides are preferred when available because they reflect GMAT's resolved ephemeris and frame handling. SPICE is the fallback or external reference path.

Commands:

```bash
python -m compiler spice-requests examples/cislunar_demo/mission_spec.json --out generated/cislunar_demo/simulation
python -m compiler resolve-spice generated/cislunar_demo/simulation/dependencies/spice_requests.json --request-id dep_luna_spice --out generated/cislunar_demo/simulation/dependencies/resolved/dep_luna_spice_ephemeris.json
python -m compiler export-visualization generated/cislunar_demo/simulation
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

Visualizer-facing restrictions:

- Spacecraft trajectory files must use the `_Ephemeris` prefix.
- Body trajectory files must use the `_BodyEphemeris` prefix.
- Ground-track files should use the `_GroundTrack` prefix.
- Checkpoints must not use `_Ephemeris` or `_BodyEphemeris` prefixes.
- Files should include a usable time column, preferably `ElapsedSecs`; `UTCGregorian` is also useful for labels and reports.
- The viewer does not transform between arbitrary frames. That should be done upstream in the simulation step, or through a separate frame converter.
- For a moving body to appear in a frame, provide a matching `body_ephemeris` output in that same frame, for example `{"type": "body_ephemeris", "body": "Luna", "frame": "EarthMJ2000Eq", "path": "outputs/_BodyEphemeris_Luna_EarthMJ2000Eq.csv"}`.
- For a static context body in a frame, declare frame metadata in `reference_frames[]`; AMAT copies it into `visualization_manifest.json`. At minimum, provide `name`, `origin`, and `axes`. For two-body rotating context, also provide `primary` and `secondary`. The viewer can place the origin at the scene center and place a secondary body as context, but this is not a substitute for a time-varying body ephemeris.

## Complete Mission Pattern

A common mission pattern has this shape:

```text
1. Define spacecraft, force models, propagators, burns, outputs, checkpoints, and events.
2. Record an initial checkpoint if the starting state should be auditable.
3. Propagate by elapsed time or to an event.
4. Execute impulsive or finite maneuvers by referencing burn definitions.
5. Record checkpoints after important events or maneuvers.
6. Continue propagation to the final analysis point.
7. Record a final checkpoint for evaluation/targeting acceptance.
8. Export spacecraft ephemerides in every frame the viewer should show.
9. Export body ephemerides or ground tracks when the viewer needs body context or surface-relative motion.
```

Use `examples/LEO_to_GEO/mission_spec.json` and `examples/MEO_demo/mission_spec.json` as current reference implementations for impulsive/event-driven and finite-burn patterns.

## Common problems

### SPICE output missing

Read the printed `visualization_export` block. If it says SPICE resolution failed, either install/verify `spiceypy` and kernels or rely on backend-provided body ephemerides when available.

### Backend rejects the generated artifact

For GMAT, if `LoadScript returned: False`, inspect `generated_mission.script` and GMAT's message/log output. Common causes are unsupported frame axes, unsupported body-state report parameters, or missing custom body definitions. Other backends should expose equivalent compile/run diagnostics through `compile_result.json` and the generated runner output.

### Body ephemeris source is not what you expected

AMAT prefers body ephemerides resolved by the active simulation backend when they are available. If they are missing, AMAT may use a SPICE-derived fallback when resolved SPICE data exists. The manifest labels the source so the viewer can display provenance.

## Current limitations

AMAT does not yet provide:

- General low-thrust or finite-burn targeting. Finite burns can be simulated with GMAT when manually specified, but the analytic targeter still seeds impulsive maneuvers. Orekit finite burns are not supported yet.
- Automated TLI/free-return targeting as a complete mission-design workflow.
- General optimizer workflows as MissionSpec-native tools.
- Full SOI switching/detection in MissionSpec execution.
- Estimation/covariance workflows.
- General visualization transforms between arbitrary frames.
- Guaranteed visualization semantics for every backend-specific custom frame.
- Direction-filtered node crossing enforcement in every backend.
- Production-grade Orekit coverage. The current Orekit backend is an initial two-body backend with limited frames, limited events, impulsive `VNB` burns, and finite-difference STM assessment support for targeting.

These are intended future layers on top of the current MissionSpec/artifact foundation.


# AMAT MissionSpec Reference

This document explains how to manually write `mission_spec.json` files for the AMAT simulation layer.

AMAT is designed for users who may not know a backend's native scripting language. Describe the mission in JSON, and AMAT validates the intent, generates backend artifacts, runs the selected simulation backend, and writes viewer-ready output files. GMAT is the primary simulation backend. Orekit is available as a swappable simulation backend for supported MissionSpec features. MissionSpec should be written as backend-neutral mission intent wherever possible.

## Core idea

A MissionSpec is the source of truth for a mission. Normal operation is controlled by editing `mission_spec.json`. Terminal commands are only for compiling, running, and troubleshooting.

MissionSpec `schema_version: "2.0.0"` is the public user-authored contract. During compilation, AMAT also writes `mission_spec.backend_ir.json`; that file is a lowered internal backend contract with its own schema version and should not be hand-authored.

## Minimal top-level structure

```json
{
  "schema_version": "2.0.0",
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
    "write_manifest": true,
    "data_prerequisites": {
      "spacecraft_ephemerides": true,
      "checkpoints": true,
      "ground_tracks": true
    }
  },
  "bodies": [],
  "reference_frames": [],
  "spacecraft": [],
  "force_models": [],
  "propagators": [],
  "maneuvers": [],
  "outputs": [],
  "checkpoints": [],
  "event_detectors": [],
  "mission_sequence": [],
  "external_dependencies": []
}
```

## Top-level field summary

| Field | Required | Purpose |
|---|---:|---|
| `schema_version` | Yes | Schema version. Use `2.0.0`. |
| `mission_id` | Yes | Stable artifact ID. Used in generated paths and manifests. |
| `mission_name` | Yes | Human-readable mission name. |
| `description` | No | Mission summary. |
| `conventions` | Yes | Global time and unit conventions. |
| `visualization` | No | Requests compiler-produced visualization prerequisites. Rendered visualization outputs are produced by the visualization layer. |
| `bodies` | No | Declares celestial bodies, including custom/fictitious bodies. |
| `reference_frame_sets` | No | Pulls reusable frame presets from catalog. |
| `reference_frames` | No | Explicit coordinate-system/frame definitions. |
| `spacecraft` | Yes | Spacecraft definitions and initial states. |
| `force_models` | Yes | Gravity and force environments. |
| `propagators` | Yes | Integrator and force-model selection. |
| `maneuvers` | No | Reusable impulsive or finite maneuver definitions. |
| `outputs` | No | Full ephemeris, body ephemeris, and final-state requests. |
| `checkpoints` | No | Sparse state snapshots written at mission-sequence locations. |
| `event_detectors` | No | Event definitions that stop propagation and trigger actions. |
| `mission_sequence` | Yes | Ordered phase/step mission timeline. |
| `external_dependencies` | No | SPICE ephemeris and other external data declarations. |

## Naming rules

IDs such as `mission_id`, spacecraft `id`, propagator `id`, and checkpoint `id` should use letters, numbers, `_`, or `-`.

Backend object names such as spacecraft `name`, force model `name`, propagator `name`, and maneuver `name` should start with a letter and then use letters, numbers, or `_` only. This keeps generated GMAT artifacts valid and is also a good portable convention for future backends.

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

MissionSpec is backend-neutral, but each backend supports a different subset. Both GMAT and Orekit support Cartesian/Keplerian initial spacecraft states, point-mass central gravity, checkpoint CSVs, and final-state output intent.

| Capability | GMAT backend | Orekit backend |
|---|---|---|
| Built-in central bodies | GMAT built-ins and configured bodies | Sun, Mercury, Venus, Earth, Luna/Moon, Mars, Jupiter, Saturn, Uranus, Neptune, Pluto |
| Propagation model | GMAT propagation with configured force model | Two-body `KeplerianPropagator` or numerical propagation for supported gravity models |
| Spherical-harmonic gravity | Declared and emitted for GMAT | Supported when local Orekit data provide the gravity model |
| Third-body gravity | Declared and emitted for GMAT | Supported for Orekit built-in bodies when local Orekit data are available |
| Drag, SRP, relativity, tides | Backend-dependent force-model support | Supported through selected Orekit force-model hooks when required spacecraft properties and Orekit data are available |
| Finite maneuvers | Supported by MissionSpec and GMAT compiler | Supported as segmented thrust propagation, not full force-model coupling |
| Impulsive maneuvers | Supported | Supported in `VNB`, `LVLH`, `SpacecraftBody`, and supported inertial/fixed frames |
| Direct maneuver steps | Supported | Supported for impulsive and finite maneuvers |
| Event actions | Supported | Supported for date/elapsed time, anomaly, apsis, node, distance/SOI, elevation, and eclipse-style timing |
| Spacecraft ephemeris CSV | Supported | Supported for GMAT-style body-centered inertial/fixed frame names where Orekit or an adapter fallback can resolve them |
| Keplerian output for target evaluation | Supported | Supported in generated Orekit CSV columns |
| Body ephemeris output | Supported when GMAT report parameters or SPICE fallback are available | Supported for Orekit built-in celestial bodies, with SPICE fallback prerequisites generated for declared SPICE dependencies |
| Ground-track CSV | Supported by GMAT-backed reports | Supported from surface-fixed spacecraft states |
| Body-fixed output frames | Supported when backend outputs them | Supported for validated major-body fixed fallback frames; not general arbitrary transforms |
| Targeter closed-loop STM artifact | GMAT can emit configured STM artifacts | Orekit adapter can synthesize finite-difference STM assessments from perturbation runs |
| Visualization | Uses backend outputs and manifests | Uses Orekit spacecraft ephemeris, checkpoint, final-state, supported body-ephemeris, and ground-track outputs plus manifests |

Orekit accepts AMAT/GMAT-style body-centered frame names for supported major bodies:

```text
<Body>MJ2000Eq, <Body>MJ2000Ec, <Body>Fixed, <Body>TODEq, <Body>TODEc,
<Body>MODEq, <Body>MODEc, <Body>TOEEq, <Body>TOEEc, <Body>MOEEq,
<Body>MOEEc, <Body>BodyInertial, <Body>ICRF, <Body>Equator,
<Body>BodySpinSun, plus Earth GSE/GSM/TEME-style names where used as
adapter-level inertial labels.
```

The Orekit adapter maps these names into Orekit inertial frames or body-oriented fallback frames. It also supports topocentric station frames and local orbital maneuver frames where the adapter can resolve them. It is not a general arbitrary-frame transformation engine. Object-referenced/two-body rotating frames remain GMAT-authoritative.

## Visualization settings

Recommended default:

```json
{
  "visualization": {
    "enabled": true,
    "write_manifest": true,
    "data_prerequisites": {
      "spacecraft_ephemerides": true,
      "checkpoints": true,
      "ground_tracks": true
    }
  }
}
```

Behavior:

- `enabled`: asks the compiler/backend adapter to prepare visualization prerequisites.
- `write_manifest`: writes `visualization_manifest.json`.
- `data_prerequisites`: hints which data products the visualization layer should be able to consume. Rendered HTML and viewer reports are produced by `visualizer`, not by MissionSpec itself.

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
| Local maneuver frames | `VNB`, `LVLH`, `SpacecraftBody` | Used by maneuver definitions rather than full trajectory outputs. |

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

Each spacecraft needs an ID, backend object name, epoch, reference frame, orbit state, and mass.

### Keplerian state

```json
{
  "id": "sat",
  "name": "Sat",
  "epoch": "2026-06-01T00:00:00.000Z",
  "reference_frame": "EarthMJ2000Eq",
  "dry_mass": 500.0,
  "orbit_state": {
    "representation": "Keplerian",
    "position_angle_type": "True",
    "keplerian": {
      "semi_major_axis": 6678.1363,
      "eccentricity": 0.0,
      "inclination": 35.0,
      "right_ascension_of_ascending_node": 0.0,
      "argument_of_periapsis": 0.0,
      "anomaly": 0.0,
      "anomaly_type": "True"
    }
  }
}
```

Required Keplerian fields:

| Field | Unit | Meaning |
|---|---|---|
| `semi_major_axis` | km | Semi-major axis. |
| `eccentricity` | unitless | Eccentricity. |
| `inclination` | deg | Inclination. |
| `right_ascension_of_ascending_node` | deg | Right ascension of ascending node. |
| `argument_of_periapsis` | deg | Argument of periapsis. |
| `anomaly` | deg | True, mean, or eccentric anomaly according to `anomaly_type`. |

### Cartesian state

```json
{
  "id": "sat",
  "name": "Sat",
  "epoch": "2026-06-01T00:00:00.000Z",
  "reference_frame": "EarthMJ2000Eq",
  "dry_mass": 500.0,
  "orbit_state": {
    "representation": "Cartesian",
    "cartesian": {
      "position": [6678.1363, 0, 0],
      "velocity": [0, 7.7258, 0]
    }
  }
}
```

Cartesian states are ordered as:

```text
position = [X, Y, Z]
velocity = [VX, VY, VZ]
```

Both vectors are expressed in the spacecraft `reference_frame`. For example, if `reference_frame` is `EarthMJ2000Eq`, then `position` and `velocity` are Earth-centered MJ2000 equatorial Cartesian components in kilometers and kilometers per second.

## Force models

A force model describes central gravity and optional perturbing forces.

Example geocentric model with lunar gravity:

```json
{
  "id": "earth_fm",
  "name": "EarthFM",
  "central_body": "Earth",
  "gravity": {
    "model": "PointMass"
  },
  "third_body_gravity": {
    "enabled": true,
    "bodies": ["Luna"]
  }
}
```

Earth is the default central body if omitted, but explicit `central_body` is preferred.

Orekit backend note: the Orekit adapter supports point-mass/two-body central gravity and numerical propagation for declared spherical-harmonic gravity plus third-body/point-mass perturbing bodies when the local Orekit data set supplies the needed gravity and body data. It also has MissionSpec hooks for Harris-Priester drag, solar radiation pressure, relativity, solid tides, and ocean tides. These force terms require the matching spacecraft fields and Orekit data/runtime classes; otherwise the generated runner fails with an actionable runtime error. Orekit rejects custom central bodies without a built-in `GM` entry.

Common non-gravity force-model fields:

```json
{
  "drag": {
    "enabled": true,
    "atmosphere_model": "HarrisPriester"
  },
  "solar_radiation_pressure": {
    "enabled": true
  },
  "relativity": {
    "enabled": true
  },
  "solid_tides": {
    "enabled": true
  },
  "ocean_tides": {
    "enabled": true
  }
}
```

For drag, the spacecraft should define `dry_mass`, `drag_area`, and `drag_coefficient`. For solar radiation pressure, define `dry_mass`, `srp_area`, and `coefficient_of_reflectivity`.

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
    "model": "SphericalHarmonic",
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
  "initial_step": 10,
  "minimum_step": 0.001,
  "maximum_step": 300
}
```

These fields control propagation accuracy and backend integration behavior. They do not define the CSV row cadence. Use `outputs[].step` for the cadence of spacecraft ephemeris, ground-track, and body-ephemeris files.

Backend behavior:

- GMAT maps these fields to `InitialStepSize`, `MinStep`, `MaxStep`, and `Accuracy`.
- Orekit uses `maximum_step` as the propagation chunk limit and also samples more finely when an output requests a smaller `step`.

## Maneuvers

Maneuver definitions describe reusable impulsive or finite maneuver models. A mission-sequence maneuver step or event action chooses which spacecraft receives the maneuver and when it is executed.

The specifications of impulsive and finite maneuvers are defined in `maneuvers[]`. A mission-sequence step does not contain the maneuver vector or thrust model; it references a maneuver by ID.

### Impulsive maneuver

```json
{
  "id": "raise_apogee_to_500km",
  "name": "RaiseApogeeTo500km",
  "maneuver_type": "ImpulsiveBurn",
  "reference_frame": "VNB",
  "origin": "Earth",
  "delta_v": [0.056781639, 0.0, 0.0]
}
```

For an impulsive maneuver, `delta_v` is the maneuver vector in the maneuver `reference_frame`, ordered as:

```text
delta_v = [Element1, Element2, Element3]
```

In a local `VNB` maneuver frame, this corresponds to velocity-axis, normal-axis, and binormal-axis components as interpreted by the backend.

Supported maneuver frame choices:

| Frame kind | Examples | Use |
|---|---|---|
| Local orbital frames | `VNB`, `LVLH` | Prograde/normal/radial style maneuvers tied to the spacecraft state. |
| Spacecraft body frame | `SpacecraftBody` | Body-axis thrust directions when attitude/body axes are meaningful to the backend. |
| Inertial body-centered frames | `EarthMJ2000Eq`, `EarthMJ2000Ec`, `LunaMJ2000Eq` | Fixed inertial direction maneuvers. |
| Declared custom frames | Any frame in `reference_frames[]` that the backend can emit/use | Specialized object-referenced or mission-specific maneuver directions. |

For the GMAT backend, local frames are emitted as GMAT `Local` burn coordinate systems. Other frame names are emitted as backend coordinate systems, so they must be known to GMAT or declared in `reference_frames[]`.

Orekit backend note: the Orekit adapter supports impulsive maneuvers in `VNB`, `LVLH`, `SpacecraftBody`, and supported inertial/fixed frames. `VNB` components are velocity-axis, normal-axis, binormal-axis. `LVLH` components are radial, along-track, normal. Inertial/fixed-frame components are transformed into the propagation frame at the maneuver epoch.

### Finite maneuver

Finite maneuvers are available in MissionSpec. In the GMAT backend, they compile to `ChemicalTank`, `ChemicalThruster`, and `FiniteBurn` resources. In the Orekit backend, finite maneuvers execute as segmented thrust propagation in the requested maneuver frame. This supports mission sequencing and visualization, but it is not coupled to Orekit's full numerical force-model stack or propellant mass depletion.

```json
{
  "id": "finite_raise_apogee",
  "name": "FiniteRaiseApogee",
  "maneuver_type": "FiniteBurn",
  "reference_frame": "VNB",
  "origin": "Earth",
  "thrust": 490.3325,
  "specific_impulse": 320.0,
  "direction": [1.0, 0.0, 0.0],
  "decrement_mass": false,
  "duty_cycle": 1.0,
  "fuel_mass": 1000.0
}
```

For a finite maneuver, `direction` is a unit-like thrust direction vector in the maneuver `reference_frame`, ordered as:

```text
direction = [Direction1, Direction2, Direction3]
```

AMAT normalizes this vector before backend emission. The maneuver step or event action that invokes a finite maneuver must include both `propagator` and `duration`, because the maneuver is applied while propagating.

## Outputs

Outputs are full-run products or viewer artifacts.

### Full spacecraft ephemeris

Full spacecraft ephemeris files must use the `.eph.csv` extension so the visualizer can discover them as spacecraft trajectories.

```json
{
  "id": "spacecraft_ephemeris",
  "type": "FullEphemeris",
  "enabled": true,
  "spacecraft": "sat",
  "frames": ["EarthMJ2000Eq"],
  "step": 300,
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
  "path_template": "outputs/{spacecraft}_{frame}.eph.csv",
  "include_header": true
}
```

The compiler expands unqualified parameters relative to the selected spacecraft. For example, if the output's spacecraft has `"name": "Sat"`, then `EarthMJ2000Eq.X` becomes a backend-specific spacecraft state parameter for `Sat` in the GMAT backend.

Common spacecraft ephemeris presets can be requested through `state_groups` instead of writing every column manually:

```json
{
  "id": "eci_and_fixed_ephemeris",
  "type": "EphemerisFile",
  "spacecraft": "sat",
  "frames": ["EarthMJ2000Eq", "EarthFixed"],
  "step": 300,
  "state_groups": ["elapsed_time", "cartesian", "keplerian"],
  "path_template": "outputs/{spacecraft}_{frame}.eph.csv"
}
```

`step` is the human-facing output cadence in seconds. AMAT treats it as authoritative for ephemeris-style CSV files:

- GMAT runs normalize ReportFile CSVs and keep rows on the requested elapsed-time grid when the backend produced data at that cadence or finer.
- Orekit runs sample propagation densely enough for the smallest requested output cadence and write each output file on its own `step` grid.
- Surface-fixed spacecraft ephemeris outputs automatically generate matching ground-track CSVs using the same cadence.
- Checkpoints and final-state outputs ignore `step`; they are sparse mission-sequence products.

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
  "type": "BodyEphemeris",
  "enabled": true,
  "body": "Luna",
  "reference_frame": "EarthMJ2000Eq",
  "source": "spice",
  "dependency_id": "dep_luna_spice",
  "path": "outputs/Luna_EarthMJ2000Eq.body.eph.csv",
  "include_radius_km": true
}
```

If the simulation backend provides the requested body ephemeris, AMAT uses that backend-resolved output so visualization stays aligned with propagation. If the backend cannot provide it, resolved SPICE data is the fallback source. The manifest records the selected source so the viewer can display provenance.

Orekit backend note: AMAT's Orekit runner can generate body ephemeris outputs for Orekit built-in celestial bodies when the local Orekit data support the requested body and frame. Use backend-independent SPICE resolution when the body or frame is outside the Orekit adapter's supported set.

### Final state

```json
{
  "type": "FinalState",
  "spacecraft": "sat"
}
```

`final_state` is a declarative output request: it records that the mission wants a final state product for a spacecraft. It is useful as backend-neutral intent, target evaluation input, and summary/report generation. The Orekit backend writes this product directly; other backends may satisfy it through their native report mechanisms.

Use an explicit checkpoint at the final mission-sequence location when you need a reliable final state CSV for evaluation, targeting acceptance, or visualization.

## Checkpoints

Checkpoints are sparse one-row state snapshots instead of full trajectories.

Use `state_groups` for common spacecraft state products, or `parameters`/`fields` for explicit backend-style parameters.

```json
{
  "id": "initial_state",
  "enabled": true,
  "spacecraft": "sat",
  "reference_frame": "EarthMJ2000Eq",
  "path": "outputs/initial_state.csv",
  "state_groups": ["ElapsedTime", "Cartesian", "Keplerian"],
  "include_header": true
}
```

Equivalent explicit-parameter form:

```json
{
  "id": "initial_state",
  "enabled": true,
  "spacecraft": "sat",
  "reference_frame": "EarthMJ2000Eq",
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

Checkpoint files should not use `.eph.csv` or `.body.eph.csv`. Those extensions are reserved for dense spacecraft and body trajectories, and using them for checkpoints will confuse visualizer discovery.

Checkpoint files should include at least one timestamp column. Recommended timestamp columns:

```text
UTCGregorian, ElapsedSecs, A1ModJulian
```

## Event Detectors

Events stop propagation and then execute ordered actions.

### Parameter reaches

```json
{
  "id": "event_ta_270",
  "event_detector_type": "ParameterCondition",
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
      "command": "Checkpoint",
      "checkpoint_id": "final_ta_270"
    }
  ]
}
```

### Event aliases

```json
{
  "id": "event_apogee",
  "event_detector_type": "ApsideDetector",
  "event": "apoapsis",
  "spacecraft": "sat",
  "propagator": "earth_prop",
  "central_body": "Earth",
  "actions": [
    {
      "action_id": "checkpoint_at_apogee",
      "command": "Checkpoint",
      "checkpoint_id": "at_apogee"
    }
  ]
}
```

Supported event aliases and event types:

```text
periapsis, apoapsis, node_crossing
```

`periapsis` and `apoapsis` use `"event_detector_type": "ApsideDetector"` with `"event": "periapsis"` or `"event": "apoapsis"`. The GMAT backend maps these to true-anomaly stop conditions. Apoapsis is not valid for hyperbolic trajectories.

For orbital-plane crossings, use `"event_detector_type": "NodeDetector"`. This is clearer than treating nodes as generic orbital events because the event is defined by crossing a reference plane:

```json
{
  "id": "node_event",
  "event_detector_type": "NodeDetector",
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

Orekit backend event support is MissionSpec-oriented. Analytic anomaly and apsis/node shortcuts are available for bounded Keplerian timing, and general distance-style events use a deterministic scalar search over Orekit-propagated states:

| Event form | Orekit status |
|---|---|
| `ParameterCondition` with `ElapsedSecs` | Supported |
| `ParameterCondition` with `Earth.ArgumentOfLatitude` | Supported |
| `ApsideDetector` with `event: "apoapsis"` | Supported |
| `ApsideDetector` with `event: "periapsis"` | Supported |
| true-anomaly parameter events | Supported for bounded Keplerian two-body propagation |
| node-crossing events | Supported for bounded Keplerian two-body propagation in supported inertial frames |
| `DateDetector` / date events | Supported |
| `DistanceThresholdDetector` | Supported for Orekit built-in bodies |
| `SOICrossingDetector` | Supported as a body-distance threshold preset |
| `ElevationDetector` | Supported for topocentric station coordinates or station frames |
| `EclipseDetector` | Supported with Sun/body occultation geometry |
| `direction`, `terminal`, `max_check_s`, `threshold_s`, `max_iterations` | Accepted; `terminal` is naturally true for MissionSpec event-action steps |

### Event actions

Each action requires `action_id`.

```json
{
  "action_id": "maneuver_at_event",
  "command": "Maneuver",
  "spacecraft": "sat",
  "maneuver": "my_maneuver"
}
```

For finite-maneuver event actions, include `propagator` and `duration`:

```json
{
  "action_id": "finite_maneuver_at_event",
  "command": "Maneuver",
  "spacecraft": "sat",
  "maneuver": "finite_raise_apogee",
  "propagator": "earth_prop",
  "duration": 745.0
}
```

Supported action types:

```text
Checkpoint, Maneuver, Report, Custom
```

Raw GMAT custom actions are backend-specific. Keep them out of backend-neutral examples unless the mission is intentionally GMAT-only.

GMAT custom actions insert raw GMAT script commands at that event-action location. They are an escape hatch for backend features that AMAT does not model yet. AMAT does not deeply validate the commands, does not translate them to other backends, and cannot guarantee visualization/evaluation metadata for side effects they create. Prefer normal `Propagate`, `Maneuver`, `Checkpoint`, and `Report` actions whenever possible.

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
          "command": "Checkpoint",
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
          "command": "Propagate",
          "spacecraft": "sat",
          "propagator": "earth_prop",
          "duration": 5431.1762752061
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
  "command": "Propagate",
  "spacecraft": "sat",
  "propagator": "earth_prop",
  "duration": 3600
}
```

### Maneuver

```json
{
  "step_id": "burn_001",
  "command": "Maneuver",
  "spacecraft": "sat",
  "maneuver": "raise_apogee_to_500km"
}
```

A maneuver step invokes a maneuver definition from `maneuvers[]`; the maneuver vector or thrust model lives in the maneuver definition, not in the step. The step supplies:

- `spacecraft`: the spacecraft receiving the maneuver.
- `maneuver`: the maneuver definition ID to execute.
- `propagator` and `duration`: required only for finite maneuvers.

Orekit backend note: direct maneuver steps are supported for impulsive and finite maneuvers in supported frames. This is what allows targeter-generated in-plane phasing sequences to run as maneuver, coast, restore-maneuver timelines.

Impulsive example:

```json
{
  "step_id": "impulsive_burn_001",
  "command": "Maneuver",
  "spacecraft": "sat",
  "maneuver": "raise_apogee_to_500km"
}
```

Finite-maneuver example:

```json
{
  "step_id": "finite_burn_001",
  "command": "Maneuver",
  "spacecraft": "sat",
  "maneuver": "finite_raise_apogee",
  "propagator": "earth_prop",
  "duration": 745.0
}
```

If you only want to record state without applying a maneuver, use a `checkpoint` step instead.

### Checkpoint

```json
{
  "step_id": "checkpoint_001",
  "command": "Checkpoint",
  "checkpoint_id": "initial_state"
}
```

### Event action

```json
{
  "step_id": "event_action_ta_270",
  "command": "EventAction",
  "event_id": "event_ta_270"
}
```

## External dependencies and SPICE

SPICE dependencies are declared in `external_dependencies[]`.

```json
{
  "id": "dep_luna_spice",
  "type": "SPICEEphemeris",
  "provider": "SPICE",
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
python -m compiler spice-requests path/to/mission_spec.json --out generated/<mission_id>/simulation
python -m compiler resolve-spice generated/<mission_id>/simulation/dependencies/spice_requests.json --request-id dep_luna_spice --out generated/<mission_id>/simulation/dependencies/resolved/dep_luna_spice_ephemeris.json
python -m compiler export-visualization generated/<mission_id>/simulation
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

The viewer loads `*.eph.csv` as spacecraft trajectories and `*.body.eph.csv` as body trajectories.

Visualizer-facing restrictions:

- Spacecraft trajectory files must end with `.eph.csv`.
- Body trajectory files must end with `.body.eph.csv`.
- Ground-track files should use the `_GroundTrack` prefix.
- Checkpoints must not use `.eph.csv` or `.body.eph.csv`.
- Files should include a usable time column, preferably `ElapsedSecs`; `UTCGregorian` is also useful for labels and reports.
- The viewer does not transform between arbitrary frames. That should be done upstream in the simulation step, or through a separate frame converter.
- For a moving body to appear in a frame, provide a matching `BodyEphemeris` output in that same frame, for example `{"type": "BodyEphemeris", "body": "Luna", "reference_frame": "EarthMJ2000Eq", "path": "outputs/Luna_EarthMJ2000Eq.body.eph.csv"}`.
- For a static context body in a frame, declare frame metadata in `reference_frames[]`; AMAT copies it into `visualization_manifest.json`. At minimum, provide `name`, `origin`, and `axes`. For two-body rotating context, also provide `primary` and `secondary`. The viewer can place the origin at the scene center and place a secondary body as context, but this is not a substitute for a time-varying body ephemeris.

## Complete Mission Pattern

A common mission pattern has this shape:

```text
1. Define spacecraft, force models, propagators, maneuvers, outputs, checkpoints, and event detectors.
2. Record an initial checkpoint if the starting state should be auditable.
3. Propagate by elapsed time or to an event.
4. Execute impulsive or finite maneuvers by referencing maneuver definitions.
5. Record checkpoints after important events or maneuvers.
6. Continue propagation to the final analysis point.
7. Record a final checkpoint for evaluation/targeting acceptance.
8. Export spacecraft ephemerides in every frame the viewer should show.
9. Export body ephemerides or ground tracks when the viewer needs body context or surface-relative motion.
```

Use `generated/LEO_to_GEO/targeting/candidate_mission_spec.json` after running `targeter solve` as the reference for an event-driven impulsive targeting candidate.

## Common problems

### SPICE output missing

Read the printed `visualization_export` block. If it says SPICE resolution failed, either install/verify `spiceypy` and kernels or rely on backend-provided body ephemerides when available.

### Backend rejects the generated artifact

For GMAT, if `LoadScript returned: False`, inspect `generated_mission.script` and GMAT's message/log output. Common causes are unsupported frame axes, unsupported body-state report parameters, or missing custom body definitions. Other backends should expose equivalent compile/run diagnostics through `compile_result.json` and the generated runner output.

### Body ephemeris source is not what you expected

AMAT prefers body ephemerides resolved by the active simulation backend when they are available. If they are missing, AMAT may use a SPICE-derived fallback when resolved SPICE data exists. The manifest labels the source so the viewer can display provenance.

## Limitations

AMAT does not provide:

- General low-thrust or finite-maneuver targeting. Finite maneuvers can be simulated when manually specified, but the analytic targeter seeds impulsive maneuvers.
- Automated TLI/free-return targeting as a complete mission-design workflow.
- General optimizer workflows as MissionSpec-native tools.
- Automatic central-body state handoff across SOI boundaries.
- Estimation/covariance workflows.
- General visualization transforms between arbitrary frames.
- Guaranteed visualization semantics for every backend-specific custom frame.
- Direction-filtered node crossing enforcement in every backend.
- Full raw Orekit API exposure. The Orekit backend exposes MissionSpec-backed frame, event, force-model, finite-maneuver, and finite-difference correction features, but does not expose every Orekit Java class directly.

These are intended future layers on top of the current MissionSpec/artifact foundation.


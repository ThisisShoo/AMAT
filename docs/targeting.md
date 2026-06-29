# AMAT Targeting

This document explains how to write and run AMAT `target_problem.json` files.

Targeting turns a desired orbital outcome into a candidate MissionSpec. It is separate from simulation, optimization, and visualization. A successful targeting solve means AMAT produced a structurally valid candidate; final acceptance still depends on evaluating propagated simulation outputs.

## Layer Boundary

```text
TargetProblem
  -> validation and canonicalization
  -> targeting formulation
  -> analytic seed candidate
  -> MissionSpec materialization
  -> optional simulation-backed evaluation
  -> optional correction loop
```

The targeter does not own propagation. It can call a simulation backend through a swappable adapter during closed-loop workflows, but the TargetProblem itself should stay backend-neutral.

## TargetProblem Structure

Minimal shape:

```json
{
  "schema_version": "1.0.0",
  "problem_id": "my_transfer",
  "mission_id": "my_transfer",
  "transfer_strategy": {},
  "initial_state": {},
  "target": {},
  "limits": {},
  "execution": {},
  "verification": {},
  "metadata": {}
}
```

Top-level sections:

| Field | Required | Purpose |
|---|---:|---|
| `schema_version` | Yes | Must be `1.0.0`. |
| `problem_id` | Yes | Stable targeting problem ID. |
| `mission_id` | No | Mission/artifact ID. Defaults to `problem_id`. |
| `transfer_strategy` | Yes | Transfer family, central body, and maneuver policy. |
| `initial_state` | Yes | Starting orbit/state for the analytic seed. |
| `target` | Yes | Desired final orbit/state constraints. |
| `limits` | No | Mission-wide limits such as delta-v or minimum altitude. |
| `execution` | No | Backend and artifact behavior for evaluation/closed loop. |
| `verification` | No | Acceptance level metadata. |
| `metadata` | No | Human/project metadata. |

## Transfer Strategy

`transfer_strategy` selects the transfer family, central body, and maneuver placement policy.

Supported form:

```json
{
  "type": "two_impulse_apsidal_transfer",
  "central_body": "Earth",
  "maneuver_policy": {
    "type": "valid_node_low_speed",
    "maneuver_model": "impulsive",
    "departure_event": {"type": "initial_state"},
    "arrival_event": {"type": "apoapsis"},
    "allow_departure_phasing": true,
    "prefer_apsis_alignment": true,
    "fallback": "split_at_nearest_valid_node",
    "merge_maneuver_angle_tolerance_deg": 2.0
  }
}
```

### Transfer Type

| Value | Status | Meaning |
|---|---|---|
| `two_impulse_apsidal_transfer` | Supported | General two-impulse seed between selected endpoint geometry. Preferred public name. |
| `hohmann_transfer` | Supported alias | Circular coplanar cases reduce to classical Hohmann behavior. Internally uses the same apsidal-transfer seed path. |
| `bi_elliptic_transfer` | Planned | Not implemented as a TargetProblem solve. |
| `lambert_transfer` | Planned | Lambert solving exists inside conic-chain seed helpers, but not as a general TargetProblem strategy. |
| `patched_conic_transfer` | Planned | Building blocks exist; not exposed as a complete TargetProblem strategy. |
| `conic_chain_transfer` | Planned | Seed helpers exist for up to three connecting conics; full TargetProblem integration is incomplete. |
| `low_thrust_transcription` | Unsupported | Not implemented. |

Hohmann and Lambert are not interchangeable. Hohmann is a special two-impulse transfer case. Lambert is a boundary-value solve used by cross-SOI seed helpers and future transfer strategies.

### Central Body

Built-in body constants use NASA/JPL Solar System Dynamics values. Planetary `GM` values come from JPL DE440 astrodynamic parameters; radii come from JPL planetary and satellite physical-parameter tables. For the giant planets and Pluto, the listed `GM` is the system gravitational parameter.

| `central_body` | Radius km | GM km^3/s^2 |
|---|---:|---:|
| `Sun` | 695700.0 | 132712440041.27942 |
| `Mercury` | 2440.53 | 22031.868551 |
| `Venus` | 6051.8 | 324858.592 |
| `Earth` | 6378.1363 | 398600.435507 |
| `Luna` or `Moon` | 1737.4 | 4902.800118 |
| `Mars` | 3396.19 | 42828.375816 |
| `Jupiter` | 71492.0 | 126712764.1 |
| `Saturn` | 60268.0 | 37940584.8418 |
| `Uranus` | 25559.0 | 5794556.4 |
| `Neptune` | 24764.0 | 6836527.10058 |
| `Pluto` | 1188.3 | 975.5 |
| Custom string | required | required |

Custom-body fields:

| Field | Unit | Required | Meaning |
|---|---|---:|---|
| `central_body_radius` | `km` | Custom bodies only | Radius used for altitude conversion and body-intersection checks. |
| `central_body_mu` | `km^3/s^2` | Custom bodies only | Gravitational parameter used by the analytic two-body seed. |
| `stationary_orbit_radius` | `km` | No | Radius used by `geostationary_orbit`-style defaults. Earth supplies this automatically. |

Known-body constants can be overridden by explicitly providing these fields. If `initial_state.central_body` is supplied, it must match `transfer_strategy.central_body`.

## Maneuver Policy

`maneuver_policy` combines the maneuver model, endpoint event choices, and plane-change placement behavior.

String shorthand:

```json
"maneuver_policy": "valid_node_low_speed"
```

Structured form:

```json
"maneuver_policy": {
  "type": "valid_node_low_speed",
  "maneuver_model": "impulsive",
  "departure_event": {"type": "initial_state"},
  "arrival_event": {"type": "apoapsis"},
  "allow_departure_phasing": true,
  "prefer_apsis_alignment": true,
  "fallback": "split_at_nearest_valid_node",
  "merge_maneuver_angle_tolerance_deg": 2.0
}
```

Available policies:

| Policy | Behavior |
|---|---|
| `valid_node_low_speed` | Places plane-change work on the intersection line between the current and target orbital planes. It prefers low-speed opportunities and merges with an energy maneuver only when the node and maneuver opportunity are within `merge_maneuver_angle_tolerance_deg`. If phasing is enabled for a circular departure, AMAT may wait in the departure orbit so arrival occurs at a valid node. Otherwise it inserts a separate node plane-change maneuver. |

Policy fields:

| Field | Values | Default | Meaning |
|---|---|---|---|
| `type` | `valid_node_low_speed` | required | Maneuver placement policy. |
| `maneuver_model` | `impulsive`, `finite` | `impulsive` | `finite` is accepted as intent, but analytic seed generation remains impulsive. |
| `departure_event` | endpoint event object | `{"type": "initial_state"}` | Event or state used for the first transfer maneuver. |
| `arrival_event` | endpoint event object | `{"type": "apoapsis"}` | Event used for the arrival/insertion maneuver. |
| `allow_departure_phasing` | `true`, `false` | `true` | Permit waiting in a circular departure orbit to align arrival with a target-plane node. |
| `prefer_apsis_alignment` | `true`, `false` | `true` | Prefer merging plane correction with an apsidal energy maneuver when geometry allows. |
| `fallback` | `split_at_nearest_valid_node` | `split_at_nearest_valid_node` | Separate plane-change fallback when merger is invalid. |
| `merge_maneuver_angle_tolerance_deg` | number >= 0 | `2.0` | Angular tolerance for treating two maneuver opportunities as coincident. |

Example:

```json
{
  "type": "two_impulse_apsidal_transfer",
  "central_body": "Mars",
  "maneuver_policy": {
    "type": "valid_node_low_speed",
    "maneuver_model": "impulsive",
    "departure_event": {
      "type": "true_anomaly",
      "value": {"value": 35.0, "unit": "deg"}
    },
    "arrival_event": {
      "type": "apoapsis"
    },
    "allow_departure_phasing": false,
    "prefer_apsis_alignment": true,
    "fallback": "split_at_nearest_valid_node"
  }
}
```

Endpoint event objects:

| Object                                                                     | Valid for             | Resolves to                                                                                                                |
| -------------------------------------------------------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `{"type": "initial_state"}`                                                | Departure only        | The supplied initial state's `true_anomaly`.                                                                               |
| `{"type": "true_anomaly", "value": {"value": 35, "unit": "deg"}}`          | Departure and arrival | The supplied true anomaly.                                                                                                 |
| `{"type": "argument_of_latitude", "value": {"value": 180, "unit": "deg"}}` | Departure and arrival | The supplied argument of latitude, converted to true anomaly with `true_anomaly = argument_of_latitude - aop mod 360 deg`. |
| `{"type": "periapsis"}`                                                    | Departure and arrival | True anomaly `0 deg`.                                                                                                      |
| `{"type": "apoapsis"}`                                                     | Departure and arrival | True anomaly `180 deg`.                                                                                                    |
| `{"type": "apsis", "kind": "periapsis"}`                                   | Departure and arrival | Canonicalizes to `{"type": "periapsis"}`.                                                                                  |
| `{"type": "apsis", "kind": "apoapsis"}`                                    | Departure and arrival | Canonicalizes to `{"type": "apoapsis"}`.                                                                                   |
| `{"type": "ascending_node"}`                                               | Departure and arrival | True anomaly `-aop mod 360 deg` for the relevant endpoint orbit.                                                           |
| `{"type": "descending_node"}`                                              | Departure and arrival | True anomaly `180 - aop mod 360 deg` for the relevant endpoint orbit.                                                      |
| `{"type": "node", "kind": "ascending"}`                                    | Departure and arrival | Canonicalizes to `{"type": "ascending_node"}`.                                                                             |
| `{"type": "node", "kind": "descending"}`                                   | Departure and arrival | Canonicalizes to `{"type": "descending_node"}`.                                                                            |

Grouped endpoint events may either select a specific member or defer selection to the targeter.

| Object | Meaning |
|---|---|
| `{"type": "apsis"}` | Select the next apsis, either periapsis or apoapsis, whichever is encountered first in the forward direction. |
| `{"type": "apsis", "kind": "periapsis"}` | Select periapsis explicitly. |
| `{"type": "apsis", "kind": "apoapsis"}` | Select apoapsis explicitly. |
| `{"type": "node"}` | Select the next orbital node, either ascending or descending, whichever is encountered first in the forward direction. |
| `{"type": "node", "kind": "ascending"}` | Select the ascending node explicitly. |
| `{"type": "node", "kind": "descending"}` | Select the descending node explicitly. |

When `kind` is omitted, AMAT resolves the grouped endpoint to the next concrete event before seed generation. The resolved event is stored as `resolved_specific_type`, and the corresponding true anomaly is stored as `resolved_true_anomaly`.

Example using grouped endpoint events:

```json
"maneuver_policy": {
  "type": "valid_node_low_speed",
  "maneuver_model": "impulsive",
  "departure_event": {
    "type": "node",
    "kind": "ascending"
  },
  "arrival_event": {
    "type": "apsis",
    "kind": "apoapsis"
  },
  "allow_departure_phasing": false,
  "prefer_apsis_alignment": true,
  "fallback": "split_at_nearest_valid_node"
}
```

AMAT canonicalizes every endpoint event to a resolved true anomaly before seed generation. Apsis and node objects are shortcuts; they do not create a second endpoint-event representation.


## Initial State

Supported representations:

| `representation` | Status | Notes |
|---|---|---|
| `circular_orbit` | Supported | Uses `altitude` and the selected central-body radius to compute `sma`. |
| `keplerian` | Supported | Can start at any supplied `true_anomaly`; the first transfer maneuver is immediate if the state is not at an apsis. |
| `cartesian` | Supported | Uses `position_km` and `velocity_km_s`; AMAT derives equivalent Keplerian elements for the analytic seed and preserves the Cartesian state in the materialized MissionSpec. |
| `cometary` | Supported | Uses periapsis radius, eccentricity, and angular elements; AMAT derives equivalent Keplerian elements for the analytic seed. Bound elliptic inputs are required. |

Circular-orbit form:

```json
{
  "representation": "circular_orbit",
  "central_body": "<central-body-name>",
  "altitude": {"value": 300.0, "unit": "km"},
  "inclination": {"value": 0.0, "unit": "deg"},
  "raan": {"value": 0.0, "unit": "deg"},
  "aop": {"value": 0.0, "unit": "deg"},
  "true_anomaly": {"value": 0.0, "unit": "deg"},
  "epoch": "2026-01-01T00:00:00Z",
  "frame": "<default-inertial-frame>"
}
```

Keplerian form:

```json
{
  "representation": "keplerian",
  "central_body": "<central-body-name>",
  "sma": {"value": 6678.1363, "unit": "km"},
  "eccentricity": 0.0,
  "inclination": {"value": 0.0, "unit": "deg"},
  "raan": {"value": 0.0, "unit": "deg"},
  "aop": {"value": 0.0, "unit": "deg"},
  "true_anomaly": {"value": 45.0, "unit": "deg"},
  "epoch": "2026-01-01T00:00:00Z",
  "frame": "<default-inertial-frame>"
}
```

Cartesian form:

```json
{
  "representation": "cartesian",
  "central_body": "<central-body-name>",
  "position_km": [6678.1363, 0.0, 0.0],
  "velocity_km_s": [0.0, 7.7258, 0.0],
  "epoch": "2026-01-01T00:00:00Z",
  "frame": "<default-inertial-frame>"
}
```

Cometary form:

```json
{
  "representation": "cometary",
  "central_body": "<central-body-name>",
  "periapsis_radius": {"value": 8000.0, "unit": "km"},
  "eccentricity": 0.2,
  "inclination": {"value": 5.0, "unit": "deg"},
  "raan": {"value": 10.0, "unit": "deg"},
  "aop": {"value": 20.0, "unit": "deg"},
  "true_anomaly": {"value": 30.0, "unit": "deg"},
  "epoch": "2026-01-01T00:00:00Z",
  "frame": "<default-inertial-frame>"
}
```

If `frame` is omitted, AMAT defaults to `EarthMJ2000Eq` for Earth-centered problems and `<central_body>MJ2000Ec` for every other central body.

## Target

Supported target types:

| Value | Status | Meaning |
|---|---|---|
| `geostationary_orbit` | Earth default supported | Defaults to Earth GEO radius, near-zero eccentricity, and near-equatorial inclination. For other bodies, provide `sma` or `transfer_strategy.stationary_orbit_radius`. |
| `circular_orbit` | Supported | Target circular orbit by `altitude` or `sma`. |
| `keplerian_state` | Supported | Target final Keplerian orbit terms directly. |
| `cartesian_state` | Supported | Target by `position_km` and `velocity_km_s`; AMAT derives equivalent orbital elements for seed generation and acceptance constraints. |
| `cometary_state` | Supported | Target by periapsis radius, eccentricity, and angular elements; AMAT derives equivalent Keplerian elements. Bound elliptic inputs are required. |

Common target fields:

```json
{
  "type": "keplerian_state",
  "sma": {"value": 42164.1696, "unit": "km"},
  "eccentricity": 0.0,
  "eccentricity_max": 0.0001,
  "inclination": {"value": 0.0, "unit": "deg"},
  "inclination_max": {"value": 0.05, "unit": "deg"},
  "raan": {"value": 0.0, "unit": "deg"},
  "aop": {"value": 0.0, "unit": "deg"},
  "argument_of_latitude": {"value": 45.0, "unit": "deg"},
  "argument_of_latitude_max": {"value": 0.1, "unit": "deg"}
}
```

Notes:

- `argument_of_latitude` is optional. Use it when the final location in the orbital plane matters, such as targeting a specific body-fixed ground-track relationship.

## Phasing Policy

Phasing is used when the final position along the target orbit matters and orbit shape targeting alone is insufficient.

If `target.argument_of_latitude` is present, AMAT enables phase strategy selection automatically unless `transfer_strategy.phase_policy.mode` is set to `disabled`. An explicit `phase_policy` is still useful when you want to restrict strategies, cap delta-v, or change the search bounds.

```json
"phase_policy": {
  "mode": "auto",
  "allowed_strategies": ["coast_to_phase", "in_plane_drift"],
  "objective": "min_delta_v",
  "max_revolutions": 5,
  "restore_target_orbit": true
}
```

Supported fields:

| Field | Values | Meaning |
|---|---|---|
| `mode` | `auto`, `explicit`, `disabled` | Enables or disables phase strategy selection. |
| `allowed_strategies` | Array | Candidate strategies the selector may consider. |
| `objective` | String | Selection objective. `min_delta_v` is the current practical objective. |
| `max_revolutions` | Integer | Maximum drift-orbit revolutions for analytic in-plane phasing. |
| `max_delta_v_km_s` | Number or `null` | Optional phasing delta-v cap. |
| `restore_target_orbit` | Boolean | Whether the phase strategy must return to the target orbit after phasing. |
| `target` | `argument_of_latitude` | The phase parameter being targeted. |
| `at` | String | The evaluation point, currently `final_state`. |

Strategy support:

| Strategy | Status | Behavior |
|---|---|---|
| `coast_to_phase` | Selector-aware | Rejected when the final-state propagation duration is fixed. |
| `in_plane_drift` | Implemented | Adds an in-plane maneuver, drift coast, and restore maneuver around the target body. |
| `departure_epoch_shift` | Planned | Shift departure timing to satisfy phase before transfer. |
| `transfer_time_adjustment` | Planned | Adjust transfer duration or arrival branch. |
| `resonant` | Planned | Use resonant cycles for repeated body-relative geometry. |
| `multi_revolution_transfer` | Planned | Select multi-revolution transfer branches. |

When phasing is active, the selector writes `phase_strategy_decision.json` during `targeter solve`. The default automatic policy considers `coast_to_phase` and `in_plane_drift` with a `min_delta_v` objective. The implemented strategy is body-neutral: it uses the target central body's gravitational parameter and semi-major axis, not Earth/GEO constants.

`in_plane_drift` materializes as an in-plane maneuver, a drift propagation segment, and a restore maneuver. Simulation backends must support direct impulsive maneuver steps to run that candidate. Orekit supports these direct impulsive `VNB` steps; finite-maneuver phasing is unsupported.

- `raan` and `aop` are physically undefined for exactly equatorial or circular orbits. Evaluation suppresses undefined RAAN/AOP residuals when target and achieved inclination/eccentricity are within tolerance.
- `altitude` targets are converted using `transfer_strategy.central_body_radius`.
- Cartesian and cometary target inputs are canonicalized to Keplerian fields before formulation. The analytic seed supports bound elliptic endpoint orbits only.

## Limits, Execution, and Verification

Example:

```json
{
  "limits": {
    "maximum_total_delta_v": {"value": 4.5, "unit": "km/s"},
    "minimum_altitude": {"value": 200.0, "unit": "km"}
  },
  "execution": {
    "backend": "<simulation-backend-id>",
    "targeting_fidelity": "two_body",
    "acceptance_fidelity": "operational",
    "artifact_persistence": "accepted_iterations"
  },
  "verification": {
    "required_level": "L1",
    "run_acceptance_simulation": false
  }
}
```

Execution fields are backend-neutral intent. The closed-loop implementation selects simulation and correction adapters by ID; available adapter IDs are implementation details rather than TargetProblem concepts.

## Closed-Loop Requirements

Closed-loop targeting is simulation-backed. It needs:

- A simulation backend ID, such as `gmat` or `orekit`.
- A correction backend ID. Use `stm` for a generic STM-shaped assessment artifact, or `orekit_fd` when the Orekit simulation adapter is expected to synthesize finite-difference sensitivities from perturbation runs.
- Runtime outputs that include a final-state checkpoint with the state columns required by the TargetProblem acceptance metrics.
- STM assessment artifacts when the selected correction backend needs them. Orekit can synthesize finite-difference STM assessments; GMAT workflows must emit or provide configured STM artifacts.

Closed-loop artifacts are operational evidence, not a guarantee of high-fidelity mission success. Always finish with `targeter evaluate` against the completed simulation outputs.

## Commands

This section only covers `targeter` commands.

| Task | Command |
|---|---|
| Validate a TargetProblem | `python -m targeter validate path/to/target_problem.json` |
| Solve an analytic candidate | `python -m targeter solve path/to/target_problem.json --out generated/<mission_id>/targeting` |
| Evaluate completed simulation outputs | `python -m targeter evaluate path/to/target_problem.json --simulation-dir generated/<mission_id>/simulation --out generated/<mission_id>/targeting` |
| Prepare a closed-loop iteration | `python -m targeter closed-loop path/to/target_problem.json --out generated/<mission_id>/targeting` |
| Run closed loop with explicit modules | `python -m targeter closed-loop path/to/target_problem.json --simulation-backend <backend-id> --correction-backend <correction-backend-id> --max-iterations 3 --run --out generated/<mission_id>/targeting` |
| Generate a conic-chain seed | `python -m targeter conic-chain-seed --body-ephemeris path/to/Target_Frame.body.eph.csv --body <body-name> --frame <frame-name> --departure-body <origin-body-name> --target-body <target-body-name> --central-body <central-body-name> --departure-altitude-km <parking-orbit-altitude> --seed-out generated/<mission_id>/targeting/conic_chain_seed.json` |

For custom central bodies in `conic-chain-seed`, also provide `--central-mu-km3-s2` and `--central-radius-km`.

## Targeting Artifacts

`solve` writes:

```text
generated/<mission_id>/targeting/
  target_problem.canonical.json
  maneuver_plan.json
  targeting_result.json
  candidate_mission_spec.json
```

Use `--artifact-profile debug` to also write `targeting_formulation.json`, `initial_candidate.json`, `phase_strategy_decision.json`, `acceptance_result.json`, and `provenance.json`.

`evaluate` consumes completed simulation outputs and writes:

```text
simulation_evaluation.json
acceptance_result.json
```

`acceptance_result.json` remains `not_run` until a completed simulation is evaluated.

## Epoch Convention

AMAT stores absolute epochs as UTC ISO 8601 strings:

```text
YYYY-MM-DDTHH:MM:SS.sssZ
```

Backend adapters render those values only when generating backend artifacts. This keeps TargetProblem and MissionSpec files backend-neutral.

## Techniques

AMAT uses three targeting techniques:

| Technique | Purpose |
|---|---|
| Analytic two-impulse seed | Produces the initial candidate for same-central-body transfers. Circular coplanar cases reduce to classical Hohmann behavior; elliptical endpoints and node-aware plane changes are also supported. |
| Conic-chain seed | Produces patched-conic cross-SOI seeds from backend-produced body ephemerides. Lambert solving is used inside this helper, but is not a top-level `transfer_strategy.type`. |
| Closed-loop correction | Runs simulation-backed evaluation and delegates correction to a selected correction module. The `stm` backend consumes STM assessment artifacts and stops if those artifacts are unavailable. The `orekit_fd` backend consumes the finite-difference STM-shaped artifacts synthesized by the Orekit simulation adapter. |

These techniques produce candidates and corrections, not proof of final high-fidelity success. Use `targeter evaluate` or a closed-loop run to compare propagated outputs against the TargetProblem.

## Limitations

TargetProblem limitations:

- General Lambert transfer as a TargetProblem strategy.
- General patched-conic or conic-chain materialization from a TargetProblem.
- Native finite-maneuver seed generation. Finite maneuvers can be simulated in MissionSpec, but analytic targeting seeds impulsive maneuvers.
- Automatic central-body state handoff across SOI boundaries as part of TargetProblem execution.
- Optimizer-backed TargetProblem solve modes.
- Full feature parity across simulation backend adapters. GMAT is the primary high-fidelity backend; Orekit supports selected targeting workflows.
- Guaranteed propagation support for arbitrary custom central bodies. The targeter can materialize a candidate with custom body constants, but the selected compiler/simulation backend must also support that body.

## Data Sources

Built-in `GM` values use [NASA/JPL Solar System Dynamics astrodynamic parameters](https://ssd.jpl.nasa.gov/astro_par.html). Built-in planetary radii use [NASA/JPL planetary physical parameters](https://ssd.jpl.nasa.gov/planets/phys_par.html). Luna/Moon radius and `GM` use [NASA/JPL planetary satellite physical parameters](https://ssd.jpl.nasa.gov/sats/phys_par/).

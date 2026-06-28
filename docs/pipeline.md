# AMAT Operation Pipeline

This document shows how to run AMAT through the targeting, simulation, and visualization layers.

AMAT supports two entry points:

- Targeting-first: start with `target_problem.json`, generate a candidate MissionSpec, compile, run, evaluate, and visualize. 
- Simulation-first: start with an authored `mission_spec.json`, compile, run, and visualize.

Use commands from the project root. On Windows, replace `python` with the interpreter you installed AMAT into if needed.

## Folder Layout

Use one mission folder under `generated/<mission_id>/`:

```text
generated/<mission_id>/
  targeting/
    target_problem.canonical.json
    targeting_formulation.json
    initial_candidate.json
    targeting_result.json
    candidate_mission_spec.json
    acceptance_result.json
    provenance.json
  simulation/
    mission_spec.canonical.json  # public MissionSpec, schema_version 2.0.0
    mission_spec.backend_ir.json  # lowered backend input, schema_version 1.0.0
    generated_mission.py
    generated_mission.script    # GMAT backend only
    compile_result.json
    validation_report.json
    artifact_manifest.json
    visualization_manifest.json
    outputs/
    visualization/
      trajectory.html
      visualization_report.json
```

The visualizer can discover this layout when pointed at the mission id, the mission root, the `targeting/` directory, or the `simulation/` directory.

Layer ownership:

- `targeter` owns TargetProblem validation, analytic candidates, closed-loop correction artifacts, and acceptance reports.
- `compiler` owns public MissionSpec validation, canonicalization, backend IR lowering, generated backend artifacts, and visualization prerequisites.
- The generated backend runner owns runtime CSV products under `simulation/outputs/`.
- `visualizer` owns standalone HTML generation and `visualization_report.json`.

## Targeting-First Pipeline

Start with a semantic target problem. The targeting layer generates analytic initial candidates. By itself, it does not run any simulation.

### 1. Validate The Target Problem

```bash
python -m targeter validate examples/LEO_to_GEO/target_problem.json
```

Validation canonicalizes the target problem internally and reports whether the request is structurally supported.

### 2. Solve For An Initial Candidate

```bash
python -m targeter solve examples/LEO_to_GEO/target_problem.json \
  --out generated/LEO_to_GEO/targeting
```

This writes the targeting artifacts and `candidate_mission_spec.json`.

For impulsive non-coplanar transfers, the initial guess is node-aware: AMAT computes the intersection between the initial and target orbital planes, chooses the node closest to apoapsis on the transfer arc, and emits a separate plane-change maneuver unless that node is close enough to merge with an apsidal energy maneuver.

### 3. Validate The Candidate MissionSpec

```bash
python -m compiler validate generated/LEO_to_GEO/targeting/candidate_mission_spec.json
```

This checks the MissionSpec that will be handed to the simulation compiler.

### 4. Compile The Simulation

```bash
python -m compiler compile generated/LEO_to_GEO/targeting/candidate_mission_spec.json \
  --out generated/LEO_to_GEO/simulation
```

Compilation writes the canonical MissionSpec, generated Python runner, manifests, expected output declarations, and visualization manifest. GMAT compilation also writes a GMAT-native script for audit and replay.

To compile with Orekit instead of GMAT, pass the backend explicitly:

```bash
python -m compiler compile generated/LEO_to_GEO/targeting/candidate_mission_spec.json \
  --backend orekit \
  --out generated/LEO_to_GEO/simulation
```

Orekit compilation writes a generated Python runner and normal AMAT manifests. It does not write a GMAT-native script.

### 5. Run The Simulation Backend

```bash
python generated/LEO_to_GEO/simulation/generated_mission.py --run
```

For GMAT, the runner loads and replays `generated_mission.script` when the mission needs GMAT ReportFile outputs. For Orekit, the runner starts Orekit through JPype and uses the generated runtime specification directly. Runtime CSV files are written under:

```text
generated/LEO_to_GEO/simulation/outputs/
```

### 6. Evaluate The Runtime Result

```bash
python -m targeter evaluate examples/LEO_to_GEO/target_problem.json \
  --simulation-dir generated/LEO_to_GEO/simulation \
  --out generated/LEO_to_GEO/targeting
```

Evaluation compares the runtime final state against the target problem and updates:

```text
generated/LEO_to_GEO/targeting/simulation_evaluation.json
generated/LEO_to_GEO/targeting/acceptance_result.json
```

If the result is outside tolerance, use the evaluation artifact to decide whether the next step is patched-conic/hyperbola refinement, STM correction, or manual mission redesign.

For a targeting-first closed-loop run with Orekit:

```bash
python -m targeter closed-loop examples/LEO_to_GEO/target_problem.json \
  --simulation-backend orekit \
  --correction-backend orekit_fd \
  --max-iterations 3 \
  --run \
  --out generated/LEO_to_GEO/targeting
```

The Orekit simulation adapter can synthesize `outputs/stm_assessment.json` by running finite-difference perturbation simulations. The `orekit_fd` correction backend consumes that artifact through the same backend-neutral linear correction contract while preserving the explicit Orekit finite-difference backend choice. The generic `stm` correction backend can also consume the same artifact when selected explicitly.

### 7. Render The Visualization

```bash
python -m visualizer view --mission-dir generated/LEO_to_GEO/simulation
```

or, when using the standard generated layout:

```bash
python -m visualizer view LEO_to_GEO
```

The viewer writes:

```text
generated/LEO_to_GEO/simulation/visualization/trajectory.html
generated/LEO_to_GEO/simulation/visualization/visualization_report.json
```

Open `trajectory.html` in a browser.

## Simulation-First Pipeline

Use this path when a hand-authored MissionSpec already exists. The file must use public MissionSpec `schema_version: "2.0.0"`, not the lowered backend IR.

### 1. Validate

```bash
python -m compiler validate path/to/mission_spec.json
```

### 2. Compile

```bash
python -m compiler compile path/to/mission_spec.json \
  --out generated/<mission_id>/simulation
```

### 3. Run

```bash
python generated/<mission_id>/simulation/generated_mission.py --run
```

### 4. Render

```bash
python -m visualizer view --mission-dir generated/<mission_id>/simulation
```

## Visualization Refresh Only

If GMAT outputs already exist and only viewer artifacts need regeneration:

```bash
python -m compiler export-visualization generated/cislunar_demo/simulation
python -m visualizer view --mission-dir generated/cislunar_demo/simulation
```

Use this after changing visualization code, body textures, frame declarations, or manifest generation.

## Important Artifacts

Targeting artifacts:

- `target_problem.canonical.json`: normalized public request.
- `targeting_formulation.json`: constraints, decision variables, and solver contract.
- `initial_candidate.json`: analytic seed with maneuver list and delta-v estimates.
- `candidate_mission_spec.json`: handoff into the simulation layer.
- `targeting_result.json`: targeting-layer summary.
- `acceptance_result.json`: not-run after `solve`, updated after `evaluate`.

Simulation artifacts:

- `generated_mission.script`: GMAT-native script for audit and replay. Orekit runs do not emit this file.
- `generated_mission.py`: Python runner.
- `outputs/*.csv`: backend runtime outputs. GMAT writes ReportFile-derived CSVs and normalizes ephemeris-style files to requested `outputs[].step` cadence when possible; Orekit writes spacecraft ephemeris, checkpoint, final-state, supported body-ephemeris, and ground-track CSVs on the requested output cadence for supported or validated fallback frames.
- `dependencies/spice_requests.json`: optional SPICE request contract generated when the MissionSpec declares SPICE ephemeris dependencies, including Orekit body-ephemeris fallback prerequisites.
- `outputs/stm_assessment.json`: optional targeter correction artifact. Orekit can synthesize it from finite-difference perturbation runs during closed-loop targeting.
- `visualization_manifest.json`: viewer-facing description of traces, frames, checkpoints, bodies, finite maneuvers, and ground tracks.

Visualization artifacts:

- `trajectory.html`: standalone interactive viewer.
- `visualization_report.json`: what the viewer discovered and loaded.

## Time And Sampling Controls

MissionSpec separates propagation control from output cadence:

- `propagators[].initial_step`, `minimum_step`, `maximum_step`, and `accuracy` control backend propagation behavior.
- `outputs[].step` controls the row cadence for spacecraft ephemeris, ground-track, and body-ephemeris CSV files.
- Checkpoints and final-state outputs are sparse products and ignore `outputs[].step`.
- GMAT emits ReportFile products and AMAT normalizes ephemeris-style files to the requested elapsed-time cadence when possible.
- Orekit samples densely enough for the requested output cadence and writes each output file on its own `step` grid.

## Common Checks

After targeting:

```bash
type generated/<mission_id>/targeting/initial_candidate.json
```

Confirm the maneuver plan has the expected maneuver count, event detectors, and plane-change placement.

After compile:

```bash
type generated/<mission_id>/simulation/generated_mission.script
```

Check that event-driven maneuvers compile into the expected GMAT `Propagate` and `Maneuver` commands.

For Orekit runs, inspect `generated_mission.py` and `compile_result.json` instead. Orekit supports elapsed-time/date propagation, checkpoints, direct impulsive and segmented finite maneuver steps in supported maneuver frames, per-segment propagator context, two-body propagation, selected numerical force-model propagation, date/anomaly/apsis/node/distance/SOI/elevation/eclipse event actions, spacecraft ephemeris, final-state output, supported body ephemerides, ground tracks from surface-fixed states, and finite-difference STM assessment generation during targeter closed-loop runs.

After run:

```bash
dir generated/<mission_id>/simulation/outputs
```

Confirm expected ephemeris, checkpoint, body ephemeris, and ground-track CSVs exist.

For Orekit, expect spacecraft ephemeris, checkpoint, final-state, supported body-ephemeris, and ground-track CSVs when those products are requested and the requested bodies/frames are in the adapter's supported set. For SPICE-backed body ephemerides, expect `dependencies/spice_requests.json` after compile and resolved `*.body.eph.csv` files after the visualization export/SPICE resolution step.

After render:

```bash
type generated/<mission_id>/simulation/visualization/visualization_report.json
```

Confirm the viewer loaded the intended frames and traces.

## Troubleshooting

If `python -m targeter solve` succeeds but simulation misses the target, remember that the analytic candidate is a seed. Run `python -m targeter evaluate` and inspect the residuals before changing the mission.

If `targeter evaluate` reports empty residuals, inspect `outputs/final_state_checkpoint.csv`. It must include final Keplerian or Cartesian state columns, not only time columns.

If GMAT fails to load the script, inspect `generated_mission.script` first. Common causes are unsupported frame names, unsupported report parameters, or a MissionSpec event that compiles to an impossible stop condition.

If the generated runner cannot import GMAT or Orekit, confirm that `GMAT`, `OREKIT_DATA_PATH`, `JAVA_HOME`, and the active Python environment match the backend you are running.

If visualization cannot find outputs, pass `--mission-dir` explicitly to the directory containing `outputs/`, usually `generated/<mission_id>/simulation`.

If the viewer omits a body in a rotating frame, check `visualization_manifest.json` for `frames`, `body_ephemerides`, and `force_model_bodies`.



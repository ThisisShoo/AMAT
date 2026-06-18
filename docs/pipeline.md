# AMAT Pipeline

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
    mission_spec.canonical.json
    generated_mission.py
    generated_mission.script
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

## Targeting-First Pipeline

Start with a semantic target problem. The targeting layer currently generates analytic initial candidates. By itself, it does not run any simulation.

### 1. Validate The Target Problem

```bash
python -m mission_targeting validate examples/elliptical_LEO_to_GEO/target_problem.json
```

Validation canonicalizes the target problem internally and reports whether the request is structurally supported.

### 2. Solve For An Initial Candidate

```bash
python -m mission_targeting solve examples/elliptical_LEO_to_GEO/target_problem.json \
  --out generated/elliptical_LEO_to_GEO/targeting
```

This writes the targeting artifacts and `candidate_mission_spec.json`.

For impulsive non-coplanar transfers, the initial guess is node-aware: AMAT computes the intersection between the initial and target orbital planes, chooses the node closest to apoapsis on the transfer arc, and emits a separate plane-change maneuver unless that node is close enough to merge with an apsidal energy burn.

### 3. Validate The Candidate MissionSpec

```bash
python -m mission_compiler validate generated/elliptical_LEO_to_GEO/targeting/candidate_mission_spec.json
```

This checks the MissionSpec that will be handed to the simulation compiler.

### 4. Compile The Simulation

```bash
python -m mission_compiler compile generated/elliptical_LEO_to_GEO/targeting/candidate_mission_spec.json \
  --out generated/elliptical_LEO_to_GEO/simulation
```

Compilation writes the canonical MissionSpec, GMAT-native script, generated Python runner, manifests, expected output declarations, and visualization manifest.

### 5. Run GMAT

```bash
python generated/elliptical_LEO_to_GEO/simulation/generated_mission.py --run
```

The runner loads and replays `generated_mission.script` when the mission needs GMAT ReportFile outputs. Runtime CSV files are written under:

```text
generated/elliptical_LEO_to_GEO/simulation/outputs/
```

### 6. Evaluate The Runtime Result

```bash
python -m mission_targeting evaluate examples/elliptical_LEO_to_GEO/target_problem.json \
  --simulation-dir generated/elliptical_LEO_to_GEO/simulation \
  --out generated/elliptical_LEO_to_GEO/targeting
```

Evaluation compares the runtime final state against the target problem and updates:

```text
generated/elliptical_LEO_to_GEO/targeting/simulation_evaluation.json
generated/elliptical_LEO_to_GEO/targeting/acceptance_result.json
```

If the result is outside tolerance, use the evaluation artifact to decide whether the next step is patched-conic/hyperbola refinement, STM correction, or manual mission redesign.

### 7. Render The Visualization

```bash
python -m mission_visualizer view --mission-dir generated/elliptical_LEO_to_GEO/simulation
```

or, when using the standard generated layout:

```bash
python -m mission_visualizer view elliptical_LEO_to_GEO
```

The viewer writes:

```text
generated/elliptical_LEO_to_GEO/simulation/visualization/trajectory.html
generated/elliptical_LEO_to_GEO/simulation/visualization/visualization_report.json
```

Open `trajectory.html` in a browser.

## Simulation-First Pipeline

Use this path when an example or hand-authored MissionSpec already exists.

### 1. Validate

```bash
python -m mission_compiler validate examples/elliptical_LEO_to_GEO/mission_spec.json
```

### 2. Compile

```bash
python -m mission_compiler compile examples/elliptical_LEO_to_GEO/mission_spec.json \
  --out generated/elliptical_LEO_to_GEO/simulation
```

### 3. Run

```bash
python generated/elliptical_LEO_to_GEO/simulation/generated_mission.py --run
```

### 4. Render

```bash
python -m mission_visualizer view --mission-dir generated/elliptical_LEO_to_GEO/simulation
```

The same pattern applies to the current demonstration examples:

```bash
python -m mission_compiler compile examples/cislunar_demo/mission_spec.json --out generated/cislunar_demo/simulation
python generated/cislunar_demo/simulation/generated_mission.py --run
python -m mission_visualizer view --mission-dir generated/cislunar_demo/simulation
```

```bash
python -m mission_compiler compile examples/MEO_demo/mission_spec.json --out generated/MEO_demo/simulation
python generated/MEO_demo/simulation/generated_mission.py --run
python -m mission_visualizer view --mission-dir generated/MEO_demo/simulation
```

## Visualization Refresh Only

If GMAT outputs already exist and only viewer artifacts need regeneration:

```bash
python -m mission_compiler export-visualization generated/cislunar_demo/simulation
python -m mission_visualizer view --mission-dir generated/cislunar_demo/simulation
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

- `generated_mission.script`: GMAT-native script for audit and replay.
- `generated_mission.py`: Python runner.
- `outputs/*.csv`: GMAT ReportFile outputs.
- `visualization_manifest.json`: viewer-facing description of traces, frames, checkpoints, bodies, finite burns, and ground tracks.

Visualization artifacts:

- `trajectory.html`: standalone interactive viewer.
- `visualization_report.json`: what the viewer discovered and loaded.

## Common Checks

After targeting:

```bash
type generated/<mission_id>/targeting/initial_candidate.json
```

Confirm the maneuver plan has the expected burn count, events, and plane-change placement.

After compile:

```bash
type generated/<mission_id>/simulation/generated_mission.script
```

Check that event-driven maneuvers compile into the expected GMAT `Propagate` and `Maneuver` commands.

After run:

```bash
dir generated/<mission_id>/simulation/outputs
```

Confirm expected ephemeris, checkpoint, body ephemeris, and ground-track CSVs exist.

After render:

```bash
type generated/<mission_id>/simulation/visualization/visualization_report.json
```

Confirm the viewer loaded the intended frames and traces.

## Troubleshooting

If `python -m mission_targeting solve` succeeds but simulation misses the target, remember that the analytic candidate is a seed. Run `python -m mission_targeting evaluate` and inspect the residuals before changing the mission.

If GMAT fails to load the script, inspect `generated_mission.script` first. Common causes are unsupported frame names, unsupported report parameters, or a MissionSpec event that compiles to an impossible stop condition.

If visualization cannot find outputs, pass `--mission-dir` explicitly to the directory containing `outputs/`, usually `generated/<mission_id>/simulation`.

If the viewer omits a body in a rotating frame, check `visualization_manifest.json` for `frames`, `body_ephemerides`, and `force_model_bodies`.

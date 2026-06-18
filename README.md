# AMAT

AMAT is a mission simulation, targeting, optimization, and visualization workbench for spacecraft trajectory studies. It turns machine-readable mission descriptions into GMAT-backed simulations, collects repeatable artifacts, and renders interactive trajectory views for inspection.

AMAT is not meant to replace GMAT, SPICE, or a flight dynamics toolchain. It sits above them as an orchestration layer: users describe a mission in AMAT's data models, AMAT generates auditable backend artifacts, GMAT performs propagation, and the visualization layer presents the resulting trajectory products.

## What AMAT Does

AMAT currently provides four cooperating layers:

- **Mission compilation**: validates a `mission_spec.json`, canonicalizes it, and emits GMAT-native scripts plus generated Python runners.
- **Simulation execution**: runs generated GMAT missions and collects spacecraft ephemerides, checkpoints, body ephemerides, reports, manifests, and provenance under `generated/<mission_id>/`.
- **Targeting and optimization**: creates initial maneuver seeds for supported transfer problems and provides a swappable optimization layer, currently with GMAT as the first backend.
- **Visualization**: reads generated simulation artifacts and creates an interactive 3D HTML viewer with spacecraft trajectories, body ephemerides, checkpoints, ground tracks, and reference-frame context.

The normal artifact flow is:

```text
MissionSpec or TargetProblem
  -> AMAT validation/canonicalization
  -> generated GMAT script and Python runner
  -> GMAT propagation
  -> output CSVs and manifests
  -> interactive visualization
```

## Installation

AMAT is a Python project. Install it from the repository root:

```bash
python -m pip install -e .[dev]
```

This installs the AMAT packages and development test dependency. The core dependencies include `gmatpyplus`, `spiceypy`, `numpy`, `pandas`, `jinja2`, `jsonschema`, and `plotly`.

Verify that the CLIs import:

```bash
python -m mission_compiler --help
python -m mission_targeting --help
python -m mission_optimization --help
python -m mission_visualizer --help
```

Installed console entry points are also declared:

```bash
amat --help
amat-target --help
amat-optimize --help
mission-visualizer --help
```

Using `python -m ...` is preferred during development because it makes the active Python environment explicit.

## GMAT Setup

AMAT's simulation backend requires GMAT and its Python interface. The `gmatpyplus` wrapper expects a GMAT installation path. Set the `GMAT` environment variable to the GMAT root directory.

Windows PowerShell example:

```powershell
$env:GMAT = "C:\Users\<username>\Apps\GMAT-R2026a"
```

For a persistent setup, add `GMAT` through your operating system's environment variable settings.

The generated runner prints the GMAT path it is using:

```text
Running GMAT in <path-to-GMAT>
```

If GMAT cannot be loaded, first confirm:

- `GMAT` points at the GMAT root, not a generated AMAT directory.
- The GMAT Python interface works in the same Python environment used for AMAT.
- `gmatpyplus` is installed in that environment.

## Verify the install

After installation and GMAT setup, run the test suite:

```bash
python -m pytest
```

Then do a minimal compile check from the project root:

```bash
python -m mission_compiler validate examples/elliptical_LEO_to_GEO/mission_spec.json
python -m mission_compiler compile examples/elliptical_LEO_to_GEO/mission_spec.json --out generated/elliptical_LEO_to_GEO/simulation
```

At this point AMAT is installed and can generate mission artifacts. To confirm the full GMAT-backed path, run the generated mission and render the visualization:

```bash
python generated/elliptical_LEO_to_GEO/simulation/generated_mission.py --run
python -m mission_visualizer view --mission-dir generated/elliptical_LEO_to_GEO/simulation
```

The viewer writes:

```text
generated/elliptical_LEO_to_GEO/simulation/visualization/trajectory.html
generated/elliptical_LEO_to_GEO/simulation/visualization/visualization_report.json
```

Open `trajectory.html` in a browser to inspect the result.

## Documentation

Use these documents for hands-on workflows and schema details:

- [docs/pipeline.md](docs/pipeline.md): targeting-first and simulation-first execution pipelines.
- [docs/mission_spec_reference.md](docs/mission_spec_reference.md): How to define the mission for the simulation layer. Includes `mission_spec.json` structure, supported sections, events, outputs, frames, and dependencies.
- [docs/targeting.md](docs/targeting.md): targeting-layer concepts, current boundaries, transfer conventions, and cislunar seeding.

Useful examples:

- `examples/elliptical_LEO_to_GEO/mission_spec.json`: Earth-orbit transfer example.
- `examples/elliptical_LEO_to_GEO/target_problem.json`: targeting-first Earth-orbit transfer seed.
- `examples/MEO_demo/mission_spec.json`: medium Earth orbit propagation example.
- `examples/cislunar_demo/mission_spec.json`: GMAT-backed cislunar demonstration with body ephemerides.

## Current Capabilities

AMAT currently only support GMAT as the simulation backend. Targeting and rendering are done natively, unless a high-fidelity simulation pass is needed. Please raise an issue to include other simulation or optimization backends. 

Spaceflight-related capabilities include but not limited to:

- Cartesian and Keplerian spacecraft initial states.
- Multi-phase mission sequences.
- Propagation, impulsive maneuvers, event actions, and checkpoints.
- GMAT point-mass and spherical-harmonic force model declarations.
- Multi-body gravities. 
- Simulation-coupled body ephemeris, with SPICE fallback when configured. 
- Interactive trajectory visualization. 

## Acknowledgement

AMAT was originally inspired by the GMAT Python wrapper `gmatpyplus` written by **weasdown**: 

```text
https://github.com/weasdown/gmatpyplus
```

Later, AMAT was ~~scope crept~~ expanded into a broader backend-agnostic framework for mission design and analysis. AMAT calls GMAT features through `gmatpyplus` and generates a separate `.script` file for human audit and review.

## AI Disclosure

This repository utilizes ChatGPT, and its derivative, Codex, for code generation, optimization, and documentation. All AI-generated code is thoroughly tested and vetted by human maintainers for quality, fidality, and consistency. 

## Development Status

AMAT is under active development. The core design goal is to keep mission intent, generated backend artifacts, simulation outputs, and visualization products explicit and inspectable. When behavior is ambiguous, GMAT propagation outputs and generated manifests are treated as the source of truth for downstream visualization.

# AMAT

AMAT is a mission simulation, targeting, optimization, and visualization workbench for spacecraft trajectory studies. It turns machine-readable mission descriptions into GMAT-backed simulations, collects repeatable artifacts, and renders interactive trajectory views for inspection.

## What AMAT Does

AMAT currently provides four cooperating layers:

- **Mission compilation**: validates a human- or machine-written `mission_spec.json`, canonicalizes it, and emits scripts and generated Python runners to operate other softwares.
- **Simulation execution**: runs generated missions and collects spacecraft and body ephemerides. User-defined checkpoints are available to sample spacecraft states at any point during flight. All outputs are saved under `generated/<mission_id>/`.
- **Targeting and optimization**: creates initial maneuver seeds for supported transfer problems and provides a swappable optimization layer, currently with GMAT as the first supported backend.
- **Visualization**: reads generated simulation artifacts and creates an interactive 3D HTML viewer with spacecraft trajectories, body ephemerides, checkpoints, ground tracks, and reference-frame context.

A typical workflow resembles:

```text
MissionSpec or TargetProblem
  1. AMAT validation/canonicalization
  2. generated script and Python runner
  3. Propagation
  4. output CSVs and manifests
  5. interactive visualization
```

## Installation

AMAT is a Python project. Install it from the repository root:

```bash
python -m pip install -e .[dev]
```

This installs the AMAT packages and development test dependency. The core dependencies include `gmatpyplus`, `spiceypy`, `numpy`, `pandas`, `jinja2`, `jsonschema`, and `plotly`.

Verify that the CLIs import:

```bash
python -m compiler --help
python -m targeter --help
python -m optimizer --help
python -m visualizer --help
```

Installed console entry points are also declared:

```bash
compiler --help
targeter --help
optimizer --help
visualizer --help
amat --help
```

Using `python -m ...` is preferred during development because it makes the active Python environment explicit.

## Backend setup

### GMAT - General Mission Analysis Tool

[GMAT](https://etd.gsfc.nasa.gov/capabilities/capabilities-listing/general-mission-analysis-tool-gmat/), or General Mission Analysis Tool, is a NASA open-source trajectory optimization and optimization software. It serves as one of AMAT's optional simulation backends. AMAT currently operates GMAT through the `gmatpyplus` wrapper, which expects a GMAT installation path. Set the `GMAT` environment variable to the GMAT root directory.

Windows PowerShell example:

```powershell
$env:GMAT = "$env:USERPROFILE\Apps\GMAT-R2026a"
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

After installation and simulation tool setup, run the test suite:

```bash
python -m pytest
```

Then do a minimal compile check from the project root:

```bash
python -m compiler validate examples/LEO_to_GEO/mission_spec.json
python -m compiler compile examples/LEO_to_GEO/mission_spec.json --out generated/LEO_to_GEO/simulation
```

At this point AMAT is installed and can generate mission artifacts. To confirm the full GMAT-backed path, run the generated mission and render the visualization:

```bash
python generated/LEO_to_GEO/simulation/generated_mission.py --run
python -m visualizer view --mission-dir generated/LEO_to_GEO/simulation
```

The viewer writes:

```text
generated/LEO_to_GEO/simulation/visualization/trajectory.html
generated/LEO_to_GEO/simulation/visualization/visualization_report.json
```

Open `trajectory.html` in a browser to inspect the result.

## Documentation

Use these documents for hands-on workflows and schema details:

- [docs/pipeline.md](docs/pipeline.md): targeting-first and simulation-first execution pipelines.
- [docs/mission_spec_reference.md](docs/mission_spec_reference.md): How to define the mission for the simulation layer. Includes `mission_spec.json` structure, supported sections, events, outputs, frames, and dependencies.
- [docs/targeting.md](docs/targeting.md): targeting-layer concepts, current boundaries, transfer conventions, and cislunar seeding.

Useful examples:

- `examples/LEO_to_GEO/mission_spec.json`: Earth-orbit transfer example.
- `examples/LEO_to_GEO/target_problem.json`: targeting-first Earth-orbit transfer seed.
- `examples/MEO_demo/mission_spec.json`: medium Earth orbit propagation example.
- `examples/cislunar_demo/mission_spec.json`: GMAT-backed cislunar demonstration with body ephemerides.

## Current Capabilities

AMAT currently only support GMAT as the simulation backend. Targeting and rendering are done natively, unless a high-fidelity simulation pass is needed. Please raise an [issue](https://github.com/ThisisShoo/AMAT/issues) to include other simulation or optimization backends. 

Spaceflight-related capabilities include but not limited to:

- Body-agnostic cartesian and Keplerian spacecraft states
- Multi-phase mission sequences combining propagation, impulsive maneuvers, event actions, and checkpoints.
- GMAT point-mass and spherical-harmonic force model declarations.
- Multi-body gravities. 
- Simulation-coupled body ephemeris, with SPICE fallback when configured. 
- HTML-based interactive trajectory visualization with backend-defined frames. 

## Development Roadmap (in order of priority)*

- Finite burn compatibility 
- Orekit integration
- Multi-spacecraft missions
- Human-agent-AMAT interfaces
- Persistent UI
- ... (TBD)

*List subject to change based on user feedbacks and development status.*

<!-- ## Acknowledgement

AMAT grew out of my earlier research project, the [GMAT Monte Carlo Propagator](https://github.com/ThisisShoo/GMAT-Monte-Carlo-Propagator), which automated Monte Carlo simulations using GMAT as the physics backend.

The direct spark for AMAT came from a message I received from [**weasdown**](https://github.com/weasdown) about an update to his GMAT wrapper. That message prompted me to revisit the broader problem of building reliable, programmable interfaces around GMAT, and ultimately led to the development of AMAT.

This project would not have come to fruition without **weasdown**'s dedication to the GMAT community and his work making GMAT more accessible. I am deeply grateful for his contributions and for the inspiration they provided.  -->


## AI Disclosure

This repository utilizes ChatGPT, and its derivative, Codex, for code generation, optimization, and documentation. All AI-generated content is thoroughly tested and reviewed by a combination of cross-agent, inter-model, and human-led review processes for quality, fidality, and consistency. 

## Author

* **Shuhan Zheng** - Initial work / lead developer - [thisisshoo](https://github.com/ThisisShoo)

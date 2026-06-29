# AMAT

AMAT is a mission simulation, targeting, optimization, and visualization workbench for spacecraft trajectory studies. It turns machine-readable mission descriptions into backend-generated simulations, collects repeatable artifacts, and renders interactive trajectory views for inspection.

## What AMAT Does

AMAT provides four cooperating layers:

- **Mission compilation**: validates a human- or machine-written MissionSpec, canonicalizes it, and emits backend scripts and generated Python runners.
- **Simulation execution**: runs generated missions and collects spacecraft and body ephemerides. User-defined checkpoints are available to sample spacecraft states at any point during flight. All outputs are saved under `generated/<mission_id>/`.
- **Targeting and optimization**: creates initial maneuver seeds for supported transfer problems and provides swappable correction and optimization modules.
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

AMAT requires Python 3.10 or newer. Install it from the repository root:

```bash
python -m pip install -e .[dev]
```

This installs the AMAT packages and development test dependency. The core dependencies include `gmatpyplus`, `spiceypy`, `numpy`, `pandas`, `jinja2`, `jsonschema`, and `plotly`.

For the Orekit backend, install the optional extra:

```bash
python -m pip install -e .[dev,orekit]
```

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

[GMAT](https://etd.gsfc.nasa.gov/capabilities/capabilities-listing/general-mission-analysis-tool-gmat/), or General Mission Analysis Tool, is a NASA open-source trajectory design and analysis application. It serves as AMAT's primary high-fidelity simulation backend. AMAT operates GMAT through the `gmatpyplus` wrapper, which expects a GMAT installation path. Set the `GMAT` environment variable to the GMAT root directory.

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

### Orekit JPype

Orekit is available as a simulation backend through `orekit-jpype`. It is useful for portable propagation, selected numerical force-model propagation, Orekit-backed targeter acceptance runs, and backend-swapping tests. Install AMAT with the `orekit` extra, make sure a Java runtime is available, and set `OREKIT_DATA_PATH` to an Orekit data directory:

```powershell
$env:OREKIT_DATA_PATH = "D:\path\to\orekit-data"
```

If Java is not on `PATH`, set `JAVA_HOME` and prepend its `bin` directory before running an Orekit mission:

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-25.0.3.9-hotspot"
$env:Path = "$env:JAVA_HOME\bin;$env:Path"
```

Orekit-backed spaceflight support in AMAT:

- Cartesian and Keplerian spacecraft initial states.
- Built-in point-mass central gravity for Sun, Mercury, Venus, Earth, Luna/Moon, Mars, Jupiter, Saturn, Uranus, Neptune, and Pluto.
- Two-body propagation with Orekit `KeplerianPropagator`.
- Numerical propagation for declared spherical-harmonic gravity, third-body/point-mass perturbing bodies, Harris-Priester drag, solar radiation pressure, relativity, and Earth tides when the local Orekit data set and spacecraft properties support them.
- GMAT-style body-centered inertial/fixed frame names for supported major bodies, using Orekit-native frames or validated adapter fallbacks.
- Topocentric station frames and local orbital maneuver frames where supported by the adapter.
- Mission sequence steps: elapsed-time propagation, checkpoints, direct impulsive/finite maneuvers, per-segment propagator context, and event actions.
- Events: elapsed seconds/date, true anomaly, argument of latitude, periapsis, apoapsis, node-crossing, distance threshold, SOI crossing, elevation, and eclipse-style timing.
- Impulsive maneuvers in `VNB`, `LVLH`, `SpacecraftBody`, and supported inertial/fixed frames.
- Finite maneuvers as segmented thrust propagation in supported maneuver frames.
- Spacecraft ephemeris CSV, checkpoint CSV, final-state CSV, body ephemeris CSV for built-in bodies, and ground-track CSV from surface-fixed spacecraft states.
- Validated fallback output frames, including body-fixed spacecraft ephemeris output for supported major bodies.
- Keplerian columns in output CSVs for target evaluation.
- Targeter closed-loop compatibility through finite-difference STM assessment artifacts synthesized from Orekit perturbation runs and the explicit `orekit_fd` correction backend.

Orekit backend limitations:

- Finite maneuvers are available as segmented thrust propagation; they are not coupled into a full high-fidelity numerical force model with propellant mass depletion.
- Object-referenced/two-body rotating frames remain GMAT-authoritative.
- No native Orekit variational-equation STM yet; Orekit correction currently uses finite differences.
- No arbitrary frame transformation; output fallback frames must be explicitly supported by the adapter.
- Custom/non-built-in body ephemerides require configured SPICE fallback or another backend.
- Orekit is a swappable backend for supported workflows, not a full replacement for GMAT.

## Verify the install

After installation and simulation tool setup, run the test suite:

```bash
python -m pytest
```

Then run the targeting-first LEO-to-GEO example from the project root:

```bash
python -m targeter solve examples/LEO_to_GEO/target_problem.json --out generated/LEO_to_GEO/targeting
type generated/LEO_to_GEO/targeting/maneuver_plan.json
python -m compiler validate generated/LEO_to_GEO/targeting/candidate_mission_spec.json
python -m compiler compile generated/LEO_to_GEO/targeting/candidate_mission_spec.json --backend gmat --out generated/LEO_to_GEO/simulation
```

Use `--artifact-profile debug` with `targeter solve` or `compiler compile` when you want expanded audit and diagnostic files.

At this point AMAT is installed and can generate mission artifacts. To confirm a complete backend run, acceptance evaluation, and render path:

```bash
python generated/LEO_to_GEO/simulation/generated_mission.py --run
python -m targeter evaluate examples/LEO_to_GEO/target_problem.json --simulation-dir generated/LEO_to_GEO/simulation --out generated/LEO_to_GEO/targeting
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
- [docs/mission_spec_reference.md](docs/mission_spec_reference.md): How to define the mission for the simulation layer. Includes `mission_spec.json` structure, supported sections, event detectors, outputs, frames, and dependencies.
- [docs/targeting.md](docs/targeting.md): targeting-layer concepts, supported boundaries, transfer conventions, and cislunar seeding.

Useful examples:

- `examples/LEO_to_GEO/target_problem.json`: targeting-first Earth-orbit transfer seed.
- `examples/LEO_to_GEO_orekit/target_problem.json`: Orekit-oriented targeting-first counterpart.
- `examples/phasing_example/target_problem.json`: phase-targeting problem setup.

## Capability Summary

AMAT supports GMAT as the primary simulation backend and Orekit as a swappable backend for supported workflows. Targeting and rendering are native AMAT layers unless a simulation-backed acceptance or correction pass is requested.

Spaceflight-related capabilities include but not limited to:

- Body-agnostic Cartesian and Keplerian spacecraft states.
- Multi-phase mission sequences combining propagation, impulsive maneuvers, event actions, and checkpoints.
- GMAT point-mass and spherical-harmonic force model declarations.
- GMAT multi-body gravity declarations.
- Orekit two-body propagation and selected numerical force-model propagation for supported built-in central bodies.
- Orekit finite-difference STM assessment artifacts and `orekit_fd` correction backend for targeter closed-loop correction.
- Simulation-coupled body ephemeris, with SPICE fallback when configured.
- HTML-based interactive trajectory visualization with backend-defined frames.

The detailed backend capability matrix lives in [docs/mission_spec_reference.md](docs/mission_spec_reference.md).

<!-- ## Acknowledgement

AMAT grew out of my earlier research project, the [GMAT Monte Carlo Propagator](https://github.com/ThisisShoo/GMAT-Monte-Carlo-Propagator), which automated Monte Carlo simulations using GMAT as the physics backend.

The direct spark for AMAT came from a message I received from [**weasdown**](https://github.com/weasdown) about an update to his GMAT wrapper. That message prompted me to revisit the broader problem of building reliable, programmable interfaces around GMAT, and ultimately led to the development of AMAT.

This project would not have come to fruition without **weasdown**'s dedication to the GMAT community and his work making GMAT more accessible. I am deeply grateful for his contributions and for the inspiration they provided.  -->


## AI Disclosure

This repository utilizes ChatGPT, and its derivative, Codex, for code generation, optimization, and documentation. All AI-generated content is thoroughly tested and reviewed by a combination of cross-agent, inter-model, and human-led review processes for quality, fidality, and consistency. 

## Author

* **Shuhan Zheng** - Initial work / lead developer - [thisisshoo](https://github.com/ThisisShoo)

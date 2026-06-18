# AMAT Targeting

AMAT's targeting layer turns a semantic `target_problem.json` into targeting artifacts and a concrete MissionSpec that the simulation layer can compile and run.

Targeting is intentionally separate from simulation. The targeting layer can generate an analytic seed and a MissionSpec handoff, but GMAT execution and final verification happen downstream through the normal simulation pipeline.

## Layer Boundary

```text
TargetProblem
  -> validation and canonicalization
  -> targeting formulation
  -> analytic initial candidate
  -> MissionSpec materialization
  -> GMAT simulation
  -> simulation evaluation
```

A successful targeting solve means AMAT produced a structurally valid initial candidate. It does not by itself prove that GMAT propagation will meet every requirement.

## Current Scope

The current targeting implementation supports selected impulsive transfer seeds:

- Earth-centered Keplerian initial states.
- GEO and GEO-like circular target orbits.
- Circular coplanar Hohmann-style transfers.
- Generalized apsidal transfer seeds.
- Node-aware impulsive plane-change placement.
- Ephemeris-aware conic-chain Lambert seeding from GMAT-reported body ephemerides.
- Closed-loop STM correction hooks that re-evaluate after each applied correction.
- MissionSpec materialization for downstream simulation.
- Simulation evaluation against completed GMAT outputs.

It does not yet provide a general global optimizer, trajectory architecture synthesis, free-return design, low-thrust transcription, or estimation.

## TargetProblem Concepts

`target_problem.json` records what must be achieved and what controls targeting may change. Solver-specific tuning belongs outside the problem definition.

Important sections include:

- `architecture_ref`: the selected transfer architecture or mission-design family.
- `initial_state`: the spacecraft state, body, frame, epoch, representation, values, and units.
- `allowed_controls`: physical controls that a later formulation may vary.
- `metrics`: backend-neutral quantities such as `spacecraft.final.orbit.sma`.
- `constraints`: endpoint, path, variable-bound, event, or operational requirements.
- `limits`: mission-wide limits such as maximum total delta-v or elapsed time.
- `fidelity_policy`: intended targeting and acceptance models.
- `verification_policy`: required independence level for acceptance.

Semantic metric IDs are intentionally not GMAT column names. The evaluation layer maps public metrics onto generated output files after simulation.

## Commands

Validate a target problem:

```bash
python -m mission_targeting validate examples/elliptical_LEO_to_GEO/target_problem.json
```

Solve for an initial candidate:

```bash
python -m mission_targeting solve examples/elliptical_LEO_to_GEO/target_problem.json \
  --out generated/elliptical_LEO_to_GEO/targeting
```

Compile the materialized MissionSpec:

```bash
python -m mission_compiler compile generated/elliptical_LEO_to_GEO/targeting/candidate_mission_spec.json \
  --out generated/elliptical_LEO_to_GEO/simulation
```

Run GMAT:

```bash
python generated/elliptical_LEO_to_GEO/simulation/generated_mission.py --run
```

Evaluate the simulation result:

```bash
python -m mission_targeting evaluate examples/elliptical_LEO_to_GEO/target_problem.json \
  --simulation-dir generated/elliptical_LEO_to_GEO/simulation \
  --out generated/elliptical_LEO_to_GEO/targeting
```

For the complete end-to-end workflow, see [pipeline.md](pipeline.md).

## Targeting Outputs

`solve` writes targeting artifacts such as:

```text
generated/<mission_id>/targeting/
  target_problem.canonical.json
  targeting_formulation.json
  initial_candidate.json
  targeting_result.json
  candidate_mission_spec.json
  acceptance_result.json
  provenance.json
```

`evaluate` consumes completed simulation outputs and adds:

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

Backend adapters render those values only when generating backend artifacts. For GMAT, AMAT converts the canonical epoch into GMAT's UTCGregorian form, for example:

```text
2026-01-01T00:00:00.000Z
  -> 01 Jan 2026 00:00:00.000
```

This keeps TargetProblem and MissionSpec files backend-neutral.

## Transfer Strategy Terms

AMAT uses `transfer_strategy` for a selected mission-design method such as:

- Hohmann transfer.
- Generalized two-impulse apsidal transfer.
- Bi-elliptic transfer.
- Lambert transfer.
- Patched-conic transfer.
- Multiple-shooting transfer.
- Low-thrust transcription.

`trajectory architecture` refers to the larger topology made of phases, encounters, legs, nodes, and maneuver opportunities.

## Plane-Change Policy

For impulsive non-coplanar transfers, AMAT's default policy is `valid_node_low_speed`.

The policy is:

- Plane-change work must occur on a valid intersection line between the current and target orbital planes unless a later high-fidelity correction layer explicitly owns the miss.
- If timing is flexible and the departure orbit is circular enough for the analytic model, AMAT may wait in the departure orbit so the transfer arrival apsis lies on that node line.
- AMAT prefers low-speed opportunities, so an aligned arrival apsis can merge circularization and plane correction.
- AMAT does not force concurrent burns. It merges effects only when the valid node and energy-change opportunity coincide within `merge_maneuver_angle_tolerance_deg`.
- If apsis alignment is unavailable, AMAT falls back to a separate plane-change maneuver at the nearest valid node on the transfer arc.

The structured form is:

```json
"plane_change_policy": {
  "type": "valid_node_low_speed",
  "allow_departure_phasing": true,
  "prefer_apsis_alignment": true,
  "fallback": "split_at_nearest_valid_node"
}
```

Legacy policy names such as `node_near_apoapsis`, `concurrent_minimum_delta_v`, `arrival_only`, and `departure_only` remain accepted for compatibility. `node_near_apoapsis` preserves the older behavior: it does not phase the departure orbit, and it places a separate plane-change maneuver at the valid node closest to the transfer arrival apsis when the node does not coincide with an energy burn.

## Cross-SOI Conic Chains

Cross-SOI seeds live in `mission_targeting/conic_chain.py`. A conic chain is an ordered sequence of up to three connecting patched conics. That is enough for planet-to-moon, moon-to-planet, and interplanetary-style chains with an intermediate encounter leg while keeping the analytic seed separate from the later correction pass.

The seed layer uses resolved body ephemerides as input to Lambert helpers. This keeps targeting, propagation, and visualization aligned to the same body phases when those ephemerides come from the GMAT simulation layer.

`mission_targeting/cislunar.py` remains a cislunar MissionSpec compatibility wrapper. Generic cross-SOI seed concepts belong in `conic_chain.py`.

## STM Closed Loop

The correction strategy is:

1. Generate a patched-conics or conic-chain seed.
2. Optionally refine the SOI/hyperbola handoff.
3. Run the high-fidelity simulation/evaluation layer.
4. Use STM artifacts to compute a correction.
5. Apply the correction and evaluate again until the residual meets tolerance or the iteration limit is reached.

The closed-loop runner is backend-neutral. In production, its evaluator can compile/run GMAT and read final-state plus STM artifacts; in tests, the same loop can use pure Python models.

## Cislunar Compatibility Command

The cislunar command uses GMAT's resolved Luna ephemeris as input to the conic-chain Lambert helper, then writes the existing demo MissionSpec shape.

The command shape is:

```bash
python -m mission_targeting cislunar-seed examples/cislunar_demo/mission_spec.json \
  --body-ephemeris generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Luna_EarthMJ2000Eq.csv \
  --out examples/cislunar_demo/mission_spec.json \
  --seed-out generated/cislunar_demo/targeting/cislunar_lambert_seed.json
```

Use this after an initial GMAT run has produced the body ephemeris file. The generated seed JSON records the selected Luna sample, TLI magnitude, and arrival v-infinity.

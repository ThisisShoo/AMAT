from __future__ import annotations
import hashlib, json, platform
from pathlib import Path
from typing import Any
from mission_targeting.artifacts import build_targeting_result
from mission_targeting.domain import canonicalize_target_problem, validate_target_problem
from mission_targeting.evaluation import not_run_acceptance
from mission_targeting.formulation import build_targeting_formulation
from mission_targeting.initial_guess import generate_hohmann_candidate
from mission_targeting.io import read_json, write_json
from mission_targeting.materialization import materialize_mission_spec

def _hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def validate_file(path: str | Path) -> dict[str, Any]:
    raw = read_json(path); warnings = validate_target_problem(raw); p = canonicalize_target_problem(raw)
    return {"ok": True, "status": "valid", "problem_id": p["problem_id"], "mission_id": p["mission_id"], "transfer_strategy": p["transfer_strategy"]["type"], "warnings": warnings}

def canonicalize_file(path: str | Path, out: str | Path) -> dict[str, Any]:
    p = canonicalize_target_problem(read_json(path)); write_json(out, p)
    return {"ok": True, "status": "canonicalized", "problem_id": p["problem_id"], "artifact": str(out)}

def solve_file(path: str | Path, out_dir: str | Path) -> dict[str, Any]:
    raw = read_json(path); warnings = validate_target_problem(raw); p = canonicalize_target_problem(raw)
    formulation = build_targeting_formulation(p); candidate = generate_hohmann_candidate(p)
    mission_spec = materialize_mission_spec(p, candidate); result = build_targeting_result(p, formulation, candidate)
    acceptance = not_run_acceptance(p, candidate)
    out = Path(out_dir)
    write_json(out/"target_problem.canonical.json", p); write_json(out/"targeting_formulation.json", formulation)
    write_json(out/"initial_candidate.json", candidate); write_json(out/"targeting_result.json", result)
    write_json(out/"candidate_mission_spec.json", mission_spec); write_json(out/"acceptance_result.json", acceptance)
    provenance = {"schema_version": "1.0.0", "problem_hash": _hash(p), "formulation_hash": _hash(formulation), "candidate_hash": _hash(candidate), "mission_spec_hash": _hash(mission_spec), "python_version": platform.python_version(), "warnings": warnings}
    write_json(out/"provenance.json", provenance)
    return {"ok": result["summary_status"] == "analytically_feasible", "status": result["summary_status"], "problem_id": p["problem_id"], "total_delta_v_km_s": candidate["analytic_assessment"]["total_delta_v_km_s"], "time_of_flight_s": candidate["variable_values"]["transfer.coast_time"]["value"], "artifacts": {name: str(out/name) for name in ["target_problem.canonical.json","targeting_formulation.json","initial_candidate.json","targeting_result.json","candidate_mission_spec.json","acceptance_result.json","provenance.json"]}}

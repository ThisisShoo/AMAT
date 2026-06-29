from __future__ import annotations
import argparse, json
from targeter.errors import TargetingError
from targeter.evaluation import build_acceptance_result, evaluate_simulation
from targeter.io import read_json, write_json
from targeter.conic_chain import load_body_ephemeris_csv
from targeter.constants import get_body_constants
from targeter.execution import execute_closed_loop_file
from targeter.maneuver_planner.operations.body_transfer import plan_conic_chain_seed
from targeter.service import canonicalize_file, solve_file, validate_file

def _cli_result(result: dict) -> dict:
    hidden = {
        "target_problem",
        "targeting_formulation",
        "maneuver_plan",
        "candidate",
        "candidate_mission_spec",
        "targeting_result",
        "acceptance_result",
        "provenance",
    }
    return {key: value for key, value in result.items() if key not in hidden}

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m targeter")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("target_problem")
    c = sub.add_parser("canonicalize"); c.add_argument("target_problem"); c.add_argument("--out", required=True)
    s = sub.add_parser("solve"); s.add_argument("target_problem"); s.add_argument("--out", default="generated/targeting"); s.add_argument("--artifact-profile", choices=["standard", "debug"], default="standard")
    e = sub.add_parser("evaluate"); e.add_argument("target_problem"); e.add_argument("--simulation-dir", required=True); e.add_argument("--out", default=None)
    cl = sub.add_parser("closed-loop", help="Run the modular targeting closed loop")
    cl.add_argument("target_problem")
    cl.add_argument("--out", default="generated/targeting")
    cl.add_argument("--simulation-backend", default=None)
    cl.add_argument("--correction-backend", default=None)
    cl.add_argument("--max-iterations", type=int, default=None)
    cl.add_argument("--run", action="store_true")
    cc = sub.add_parser("conic-chain-seed", help="Generate a cross-SOI conic-chain seed from a backend-produced body ephemeris CSV")
    cc.add_argument("--body-ephemeris", required=True)
    cc.add_argument("--seed-out", required=True)
    cc.add_argument("--body", default="Luna")
    cc.add_argument("--frame", default="EarthMJ2000Eq")
    cc.add_argument("--departure-body", default="Earth")
    cc.add_argument("--target-body", default=None)
    cc.add_argument("--central-body", default="Earth")
    cc.add_argument("--central-mu-km3-s2", type=float, default=None)
    cc.add_argument("--central-radius-km", type=float, default=None)
    cc.add_argument("--departure-altitude-km", type=float, default=300.0)
    cc.add_argument("--min-tof-s", type=float, default=2.5 * 86400.0)
    cc.add_argument("--max-tof-s", type=float, default=7.0 * 86400.0)
    cc.add_argument("--phase-samples", type=int, default=96)
    args = parser.parse_args(argv)
    try:
        if args.cmd == "validate":
            result = validate_file(args.target_problem)
        elif args.cmd == "canonicalize":
            result = canonicalize_file(args.target_problem, args.out)
        elif args.cmd == "solve":
            result = solve_file(args.target_problem, args.out, artifact_profile=args.artifact_profile)
        elif args.cmd == "evaluate":
            problem = read_json(args.target_problem)
            evaluation = evaluate_simulation(problem, args.simulation_dir)
            acceptance = build_acceptance_result(problem, evaluation)
            result = {
                "ok": evaluation["evaluation_status"] == "passed",
                "status": evaluation["evaluation_status"],
                "problem_id": evaluation["problem_id"],
                "mission_id": evaluation["mission_id"],
                "simulation_evaluation": evaluation,
                "acceptance_result": acceptance,
            }
            if args.out:
                write_json(f"{args.out}/simulation_evaluation.json", evaluation)
                write_json(f"{args.out}/acceptance_result.json", acceptance)
                result["artifacts"] = {
                    "simulation_evaluation": f"{args.out}/simulation_evaluation.json",
                    "acceptance_result": f"{args.out}/acceptance_result.json",
                }
        elif args.cmd == "closed-loop":
            result = execute_closed_loop_file(
                args.target_problem,
                args.out,
                simulation_backend=args.simulation_backend,
                correction_backend=args.correction_backend,
                run=args.run,
                max_iterations=args.max_iterations,
            )
        else:
            body_constants = get_body_constants(args.central_body)
            central_mu = args.central_mu_km3_s2 or (body_constants.mu_km3_s2 if body_constants else None)
            central_radius = args.central_radius_km or (body_constants.radius_km if body_constants else None)
            if central_mu is None or central_radius is None:
                raise ValueError("custom central body conic-chain seeds require --central-mu-km3-s2 and --central-radius-km")
            samples = load_body_ephemeris_csv(args.body_ephemeris, body=args.body, frame=args.frame)
            seed = plan_conic_chain_seed(
                samples,
                departure_body=args.departure_body,
                target_body=args.target_body or args.body,
                central_body=args.central_body,
                leo_altitude_km=args.departure_altitude_km,
                central_mu_km3_s2=central_mu,
                central_radius_km=central_radius,
                min_tof_s=args.min_tof_s,
                max_tof_s=args.max_tof_s,
                departure_phase_samples=args.phase_samples,
            )
            write_json(args.seed_out, seed.to_dict())
            first_leg = seed.first_leg
            result = {
                "ok": True,
                "status": "completed",
                "legs": len(seed.legs),
                "target_elapsed_s": first_leg.target.elapsed_s,
                "departure_delta_v_magnitude_km_s": sum(x * x for x in first_leg.departure_delta_v_km_s) ** 0.5,
                "arrival_v_inf_magnitude_km_s": sum(x * x for x in first_leg.arrival_v_inf_km_s) ** 0.5,
                "artifacts": {"seed": args.seed_out},
            }
    except (TargetingError, OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "status": "invalid_problem", "error": str(exc)}, indent=2, sort_keys=True)); return 1
    print(json.dumps(_cli_result(result), indent=2, sort_keys=True)); return 0 if result.get("ok", True) else 1


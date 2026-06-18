from __future__ import annotations
import argparse, json
from mission_targeting.errors import TargetingError
from mission_targeting.evaluation import build_acceptance_result, evaluate_simulation
from mission_targeting.io import read_json, write_json
from mission_targeting.service import canonicalize_file, solve_file, validate_file
from mission_targeting.cislunar import load_gmat_body_ephemeris_csv, retarget_cislunar_mission_spec, solve_ephemeris_lambert_seed
from mission_targeting.conic_chain import solve_single_leg_ephemeris_lambert_seed

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mission_targeting")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("target_problem")
    c = sub.add_parser("canonicalize"); c.add_argument("target_problem"); c.add_argument("--out", required=True)
    s = sub.add_parser("solve"); s.add_argument("target_problem"); s.add_argument("--out", default="generated/targeting")
    e = sub.add_parser("evaluate"); e.add_argument("target_problem"); e.add_argument("--simulation-dir", required=True); e.add_argument("--out", default=None)
    cs = sub.add_parser("cislunar-seed", help="Retarget a cislunar MissionSpec from a GMAT body ephemeris CSV")
    cs.add_argument("mission_spec")
    cs.add_argument("--body-ephemeris", required=True)
    cs.add_argument("--out", required=True)
    cs.add_argument("--seed-out", default=None)
    cs.add_argument("--min-tof-s", type=float, default=2.5 * 86400.0)
    cs.add_argument("--max-tof-s", type=float, default=7.0 * 86400.0)
    cs.add_argument("--phase-samples", type=int, default=96)
    cc = sub.add_parser("conic-chain-seed", help="Generate a cross-SOI conic-chain seed from a GMAT body ephemeris CSV")
    cc.add_argument("--body-ephemeris", required=True)
    cc.add_argument("--seed-out", required=True)
    cc.add_argument("--body", default="Luna")
    cc.add_argument("--frame", default="EarthMJ2000Eq")
    cc.add_argument("--departure-body", default="Earth")
    cc.add_argument("--target-body", default=None)
    cc.add_argument("--central-body", default="Earth")
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
            result = solve_file(args.target_problem, args.out)
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
        elif args.cmd == "cislunar-seed":
            spec = read_json(args.mission_spec)
            samples = load_gmat_body_ephemeris_csv(args.body_ephemeris, body="Luna", frame="EarthMJ2000Eq")
            seed = solve_ephemeris_lambert_seed(
                samples,
                min_tof_s=args.min_tof_s,
                max_tof_s=args.max_tof_s,
                departure_phase_samples=args.phase_samples,
            )
            retargeted = retarget_cislunar_mission_spec(spec, seed)
            write_json(args.out, retargeted)
            artifacts = {"mission_spec": args.out}
            if args.seed_out:
                write_json(args.seed_out, seed.to_dict())
                artifacts["seed"] = args.seed_out
            result = {
                "ok": True,
                "status": "completed",
                "mission_id": retargeted.get("mission_id"),
                "target_elapsed_s": seed.target_elapsed_s,
                "tli_delta_v_magnitude_km_s": seed.tli_delta_v_magnitude_km_s,
                "arrival_v_inf_magnitude_km_s": seed.arrival_v_inf_magnitude_km_s,
                "artifacts": artifacts,
            }
        else:
            samples = load_gmat_body_ephemeris_csv(args.body_ephemeris, body=args.body, frame=args.frame)
            seed = solve_single_leg_ephemeris_lambert_seed(
                samples,
                departure_body=args.departure_body,
                target_body=args.target_body or args.body,
                central_body=args.central_body,
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
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result.get("ok", True) else 1

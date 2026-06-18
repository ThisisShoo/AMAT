from __future__ import annotations

import argparse
import json

from .errors import OptimizationError
from .service import solve_file, validate_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mission_optimization")
    sub = parser.add_subparsers(dest="cmd", required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("optimization_problem")

    solve = sub.add_parser("solve")
    solve.add_argument("optimization_problem")
    solve.add_argument("--out", default="generated/optimization")
    solve.add_argument("--run", action="store_true", help="Run the compiled backend simulation for the candidate")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "validate":
            result = validate_file(args.optimization_problem)
        else:
            result = solve_file(args.optimization_problem, args.out, run=args.run)
    except (OptimizationError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "status": "invalid_problem", "error": str(exc)}, indent=2, sort_keys=True))
        return 1

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok", True) else 1

from __future__ import annotations

import argparse
import json
from pathlib import Path

from compiler.artifacts.bundle import compile_bundle, validate_mission
from compiler.io import read_json
from compiler.ir.canonicalize import canonicalize
from compiler.runtime.run_python import run_generated_python
from compiler.dependencies.spice import write_spice_requests, resolve_spice_request
from compiler.io import write_json
from compiler.visualization import export_visualization_artifacts


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        import sys
        argv = sys.argv[1:]
    if argv and argv[0] == "target":
        from targeter.cli import main as targeting_main
        return targeting_main(argv[1:])
    if argv and argv[0] in {"optimize", "optimization"}:
        from optimizer.cli import main as optimization_main
        return optimization_main(argv[1:])
    parser = argparse.ArgumentParser(prog="python -m compiler")
    sub = parser.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="Validate a MissionSpec")
    v.add_argument("mission_spec")
    v.add_argument("--backend", default="gmat")

    c = sub.add_parser("compile", help="Compile a MissionSpec into GMAT demo artifacts")
    c.add_argument("mission_spec")
    c.add_argument("--backend", default="gmat")
    c.add_argument("--out", default="generated/mission")

    r = sub.add_parser("run-python", help="Run a generated gmatpyplus Python mission directly, without loading a .script")
    r.add_argument("script_path")
    r.add_argument("--save-script", action="store_true", help="Also write/update generated_mission.script before running")
    r.add_argument("--timeout", type=int, default=300)

    sr = sub.add_parser("spice-requests", help="Generate SPICE ephemeris request artifacts from a MissionSpec")
    sr.add_argument("mission_spec")
    sr.add_argument("--out", default="generated/mission")

    rs = sub.add_parser("resolve-spice", help="Resolve a SPICE request JSON file using spiceypy, if installed")
    rs.add_argument("request_file")
    rs.add_argument("--request-id", default=None)
    rs.add_argument("--out", default=None)

    ev = sub.add_parser("export-visualization", help="Export viewer-facing body ephemerides, clean CSVs, and visualization_manifest.json")
    ev.add_argument("mission_dir")

    args = parser.parse_args(argv)

    if args.cmd == "validate":
        spec = canonicalize(read_json(args.mission_spec))
        report = validate_mission(spec, args.backend)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] != "failed" else 1

    if args.cmd == "compile":
        result = compile_bundle(args.mission_spec, Path(args.out), args.backend)
        print(json.dumps(result["compile_result"], indent=2, sort_keys=True))
        return 0 if result["compile_result"]["status"] != "failed" else 1

    if args.cmd == "run-python":
        result = run_generated_python(args.script_path, save_script=args.save_script, timeout_s=args.timeout)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["ok"] else 1

    if args.cmd == "spice-requests":
        spec = canonicalize(read_json(args.mission_spec))
        requests = write_spice_requests(spec, Path(args.out))
        result = {"mission_id": spec["mission_id"], "count": len(requests), "path": str(Path(args.out) / "dependencies" / "spice_requests.json")}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    if args.cmd == "resolve-spice":
        payload = read_json(args.request_file)
        requests = payload.get("requests") if isinstance(payload, dict) else None
        if requests is None:
            requests = [payload]
        selected = None
        for req in requests:
            if args.request_id is None or req.get("request_id") == args.request_id or req.get("dependency_id") == args.request_id:
                selected = req
                break
        if selected is None:
            print(json.dumps({"ok": False, "error": "No matching SPICE request found"}, indent=2))
            return 1
        out = args.out or selected.get("output", {}).get("path") or f"{selected.get('dependency_id', 'spice')}_ephemeris.json"
        result = resolve_spice_request(selected, out)
        print(json.dumps({"ok": True, "path": out, "states": len(result.get("states", []))}, indent=2, sort_keys=True))
        return 0

    if args.cmd == "export-visualization":
        result = export_visualization_artifacts(Path(args.mission_dir))
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())


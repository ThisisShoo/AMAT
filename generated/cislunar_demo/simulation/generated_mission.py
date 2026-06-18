"""
Generated GMAT/gmatpyplus mission script.

Source MissionSpec: cislunar_demo

Normal operation is controlled by mission_spec.json.  Terminal flags are only
for troubleshooting/export.  If mission_spec.json requests full ephemeris or
checkpoints, this script runs the generated GMAT script through GMAT's native
LoadScript/RunScript path so ReportFile output is handled by GMAT itself.
"""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import gmatpyplus as gp
except Exception as exc:  # pragma: no cover - generated runtime guard
    raise RuntimeError("GMAT/gmatpyplus is required to run this generated script") from exc

MISSION_ID = "cislunar_demo"
ROOT = Path(__file__).resolve().parent

def _ensure_project_import_path() -> None:
    """Allow generated scripts in generated/<mission_id>/ to import mission_compiler.

    Users normally run this file directly, e.g.
    python generated/event_test/generated_mission.py --run. In that mode
    Python places generated/event_test on sys.path, not necessarily the AMAT
    project root. Add the nearest parent containing mission_compiler so
    automatic visualization export can run without requiring pip install -e .
    """
    candidates = [ROOT, *ROOT.parents, Path.cwd(), *Path.cwd().parents]
    for candidate in candidates:
        if (candidate / "mission_compiler").is_dir():
            text = str(candidate)
            if text not in sys.path:
                sys.path.insert(0, text)
            return

_ensure_project_import_path()
OUTPUT_DIR = ROOT / "outputs"
SCRIPT_PATH = ROOT / "generated_mission.script"
REQUIRES_SCRIPT_REPLAY = True
VISUALIZATION_ENABLED = True
VISUALIZATION_AUTO_EXPORT_AFTER_RUN = True
EXPECTED_OUTPUTS = [
    str(ROOT / "outputs/_Ephemeris_CislunarSat_EarthMJ2000Eq.csv"),
    str(ROOT / "outputs/_Ephemeris_CislunarSat_LunaMJ2000Eq.csv"),
    str(ROOT / "outputs/_Ephemeris_CislunarSat_EarthLunaRotating.csv"),
    str(ROOT / "outputs/_Ephemeris_CislunarSat_LunaEarthRotating.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Luna_EarthMJ2000Eq.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Sun_EarthMJ2000Eq.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Earth_LunaMJ2000Eq.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Sun_LunaMJ2000Eq.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Sun_EarthLunaRotating.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Luna_EarthLunaRotating.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Earth_LunaEarthRotating.csv"),
    str(ROOT / "outputs/_BodyEphemeris_Sun_LunaEarthRotating.csv"),
    str(ROOT / "outputs/post_tli.csv"),
    str(ROOT / "outputs/post_loi.csv"),
]
REPORT_COPIES = [
    {"source_filename": "_Ephemeris_CislunarSat_EarthMJ2000Eq.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_Ephemeris_CislunarSat_EarthMJ2000Eq.csv"},
    {"source_filename": "_Ephemeris_CislunarSat_LunaMJ2000Eq.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_Ephemeris_CislunarSat_LunaMJ2000Eq.csv"},
    {"source_filename": "_Ephemeris_CislunarSat_EarthLunaRotating.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_Ephemeris_CislunarSat_EarthLunaRotating.csv"},
    {"source_filename": "_Ephemeris_CislunarSat_LunaEarthRotating.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_Ephemeris_CislunarSat_LunaEarthRotating.csv"},
    {"source_filename": "_BodyEphemeris_Luna_EarthMJ2000Eq.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Luna_EarthMJ2000Eq.csv"},
    {"source_filename": "_BodyEphemeris_Sun_EarthMJ2000Eq.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Sun_EarthMJ2000Eq.csv"},
    {"source_filename": "_BodyEphemeris_Earth_LunaMJ2000Eq.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Earth_LunaMJ2000Eq.csv"},
    {"source_filename": "_BodyEphemeris_Sun_LunaMJ2000Eq.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Sun_LunaMJ2000Eq.csv"},
    {"source_filename": "_BodyEphemeris_Sun_EarthLunaRotating.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Sun_EarthLunaRotating.csv"},
    {"source_filename": "_BodyEphemeris_Luna_EarthLunaRotating.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Luna_EarthLunaRotating.csv"},
    {"source_filename": "_BodyEphemeris_Earth_LunaEarthRotating.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Earth_LunaEarthRotating.csv"},
    {"source_filename": "_BodyEphemeris_Sun_LunaEarthRotating.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/_BodyEphemeris_Sun_LunaEarthRotating.csv"},
    {"source_filename": "post_tli.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/post_tli.csv"},
    {"source_filename": "post_loi.csv", "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/post_loi.csv"},
]
CHECKPOINT_REPORTS = [
    {
        "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/post_tli.csv",
        "include_header": True,
        "parameters": [r"CislunarSat.UTCGregorian", r"CislunarSat.ElapsedSecs", r"CislunarSat.EarthMJ2000Eq.X", r"CislunarSat.EarthMJ2000Eq.Y", r"CislunarSat.EarthMJ2000Eq.Z", r"CislunarSat.EarthMJ2000Eq.VX", r"CislunarSat.EarthMJ2000Eq.VY", r"CislunarSat.EarthMJ2000Eq.VZ", r"CislunarSat.Earth.SMA", r"CislunarSat.Earth.ECC", r"CislunarSat.EarthMJ2000Eq.INC", r"CislunarSat.EarthMJ2000Eq.RAAN", r"CislunarSat.EarthMJ2000Eq.AOP", r"CislunarSat.Earth.TA"],
    },
    {
        "desired_path": r"D:/Documents and stuff/Random stuff/Pet Projects/Agnetic GMAT/AMAT/generated/cislunar_demo/simulation/outputs/post_loi.csv",
        "include_header": True,
        "parameters": [r"CislunarSat.UTCGregorian", r"CislunarSat.ElapsedSecs", r"CislunarSat.LunaMJ2000Eq.X", r"CislunarSat.LunaMJ2000Eq.Y", r"CislunarSat.LunaMJ2000Eq.Z", r"CislunarSat.LunaMJ2000Eq.VX", r"CislunarSat.LunaMJ2000Eq.VY", r"CislunarSat.LunaMJ2000Eq.VZ", r"CislunarSat.Luna.SMA", r"CislunarSat.Luna.ECC", r"CislunarSat.LunaMJ2000Eq.INC", r"CislunarSat.LunaMJ2000Eq.RAAN", r"CislunarSat.LunaMJ2000Eq.AOP", r"CislunarSat.Luna.TA"],
    },
]
def _gmat_module() -> Any:
    return getattr(gp, "gmat", gp)


def _call_gmat_function(names: list[str], *args: Any) -> Any:
    """Call a GMAT/gmatpyplus function from the first available location."""
    candidates = [gp, _gmat_module()]
    for obj in candidates:
        for name in names:
            fn = getattr(obj, name, None)
            if callable(fn):
                return fn(*args)
    raise RuntimeError(f"None of the GMAT functions are available: {names}")


def _clear_gmat_state() -> None:
    if hasattr(_gmat_module(), "Clear"):
        try:
            _gmat_module().Clear()
        except Exception:
            pass


def _get_state(spacecraft: Any) -> list[float | None]:
    state: list[float | None] = [None] * 6
    for idx in range(13, 19):
        try:
            state[idx - 13] = float(spacecraft.GetField(idx))
        except Exception:
            state[idx - 13] = None
    return state


def build_objects() -> dict[str, Any]:
    """Build a direct Python GMAT mission for missions without full ephemeris/checkpoints."""
    _clear_gmat_state()
    objects: dict[str, Any] = {}

    CislunarSat = gp.Spacecraft("CislunarSat")
    CislunarSat.SetField("DateFormat", "UTCGregorian")
    CislunarSat.SetField("Epoch", "01 Jun 2026 00:00:00.000")
    CislunarSat.SetField("CoordinateSystem", "EarthMJ2000Eq")
    CislunarSat.SetField("DisplayStateType", "Cartesian")
    CislunarSat.SetField("X", -4947.9535435061525)
    CislunarSat.SetField("Y", 4053.0644613947075)
    CislunarSat.SetField("Z", 1920.398043235261)
    CislunarSat.SetField("VX", -5.1791178775370375)
    CislunarSat.SetField("VY", -4.963716277224432)
    CislunarSat.SetField("VZ", -2.868036985421945)
    CislunarSat.SetField("DryMass", 1000.0)
    CislunarSat.SetField("Cd", 2.2)
    CislunarSat.SetField("Cr", 1.8)
    CislunarSat.SetField("DragArea", 8.0)
    CislunarSat.SetField("SRPArea", 12.0)
    objects["cislunar_sat"] = CislunarSat

    raise RuntimeError("Direct Python force-model execution is not enabled for multi-body/spherical-harmonic force models in this MVP; use script replay, which is selected automatically.")

    CislunarProp_integrator = gp.PropSetup.Propagator(
        name="CislunarProp_Integrator",
        integrator="RungeKutta89",
    )
    CislunarProp = gp.PropSetup(
        "CislunarProp",
        fm=objects["earth_luna_8x8"],
        gator=CislunarProp_integrator,
        initial_step_size=60.0,
        accuracy=1e-09,
        min_step=0.1,
        max_step=1800.0,
    )
    objects["cislunar_prop"] = CislunarProp

    if hasattr(gp, "Initialize"):
        gp.Initialize()
    return objects


def build_mission_sequence(objects: dict[str, Any]) -> list[Any]:
    mcs: list[Any] = []
    # Phase: cislunar_transfer - Impulsive cislunar transfer
    raise RuntimeError("Direct Python maneuver execution is not enabled in this MVP; run with script replay, which is selected automatically for missions with burns.")
    # Sparse checkpoints are handled by GMAT script replay mode.
    raise RuntimeError("Direct Python event-action execution is not enabled in this MVP; run with script replay, which is selected automatically for missions with events.")
    mcs.append(
        gp.Propagate(
            "Propagate_lunar_orbit_checkout_CislunarSat",
            objects["cislunar_sat"],
            objects["cislunar_prop"],
            ("CislunarSat.ElapsedSecs", 172800.0),
        )
    )
    return mcs


def save_script(path: str | Path | None = None) -> Path:
    """Save/export the current direct-Python object graph as GMAT script."""
    script_path = Path(path) if path else SCRIPT_PATH
    _call_gmat_function(["SaveScript"], str(script_path))
    return script_path



def _candidate_report_locations(filename: str) -> list[Path]:
    """Return likely locations where GMAT writes ReportFile output.

    Native GMAT script mode is most reliable when ReportFile.Filename is a
    plain filename. GMAT commonly writes such files into its configured output
    directory, not the project directory. We therefore search the GMAT output
    directory first, then local fallback locations, and copy results into the
    generated mission outputs folder after RunScript returns.
    """
    candidates: list[Path] = []
    gmat_root = os.environ.get("GMAT") or os.environ.get("GMAT_ROOT") or os.environ.get("GMAT_PATH")
    if gmat_root:
        candidates.append(Path(gmat_root) / "output" / filename)
        candidates.append(Path(gmat_root) / "bin" / "output" / filename)
    candidates.extend([
        ROOT / filename,
        ROOT / "outputs" / filename,
        Path.cwd() / filename,
        Path.cwd() / "output" / filename,
        Path.cwd() / "outputs" / filename,
    ])
    # Preserve order while removing duplicates.
    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item.resolve()) if item.exists() else str(item)
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def _collect_report_outputs() -> dict[str, Any]:
    copied: list[dict[str, str]] = []
    still_missing: list[str] = []
    searched: dict[str, list[str]] = {}
    normalized_csvs: list[dict[str, Any]] = []
    for item in REPORT_COPIES:
        filename = item["source_filename"]
        desired = Path(item["desired_path"])
        desired.parent.mkdir(parents=True, exist_ok=True)
        candidates = [desired, *[path for path in _candidate_report_locations(filename) if path != desired]]
        searched[str(desired)] = [str(path) for path in candidates]
        source = next((path for path in candidates if path.exists()), None)
        if source is None:
            still_missing.append(str(desired))
            continue
        if source.resolve() != desired.resolve():
            shutil.copy2(source, desired)
        normalized_csvs.append(_normalize_csv_file(desired))
        copied.append({"from": str(source), "to": str(desired)})
    checkpoint_headers = _finalize_checkpoint_headers()
    return {
        "copied_outputs": copied,
        "missing_outputs": still_missing,
        "searched_locations": searched,
        "normalized_csvs": normalized_csvs,
        **checkpoint_headers,
    }


def _clean_prior_report_outputs() -> list[str]:
    removed: list[str] = []
    targets = set(EXPECTED_OUTPUTS)
    for item in REPORT_COPIES:
        for path in _candidate_report_locations(item["source_filename"]):
            targets.add(str(path))
    for text in sorted(targets):
        path = Path(text)
        try:
            if path.exists():
                path.unlink()
                removed.append(str(path))
        except Exception:
            pass
    return removed


def _clean_csv_row(row: list[str]) -> list[str]:
    return [cell.strip() for cell in row if cell is not None and cell.strip() != ""]



def _normalize_csv_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "changed": False}
    try:
        with path.open("r", newline="", encoding="utf-8", errors="replace") as f:
            rows = [_clean_csv_row(row) for row in csv.reader(f)]
        rows = [row for row in rows if row]
        before = path.read_text(encoding="utf-8", errors="replace")
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(rows)
        after = path.read_text(encoding="utf-8", errors="replace")
        return {"path": str(path), "exists": True, "changed": before != after, "rows": len(rows)}
    except Exception as exc:
        return {"path": str(path), "exists": True, "changed": False, "error": str(exc)}


def _finalize_checkpoint_headers() -> dict[str, Any]:
    """Ensure sparse checkpoint files have deterministic one-row snapshot headers.

    GMAT's Report command writes the snapshot data at the exact mission-sequence
    location. Some GMAT versions do not emit headers for Report-command output,
    so the generated runner inserts the user-defined parameter list as the first
    row after the run. This preserves the rule that checkpoint files are sparse
    state snapshots, not trajectory files.
    """
    updated: list[str] = []
    missing: list[str] = []
    errors: list[dict[str, str]] = []
    for item in CHECKPOINT_REPORTS:
        path = Path(item["desired_path"])
        if not path.exists():
            missing.append(str(path))
            continue
        if not item.get("include_header", True):
            continue
        header = [str(p) for p in item.get("parameters", [])]
        try:
            with path.open("r", newline="", encoding="utf-8", errors="replace") as f:
                rows = [_clean_csv_row(row) for row in csv.reader(f)]
            rows = [row for row in rows if row]
            if rows and rows[0] == header:
                continue
            with path.open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(rows)
            updated.append(str(path))
        except Exception as exc:
            errors.append({"path": str(path), "error": str(exc)})
    return {
        "checkpoint_headers_updated": updated,
        "checkpoint_header_missing_files": missing,
        "checkpoint_header_errors": errors,
    }

def _find_elapsed_column(header: list[str]) -> int | None:
    for idx, name in enumerate(header):
        compact = name.strip().replace(" ", "")
        if compact.endswith(".ElapsedSecs") or compact == "ElapsedSecs" or "ElapsedSecs" in compact:
            return idx
    return None



def _auto_export_visualization_artifacts() -> dict[str, Any]:
    """Refresh viewer-facing artifacts after runtime outputs are available.

    Normal operation should leave the visualization layer with ready-to-load
    data after `generated_mission.py --run`: cleaned spacecraft/checkpoint CSVs,
    SPICE-derived body ephemeris CSVs when resolved files are present, and a
    refreshed visualization_manifest.json.  The standalone CLI command
    `export-visualization` remains available as a repair/troubleshooting path.
    """
    if not (VISUALIZATION_ENABLED and VISUALIZATION_AUTO_EXPORT_AFTER_RUN):
        return {"enabled": VISUALIZATION_ENABLED, "auto_export_after_run": VISUALIZATION_AUTO_EXPORT_AFTER_RUN, "status": "skipped"}
    try:
        from mission_compiler.visualization import export_visualization_artifacts
        export = export_visualization_artifacts(ROOT)
        export["enabled"] = True
        export["auto_export_after_run"] = True
        export["status"] = "completed"
        return export
    except Exception as exc:  # pragma: no cover - runtime diagnostic path
        return {
            "enabled": True,
            "auto_export_after_run": True,
            "status": "failed",
            "error": str(exc),
        }

def run_script_replay() -> dict[str, Any]:
    """Run generated_mission.script through GMAT's native script runner.

    Use this mode whenever mission_spec.json requests full ephemeris or sparse
    checkpoints.  GMAT owns ReportFile creation, headers, data publication, and
    file finalization; Python only loads/runs the script and reports output paths.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    removed_prior_outputs = _clean_prior_report_outputs()
    print(f"Loading GMAT script: {SCRIPT_PATH}")
    load_code = _call_gmat_function(["LoadScript"], str(SCRIPT_PATH))
    print(f"GMAT LoadScript returned: {load_code}")
    print("Starting GMAT RunScript...")
    run_code = _call_gmat_function(["RunScript"])
    print(f"GMAT RunScript returned: {run_code}")
    collected = _collect_report_outputs()
    visualization_export = _auto_export_visualization_artifacts()
    return {
        "mission_id": MISSION_ID,
        "execution_mode": "script_replay",
        "load_code": load_code,
        "run_code": run_code,
        "outputs_dir": str(OUTPUT_DIR),
        "expected_outputs": EXPECTED_OUTPUTS,
        "removed_prior_outputs": removed_prior_outputs,
        **collected,
        "visualization_export": visualization_export,
    }


def run_direct_python() -> dict[str, Any]:
    """Run directly through gmatpyplus object mode.

    This mode is only used when mission_spec.json does not request full ephemeris
    or checkpoints, because ReportFile/subscriber handling is more reliable in
    native GMAT script replay mode.
    """
    objects = build_objects()
    mcs = build_mission_sequence(objects)
    before = {
        "cislunar_sat": _get_state(objects["cislunar_sat"]),
    }
    run_code = gp.RunMission(mcs)
    after: dict[str, Any] = {}
    try:
        runtime_sc = _gmat_module().GetRuntimeObject("CislunarSat")
    except Exception:
        runtime_sc = objects["cislunar_sat"]
    after["cislunar_sat"] = _get_state(runtime_sc)
    visualization_export = _auto_export_visualization_artifacts()
    return {
        "mission_id": MISSION_ID,
        "execution_mode": "direct_python",
        "run_code": int(run_code) if isinstance(run_code, (int, float, str)) and str(run_code).isdigit() else run_code,
        "state_before": before,
        "state_after": after,
        "visualization_export": visualization_export,
    }


def run_mission() -> dict[str, Any]:
    return run_script_replay() if REQUIRES_SCRIPT_REPLAY else run_direct_python()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="Run according to mission_spec.json execution needs")
    parser.add_argument("--save-script", action="store_true", help="Troubleshooting only: export direct-Python object graph")
    parser.add_argument("--force-direct-python", action="store_true", help="Troubleshooting only: bypass script replay")
    args = parser.parse_args()

    if args.run:
        result = run_direct_python() if args.force_direct_python else run_mission()
        print(result)
        return

    if args.save_script:
        build_objects()
        print(f"Saved script: {save_script()}")
        return

    print("Generated mission is ready.")
    print("Normal operation is controlled by mission_spec.json; use --run to execute it.")
    print(f"Execution mode: {'script_replay' if REQUIRES_SCRIPT_REPLAY else 'direct_python'}")
    print(f"Runtime outputs will be written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
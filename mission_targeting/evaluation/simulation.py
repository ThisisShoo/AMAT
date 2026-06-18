from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np

from mission_compiler.io import read_json
from mission_targeting.constants import EARTH_RADIUS_KM, LUNA_RADIUS_KM
from mission_targeting.domain import canonicalize_target_problem
from mission_visualizer.gmat_report_parser import infer_object_frame_from_columns, parse_gmat_report, resolve_column


BODY_RADII_KM = {
    "Earth": EARTH_RADIUS_KM,
    "Luna": LUNA_RADIUS_KM,
    "Moon": LUNA_RADIUS_KM,
}


def _quantity_value(value: Any) -> float:
    if isinstance(value, dict):
        return float(value["value"])
    return float(value)


def _find_column(columns: list[str], suffixes: list[str]) -> str | None:
    for suffix in suffixes:
        for col in columns:
            if col == suffix or col.endswith("." + suffix):
                return col
    return None


def _final_checkpoint(outputs_dir: Path) -> Path:
    preferred = outputs_dir / "final_state_checkpoint.csv"
    if preferred.exists():
        return preferred
    matches = sorted(outputs_dir.glob("*final*.csv"))
    if matches:
        return matches[0]
    raise FileNotFoundError(f"No final checkpoint CSV found in {outputs_dir}")


def _simulation_paths(simulation_dir: str | Path) -> tuple[Path, Path]:
    sim = Path(simulation_dir)
    outputs = sim / "outputs"
    if outputs.is_dir():
        return sim, outputs
    if sim.name == "outputs" and sim.is_dir():
        return sim.parent, sim
    raise FileNotFoundError(f"Could not find outputs/ under {sim}")


def _mission_spec_for(simulation_dir: Path) -> dict[str, Any] | None:
    for name in ("mission_spec.canonical.json", "mission_spec.json"):
        path = simulation_dir / name
        if path.exists():
            return read_json(path)
    return None


def _burn_total_delta_v(mission_spec: dict[str, Any] | None) -> float | None:
    if not mission_spec:
        return None
    total = 0.0
    found = False
    for burn in mission_spec.get("burns", []) or []:
        dv = burn.get("delta_v_km_s")
        if isinstance(dv, list) and dv:
            total += math.sqrt(sum(float(x) ** 2 for x in dv))
            found = True
    return total if found else None


def _body_radius(body: str | None) -> float | None:
    if not body:
        return None
    return BODY_RADII_KM.get(body)


def _origin_from_frame(frame: str | None, default: str = "Earth") -> str:
    if not frame:
        return default
    if frame.endswith("MJ2000Eq"):
        return frame[: -len("MJ2000Eq")] or default
    if frame.startswith("Earth"):
        return "Earth"
    if frame.startswith("Luna"):
        return "Luna"
    return default


def _extract_final_metrics(problem: dict[str, Any], outputs_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _final_checkpoint(outputs_dir)
    df = parse_gmat_report(path)
    if df.empty:
        raise ValueError(f"Final checkpoint is empty: {path}")
    row = df.iloc[-1]
    cols = list(df.columns)
    spacecraft, frame = infer_object_frame_from_columns(cols)
    central_body = problem.get("transfer_strategy", {}).get("central_body") or _origin_from_frame(frame)
    origin = _origin_from_frame(frame, str(central_body))

    metric_columns = {
        "spacecraft.final.orbit.sma": _find_column(cols, [f"{origin}.SMA", "SMA"]),
        "spacecraft.final.orbit.eccentricity": _find_column(cols, [f"{origin}.ECC", "ECC"]),
        "spacecraft.final.orbit.inclination": _find_column(cols, [f"{frame}.INC" if frame else "INC", "INC"]),
        "spacecraft.final.orbit.raan": _find_column(cols, [f"{frame}.RAAN" if frame else "RAAN", "RAAN"]),
        "spacecraft.final.orbit.aop": _find_column(cols, [f"{frame}.AOP" if frame else "AOP", "AOP"]),
        "spacecraft.final.orbit.ta": _find_column(cols, [f"{origin}.TA", "TA"]),
    }
    metrics: dict[str, Any] = {}
    evidence: dict[str, Any] = {
        "final_checkpoint": str(path),
        "spacecraft": spacecraft,
        "frame": frame,
        "central_body": central_body,
        "columns": {},
    }
    for metric_id, col in metric_columns.items():
        if col and col in df:
            value = row[col]
            if value is not None and not (isinstance(value, float) and np.isnan(value)):
                metrics[metric_id] = {"value": float(value), "unit": "deg" if metric_id.endswith(("inclination", "raan", "aop", "ta")) else ("1" if metric_id.endswith("eccentricity") else "km")}
                evidence["columns"][metric_id] = col
    return metrics, evidence


def _declared_ephemeris_paths(outputs_dir: Path, spacecraft: str | None = None) -> list[Path]:
    spec_path = outputs_dir.parent / "mission_spec.canonical.json"
    if not spec_path.exists():
        return []
    try:
        spec = read_json(spec_path)
    except Exception:
        return []
    paths: list[Path] = []
    for out in spec.get("outputs", []) or []:
        if out.get("type") not in {"spacecraft_ephemeris", "state_history", "full_ephemeris"}:
            continue
        if spacecraft and out.get("spacecraft") not in {None, spacecraft, "sat"}:
            continue
        raw_path = out.get("path")
        if raw_path:
            path = outputs_dir.parent / str(raw_path)
            if path.exists():
                paths.append(path)
            continue
        raw_template = out.get("path_template")
        if raw_template:
            for frame in out.get("frames", []) or []:
                path = outputs_dir.parent / str(raw_template).format(frame=frame)
                if path.exists():
                    paths.append(path)
    return sorted(dict.fromkeys(paths))


def _minimum_altitude(
    problem: dict[str, Any],
    outputs_dir: Path,
    spacecraft: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ephemerides = _declared_ephemeris_paths(outputs_dir, spacecraft) or sorted(outputs_dir.glob("_Ephemeris*.csv"))
    if spacecraft:
        preferred = [path for path in ephemerides if spacecraft in path.name]
        if preferred:
            ephemerides = preferred
    if not ephemerides:
        return None, None
    path = ephemerides[0]
    df = parse_gmat_report(path)
    if df.empty:
        return None, None
    cols = list(df.columns)
    _, frame = infer_object_frame_from_columns(cols)
    central_body = problem.get("transfer_strategy", {}).get("central_body") or _origin_from_frame(frame)
    radius = _body_radius(str(central_body))
    if radius is None:
        return None, None
    x_col = resolve_column(cols, None, ["X"])
    y_col = resolve_column(cols, None, ["Y"])
    z_col = resolve_column(cols, None, ["Z"])
    if not all([x_col, y_col, z_col]):
        return None, None
    xyz = df[[x_col, y_col, z_col]].astype(float).to_numpy()
    altitudes = np.linalg.norm(xyz, axis=1) - radius
    minimum = float(np.nanmin(altitudes))
    return (
        {"value": minimum, "unit": "km"},
        {"ephemeris": str(path), "frame": frame, "central_body": central_body, "columns": [x_col, y_col, z_col]},
    )


def _residual(metric_id: str, achieved: float, target: float, tolerance: float, unit: str, relation: str = "eq") -> dict[str, Any]:
    if relation == "ge":
        residual = achieved - target
        passed = residual >= -tolerance
    elif relation == "le":
        residual = achieved - target
        passed = residual <= tolerance
    else:
        residual = achieved - target
        passed = abs(residual) <= tolerance
    return {
        "metric_id": metric_id,
        "achieved": {"value": achieved, "unit": unit},
        "target": {"value": target, "unit": unit},
        "residual": {"value": residual, "unit": unit},
        "tolerance": {"value": tolerance, "unit": unit},
        "relation": relation,
        "passed": bool(passed),
    }


def _angle_delta_deg(achieved: float, target: float) -> float:
    return (achieved - target + 180.0) % 360.0 - 180.0


def _angle_residual(metric_id: str, achieved: float, target: float, tolerance: float) -> dict[str, Any]:
    residual = _angle_delta_deg(achieved, target)
    return {
        "metric_id": metric_id,
        "achieved": {"value": achieved, "unit": "deg"},
        "target": {"value": target, "unit": "deg"},
        "residual": {"value": residual, "unit": "deg"},
        "tolerance": {"value": tolerance, "unit": "deg"},
        "relation": "eq",
        "passed": bool(abs(residual) <= tolerance),
    }


def _constraint_residuals(problem: dict[str, Any], metrics: dict[str, Any]) -> list[dict[str, Any]]:
    target = problem["target"]
    residuals: list[dict[str, Any]] = []
    angular_tolerance = _quantity_value(target.get("angle_tolerance", target.get("inclination_max", {"value": 0.05})))
    target_ecc = float(target.get("eccentricity", 0.0))
    eccentricity_tolerance = float(target.get("eccentricity_max", 1e-4))
    target_inc = _quantity_value(target["inclination"])
    inclination_tolerance = _quantity_value(target.get("inclination_max", {"value": 0.05}))
    achieved_ecc = metrics.get("spacecraft.final.orbit.eccentricity", {}).get("value")
    achieved_inc = metrics.get("spacecraft.final.orbit.inclination", {}).get("value")
    raan_is_defined = not (
        abs(target_inc) <= inclination_tolerance
        and achieved_inc is not None
        and abs(float(achieved_inc)) <= inclination_tolerance
    )
    aop_is_defined = not (
        abs(target_ecc) <= eccentricity_tolerance
        and achieved_ecc is not None
        and abs(float(achieved_ecc)) <= eccentricity_tolerance
    )

    if "spacecraft.final.orbit.sma" in metrics:
        residuals.append(_residual(
            "spacecraft.final.orbit.sma",
            metrics["spacecraft.final.orbit.sma"]["value"],
            _quantity_value(target["sma"]),
            1.0,
            "km",
        ))
    if "spacecraft.final.orbit.eccentricity" in metrics:
        residuals.append(_residual(
            "spacecraft.final.orbit.eccentricity",
            metrics["spacecraft.final.orbit.eccentricity"]["value"],
            float(target.get("eccentricity", 0.0)),
            float(target.get("eccentricity_max", 1e-4)),
            "1",
        ))
    if "spacecraft.final.orbit.inclination" in metrics:
        residuals.append(_angle_residual(
            "spacecraft.final.orbit.inclination",
            metrics["spacecraft.final.orbit.inclination"]["value"],
            target_inc,
            inclination_tolerance,
        ))
    if raan_is_defined and "spacecraft.final.orbit.raan" in metrics:
        residuals.append(_angle_residual(
            "spacecraft.final.orbit.raan",
            metrics["spacecraft.final.orbit.raan"]["value"],
            _quantity_value(target["raan"]),
            angular_tolerance,
        ))
    if aop_is_defined and "spacecraft.final.orbit.aop" in metrics:
        residuals.append(_angle_residual(
            "spacecraft.final.orbit.aop",
            metrics["spacecraft.final.orbit.aop"]["value"],
            _quantity_value(target["aop"]),
            angular_tolerance,
        ))
    if "spacecraft.final.orbit.ta" in metrics:
        ta_target = target.get("true_anomaly") or target.get("ta")
        if ta_target is not None:
            residuals.append(_angle_residual(
                "spacecraft.final.orbit.ta",
                metrics["spacecraft.final.orbit.ta"]["value"],
                _quantity_value(ta_target),
                angular_tolerance,
            ))

    limits = problem.get("limits", {})
    if "minimum_altitude" in limits and "trajectory.minimum_altitude" in metrics:
        residuals.append(_residual(
            "trajectory.minimum_altitude",
            metrics["trajectory.minimum_altitude"]["value"],
            _quantity_value(limits["minimum_altitude"]),
            0.0,
            "km",
            relation="ge",
        ))
    if "maximum_total_delta_v" in limits and "mission.total_delta_v" in metrics:
        residuals.append(_residual(
            "mission.total_delta_v",
            metrics["mission.total_delta_v"]["value"],
            _quantity_value(limits["maximum_total_delta_v"]),
            0.0,
            "km/s",
            relation="le",
        ))
    return residuals


def evaluate_simulation(problem: dict[str, Any], simulation_dir: str | Path) -> dict[str, Any]:
    """Evaluate a completed AMAT simulation against a TargetProblem.

    This milestone intentionally consumes existing artifacts only. It does not
    compile, run GMAT, or correct variables.
    """
    p = canonicalize_target_problem(problem)
    sim, outputs = _simulation_paths(simulation_dir)
    mission_spec = _mission_spec_for(sim)

    metrics, evidence = _extract_final_metrics(p, outputs)
    min_alt, min_alt_evidence = _minimum_altitude(p, outputs, evidence.get("spacecraft"))
    if min_alt is not None:
        metrics["trajectory.minimum_altitude"] = min_alt
        evidence["minimum_altitude"] = min_alt_evidence
    total_dv = _burn_total_delta_v(mission_spec)
    if total_dv is not None:
        metrics["mission.total_delta_v"] = {"value": total_dv, "unit": "km/s"}
        evidence["mission_spec"] = str(sim / "mission_spec.canonical.json")

    residuals = _constraint_residuals(p, metrics)
    passed = bool(residuals) and all(r["passed"] for r in residuals)
    return {
        "schema_version": "1.0.0",
        "problem_id": p["problem_id"],
        "mission_id": p["mission_id"],
        "simulation_dir": str(sim),
        "outputs_dir": str(outputs),
        "simulation_status": "completed",
        "evaluation_status": "passed" if passed else "failed",
        "metrics": metrics,
        "residuals": residuals,
        "evidence": evidence,
    }


def build_acceptance_result(problem: dict[str, Any], evaluation: dict[str, Any], candidate_id: str | None = None) -> dict[str, Any]:
    p = canonicalize_target_problem(problem)
    passed = evaluation.get("evaluation_status") == "passed"
    return {
        "schema_version": "1.0.0",
        "problem_id": p["problem_id"],
        "mission_id": p["mission_id"],
        "candidate_id": candidate_id,
        "simulation_status": evaluation.get("simulation_status", "unknown"),
        "targeting_status": "accepted" if passed else "not_accepted",
        "verification_status": "L1_passed" if passed else "L1_failed",
        "required_verification_level": p["verification"]["required_level"],
        "acceptance_status": "passed" if passed else "failed",
        "residuals": evaluation.get("residuals", []),
        "evidence_artifacts": {
            "simulation_evaluation": "simulation_evaluation.json",
        },
    }

from __future__ import annotations

from mission_compiler.errors import MissionValidationError


def validate_units(spec: dict) -> list[dict]:
    c = spec.get("conventions", {})
    expected = {
        "distance_unit": "km",
        "velocity_unit": "km/s",
        "angle_unit": "deg",
        "mass_unit": "kg",
        "time_scale": "UTC",
    }
    problems = [f"{k} must be {v}" for k, v in expected.items() if c.get(k) != v]
    if problems:
        raise MissionValidationError("; ".join(problems))
    return [{"check_id": "units", "status": "passed", "severity": "error", "message": "MVP units and time scale are explicit and supported."}]

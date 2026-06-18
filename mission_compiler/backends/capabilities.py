from __future__ import annotations

from mission_compiler.errors import BackendCapabilityError
from mission_compiler.ir.sequence import iter_steps

GMAT_BUILTIN_MAJOR_BODIES = {
    "Sun", "Mercury", "Venus", "Earth", "Luna", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"
}


def check_capability(spec: dict, capability: dict) -> list[dict]:
    supported = capability["supported"]
    problems: list[str] = []
    declared_bodies = {b.get("name") for b in spec.get("bodies", [])} | {b.get("id") for b in spec.get("bodies", [])}
    declared_bodies = {b for b in declared_bodies if b}
    allow_custom = supported.get("custom_bodies", False)
    for fm in spec.get("force_models", []):
        central = fm.get("central_body", "Earth")
        if central not in supported.get("central_bodies", []) and central not in declared_bodies and not allow_custom:
            problems.append(f"central body {central} is unsupported")
        gravity_type = fm["gravity"]["type"]
        if gravity_type == "basic_earth_gravity":
            gravity_type = "spherical_harmonic"
        if gravity_type not in supported["force_models"]:
            problems.append(f"gravity model {fm['gravity']['type']} is unsupported")
        requested_point_masses = set((fm.get("point_masses") or []) + fm.get("third_body_gravity", {}).get("bodies", []))
        for body in requested_point_masses:
            if body in GMAT_BUILTIN_MAJOR_BODIES:
                continue
            if body in declared_bodies and allow_custom:
                continue
            problems.append(f"point mass {body} is unsupported or undeclared")
    for p in spec.get("propagators", []):
        if p["integrator"] not in supported["integrators"]:
            problems.append(f"integrator {p['integrator']} is unsupported")
    for burn in spec.get("burns", []):
        if burn["type"] not in supported.get("maneuvers", []):
            problems.append(f"burn type {burn['type']} is unsupported")
    for _, step, _ in iter_steps(spec):
        if step["type"] not in supported["commands"]:
            problems.append(f"command {step['type']} is unsupported")
    for out in spec.get("outputs", []):
        if out["type"] not in supported.get("outputs", []):
            problems.append(f"output {out['type']} is unsupported")
    if problems:
        raise BackendCapabilityError("; ".join(problems))
    return [{"check_id": "backend_capability", "status": "passed", "severity": "error", "message": "MissionSpec fits selected backend capability."}]

from __future__ import annotations

from copy import deepcopy
from typing import Any


def normalize_mission_sequence(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return mission_sequence as explicit phases with ordered steps.

    Backward-compatible flat propagate commands are wrapped into one default
    phase. New MissionSpec entries keep their manual phase boundaries.
    """
    raw = deepcopy(spec.get("mission_sequence", []))
    if not raw:
        return []

    # New phased form: every top-level entry has steps.
    if all("steps" in item for item in raw):
        return raw

    # Backward-compatible flat form: one default phase, auto step ids.
    steps = []
    for idx, item in enumerate(raw, start=1):
        step = deepcopy(item)
        step.setdefault("step_id", f"legacy_step_{idx}")
        steps.append(step)
    return [
        {
            "phase_id": "default_phase",
            "name": "Default phase",
            "description": "Auto-created from deprecated flat mission_sequence.",
            "steps": steps,
        }
    ]


def iter_steps(spec: dict[str, Any]):
    """Yield (phase, step, global_step_index) for normalized phases."""
    index = 0
    for phase in normalize_mission_sequence(spec):
        for step in phase.get("steps", []):
            index += 1
            yield phase, step, index


def flatten_steps(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for _, step, _ in iter_steps(spec)]


def append_mission_sequence_phase(
    spec: dict[str, Any],
    *,
    phase_id: str,
    name: str,
    steps: list[dict[str, Any]],
    description: str | None = None,
) -> dict[str, Any]:
    """Append a manually authored phase to a MissionSpec sequence.

    The existing sequence is normalized first, so callers can safely append to
    either the phased representation or the legacy flat command list.
    """
    phase: dict[str, Any] = {
        "phase_id": phase_id,
        "name": name,
        "steps": steps,
    }
    if description:
        phase["description"] = description
    spec["mission_sequence"] = normalize_mission_sequence(spec)
    spec["mission_sequence"].append(phase)
    return phase

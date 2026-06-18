from __future__ import annotations

from mission_compiler.ir.defaults import apply_defaults
from mission_compiler.ir.sequence import normalize_mission_sequence


def _sort_by_id(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda x: x.get("id") or x.get("type") or "")


def canonicalize(spec: dict) -> dict:
    spec = apply_defaults(spec)
    for key in ["spacecraft", "force_models", "propagators", "burns"]:
        if key in spec:
            spec[key] = _sort_by_id(spec.get(key, []))
    spec["mission_sequence"] = normalize_mission_sequence(spec)
    # Keep phase and step order exactly as supplied.
    return spec

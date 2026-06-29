from __future__ import annotations

from typing import Any

from targeter.phase.selector import apply_phase_strategy, select_phase_strategy


def apply_phasing(problem: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return apply_phase_strategy(problem, candidate)


def select_phasing(problem: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return select_phase_strategy(problem, candidate)

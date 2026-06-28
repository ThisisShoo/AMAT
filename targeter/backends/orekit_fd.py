from __future__ import annotations

from typing import Any

from targeter.backends.base import CorrectionResult, SimulationRunResult
from targeter.backends.stm import StmCorrectionBackend


class OrekitFiniteDifferenceCorrectionBackend:
    """Orekit finite-difference correction backend.

    The Orekit simulation adapter writes an STM-shaped finite-difference
    sensitivity assessment from perturbation runs.  This correction backend
    consumes that artifact through the same linear correction contract as the
    backend-neutral STM corrector while preserving the user-visible backend ID.
    """

    backend_id = "orekit_fd"

    def __init__(self) -> None:
        self._stm = StmCorrectionBackend()

    def correct(
        self,
        problem: dict[str, Any],
        candidate: dict[str, Any],
        simulation: SimulationRunResult,
        config: dict[str, Any],
    ) -> CorrectionResult:
        result = self._stm.correct(problem, candidate, simulation, config)
        return CorrectionResult(
            backend_id=self.backend_id,
            status=result.status,
            candidate=result.candidate,
            correction=result.correction,
            errors=result.errors,
        )

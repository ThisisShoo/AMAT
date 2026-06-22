from __future__ import annotations

from targeter.backends.base import CorrectionBackend, SimulationBackend
from targeter.backends.stm import StmCorrectionBackend


def get_simulation_backend(backend_id: str) -> SimulationBackend:
    if backend_id == "gmat":
        from targeter.backends.gmat import GmatSimulationBackend

        return GmatSimulationBackend()
    raise ValueError(f"Unknown targeting simulation backend {backend_id!r}")


def get_correction_backend(backend_id: str) -> CorrectionBackend:
    if backend_id in {"stm", "stm_linear"}:
        return StmCorrectionBackend()
    raise ValueError(f"Unknown targeting correction backend {backend_id!r}")

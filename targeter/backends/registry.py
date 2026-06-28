from __future__ import annotations

from targeter.backends.base import CorrectionBackend, SimulationBackend
from targeter.backends.stm import StmCorrectionBackend


def get_simulation_backend(backend_id: str) -> SimulationBackend:
    key = backend_id.strip().lower()
    if key == "gmat":
        from targeter.backends.gmat import GmatSimulationBackend

        return GmatSimulationBackend()
    if key == "orekit":
        from targeter.backends.orekit import OrekitSimulationBackend

        return OrekitSimulationBackend()
    raise ValueError(f"Unknown targeting simulation backend {backend_id!r}")


def get_correction_backend(backend_id: str) -> CorrectionBackend:
    key = backend_id.strip().lower()
    if key in {"stm", "stm_linear"}:
        return StmCorrectionBackend()
    if key in {"orekit_fd", "orekit-fd", "orekit_finite_difference"}:
        from targeter.backends.orekit_fd import OrekitFiniteDifferenceCorrectionBackend

        return OrekitFiniteDifferenceCorrectionBackend()
    raise ValueError(f"Unknown targeting correction backend {backend_id!r}")

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class SimulationRunResult:
    backend_id: str
    status: str
    simulation_dir: str
    mission_spec: dict[str, Any]
    evaluation: dict[str, Any] | None
    compile_result: dict[str, Any] | None = None
    run_result: dict[str, Any] | None = None
    correction_artifacts: dict[str, Any] | None = None
    errors: tuple[str, ...] = ()

    @property
    def converged(self) -> bool:
        return bool(self.evaluation and self.evaluation.get("evaluation_status") == "passed")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["converged"] = self.converged
        return payload


@dataclass(frozen=True)
class CorrectionResult:
    backend_id: str
    status: str
    candidate: dict[str, Any] | None
    correction: dict[str, Any] | None = None
    errors: tuple[str, ...] = ()

    @property
    def corrected(self) -> bool:
        return self.status == "corrected" and self.candidate is not None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["corrected"] = self.corrected
        return payload


class SimulationBackend(Protocol):
    backend_id: str

    def evaluate_candidate(
        self,
        problem: dict[str, Any],
        candidate: dict[str, Any],
        mission_spec: dict[str, Any],
        out_dir: Path,
        *,
        run: bool,
    ) -> SimulationRunResult:
        ...


class CorrectionBackend(Protocol):
    backend_id: str

    def correct(
        self,
        problem: dict[str, Any],
        candidate: dict[str, Any],
        simulation: SimulationRunResult,
        config: dict[str, Any],
    ) -> CorrectionResult:
        ...

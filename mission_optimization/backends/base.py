from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class OptimizationBackend(Protocol):
    backend_id: str

    def solve(self, problem: dict[str, Any], out_dir: Path, run: bool = False) -> dict[str, Any]:
        """Evaluate or optimize the supplied canonical optimization problem."""

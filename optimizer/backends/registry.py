from __future__ import annotations

from .gmat import GmatOptimizationBackend
from .orekit import OrekitOptimizationBackend


def get_backend(backend_id: str):
    key = backend_id.strip().lower()
    if key == "gmat":
        return GmatOptimizationBackend()
    if key == "orekit":
        return OrekitOptimizationBackend()
    raise ValueError(f"Unknown optimization backend: {backend_id}")

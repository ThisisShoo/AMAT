from __future__ import annotations

from compiler.backends.gmat.compiler import GmatCompiler
from compiler.backends.orekit.compiler import OrekitCompiler


def get_backend(backend_id: str):
    key = backend_id.strip().lower()
    if key == "gmat":
        return GmatCompiler()
    if key == "orekit":
        return OrekitCompiler()
    raise ValueError(f"Unknown backend: {backend_id}")


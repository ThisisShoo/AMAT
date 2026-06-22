from __future__ import annotations

from compiler.backends.gmat.compiler import GmatCompiler


def get_backend(backend_id: str):
    if backend_id == "gmat":
        return GmatCompiler()
    raise ValueError(f"Unknown backend: {backend_id}")


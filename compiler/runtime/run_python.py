from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def run_generated_python(script_path: str | Path, save_script: bool = False, timeout_s: int = 300) -> dict:
    """Run a generated gmatpyplus Python mission script in a subprocess."""
    script = Path(script_path)
    if not script.exists():
        raise FileNotFoundError(script)
    cmd = [sys.executable, str(script), "--run"]
    cmd.append("--save-script" if save_script else "--no-save-script")
    proc = subprocess.run(cmd, cwd=str(script.parent), text=True, capture_output=True, timeout=timeout_s)
    return {
        "script_path": str(script),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "ok": proc.returncode == 0,
    }

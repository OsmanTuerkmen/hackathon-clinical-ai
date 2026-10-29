"""Project-local dependency bootstrap for the jury command-line entrypoints."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def ensure_runtime(script_path, arguments):
    try:
        import fastapi  # noqa: F401
        import duckdb  # noqa: F401
        import pydantic  # noqa: F401
        import uvicorn  # noqa: F401
        return
    except ImportError:
        pass
    virtualenv = ROOT / ".venv"
    python = virtualenv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(virtualenv)], check=True)
    if subprocess.run(
        [str(python), "-c", "import fastapi, duckdb, pydantic, uvicorn"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode:
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")],
            check=True,
        )
    os.execv(str(python), [str(python), str(Path(script_path).resolve()), *arguments])

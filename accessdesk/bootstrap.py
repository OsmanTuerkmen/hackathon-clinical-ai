"""Project-local dependency bootstrap for the jury command-line entrypoints."""
import os
import subprocess
import sys
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ai_key_configured():
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return True
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return False
    try:
        return any(
            line.strip().split("=", 1)[0].strip() == "ANTHROPIC_API_KEY"
            and line.strip().split("=", 1)[1].strip().strip("'\"")
            for line in env_path.read_text(encoding="utf-8").splitlines()
            if "=" in line and not line.lstrip().startswith("#")
        )
    except OSError:
        return False


def ensure_runtime(script_path, arguments):
    ai_required = _ai_key_configured() and importlib.util.find_spec("anthropic") is None
    try:
        import fastapi  # noqa: F401
        import duckdb  # noqa: F401
        import pydantic  # noqa: F401
        import uvicorn  # noqa: F401
        if not ai_required:
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
    if _ai_key_configured() and subprocess.run(
        [str(python), "-c", "import anthropic"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode:
        subprocess.run(
            [str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements-ai.txt")],
            check=True,
        )
    os.execv(str(python), [str(python), str(Path(script_path).resolve()), *arguments])

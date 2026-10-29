"""Atomic JSON persistence for local workflow state."""
import json
import os
from pathlib import Path


def write_json_atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(path.name + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=1, default=str)
        stream.write("\n")
    os.replace(temporary_path, path)

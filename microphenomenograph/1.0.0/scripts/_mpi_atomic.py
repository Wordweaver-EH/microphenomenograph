"""Atomic file primitives for mpi_step.py."""
import json
import os
import uuid
from pathlib import Path


def atomic_write(path: str | Path, content: str) -> None:
    """Write content to path atomically via .tmp -> os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def append_jsonl(path: str | Path, obj: dict) -> None:
    """Append one JSON object as a line to a JSONL file. fsync before close."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False, sort_keys=False) + "\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())


def load_or_create_run_id(run_id_path: str | Path) -> str:
    """Return existing run_id from path or create and persist a new UUID4."""
    path = Path(run_id_path)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    new_id = str(uuid.uuid4())
    atomic_write(path, new_id + "\n")
    return new_id

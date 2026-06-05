"""Atomic file primitives for mpi_step.py."""
import json
import os
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path


def atomic_write(path: str | Path, content: str) -> None:
    """Write content to path atomically via .tmp -> os.replace.

    On failure: leaves tmp file unlinked and original path untouched.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        # Clean up tmp file on failure
        if tmp.exists():
            tmp.unlink()
        raise


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


# ---------------------------------------------------------------------------
# Cross-platform advisory close lock
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as _wt
    import msvcrt as _msvcrt

    _LOCKFILE_EXCLUSIVE_LOCK = 0x00000002
    _LOCK_BYTES = 0xFFFF0000

    class _OFFSET(ctypes.Structure):
        _fields_ = [("Offset", _wt.DWORD), ("OffsetHigh", _wt.DWORD)]

    class _OFFSET_UNION(ctypes.Union):
        _anonymous_ = ["_offset"]
        _fields_ = [("_offset", _OFFSET), ("Pointer", ctypes.c_void_p)]

    class _OVERLAPPED(ctypes.Structure):
        _anonymous_ = ["_offset_union"]
        _fields_ = [
            ("Internal",      ctypes.c_ulong),
            ("InternalHigh",  ctypes.c_ulong),
            ("_offset_union", _OFFSET_UNION),
            ("hEvent",        _wt.HANDLE),
        ]

    _LockFileEx = ctypes.windll.kernel32.LockFileEx
    _LockFileEx.restype  = _wt.BOOL
    _LockFileEx.argtypes = [_wt.HANDLE, _wt.DWORD, _wt.DWORD,
                            _wt.DWORD, _wt.DWORD, ctypes.POINTER(_OVERLAPPED)]

    _UnlockFileEx = ctypes.windll.kernel32.UnlockFileEx
    _UnlockFileEx.restype  = _wt.BOOL
    _UnlockFileEx.argtypes = [_wt.HANDLE, _wt.DWORD,
                              _wt.DWORD, _wt.DWORD, ctypes.POINTER(_OVERLAPPED)]

    def _lock_acquire(fh: object) -> None:
        handle = _msvcrt.get_osfhandle(fh.fileno())  # type: ignore[attr-defined]
        ov = _OVERLAPPED()
        if not _LockFileEx(handle, _LOCKFILE_EXCLUSIVE_LOCK, 0,
                           _LOCK_BYTES, 0, ctypes.byref(ov)):
            raise OSError(f"LockFileEx failed: {ctypes.GetLastError()}")

    def _lock_release(fh: object) -> None:
        handle = _msvcrt.get_osfhandle(fh.fileno())  # type: ignore[attr-defined]
        ov = _OVERLAPPED()
        _UnlockFileEx(handle, 0, _LOCK_BYTES, 0, ctypes.byref(ov))

else:
    import fcntl as _fcntl

    def _lock_acquire(fh: object) -> None:
        _fcntl.flock(fh, _fcntl.LOCK_EX)   # blocks until acquired

    def _lock_release(fh: object) -> None:
        _fcntl.flock(fh, _fcntl.LOCK_UN)   # explicit unlock before close


@contextmanager
def acquire_close_lock(run_dir: "Path"):
    """
    Advisory exclusive lock for a run directory's close operations.

    Held for the full duration of:
      manifest re-read -> prereq check -> mutate -> write -> primary git commit
      -> cascade-reset manifest write -> cascade-reset git commit (if applicable)

    Lock file: <run_dir>/.mpi/close.lock

    On POSIX: fcntl.flock(LOCK_EX).
    On Windows: kernel32.LockFileEx via ctypes.

    Lock is automatically released by the OS if the holding process exits abnormally.
    The lock file persists after release and is re-lockable — this is by design.
    The correct post-interrupt test is re-lockability, not file absence.
    """
    lock_path = Path(run_dir) / ".mpi" / "close.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a") as fh:
        try:
            _lock_acquire(fh)
            yield
        finally:
            _lock_release(fh)

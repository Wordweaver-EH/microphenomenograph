# Pipeline Correctness Implementation Plan — Phase 4

**Goal:** Add `acquire_close_lock(run_dir)` context manager to `_mpi_atomic.py` and wrap `cmd_close`'s manifest-read → prereq-check → mutate → write → commit → cascade-reset block with it, preventing the parallel-manifest-write race in yolo mode.

**Architecture:** The lock (`<run_dir>/.mpi/close.lock`) is acquired just before the manifest's fresh re-read at line ~1251 of `cmd_close`, after artifact/schema/span validation. The lock is held through **both** the primary git commit (line ~1400) **and** the cascade-reset manifest write + commit (lines 1479–1527). The cascade-reset block (`diachronic.criteria_revision` re-close) also does a read-modify-write of the manifest and a second git commit; leaving it outside the lock creates the same race AC4 targets. The lock is released at line ~1528 (after the cascade-reset block). The initial manifest read at line 1134 (used for span validation only) is left in place; a fresh re-read happens inside the lock at the top. On POSIX: `fcntl.flock(LOCK_EX)`. On Windows: `ctypes` + `kernel32.LockFileEx`. Locks are automatically released by the OS on process exit, crash, or SIGTERM.

**Note on `unlock` subcommand:** `mpi_step.py unlock` (line 1686) is a `NotImplementedError` stub documented for releasing stale `.mpi/close.lock` files from a prior session. It is **unrelated** to the advisory lock this phase introduces: `fcntl.flock`/`LockFileEx` locks release automatically on process death and never need manual cleanup. The `unlock` stub addresses a different (future) scenario — user-visible lock starvation. Do not call `unlock` as part of this phase's implementation.

**Tech Stack:** Python 3, `fcntl` (POSIX), `ctypes` + `kernel32` (Windows), `subprocess`, pytest.

**Scope:** Phase 4 of 8 (independent — can be implemented in parallel with Phases 1, 2, 5).

**Codebase verified:** 2026-06-05

**Investigator findings:**
- `_mpi_atomic.py` is 44 lines; no existing locking code, no `fcntl`/`msvcrt` imports.
- `cmd_close`: manifest read at line 1134 (used for span validation); git commit at line ~1400.
- No existing parallel/concurrent close tests in `test_mpi_step.py`.
- Current environment is Windows; code must work cross-platform.

**External dependency findings:**
- POSIX: use `fcntl.flock(fh, fcntl.LOCK_EX)` + explicit `LOCK_UN` in `finally`. Lock releases automatically on process death.
- Windows: use `ctypes` + `kernel32.LockFileEx` via `msvcrt.get_osfhandle()`. Do NOT use `msvcrt.locking()` — unreliable for advisory use (byte-range only, non-blocking mode broken, uncertain crash cleanup).
- Lock file in "a" mode — creates if absent, does not truncate content.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC4: Manifest write safety under parallel closes
- **cross-scope-prereq-resolution.AC4.1 Success:** Two parallel `cmd_close` calls on different participants in the same run both commit their changes; both manifest entries show `done` when both finish.
- **cross-scope-prereq-resolution.AC4.2 Success:** A close that acquires the run lock always reads the manifest after all prior lock-holders have written and committed; no mutation is silently overwritten.
- **cross-scope-prereq-resolution.AC4.3 Success:** A `cmd_close` process that holds a run lock and is then interrupted (SIGTERM / KeyboardInterrupt) leaves the lock file behind in an unlocked state; a subsequent `acquire_close_lock(run_dir)` call succeeds without blocking.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add `acquire_close_lock()` to `_mpi_atomic.py`

**Verifies:** cross-scope-prereq-resolution.AC4.3 (re-lockability after interrupt)

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/_mpi_atomic.py`

**Implementation:**

Add to the top of `_mpi_atomic.py` after the existing imports:

```python
import sys
from contextlib import contextmanager
```

Then add the lock implementation after the `load_or_create_run_id` function (after line 44), before any future content:

```python
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
```

**Verification:**
```python
# Quick REPL test (from scripts/):
from pathlib import Path
import tempfile, os
with tempfile.TemporaryDirectory() as d:
    run_dir = Path(d)
    (run_dir / ".mpi").mkdir()
    from _mpi_atomic import acquire_close_lock
    with acquire_close_lock(run_dir):
        assert (run_dir / ".mpi" / "close.lock").exists()
    # After context: lock released, file still exists (correct)
    assert (run_dir / ".mpi" / "close.lock").exists()
    print("OK")
```

**Commit:** `feat: add acquire_close_lock context manager to _mpi_atomic.py (cross-platform fcntl/LockFileEx)`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wrap `cmd_close` manifest block with the lock; add tests

**Verifies:** cross-scope-prereq-resolution.AC4.1, AC4.2, AC4.3

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py`

**Implementation — update import at line 16:**

```python
from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id, acquire_close_lock
```

**Implementation — restructure `cmd_close`:**

The initial manifest read at line 1134 is kept for span validation (which runs outside the lock). After span validation and the IRR gate check, insert the lock and add a fresh manifest re-read.

Find the block starting at line 1251 (the prereq check comment):

```python
    # Check substep DAG prerequisites
    prereqs = SUBSTEP_PREREQUISITES.get((args.stage, args.substep), [])
```

Replace from line 1251 through **line ~1527** (the end of the cascade-reset block, just before the `print(f"OK ...")` at line 1529). The lock must cover both the primary commit (~line 1400) AND the cascade-reset manifest write + commit (lines 1479–1527). The cascade-reset's own `_load_manifest` at line 1483 happens inside the lock and reads the just-committed state — correct behaviour.

```python
    # Acquire close lock — wraps manifest re-read → prereq check → mutate → write → commit.
    # The initial manifest read above was used for span validation only.
    # A fresh read inside the lock guarantees we see any mutations made by concurrent closes.
    with acquire_close_lock(run_dir):
        manifest = _load_manifest(run_dir)

        # Check substep DAG prerequisites (with fresh manifest)
        prereqs = SUBSTEP_PREREQUISITES.get((args.stage, args.substep), [])
        for prereq_stage, prereq_substep in prereqs:
            prereq_participant = _prereq_participant_key(
                args.participant,
                prereq_stage,
                prereq_substep=prereq_substep,
                downstream_stage=args.stage,
                downstream_substep=args.substep,
            )
            if prereq_participant == "all_match":
                if not _all_candidate_draftings_done(manifest, prereq_stage, prereq_substep):
                    msg = (f"prereq_unsatisfied: all ({prereq_stage}, {prereq_substep}) "
                           f"entries must be 'done' before closing ({args.stage}, {args.substep})")
                    print(f"ERROR {msg}", file=sys.stderr)
                    return _abort(msg)
            else:
                status = _get_substep_status(manifest, prereq_participant, prereq_stage, prereq_substep)
                if status != "done":
                    msg = (f"prereq_unsatisfied: ({prereq_stage}, {prereq_substep}) "
                           f"must be 'done' before closing ({args.stage}, {args.substep}); "
                           f"current status: {status}")
                    print(f"ERROR {msg}", file=sys.stderr)
                    return _abort(msg)

        # [IRR gate check, substep reservation, artifact SHAs, audit events,
        #  manifest mutation, study-block mutation, manifest save, primary git commit,
        #  IRR auto-trigger, IRR alignment auto-accept, cascade-reset manifest write
        #  and cascade-reset git commit (lines 1263–1527) — all existing code goes here,
        #  unchanged except that it now operates on the fresh manifest inside the lock]
```

The key structural changes are:
1. Add `with acquire_close_lock(run_dir):` at line ~1251 (before prereq checks)
2. Add `manifest = _load_manifest(run_dir)` as the first statement inside the lock block
3. The old prereq check code (previously at 1251-1261) is now inside the lock using the updated form (Phase 3 changes)
4. All code from prereq checks through **line 1527** (end of cascade-reset block) runs inside the lock context
5. Lines 1529-1530 (`print(f"OK ...")` and `return 0`) are OUTSIDE the lock
6. The `_abort` helper defined earlier (line 1156) is still in scope; it uses `append_jsonl` (no manifest write), so it works inside the lock

**Why include cascade-reset inside the lock:** The cascade-reset block at lines 1479–1527 (`diachronic.criteria_revision` re-close) does a fresh `_load_manifest` at line 1483, mutates the manifest via `_cascade_reset`, writes via `_save_manifest` at line 1505, and commits at lines 1522-1525. Two concurrent `criteria_revision` re-closes for different participants (yolo mode) would race on exactly this path — the same read-modify-write hazard AC4 targets. Extending the lock through line 1527 serializes them.

**Testing — add class `TestManifestWriteSafety` to `test_mpi_step.py`:**

Uses `subprocess.Popen` to launch two simultaneous closes. Follow the pattern of `TestCloseHappyPath` for the run directory setup and valid payload construction.

Tests must verify:

- **AC4.1:** Launch two `mpi_step.py close` processes simultaneously (different participants `p1s1` and `p2s1`, both closing `diachronic.criteria_grouping`). Join both. Verify both processes exit 0 and both `manifest["participants"]["p1s1"]...status` and `manifest["participants"]["p2s1"]...status` are `"done"` in the final manifest.

- **AC4.2:** Verify the final manifest has entries for BOTH participants — the lock prevented overwrite. Check that `manifest["participants"]` has keys for both `p1s1` and `p2s1`.

- **AC4.3:** Start a close in a subprocess, send SIGTERM after a brief pause (enough for it to acquire the lock but not complete). Use `subprocess.Popen.send_signal(signal.SIGTERM)`. Confirm the process terminates. Then call `acquire_close_lock(run_dir)` in-process — it must succeed without blocking. The `.mpi/close.lock` file must exist.

Note on Windows: `SIGTERM` on Windows is handled differently — use `process.terminate()` which sends the equivalent. The test should use `process.terminate()` for portability.

**Add a serialization test (proves the lock actually blocks, not just that timing was lucky):**
- In-process: spawn a thread that calls `acquire_close_lock(run_dir)` and immediately writes a flag file inside the lock. From the main thread, also call `acquire_close_lock(run_dir)`. Verify the second acquisition blocks until the first releases (use a `threading.Event` to signal release). This is a deterministic correctness test, not a race-winning timing test. Works on both POSIX and Windows since both use blocking lock primitives.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestManifestWriteSafety -v
```
Expected: all three AC4 tests pass.

```
python -m pytest test_mpi_step.py -v
```
Expected: full suite passes, no regressions.

**Commit:** `feat: wrap cmd_close manifest block with acquire_close_lock; tests for AC4`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

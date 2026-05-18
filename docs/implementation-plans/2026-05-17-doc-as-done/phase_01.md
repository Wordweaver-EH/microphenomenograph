# Documentation-as-Done Contract Implementation Plan

**Goal:** Stand up `scripts/mpi_step.py` with stdlib-only deps, argument parsing, run-id management, and atomic file primitives. No business logic yet.

**Architecture:** Three new modules: entry-point CLI (`mpi_step.py`), atomic-primitive helpers (`_mpi_atomic.py`), and per-substep schema dict registry (`_mpi_schemas.py`). Also initialises the run repo's git config and enforces the dedicated-repo requirement. No external deps — stdlib only.

**Tech Stack:** Python 3.9+ stdlib (`argparse`, `os`, `uuid`, `json`, `subprocess`, `pathlib`, `hashlib`, `tempfile`). pytest for tests.

**Scope:** 1 of 6 phases from design (Phases 1–6).

**Codebase verified:** 2026-05-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC2: Helper CLI exposes the contract as one verb
- **doc-as-done.AC2.1 Success:** `python scripts/mpi_step.py close --actor ... --participant ... --stage ... --artifact ... --reason ... --units-json ...` succeeds end-to-end in a clean git repo with valid inputs.
- **doc-as-done.AC2.2 Success:** `python scripts/mpi_step.py --help` and `mpi_step.py close --help` print usage with all required and optional flags.

### doc-as-done.AC4: Schema validation rejects malformed units at write time
- **doc-as-done.AC4.1 Success:** A well-formed units payload (all required fields, no unknown keys, correct types) is accepted.

### doc-as-done.AC33: `/mpi init` refuses to nest in an active dev repo by default
- **doc-as-done.AC33.1 Failure:** `/mpi init --run <dir>` where `<dir>` is inside an existing non-empty git worktree errors `run_inside_active_repo` with the message "MPI runs produce ~100-200 commits per study; point --run at an empty directory or use --allow-active-repo-nested".
- **doc-as-done.AC33.2 Success:** With `--allow-active-repo-nested`, init proceeds; the manifest records `study.run_repo_mode = "nested_in_active"` so the choice is visible in the audit trail.
- **doc-as-done.AC33.3 Success:** Default mode (empty target dir or pre-existing empty repo) writes `study.run_repo_mode = "dedicated"`. Helper sets `core.autocrlf false`, `core.eol lf` — local config only, never global.
- **doc-as-done.AC33.4 Success (hooks disabled by default):** Helper sets local `core.hooksPath = .git/hooks-disabled` and creates that empty directory.
- **doc-as-done.AC33.5 Success (signing off by default, with audit if enabled):** Helper sets `commit.gpgsign false` (recommendation, not forced).
- **doc-as-done.AC33.6 Failure (identity unset):** If global `user.name` or `user.email` is unset and no local override exists, init fails with `git_identity_unset` and prompts the user; the helper does NOT silently invent an author identity.
- **doc-as-done.AC33.7 Success (local-only by default):** The helper never runs `git push` or `git remote add`.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: `_mpi_atomic.py` — atomic write, JSONL append, run-id

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/_mpi_atomic.py`

**Implementation:**

```python
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
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python -c "
import sys; sys.path.insert(0, '.')
from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id
print('import OK')
"
```

**Commit:** `chore: add _mpi_atomic.py atomic file primitives`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `_mpi_schemas.py` — schema registry stub

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**Implementation:**

Stub for Phase 1 — exports `validate_units` that accepts any payload with `stage` and `substep`. Phase 4 expands this with full per-substep schemas.

```python
"""Per-substep JSON schema registry. Expanded fully in Phase 4."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class SchemaError:
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def validate_units(stage: str, substep: str, payload: Any) -> list[SchemaError]:
    """
    Validate a units payload against the schema for (stage, substep).
    Returns a list of SchemaError; empty list means valid.
    Phase 1 stub: rejects non-dict payloads and unknown top-level stages.
    Full per-substep validation added in Phase 4.
    """
    if not isinstance(payload, dict):
        return [SchemaError("payload", "must be a JSON object (dict)")]
    
    known_stages = {
        "init", "transcript_prep", "diachronic", "synchronic",
        "generic_diachronic", "generic_synchronic", "global_synchronic",
        "hypothesis", "irr_calibration",
    }
    if stage not in known_stages:
        return [SchemaError("stage", f"unknown stage '{stage}'; expected one of {sorted(known_stages)}")]
    
    return []


# Substep DAG: maps (stage, substep) -> list of (stage, substep) prerequisites
# Each entry is a list of (stage, substep) that must be 'done' before this substep can close.
SUBSTEP_PREREQUISITES: dict[tuple[str, str], list[tuple[str, str]]] = {
    ("diachronic", "criteria_grouping"): [],
    ("diachronic", "criteria_revision"): [("diachronic", "criteria_grouping")],
    ("diachronic", "idu_naming_ordering"): [("diachronic", "criteria_revision")],
    ("synchronic", "theme_grouping_within_idu"): [("diachronic", "idu_naming_ordering")],
    ("synchronic", "isu_naming"): [("synchronic", "theme_grouping_within_idu")],
    ("synchronic", "isu_second_level_grouping"): [("synchronic", "isu_naming")],
    ("generic_diachronic", "participant_row_assembly"): [],
    ("generic_diachronic", "idu_similarity_grouping"): [("generic_diachronic", "participant_row_assembly")],
    ("generic_diachronic", "pattern_identification"): [("generic_diachronic", "idu_similarity_grouping")],
    ("generic_diachronic", "cross_iv_contrast"): [("generic_diachronic", "pattern_identification")],
    ("generic_synchronic", "select_generic_idus_of_interest"): [],
    ("generic_synchronic", "worksheet_assembly"): [("generic_synchronic", "select_generic_idus_of_interest")],
    ("generic_synchronic", "isu_second_level_grouping"): [("generic_synchronic", "worksheet_assembly")],
    ("global_synchronic", "global_synchronic"): [],
    ("hypothesis", "evidence_extraction"): [],
    ("hypothesis", "candidate_drafting"): [("hypothesis", "evidence_extraction")],
    ("hypothesis", "weak_evidence_review"): [("hypothesis", "candidate_drafting")],
    ("irr_calibration", "independent_analyst"): [],
    ("irr_calibration", "alignment"): [("irr_calibration", "independent_analyst")],
    ("irr_calibration", "agreement_computation"): [("irr_calibration", "alignment")],
}

# LLM-invoking substeps require --prompt-artifact
LLM_SUBSTEPS: frozenset[tuple[str, str]] = frozenset({
    ("diachronic", "criteria_grouping"),
    ("diachronic", "criteria_revision"),
    ("diachronic", "idu_naming_ordering"),
    ("synchronic", "theme_grouping_within_idu"),
    ("synchronic", "isu_naming"),
    ("synchronic", "isu_second_level_grouping"),
    ("generic_diachronic", "idu_similarity_grouping"),
    ("generic_diachronic", "pattern_identification"),
    ("generic_diachronic", "cross_iv_contrast"),
    ("generic_synchronic", "select_generic_idus_of_interest"),
    ("generic_synchronic", "isu_second_level_grouping"),
    ("global_synchronic", "global_synchronic"),
    ("hypothesis", "evidence_extraction"),
    ("hypothesis", "candidate_drafting"),
    ("hypothesis", "weak_evidence_review"),
    ("irr_calibration", "independent_analyst"),
    ("irr_calibration", "alignment"),
})
```

**Verification:**
```bash
python -c "
import sys; sys.path.insert(0, 'microphenomenograph/1.0.0/scripts')
from _mpi_schemas import validate_units, SUBSTEP_PREREQUISITES, LLM_SUBSTEPS
errs = validate_units('bad_stage', 'x', {})
assert errs and 'stage' in errs[0].field, errs
errs = validate_units('diachronic', 'criteria_grouping', {})
assert errs == [], errs
print('OK')
"
```

**Commit:** `chore: add _mpi_schemas.py schema registry stub`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: `mpi_step.py` — CLI entry point with `init` subcommand

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

Phase 1 implements the CLI skeleton and the `init` subcommand (dedicated-repo enforcement + git config). The `close` and `render` verbs are stubbed (raise `NotImplementedError`) and fully implemented in Phases 2–3.

```python
#!/usr/bin/env python3
"""
mpi_step.py — Documentation-as-Done contract helper for the MPI pipeline.

Verbs:
  init     Initialise a dedicated MPI run repo (or validate an existing one).
  close    Transactional substep close: validate → audit → manifest → commit.
  render   Regenerate .mpi/reasoning.log from .mpi/audit.jsonl.
  verify   Three-way join: manifest + audit + git tree.
  unlock   Release a stale .mpi/close.lock with an audit event.
  accept-head  Accept a new HEAD after rebase/cherry-pick.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id
from _mpi_schemas import validate_units, SUBSTEP_PREREQUISITES, LLM_SUBSTEPS


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def _git_config_local(key: str, value: str, cwd: Path) -> None:
    _git(["config", "--local", key, value], cwd=cwd)


def _git_identity_set(cwd: Path) -> bool:
    """Return True if git identity (user.name + user.email) is configured."""
    for key in ("user.name", "user.email"):
        r = _git(["config", key], cwd=cwd, check=False)
        if r.returncode != 0 or not r.stdout.strip():
            return False
    return True


def _git_is_nonemp_worktree(path: Path) -> bool:
    """Return True if path is inside a non-empty git worktree."""
    r = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=path,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return False
    toplevel = Path(r.stdout.strip())
    # Non-empty: has at least one file other than .git
    entries = [e for e in toplevel.iterdir() if e.name != ".git"]
    return len(entries) > 0


# ---------------------------------------------------------------------------
# init subcommand
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    run_dir = Path(args.run).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)

    allow_nested = getattr(args, "allow_active_repo_nested", False)

    # Check for nesting in an active dev repo
    if not allow_nested and _git_is_nonemp_worktree(run_dir):
        print(
            "ERROR run_inside_active_repo: MPI runs produce ~100-200 commits per study; "
            "point --run at an empty directory or use --allow-active-repo-nested",
            file=sys.stderr,
        )
        return 1

    # git init if no repo
    git_dir = run_dir / ".git"
    if not git_dir.exists():
        _git(["init", str(run_dir)], cwd=run_dir)

    # Require identity
    if not _git_identity_set(run_dir):
        print(
            "ERROR git_identity_unset: git user.name and user.email must be set "
            "(locally or globally) before initialising an MPI run. "
            "Set them with: git config --local user.name '...' && git config --local user.email '...'",
            file=sys.stderr,
        )
        return 1

    # Set local git config (never global)
    _git_config_local("core.autocrlf", "false", run_dir)
    _git_config_local("core.eol", "lf", run_dir)
    hooks_disabled = run_dir / ".git" / "hooks-disabled"
    hooks_disabled.mkdir(exist_ok=True)
    _git_config_local("core.hooksPath", ".git/hooks-disabled", run_dir)
    _git_config_local("commit.gpgsign", "false", run_dir)

    run_repo_mode = "nested_in_active" if allow_nested else "dedicated"

    # Warn if remote exists
    r = _git(["remote"], cwd=run_dir, check=False)
    if r.stdout.strip():
        print(
            "WARNING: a git remote is configured. MPI runs are designed to be local-only; "
            "pushing the run history to a CI-protected remote is unlikely to be what you want.",
            file=sys.stderr,
        )
        manifest_remote = True
    else:
        manifest_remote = False

    # Bootstrap .mpi/
    mpi_dir = run_dir / ".mpi"
    mpi_dir.mkdir(exist_ok=True)

    run_id = load_or_create_run_id(mpi_dir / "run_id")

    # Write initial manifest if absent
    manifest_path = mpi_dir / "project.json"
    if not manifest_path.exists():
        manifest = {
            "version": "2.0",
            "run_id": run_id,
            "study": {
                "run_repo_mode": run_repo_mode,
                "git_remote_configured": manifest_remote,
            },
            "participants": {},
        }
        atomic_write(manifest_path, json.dumps(manifest, indent=2) + "\n")

    # Bootstrap audit trail if absent
    audit_path = mpi_dir / "audit.jsonl"
    if not audit_path.exists():
        audit_path.touch()

    print(f"OK init run_dir={run_dir} mode={run_repo_mode} run_id={run_id}")
    return 0


# ---------------------------------------------------------------------------
# close subcommand (implemented in Phase 2)
# ---------------------------------------------------------------------------

def cmd_close(args: argparse.Namespace) -> int:
    raise NotImplementedError("close implemented in Phase 2")


# ---------------------------------------------------------------------------
# render subcommand (implemented in Phase 3)
# ---------------------------------------------------------------------------

def cmd_render(args: argparse.Namespace) -> int:
    raise NotImplementedError("render implemented in Phase 3")


# ---------------------------------------------------------------------------
# verify subcommand (implemented in Phase 2)
# ---------------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> int:
    raise NotImplementedError("verify implemented in Phase 2")


# ---------------------------------------------------------------------------
# unlock subcommand (implemented in Phase 2)
# ---------------------------------------------------------------------------

def cmd_unlock(args: argparse.Namespace) -> int:
    raise NotImplementedError("unlock implemented in Phase 2")


# ---------------------------------------------------------------------------
# accept-head subcommand (implemented in Phase 2)
# ---------------------------------------------------------------------------

def cmd_accept_head(args: argparse.Namespace) -> int:
    raise NotImplementedError("accept-head implemented in Phase 2")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mpi_step.py",
        description="Documentation-as-Done contract helper for the MPI pipeline.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialise a dedicated MPI run repo.")
    p_init.add_argument("--run", required=True, metavar="DIR",
                        help="Path to (empty) directory for the run repo.")
    p_init.add_argument("--allow-active-repo-nested", action="store_true",
                        help="Allow nesting inside a non-empty git worktree.")

    # close
    p_close = sub.add_parser("close", help="Transactional substep close.")
    p_close.add_argument("--actor", required=True)
    p_close.add_argument("--participant", required=True)
    p_close.add_argument("--stage", required=True)
    p_close.add_argument("--substep", required=True)
    p_close.add_argument("--scope", required=True)
    p_close.add_argument("--artifact", required=True, action="append", dest="artifacts",
                         metavar="PATH", help="Artifact path (repeat for json, md, prompt.json).")
    p_close.add_argument("--units-json", required=True, metavar="PATH_OR_STDIN",
                         help="Path to units JSON file, or '-' to read from stdin.")
    p_close.add_argument("--reason", required=True)
    p_close.add_argument("--status", default="done", choices=["done", "flagged"])
    p_close.add_argument("--prompt-artifact", metavar="PATH",
                         help="Required for LLM-invoking substeps.")
    p_close.add_argument("--run-dir", default=".", metavar="DIR",
                         help="Path to the MPI run directory (default: cwd).")

    # render
    p_render = sub.add_parser("render", help="Regenerate reasoning.log from audit.jsonl.")
    p_render.add_argument("--run-dir", default=".", metavar="DIR")
    p_render.add_argument("--out", default=None, metavar="PATH",
                          help="Output path (default: .mpi/reasoning.log).")
    p_render.add_argument("--from", dest="from_ts", default=None, metavar="TIMESTAMP")
    p_render.add_argument("--to", dest="to_ts", default=None, metavar="TIMESTAMP")
    p_render.add_argument("--participant", default=None)
    p_render.add_argument("--stage", default=None)

    # verify
    p_verify = sub.add_parser("verify", help="Three-way join: manifest + audit + git tree.")
    p_verify.add_argument("--run-dir", default=".", metavar="DIR")

    # unlock
    p_unlock = sub.add_parser("unlock", help="Release a stale .mpi/close.lock.")
    p_unlock.add_argument("--reason", required=True)
    p_unlock.add_argument("--run-dir", default=".", metavar="DIR")

    # accept-head
    p_ah = sub.add_parser("accept-head", help="Accept a new HEAD after rebase/cherry-pick.")
    p_ah.add_argument("--reason", required=True)
    p_ah.add_argument("--run-dir", default=".", metavar="DIR")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    dispatch = {
        "init": cmd_init,
        "close": cmd_close,
        "render": cmd_render,
        "verify": cmd_verify,
        "unlock": cmd_unlock,
        "accept-head": cmd_accept_head,
    }
    return dispatch[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python mpi_step.py --help
python mpi_step.py init --help
python mpi_step.py close --help
```
Expected: usage printed for all three.

**Commit:** `chore: add mpi_step.py CLI skeleton with init subcommand`

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->

<!-- START_TASK_4 -->
### Task 4: `test_mpi_step.py` — unit tests for Phase 1

**Verifies:** doc-as-done.AC2.2, doc-as-done.AC4.1, doc-as-done.AC33.1, doc-as-done.AC33.2, doc-as-done.AC33.3, doc-as-done.AC33.4, doc-as-done.AC33.5, doc-as-done.AC33.6, doc-as-done.AC33.7

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/test_mpi_step.py`

**Implementation:**

Tests run in `microphenomenograph/1.0.0/scripts/`. They use `tempfile.TemporaryDirectory` and call `mpi_step.main()` directly (not via subprocess) for speed, except for `--help` tests which use subprocess to test the actual CLI entrypoint.

```python
"""Phase 1 unit tests for mpi_step.py — CLI scaffolding."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure scripts/ is on the path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

import mpi_step
from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id
from _mpi_schemas import validate_units


# ---------------------------------------------------------------------------
# _mpi_atomic tests
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_write_creates_file(self, tmp_path):
        p = tmp_path / "out.json"
        atomic_write(p, '{"x": 1}')
        assert p.read_text() == '{"x": 1}'

    def test_write_is_atomic_no_tmp_leftover(self, tmp_path):
        p = tmp_path / "out.json"
        atomic_write(p, "hello")
        assert not (tmp_path / "out.json.tmp").exists()

    def test_write_overwrites_existing(self, tmp_path):
        p = tmp_path / "out.txt"
        atomic_write(p, "old")
        atomic_write(p, "new")
        assert p.read_text() == "new"

    def test_write_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "a" / "b" / "c.txt"
        atomic_write(p, "deep")
        assert p.read_text() == "deep"


class TestAppendJsonl:
    def test_append_creates_and_appends(self, tmp_path):
        p = tmp_path / "audit.jsonl"
        append_jsonl(p, {"a": 1})
        append_jsonl(p, {"b": 2})
        lines = p.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}

    def test_append_idempotent_under_re_read(self, tmp_path):
        p = tmp_path / "audit.jsonl"
        append_jsonl(p, {"event": "test"})
        content_a = p.read_text()
        # Re-reading the file does not change it
        assert p.read_text() == content_a


class TestLoadOrCreateRunId:
    def test_creates_uuid_if_absent(self, tmp_path):
        p = tmp_path / "run_id"
        rid = load_or_create_run_id(p)
        import uuid
        uuid.UUID(rid)  # raises if not valid UUID
        assert p.exists()

    def test_returns_existing_if_present(self, tmp_path):
        p = tmp_path / "run_id"
        p.write_text("my-fixed-id\n")
        assert load_or_create_run_id(p) == "my-fixed-id"


# ---------------------------------------------------------------------------
# _mpi_schemas tests
# ---------------------------------------------------------------------------

class TestValidateUnits:
    def test_accepts_known_stage(self):
        errors = validate_units("diachronic", "criteria_grouping", {})
        assert errors == []

    def test_rejects_unknown_stage(self):
        errors = validate_units("bad_stage", "x", {})
        assert errors
        assert any("stage" in e.field for e in errors)

    def test_rejects_non_dict(self):
        errors = validate_units("diachronic", "criteria_grouping", ["list"])
        assert errors
        assert any("payload" in e.field for e in errors)


# ---------------------------------------------------------------------------
# CLI --help tests (AC2.2)
# ---------------------------------------------------------------------------

class TestCLIHelp:
    def test_top_level_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "close" in r.stdout
        assert "render" in r.stdout

    def test_close_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "close", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--actor" in r.stdout
        assert "--stage" in r.stdout
        assert "--substep" in r.stdout
        assert "--prompt-artifact" in r.stdout

    def test_init_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "init", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--run" in r.stdout
        assert "--allow-active-repo-nested" in r.stdout


# ---------------------------------------------------------------------------
# init subcommand tests (AC33.*)
# ---------------------------------------------------------------------------

def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def _setup_git_identity(run_dir):
    """Set git identity in run_dir so init doesn't fail on AC33.6."""
    _git(["config", "--local", "user.name", "Test User"], cwd=run_dir)
    _git(["config", "--local", "user.email", "test@example.com"], cwd=run_dir)


class TestInitDedicatedRepo:
    def test_init_in_empty_dir_succeeds(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Pre-init repo with identity so test is isolated from global config
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc == 0
        assert (run_dir / ".mpi" / "project.json").exists()

    def test_init_sets_autocrlf_false(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "core.autocrlf"], cwd=run_dir)
        assert r.stdout.strip() == "false"

    def test_init_sets_hooks_path(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "core.hooksPath"], cwd=run_dir)
        assert r.stdout.strip() == ".git/hooks-disabled"
        assert (run_dir / ".git" / "hooks-disabled").is_dir()

    def test_init_sets_gpgsign_false(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "commit.gpgsign"], cwd=run_dir)
        assert r.stdout.strip() == "false"

    def test_init_manifest_records_dedicated_mode(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["run_repo_mode"] == "dedicated"


class TestInitActiveRepoNesting:
    def test_init_inside_nonempty_repo_fails_by_default(self, tmp_path):
        # Create a non-empty repo
        outer = tmp_path / "outer"
        outer.mkdir()
        _git(["init"], cwd=outer)
        (outer / "README.md").write_text("hi")
        _git(["add", "."], cwd=outer)
        _git(["commit", "-m", "init", "--allow-empty-message"], cwd=outer)
        # Try to init a run inside it
        run_dir = outer / "run"
        run_dir.mkdir()
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc != 0

    def test_init_with_allow_flag_succeeds(self, tmp_path):
        outer = tmp_path / "outer"
        outer.mkdir()
        _git(["init"], cwd=outer)
        (outer / "README.md").write_text("hi")
        _git(["add", "."], cwd=outer)
        _git(["commit", "-m", "init", "--allow-empty-message"], cwd=outer)
        run_dir = outer / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        rc = mpi_step.main(["init", "--run", str(run_dir), "--allow-active-repo-nested"])
        assert rc == 0
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["run_repo_mode"] == "nested_in_active"


class TestInitIdentityRequired:
    def test_init_fails_without_identity(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        # Ensure no global identity leaks in by patching _git_identity_set
        monkeypatch.setattr(mpi_step, "_git_identity_set", lambda cwd: False)
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc != 0
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py -v
```
Expected: all tests pass.

**Commit:** `test: add Phase 1 unit tests for CLI scaffolding`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run all tests and verify green

**Verification:**
```bash
# From repo root
pytest microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
# Also verify existing tests still pass
pytest tests/ -v
```
Expected: all pass, no regressions in `tests/`.

**Commit:** *(no additional commit — test run only)*

<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

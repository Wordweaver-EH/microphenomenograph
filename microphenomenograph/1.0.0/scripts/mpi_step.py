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


def _git_is_nonempty_worktree(path: Path) -> bool:
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
    if not allow_nested and _git_is_nonempty_worktree(run_dir):
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

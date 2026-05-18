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
# Manifest helpers
# ---------------------------------------------------------------------------

def _load_manifest(run_dir: Path) -> dict:
    path = run_dir / ".mpi" / "project.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_manifest(run_dir: Path, manifest: dict) -> None:
    path = run_dir / ".mpi" / "project.json"
    atomic_write(path, json.dumps(manifest, indent=2) + "\n")


def _get_substep_status(manifest: dict, participant: str, stage: str, substep: str) -> str:
    """Return status of a substep; 'pending' if not found."""
    p = manifest.get("participants", {}).get(participant, {})
    stages = p.get("stages", {})
    s = stages.get(stage, {})
    return s.get("substeps", {}).get(substep, {}).get("status", "pending")


def _derive_stage_status(substep_map: dict) -> str:
    """Derive stage status from substep statuses."""
    statuses = [v.get("status", "pending") for v in substep_map.values()]
    if not statuses:
        return "pending"
    if any(s == "error" for s in statuses):
        return "error"
    if any(s == "flagged" for s in statuses):
        return "flagged"
    if all(s == "done" for s in statuses):
        return "done"
    return "pending"


def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_head_sha(run_dir: Path) -> str | None:
    r = _git(["rev-parse", "HEAD"], cwd=run_dir, check=False)
    if r.returncode != 0:
        return None
    return r.stdout.strip()


def _build_audit_event(
    *,
    action: str,
    run_dir: Path,
    close_id: str,
    actor: str,
    participant: str,
    stage: str,
    substep: str,
    scope: str,
    reason: str,
    outcome: str = "success",
    extra: dict | None = None,
) -> dict:
    from datetime import datetime, timezone
    event = {
        "event_id": str(uuid.uuid4()),
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": load_or_create_run_id(run_dir / ".mpi" / "run_id"),
        "span_id": str(uuid.uuid4()),
        "actor": {"kind": "subagent", "name": actor},
        "event": {"kind": "event", "action": action, "outcome": outcome},
        "mpi": {
            "participant_id": participant,
            "stage": stage,
            "substep": substep,
            "scope": scope,
            "close_id": close_id,
        },
        "reason": reason,
    }
    if extra:
        event["mpi"].update(extra)
    return event


# ---------------------------------------------------------------------------
# close subcommand (implemented in Phase 2)
# ---------------------------------------------------------------------------

def cmd_close(args: argparse.Namespace) -> int:
    run_dir = Path(getattr(args, "run_dir", ".")).resolve()
    audit_path = run_dir / ".mpi" / "audit.jsonl"

    # --- Phase 1: close_attempted ---
    close_id = str(uuid.uuid4())
    try:
        manifest = _load_manifest(run_dir)
    except FileNotFoundError as e:
        print(f"ERROR manifest_not_found: {e}", file=sys.stderr)
        return 1

    parent_head_sha = _git_head_sha(run_dir)

    e_attempted = _build_audit_event(
        action="close_attempted",
        run_dir=run_dir,
        close_id=close_id,
        actor=args.actor,
        participant=args.participant,
        stage=args.stage,
        substep=args.substep,
        scope=args.scope,
        reason=args.reason,
        extra={"parent_head_sha": parent_head_sha},
    )
    append_jsonl(audit_path, e_attempted)

    def _abort(reason: str) -> int:
        """Emit a terminal close_aborted event (outcome=failure) then return 1."""
        e = _build_audit_event(
            action="close_aborted", outcome="failure",
            run_dir=run_dir, close_id=close_id, actor=args.actor,
            participant=args.participant, stage=args.stage, substep=args.substep,
            scope=args.scope, reason=reason,
        )
        append_jsonl(audit_path, e)
        return 1

    # --- Phase 2: artifacts_validated ---
    artifacts = args.artifacts or []
    for art_path in artifacts:
        p = Path(art_path)
        if not p.exists() or p.stat().st_size == 0:
            print(f"ERROR artifact_missing_or_empty: {art_path}", file=sys.stderr)
            return _abort(f"artifact_missing_or_empty: {art_path}")

    # Load and validate units-json
    units_json_arg = args.units_json
    if units_json_arg == "-":
        units_payload = json.load(sys.stdin)
    else:
        units_path = Path(units_json_arg)
        if not units_path.exists():
            print(f"ERROR units_json_not_found: {units_json_arg}", file=sys.stderr)
            return _abort(f"units_json_not_found: {units_json_arg}")
        units_payload = json.loads(units_path.read_text(encoding="utf-8"))

    schema_errors = validate_units(args.stage, args.substep, units_payload)
    if schema_errors:
        for err in schema_errors:
            print(f"ERROR schema_validation_failed: {err}", file=sys.stderr)
        return _abort(f"schema_validation_failed: {schema_errors[0]}")

    # Check LLM substep requires --prompt-artifact and validate it
    from _mpi_schemas import validate_prompt_artifact
    if (args.stage, args.substep) in LLM_SUBSTEPS:
        if not getattr(args, "prompt_artifact", None):
            msg = (f"prompt_artifact_required: substep ({args.stage}, {args.substep}) "
                   "is LLM-invoking and requires --prompt-artifact")
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)
        pa = Path(args.prompt_artifact)
        if not pa.exists():
            msg = f"prompt_artifact_not_found: {args.prompt_artifact}"
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)
        try:
            pa_data = json.loads(pa.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"prompt_artifact_invalid_json: {exc}"
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)
        pa_errors = validate_prompt_artifact(pa_data, check_agent_sha=False)
        if pa_errors:
            for err in pa_errors:
                print(f"ERROR prompt_artifact_schema_invalid: {err}", file=sys.stderr)
            return _abort(f"prompt_artifact_schema_invalid: {pa_errors[0]}")
    elif getattr(args, "prompt_artifact", None):
        msg = (f"prompt_artifact_unexpected: substep ({args.stage}, {args.substep}) "
               "is orchestrator-only and must NOT have --prompt-artifact")
        print(f"ERROR {msg}", file=sys.stderr)
        return _abort(msg)

    # Check substep DAG prerequisites
    prereqs = SUBSTEP_PREREQUISITES.get((args.stage, args.substep), [])
    for prereq_stage, prereq_substep in prereqs:
        status = _get_substep_status(manifest, args.participant, prereq_stage, prereq_substep)
        if status != "done":
            msg = (f"prereq_unsatisfied: ({prereq_stage}, {prereq_substep}) "
                   f"must be 'done' before closing ({args.stage}, {args.substep}); "
                   f"current status: {status}")
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)

    # Compute artifact SHAs
    artifact_shas = {}
    for art_path in artifacts:
        artifact_shas[art_path] = _sha256_file(Path(art_path))
    if getattr(args, "prompt_artifact", None):
        pa_path = str(args.prompt_artifact)
        artifact_shas[pa_path] = _sha256_file(Path(pa_path))

    e_validated = _build_audit_event(
        action="artifacts_validated",
        run_dir=run_dir,
        close_id=close_id,
        actor=args.actor,
        participant=args.participant,
        stage=args.stage,
        substep=args.substep,
        scope=args.scope,
        reason=args.reason,
        extra={"artifact_sha256": artifact_shas},
    )
    append_jsonl(audit_path, e_validated)

    # --- Phase 3: audit_appended ---
    # Write per-unit events
    # Extract flat list of analytic units from any substep payload shape.
    # Diachronic: payload["idus"]; synchronic top-level: payload["isus"];
    # synchronic nested (per-IDU): flatten payload["isus"] across IDU entries.
    _raw = units_payload if isinstance(units_payload, list) else units_payload.get("idus", units_payload.get("isus", []))
    if isinstance(_raw, list) and _raw and isinstance(_raw[0], dict) and "isus" in _raw[0]:
        # per-IDU shape: list of {idu_name, isus: [...]}
        units: list = [isu for idu_entry in _raw for isu in idu_entry.get("isus", [])]
    else:
        units = _raw if isinstance(_raw, list) else []
    e_audit = _build_audit_event(
        action="audit_appended",
        run_dir=run_dir,
        close_id=close_id,
        actor=args.actor,
        participant=args.participant,
        stage=args.stage,
        substep=args.substep,
        scope=args.scope,
        reason=args.reason,
        extra={
            "artifact_paths": artifacts,
            "prompt_artifact_path": getattr(args, "prompt_artifact", None),
            "n_units": len(units) if isinstance(units, list) else 0,
            "n_flagged": sum(1 for u in (units if isinstance(units, list) else []) if isinstance(u, dict) and u.get("flag_for_review")),
        },
    )
    append_jsonl(audit_path, e_audit)

    # --- Phase 4: manifest_replaced ---
    # Build new manifest — preserve existing structure, update substep entry
    manifest.setdefault("participants", {})
    manifest["participants"].setdefault(args.participant, {"stages": {}})
    manifest["participants"][args.participant].setdefault("stages", {})
    manifest["participants"][args.participant]["stages"].setdefault(args.stage, {"substeps": {}})
    stage_entry = manifest["participants"][args.participant]["stages"][args.stage]
    stage_entry.setdefault("substeps", {})

    stage_entry["substeps"][args.substep] = {
        "status": args.status,
        "output_paths": artifacts,
        "close_id": close_id,
        "parent_head_sha": parent_head_sha,
        "artifact_shas": artifact_shas,
        "expected_action": "git_commit_succeeded",
    }
    stage_entry["status"] = _derive_stage_status(stage_entry["substeps"])

    # Save a copy of the old manifest text for rollback (read_text avoids decode dance)
    manifest_path = run_dir / ".mpi" / "project.json"
    manifest_backup = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else "{}"

    try:
        _save_manifest(run_dir, manifest)
    except OSError as e:
        print(f"ERROR manifest_write_failed: {e}", file=sys.stderr)
        return _abort(f"manifest_write_failed: {e}")

    e_manifest = _build_audit_event(
        action="manifest_replaced",
        run_dir=run_dir,
        close_id=close_id,
        actor=args.actor,
        participant=args.participant,
        stage=args.stage,
        substep=args.substep,
        scope=args.scope,
        reason=args.reason,
    )
    append_jsonl(audit_path, e_manifest)

    # --- Phase 5: git_commit_succeeded / git_commit_failed ---
    add_paths = list(artifacts) + [str(manifest_path), str(audit_path)]
    if getattr(args, "prompt_artifact", None):
        add_paths.append(str(args.prompt_artifact))

    n_units = len(units) if isinstance(units, list) else 0
    n_flagged = sum(1 for u in (units if isinstance(units, list) else []) if u.get("flag_for_review"))
    commit_msg = f"mpi: {args.actor} {args.stage}.{args.substep} {args.scope} ({n_units}units {n_flagged}flagged)"

    r_add = _git(["add"] + add_paths, cwd=run_dir, check=False)
    if r_add.returncode != 0:
        print(f"ERROR git_add_failed: {r_add.stderr}", file=sys.stderr)
        # rollback manifest
        atomic_write(manifest_path, manifest_backup)
        e_rolled = _build_audit_event(
            action="manifest_rolled_back",
            outcome="failure",
            run_dir=run_dir, close_id=close_id, actor=args.actor,
            participant=args.participant, stage=args.stage, substep=args.substep,
            scope=args.scope, reason="git add failed",
        )
        append_jsonl(audit_path, e_rolled)
        return 1

    r_commit = _git(["commit", "-m", commit_msg], cwd=run_dir, check=False)
    if r_commit.returncode != 0:
        print(f"ERROR git_commit_failed: {r_commit.stderr}", file=sys.stderr)
        # rollback manifest
        atomic_write(manifest_path, manifest_backup)
        e_failed = _build_audit_event(
            action="git_commit_failed",
            outcome="failure",
            run_dir=run_dir, close_id=close_id, actor=args.actor,
            participant=args.participant, stage=args.stage, substep=args.substep,
            scope=args.scope, reason=r_commit.stderr.strip(),
        )
        append_jsonl(audit_path, e_failed)
        e_rolled = _build_audit_event(
            action="manifest_rolled_back",
            outcome="failure",
            run_dir=run_dir, close_id=close_id, actor=args.actor,
            participant=args.participant, stage=args.stage, substep=args.substep,
            scope=args.scope, reason="git commit failed",
        )
        append_jsonl(audit_path, e_rolled)
        return 1

    commit_sha = _git_head_sha(run_dir)
    e_success = _build_audit_event(
        action="git_commit_succeeded",
        run_dir=run_dir,
        close_id=close_id,
        actor=args.actor,
        participant=args.participant,
        stage=args.stage,
        substep=args.substep,
        scope=args.scope,
        reason=args.reason,
        extra={"git_commit_sha": commit_sha, "artifact_sha256": artifact_shas},
    )
    append_jsonl(audit_path, e_success)

    print(f"OK {args.scope} {args.stage}.{args.substep} commit={commit_sha[:7] if commit_sha else 'none'}")
    return 0


# ---------------------------------------------------------------------------
# render subcommand (implemented in Phase 3)
# ---------------------------------------------------------------------------

def cmd_render(args: argparse.Namespace) -> int:
    run_dir = Path(getattr(args, "run_dir", ".")).resolve()
    audit_path = run_dir / ".mpi" / "audit.jsonl"

    if not audit_path.exists():
        print(f"ERROR audit_not_found: {audit_path}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else run_dir / ".mpi" / "reasoning.log"

    lines_in = audit_path.read_text(encoding="utf-8").splitlines()
    rendered = []

    for i, raw_line in enumerate(lines_in, start=1):
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            ev = json.loads(raw_line)
        except json.JSONDecodeError:
            rendered.append(f"MALFORMED:{i}: {raw_line}")
            continue

        # Apply filters
        ts = ev.get("@timestamp", "")
        if args.from_ts and ts < args.from_ts:
            continue
        if args.to_ts and ts > args.to_ts:
            continue

        mpi = ev.get("mpi", {})
        participant = mpi.get("participant_id", "")
        stage = mpi.get("stage", "")
        substep = mpi.get("substep", "")
        action = ev.get("event", {}).get("action", "")
        actor_name = ev.get("actor", {}).get("name", "")
        reason = ev.get("reason", "")

        if args.participant and participant != args.participant:
            continue
        if args.stage and stage != args.stage:
            continue

        # Format the line
        stage_substep = f"{stage}.{substep}" if substep else stage
        n_units = mpi.get("n_units", "")
        n_flagged = mpi.get("n_flagged", "")
        commit_part = ""

        if action == "git_commit_succeeded":
            sha = mpi.get("git_commit_sha", "")
            commit_part = f" commit={sha[:7] if sha else '?'}"

        parts = [f"[{ts}]", actor_name, participant, f"{stage_substep}:"]
        detail = reason
        if n_units != "":
            detail += f". {n_units} units"
            if n_flagged:
                detail += f", {n_flagged} flagged"
        detail += commit_part
        parts.append(detail)

        rendered.append(" ".join(parts))

    output = "\n".join(rendered) + ("\n" if rendered else "")
    atomic_write(out_path, output)
    return 0


# ---------------------------------------------------------------------------
# verify subcommand (implemented in Phase 2)
# ---------------------------------------------------------------------------

def cmd_verify(args: argparse.Namespace) -> int:
    run_dir = Path(getattr(args, "run_dir", ".")).resolve()
    try:
        manifest = _load_manifest(run_dir)
    except FileNotFoundError as e:
        print(f"ERROR manifest_not_found: {e}", file=sys.stderr)
        return 1

    audit_path = run_dir / ".mpi" / "audit.jsonl"
    if not audit_path.exists():
        print("ERROR audit_not_found", file=sys.stderr)
        return 1

    # Load all audit events
    events = []
    for line in audit_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    # Build index: close_id -> git_commit_sha from git_commit_succeeded events
    commit_by_close: dict[str, str] = {}
    for ev in events:
        if ev.get("event", {}).get("action") == "git_commit_succeeded":
            cid = ev.get("mpi", {}).get("close_id")
            sha = ev.get("mpi", {}).get("git_commit_sha")
            if cid and sha:
                commit_by_close[cid] = sha

    failures = []
    for participant, pdata in manifest.get("participants", {}).items():
        for stage, sdata in pdata.get("stages", {}).items():
            for substep, ssdata in sdata.get("substeps", {}).items():
                if ssdata.get("status") != "done":
                    continue
                close_id = ssdata.get("close_id")
                if not close_id:
                    failures.append(f"{participant}/{stage}/{substep}: missing close_id in manifest")
                    continue
                sha = commit_by_close.get(close_id)
                if not sha:
                    failures.append(f"{participant}/{stage}/{substep}: no git_commit_succeeded event for close_id={close_id}")
                    continue
                # Verify the commit exists in git log
                r = _git(["cat-file", "-t", sha], cwd=run_dir, check=False)
                if r.stdout.strip() != "commit":
                    failures.append(f"{participant}/{stage}/{substep}: commit sha {sha} not found in git")

    if failures:
        for f in failures:
            print(f"FAIL {f}", file=sys.stderr)
        return 1

    print("OK all done substeps verified")
    return 0


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

#!/usr/bin/env python3
"""
mpi_step.py — Documentation-as-Done contract helper for the MPI pipeline.

Verbs:
  init          Initialise a dedicated MPI run repo (or validate an existing one).
  close         Transactional substep close: validate → audit → manifest → commit.
  render        Regenerate .mpi/reasoning.log from .mpi/audit.jsonl.
  verify        Three-way join: manifest + audit + git tree.
  unlock        Release a stale .mpi/close.lock with an audit event.
  accept-head   Accept a new HEAD after rebase/cherry-pick.
  acquire-lease Acquire a run-level exclusive lease (.mpi/run.lease).
  release-lease Release the run-level lease.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id, acquire_close_lock
from _mpi_schemas import (
    validate_units, validate_prompt_artifact,
    SUBSTEP_PREREQUISITES, LLM_SUBSTEPS, PREREQ_SCOPE_TRANSFORMS, COMPLETENESS_GATES,
)


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

    # Write .gitignore for transient runtime files so the run repo stays clean
    # between closes.  close.lock persists after release by design (AC4.3); without
    # this entry it would appear as an untracked file in git-status after every close.
    gitignore_path = mpi_dir / ".gitignore"
    if not gitignore_path.exists():
        atomic_write(gitignore_path, "# Transient runtime files — not tracked by git\nclose.lock\n")

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
                "calibration_transcript_ids": [],
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


def _prereq_participant_key(
    participant: str,
    prereq_stage: str,
    prereq_substep: str = "",
    downstream_stage: str = "",
    downstream_substep: str = "",
) -> str:
    """
    Derive the participant key for checking a prerequisite.

    Returns one of:
    - A string participant key (possibly transformed from the downstream key)
    - "all_match" sentinel — caller should use _all_candidate_draftings_done()

    Checks in order:
    1. PREREQ_SCOPE_TRANSFORMS table (new cross-participant edges)
    2. Legacy synchronic -> diachronic strip (preserved for backward compat)
    3. Default: return participant unchanged
    """
    # 1. Consult PREREQ_SCOPE_TRANSFORMS when enough context is provided
    if downstream_stage and downstream_substep and prereq_stage and prereq_substep:
        key = (downstream_stage, downstream_substep, prereq_stage, prereq_substep)
        transform = PREREQ_SCOPE_TRANSFORMS.get(key)
        if transform is not None:
            if transform == "all_match":
                return "all_match"
            # transform is a callable: apply it to the current participant scope
            return transform(participant)

    # 2. Legacy: synchronic -> diachronic scope strip
    if prereq_stage == "diachronic" and "-idu" in participant:
        idx = participant.rfind("-idu")
        if idx > 0:
            return participant[:idx]

    # 3. Default: unchanged
    return participant


def _get_substep_status(manifest: dict, participant: str, stage: str, substep: str) -> str:
    """Return status of a substep; 'pending' if not found."""
    p = manifest.get("participants", {}).get(participant, {})
    stages = p.get("stages", {})
    s = stages.get(stage, {})
    return s.get("substeps", {}).get(substep, {}).get("status", "pending")


def _all_candidate_draftings_done(
    manifest: dict,
    prereq_stage: str,
    prereq_substep: str,
) -> bool:
    """
    All-match gate: every manifest entry for (prereq_stage, prereq_substep)
    across all participant keys must have status 'done'.

    Returns False if:
    - No matching entries exist at all (nothing done yet)
    - Any matching entry has status other than 'done'

    When study.dv_focuses is non-null, additionally checks that every
    declared focus has a matching entry (not just present-in-manifest ones).
    This is the Phase 8 extension point; for now (Phases 1-7) dv_focuses
    is always null, so only the manifest-scan path is needed.
    """
    participants = manifest.get("participants", {})
    found_any = False
    dv_focuses = manifest.get("study", {}).get("dv_focuses")

    for pid, pdata in participants.items():
        stages = pdata.get("stages", {})
        stage_data = stages.get(prereq_stage, {})
        substeps = stage_data.get("substeps", {})
        if prereq_substep in substeps:
            found_any = True
            if substeps[prereq_substep].get("status") != "done":
                return False

    if not found_any:
        return False

    # Phase 8 extension: if dv_focuses is declared, check all are present
    if dv_focuses is not None:
        for focus in dv_focuses:
            focus_key = f"dv-{focus}"
            p = participants.get(focus_key, {})
            status = (p.get("stages", {})
                       .get(prereq_stage, {})
                       .get("substeps", {})
                       .get(prereq_substep, {})
                       .get("status"))
            if status != "done":
                return False

    return True


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
    actor_kind: str = "subagent",
    extra: dict | None = None,
) -> dict:
    from datetime import datetime, timezone
    event = {
        "event_id": str(uuid.uuid4()),
        "@timestamp": datetime.now(timezone.utc).isoformat(),
        "trace_id": load_or_create_run_id(run_dir / ".mpi" / "run_id"),
        "span_id": str(uuid.uuid4()),
        "actor": {"kind": actor_kind, "name": actor},
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
# Units extraction helper
# ---------------------------------------------------------------------------

def _extract_units(payload: dict | list) -> list:
    """
    Extract a flat list of analytic units from a substep payload.
    Handles three shapes:
    1. Diachronic: payload["idus"]
    2. Synchronic flat: payload["isus"]
    3. Synchronic nested (per-IDU): payload["isus"] = [{idu_name, isus: [...]}]
    Returns a flat list of unit dicts; empty list if no units found.
    """
    _raw = payload if isinstance(payload, list) else payload.get("idus", payload.get("isus", []))
    if isinstance(_raw, list) and _raw and isinstance(_raw[0], dict) and "isus" in _raw[0]:
        # per-IDU shape: list of {idu_name, isus: [...]}
        return [isu for idu_entry in _raw for isu in idu_entry.get("isus", [])]
    else:
        return _raw if isinstance(_raw, list) else []


# ---------------------------------------------------------------------------
# Task 3: Cascade reset (AC16.1, AC16.2, AC30.1–AC30.3)
# ---------------------------------------------------------------------------

# Substeps affected by a criteria_revision re-close for a given scope (pNsN)
_CASCADE_DIACHRONIC_SUBSTEPS = ["idu_naming_ordering"]
_CASCADE_SYNCHRONIC_SUBSTEPS = [
    "theme_grouping_within_idu",
    "isu_naming",
    "isu_second_level_grouping",
]
# Cross-participant stages and substeps reset when any transcript's criteria_revision is re-closed
_CASCADE_CROSS_PARTICIPANT_STAGES = {
    "generic_diachronic": [
        "participant_row_assembly",
        "idu_similarity_grouping",
        "pattern_identification",
        "cross_iv_contrast",
    ],
    "generic_synchronic": [
        "select_generic_idus_of_interest",
        "worksheet_assembly",
        "isu_second_level_grouping",
    ],
    "global_synchronic": ["global_synchronic"],
    "hypothesis": ["evidence_extraction", "candidate_drafting", "weak_evidence_review"],
}


def _cascade_reset(
    run_dir: Path,
    scope: str,
    revision_close_id: str,
    manifest: dict,
    audit_path: Path,
    actor: str,
    actor_kind: str,
) -> dict:
    """
    Cascade reset for pNsN after a criteria_revision re-close:
    1. Move affected artifact files to analyses/_superseded/<revision_close_id>/
    2. Write tombstone.json in _superseded/<revision_close_id>/
    3. Reset affected substep statuses to 'pending' in manifest (single write)
    4. Emit one cascade_reset audit event per reset substep
    Returns updated manifest dict.
    """
    analyses_dir = run_dir / "analyses"

    reset_substep_labels: list[str] = []
    # Collect (art_scope, art_stage, art_substep) tuples to move — file movement
    # is deferred until after we know the superseded_dir path.
    reset_file_moves: list[tuple[str, str, str]] = []
    participants = manifest.get("participants", {})

    def _check_substep(p_key: str, stage: str, substep: str, art_scope: str) -> bool:
        """
        Return True if the substep is 'done' (i.e. will be reset).
        Collects the file-move tuple for later; does NOT move files yet
        (superseded_dir is not yet defined at this point).
        """
        p_data = participants.get(p_key, {})
        stage_data = p_data.get("stages", {}).get(stage, {})
        substep_data = stage_data.get("substeps", {}).get(substep, {})
        if substep_data.get("status") == "done":
            reset_file_moves.append((art_scope, stage, substep))
            return True
        return False

    # --- Collect diachronic downstream substeps for scope (pNsN) ---
    for substep in _CASCADE_DIACHRONIC_SUBSTEPS:
        if _check_substep(scope, "diachronic", substep, scope):
            reset_substep_labels.append(f"{scope} diachronic.{substep}")

    # --- Collect all synchronic substeps for all iduN scopes under this transcript ---
    idu_prefix = f"{scope}-idu"
    for p_key in list(participants.keys()):
        if p_key.startswith(idu_prefix):
            for substep in _CASCADE_SYNCHRONIC_SUBSTEPS:
                if _check_substep(p_key, "synchronic", substep, p_key):
                    reset_substep_labels.append(f"{p_key} synchronic.{substep}")

    # --- Collect cross-participant stages ---
    # Cross-participant stages use non-pNsN keys; we look for any participant key
    # matching the stage (generic/global/hypothesis) regardless of scope
    for cross_stage, cross_substeps in _CASCADE_CROSS_PARTICIPANT_STAGES.items():
        for p_key in list(participants.keys()):
            for substep in cross_substeps:
                if _check_substep(p_key, cross_stage, substep, p_key):
                    reset_substep_labels.append(f"{p_key} {cross_stage}.{substep}")

    if not reset_substep_labels:
        # Nothing downstream was done — no cascade needed
        return manifest

    # Create _superseded directory only now that we know resets will occur
    superseded_dir = analyses_dir / "_superseded" / revision_close_id
    superseded_dir.mkdir(parents=True, exist_ok=True)

    # Move artifact files into superseded_dir
    for art_scope, art_stage, art_substep in reset_file_moves:
        for ext in ("json", "md", "prompt.json"):
            src = analyses_dir / f"{art_scope}-{art_stage}.{art_substep}.{ext}"
            if src.exists():
                dst = superseded_dir / f"{art_scope}-{art_stage}.{art_substep}.{ext}"
                try:
                    os.rename(str(src), str(dst))
                except OSError:
                    pass  # Non-fatal: continue cascade

    # --- Write tombstone ---
    tombstone = {
        "cascade_source": revision_close_id,
        "reset_at": datetime.now(timezone.utc).isoformat(),
        "reset_substeps": reset_substep_labels,
        "reason": "diachronic.criteria_revision re-close triggered cascade",
    }
    tombstone_path = superseded_dir / "tombstone.json"
    atomic_write(tombstone_path, json.dumps(tombstone, indent=2) + "\n")

    # --- Emit audit events BEFORE manifest write ---
    run_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
    for label in reset_substep_labels:
        parts = label.split(" ", 1)
        label_scope = parts[0] if parts else ""
        stage_substep = parts[1] if len(parts) > 1 else ""
        stage_part, _, substep_part = stage_substep.partition(".")
        cascade_event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": run_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": actor_kind, "name": actor},
            "event": {"kind": "event", "action": "cascade_reset", "outcome": "success"},
            "mpi": {
                "participant_id": label_scope,
                "stage": stage_part,
                "substep": substep_part,
                "scope": label_scope,
                "close_id": str(uuid.uuid4()),
                "cascade_source": revision_close_id,
            },
            "reason": f"cascade reset triggered by criteria_revision re-close {revision_close_id}",
        }
        append_jsonl(audit_path, cascade_event)

    # --- Update manifest: reset all affected substeps to pending ---
    # Apply resets based on our label list
    for label in reset_substep_labels:
        parts = label.split(" ", 1)
        label_scope = parts[0] if parts else ""
        stage_substep = parts[1] if len(parts) > 1 else ""
        stage_part, _, substep_part = stage_substep.partition(".")
        p_data = participants.get(label_scope, {})
        stage_data = p_data.get("stages", {}).get(stage_part, {})
        substep_data = stage_data.get("substeps", {}).get(substep_part)
        if substep_data is not None:
            substep_data["status"] = "pending"
            substep_data["output_paths"] = []
            # Derive new stage status
            substeps_map = stage_data.get("substeps", {})
            stage_data["status"] = _derive_stage_status(substeps_map)

    return manifest


# ---------------------------------------------------------------------------
# Task 4: Run-lease and substep-reservation (AC20.6, AC20.7)
# ---------------------------------------------------------------------------

def _acquire_run_lease(run_dir: Path, run_id: str, audit_path: Path) -> int:
    """
    Write .mpi/run.lease = {pid, hostname, run_id, started_at, command}.
    If lease file exists and holder PID is alive on same host: exit with run_lease_held.
    If lease file exists and holder PID is dead: auto-reclaim (emit stale_lease_reclaimed event).
    Cross-host: refuse with cross_host_lease_unresolvable.
    Returns 0 on success, 1 on failure.
    """
    lease_path = run_dir / ".mpi" / "run.lease"
    current_hostname = socket.gethostname()
    current_pid = os.getpid()

    if lease_path.exists():
        try:
            existing = json.loads(lease_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

        holder_hostname = existing.get("hostname", "")
        holder_pid = existing.get("pid")

        if holder_hostname and holder_hostname != current_hostname:
            # Cross-host: cannot resolve
            print(
                f"ERROR cross_host_lease_unresolvable: lease held by {holder_hostname} "
                f"(PID {holder_pid}); current host is {current_hostname}. "
                "Manually remove .mpi/run.lease to proceed.",
                file=sys.stderr,
            )
            return 1

        # Same host: check if PID is alive
        pid_alive = False
        if holder_pid is not None:
            try:
                os.kill(int(holder_pid), 0)  # Signal 0 = check existence
                pid_alive = True
            except (ProcessLookupError, PermissionError, ValueError):
                pid_alive = False

        if pid_alive:
            print(
                f"ERROR run_lease_held: lease held by PID {holder_pid} on {holder_hostname} "
                f"(started {existing.get('started_at', '?')}). "
                "Wait for the run to complete or kill that process.",
                file=sys.stderr,
            )
            return 1

        # PID is dead — reclaim
        trace_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
        reclaim_event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": trace_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "orchestrator", "name": "mpi_step"},
            "event": {"kind": "event", "action": "stale_lease_reclaimed", "outcome": "success"},
            "mpi": {
                "stale_pid": holder_pid,
                "stale_hostname": holder_hostname,
                "stale_started_at": existing.get("started_at"),
            },
            "reason": f"stale lease from dead PID {holder_pid} reclaimed",
        }
        if audit_path.exists():
            append_jsonl(audit_path, reclaim_event)

    # Write the new lease
    lease_data = {
        "pid": current_pid,
        "hostname": current_hostname,
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "command": " ".join(sys.argv),
    }
    atomic_write(lease_path, json.dumps(lease_data, indent=2) + "\n")
    return 0


def _release_run_lease(run_dir: Path) -> None:
    """Remove .mpi/run.lease. Called on normal exit and by signal handlers (SIGINT, SIGTERM)."""
    lease_path = run_dir / ".mpi" / "run.lease"
    try:
        if lease_path.exists():
            lease_path.unlink()
    except OSError:
        pass


def _acquire_substep_reservation(
    run_dir: Path,
    stage: str,
    substep: str,
    scope: str,
    close_id: str,
    artifacts: list[str],
) -> int:
    """
    Write analyses/<scope>-<stage>.<substep>.reservation.json = {close_id, pid, started_at,
    intended_artifact_paths}.
    If reservation file exists for same (stage, substep, scope): exit with substep_reservation_held.
    Returns 0 on success, 1 if reservation is held.
    """
    analyses_dir = run_dir / "analyses"
    analyses_dir.mkdir(exist_ok=True)
    reservation_path = analyses_dir / f"{scope}-{stage}.{substep}.reservation.json"

    if reservation_path.exists():
        try:
            existing = json.loads(reservation_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}
        print(
            f"ERROR substep_reservation_held: reservation exists for "
            f"({stage}, {substep}, {scope}) with close_id={existing.get('close_id', '?')} "
            f"PID={existing.get('pid', '?')}. "
            "Wait for the in-progress close to complete.",
            file=sys.stderr,
        )
        return 1

    reservation_data = {
        "close_id": close_id,
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "intended_artifact_paths": artifacts,
    }
    # Use direct write (not atomic_write) for the reservation lock file;
    # it is a coordination token, not a safety-critical data file.
    try:
        reservation_path.write_text(
            json.dumps(reservation_data, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        # Best-effort: if we can't write the reservation, skip it (non-fatal)
        pass
    return 0


def _release_substep_reservation(
    run_dir: Path,
    stage: str,
    substep: str,
    scope: str,
) -> None:
    """Remove the reservation file. Called on git_commit_succeeded or manifest_rolled_back."""
    reservation_path = run_dir / "analyses" / f"{scope}-{stage}.{substep}.reservation.json"
    try:
        if reservation_path.exists():
            reservation_path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Task 4: Acquire/release-lease subcommands
# ---------------------------------------------------------------------------

def cmd_acquire_lease(args: argparse.Namespace) -> int:
    run_dir = Path(getattr(args, "run_dir", ".")).resolve()
    mpi_dir = run_dir / ".mpi"
    if not mpi_dir.exists():
        print(f"ERROR mpi_not_initialised: {mpi_dir} does not exist", file=sys.stderr)
        return 1
    run_id = load_or_create_run_id(mpi_dir / "run_id")
    audit_path = mpi_dir / "audit.jsonl"
    rc = _acquire_run_lease(run_dir, run_id, audit_path)
    if rc == 0:
        print(f"OK lease acquired run_id={run_id} pid={os.getpid()}")

        # Register signal handlers to release the lease on interrupt/termination
        def _on_signal(signum, frame):
            _release_run_lease(run_dir)
            sys.exit(1)

        try:
            signal.signal(signal.SIGINT, _on_signal)
            signal.signal(signal.SIGTERM, _on_signal)
        except (OSError, ValueError):
            pass  # Signal registration is best-effort

    return rc


def cmd_release_lease(args: argparse.Namespace) -> int:
    run_dir = Path(getattr(args, "run_dir", ".")).resolve()
    _release_run_lease(run_dir)
    print(f"OK lease released run_dir={run_dir}")
    return 0


# ---------------------------------------------------------------------------
# Task 5: Span offset resolution (AC28.3, AC28.4)
# ---------------------------------------------------------------------------

def _validate_utterance_refs(
    run_dir: Path,
    units_payload: dict,
    stage: str,
    substep: str,
    manifest: dict,
) -> list[str]:
    """
    Validate all utterance_refs in the units payload against the offset registry.

    Handles TWO payload shapes:

    SHAPE A — per-transcript analytic units (diachronic, synchronic,
    generic_diachronic, generic_synchronic, global_synchronic):
      Each unit is a dict with a top-level 'utterance_refs' list.
      Check each unit: if utterance_refs is empty/missing → 'missing_span_refs'.
      Validate each ref (see steps 1-4 below).

    SHAPE B — hypothesis candidates (hypothesis.candidate_drafting,
    hypothesis.evidence_extraction):
      Spans are nested: units_payload['candidates'][i]['claims'][j]
        ['{supports|contradicts|ambiguous}'][k]['raw_span_refs']
      Each raw_span_refs entry is a {transcript_id, utterance_number,
      byte_start, byte_end, raw_excerpt} object.

    For each ref object:
    1. Load transcripts/offsets/<transcript_id>.json
       → 'offset_registry_missing' if file absent
    2. Look up utterance_number → raw byte range
       → 'span_out_of_range' if utterance_number not in registry
    3. Read raw bytes from transcripts/raw/<transcript_id>.txt[byte_start:byte_end]
       → 'span_out_of_range' if byte range outside file
    4. Decode as UTF-8, compare to ref['raw_excerpt']
       → 'span_excerpt_mismatch' if mismatch (include both excerpts in message)

    Returns list of error strings (empty = all valid).
    """
    errors: list[str] = []
    # Cache loaded registries to avoid repeated disk reads
    registry_cache: dict[str, dict] = {}
    raw_file_cache: dict[str, bytes] = {}

    # Early-exit: if the entire transcripts/offsets/ directory doesn't exist,
    # skip span validation (pipeline hasn't run transcript_prep yet).
    offsets_dir = run_dir / "transcripts" / "offsets"
    if not offsets_dir.is_dir():
        return errors  # Not yet initialized; skip validation

    def _validate_ref(ref: dict, ref_label: str) -> list[str]:
        """Validate a single utterance/span ref object."""
        ref_errors: list[str] = []
        if not isinstance(ref, dict):
            return [f"{ref_label}: must be an object"]

        transcript_id = ref.get("transcript_id", "")
        utterance_number = ref.get("utterance_number")
        byte_start = ref.get("byte_start")
        byte_end = ref.get("byte_end")
        raw_excerpt = ref.get("raw_excerpt", "")

        # Step 1: Load offset registry
        if transcript_id not in registry_cache:
            registry_file = offsets_dir / f"{transcript_id}.json"
            if not registry_file.exists():
                return [
                    f"offset_registry_missing: transcripts/offsets/{transcript_id}.json "
                    f"not found — run transcript_prep.register_offsets before any LLM substep"
                ]
            try:
                registry_cache[transcript_id] = json.loads(
                    registry_file.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError) as exc:
                return [f"offset_registry_missing: failed to load {transcript_id}.json: {exc}"]

        registry = registry_cache[transcript_id]

        # Step 2: Look up utterance_number (registry keys are always strings)
        unum_key = str(utterance_number) if utterance_number is not None else None

        unum_entry = registry.get(unum_key)
        if unum_entry is None:
            ref_errors.append(
                f"span_out_of_range: {ref_label}: utterance_number={utterance_number} "
                f"not in offset registry for {transcript_id}"
            )
            return ref_errors

        # Validate byte range against utterance's registered range
        if byte_start is None or byte_end is None:
            return ref_errors  # Schema already validates required fields
        utt_byte_start = unum_entry.get("byte_start")
        utt_byte_end = unum_entry.get("byte_end")
        if utt_byte_start is not None and utt_byte_end is not None:
            if not (utt_byte_start <= byte_start <= byte_end <= utt_byte_end):
                ref_errors.append(
                    f"span_out_of_range: {ref_label}: "
                    f"ref byte range [{byte_start}:{byte_end}] outside utterance range "
                    f"[{utt_byte_start}:{utt_byte_end}] for {transcript_id}.{utterance_number}"
                )
                return ref_errors

        # Step 3: Load raw transcript bytes
        if transcript_id not in raw_file_cache:
            raw_file = run_dir / "transcripts" / "raw" / f"{transcript_id}.txt"
            if not raw_file.exists():
                # Try without extension
                raw_file_noext = run_dir / "transcripts" / "raw" / transcript_id
                if raw_file_noext.exists():
                    raw_file = raw_file_noext
                else:
                    ref_errors.append(
                        f"offset_registry_missing: transcripts/raw/{transcript_id}.txt "
                        "not found"
                    )
                    return ref_errors
            try:
                raw_file_cache[transcript_id] = raw_file.read_bytes()
            except OSError as exc:
                ref_errors.append(
                    f"offset_registry_missing: failed to read {transcript_id}.txt: {exc}"
                )
                return ref_errors

        raw_bytes = raw_file_cache[transcript_id]
        file_size = len(raw_bytes)

        # Validate byte range
        if byte_start is None or byte_end is None:
            return ref_errors  # Schema already validates required fields

        if not (0 <= byte_start <= byte_end <= file_size):
            ref_errors.append(
                f"span_out_of_range: {ref_label}: "
                f"byte range [{byte_start}:{byte_end}] outside file size {file_size} "
                f"for {transcript_id}.txt"
            )
            return ref_errors

        # Step 4: Compare raw_excerpt
        try:
            actual_text = raw_bytes[byte_start:byte_end].decode("utf-8")
        except UnicodeDecodeError as exc:
            ref_errors.append(
                f"span_out_of_range: {ref_label}: "
                f"byte range [{byte_start}:{byte_end}] is not valid UTF-8: {exc}"
            )
            return ref_errors

        if actual_text != raw_excerpt:
            ref_errors.append(
                f"span_excerpt_mismatch: {ref_label}: "
                f"expected={raw_excerpt!r} actual={actual_text!r} "
                f"(transcript={transcript_id}, utterance={utterance_number}, "
                f"bytes=[{byte_start}:{byte_end}])"
            )

        return ref_errors

    # --- Determine payload shape ---
    is_hypothesis = stage == "hypothesis" and substep in (
        "candidate_drafting", "evidence_extraction"
    )

    if is_hypothesis:
        # SHAPE B: hypothesis candidates with nested raw_span_refs
        candidates = units_payload.get("candidates", [])
        if not isinstance(candidates, list):
            return errors
        for i, cand in enumerate(candidates):
            if not isinstance(cand, dict):
                continue
            claims = cand.get("claims", [])
            if not isinstance(claims, list):
                continue
            for j, claim in enumerate(claims):
                if not isinstance(claim, dict):
                    continue
                # Check if claim has any span-bearing evidence
                supports = claim.get("supports", [])
                contradicts = claim.get("contradicts", [])
                ambiguous = claim.get("ambiguous", [])
                has_not_applicable = "not_applicable" in claim

                all_evidence_lists = [supports, contradicts, ambiguous]
                all_empty = all(
                    not isinstance(ev_list, list) or len(ev_list) == 0
                    for ev_list in all_evidence_lists
                )
                if all_empty and not has_not_applicable:
                    errors.append(
                        f"missing_span_refs: candidates[{i}].claims[{j}]: "
                        "must have at least one non-empty supports/contradicts/ambiguous "
                        "or an explicit not_applicable field"
                    )
                    continue

                for ev_type in ("supports", "contradicts", "ambiguous"):
                    ev_list = claim.get(ev_type, [])
                    if not isinstance(ev_list, list):
                        continue
                    for k, evidence in enumerate(ev_list):
                        if not isinstance(evidence, dict):
                            continue
                        raw_span_refs = evidence.get("raw_span_refs", [])
                        if not isinstance(raw_span_refs, list) or len(raw_span_refs) == 0:
                            continue
                        for m, ref in enumerate(raw_span_refs):
                            label = (
                                f"candidates[{i}].claims[{j}].{ev_type}[{k}]"
                                f".raw_span_refs[{m}]"
                            )
                            errors.extend(_validate_ref(ref, label))
    else:
        # SHAPE A: per-transcript analytic units with utterance_refs
        # Extract units using the same logic as _extract_units
        units = _extract_units(units_payload)
        for idx, unit in enumerate(units):
            if not isinstance(unit, dict):
                continue
            refs = unit.get("utterance_refs")
            if refs is None or (isinstance(refs, list) and len(refs) == 0):
                errors.append(
                    f"missing_span_refs: unit[{idx}]: "
                    "utterance_refs is missing or empty"
                )
                continue
            if not isinstance(refs, list):
                errors.append(
                    f"missing_span_refs: unit[{idx}]: utterance_refs must be a list"
                )
                continue
            for i, ref in enumerate(refs):
                label = f"unit[{idx}].utterance_refs[{i}]"
                errors.extend(_validate_ref(ref, label))

    return errors


# ---------------------------------------------------------------------------
# IRR calibration helpers (Phase 13)
# ---------------------------------------------------------------------------

def _get_calibration_transcript_ids(manifest: dict) -> set:
    """
    Get the set of calibration transcript IDs from the manifest.
    Reads calibration_transcript_ids field (list of transcript IDs).
    If not present or empty, returns an empty set.

    Args:
        manifest: project.json parsed dict

    Returns: set of transcript IDs (e.g., {"p1s1", "p2s3"})
    """
    study = manifest.get("study", {})
    cal_ids = study.get("calibration_transcript_ids", [])
    if isinstance(cal_ids, list):
        return set(cal_ids)
    return set()


def _load_irr_records(run_dir: Path) -> list:
    """
    Load IRR calibration records from .mpi/irr_calibration.jsonl.
    Returns list of dicts, or [] if file doesn't exist.
    """
    irr_path = run_dir / ".mpi" / "irr_calibration.jsonl"
    if not irr_path.exists():
        return []
    records = []
    try:
        with open(irr_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except (json.JSONDecodeError, OSError):
        return []
    return records


def _is_last_synchronic_idu(manifest: dict, transcript_id: str) -> bool:
    """
    Check if all IDU scopes for transcript_id have synchronic.isu_second_level_grouping done.
    Returns True if all IDUs of this transcript have synchronic.isu_second_level_grouping done.
    """
    participants = manifest.get("participants", {})
    all_done = True
    found_any = False
    for pid, pdata in participants.items():
        # Check if this participant is for the target transcript
        if not pid.startswith(transcript_id + "-idu"):
            continue
        found_any = True
        stages = pdata.get("stages", {})
        synchronic = stages.get("synchronic", {})
        isu_status = synchronic.get("substeps", {}).get("isu_second_level_grouping", {})
        if isu_status.get("status") != "done":
            all_done = False
            break
    return found_any and all_done


def _maybe_trigger_irr_calibration(
    run_dir: Path,
    stage: str,
    substep: str,
    scope: str,
    manifest: dict,
    close_id: str,
    audit_path: Path,
) -> None:
    """
    Check if the just-closed substep triggers IRR calibration.
    Fires for:
      - diachronic.idu_naming_ordering: scope is pNsN (transcript scope)
      - synchronic.isu_second_level_grouping (last IDU): scope is pNsN-iduN

    Appends irr_calibration_scheduled audit event if triggered.
    """
    calibration_ids = _get_calibration_transcript_ids(manifest)

    # Derive transcript_id from scope (handles both pNsN and pNsN-iduN forms)
    transcript_id = scope.split("-idu")[0]  # "p1s1-idu2" → "p1s1"; "p1s1" → "p1s1"

    if transcript_id not in calibration_ids:
        return

    trigger_irr = False
    irr_stage = None

    if stage == "diachronic" and substep == "idu_naming_ordering":
        trigger_irr = True
        irr_stage = "diachronic"
    elif stage == "synchronic" and substep == "isu_second_level_grouping":
        # Only trigger after LAST IDU for this transcript
        if _is_last_synchronic_idu(manifest, transcript_id):
            trigger_irr = True
            irr_stage = "synchronic"

    if trigger_irr and irr_stage:
        run_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
        event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": run_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "orchestrator", "name": "orchestrator"},
            "event": {"kind": "event", "action": "irr_calibration_scheduled", "outcome": "success"},
            "mpi": {
                "stage": irr_stage,
                "transcript_id": transcript_id,
                "triggered_by": f"{stage}.{substep}",
            },
            "reason": f"Calibration transcript {transcript_id} {irr_stage} stage complete",
        }
        append_jsonl(audit_path, event)


def _check_irr_gate(
    run_dir: Path,
    stage: str,
    substep: str,
    scope: str,
    args,
    audit_path: Path,
) -> int:
    """
    At the start of each cross-participant close, check IRR calibration outcome.

    Maps cross-participant stages to upstream IRR stage:
      - generic_diachronic → diachronic
      - generic_synchronic → synchronic
      - global_synchronic → synchronic
      - hypothesis → synchronic

    Filters irr_calibration.jsonl to records matching the upstream stage.
    If any matching record has outcome != "passed": ALWAYS emit irr_warning audit event.
    - Without --strict-irr: proceed (return 0).
    - With --strict-irr: exit with irr_check_failed (return 1).
    """
    # Map cross-participant stages to upstream IRR stages
    stage_to_irr_stage = {
        "generic_diachronic": "diachronic",
        "generic_synchronic": "synchronic",
        "global_synchronic": "synchronic",
        "hypothesis": "synchronic",
    }
    irr_stage = stage_to_irr_stage.get(stage)
    if not irr_stage:
        # Not a cross-participant stage, skip IRR check
        return 0

    irr_records = _load_irr_records(run_dir)
    # Filter records to those matching the upstream stage
    stage_records = [r for r in irr_records if r.get("stage") == irr_stage]

    # Determine outcome: if no records, outcome is None (irr_missing).
    # If any matching record has outcome != "passed", use that outcome.
    # Otherwise, all records passed.
    if not stage_records:
        outcome = None  # No records → irr_missing path
    else:
        # Find first non-"passed" outcome, or default to "passed"
        failing = [r.get("outcome") for r in stage_records if r.get("outcome") != "passed"]
        outcome = failing[0] if failing else "passed"

    if outcome != "passed":
        # Always emit irr_warning, regardless of --strict-irr
        run_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
        blocked_reason = "irr_low" if outcome == "low" else "irr_missing"
        irr_warning_event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": run_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "orchestrator", "name": "orchestrator"},
            "event": {"kind": "event", "action": "irr_warning", "outcome": "warning"},
            "mpi": {
                "stage": stage,
                "substep": substep,
                "scope": scope,
                "blocked_reason": blocked_reason,
            },
            "reason": f"IRR outcome is {outcome or 'missing'}; {'--strict-irr blocks' if getattr(args, 'strict_irr', False) else 'proceeding'}"
        }
        append_jsonl(audit_path, irr_warning_event)

        if getattr(args, 'strict_irr', False):
            print(f"ERROR irr_check_failed: IRR outcome is {outcome or 'missing'} (--strict-irr set)", file=sys.stderr)
            return 1
    return 0


def _check_completeness_gate(
    run_dir: Path,
    manifest: dict,
    stage: str,
    scope: str,
    args,
    audit_path: Path,
) -> int:
    """
    For cross-participant stages, verify that all required upstream substeps are done
    for all relevant transcripts in the event group.

    Reads study.event_groups from the manifest. If absent (legacy manifest), emits a
    completeness_gate_skipped warning and returns 0.

    Returns 0 to proceed, 1 to block.
    """
    gate = COMPLETENESS_GATES.get(stage)
    if gate is None:
        return 0  # Stage has no completeness gate

    study = manifest.get("study", {})
    event_groups = study.get("event_groups")

    if not event_groups:
        # Legacy manifest without event_groups — warn and proceed
        run_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
        warn_event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": datetime.now(timezone.utc).isoformat(),  # datetime/timezone already imported
            "trace_id": run_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "orchestrator", "name": "orchestrator"},
            "event": {"kind": "event", "action": "completeness_gate_skipped",
                      "outcome": "warning"},
            "mpi": {"stage": stage, "scope": scope},
            "reason": "completeness_gate_skipped: event_groups_missing in study block",
        }
        append_jsonl(audit_path, warn_event)
        print(
            f"WARNING completeness_gate_skipped: event_groups not in manifest; "
            f"completeness gate for {stage} bypassed",
            file=sys.stderr,
        )
        return 0

    # Determine which events to check
    scope_to_event_fn = gate.get("scope_to_event")
    event_id = scope_to_event_fn(scope) if scope_to_event_fn else None

    if event_id is not None:
        events_to_check = {event_id: event_groups.get(event_id, [])}
    else:
        events_to_check = event_groups  # all events

    participants = manifest.get("participants", {})
    required_per_transcript = gate.get("required_per_transcript", [])
    required_cross_participant = gate.get("required_cross_participant", [])

    for evt_id, transcript_ids in events_to_check.items():
        # Check per-transcript requirements
        for transcript_id in transcript_ids:
            for req_stage, req_substep in required_per_transcript:
                if req_stage == "synchronic":
                    # Synchronic is IDU-scoped: check all pNsN-iduK keys for this transcript
                    idu_prefix = f"{transcript_id}-idu"
                    found_any_idu = False
                    for pid, pdata in participants.items():
                        if not pid.startswith(idu_prefix):
                            continue
                        found_any_idu = True
                        status = (pdata.get("stages", {})
                                       .get(req_stage, {})
                                       .get("substeps", {})
                                       .get(req_substep, {})
                                       .get("status"))
                        if status != "done":
                            print(
                                f"ERROR completeness_gate_unsatisfied: "
                                f"{transcript_id} {req_stage}.{req_substep} "
                                f"status={status!r} (event {evt_id})",
                                file=sys.stderr,
                            )
                            return 1
                    if not found_any_idu:
                        print(
                            f"ERROR completeness_gate_unsatisfied: "
                            f"no IDU scopes found for {transcript_id} "
                            f"— {req_stage}.{req_substep} not done (event {evt_id})",
                            file=sys.stderr,
                        )
                        return 1
                else:
                    # Transcript-scoped: look up directly by transcript_id
                    status = (participants.get(transcript_id, {})
                                         .get("stages", {})
                                         .get(req_stage, {})
                                         .get("substeps", {})
                                         .get(req_substep, {})
                                         .get("status"))
                    if status != "done":
                        print(
                            f"ERROR completeness_gate_unsatisfied: "
                            f"{transcript_id} {req_stage}.{req_substep} "
                            f"status={status!r} (event {evt_id})",
                            file=sys.stderr,
                        )
                        return 1

        # Check cross-participant requirements for this event
        # Each entry is a 3-tuple: (key_prefix, req_stage, req_substep)
        # key_prefix=None → match participant keys for this specific event:
        #   pid == evt_id OR pid.startswith(evt_id + "-")
        #   (the "+"-" boundary prevents event1 from matching event12, event13 etc.)
        # key_prefix=str  → match pids that startswith that literal string
        for key_prefix, req_stage, req_substep in required_cross_participant:
            found_done = False
            for pid, pdata in participants.items():
                if key_prefix is None:
                    # Event-ID boundary match: exact equality OR evt_id + "-" prefix
                    if not (pid == evt_id or pid.startswith(evt_id + "-")):
                        continue
                else:
                    if not pid.startswith(key_prefix):
                        continue
                status = (pdata.get("stages", {})
                               .get(req_stage, {})
                               .get("substeps", {})
                               .get(req_substep, {})
                               .get("status"))
                if status == "done":
                    found_done = True
                    break
            if not found_done:
                eff = f"{evt_id}(-)" if key_prefix is None else key_prefix
                print(
                    f"ERROR completeness_gate_unsatisfied: "
                    f"no {req_stage}.{req_substep} done "
                    f"(prefix={eff!r}, event={evt_id})",
                    file=sys.stderr,
                )
                return 1

    return 0


# ---------------------------------------------------------------------------
# close subcommand (implemented in Phase 2)
# ---------------------------------------------------------------------------

def cmd_close(args: argparse.Namespace) -> int:

    run_dir = Path(getattr(args, "run_dir", ".")).resolve()
    audit_path = run_dir / ".mpi" / "audit.jsonl"

    # --- Read-only mode: emit stage_read audit event, no artifacts/manifest/commit ---
    if args.status == "read":
        if not audit_path.exists():
            print(f"ERROR audit_not_found: {audit_path}", file=sys.stderr)
            return 1
        run_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
        event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "trace_id": run_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "orchestrator", "name": args.actor},
            "event": {"kind": "event", "action": "stage_read", "outcome": "success"},
            "mpi": {
                "stage": args.stage,
                "substep": args.substep,
                "scope": args.scope,
                "stage_phase": "read",
            },
            "reason": args.reason,
        }
        append_jsonl(audit_path, event)
        print(f"OK {args.scope} {args.stage}.{args.substep} stage_phase=read")
        return 0

    # --- Non-read path: enforce required arguments ---
    if args.participant is None:
        print("ERROR missing_argument: --participant is required for non-read close", file=sys.stderr)
        return 1
    if args.units_json is None:
        print("ERROR missing_argument: --units-json is required for non-read close", file=sys.stderr)
        return 1
    if not args.artifacts:
        print("ERROR missing_argument: --artifact is required for non-read close", file=sys.stderr)
        return 1

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
        actor_kind=getattr(args, "actor_kind", "subagent"),
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
            actor_kind=getattr(args, "actor_kind", "subagent"),
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
        # AC11.3: Schema validation only at close time; SHA-mismatch enforcement
        # (full replay-grade path resolution and verification) deferred to mpi_replay.py.
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

    # --- Task 5: Span offset resolution (AC28.3, AC28.4) ---
    # Only apply to LLM substeps (orchestrator-only substeps skip span validation)
    if (args.stage, args.substep) in LLM_SUBSTEPS:
        span_errors = _validate_utterance_refs(
            run_dir, units_payload, args.stage, args.substep, manifest
        )
        if span_errors:
            for span_err in span_errors:
                print(f"ERROR span_validation_failed: {span_err}", file=sys.stderr)
            # Emit span_validation_failed audit event before aborting
            e_span_fail = _build_audit_event(
                action="span_validation_failed",
                outcome="failure",
                run_dir=run_dir,
                close_id=close_id,
                actor=args.actor,
                actor_kind=getattr(args, "actor_kind", "subagent"),
                participant=args.participant,
                stage=args.stage,
                substep=args.substep,
                scope=args.scope,
                reason=f"span_validation_failed: {span_errors[0]}",
                extra={"errors": span_errors},
            )
            append_jsonl(audit_path, e_span_fail)
            return _abort(f"span_validation_failed: {span_errors[0]}")

    # Acquire close lock — wraps manifest re-read → prereq check → mutate → write → commit.
    # The initial manifest read above was used for span validation only.
    # A fresh read inside the lock guarantees we see any mutations made by concurrent closes.
    with acquire_close_lock(run_dir):
        manifest = _load_manifest(run_dir)

        # Check substep DAG prerequisites
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

        # --- IRR gate check (Phase 13, AC13.8-13.9) ---
        # For cross-participant stages, check IRR calibration outcome
        cross_participant_stages = {"generic_diachronic", "generic_synchronic", "global_synchronic", "hypothesis"}
        if args.stage in cross_participant_stages:
            irr_check_rc = _check_irr_gate(run_dir, args.stage, args.substep, args.scope, args, audit_path)
            if irr_check_rc != 0:
                return _abort("irr_check_failed")

        # --- DV focus scope guard (Phase 8, AC8.2) ---
        # When study.dv_focuses is declared, hypothesis.evidence_extraction must
        # only use scopes from the declared list.
        if args.stage == "hypothesis" and args.substep == "evidence_extraction":
            dv_focuses = manifest.get("study", {}).get("dv_focuses")
            if dv_focuses is not None:
                # Extract focus name from scope "dv-<focus>"
                focus_name = args.scope[len("dv-"):] if args.scope.startswith("dv-") else args.scope
                if focus_name not in dv_focuses:
                    msg = (
                        f"undeclared_dv_focus: focus '{focus_name}' is not in "
                        f"study.dv_focuses {dv_focuses!r}. "
                        f"Either add it to the declared list at confirm_study_config "
                        f"or set dv_focuses to null to allow emergent focuses."
                    )
                    print(f"ERROR {msg}", file=sys.stderr)
                    return _abort(msg)

        # --- Completeness gate check (Phase 7, AC7.2-7.5) ---
        # For cross-participant stages, verify all upstream transcripts are complete.
        # Reads study.event_groups; legacy manifests (no event_groups) warn and proceed.
        if args.stage in cross_participant_stages:
            completeness_rc = _check_completeness_gate(
                run_dir, manifest, args.stage, args.scope, args, audit_path
            )
            if completeness_rc != 0:
                return _abort("completeness_gate_unsatisfied")

        # --- Task 4: Acquire substep reservation (AC20.7) ---
        reservation_rc = _acquire_substep_reservation(
            run_dir, args.stage, args.substep, args.scope, close_id,
            list(artifacts),
        )
        if reservation_rc != 0:
            return _abort("substep_reservation_held")

        def _abort_with_release(reason: str) -> int:
            """Abort and release the substep reservation."""
            _release_substep_reservation(run_dir, args.stage, args.substep, args.scope)
            return _abort(reason)

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
            actor_kind=getattr(args, "actor_kind", "subagent"),
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
        units = _extract_units(units_payload)
        e_audit = _build_audit_event(
            action="audit_appended",
            run_dir=run_dir,
            close_id=close_id,
            actor=args.actor,
            actor_kind=getattr(args, "actor_kind", "subagent"),
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

        # --- Study-block mutation for init.confirm_study_config ---
        # When the orchestrator closes confirm_study_config, the validated payload
        # carries event_groups, dv_focuses, and config_provenance which must be
        # written to manifest["study"] (not just to the substep entry).
        if args.stage == "init" and args.substep == "confirm_study_config":
            manifest.setdefault("study", {})
            manifest["study"]["event_groups"] = units_payload.get("event_groups")
            dv_focuses_val = units_payload.get("dv_focuses")
            manifest["study"]["dv_focuses"] = dv_focuses_val  # may be null
            manifest["study"]["config_provenance"] = units_payload.get("config_provenance")
            # AC8.5: record whether DV focuses were researcher-specified or emerged from analysis
            manifest["study"]["dv_focuses_provenance"] = (
                "researcher_specified" if dv_focuses_val is not None else "emergent"
            )

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
            actor_kind=getattr(args, "actor_kind", "subagent"),
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
                actor_kind=getattr(args, "actor_kind", "subagent"),
                participant=args.participant, stage=args.stage, substep=args.substep,
                scope=args.scope, reason="git add failed",
            )
            append_jsonl(audit_path, e_rolled)
            # Task 4: Release substep reservation on rollback
            _release_substep_reservation(run_dir, args.stage, args.substep, args.scope)
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
                actor_kind=getattr(args, "actor_kind", "subagent"),
                participant=args.participant, stage=args.stage, substep=args.substep,
                scope=args.scope, reason=r_commit.stderr.strip(),
            )
            append_jsonl(audit_path, e_failed)
            e_rolled = _build_audit_event(
                action="manifest_rolled_back",
                outcome="failure",
                run_dir=run_dir, close_id=close_id, actor=args.actor,
                actor_kind=getattr(args, "actor_kind", "subagent"),
                participant=args.participant, stage=args.stage, substep=args.substep,
                scope=args.scope, reason="git commit failed",
            )
            append_jsonl(audit_path, e_rolled)
            # Task 4: Release substep reservation on rollback
            _release_substep_reservation(run_dir, args.stage, args.substep, args.scope)
            return 1

        commit_sha = _git_head_sha(run_dir)
        e_success = _build_audit_event(
            action="git_commit_succeeded",
            run_dir=run_dir,
            close_id=close_id,
            actor=args.actor,
            actor_kind=getattr(args, "actor_kind", "subagent"),
            participant=args.participant,
            stage=args.stage,
            substep=args.substep,
            scope=args.scope,
            reason=args.reason,
            extra={"git_commit_sha": commit_sha, "artifact_sha256": artifact_shas},
        )
        append_jsonl(audit_path, e_success)

        # Task 4: Release substep reservation on success
        _release_substep_reservation(run_dir, args.stage, args.substep, args.scope)

        # --- Phase 13: IRR calibration auto-trigger (AC13.2) ---
        reload_manifest = _load_manifest(run_dir)
        _maybe_trigger_irr_calibration(
            run_dir=run_dir,
            stage=args.stage,
            substep=args.substep,
            scope=args.scope,
            manifest=reload_manifest,
            close_id=close_id,
            audit_path=audit_path,
        )

        # --- Phase 13: IRR alignment auto-accept in yolo mode (AC13.3) ---
        if args.stage == "irr_calibration" and args.substep == "alignment":
            # Emit irr_alignment_auto_accepted event on successful alignment close
            run_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
            auto_accept_event = {
                "event_id": str(uuid.uuid4()),
                "@timestamp": datetime.now(timezone.utc).isoformat(),
                "trace_id": run_id,
                "span_id": str(uuid.uuid4()),
                "actor": {"kind": getattr(args, "actor_kind", "subagent"), "name": args.actor},
                "event": {"kind": "event", "action": "irr_alignment_auto_accepted", "outcome": "success"},
                "mpi": {
                    "stage": "irr_calibration",
                    "substep": "alignment",
                    "scope": args.scope,
                    "close_id": close_id,
                },
                "reason": "IRR calibration alignment auto-accepted on successful close",
            }
            append_jsonl(audit_path, auto_accept_event)

        # --- Task 3: Cascade reset after criteria_revision re-close (AC16.1, AC16.2, AC30.1-30.3) ---
        if args.stage == "diachronic" and args.substep == "criteria_revision":
            # Check if any downstream substeps are 'done' — if so, cascade reset them.
            # Re-load the just-committed manifest (contains the criteria_revision status=done).
            reload_manifest = _load_manifest(run_dir)
            superseded_before = len(list(
                (run_dir / "analyses" / "_superseded").iterdir()
            )) if (run_dir / "analyses" / "_superseded").exists() else 0

            updated_manifest = _cascade_reset(
                run_dir=run_dir,
                scope=args.scope,
                revision_close_id=close_id,
                manifest=reload_manifest,
                audit_path=audit_path,
                actor=args.actor,
                actor_kind=getattr(args, "actor_kind", "subagent"),
            )

            # Check if cascade actually reset anything (new _superseded dir created)
            superseded_after = len(list(
                (run_dir / "analyses" / "_superseded").iterdir()
            )) if (run_dir / "analyses" / "_superseded").exists() else 0

            if superseded_after > superseded_before:
                # Cascade produced changes — save manifest and commit
                _save_manifest(run_dir, updated_manifest)
                # Stage the _superseded directory tree and manifest explicitly
                cascade_add_paths = [
                    str(manifest_path),
                    str(audit_path),
                    str(run_dir / "analyses" / "_superseded" / close_id),
                ]
                r_cascade_add = _git(
                    ["add"] + cascade_add_paths,
                    cwd=run_dir, check=False,
                )
                if r_cascade_add.returncode == 0:
                    # Also stage all deletions in analyses/ (original artifact paths)
                    _git(
                        ["add", "-u", "analyses/"],
                        cwd=run_dir, check=False,
                    )
                    _git(
                        ["commit", "-m",
                         f"mpi: cascade reset after criteria_revision re-close {close_id[:7]}"],
                        cwd=run_dir, check=False,
                    )
                    # Non-fatal: if nothing to commit (--allow-empty not needed), continue

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

    # --- Task 3 (AC30.3): Append superseded-count summary line ---
    superseded_dir = run_dir / "analyses" / "_superseded"
    if superseded_dir.is_dir():
        superseded_subdirs = [
            d for d in superseded_dir.iterdir() if d.is_dir()
        ]
        n_superseded = len(superseded_subdirs)
        if n_superseded > 0:
            rendered.append(
                f"_superseded/ contains {n_superseded} close_id(s) worth of artifacts"
            )

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

    # Completeness invariant: cross-participant done substeps should not have
    # incomplete upstream entries.
    event_groups = manifest.get("study", {}).get("event_groups")
    if event_groups:
        for stage, gate in COMPLETENESS_GATES.items():
            # Find all done substeps for this stage in the manifest
            for pid, pdata in manifest.get("participants", {}).items():
                for substep_name, substep_data in (
                    pdata.get("stages", {}).get(stage, {}).get("substeps", {}).items()
                ):
                    if substep_data.get("status") == "done":
                        # Re-run completeness check for this scope
                        # Note: passing pid as the scope is safe because _check_completeness_gate
                        # only reads args.stage, args.substep, args.scope from the gate table,
                        # never reads args.participant or other verify-specific fields.
                        rc = _check_completeness_gate(
                            run_dir, manifest, stage, pid, args, audit_path
                        )
                        if rc != 0:
                            failures.append(  # cmd_verify uses `failures`, not `issues` (line 1954)
                                f"completeness_invariant_violated: {stage} "
                                f"{substep_name} is done under {pid} but upstream "
                                f"transcripts are incomplete"
                            )
                            break

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
    p_close.add_argument("--actor-kind", default="subagent", choices=["subagent", "orchestrator"],
                         help="Actor kind: 'subagent' (default) or 'orchestrator'.")
    p_close.add_argument("--participant", default=None)
    p_close.add_argument("--stage", required=True)
    p_close.add_argument("--substep", required=True)
    p_close.add_argument("--scope", required=True)
    p_close.add_argument("--artifact", action="append", dest="artifacts",
                         metavar="PATH", help="Artifact path (repeat for json, md, prompt.json).")
    p_close.add_argument("--units-json", default=None, metavar="PATH_OR_STDIN",
                         help="Path to units JSON file, or '-' to read from stdin.")
    p_close.add_argument("--reason", required=True)
    p_close.add_argument("--status", default="done", choices=["done", "flagged", "read"])
    p_close.add_argument("--prompt-artifact", metavar="PATH",
                         help="Required for LLM-invoking substeps.")
    p_close.add_argument("--run-dir", default=".", metavar="DIR",
                         help="Path to the MPI run directory (default: cwd).")
    p_close.add_argument("--strict-irr", action="store_true",
                         help="Block cross-participant stages if IRR is missing or low.")

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

    # acquire-lease (Task 4: AC20.6)
    p_al = sub.add_parser("acquire-lease", help="Acquire a run-level exclusive lease (.mpi/run.lease).")
    p_al.add_argument("--run-dir", default=".", metavar="DIR")

    # release-lease (Task 4: AC20.6)
    p_rl = sub.add_parser("release-lease", help="Release the run-level lease.")
    p_rl.add_argument("--run-dir", default=".", metavar="DIR")

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
        "acquire-lease": cmd_acquire_lease,
        "release-lease": cmd_release_lease,
    }
    return dispatch[args.verb](args)


if __name__ == "__main__":
    sys.exit(main())

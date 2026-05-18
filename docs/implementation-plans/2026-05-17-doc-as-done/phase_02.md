# Documentation-as-Done Contract Implementation Plan

**Goal:** Implement the transactional `close` verb at substep granularity: pre-checks → audit append → atomic manifest update → git commit, with rollback semantics on failure.

**Architecture:** Extend `mpi_step.py close` with the six-phase close protocol (close_attempted → artifacts_validated → audit_appended → manifest_replaced → git_commit_succeeded/failed → manifest_rolled_back). Manifest schema extended to include `substeps` map under each stage entry. Substep DAG enforced via `_mpi_schemas.SUBSTEP_PREREQUISITES`.

**Tech Stack:** Python 3.9+ stdlib. Manifest writes use `.tmp` → `os.replace` (from Phase 1's `_mpi_atomic`).

**Scope:** Phase 2 of 6.

**Codebase verified:** 2026-05-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC1: Every step closes via the phased close protocol or stays `pending`
- **doc-as-done.AC1.1 Success:** A successful `mpi_step.py close` emits the full event sequence in `.mpi/audit.jsonl`: `close_attempted` → `artifacts_validated` → `audit_appended` → `manifest_replaced` → `git_commit_succeeded`. All five share the same `close_id` (UUID4). The `git_commit_succeeded` event records `mpi.git_commit_sha` (post-commit, now computable).
- **doc-as-done.AC1.2 Failure (commit):** If `git commit` fails, the helper emits `git_commit_failed` followed by `manifest_rolled_back`; manifest reverts to its pre-`manifest_replaced` state; substep stays `pending`.
- **doc-as-done.AC1.3 Failure (audit append):** If audit append fails before manifest mutation, the helper emits no `manifest_replaced` event, leaves the manifest untouched, and exits non-zero.
- **doc-as-done.AC1.4 Success (no SHA self-reference):** The manifest entry records `close_id`, `parent_head_sha`, `artifact_shas`, and `expected_action: "git_commit_succeeded"` — NOT the SHA of the same commit it sits inside.
- **doc-as-done.AC1.5 Success (done definition):** A substep is `done` iff (a) manifest status is `done`, (b) `audit.jsonl` contains a `git_commit_succeeded` event with matching `close_id`, AND (c) that event's `mpi.git_commit_sha` resolves to a commit in `git log` whose tree contains the manifest entry as recorded.

### doc-as-done.AC2: Helper CLI exposes the contract as one verb
- **doc-as-done.AC2.3 Failure:** Missing `--artifact` path, missing `.mpi/project.json`, or empty artifact file causes the helper to exit non-zero with a named error and zero state mutation.

### doc-as-done.AC3: Manifest mutation is atomic
- **doc-as-done.AC3.1 Success:** Manifest writes use `.tmp` → `os.replace` so concurrent readers see either the old or the new manifest, never a partial one.
- **doc-as-done.AC3.2 Failure:** A simulated `os.replace` failure leaves the manifest at its previous state and the `.tmp` file unlinked.

### doc-as-done.AC4: Schema validation rejects malformed units at write time
- **doc-as-done.AC4.2 Failure:** A units payload using `title` instead of `idu_name`, or `utterance_lines` instead of `utterance_numbers`, is rejected with a named error pointing at the offending field.
- **doc-as-done.AC4.3 Failure:** `confidence` outside 1–5, non-boolean `flag_for_review`, or missing `hinge_to_next` on a non-last IDU is rejected.

### doc-as-done.AC10: Substep granularity replaces stage granularity
- **doc-as-done.AC10.1 Success:** The manifest's per-transcript `stages.<stage>` entry contains a `substeps: {<substep>: {status, output_paths[]}}` map; stage `status` is derived from substep statuses (all done → done; any flagged → flagged; any error → error).
- **doc-as-done.AC10.2 Success:** `mpi_step.py close --substep <S2>` enforces the substep DAG — closing `diachronic.idu_naming_ordering` is rejected if `diachronic.criteria_revision` is not `done`.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Extend manifest schema for substeps

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (add manifest helpers)

**Implementation:**

Add these helper functions to `mpi_step.py` (before `cmd_close`):

```python
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
```

**Verification:** Import check — `python -c "import mpi_step; print('OK')"` from scripts dir.

**Commit:** `feat: add manifest helpers and audit event builder to mpi_step.py`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Implement `cmd_close` — the six-phase transaction

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (replace `cmd_close` stub)

**Implementation:**

Replace the `NotImplementedError` stub in `cmd_close` with the full implementation:

```python
def cmd_close(args: argparse.Namespace) -> int:
    import hashlib

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

    # Check LLM substep requires --prompt-artifact
    from _mpi_schemas import LLM_SUBSTEPS
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

    # Check substep DAG prerequisites
    from _mpi_schemas import SUBSTEP_PREREQUISITES
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

    _save_manifest(run_dir, manifest)

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
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python -c "
import sys; sys.path.insert(0, '.')
import mpi_step
print('import OK')
"
```

**Commit:** `feat: implement mpi_step.py close transaction (Phase 2)`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Implement `cmd_verify` — three-way join

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (replace `cmd_verify` stub)

**Implementation:**

Replace `cmd_verify` stub:

```python
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
```

**Commit:** `feat: implement mpi_step.py verify command`

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->

<!-- START_TASK_4 -->
### Task 4: Tests for Phase 2 — close transaction and verify

**Verifies:** doc-as-done.AC1.1, doc-as-done.AC1.2, doc-as-done.AC1.3, doc-as-done.AC2.3, doc-as-done.AC3.1, doc-as-done.AC3.2, doc-as-done.AC4.2, doc-as-done.AC4.3, doc-as-done.AC10.1, doc-as-done.AC10.2

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py` (append Phase 2 test classes)

**Implementation:**

Append these classes to the existing `test_mpi_step.py`:

```python
# ---------------------------------------------------------------------------
# Phase 2: close transaction tests
# ---------------------------------------------------------------------------

import shutil


def _init_run_dir(tmp_path: Path) -> Path:
    """Create a git-initialised MPI run dir with identity set."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    subprocess.run(["git", "init"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.name", "Test"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.email", "t@t.com"], cwd=run_dir, capture_output=True)
    mpi_step.main(["init", "--run", str(run_dir)])
    return run_dir


def _write_artifact(run_dir: Path, name: str, content: str = '{"ok": true}') -> Path:
    p = run_dir / "analyses" / name
    p.parent.mkdir(exist_ok=True)
    p.write_text(content)
    return p


def _write_prompt_artifact(run_dir: Path, scope: str, stage: str, substep: str) -> Path:
    p = run_dir / "analyses" / f"{scope}-{stage}.{substep}.prompt.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "2",
        "actor": {"kind": "subagent", "name": "mpi-analyst",
                  "agent_file_sha256": "abc123", "agent_file_path": "agents/mpi-analyst.md"},
        "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
        "sampling": {"temperature": 1.0, "top_p": 1.0, "top_k": None,
                     "max_tokens": 8192, "seed": None, "stop_sequences": []},
        "stage": stage, "substep": substep, "scope": scope,
        "prompt": {"system": "...", "messages": [], "tools_available": []},
        "response": {"raw_text": "...", "tool_calls": [], "parsed_units_path": ""},
        "metadata": {"finish_reason": "end_turn",
                     "usage": {"input_tokens": 0, "output_tokens": 0,
                               "cache_read_tokens": 0, "cache_write_tokens": 0},
                     "duration_ms": 100, "timestamp": "2026-05-18T00:00:00Z",
                     "anthropic_request_id": "req_xxx"},
    }))
    return p


def _write_units_json(run_dir: Path, name: str, payload: dict) -> Path:
    p = run_dir / name
    p.write_text(json.dumps(payload))
    return p


VALID_CRITERIA_GROUPING_UNITS = {
    "analysis_type": "diachronic",
    "participant": "p1s1",
    "reasoning_summary": "test",
    "idus": [
        {
            "idu_number": 1, "idu_name": "Start", "moment": 1,
            "criteria": "The utterances talk about starting.",
            "confidence": 4, "flag_for_review": False,
            "utterance_numbers": ["1", "2"],
            "hinge_to_next": None,
        }
    ],
}


class TestCloseHappyPath:
    def test_close_criteria_grouping_succeeds(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", "p1s1",
            "--stage", "diachronic",
            "--substep", "criteria_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "criteria grouped",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0

    def test_close_writes_audit_events(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        audit = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit if l.strip()]
        actions = [e["event"]["action"] for e in events]
        assert "close_attempted" in actions
        assert "artifacts_validated" in actions
        assert "audit_appended" in actions
        assert "manifest_replaced" in actions
        assert "git_commit_succeeded" in actions

    def test_close_events_share_close_id(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        audit = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit if l.strip()]
        close_ids = {e["mpi"]["close_id"] for e in events if "close_id" in e.get("mpi", {})}
        assert len(close_ids) == 1, f"Expected 1 close_id, got {close_ids}"

    def test_close_updates_manifest_substeps(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        substep = manifest["participants"]["p1s1"]["stages"]["diachronic"]["substeps"]["criteria_grouping"]
        assert substep["status"] == "done"
        assert "close_id" in substep
        assert substep.get("expected_action") == "git_commit_succeeded"
        # No git_commit_sha in manifest (self-reference impossibility)
        assert "git_commit_sha" not in substep


class TestCloseFailures:
    def test_missing_artifact_fails(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(run_dir / "nonexistent.json"),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_missing_manifest_fails(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        rc = mpi_step.main([
            "close", "--actor", "x", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", "x.json",
            "--units-json", "x.json", "--reason", "x",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_dag_prereq_enforced(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "idu_naming_ordering")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        # criteria_revision not done — close should fail
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "idu_naming_ordering",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_llm_substep_requires_prompt_artifact(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            # NO --prompt-artifact
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_manifest_unchanged_on_failure(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        manifest_before = (run_dir / ".mpi" / "project.json").read_text()
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        # Missing artifact
        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(run_dir / "missing.json"),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        manifest_after = (run_dir / ".mpi" / "project.json").read_text()
        assert manifest_before == manifest_after
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestCloseHappyPath test_mpi_step.py::TestCloseFailures -v
```
Expected: all tests pass.

**Commit:** `test: add Phase 2 close transaction tests`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run full test suite

**Verification:**
```bash
pytest microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
pytest tests/ -v
```
Expected: all pass.

**Commit:** *(no additional commit — test run only)*

<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

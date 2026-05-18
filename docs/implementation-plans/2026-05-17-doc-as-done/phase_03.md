# Documentation-as-Done Contract Implementation Plan

**Goal:** Implement `mpi_step.py render` to regenerate `.mpi/reasoning.log` from `.mpi/audit.jsonl` with optional filtering. Canonical one-line format replaces all previous hand-written formats.

**Architecture:** Pure read-only operation: read JSONL, filter by optional criteria, format each event as a single line, write to `--out`. Malformed lines emit a `MALFORMED:<lineno>` placeholder rather than aborting. The render is idempotent — running it twice produces byte-identical output.

**Tech Stack:** Python 3.9+ stdlib only.

**Scope:** Phase 3 of 6.

**Codebase verified:** 2026-05-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC3: Manifest mutation is atomic
- **doc-as-done.AC3.3 Success:** Re-running `mpi_step.py render` is idempotent — running it twice produces byte-identical `reasoning.log`.

### doc-as-done.AC5: Audit trail is the single source of truth for logs
- **doc-as-done.AC5.1 Success:** `mpi_step.py render` reads `.mpi/audit.jsonl` and produces `.mpi/reasoning.log` containing one line per event in the canonical format.
- **doc-as-done.AC5.2 Failure-tolerance:** A malformed JSONL line in the middle of the file emits a `MALFORMED:<lineno>` placeholder in the rendered output but does not abort rendering.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Implement `cmd_render`

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (replace `cmd_render` stub)

**Implementation:**

The canonical line format is:
```
[<ts>] <actor> <participant> <stage>.<substep>: <reason>. <N> units, <K> flagged. commit=<sha7>
```

For events without substep (e.g., `close_attempted`), substep is omitted. For events without units count, those fields are omitted. `commit=` is only present on `git_commit_succeeded` events.

Replace the `cmd_render` stub:

```python
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

**Commit:** `feat: implement mpi_step.py render verb`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tests for Phase 3 — render and idempotency

**Verifies:** doc-as-done.AC3.3, doc-as-done.AC5.1, doc-as-done.AC5.2

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py` (append Phase 3 test classes)

**Implementation:**

Append these classes to `test_mpi_step.py`:

```python
# ---------------------------------------------------------------------------
# Phase 3: render tests
# ---------------------------------------------------------------------------

SAMPLE_AUDIT_EVENTS = [
    {
        "event_id": "evt-1", "@timestamp": "2026-05-18T10:00:00Z",
        "trace_id": "trace-abc", "span_id": "span-1",
        "actor": {"kind": "subagent", "name": "mpi-analyst"},
        "event": {"kind": "event", "action": "close_attempted", "outcome": "success"},
        "mpi": {
            "participant_id": "p1s1", "stage": "diachronic",
            "substep": "criteria_grouping", "scope": "p1s1",
            "close_id": "close-xyz", "n_units": 3,
        },
        "reason": "starting close",
    },
    {
        "event_id": "evt-2", "@timestamp": "2026-05-18T10:00:01Z",
        "trace_id": "trace-abc", "span_id": "span-2",
        "actor": {"kind": "subagent", "name": "mpi-analyst"},
        "event": {"kind": "event", "action": "git_commit_succeeded", "outcome": "success"},
        "mpi": {
            "participant_id": "p1s1", "stage": "diachronic",
            "substep": "criteria_grouping", "scope": "p1s1",
            "close_id": "close-xyz", "git_commit_sha": "abcdef1234567",
        },
        "reason": "commit ok",
    },
]


class TestRender:
    def _write_audit(self, tmp_path: Path, events: list) -> Path:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        audit = mpi_dir / "audit.jsonl"
        for ev in events:
            audit_line = json.dumps(ev) + "\n"
            with open(audit, "a") as f:
                f.write(audit_line)
        return run_dir

    def test_render_produces_reasoning_log(self, tmp_path):
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS)
        rc = mpi_step.main(["render", "--run-dir", str(run_dir)])
        assert rc == 0
        log = (run_dir / ".mpi" / "reasoning.log").read_text()
        assert "close_attempted" in log or "starting close" in log
        assert "p1s1" in log

    def test_render_includes_commit_sha(self, tmp_path):
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS)
        mpi_step.main(["render", "--run-dir", str(run_dir)])
        log = (run_dir / ".mpi" / "reasoning.log").read_text()
        assert "abcdef1" in log

    def test_render_idempotent(self, tmp_path):
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS)
        mpi_step.main(["render", "--run-dir", str(run_dir)])
        content_a = (run_dir / ".mpi" / "reasoning.log").read_bytes()
        mpi_step.main(["render", "--run-dir", str(run_dir)])
        content_b = (run_dir / ".mpi" / "reasoning.log").read_bytes()
        assert content_a == content_b

    def test_render_malformed_line_placeholder(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        audit = mpi_dir / "audit.jsonl"
        # Good line, bad line, good line
        audit.write_text(
            json.dumps(SAMPLE_AUDIT_EVENTS[0]) + "\n"
            + "THIS IS NOT JSON @@@@\n"
            + json.dumps(SAMPLE_AUDIT_EVENTS[1]) + "\n"
        )
        rc = mpi_step.main(["render", "--run-dir", str(run_dir)])
        assert rc == 0
        log = (run_dir / ".mpi" / "reasoning.log").read_text()
        assert "MALFORMED:2" in log
        assert "p1s1" in log  # other events still rendered

    def test_render_filter_by_participant(self, tmp_path):
        extra_event = {
            "event_id": "evt-3", "@timestamp": "2026-05-18T10:00:02Z",
            "trace_id": "trace-abc", "span_id": "span-3",
            "actor": {"kind": "subagent", "name": "mpi-analyst"},
            "event": {"kind": "event", "action": "close_attempted", "outcome": "success"},
            "mpi": {
                "participant_id": "p2s1", "stage": "diachronic",
                "substep": "criteria_grouping", "scope": "p2s1",
                "close_id": "close-zzz",
            },
            "reason": "other participant",
        }
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS + [extra_event])
        out = tmp_path / "filtered.log"
        mpi_step.main(["render", "--run-dir", str(run_dir), "--participant", "p1s1", "--out", str(out)])
        log = out.read_text()
        assert "p1s1" in log
        assert "p2s1" not in log
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestRender -v
```
Expected: all pass.

**Commit:** `test: add Phase 3 render tests`

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

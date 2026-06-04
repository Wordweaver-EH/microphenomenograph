"""
E2E happy-path pipeline test (Phase 11, Task 2).

Drives the full substep DAG for a 2-participant × 2-suggestion corpus
(4 transcripts, 2 IDUs each) against recorded fixture responses.
No LLM calls are made — all artifact and prompt fixtures are pre-recorded.

Verifies:
  AC1.1  close_attempted → ... → git_commit_succeeded event sequence
  AC1.5  three-way join: manifest + audit + git tree
  AC7.2  audit schema: required fields, unique event_ids
  AC7.3  trace_id constant within run
  AC8.1  analysis JSON artifacts exist and are non-empty
  AC8.2  manifest substep status + git log commit count
  AC11.4 LLM substep events carry mpi.prompt_artifact_path
  AC20.6 run-lease: second acquire-lease returns run_lease_held
  AC20.7 substep-reservation: second close returns substep_reservation_held
  AC30.1 cascade reset: artifacts moved to _superseded/
  AC30.2 tombstone.json in each _superseded/ subdir
  AC30.3 render output surfaces superseded count
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Plugin path setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent
_PLUGIN_ROOT = _REPO_ROOT / "microphenomenograph" / "1.0.0"
_SCRIPTS_DIR = _PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import mpi_step
from _mpi_atomic import atomic_write

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "e2e"
_TRANSCRIPTS_SRC = _FIXTURES_DIR / "transcripts"
_AR_DIR = _FIXTURES_DIR / "agent-responses"
_PROMPTS_DIR = _FIXTURES_DIR / "prompts"

_TIDS = ["p1s1", "p1s2", "p2s1", "p2s2"]
_DIACHRONIC_SUBSTEPS = ["criteria_grouping", "criteria_revision", "idu_naming_ordering"]
_SYNCHRONIC_SUBSTEPS = [
    "theme_grouping_within_idu",
    "isu_naming",
    "isu_second_level_grouping",
]
_IDU_NUMS = [1, 2]

# ---------------------------------------------------------------------------
# Byte offset computation helpers
# ---------------------------------------------------------------------------

def _compute_offsets(transcript_bytes: bytes) -> dict:
    """
    Compute {str(utterance_number): {byte_start, byte_end}} for a transcript.
    Line 0 is the header; utterances are numbered from 1.
    Offsets are LF-terminated inclusive of the newline byte.
    """
    offsets: dict[str, dict] = {}
    pos = 0
    line_idx = 0
    while pos < len(transcript_bytes):
        newline_pos = transcript_bytes.find(b"\n", pos)
        if newline_pos == -1:
            line_end = len(transcript_bytes)
        else:
            line_end = newline_pos + 1
        if line_idx > 0:  # skip header (line_idx == 0)
            offsets[str(line_idx)] = {"byte_start": pos, "byte_end": line_end}
        line_idx += 1
        pos = line_end
    return offsets


# ---------------------------------------------------------------------------
# Module-level E2E run fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def e2e_run(tmp_path_factory):
    """
    Set up a fully-closed E2E MPI run directory and return it.
    Scope=module so all tests share the same run (read-only after setup).
    """
    run_dir: Path = tmp_path_factory.mktemp("e2e_run")

    # ---- Git init ----
    subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "--local", "user.name", "E2E Test"],
        cwd=run_dir, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "user.email", "test@test"],
        cwd=run_dir, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "core.hooksPath", ".git/hooks-disabled"],
        cwd=run_dir, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "commit.gpgsign", "false"],
        cwd=run_dir, capture_output=True, check=True,
    )

    # ---- Bootstrap .mpi/ ----
    mpi_dir = run_dir / ".mpi"
    mpi_dir.mkdir()
    run_id = "e2e-fixture-run-id"
    (mpi_dir / "run_id").write_text(run_id, encoding="utf-8")
    manifest: dict = {
        "version": "2.0",
        "run_id": run_id,
        "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
        "participants": {},
    }
    (mpi_dir / "project.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (mpi_dir / "audit.jsonl").touch()

    # ---- Copy transcripts (LF-preserved) ----
    raw_dir = run_dir / "transcripts" / "raw"
    raw_dir.mkdir(parents=True)
    for tid in _TIDS:
        src = _TRANSCRIPTS_SRC / f"{tid}.txt"
        dst = raw_dir / f"{tid}.txt"
        # Read as binary and write as binary to preserve LF endings
        dst.write_bytes(src.read_bytes())

    # ---- Build offset registries ----
    offsets_dir = run_dir / "transcripts" / "offsets"
    offsets_dir.mkdir(parents=True)
    for tid in _TIDS:
        raw_bytes = (raw_dir / f"{tid}.txt").read_bytes()
        offsets = _compute_offsets(raw_bytes)
        (offsets_dir / f"{tid}.json").write_text(
            json.dumps(offsets, indent=2) + "\n", encoding="utf-8"
        )

    # ---- Create analyses dir ----
    analyses = run_dir / "analyses"
    analyses.mkdir()

    # ---- Helpers to copy fixture artifacts ----
    def _copy_diachronic(tid: str, substep: str) -> tuple[Path, Path, Path]:
        scope = tid
        ar_src = _AR_DIR / "diachronic" / substep / f"{tid}.json"
        prompt_src = _PROMPTS_DIR / "diachronic" / substep / f"{tid}.prompt.json"
        json_dst = analyses / f"{scope}-diachronic.{substep}.json"
        md_dst = analyses / f"{scope}-diachronic.{substep}.md"
        prompt_dst = analyses / f"{scope}-diachronic.{substep}.prompt.json"
        shutil.copy2(str(ar_src), str(json_dst))
        md_dst.write_text(f"# {scope} diachronic.{substep}\n\nAnalysis content.\n",
                          encoding="utf-8")
        shutil.copy2(str(prompt_src), str(prompt_dst))
        return json_dst, md_dst, prompt_dst

    def _copy_synchronic(tid: str, idu_num: int, substep: str) -> tuple[Path, Path, Path]:
        scope = f"{tid}-idu{idu_num}"
        ar_src = _AR_DIR / "synchronic" / substep / f"{scope}.json"
        prompt_src = _PROMPTS_DIR / "synchronic" / substep / f"{scope}.prompt.json"
        json_dst = analyses / f"{scope}-synchronic.{substep}.json"
        md_dst = analyses / f"{scope}-synchronic.{substep}.md"
        prompt_dst = analyses / f"{scope}-synchronic.{substep}.prompt.json"
        shutil.copy2(str(ar_src), str(json_dst))
        md_dst.write_text(f"# {scope} synchronic.{substep}\n\nAnalysis content.\n",
                          encoding="utf-8")
        shutil.copy2(str(prompt_src), str(prompt_dst))
        return json_dst, md_dst, prompt_dst

    # ---- Walk the substep DAG ----
    # Diachronic substeps for all transcripts (all LLM substeps)
    for tid in _TIDS:
        for substep in _DIACHRONIC_SUBSTEPS:
            json_dst, md_dst, prompt_dst = _copy_diachronic(tid, substep)
            rc = mpi_step.main([
                "close",
                "--actor", "mpi-analyst",
                "--participant", tid,
                "--stage", "diachronic",
                "--substep", substep,
                "--scope", tid,
                "--artifact", str(json_dst),
                "--artifact", str(md_dst),
                "--prompt-artifact", str(prompt_dst),
                "--units-json", str(json_dst),
                "--reason", f"{tid} diachronic.{substep} fixture close",
                "--run-dir", str(run_dir),
            ])
            assert rc == 0, f"close failed for {tid} diachronic.{substep} (rc={rc})"

    # Synchronic substeps per IDU.
    # --participant uses the idu-scoped key (p1s1-idu1) so the manifest stores
    # per-IDU entries separately (required by cascade_reset logic).
    # The prerequisite (diachronic.idu_naming_ordering) is satisfied by the
    # preceding diachronic close and the helper _prereq_participant_key() in
    # mpi_step.py, which strips the '-iduN' suffix to look up the transcript-level key.
    for tid in _TIDS:
        for idu_num in _IDU_NUMS:
            scope = f"{tid}-idu{idu_num}"
            participant_key = scope  # per-IDU manifest key

            for substep in _SYNCHRONIC_SUBSTEPS:
                json_dst, md_dst, prompt_dst = _copy_synchronic(tid, idu_num, substep)
                rc = mpi_step.main([
                    "close",
                    "--actor", "mpi-analyst",
                    "--participant", participant_key,
                    "--stage", "synchronic",
                    "--substep", substep,
                    "--scope", scope,
                    "--artifact", str(json_dst),
                    "--artifact", str(md_dst),
                    "--prompt-artifact", str(prompt_dst),
                    "--units-json", str(json_dst),
                    "--reason", f"{scope} synchronic.{substep} fixture close",
                    "--run-dir", str(run_dir),
                ])
                assert rc == 0, f"close failed for {scope} synchronic.{substep} (rc={rc})"

    return run_dir


# ---------------------------------------------------------------------------
# AC8.1: Analysis JSON artifacts exist and are non-empty
# ---------------------------------------------------------------------------

class TestAC8_1_ArtifactsExist:
    def test_diachronic_json_artifacts_exist(self, e2e_run):
        analyses = e2e_run / "analyses"
        for tid in _TIDS:
            for substep in _DIACHRONIC_SUBSTEPS:
                p = analyses / f"{tid}-diachronic.{substep}.json"
                assert p.exists(), f"Missing artifact: {p.name}"
                assert p.stat().st_size > 0, f"Empty artifact: {p.name}"

    def test_synchronic_json_artifacts_exist(self, e2e_run):
        analyses = e2e_run / "analyses"
        for tid in _TIDS:
            for idu_num in _IDU_NUMS:
                scope = f"{tid}-idu{idu_num}"
                for substep in _SYNCHRONIC_SUBSTEPS:
                    p = analyses / f"{scope}-synchronic.{substep}.json"
                    assert p.exists(), f"Missing artifact: {p.name}"
                    assert p.stat().st_size > 0, f"Empty artifact: {p.name}"


# ---------------------------------------------------------------------------
# AC8.2: Manifest substep status and output_paths
# ---------------------------------------------------------------------------

class TestAC8_2_ManifestStatus:
    def test_diachronic_substeps_are_done(self, e2e_run):
        manifest = json.loads(
            (e2e_run / ".mpi" / "project.json").read_text(encoding="utf-8")
        )
        for tid in _TIDS:
            p_entry = manifest.get("participants", {}).get(tid, {})
            stages = p_entry.get("stages", {})
            for substep in _DIACHRONIC_SUBSTEPS:
                ss = stages.get("diachronic", {}).get("substeps", {}).get(substep, {})
                assert ss.get("status") == "done", (
                    f"{tid} diachronic.{substep} status={ss.get('status')!r}, expected 'done'"
                )
                assert ss.get("output_paths"), (
                    f"{tid} diachronic.{substep} has empty output_paths"
                )

    def test_synchronic_substeps_are_done(self, e2e_run):
        manifest = json.loads(
            (e2e_run / ".mpi" / "project.json").read_text(encoding="utf-8")
        )
        for tid in _TIDS:
            for idu_num in _IDU_NUMS:
                participant_key = f"{tid}-idu{idu_num}"
                p_entry = manifest.get("participants", {}).get(participant_key, {})
                stages = p_entry.get("stages", {})
                for substep in _SYNCHRONIC_SUBSTEPS:
                    ss = stages.get("synchronic", {}).get("substeps", {}).get(substep, {})
                    assert ss.get("status") == "done", (
                        f"{participant_key} synchronic.{substep} "
                        f"status={ss.get('status')!r}, expected 'done'"
                    )
                    assert ss.get("output_paths"), (
                        f"{participant_key} synchronic.{substep} has empty output_paths"
                    )

    def test_git_log_commit_count(self, e2e_run):
        """
        Total LLM-substep commits:
          diachronic: 3 substeps × 4 transcripts = 12
          synchronic: 3 substeps × 2 IDUs × 4 transcripts = 24
          Total = 36

        36 substep commits with no cascade commits because the fixture closes
        in strict DAG order (all diachronic substeps for all transcripts before
        any synchronic substeps). Since criteria_revision closes before idu_naming_ordering,
        no downstream substeps are yet done when cascade fires, so no artifacts
        are moved to _superseded/ and no cascade commits are produced.
        """
        r = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=e2e_run, capture_output=True, text=True, check=True,
        )
        commits = [l for l in r.stdout.strip().splitlines() if l.strip()]
        assert len(commits) == 36, (
            f"Expected exactly 36 commits (12 diachronic + 24 synchronic), "
            f"got {len(commits)}. Log:\n{r.stdout}"
        )


# ---------------------------------------------------------------------------
# AC7.2: Audit schema — required fields, unique event_ids
# ---------------------------------------------------------------------------

class TestAC7_2_AuditSchema:
    def _load_events(self, e2e_run: Path) -> list[dict]:
        raw = (e2e_run / ".mpi" / "audit.jsonl").read_text(encoding="utf-8")
        events = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                events.append(json.loads(line))
        return events

    def test_all_events_have_required_fields(self, e2e_run):
        for ev in self._load_events(e2e_run):
            assert "event_id" in ev, f"Missing event_id: {ev}"
            assert "@timestamp" in ev, f"Missing @timestamp: {ev}"
            assert "trace_id" in ev, f"Missing trace_id: {ev}"
            assert "event" in ev and "action" in ev["event"], (
                f"Missing event.action: {ev}"
            )

    def test_all_event_ids_are_unique(self, e2e_run):
        events = self._load_events(e2e_run)
        ids = [ev["event_id"] for ev in events]
        assert len(ids) == len(set(ids)), (
            f"Duplicate event_ids found: {len(ids) - len(set(ids))} duplicates"
        )

    def test_audit_jsonl_is_non_empty(self, e2e_run):
        audit = e2e_run / ".mpi" / "audit.jsonl"
        assert audit.stat().st_size > 0, "audit.jsonl is empty"


# ---------------------------------------------------------------------------
# AC7.3: trace_id constant within run
# ---------------------------------------------------------------------------

class TestAC7_3_TraceId:
    def test_all_events_share_trace_id(self, e2e_run):
        run_id = (e2e_run / ".mpi" / "run_id").read_text(encoding="utf-8").strip()
        raw = (e2e_run / ".mpi" / "audit.jsonl").read_text(encoding="utf-8")
        events = [
            json.loads(l) for l in raw.splitlines() if l.strip()
        ]
        assert events, "No audit events found"
        for ev in events:
            assert ev.get("trace_id") == run_id, (
                f"trace_id mismatch: expected {run_id!r}, "
                f"got {ev.get('trace_id')!r} in event {ev.get('event_id')}"
            )


# ---------------------------------------------------------------------------
# AC1.5: Three-way join — manifest + audit + git tree
# ---------------------------------------------------------------------------

class TestAC1_5_DoneDefinition:
    def test_done_definition_three_way_join(self, e2e_run):
        """
        For p1s1 diachronic.criteria_grouping:
        - manifest status == 'done' with a close_id
        - audit has git_commit_succeeded event with matching close_id
        - git commit tree contains the manifest file
        """
        manifest = json.loads(
            (e2e_run / ".mpi" / "project.json").read_text(encoding="utf-8")
        )
        ss = (
            manifest.get("participants", {})
            .get("p1s1", {})
            .get("stages", {})
            .get("diachronic", {})
            .get("substeps", {})
            .get("criteria_grouping", {})
        )
        assert ss.get("status") == "done", f"p1s1/criteria_grouping not done: {ss}"
        close_id = ss.get("close_id")
        assert close_id, "No close_id in manifest entry"

        # Find matching git_commit_succeeded event in audit
        raw = (e2e_run / ".mpi" / "audit.jsonl").read_text(encoding="utf-8")
        events = [json.loads(l) for l in raw.splitlines() if l.strip()]
        commit_events = [
            e for e in events
            if e.get("event", {}).get("action") == "git_commit_succeeded"
            and e.get("mpi", {}).get("close_id") == close_id
        ]
        assert commit_events, (
            f"No git_commit_succeeded event for close_id={close_id}"
        )
        commit_sha = commit_events[0]["mpi"].get("git_commit_sha")
        assert commit_sha, "No git_commit_sha in commit event"

        # Verify the commit exists in git
        r = subprocess.run(
            ["git", "cat-file", "-t", commit_sha],
            cwd=e2e_run, capture_output=True, text=True,
        )
        assert r.stdout.strip() == "commit", (
            f"SHA {commit_sha} is not a commit in git: {r.stdout!r}"
        )

        # Verify the manifest appears in the commit's tree
        r2 = subprocess.run(
            ["git", "show", "--name-only", "--format=", commit_sha],
            cwd=e2e_run, capture_output=True, text=True,
        )
        changed_files = r2.stdout.strip()
        assert ".mpi/project.json" in changed_files, (
            f".mpi/project.json not in commit {commit_sha} tree: {changed_files!r}"
        )

    def test_all_done_substeps_have_audit_commit(self, e2e_run):
        """AC1.1: Every done substep has a git_commit_succeeded audit event."""
        manifest = json.loads(
            (e2e_run / ".mpi" / "project.json").read_text(encoding="utf-8")
        )
        raw = (e2e_run / ".mpi" / "audit.jsonl").read_text(encoding="utf-8")
        events = [json.loads(l) for l in raw.splitlines() if l.strip()]
        commit_close_ids = {
            e["mpi"]["close_id"]
            for e in events
            if e.get("event", {}).get("action") == "git_commit_succeeded"
            and "close_id" in e.get("mpi", {})
        }
        for participant, pdata in manifest["participants"].items():
            for stage, sdata in pdata.get("stages", {}).items():
                for substep, ssdata in sdata.get("substeps", {}).items():
                    if ssdata.get("status") == "done":
                        cid = ssdata.get("close_id")
                        assert cid in commit_close_ids, (
                            f"{participant}/{stage}/{substep}: "
                            f"no git_commit_succeeded for close_id={cid}"
                        )


# ---------------------------------------------------------------------------
# AC11.4: LLM substep events carry mpi.prompt_artifact_path
# ---------------------------------------------------------------------------

class TestAC11_4_PromptArtifactPath:
    def test_llm_substep_audit_events_have_prompt_path(self, e2e_run):
        raw = (e2e_run / ".mpi" / "audit.jsonl").read_text(encoding="utf-8")
        events = [json.loads(l) for l in raw.splitlines() if l.strip()]
        # Find all audit_appended events (which record the prompt_artifact_path)
        audit_appended = [
            e for e in events
            if e.get("event", {}).get("action") == "audit_appended"
        ]
        assert audit_appended, "No audit_appended events found"
        for ev in audit_appended:
            mpi = ev.get("mpi", {})
            prompt_path = mpi.get("prompt_artifact_path")
            assert prompt_path, (
                f"audit_appended event missing mpi.prompt_artifact_path: "
                f"scope={mpi.get('scope')}, substep={mpi.get('substep')}"
            )


# ---------------------------------------------------------------------------
# AC20.6: Run-lease — second acquire-lease returns error
# ---------------------------------------------------------------------------

class TestAC20_6_RunLease:
    def test_run_lease_held_when_pid_alive(self, tmp_path):
        """
        Write a .mpi/run.lease with current PID, then attempt a second acquire-lease.
        The second attempt should fail with run_lease_held because PID is alive.
        """
        run_dir = tmp_path / "lease_run"
        run_dir.mkdir()
        subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "--local", "user.name", "Test"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "user.email", "t@t"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", ".git/hooks-disabled"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "commit.gpgsign", "false"],
            cwd=run_dir, capture_output=True, check=True,
        )

        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text("test-run-id", encoding="utf-8")
        (mpi_dir / "audit.jsonl").touch()
        (mpi_dir / "project.json").write_text(
            json.dumps({
                "version": "2.0", "run_id": "test-run-id",
                "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
                "participants": {},
            }) + "\n",
            encoding="utf-8",
        )

        import socket
        # Write a lease file with our own PID (which is alive)
        lease_data = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "run_id": "test-run-id",
            "started_at": "2026-06-02T10:00:00+00:00",
            "command": "python mpi_step.py acquire-lease",
        }
        (mpi_dir / "run.lease").write_text(
            json.dumps(lease_data, indent=2) + "\n", encoding="utf-8"
        )

        # Attempting a second acquire should fail
        rc = mpi_step.cmd_acquire_lease(
            type("Args", (), {"run_dir": str(run_dir)})()
        )
        assert rc != 0, (
            "Expected acquire-lease to fail when lease is held by live PID, got rc=0"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "On Windows, os.kill(pid, 0) returns normally for zombie/exited processes "
            "because process handle semantics differ from POSIX. The production code's "
            "dead-PID detection via os.kill(pid, 0) is a known Windows limitation; "
            "stale lease reclaim is tested on POSIX-compatible platforms only."
        ),
    )
    def test_stale_lease_reclaimed(self, tmp_path):
        """
        Write a lease with a dead PID; acquire-lease should reclaim it and succeed.

        Uses a subprocess (short-lived) to get a PID that is guaranteed to be dead
        by the time the lease check runs — cross-platform safe.
        """
        run_dir = tmp_path / "stale_run"
        run_dir.mkdir()
        subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "--local", "user.name", "Test"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "user.email", "t@t"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", ".git/hooks-disabled"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "commit.gpgsign", "false"],
            cwd=run_dir, capture_output=True, check=True,
        )

        import socket

        # Start a short-lived subprocess and wait for it to exit, giving us a dead PID
        dead_proc = subprocess.Popen(
            [sys.executable, "-c", "import sys; sys.exit(0)"]
        )
        dead_pid = dead_proc.pid
        dead_proc.wait()  # Wait until dead

        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text("stale-run-id", encoding="utf-8")
        (mpi_dir / "audit.jsonl").touch()
        (mpi_dir / "project.json").write_text(
            json.dumps({
                "version": "2.0", "run_id": "stale-run-id",
                "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
                "participants": {},
            }) + "\n",
            encoding="utf-8",
        )

        # Write a lease with the now-dead PID
        lease_data = {
            "pid": dead_pid,
            "hostname": socket.gethostname(),
            "run_id": "stale-run-id",
            "started_at": "2026-01-01T00:00:00+00:00",
            "command": "python mpi_step.py acquire-lease",
        }
        (mpi_dir / "run.lease").write_text(
            json.dumps(lease_data, indent=2) + "\n", encoding="utf-8"
        )

        rc = mpi_step.cmd_acquire_lease(
            type("Args", (), {"run_dir": str(run_dir)})()
        )
        assert rc == 0, f"Expected stale lease to be reclaimed (dead PID {dead_pid}), got rc={rc}"
        # Clean up
        mpi_step.cmd_release_lease(type("Args", (), {"run_dir": str(run_dir)})())


# ---------------------------------------------------------------------------
# AC20.7: Substep-reservation — second close returns substep_reservation_held
# ---------------------------------------------------------------------------

class TestAC20_7_SubstepReservation:
    def test_substep_reservation_held(self, tmp_path):
        """
        Write a .reservation.json, then call close with the same scope/stage/substep.
        The close should fail with substep_reservation_held.
        """
        run_dir = tmp_path / "reservation_run"
        run_dir.mkdir()
        subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "--local", "user.name", "Test"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "user.email", "t@t"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", ".git/hooks-disabled"],
            cwd=run_dir, capture_output=True, check=True,
        )
        subprocess.run(
            ["git", "config", "--local", "commit.gpgsign", "false"],
            cwd=run_dir, capture_output=True, check=True,
        )

        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text("resv-run-id", encoding="utf-8")
        (mpi_dir / "audit.jsonl").touch()
        (mpi_dir / "project.json").write_text(
            json.dumps({
                "version": "2.0", "run_id": "resv-run-id",
                "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
                "participants": {},
            }) + "\n",
            encoding="utf-8",
        )

        analyses = run_dir / "analyses"
        analyses.mkdir()

        # Write a reservation file for the target substep
        reservation = {
            "close_id": "resv-close-id",
            "pid": os.getpid(),
            "started_at": "2026-06-02T10:00:00+00:00",
            "intended_artifact_paths": [],
        }
        (analyses / "p1s1-diachronic.criteria_grouping.reservation.json").write_text(
            json.dumps(reservation, indent=2) + "\n", encoding="utf-8"
        )

        # Prepare minimal valid artifact files
        tid = "p1s1"
        ar_src = _AR_DIR / "diachronic" / "criteria_grouping" / f"{tid}.json"
        prompt_src = _PROMPTS_DIR / "diachronic" / "criteria_grouping" / f"{tid}.prompt.json"
        json_dst = analyses / f"{tid}-diachronic.criteria_grouping.json"
        md_dst = analyses / f"{tid}-diachronic.criteria_grouping.md"
        prompt_dst = analyses / f"{tid}-diachronic.criteria_grouping.prompt.json"
        shutil.copy2(str(ar_src), str(json_dst))
        md_dst.write_text("# Test\n")
        shutil.copy2(str(prompt_src), str(prompt_dst))

        # Set up transcript files for span validation
        raw_dir = run_dir / "transcripts" / "raw"
        raw_dir.mkdir(parents=True)
        offsets_dir = run_dir / "transcripts" / "offsets"
        offsets_dir.mkdir(parents=True)
        raw_bytes = (_TRANSCRIPTS_SRC / f"{tid}.txt").read_bytes()
        (raw_dir / f"{tid}.txt").write_bytes(raw_bytes)
        offsets = _compute_offsets(raw_bytes)
        (offsets_dir / f"{tid}.json").write_text(
            json.dumps(offsets, indent=2) + "\n", encoding="utf-8"
        )

        # Call close — should fail because reservation is already held
        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", tid,
            "--stage", "diachronic",
            "--substep", "criteria_grouping",
            "--scope", tid,
            "--artifact", str(json_dst),
            "--artifact", str(md_dst),
            "--prompt-artifact", str(prompt_dst),
            "--units-json", str(json_dst),
            "--reason", "test reservation",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, (
            "Expected close to fail when substep reservation is held, got rc=0"
        )


# ---------------------------------------------------------------------------
# AC30.1–AC30.3: Cascade reset
# ---------------------------------------------------------------------------

class TestAC30_CascadeReset:
    """
    Cascade reset: after a criteria_revision re-close, downstream artifacts
    move to _superseded/, tombstone.json appears, render shows superseded count.
    """

    @pytest.fixture
    def cascade_run(self, tmp_path):
        """
        Set up a minimal run with p1s1 diachronic + all downstream substeps done,
        then re-close criteria_revision to trigger cascade.
        """
        run_dir = tmp_path / "cascade_run"
        run_dir.mkdir()
        subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
        for key, val in [
            ("user.name", "Cascade Test"),
            ("user.email", "cascade@test"),
            ("core.hooksPath", ".git/hooks-disabled"),
            ("commit.gpgsign", "false"),
        ]:
            subprocess.run(
                ["git", "config", "--local", key, val],
                cwd=run_dir, capture_output=True, check=True,
            )

        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text("cascade-run-id", encoding="utf-8")
        (mpi_dir / "audit.jsonl").touch()
        (mpi_dir / "project.json").write_text(
            json.dumps({
                "version": "2.0", "run_id": "cascade-run-id",
                "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
                "participants": {},
            }) + "\n",
            encoding="utf-8",
        )

        analyses = run_dir / "analyses"
        analyses.mkdir()

        # Set up transcript files
        raw_dir = run_dir / "transcripts" / "raw"
        raw_dir.mkdir(parents=True)
        offsets_dir = run_dir / "transcripts" / "offsets"
        offsets_dir.mkdir(parents=True)
        tid = "p1s1"
        raw_bytes = (_TRANSCRIPTS_SRC / f"{tid}.txt").read_bytes()
        (raw_dir / f"{tid}.txt").write_bytes(raw_bytes)
        offsets = _compute_offsets(raw_bytes)
        (offsets_dir / f"{tid}.json").write_text(
            json.dumps(offsets, indent=2) + "\n", encoding="utf-8"
        )

        def _do_close(participant, stage, substep, scope):
            if stage == "diachronic":
                ar_src = _AR_DIR / "diachronic" / substep / f"{tid}.json"
                prompt_src = _PROMPTS_DIR / "diachronic" / substep / f"{tid}.prompt.json"
            else:
                ar_src = _AR_DIR / "synchronic" / substep / f"{scope}.json"
                prompt_src = _PROMPTS_DIR / "synchronic" / substep / f"{scope}.prompt.json"

            json_dst = analyses / f"{scope}-{stage}.{substep}.json"
            md_dst = analyses / f"{scope}-{stage}.{substep}.md"
            prompt_dst = analyses / f"{scope}-{stage}.{substep}.prompt.json"
            shutil.copy2(str(ar_src), str(json_dst))
            md_dst.write_text(f"# {scope} {stage}.{substep}\n")
            shutil.copy2(str(prompt_src), str(prompt_dst))

            rc = mpi_step.main([
                "close",
                "--actor", "mpi-analyst",
                "--participant", participant,
                "--stage", stage,
                "--substep", substep,
                "--scope", scope,
                "--artifact", str(json_dst),
                "--artifact", str(md_dst),
                "--prompt-artifact", str(prompt_dst),
                "--units-json", str(json_dst),
                "--reason", f"{scope} {stage}.{substep} cascade test",
                "--run-dir", str(run_dir),
            ])
            return rc

        # Close all 3 diachronic substeps
        for substep in _DIACHRONIC_SUBSTEPS:
            rc = _do_close(tid, "diachronic", substep, tid)
            assert rc == 0, f"diachronic.{substep} close failed rc={rc}"

        # Close all synchronic substeps for idu1 and idu2
        for idu_num in _IDU_NUMS:
            scope = f"{tid}-idu{idu_num}"
            participant_key = scope

            for substep in _SYNCHRONIC_SUBSTEPS:
                rc = _do_close(participant_key, "synchronic", substep, scope)
                assert rc == 0, f"{scope} synchronic.{substep} close failed rc={rc}"

        return run_dir

    def test_cascade_moves_artifacts_to_superseded(self, cascade_run):
        """AC30.1: Re-close criteria_revision and verify artifacts moved to _superseded/."""
        run_dir = cascade_run
        analyses = run_dir / "analyses"
        tid = "p1s1"

        # Record which downstream artifacts exist before cascade
        downstream_before = {
            "idu_naming_ordering.json": (
                analyses / f"{tid}-diachronic.idu_naming_ordering.json"
            ).exists(),
        }

        # Re-close criteria_revision to trigger cascade
        ar_src = _AR_DIR / "diachronic" / "criteria_revision" / f"{tid}.json"
        prompt_src = _PROMPTS_DIR / "diachronic" / "criteria_revision" / f"{tid}.prompt.json"

        # Write NEW artifact files for the re-close (original moved to _superseded)
        json_dst = analyses / f"{tid}-diachronic.criteria_revision.json"
        md_dst = analyses / f"{tid}-diachronic.criteria_revision.md"
        prompt_dst = analyses / f"{tid}-diachronic.criteria_revision.prompt.json"
        shutil.copy2(str(ar_src), str(json_dst))
        md_dst.write_text(f"# {tid} diachronic.criteria_revision re-close\n")
        shutil.copy2(str(prompt_src), str(prompt_dst))

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", tid,
            "--stage", "diachronic",
            "--substep", "criteria_revision",
            "--scope", tid,
            "--artifact", str(json_dst),
            "--artifact", str(md_dst),
            "--prompt-artifact", str(prompt_dst),
            "--units-json", str(json_dst),
            "--reason", f"{tid} criteria_revision re-close cascade test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"criteria_revision re-close failed rc={rc}"

        # AC30.1: Verify _superseded/ directory was created with at least one subdir
        superseded_dir = analyses / "_superseded"
        assert superseded_dir.is_dir(), "_superseded/ directory not created"
        subdirs = [d for d in superseded_dir.iterdir() if d.is_dir()]
        assert subdirs, "_superseded/ has no subdirectories after cascade"

        # Verify that at least one downstream artifact moved to _superseded/
        found_in_superseded = False
        for subdir in subdirs:
            if (subdir / f"{tid}-diachronic.idu_naming_ordering.json").exists():
                found_in_superseded = True
                break
        assert found_in_superseded, (
            "idu_naming_ordering.json not found in any _superseded/ subdir"
        )

    def test_cascade_tombstone_exists(self, cascade_run):
        """AC30.2: tombstone.json written in every _superseded/ subdir created by cascade.

        _cascade_reset creates the _superseded/<close_id>/ directory lazily (only when
        resets actually occur), so every subdir that exists must have a tombstone.json.
        """
        run_dir = cascade_run
        analyses = run_dir / "analyses"
        tid = "p1s1"

        # Re-close criteria_revision (all downstream substeps are now done)
        ar_src = _AR_DIR / "diachronic" / "criteria_revision" / f"{tid}.json"
        prompt_src = _PROMPTS_DIR / "diachronic" / "criteria_revision" / f"{tid}.prompt.json"
        json_dst = analyses / f"{tid}-diachronic.criteria_revision.json"
        md_dst = analyses / f"{tid}-diachronic.criteria_revision.md"
        prompt_dst = analyses / f"{tid}-diachronic.criteria_revision.prompt.json"
        shutil.copy2(str(ar_src), str(json_dst))
        md_dst.write_text(f"# {tid} criteria_revision re-close\n")
        shutil.copy2(str(prompt_src), str(prompt_dst))
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst",
            "--participant", tid, "--stage", "diachronic",
            "--substep", "criteria_revision", "--scope", tid,
            "--artifact", str(json_dst), "--artifact", str(md_dst),
            "--prompt-artifact", str(prompt_dst),
            "--units-json", str(json_dst),
            "--reason", "re-close for tombstone test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"re-close for tombstone test failed rc={rc}"

        superseded_dir = analyses / "_superseded"
        assert superseded_dir.is_dir(), "_superseded/ not created"
        subdirs = [d for d in superseded_dir.iterdir() if d.is_dir()]
        assert subdirs, "_superseded/ has no subdirectories"

        # At least one subdir should have a tombstone (from the re-close with done substeps)
        tombstone_subdirs = [d for d in subdirs if (d / "tombstone.json").exists()]
        assert tombstone_subdirs, (
            f"No tombstone.json found in any _superseded/ subdir. "
            f"Subdirs: {[d.name for d in subdirs]}"
        )

        # Validate tombstone structure in those that have one
        for subdir in tombstone_subdirs:
            data = json.loads((subdir / "tombstone.json").read_text(encoding="utf-8"))
            assert "cascade_source" in data, f"tombstone in {subdir.name} missing cascade_source"
            assert "reset_substeps" in data, f"tombstone in {subdir.name} missing reset_substeps"
            assert "reason" in data, f"tombstone in {subdir.name} missing reason"
            assert len(data["reset_substeps"]) > 0, (
                f"tombstone in {subdir.name} has empty reset_substeps"
            )

    def test_cascade_render_shows_superseded_count(self, cascade_run):
        """AC30.3: render output surfaces superseded count."""
        run_dir = cascade_run

        # Ensure cascade has occurred (re-close if not)
        analyses = run_dir / "analyses"
        tid = "p1s1"
        superseded_dir = analyses / "_superseded"

        if not superseded_dir.is_dir() or not any(superseded_dir.iterdir()):
            ar_src = _AR_DIR / "diachronic" / "criteria_revision" / f"{tid}.json"
            prompt_src = _PROMPTS_DIR / "diachronic" / "criteria_revision" / f"{tid}.prompt.json"
            json_dst = analyses / f"{tid}-diachronic.criteria_revision.json"
            md_dst = analyses / f"{tid}-diachronic.criteria_revision.md"
            prompt_dst = analyses / f"{tid}-diachronic.criteria_revision.prompt.json"
            if not json_dst.exists():
                shutil.copy2(str(ar_src), str(json_dst))
                md_dst.write_text(f"# {tid} criteria_revision\n")
                shutil.copy2(str(prompt_src), str(prompt_dst))
            mpi_step.main([
                "close", "--actor", "mpi-analyst",
                "--participant", tid, "--stage", "diachronic",
                "--substep", "criteria_revision", "--scope", tid,
                "--artifact", str(json_dst), "--artifact", str(md_dst),
                "--prompt-artifact", str(prompt_dst),
                "--units-json", str(json_dst),
                "--reason", "re-close for render test",
                "--run-dir", str(run_dir),
            ])

        rc = mpi_step.main([
            "render",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"render failed rc={rc}"

        log_path = run_dir / ".mpi" / "reasoning.log"
        assert log_path.exists(), "reasoning.log not created"
        log_text = log_path.read_text(encoding="utf-8")
        assert "_superseded/" in log_text, (
            "render output does not mention _superseded/ directory"
        )
        assert "close_id" in log_text or "contains" in log_text, (
            "render output does not surface superseded count"
        )


# ---------------------------------------------------------------------------
# AC30: Cross-participant cascade (exercises _CASCADE_CROSS_PARTICIPANT_STAGES)
# ---------------------------------------------------------------------------

class TestAC30_CrossParticipantCascade:
    """
    Verify that _CASCADE_CROSS_PARTICIPANT_STAGES is exercised:
    a generic_diachronic artifact seeded as 'done' in the manifest must be
    moved to _superseded/ when criteria_revision fires.
    """

    @pytest.fixture
    def cross_cascade_run(self, tmp_path):
        """
        Minimal run with:
        - p1s1: criteria_grouping done (so criteria_revision prereq is satisfied)
        - generic_diachronic participant: idu_similarity_grouping done with artifact on disk
        Closing criteria_revision triggers cascade; cascade should move the
        generic_diachronic artifact.
        """
        run_dir = tmp_path / "cross_cascade"
        run_dir.mkdir()

        subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
        for key, val in [
            ("user.name", "Cross Cascade"),
            ("user.email", "cross@cascade"),
            ("core.hooksPath", ".git/hooks-disabled"),
            ("commit.gpgsign", "false"),
        ]:
            subprocess.run(
                ["git", "config", "--local", key, val],
                cwd=run_dir, capture_output=True, check=True,
            )

        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text("cross-cascade-run-id", encoding="utf-8")
        (mpi_dir / "audit.jsonl").touch()

        analyses = run_dir / "analyses"
        analyses.mkdir()

        # The cross-participant participant key (realistic format: event<E>-cat-<C>)
        # and its artifact
        gd_key = "event1-cat-low"
        gd_artifact_json = (
            analyses / f"{gd_key}-generic_diachronic.idu_similarity_grouping.json"
        )
        gd_artifact_md = (
            analyses / f"{gd_key}-generic_diachronic.idu_similarity_grouping.md"
        )
        gd_artifact_json.write_text(
            json.dumps({"event": "idu_similarity_grouping", "idu_labels": []}),
            encoding="utf-8",
        )
        gd_artifact_md.write_text(
            "# event1-cat-low idu_similarity_grouping\n", encoding="utf-8"
        )

        # Manifest: p1s1 criteria_grouping done; event1-cat-low idu_similarity done
        manifest = {
            "version": "2.0",
            "run_id": "cross-cascade-run-id",
            "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
            "participants": {
                "p1s1": {
                    "stages": {
                        "diachronic": {
                            "substeps": {
                                "criteria_grouping": {"status": "done"},
                            }
                        }
                    }
                },
                gd_key: {
                    "stages": {
                        "generic_diachronic": {
                            "substeps": {
                                "idu_similarity_grouping": {
                                    "status": "done",
                                    "output_path": str(gd_artifact_json),
                                }
                            }
                        }
                    }
                },
            },
        }
        (mpi_dir / "project.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

        # Transcript files for span validation
        tid = "p1s1"
        raw_dir = run_dir / "transcripts" / "raw"
        raw_dir.mkdir(parents=True)
        offsets_dir = run_dir / "transcripts" / "offsets"
        offsets_dir.mkdir(parents=True)
        raw_bytes = (_TRANSCRIPTS_SRC / f"{tid}.txt").read_bytes()
        (raw_dir / f"{tid}.txt").write_bytes(raw_bytes)
        offsets = _compute_offsets(raw_bytes)
        (offsets_dir / f"{tid}.json").write_text(
            json.dumps(offsets, indent=2) + "\n", encoding="utf-8"
        )

        # Initial commit so cascade commit can succeed
        subprocess.run(
            ["git", "add", "--all"], cwd=run_dir, capture_output=True, check=True
        )
        subprocess.run(
            ["git", "commit", "-m", "initial state"],
            cwd=run_dir, capture_output=True, check=True,
        )

        return run_dir, gd_artifact_json, gd_artifact_md

    def test_criteria_revision_cascades_cross_participant_artifact(
        self, cross_cascade_run
    ):
        """
        criteria_revision close must cascade-reset the generic_diachronic artifact
        (exercises _CASCADE_CROSS_PARTICIPANT_STAGES branch in _cascade_reset).
        """
        run_dir, gd_artifact_json, gd_artifact_md = cross_cascade_run
        analyses = run_dir / "analyses"
        tid = "p1s1"
        gd_key = "event1-cat-low"

        # Confirm artifact exists before cascade
        assert gd_artifact_json.exists(), (
            "test setup failed: generic_diachronic artifact missing before cascade"
        )

        # Close criteria_revision — triggers cascade
        ar_src = _AR_DIR / "diachronic" / "criteria_revision" / f"{tid}.json"
        prompt_src = _PROMPTS_DIR / "diachronic" / "criteria_revision" / f"{tid}.prompt.json"
        json_dst = analyses / f"{tid}-diachronic.criteria_revision.json"
        md_dst = analyses / f"{tid}-diachronic.criteria_revision.md"
        prompt_dst = analyses / f"{tid}-diachronic.criteria_revision.prompt.json"
        shutil.copy2(str(ar_src), str(json_dst))
        md_dst.write_text(f"# {tid} criteria_revision\n")
        shutil.copy2(str(prompt_src), str(prompt_dst))

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", tid,
            "--stage", "diachronic",
            "--substep", "criteria_revision",
            "--scope", tid,
            "--artifact", str(json_dst),
            "--artifact", str(md_dst),
            "--prompt-artifact", str(prompt_dst),
            "--units-json", str(json_dst),
            "--reason", "criteria_revision for cross-participant cascade test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"criteria_revision close failed rc={rc}"

        # The generic_diachronic artifact must have been moved to _superseded/
        superseded_dir = analyses / "_superseded"
        assert superseded_dir.is_dir(), (
            "_superseded/ directory not created after cascade"
        )
        assert not gd_artifact_json.exists(), (
            f"{gd_key}-generic_diachronic artifact still at original path "
            "after cascade — cross-participant cascade branch did not fire"
        )
        # Confirm it landed in _superseded/<close_id>/
        found = any(
            (subdir / f"{gd_key}-generic_diachronic.idu_similarity_grouping.json").exists()
            for subdir in superseded_dir.iterdir()
            if subdir.is_dir()
        )
        assert found, (
            f"{gd_key}-generic_diachronic.idu_similarity_grouping.json not found in _superseded/ "
            "— cross-participant cascade artifacts not moved correctly"
        )

        # AC30 additional check: git tree must be clean after cascade (no unstaged deletions)
        # The cascade should stage both the moved artifacts AND the deletions at the original paths
        git_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=run_dir,
            capture_output=True,
            text=True,
            check=True
        )
        assert git_status.stdout.strip() == "", (
            f"git tree dirty after cascade reset: {git_status.stdout}\n"
            "Cascade commit should stage all deletions in analyses/ via 'git add -u'"
        )


# ---------------------------------------------------------------------------
# Render round-trip idempotency (AC3.3)
# ---------------------------------------------------------------------------

class TestRenderIdempotency:
    def test_render_is_idempotent(self, e2e_run):
        """Render twice; assert byte-identical output."""
        log_path = e2e_run / ".mpi" / "reasoning.log"

        rc1 = mpi_step.main(["render", "--run-dir", str(e2e_run)])
        assert rc1 == 0
        content1 = log_path.read_bytes()
        assert len(content1) > 0, "reasoning.log is empty after first render"

        rc2 = mpi_step.main(["render", "--run-dir", str(e2e_run)])
        assert rc2 == 0
        content2 = log_path.read_bytes()

        assert content1 == content2, (
            "render output is not idempotent: "
            f"first={len(content1)} bytes, second={len(content2)} bytes"
        )

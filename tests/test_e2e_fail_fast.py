"""
E2E fail-fast / negative-path test suite (Phase 11, Task 6).

Each test case uses a fresh temp git repo with git identity and a minimal valid manifest.
All tests verify that mpi_step.py close exits non-zero on bad input, leaving the manifest
and git history unchanged, with no half-written artifacts.

Verifies:
  AC1.2  Commit failure → manifest rolls back, commit_failed in audit
  AC1.3  Audit append failure → manifest untouched (read-only audit.jsonl)
  AC8.3  Malformed units → exit non-zero, manifest unchanged, no git commit
  AC8.3  Unknown stage → exit non-zero, manifest unchanged
  AC8.3  Missing prompt artifact → exit non-zero, prompt_artifact_missing
  AC28.3 Missing span refs (utterance_refs: []) → exit non-zero, missing_span_refs
  AC28.4 Span excerpt mismatch → exit non-zero, span_excerpt_mismatch
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
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

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).parent / "fixtures" / "e2e"
_TRANSCRIPTS_SRC = _FIXTURES_DIR / "transcripts"
_AR_DIR = _FIXTURES_DIR / "agent-responses"
_PROMPTS_DIR = _FIXTURES_DIR / "prompts"

_TID = "p1s1"  # The transcript used for all fail-fast tests


# ---------------------------------------------------------------------------
# Byte offset computation (same as in test_e2e_pipeline.py)
# ---------------------------------------------------------------------------

def _compute_offsets(transcript_bytes: bytes) -> dict:
    offsets: dict[str, dict] = {}
    pos = 0
    line_idx = 0
    while pos < len(transcript_bytes):
        newline_pos = transcript_bytes.find(b"\n", pos)
        if newline_pos == -1:
            line_end = len(transcript_bytes)
        else:
            line_end = newline_pos + 1
        if line_idx > 0:
            offsets[str(line_idx)] = {"byte_start": pos, "byte_end": line_end}
        line_idx += 1
        pos = line_end
    return offsets


# ---------------------------------------------------------------------------
# Shared setup helper
# ---------------------------------------------------------------------------

def _setup_minimal_run(tmp_path: Path) -> Path:
    """
    Create a git-initialised MPI run dir with minimal .mpi/ structure.
    Does NOT call mpi_step.py init to keep tests self-contained.
    Returns the run_dir.
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
    for key, val in [
        ("user.name", "Fail-fast Test"),
        ("user.email", "fail@test"),
        ("core.hooksPath", ".git/hooks-disabled"),
        ("commit.gpgsign", "false"),
    ]:
        subprocess.run(
            ["git", "config", "--local", key, val],
            cwd=run_dir, capture_output=True, check=True,
        )

    mpi_dir = run_dir / ".mpi"
    mpi_dir.mkdir()
    run_id = "fail-fast-run-id"
    (mpi_dir / "run_id").write_text(run_id, encoding="utf-8")
    (mpi_dir / "audit.jsonl").touch()
    (mpi_dir / "project.json").write_text(
        json.dumps({
            "version": "2.0",
            "run_id": run_id,
            "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
            "participants": {},
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    # Create analyses dir
    (run_dir / "analyses").mkdir()

    # Set up transcript raw + offsets for span validation
    raw_dir = run_dir / "transcripts" / "raw"
    raw_dir.mkdir(parents=True)
    offsets_dir = run_dir / "transcripts" / "offsets"
    offsets_dir.mkdir(parents=True)
    raw_bytes = (_TRANSCRIPTS_SRC / f"{_TID}.txt").read_bytes()
    (raw_dir / f"{_TID}.txt").write_bytes(raw_bytes)
    offsets = _compute_offsets(raw_bytes)
    (offsets_dir / f"{_TID}.json").write_text(
        json.dumps(offsets, indent=2) + "\n", encoding="utf-8"
    )

    return run_dir


def _manifest_snapshot(run_dir: Path) -> str:
    """Return the current manifest as a string for unchanged-check comparisons."""
    return (run_dir / ".mpi" / "project.json").read_text(encoding="utf-8")


def _git_commit_count(run_dir: Path) -> int:
    r = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=run_dir, capture_output=True, text=True,
    )
    if r.returncode != 0:
        return 0
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    return len(lines)


def _no_tmp_files(analyses_dir: Path) -> bool:
    """
    Return True if no .tmp files exist in the analyses dir.

    Note: We check .tmp files (created by atomic_write) rather than the final
    artifact path itself, because atomic_write creates a .tmp file, writes to it,
    then renames it atomically. If close fails, the .tmp file may be left behind
    but the final artifact (json/md/prompt.json) is inputs to close, not outputs,
    so checking for leftover .tmp files is sufficient to validate no half-written
    artifacts were produced.
    """
    return not any(analyses_dir.glob("*.tmp"))


def _make_valid_units(
    *,
    utterance_refs: list | None = None,
    confidence: int = 3,
) -> dict:
    """Build a minimal valid diachronic criteria_grouping payload."""
    if utterance_refs is None:
        # Use real bytes from the p1s1.txt fixture (utterance 1)
        raw_bytes = (_TRANSCRIPTS_SRC / f"{_TID}.txt").read_bytes()
        excerpt = raw_bytes[41:86].decode("utf-8")
        utterance_refs = [
            {
                "transcript_id": _TID,
                "utterance_number": 1,
                "byte_start": 41,
                "byte_end": 86,
                "raw_excerpt": excerpt,
            }
        ]
    return {
        "analysis_type": "diachronic",
        "participant": _TID,
        "reasoning_summary": "Single IDU for testing.",
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Test IDU",
                "moment": 1,
                "criteria": "The utterances talk about a test scenario.",
                "confidence": confidence,
                "flag_for_review": False,
                "utterance_numbers": ["1", "2"],
                "hinge_to_next": None,
                "utterance_refs": utterance_refs,
            }
        ],
    }


def _make_valid_prompt(stage: str, substep: str, scope: str) -> dict:
    """Build a minimal valid prompt.json."""
    return {
        "schema_version": "2",
        "actor": {
            "kind": "subagent",
            "name": "mpi-analyst",
            "agent_file_sha256": "abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234abcd1234",
            "agent_file_path": "agents/mpi-analyst.md",
        },
        "model": {"id": "claude-sonnet-4-6", "provider": "anthropic"},
        "sampling": {"temperature": 1.0, "top_p": 1.0, "max_tokens": 8192},
        "stage": stage,
        "substep": substep,
        "scope": scope,
        "prompt": {
            "system": "You are an MPI analyst.",
            "messages": [{"role": "user", "content": "Analyse."}],
            "tools_available": [],
        },
        "response": {
            "raw_text": "Analysis complete.",
            "tool_calls": [],
            "parsed_units_path": None,
        },
        "metadata": {
            "finish_reason": "end_turn",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 50,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            },
            "duration_ms": 500,
            "timestamp": "2026-06-02T10:00:00+00:00",
        },
    }


def _write_artifacts(
    run_dir: Path,
    units: dict,
    prompt: dict | None,
    *,
    stage: str = "diachronic",
    substep: str = "criteria_grouping",
    scope: str = _TID,
) -> tuple[Path, Path, Path | None]:
    """Write json and md artifacts; optionally write prompt artifact. Returns paths."""
    analyses = run_dir / "analyses"
    json_path = analyses / f"{scope}-{stage}.{substep}.json"
    md_path = analyses / f"{scope}-{stage}.{substep}.md"
    json_path.write_text(json.dumps(units, indent=2), encoding="utf-8")
    md_path.write_text(f"# {scope} {stage}.{substep}\n\nTest.\n", encoding="utf-8")
    if prompt is not None:
        prompt_path = analyses / f"{scope}-{stage}.{substep}.prompt.json"
        prompt_path.write_text(json.dumps(prompt, indent=2), encoding="utf-8")
        return json_path, md_path, prompt_path
    return json_path, md_path, None


def _run_close(
    run_dir: Path,
    units: dict,
    prompt: dict | None = None,
    *,
    stage: str = "diachronic",
    substep: str = "criteria_grouping",
    scope: str = _TID,
    extra_args: list[str] | None = None,
) -> int:
    """Write artifacts and call close; return rc."""
    json_path, md_path, prompt_path = _write_artifacts(
        run_dir, units, prompt, stage=stage, substep=substep, scope=scope
    )
    args = [
        "close",
        "--actor", "mpi-analyst",
        "--participant", scope,
        "--stage", stage,
        "--substep", substep,
        "--scope", scope,
        "--artifact", str(json_path),
        "--artifact", str(md_path),
        "--units-json", str(json_path),
        "--reason", "fail-fast test",
        "--run-dir", str(run_dir),
    ]
    if prompt_path is not None:
        args += ["--prompt-artifact", str(prompt_path)]
    if extra_args:
        args += extra_args
    return mpi_step.main(args)


# ---------------------------------------------------------------------------
# AC8.3: Malformed units — confidence out of range
# ---------------------------------------------------------------------------

class TestAC8_3_MalformedUnits:
    def test_malformed_confidence_exit_nonzero(self, tmp_path):
        """confidence: 9 is out of range (1–5); close must exit non-zero."""
        run_dir = _setup_minimal_run(tmp_path)
        bad_units = _make_valid_units(confidence=9)
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        rc = _run_close(run_dir, bad_units, prompt)
        assert rc != 0, f"Expected exit non-zero for confidence=9, got rc={rc}"

    def test_malformed_confidence_manifest_unchanged(self, tmp_path):
        """Manifest must be unchanged after a malformed-units close attempt."""
        run_dir = _setup_minimal_run(tmp_path)
        before = _manifest_snapshot(run_dir)
        bad_units = _make_valid_units(confidence=9)
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, bad_units, prompt)
        after = _manifest_snapshot(run_dir)
        assert before == after, (
            "Manifest was modified after a malformed-units close attempt"
        )

    def test_malformed_confidence_no_git_commit(self, tmp_path):
        """No git commit must be created after a malformed-units close attempt."""
        run_dir = _setup_minimal_run(tmp_path)
        commits_before = _git_commit_count(run_dir)
        bad_units = _make_valid_units(confidence=9)
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, bad_units, prompt)
        commits_after = _git_commit_count(run_dir)
        assert commits_after == commits_before, (
            f"Git commit was created after malformed-units close: "
            f"{commits_before} → {commits_after}"
        )

    def test_malformed_confidence_no_tmp_artifacts(self, tmp_path):
        """No .tmp files must be left after a malformed-units close attempt."""
        run_dir = _setup_minimal_run(tmp_path)
        bad_units = _make_valid_units(confidence=9)
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, bad_units, prompt)
        assert _no_tmp_files(run_dir / "analyses"), (
            ".tmp files found in analyses/ after malformed-units close"
        )


# ---------------------------------------------------------------------------
# AC8.3: Unknown stage
# ---------------------------------------------------------------------------

class TestAC8_3_UnknownStage:
    def test_unknown_stage_exit_nonzero(self, tmp_path):
        """--stage fakeStage must cause exit non-zero."""
        run_dir = _setup_minimal_run(tmp_path)
        valid_units = _make_valid_units()

        analyses = run_dir / "analyses"
        json_path = analyses / f"{_TID}-fakeStage.criteria_grouping.json"
        md_path = analyses / f"{_TID}-fakeStage.criteria_grouping.md"
        json_path.write_text(json.dumps(valid_units, indent=2), encoding="utf-8")
        md_path.write_text("# test\n", encoding="utf-8")

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", _TID,
            "--stage", "fakeStage",
            "--substep", "criteria_grouping",
            "--scope", _TID,
            "--artifact", str(json_path),
            "--artifact", str(md_path),
            "--units-json", str(json_path),
            "--reason", "unknown stage test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, f"Expected exit non-zero for unknown stage, got rc={rc}"

    def test_unknown_stage_manifest_unchanged(self, tmp_path):
        """Manifest must be unchanged after an unknown-stage close attempt."""
        run_dir = _setup_minimal_run(tmp_path)
        before = _manifest_snapshot(run_dir)
        valid_units = _make_valid_units()

        analyses = run_dir / "analyses"
        json_path = analyses / f"{_TID}-fakeStage.criteria_grouping.json"
        md_path = analyses / f"{_TID}-fakeStage.criteria_grouping.md"
        json_path.write_text(json.dumps(valid_units, indent=2), encoding="utf-8")
        md_path.write_text("# test\n", encoding="utf-8")

        mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", _TID,
            "--stage", "fakeStage",
            "--substep", "criteria_grouping",
            "--scope", _TID,
            "--artifact", str(json_path),
            "--artifact", str(md_path),
            "--units-json", str(json_path),
            "--reason", "unknown stage test",
            "--run-dir", str(run_dir),
        ])
        after = _manifest_snapshot(run_dir)
        assert before == after, (
            "Manifest was modified after unknown-stage close attempt"
        )


# ---------------------------------------------------------------------------
# AC8.3: Missing prompt artifact
# ---------------------------------------------------------------------------

class TestAC8_3_MissingPromptArtifact:
    def test_missing_prompt_exit_nonzero(self, tmp_path):
        """Omitting --prompt-artifact for an LLM substep must cause exit non-zero."""
        run_dir = _setup_minimal_run(tmp_path)
        valid_units = _make_valid_units()
        # _run_close passes prompt=None → no --prompt-artifact argument
        rc = _run_close(run_dir, valid_units, prompt=None)
        assert rc != 0, (
            "Expected exit non-zero when --prompt-artifact is missing for LLM substep"
        )

    def test_missing_prompt_manifest_unchanged(self, tmp_path):
        run_dir = _setup_minimal_run(tmp_path)
        before = _manifest_snapshot(run_dir)
        valid_units = _make_valid_units()
        _run_close(run_dir, valid_units, prompt=None)
        after = _manifest_snapshot(run_dir)
        assert before == after, (
            "Manifest was modified after missing-prompt close attempt"
        )

    def test_missing_prompt_no_git_commit(self, tmp_path):
        run_dir = _setup_minimal_run(tmp_path)
        commits_before = _git_commit_count(run_dir)
        valid_units = _make_valid_units()
        _run_close(run_dir, valid_units, prompt=None)
        assert _git_commit_count(run_dir) == commits_before, (
            "Git commit was created after missing-prompt close"
        )

    def test_missing_prompt_artifact_file_path(self, tmp_path):
        """--prompt-artifact pointing to a non-existent file must fail with prompt_artifact_not_found."""
        run_dir = _setup_minimal_run(tmp_path)
        valid_units = _make_valid_units()
        json_path, md_path, _ = _write_artifacts(run_dir, valid_units, None)
        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", _TID,
            "--stage", "diachronic",
            "--substep", "criteria_grouping",
            "--scope", _TID,
            "--artifact", str(json_path),
            "--artifact", str(md_path),
            "--units-json", str(json_path),
            "--prompt-artifact", str(run_dir / "analyses" / "nonexistent.prompt.json"),
            "--reason", "missing prompt artifact path test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "Expected exit non-zero for non-existent prompt artifact"


# ---------------------------------------------------------------------------
# AC1.3: Audit append failure (read-only audit.jsonl)
# ---------------------------------------------------------------------------

class TestAC1_3_AuditAppendFailure:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "On Windows, even read-only files can be written by the file owner "
            "and chmod-based protection may not prevent Python file writes from the "
            "same user. This test relies on POSIX file permission semantics."
        ),
    )
    def test_audit_readonly_manifest_untouched(self, tmp_path):
        """
        AC1.3: If audit.jsonl is read-only before the close, the manifest must
        remain untouched (the close cannot proceed past the audit_appended phase).
        """
        run_dir = _setup_minimal_run(tmp_path)
        valid_units = _make_valid_units()
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        before = _manifest_snapshot(run_dir)

        audit_path = run_dir / ".mpi" / "audit.jsonl"
        # Make audit.jsonl read-only
        audit_path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        try:
            rc = _run_close(run_dir, valid_units, prompt)
            assert rc != 0, "Expected exit non-zero when audit.jsonl is read-only"
            after = _manifest_snapshot(run_dir)
            assert before == after, (
                "Manifest was modified despite read-only audit.jsonl (AC1.3 violated)"
            )
        finally:
            # Restore write permissions
            audit_path.chmod(
                stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH
            )


# ---------------------------------------------------------------------------
# AC1.2: Commit failure — pre-commit hook exits 1
# ---------------------------------------------------------------------------

class TestAC1_2_CommitFailure:
    def test_commit_failure_manifest_rolls_back(self, tmp_path):
        """
        AC1.2: If git commit fails (pre-commit hook exits 1),
        the manifest must be rolled back and audit contains commit_failed event.
        """
        run_dir = _setup_minimal_run(tmp_path)
        before = _manifest_snapshot(run_dir)

        # Create a hooks directory with a failing pre-commit hook
        hooks_dir = run_dir / ".git" / "failing-hooks"
        hooks_dir.mkdir()
        hook_file = hooks_dir / "pre-commit"
        # Write a pre-commit hook that always fails
        hook_file.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook_file.chmod(
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            | stat.S_IRGRP | stat.S_IXGRP
            | stat.S_IROTH | stat.S_IXOTH
        )
        # Point hooksPath to the failing hooks dir
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath",
             ".git/failing-hooks"],
            cwd=run_dir, capture_output=True, check=True,
        )

        valid_units = _make_valid_units()
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        rc = _run_close(run_dir, valid_units, prompt)
        assert rc != 0, "Expected exit non-zero when git commit fails (hook exits 1)"

        # Manifest must be rolled back
        after = _manifest_snapshot(run_dir)
        assert before == after, (
            "Manifest was not rolled back after commit failure (AC1.2 violated)"
        )

    def test_commit_failure_audit_has_commit_failed_event(self, tmp_path):
        """AC1.2: audit.jsonl must contain git_commit_failed event after commit failure."""
        run_dir = _setup_minimal_run(tmp_path)

        # Set up failing pre-commit hook
        hooks_dir = run_dir / ".git" / "failing-hooks"
        hooks_dir.mkdir()
        hook_file = hooks_dir / "pre-commit"
        hook_file.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook_file.chmod(
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            | stat.S_IRGRP | stat.S_IXGRP
            | stat.S_IROTH | stat.S_IXOTH
        )
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", ".git/failing-hooks"],
            cwd=run_dir, capture_output=True, check=True,
        )

        valid_units = _make_valid_units()
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, valid_units, prompt)

        audit_lines = (run_dir / ".mpi" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        events = [json.loads(l) for l in audit_lines if l.strip()]
        actions = [e.get("event", {}).get("action") for e in events]

        assert "git_commit_failed" in actions, (
            f"audit.jsonl missing git_commit_failed event. Actions found: {actions}"
        )

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason=(
            "Pre-commit hooks are shell scripts (#!/bin/sh) that require a POSIX "
            "shell to execute. On Windows, git may not be able to execute the hook "
            "script, producing a different failure mode than a hook that exits 1."
        ),
    )
    def test_commit_failure_audit_has_manifest_rolled_back(self, tmp_path):
        """AC1.2: audit.jsonl must contain manifest_rolled_back event after commit failure."""
        run_dir = _setup_minimal_run(tmp_path)

        hooks_dir = run_dir / ".git" / "failing-hooks"
        hooks_dir.mkdir()
        hook_file = hooks_dir / "pre-commit"
        hook_file.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        hook_file.chmod(
            stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
            | stat.S_IRGRP | stat.S_IXGRP
            | stat.S_IROTH | stat.S_IXOTH
        )
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", ".git/failing-hooks"],
            cwd=run_dir, capture_output=True, check=True,
        )

        valid_units = _make_valid_units()
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, valid_units, prompt)

        audit_lines = (run_dir / ".mpi" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        events = [json.loads(l) for l in audit_lines if l.strip()]
        actions = [e.get("event", {}).get("action") for e in events]

        assert "manifest_rolled_back" in actions, (
            f"audit.jsonl missing manifest_rolled_back event. Actions found: {actions}"
        )


# ---------------------------------------------------------------------------
# AC28.3: Missing span refs (utterance_refs: [])
# ---------------------------------------------------------------------------

class TestAC28_3_MissingSpanRefs:
    def test_empty_utterance_refs_exit_nonzero(self, tmp_path):
        """utterance_refs: [] must cause schema validation failure and exit non-zero."""
        run_dir = _setup_minimal_run(tmp_path)
        # The schema validator (_check_utterance_refs) catches empty utterance_refs
        # before span offset validation runs
        units = {
            "analysis_type": "diachronic",
            "participant": _TID,
            "reasoning_summary": "Missing refs test.",
            "idus": [
                {
                    "idu_number": 1,
                    "idu_name": "Test IDU",
                    "moment": 1,
                    "criteria": "The utterances talk about a test scenario.",
                    "confidence": 3,
                    "flag_for_review": False,
                    "utterance_numbers": ["1"],
                    "hinge_to_next": None,
                    "utterance_refs": [],  # Empty — should fail
                }
            ],
        }
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        rc = _run_close(run_dir, units, prompt)
        assert rc != 0, "Expected exit non-zero for empty utterance_refs"

    def test_empty_utterance_refs_manifest_unchanged(self, tmp_path):
        """Manifest must be unchanged when utterance_refs is empty."""
        run_dir = _setup_minimal_run(tmp_path)
        before = _manifest_snapshot(run_dir)
        units = {
            "analysis_type": "diachronic",
            "participant": _TID,
            "reasoning_summary": "Missing refs test.",
            "idus": [
                {
                    "idu_number": 1,
                    "idu_name": "Test IDU",
                    "moment": 1,
                    "criteria": "The utterances talk about a test scenario.",
                    "confidence": 3,
                    "flag_for_review": False,
                    "utterance_numbers": ["1"],
                    "hinge_to_next": None,
                    "utterance_refs": [],
                }
            ],
        }
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, units, prompt)
        assert _manifest_snapshot(run_dir) == before, (
            "Manifest was modified after empty-utterance_refs close"
        )

    def test_empty_utterance_refs_error_message_contains_missing_span_refs(
        self, tmp_path, capsys
    ):
        """Error output must mention missing_span_refs."""
        run_dir = _setup_minimal_run(tmp_path)
        units = {
            "analysis_type": "diachronic",
            "participant": _TID,
            "reasoning_summary": "Missing refs test.",
            "idus": [
                {
                    "idu_number": 1,
                    "idu_name": "Test IDU",
                    "moment": 1,
                    "criteria": "The utterances talk about a test scenario.",
                    "confidence": 3,
                    "flag_for_review": False,
                    "utterance_numbers": ["1"],
                    "hinge_to_next": None,
                    "utterance_refs": [],
                }
            ],
        }
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, units, prompt)
        captured = capsys.readouterr()
        assert "missing_span_refs" in captured.err or "missing_span_refs" in captured.out, (
            "Error output does not contain 'missing_span_refs'. "
            f"stderr={captured.err!r}, stdout={captured.out!r}"
        )

    def test_no_git_commit_for_missing_span_refs(self, tmp_path):
        """No git commit must be created when utterance_refs is empty."""
        run_dir = _setup_minimal_run(tmp_path)
        commits_before = _git_commit_count(run_dir)
        units = {
            "analysis_type": "diachronic",
            "participant": _TID,
            "reasoning_summary": "Missing refs test.",
            "idus": [
                {
                    "idu_number": 1,
                    "idu_name": "Test IDU",
                    "moment": 1,
                    "criteria": "The utterances talk about a test scenario.",
                    "confidence": 3,
                    "flag_for_review": False,
                    "utterance_numbers": ["1"],
                    "hinge_to_next": None,
                    "utterance_refs": [],
                }
            ],
        }
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, units, prompt)
        assert _git_commit_count(run_dir) == commits_before, (
            "Git commit was created despite empty utterance_refs"
        )


# ---------------------------------------------------------------------------
# AC28.4: Span excerpt mismatch
# ---------------------------------------------------------------------------

class TestAC28_4_SpanExcerptMismatch:
    """
    Feed a units JSON with a span ref whose raw_excerpt does not match the actual
    bytes at [byte_start:byte_end] in the transcript.
    Expected: exit non-zero with span_excerpt_mismatch.

    This test is the TODO from Phase 7 Task 4 mentioned in the phase_11.md spec.
    """

    def test_span_excerpt_mismatch_exit_nonzero(self, tmp_path):
        """A mismatched raw_excerpt must cause exit non-zero."""
        run_dir = _setup_minimal_run(tmp_path)
        # Use real byte range but wrong excerpt text
        units = _make_valid_units(
            utterance_refs=[
                {
                    "transcript_id": _TID,
                    "utterance_number": 1,
                    "byte_start": 41,
                    "byte_end": 86,
                    "raw_excerpt": "THIS IS THE WRONG TEXT AND DOES NOT MATCH\n",
                }
            ]
        )
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        rc = _run_close(run_dir, units, prompt)
        assert rc != 0, "Expected exit non-zero for span_excerpt_mismatch"

    def test_span_excerpt_mismatch_manifest_unchanged(self, tmp_path):
        run_dir = _setup_minimal_run(tmp_path)
        before = _manifest_snapshot(run_dir)
        units = _make_valid_units(
            utterance_refs=[
                {
                    "transcript_id": _TID,
                    "utterance_number": 1,
                    "byte_start": 41,
                    "byte_end": 86,
                    "raw_excerpt": "WRONG EXCERPT\n",
                }
            ]
        )
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, units, prompt)
        assert _manifest_snapshot(run_dir) == before, (
            "Manifest was modified after span_excerpt_mismatch close"
        )

    def test_span_excerpt_mismatch_error_message(self, tmp_path, capsys):
        """Error output must mention span_excerpt_mismatch."""
        run_dir = _setup_minimal_run(tmp_path)
        units = _make_valid_units(
            utterance_refs=[
                {
                    "transcript_id": _TID,
                    "utterance_number": 1,
                    "byte_start": 41,
                    "byte_end": 86,
                    "raw_excerpt": "WRONG EXCERPT\n",
                }
            ]
        )
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, units, prompt)
        captured = capsys.readouterr()
        assert "span_excerpt_mismatch" in captured.err or "span_excerpt_mismatch" in captured.out, (
            "Error output does not contain 'span_excerpt_mismatch'. "
            f"stderr={captured.err!r}, stdout={captured.out!r}"
        )

    def test_span_excerpt_mismatch_no_git_commit(self, tmp_path):
        run_dir = _setup_minimal_run(tmp_path)
        commits_before = _git_commit_count(run_dir)
        units = _make_valid_units(
            utterance_refs=[
                {
                    "transcript_id": _TID,
                    "utterance_number": 1,
                    "byte_start": 41,
                    "byte_end": 86,
                    "raw_excerpt": "WRONG EXCERPT\n",
                }
            ]
        )
        prompt = _make_valid_prompt("diachronic", "criteria_grouping", _TID)
        _run_close(run_dir, units, prompt)
        assert _git_commit_count(run_dir) == commits_before, (
            "Git commit was created despite span_excerpt_mismatch"
        )


# ---------------------------------------------------------------------------
# DAG prerequisite enforcement (Important #3 — AC SUBSTEP_PREREQUISITES)
# ---------------------------------------------------------------------------

class TestDAGPrerequisite:
    """
    Verify that the substep DAG prerequisite check blocks close when the
    required upstream substep is not yet done (prereq_unsatisfied).

    Tests the synchronic.theme_grouping_within_idu → diachronic.idu_naming_ordering
    edge: attempting synchronic close before diachronic.idu_naming_ordering is done
    must exit non-zero with 'prereq_unsatisfied' in the error output.
    """

    def _make_synchronic_units(self) -> dict:
        """Build a minimal valid synchronic theme_grouping_within_idu payload."""
        raw_bytes = (_TRANSCRIPTS_SRC / f"{_TID}.txt").read_bytes()
        excerpt = raw_bytes[41:86].decode("utf-8")
        return {
            "analysis_type": "synchronic",
            "participant": f"{_TID}-idu1",
            "idu_name": "Test IDU",
            "isus": [
                {
                    "isu_name": "Test ISU",
                    "criteria": "test criteria",
                    "confidence": 3,
                    "flag_for_review": False,
                    "utterance_refs": [
                        {
                            "transcript_id": _TID,
                            "utterance_number": 1,
                            "byte_start": 41,
                            "byte_end": 86,
                            "raw_excerpt": excerpt,
                        }
                    ],
                }
            ],
        }

    def test_synchronic_without_prereq_exit_nonzero(self, tmp_path):
        """
        synchronic.theme_grouping_within_idu requires diachronic.idu_naming_ordering.
        Close must exit non-zero when the prerequisite is not met.
        """
        run_dir = _setup_minimal_run(tmp_path)
        units = self._make_synchronic_units()
        prompt = _make_valid_prompt(
            "synchronic", "theme_grouping_within_idu", f"{_TID}-idu1"
        )
        rc = _run_close(
            run_dir, units, prompt,
            stage="synchronic",
            substep="theme_grouping_within_idu",
            scope=f"{_TID}-idu1",
        )
        assert rc != 0, (
            "Expected exit non-zero for synchronic close without "
            "diachronic.idu_naming_ordering done"
        )

    def test_synchronic_without_prereq_error_message(self, tmp_path, capsys):
        """Error output must mention prereq_unsatisfied."""
        run_dir = _setup_minimal_run(tmp_path)
        units = self._make_synchronic_units()
        prompt = _make_valid_prompt(
            "synchronic", "theme_grouping_within_idu", f"{_TID}-idu1"
        )
        _run_close(
            run_dir, units, prompt,
            stage="synchronic",
            substep="theme_grouping_within_idu",
            scope=f"{_TID}-idu1",
        )
        captured = capsys.readouterr()
        assert (
            "prereq_unsatisfied" in captured.err
            or "prereq_unsatisfied" in captured.out
        ), (
            "Expected 'prereq_unsatisfied' in error output. "
            f"stderr={captured.err!r}, stdout={captured.out!r}"
        )

    def test_synchronic_without_prereq_manifest_unchanged(self, tmp_path):
        """Manifest must be unchanged when a DAG prerequisite is not satisfied."""
        run_dir = _setup_minimal_run(tmp_path)
        before = _manifest_snapshot(run_dir)
        units = self._make_synchronic_units()
        prompt = _make_valid_prompt(
            "synchronic", "theme_grouping_within_idu", f"{_TID}-idu1"
        )
        _run_close(
            run_dir, units, prompt,
            stage="synchronic",
            substep="theme_grouping_within_idu",
            scope=f"{_TID}-idu1",
        )
        assert _manifest_snapshot(run_dir) == before, (
            "Manifest was modified when DAG prerequisite was not met"
        )

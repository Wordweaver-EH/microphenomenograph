"""
Tests verifying mpi-cross-analyst.md structural contracts from Phase 7.
These are contract tests — they verify the file contains the required sections and
declarations without invoking any LLM.

Phase 7 Subcomponent B adds E2E fixture close tests for generic-diachronic and
hypothesis cross-analyst substeps.
"""
import json
import subprocess
import sys
from pathlib import Path
import re

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
AGENT_FILE = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "cross_analyst"

# Import mpi_step from the plugin's scripts directory
_SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
import mpi_step


# ---------------------------------------------------------------------------
# Shared tempdir setup helper
# ---------------------------------------------------------------------------

def _setup_cross_run_dir(tmp_path: Path, seed_prereqs: dict | None = None) -> Path:
    """
    Create a minimal git-initialised MPI run dir for cross-analyst fixture tests.

    Does NOT call mpi_step.py init — creates .mpi/ structure directly to avoid
    init-side-effects and keep tests self-contained.

    seed_prereqs: optional dict mapping
        participant_key -> {stage -> {substep -> {"status": "done"}}}
    used to satisfy DAG prerequisite checks.
    """
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    subprocess.run(["git", "init"], cwd=run_dir, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "--local", "user.name", "Test"],
        cwd=run_dir, capture_output=True, check=True,
    )
    subprocess.run(
        ["git", "config", "--local", "user.email", "t@test.com"],
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

    # Build manifest with optional seeded prerequisites
    participants = {}
    if seed_prereqs:
        for participant_key, stages_data in seed_prereqs.items():
            stages = {}
            for stage, substeps_data in stages_data.items():
                substeps = {}
                for substep, entry in substeps_data.items():
                    substeps[substep] = entry
                stages[stage] = {"substeps": substeps, "status": "done"}
            participants[participant_key] = {"stages": stages}

    manifest = {
        "version": "2.0",
        "run_id": "fixture-run-id",
        "study": {"run_repo_mode": "dedicated", "git_remote_configured": False},
        "participants": participants,
    }
    (mpi_dir / "project.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    (mpi_dir / "audit.jsonl").touch()

    return run_dir


def _setup_transcript_files(run_dir: Path, transcript_id: str, raw_text: str) -> None:
    """
    Write minimal raw transcript and offset registry files for span-ref validation.
    raw_text must be ASCII and must contain at least the bytes referenced by fixtures.
    """
    raw_dir = run_dir / "transcripts" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{transcript_id}.txt").write_text(raw_text, encoding="utf-8")

    offsets_dir = run_dir / "transcripts" / "offsets"
    offsets_dir.mkdir(parents=True, exist_ok=True)
    # Minimal offset registry: one utterance at byte range 0..(len of first sentence)
    raw_bytes = raw_text.encode("utf-8")
    offsets = {
        "transcript_id": transcript_id,
        "utterances": [
            {
                "utterance_number": 1,
                "byte_start": 0,
                "byte_end": len(raw_bytes),
            }
        ],
    }
    (offsets_dir / f"{transcript_id}.json").write_text(
        json.dumps(offsets, indent=2), encoding="utf-8"
    )


class TestAC6_1_AgentTools:
    """AC6.1: mpi-cross-analyst.md declares Read, Write, Bash in tools: line."""

    def test_mpi_cross_analyst_declares_read_write_bash(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        match = re.search(r"^tools:\s*(.+)$", content, re.MULTILINE)
        assert match, "No 'tools:' line found in mpi-cross-analyst.md frontmatter"
        tools_line = match.group(1)
        assert "Read" in tools_line, f"'Read' missing from tools line: {tools_line!r}"
        assert "Write" in tools_line, f"'Write' missing from tools line: {tools_line!r}"
        assert "Bash" in tools_line, f"'Bash' missing from tools line: {tools_line!r}"


class TestAC6_2_PersistenceSection:
    """AC6.2: mpi-cross-analyst.md contains Persistence (mandatory before returning) section."""

    def test_persistence_section_exists(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "Persistence (mandatory before returning)" in content, (
            "Missing 'Persistence (mandatory before returning)' section in mpi-cross-analyst.md"
        )

    def test_persistence_section_names_close_invocation(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "mpi_step.py close" in content, (
            "mpi_step.py close invocation not found in mpi-cross-analyst.md"
        )

    def test_persistence_return_value_format(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "OK " in content and "ERROR " in content, (
            "Return value format (OK / ERROR) not documented in mpi-cross-analyst.md"
        )

    def test_orchestrator_reads_from_disk(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "The orchestrator reads from disk" in content, (
            "mpi-cross-analyst.md Persistence section must instruct agent not to return content"
        )


class TestAC10_5_CrossAnalystSubstepEnumeration:
    """AC10.5: Persistence section enumerates all LLM-driven cross-analyst substeps."""

    _LLM_SUBSTEPS = [
        "generic_diachronic.idu_similarity_grouping",
        "generic_diachronic.pattern_identification",
        "generic_diachronic.cross_iv_contrast",
        "generic_synchronic.select_generic_idus_of_interest",
        "generic_synchronic.isu_second_level_grouping",
        "global_synchronic",
        "hypothesis.evidence_extraction",
        "hypothesis.candidate_drafting",
        "hypothesis.weak_evidence_review",
        "irr_calibration.independent_analyst",
        "irr_calibration.alignment",
    ]

    _ORCHESTRATOR_SUBSTEPS = [
        "participant_row_assembly",
        "worksheet_assembly",
        "irr_calibration.agreement_computation",
    ]

    def _persistence_section(self, content: str) -> str:
        idx = content.find("## Persistence (mandatory before returning)")
        assert idx >= 0, "Persistence section not found"
        return content[idx:]

    @pytest.mark.parametrize("substep", _LLM_SUBSTEPS)
    def test_llm_substep_present(self, substep):
        content = AGENT_FILE.read_text(encoding="utf-8")
        section = self._persistence_section(content)
        assert substep in section, (
            f"LLM substep '{substep}' not found in Persistence section of mpi-cross-analyst.md"
        )

    @pytest.mark.parametrize("substep", _ORCHESTRATOR_SUBSTEPS)
    def test_orchestrator_substep_absent(self, substep):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert substep not in content, (
            f"Orchestrator-only substep '{substep}' must NOT appear in mpi-cross-analyst.md"
        )


class TestAntiFabricationClause:
    """AC5.3: Anti-fabrication rule present in agent file."""

    def test_anti_fabrication_in_agent(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "Never generate placeholder or synthetic" in content, (
            "Anti-fabrication rule ('Never generate placeholder or synthetic') "
            "not found in mpi-cross-analyst.md"
        )


class TestClaimLevelEvidence:
    """AC23.1, AC23.2: Claim-level evidence schema and raw-span anchoring documented."""

    def test_raw_span_refs_present(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "raw_span_refs" in content, (
            "mpi-cross-analyst.md must document the raw_span_refs span-grounding requirement"
        )

    def test_disclaimer_text_present(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "not causal estimates from a hypothesis test" in content, (
            "Verbatim disclaimer 'not causal estimates from a hypothesis test' "
            "not found in mpi-cross-analyst.md"
        )


# ---------------------------------------------------------------------------
# Task 3: E2E fixture close test — generic_diachronic.idu_similarity_grouping
# Verifies: AC6.2, AC10.5, AC28.5
# ---------------------------------------------------------------------------

_FIXTURE_RAW_TEXT = "I noticed something."  # 20 bytes ASCII; matches fixture byte_start=0, byte_end=20


class TestAC6_2_GenericDiachronicFixtureClose:
    """
    AC6.2, AC10.5, AC28.5: End-to-end fixture close for
    generic_diachronic.idu_similarity_grouping via mpi-cross-analyst.

    No LLM is invoked — we test the close contract by writing pre-built fixtures
    and calling mpi_step.py close directly.
    """

    def test_generic_diachronic_fixture_close(self, tmp_path):
        scope = "event1-cat-high"
        stage = "generic_diachronic"
        substep = "idu_similarity_grouping"
        transcript_id = "p1s1"

        # Seed the prerequisite (participant_row_assembly must be done)
        run_dir = _setup_cross_run_dir(
            tmp_path,
            seed_prereqs={
                scope: {
                    stage: {
                        "participant_row_assembly": {"status": "done"},
                    }
                }
            },
        )

        # Set up transcript raw file and offset registry
        _setup_transcript_files(run_dir, transcript_id, _FIXTURE_RAW_TEXT)

        # Copy fixture files into analyses/
        analyses = run_dir / "analyses"
        analyses.mkdir()

        base = f"{scope}-{stage}.{substep}"
        json_path = analyses / f"{base}.json"
        md_path = analyses / f"{base}.md"
        prompt_path = analyses / f"{base}.prompt.json"

        json_path.write_bytes((FIXTURES_DIR / f"{base}.json").read_bytes())
        md_path.write_bytes((FIXTURES_DIR / f"{base}.md").read_bytes())
        prompt_path.write_bytes((FIXTURES_DIR / f"{base}.prompt.json").read_bytes())

        # Call mpi_step.py close
        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", scope,
            "--stage", stage,
            "--substep", substep,
            "--scope", scope,
            "--artifact", str(json_path),
            "--artifact", str(md_path),
            "--prompt-artifact", str(prompt_path),
            "--units-json", str(json_path),
            "--reason", "fixture close",
            "--run-dir", str(run_dir),
        ])

        assert rc == 0, f"mpi_step.py close returned {rc}"

        # Verify audit.jsonl has git_commit_succeeded with matching close_id
        audit_lines = (run_dir / ".mpi" / "audit.jsonl").read_text(encoding="utf-8").splitlines()
        events = [json.loads(ln) for ln in audit_lines if ln.strip()]

        # Find close_attempted close_id
        attempted = [e for e in events if e.get("event", {}).get("action") == "close_attempted"]
        assert attempted, "No close_attempted event found in audit.jsonl"
        close_id = attempted[-1]["mpi"]["close_id"]

        # Find git_commit_succeeded with matching close_id
        commits = [
            e for e in events
            if e.get("event", {}).get("action") == "git_commit_succeeded"
            and e["mpi"]["close_id"] == close_id
        ]
        assert commits, f"No git_commit_succeeded with close_id={close_id} in audit.jsonl"

        # Verify manifest reflects substep done under the event scope
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text(encoding="utf-8"))
        substep_entry = (
            manifest
            .get("participants", {})
            .get(scope, {})
            .get("stages", {})
            .get(stage, {})
            .get("substeps", {})
            .get(substep, {})
        )
        assert substep_entry.get("status") == "done", (
            f"Manifest substep not done: {substep_entry}"
        )
        assert substep_entry.get("expected_action") == "git_commit_succeeded"


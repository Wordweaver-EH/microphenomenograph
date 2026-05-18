"""
Tests verifying mpi-analyst.md and SKILL.md structural contracts from Phase 6.
These are contract tests — they verify the files contain the required sections and
declarations without invoking any LLM.
"""
from pathlib import Path
import json
import re
import subprocess
import sys
import tempfile

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
AGENT_FILE = PLUGIN_ROOT / "agents" / "mpi-analyst.md"
DIACHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
SYNCHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"

# Import mpi_step from the plugin's scripts directory
_SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
import mpi_step
from _mpi_atomic import atomic_write, load_or_create_run_id


class TestAC6_1_AgentTools:
    """AC6.1: mpi-analyst.md declares Read, Write, Bash in tools: line."""

    def test_mpi_analyst_declares_write_bash(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        # Find tools: line in frontmatter
        match = re.search(r"^tools:\s*(.+)$", content, re.MULTILINE)
        assert match, "No 'tools:' line found in mpi-analyst.md frontmatter"
        tools_line = match.group(1)
        assert "Write" in tools_line, f"'Write' missing from tools line: {tools_line!r}"
        assert "Bash" in tools_line, f"'Bash' missing from tools line: {tools_line!r}"
        assert "Read" in tools_line, f"'Read' missing from tools line: {tools_line!r}"


class TestAC6_2_PersistenceSection:
    """AC6.2: mpi-analyst.md contains Persistence (mandatory before returning) subsection."""

    def test_persistence_section_exists(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "Persistence (mandatory before returning)" in content, \
            "Missing 'Persistence (mandatory before returning)' section in mpi-analyst.md"

    def test_persistence_section_names_six_substeps(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        required_substeps = [
            "diachronic.criteria_grouping",
            "diachronic.criteria_revision",
            "diachronic.idu_naming_ordering",
            "synchronic.theme_grouping_within_idu",
            "synchronic.isu_naming",
            "synchronic.isu_second_level_grouping",
        ]
        for substep in required_substeps:
            assert substep in content, \
                f"Substep '{substep}' not found in mpi-analyst.md Persistence section"

    def test_persistence_section_names_close_invocation(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "mpi_step.py close" in content, \
            "mpi_step.py close invocation not found in mpi-analyst.md"

    def test_persistence_return_value_format(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "OK " in content and "ERROR " in content, \
            "Return value format (OK / ERROR) not documented in mpi-analyst.md"


class TestAC6_3_SkillClosureSections:
    """AC6.3: SKILL.md files contain 'Closure (mandatory)' subsection."""

    def test_diachronic_skill_has_closure(self):
        content = DIACHRONIC_SKILL.read_text(encoding="utf-8")
        assert "Closure (mandatory)" in content, \
            "Missing 'Closure (mandatory)' section in mpi-diachronic/SKILL.md"

    def test_synchronic_skill_has_closure(self):
        content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
        assert "Closure (mandatory)" in content, \
            "Missing 'Closure (mandatory)' section in mpi-synchronic/SKILL.md"


class TestAC10_4_SubstepEnumeration:
    """AC10.4: Agent enumerates all 6 mpi-analyst substeps with manual-native names."""

    def test_no_deprecated_substep_names(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        # These names are from µ-PATH and must NOT appear in the agent file
        deprecated = ["diachronic.phases", "diachronic.du", "diachronic.refined_du",
                      "generic_synchronic.sss_grouping", "generic_synchronic.gss_definition"]
        for name in deprecated:
            assert name not in content, \
                f"Deprecated substep name '{name}' found in mpi-analyst.md — use manual_kev.md names"


class TestAC12_1_ManualNativeSubstepNames:
    """AC12.1: Synchronic skill uses per-IDU iteration, not per-phase."""

    def test_synchronic_skill_mentions_per_idu(self):
        content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
        assert "per IDU" in content or "per-IDU" in content or "per_idu" in content.lower(), \
            "mpi-synchronic/SKILL.md must document per-IDU iteration"

    def test_synchronic_skill_preserves_isu_second_level_column(self):
        content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
        assert "isu_second_level_of_abstraction" in content or "ISU 2nd Level" in content or \
               "isu_second_level" in content, \
            "mpi-synchronic/SKILL.md must document isu_second_level_of_abstraction column"

    def test_diachronic_skill_no_sub_phase_identification(self):
        content = DIACHRONIC_SKILL.read_text(encoding="utf-8")
        # Extract the Closure section to check manual-native constraint
        closure_start = content.find("## Closure (mandatory)")
        assert closure_start >= 0, "Closure section not found"
        closure_section = content[closure_start:]
        # The Closure section must document that diachronic does NOT include sub-phase identification
        assert "does NOT include sub-phase identification" in closure_section, \
            "mpi-diachronic/SKILL.md Closure must document that sub-phase identification is excluded"


class TestAC28_1_UtteranceRefsRequirement:
    """AC28.1: Agent documents the utterance_refs requirement."""

    def test_agent_documents_utterance_refs(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "utterance_refs" in content, \
            "mpi-analyst.md must document the utterance_refs grounding requirement"


class TestAntiFabricationClause:
    """AC5.3: Anti-fabrication rule present in agent file."""

    def test_anti_fabrication_in_agent(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "Never generate placeholder" in content or \
               "never generate placeholder" in content or \
               "Anti-fabrication" in content, \
            "Anti-fabrication rule not found in mpi-analyst.md"


def _setup_run_dir(tmp_path: Path) -> Path:
    """Create a git-initialised MPI run dir that passes init."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    subprocess.run(["git", "init"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.name", "Test"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.email", "t@test.com"], cwd=run_dir, capture_output=True)
    mpi_step.main(["init", "--run", str(run_dir)])
    return run_dir


_VALID_CRITERIA_GROUPING_UNITS = {
    "analysis_type": "diachronic",
    "participant": "p1s1",
    "reasoning_summary": "One IDU identified.",
    "idus": [
        {
            "idu_number": 1, "idu_name": "Opening Moment", "moment": 1,
            "criteria": "The utterances talk about the opening experience.",
            "confidence": 4, "flag_for_review": False,
            "utterance_numbers": ["1", "2"],
            "hinge_to_next": None,
            "utterance_refs": [
                {
                    "transcript_id": "p1s1",
                    "utterance_number": 1,
                    "byte_start": 0,
                    "byte_end": 20,
                    "raw_excerpt": "I noticed something.",
                }
            ],
        }
    ],
}

_VALID_PROMPT_ARTIFACT_DATA = {
    "schema_version": "2",
    "actor": {
        "kind": "subagent", "name": "mpi-analyst",
        "agent_file_sha256": "fakefakefakefake",
        "agent_file_path": "agents/mpi-analyst.md",
    },
    "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
    "sampling": {"temperature": 1.0, "top_p": 1.0, "top_k": None,
                 "max_tokens": 8192, "seed": None, "stop_sequences": []},
    "stage": "diachronic", "substep": "criteria_grouping", "scope": "p1s1",
    "prompt": {"system": "...", "messages": [], "tools_available": []},
    "response": {"raw_text": "...", "tool_calls": [], "parsed_units_path": ""},
    "metadata": {
        "finish_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50,
                  "cache_read_tokens": 0, "cache_write_tokens": 0},
        "duration_ms": 800, "timestamp": "2026-05-18T10:00:00Z",
        "anthropic_request_id": "req_e2e",
    },
}


class TestAC1_6_AgentSelfPersistEndToEnd:
    """
    AC1.6: mpi-analyst writes artifacts itself before invoking mpi_step.py close.
    This fixture simulates the agent workflow: write three files, then call close.
    No LLM is invoked — we're testing the close contract, not the analysis.
    """

    def test_agent_workflow_writes_artifacts_then_closes(self, tmp_path):
        run_dir = _setup_run_dir(tmp_path)
        analyses = run_dir / "analyses"
        analyses.mkdir()

        scope = "p1s1"
        stage = "diachronic"
        substep = "criteria_grouping"

        # Step 1: Agent writes JSON artifact
        json_path = analyses / f"{scope}-{stage}.{substep}.json"
        json_path.write_text(json.dumps(_VALID_CRITERIA_GROUPING_UNITS))

        # Step 2: Agent writes MD artifact
        md_path = analyses / f"{scope}-{stage}.{substep}.md"
        md_path.write_text("# IDU Analysis\n\n| IDU | Criteria |\n|-----|----------|\n| Opening Moment | ... |\n")

        # Step 3: Agent writes prompt-capture artifact
        prompt_path = analyses / f"{scope}-{stage}.{substep}.prompt.json"
        prompt_path.write_text(json.dumps(_VALID_PROMPT_ARTIFACT_DATA))

        # Step 4: Agent calls mpi_step.py close (simulated here)
        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", scope,
            "--stage", stage,
            "--substep", substep,
            "--scope", scope,
            "--artifact", str(json_path),
            "--artifact", str(md_path),
            "--prompt-artifact", str(prompt_path),
            "--units-json", str(json_path),
            "--reason", "criteria_grouping complete for p1s1",
            "--run-dir", str(run_dir),
        ])

        # Verify: close succeeded
        assert rc == 0, f"close returned {rc}"

        # Verify: manifest updated at substep granularity
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        substep_entry = (
            manifest.get("participants", {})
            .get(scope, {})
            .get("stages", {})
            .get(stage, {})
            .get("substeps", {})
            .get(substep, {})
        )
        assert substep_entry.get("status") == "done", f"substep not done: {substep_entry}"
        assert substep_entry.get("expected_action") == "git_commit_succeeded"
        assert "git_commit_sha" not in substep_entry  # AC1.4 self-reference impossibility

        # Verify: audit trail has full phase sequence
        audit_lines = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit_lines if l.strip()]
        actions = [e.get("event", {}).get("action") for e in events]
        assert "close_attempted" in actions
        assert "git_commit_succeeded" in actions

        # Verify: git has a commit with canonical message
        r = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=run_dir, capture_output=True, text=True,
        )
        assert f"mpi: mpi-analyst {stage}.{substep} {scope}" in r.stdout

    def test_agent_returning_error_instead_of_analysis_content(self, tmp_path):
        """AC1.7: When agent fails, it returns ERROR string, NOT analysis content."""
        # This is a documentation/contract test — verifies that the agent's
        # Persistence section instructs it to return ERROR, not content.
        content = AGENT_FILE.read_text(encoding="utf-8")
        # The Persistence section must document the ERROR return format
        assert "ERROR" in content and ("ERROR <" in content or "ERROR pNsN" in content), \
            "mpi-analyst.md Persistence section must document ERROR return format for failures"
        # The agent must NOT instruct itself to return analysis content on failure
        # (This is a best-effort check — full behavioral testing requires LLM-in-the-loop)
        persistence_idx = content.find("Persistence (mandatory before returning)")
        if persistence_idx >= 0:
            persistence_section = content[persistence_idx:]
            assert "Never return the analysis content" in persistence_section or \
                   "The orchestrator reads from disk" in persistence_section, \
                "mpi-analyst.md Persistence section must instruct agent to NOT return content"

"""
Tests verifying mpi-cross-analyst.md structural contracts from Phase 7.
These are contract tests — they verify the file contains the required sections and
declarations without invoking any LLM.
"""
from pathlib import Path
import re

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
AGENT_FILE = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"


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

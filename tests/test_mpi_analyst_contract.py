"""
Tests verifying mpi-analyst.md and SKILL.md structural contracts from Phase 6.
These are contract tests — they verify the files contain the required sections and
declarations without invoking any LLM.
"""
from pathlib import Path
import re
import sys

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
AGENT_FILE = PLUGIN_ROOT / "agents" / "mpi-analyst.md"
DIACHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
SYNCHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"


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

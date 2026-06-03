"""
Test plugin structure and acceptance criteria for microphenomenograph.

These tests verify:
- AC1.1: Plugin is installable (plugin.json exists and is valid)
- AC1.2: 10 skills are discoverable (each has SKILL.md with frontmatter)
- AC1.3: Unknown subcommand handling (mpi.md contains usage message)
- AC3.6: Zero-shot purity (phase2 p8-p13 never in few-shot examples)
- AC7.3: Kappa warning threshold behavior
"""

import json
import subprocess
import sys
import tempfile
import csv
import pytest
from pathlib import Path


# Root of the plugin
PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"


class TestAC1_1_PluginInstallable:
    """AC1.1: Plugin is installable."""

    def test_plugin_json_exists(self):
        """Assert plugin.json exists at the expected path."""
        plugin_json = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
        assert plugin_json.exists(), f"plugin.json not found at {plugin_json}"

    def test_plugin_json_valid(self):
        """Assert plugin.json is valid JSON."""
        plugin_json = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
        with open(plugin_json, "r") as f:
            data = json.load(f)  # Will raise if not valid JSON
        assert isinstance(data, dict), "plugin.json should contain a JSON object"

    def test_plugin_json_required_fields(self):
        """Assert plugin.json has required fields: name and version."""
        plugin_json = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
        with open(plugin_json, "r") as f:
            data = json.load(f)
        assert "name" in data, "plugin.json missing 'name' field"
        assert "version" in data, "plugin.json missing 'version' field"
        assert data["name"] == "microphenomenograph", "name should be 'microphenomenograph'"
        assert data["version"] == "1.0.0", "version should be '1.0.0'"


class TestAC1_2_SkillsDiscoverable:
    """AC1.2: 10 skills are discoverable with valid SKILL.md files."""

    EXPECTED_SKILLS = [
        "mpi-init",
        "mpi-status",
        "mpi-transcript-prep",
        "mpi-diachronic",
        "mpi-synchronic",
        "mpi-generic-diachronic",
        "mpi-generic-synchronic",
        "mpi-global-synchronic",
        "mpi-hypothesis",
        "mpi-irr",
    ]

    def test_all_10_skills_exist(self):
        """Assert all 10 skill directories exist."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.EXPECTED_SKILLS:
            skill_path = skills_dir / skill_name
            assert skill_path.is_dir(), f"Skill directory not found: {skill_path}"

    def test_all_skills_have_skill_md(self):
        """Assert each skill has a SKILL.md file."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.EXPECTED_SKILLS:
            skill_md = skills_dir / skill_name / "SKILL.md"
            assert skill_md.exists(), f"SKILL.md not found for {skill_name} at {skill_md}"

    def test_skill_md_has_frontmatter(self):
        """Assert each SKILL.md starts with --- (YAML frontmatter)."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.EXPECTED_SKILLS:
            skill_md = skills_dir / skill_name / "SKILL.md"
            with open(skill_md, "r") as f:
                first_line = f.readline().strip()
            assert (
                first_line == "---"
            ), f"SKILL.md for {skill_name} does not start with --- (YAML frontmatter)"

    def test_skill_md_has_name_field(self):
        """Assert each SKILL.md has a 'name:' field in frontmatter."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.EXPECTED_SKILLS:
            skill_md = skills_dir / skill_name / "SKILL.md"
            with open(skill_md, "r") as f:
                content = f.read()
            # Check that there is a "name:" field in the frontmatter
            lines = content.split("\n")
            found_name = False
            for i, line in enumerate(lines[1:10]):  # Check first 10 lines for name field
                if line.startswith("name:"):
                    found_name = True
                    break
            assert (
                found_name
            ), f"SKILL.md for {skill_name} does not have 'name:' field in frontmatter"


class TestAC1_3_UnknownSubcommand:
    """AC1.3: Unknown subcommand handling."""

    def test_mpi_md_unknown_subcommand_message(self):
        """Assert mpi.md contains 'Unknown subcommand' message."""
        mpi_md = PLUGIN_ROOT / "commands" / "mpi.md"
        assert mpi_md.exists(), f"mpi.md not found at {mpi_md}"
        with open(mpi_md, "r") as f:
            content = f.read()
        assert (
            "Unknown subcommand" in content
        ), "mpi.md should contain 'Unknown subcommand' message"

    def test_mpi_md_lists_main_subcommands(self):
        """Assert mpi.md lists the main subcommands."""
        mpi_md = PLUGIN_ROOT / "commands" / "mpi.md"
        with open(mpi_md, "r") as f:
            content = f.read()

        required_subcommands = ["init", "status", "transcript-prep", "diachronic", "synchronic"]
        for subcommand in required_subcommands:
            assert (
                subcommand in content
            ), f"mpi.md does not mention subcommand '{subcommand}'"


class TestManualNativeSubPhaseExclusion:
    """Test: Diachronic excludes sub-phase methodology, synchronic scopes to ISU per IDU."""

    def test_diachronic_excludes_subphase_identification(self):
        """Assert mpi-diachronic SKILL.md excludes sub-phase identification."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        # Diachronic explicitly excludes sub-phase identification
        assert (
            "sub-phase identification" in content.lower()
        ), "mpi-diachronic should document exclusion of sub-phase identification"
        # Check for references to excluded substep names
        assert (
            "diachronic.phases" in content
        ), "mpi-diachronic should reference excluded diachronic.phases substep"
        # Check for explicit exclusion language
        assert (
            "does NOT include" in content or "NOT include" in content
        ), "mpi-diachronic should explicitly state it does NOT include sub-phase steps"

    def test_synchronic_scopes_to_isu_per_idu(self):
        """Assert mpi-synchronic SKILL.md operates on ISUs per IDU (synchronic scope, not diachronic phases)."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        # Synchronic must document its own methodology: ISU per IDU
        assert (
            "synchronic.theme_grouping_within_idu" in content
        ), "mpi-synchronic must reference synchronic.theme_grouping_within_idu substep"
        # Synchronic should document ISU (Invariant Structures of Utterances) analysis
        assert (
            "ISU" in content
        ), "mpi-synchronic must reference ISU (Invariant Structures of Utterances)"
        # Synchronic should document per-IDU iteration (not diachronic.phases)
        assert (
            "per IDU within a transcript" in content
            or "synchronic.isu_naming" in content
        ), "mpi-synchronic must document per-IDU scope"
        # Check that diachronic.phases (sub-phase methodology) is NOT a synchronic concern
        assert (
            "diachronic.phases" not in content
        ), "mpi-synchronic should NOT reference diachronic.phases (diachronic-only substep)"


class TestAC3_6_ZeroShotPurity:
    """AC3.6: Phase 2 study-cohort transcripts (p8-p13) never appear as few-shot examples (zero-shot purity)."""

    def test_diachronic_declares_zero_shot(self):
        """Assert mpi-diachronic SKILL.md declares zero-shot (no examples)."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        assert (
            "zero-shot" in content.lower() or "no examples" in content.lower()
        ), "mpi-diachronic must declare zero-shot or no examples"

    def test_synchronic_declares_zero_shot(self):
        """Assert mpi-synchronic SKILL.md declares zero-shot (no examples)."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        assert (
            "zero-shot" in content.lower() or "no examples" in content.lower()
        ), "mpi-synchronic must declare zero-shot or no examples"

    def test_diachronic_no_few_shot_example_blocks(self):
        """Assert mpi-diachronic contains no few-shot example block markers (### Example or ## Example)."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        assert (
            "### Example" not in content and "## Example" not in content
        ), "mpi-diachronic must not contain example block headings (### Example or ## Example)"
        # Also check that no phase-2 participant IDs appear (p8-p13)
        for participant_id in ["p8", "p9", "p10", "p11", "p12", "p13"]:
            # Only fail if the participant ID appears outside of generic prose (e.g., "pNsN" placeholder text)
            # For now, verify that no explicit phase-2 participant references exist
            import re
            phase2_refs = re.findall(rf"{participant_id}s\d+", content)
            assert (
                len(phase2_refs) == 0
            ), f"mpi-diachronic must not reference phase-2 participant {participant_id} in examples"

    def test_synchronic_no_few_shot_example_blocks(self):
        """Assert mpi-synchronic contains no few-shot example block markers (### Example or ## Example)."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        assert (
            "### Example" not in content and "## Example" not in content
        ), "mpi-synchronic must not contain example block headings (### Example or ## Example)"
        # Also check that no phase-2 participant IDs appear (p8-p13)
        for participant_id in ["p8", "p9", "p10", "p11", "p12", "p13"]:
            import re
            phase2_refs = re.findall(rf"{participant_id}s\d+", content)
            assert (
                len(phase2_refs) == 0
            ), f"mpi-synchronic must not reference phase-2 participant {participant_id} in examples"


class TestAC6_3_ClosureSubsections:
    """AC6.3: Every SKILL.md has a Closure (mandatory) subsection."""

    SKILLS_WITH_CLOSURE = [
        "mpi-init",
        "mpi-transcript-prep",
        "mpi-diachronic",
        "mpi-synchronic",
        "mpi-generic-diachronic",
        "mpi-generic-synchronic",
        "mpi-global-synchronic",
        "mpi-hypothesis",
        "mpi-irr",
        "mpi-status",
    ]

    def test_all_closure_subsections_present(self):
        """Assert each SKILL.md contains ## Closure (mandatory) heading."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.SKILLS_WITH_CLOSURE:
            skill_md = skills_dir / skill_name / "SKILL.md"
            assert skill_md.exists(), f"SKILL.md not found for {skill_name}"
            content = skill_md.read_text(encoding="utf-8")
            assert (
                "## Closure (mandatory)" in content
            ), f"{skill_name} SKILL.md is missing '## Closure (mandatory)' heading"


class TestAC6_4_ReadOnlySkillDeclaration:
    """AC6.4: Read-only skills explicitly declare no artifact close and stage_phase: read."""

    def test_mpi_status_declares_read_only(self):
        """Assert mpi-status/SKILL.md contains 'read-only' declaration."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-status" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert (
            "read-only" in content.lower()
        ), "mpi-status/SKILL.md should declare itself a read-only skill"

    def test_mpi_status_declares_stage_phase_read(self):
        """Assert mpi-status/SKILL.md contains 'stage_phase: read'."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-status" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert (
            "stage_phase: read" in content
        ), "mpi-status/SKILL.md should declare 'stage_phase: read' for trace continuity"

    def test_mpi_irr_is_not_read_only(self):
        """Assert mpi-irr/SKILL.md explicitly states it is NOT read-only."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-irr" / "SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert (
            "NOT a read-only skill" in content
        ), "mpi-irr/SKILL.md should clarify it is NOT a read-only skill"


class TestAC7_1_OldHandwrittenContractsRemoved:
    """AC7.1: No SKILL.md hand-specifies manifest mutation prose, log line format, or git commit format."""

    SKILLS_TO_CHECK = [
        "mpi-init",
        "mpi-transcript-prep",
        "mpi-diachronic",
        "mpi-synchronic",
        "mpi-generic-diachronic",
        "mpi-generic-synchronic",
        "mpi-global-synchronic",
        "mpi-hypothesis",
        "mpi-irr",
        "mpi-status",
    ]

    def _pre_closure_content(self, content: str) -> str:
        """Return the content before the ## Closure (mandatory) section."""
        marker = "## Closure (mandatory)"
        idx = content.find(marker)
        if idx == -1:
            return content
        return content[:idx]

    def test_no_os_replace(self):
        """Assert no SKILL.md contains 'os.replace' (legacy atomic-write pattern)."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.SKILLS_TO_CHECK:
            skill_md = skills_dir / skill_name / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            assert (
                "os.replace" not in content
            ), f"{skill_name}/SKILL.md contains 'os.replace' (legacy atomic-write prose)"

    def test_no_project_json_tmp(self):
        """Assert no SKILL.md contains 'project.json.tmp' (legacy atomic-write pattern)."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.SKILLS_TO_CHECK:
            skill_md = skills_dir / skill_name / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            assert (
                "project.json.tmp" not in content
            ), f"{skill_name}/SKILL.md contains 'project.json.tmp' (legacy manifest mutation prose)"

    def test_no_log_line_format_prose(self):
        """Assert no SKILL.md contains log-line format prose outside a Closure section."""
        skills_dir = PLUGIN_ROOT / "skills"
        # The old pattern was: [<ISO timestamp>] or [<timestamp>] in a code block describing log format
        for skill_name in self.SKILLS_TO_CHECK:
            skill_md = skills_dir / skill_name / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            pre_closure = self._pre_closure_content(content)
            assert (
                "Append to `.mpi/reasoning.log`" not in pre_closure
            ), f"{skill_name}/SKILL.md contains reasoning.log format prose outside Closure section"

    def test_no_hand_crafted_git_commit_outside_closure(self):
        """Assert no SKILL.md contains hand-crafted 'git commit -m \"mpi:' lines outside Closure."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.SKILLS_TO_CHECK:
            skill_md = skills_dir / skill_name / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            pre_closure = self._pre_closure_content(content)
            assert (
                'git commit -m "mpi:' not in pre_closure
            ), f"{skill_name}/SKILL.md contains hand-crafted git commit outside Closure section"

    def test_no_update_manifest_prose_outside_closure(self):
        """Assert no SKILL.md contains 'Update manifest' prose outside Closure section."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.SKILLS_TO_CHECK:
            skill_md = skills_dir / skill_name / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            pre_closure = self._pre_closure_content(content)
            assert (
                "Update manifest" not in pre_closure
            ), f"{skill_name}/SKILL.md contains 'Update manifest' prose outside Closure section"

    def test_no_commit_if_yolo_prose_outside_closure(self):
        """Assert no SKILL.md contains 'commit if yolo' prose outside Closure section."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.SKILLS_TO_CHECK:
            skill_md = skills_dir / skill_name / "SKILL.md"
            content = skill_md.read_text(encoding="utf-8")
            pre_closure = self._pre_closure_content(content)
            assert (
                "commit if yolo" not in pre_closure
            ), f"{skill_name}/SKILL.md contains 'commit if yolo' prose outside Closure section"


class TestAC5_3_AntiFabrication:
    """AC5.3: Anti-fabrication rule present in all generative files."""

    GENERATIVE_SKILLS = [
        "mpi-diachronic",
        "mpi-synchronic",
        "mpi-generic-diachronic",
        "mpi-generic-synchronic",
        "mpi-global-synchronic",
        "mpi-hypothesis",
    ]

    NON_GENERATIVE_SKILLS = [
        "mpi-init",
        "mpi-transcript-prep",
        "mpi-status",
    ]

    ANTI_FAB_STRING = "Never generate placeholder or synthetic"

    def test_generative_skills_have_anti_fabrication_rule(self):
        """Assert each generative SKILL.md contains the anti-fabrication rule."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.GENERATIVE_SKILLS:
            skill_md = skills_dir / skill_name / "SKILL.md"
            assert skill_md.exists(), f"SKILL.md not found for {skill_name}"
            content = skill_md.read_text(encoding="utf-8")
            assert self.ANTI_FAB_STRING in content, (
                f"{skill_name}/SKILL.md is missing anti-fabrication rule "
                f"(expected '{self.ANTI_FAB_STRING}')"
            )

    def test_mpi_analyst_has_anti_fabrication_rule(self):
        """Assert mpi-analyst.md contains the anti-fabrication rule."""
        agent_md = PLUGIN_ROOT / "agents" / "mpi-analyst.md"
        assert agent_md.exists(), f"mpi-analyst.md not found at {agent_md}"
        content = agent_md.read_text(encoding="utf-8")
        assert self.ANTI_FAB_STRING in content, (
            f"mpi-analyst.md is missing anti-fabrication rule "
            f"(expected '{self.ANTI_FAB_STRING}')"
        )

    def test_mpi_cross_analyst_has_anti_fabrication_rule(self):
        """Assert mpi-cross-analyst.md contains the anti-fabrication rule."""
        agent_md = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"
        assert agent_md.exists(), f"mpi-cross-analyst.md not found at {agent_md}"
        content = agent_md.read_text(encoding="utf-8")
        assert self.ANTI_FAB_STRING in content, (
            f"mpi-cross-analyst.md is missing anti-fabrication rule "
            f"(expected '{self.ANTI_FAB_STRING}')"
        )

    def test_non_generative_skills_do_not_have_anti_fabrication_rule(self):
        """Assert orchestrator-run skills do NOT contain the anti-fabrication rule."""
        skills_dir = PLUGIN_ROOT / "skills"
        for skill_name in self.NON_GENERATIVE_SKILLS:
            skill_md = skills_dir / skill_name / "SKILL.md"
            assert skill_md.exists(), f"SKILL.md not found for {skill_name}"
            content = skill_md.read_text(encoding="utf-8")
            assert self.ANTI_FAB_STRING not in content, (
                f"{skill_name}/SKILL.md unexpectedly contains the anti-fabrication rule "
                f"(it is an orchestrator-run skill, not a generative LLM skill)"
            )


class TestAC7_3_KappaWarningThreshold:
    """AC7.3: Kappa < 0.61 triggers warning and exit code 2. [LEGACY: kappa.py merged into irr.py in Phase 13]"""

    def test_kappa_warning_on_low_value(self):
        """Test that kappa.py emits WARNING and exits with code 2 when below threshold. [SKIPPED: kappa.py merged into irr.py]"""
        kappa_script = PLUGIN_ROOT / "scripts" / "kappa.py"
        # Phase 13: kappa.py merged into irr.py; functionality tested via test_kappa.py
        if not kappa_script.exists():
            pytest.skip("kappa.py merged into irr.py (Phase 13); functionality in irr.compute_kappa and test_kappa.py")

        # Create minimal CSV files that produce low kappa
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create minimal diachronic CSVs with different categorizations
            # to produce low agreement (and thus low kappa)
            dia1_path = tmpdir / "dia1.csv"
            dia2_path = tmpdir / "dia2.csv"
            syn1_path = tmpdir / "syn1.csv"
            syn2_path = tmpdir / "syn2.csv"

            # Diachronic CSV 1: all utterances assigned to Moment 1
            with open(dia1_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Speaker", "#", "Utterance", "Moment", "IDU", "Criteria"])
                writer.writeheader()
                for i in range(1, 11):
                    writer.writerow({
                        "Speaker": "P",
                        "#": str(i),
                        "Utterance": f"ut{i}",
                        "Moment": "1",
                        "IDU": f"idu{i}",
                        "Criteria": "X",
                    })

            # Diachronic CSV 2: utterances 1-5 assigned to Moment 2, 6-10 to Moment 3
            with open(dia2_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Speaker", "#", "Utterance", "Moment", "IDU", "Criteria"])
                writer.writeheader()
                for i in range(1, 11):
                    moment = "2" if i <= 5 else "3"
                    writer.writerow({
                        "Speaker": "P",
                        "#": str(i),
                        "Utterance": f"ut{i}",
                        "Moment": moment,
                        "IDU": f"idu{i}",
                        "Criteria": "X",
                    })

            # Synchronic CSV 1: all utterances assigned to ISUnum 1
            with open(syn1_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["IDU", "#", "Utterance", "Criteria", "ISU", "ISU 2nd Level of Abstraction", "ISUnum"])
                writer.writeheader()
                for i in range(1, 11):
                    writer.writerow({
                        "IDU": f"idu{i}",
                        "#": str(i),
                        "Utterance": f"ut{i}",
                        "Criteria": "X",
                        "ISU": "ISU1",
                        "ISU 2nd Level of Abstraction": "L2",
                        "ISUnum": "1",
                    })

            # Synchronic CSV 2: different ISUnum assignments
            with open(syn2_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["IDU", "#", "Utterance", "Criteria", "ISU", "ISU 2nd Level of Abstraction", "ISUnum"])
                writer.writeheader()
                for i in range(1, 11):
                    isunum = "2" if i <= 5 else "3"
                    writer.writerow({
                        "IDU": f"idu{i}",
                        "#": str(i),
                        "Utterance": f"ut{i}",
                        "Criteria": "X",
                        "ISU": f"ISU{isunum}",
                        "ISU 2nd Level of Abstraction": "L2",
                        "ISUnum": isunum,
                    })

            # Run kappa.py
            result = subprocess.run(
                [sys.executable, str(kappa_script), str(dia1_path), str(dia2_path), str(syn1_path), str(syn2_path)],
                capture_output=True,
                text=True,
            )

            # Assert exit code is 2 (below threshold)
            assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}. Output: {result.stdout}\nStderr: {result.stderr}"

            # Assert WARNING is in stdout
            assert "WARNING" in result.stdout, f"Expected 'WARNING' in stdout. Got: {result.stdout}"

    def test_kappa_no_warning_on_high_value(self):
        """Test that kappa.py does not warn when kappa >= 0.61. [SKIPPED: kappa.py merged into irr.py]"""
        kappa_script = PLUGIN_ROOT / "scripts" / "kappa.py"
        # Phase 13: kappa.py merged into irr.py; functionality tested via test_kappa.py
        if not kappa_script.exists():
            pytest.skip("kappa.py merged into irr.py (Phase 13); functionality in irr.compute_kappa and test_kappa.py")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # Create CSVs with high agreement (same categorizations)
            dia1_path = tmpdir / "dia1.csv"
            dia2_path = tmpdir / "dia2.csv"
            syn1_path = tmpdir / "syn1.csv"
            syn2_path = tmpdir / "syn2.csv"

            # Both diachronic CSVs: identical categorizations
            for csv_path in [dia1_path, dia2_path]:
                with open(csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["Speaker", "#", "Utterance", "Moment", "IDU", "Criteria"])
                    writer.writeheader()
                    for i in range(1, 11):
                        writer.writerow({
                            "Speaker": "P",
                            "#": str(i),
                            "Utterance": f"ut{i}",
                            "Moment": "1",
                            "IDU": f"idu{i}",
                            "Criteria": "X",
                        })

            # Both synchronic CSVs: identical categorizations
            for csv_path in [syn1_path, syn2_path]:
                with open(csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=["IDU", "#", "Utterance", "Criteria", "ISU", "ISU 2nd Level of Abstraction", "ISUnum"])
                    writer.writeheader()
                    for i in range(1, 11):
                        writer.writerow({
                            "IDU": f"idu{i}",
                            "#": str(i),
                            "Utterance": f"ut{i}",
                            "Criteria": "X",
                            "ISU": "ISU1",
                            "ISU 2nd Level of Abstraction": "L2",
                            "ISUnum": "1",
                        })

            # Run kappa.py
            result = subprocess.run(
                [sys.executable, str(kappa_script), str(dia1_path), str(dia2_path), str(syn1_path), str(syn2_path)],
                capture_output=True,
                text=True,
            )

            # Assert exit code is 0 (success, above threshold or no warning)
            assert result.returncode == 0, f"Expected exit code 0, got {result.returncode}. Output: {result.stdout}\nStderr: {result.stderr}"

            # Assert no WARNING in stdout when kappa is high
            # (kappa will be 1.0 due to perfect agreement)
            assert "WARNING" not in result.stdout, f"Unexpected WARNING in stdout. Got: {result.stdout}"

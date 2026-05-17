"""
Test plugin structure and acceptance criteria for microphenomenograph.

These tests verify:
- AC1.1: Plugin is installable (plugin.json exists and is valid)
- AC1.2: 10 skills are discoverable (each has SKILL.md with frontmatter)
- AC1.3: Unknown subcommand handling (mpi.md contains usage message)
- AC3.6: Phase2 exclusion in diachronic and synchronic skills
- AC7.3: Kappa warning threshold behavior
"""

import json
import subprocess
import sys
import tempfile
import csv
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
        "mpi-kappa",
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


class TestAC3_6_Phase2Exclusion:
    """AC3.6 structural: Phase2 exclusion in diachronic and synchronic."""

    def test_diachronic_phase2_exclusion(self):
        """Assert mpi-diachronic SKILL.md excludes phase2."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        assert (
            "phase2" in content.lower()
        ), "mpi-diachronic SKILL.md should mention phase2 exclusion"
        # Check for explicit warning text
        assert (
            "NEVER" in content and "phase2" in content.lower()
        ), "mpi-diachronic should warn against using phase2"

    def test_synchronic_phase2_exclusion(self):
        """Assert mpi-synchronic SKILL.md excludes phase2."""
        skill_md = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"
        with open(skill_md, "r") as f:
            content = f.read()
        assert (
            "phase2" in content.lower()
        ), "mpi-synchronic SKILL.md should mention phase2"


class TestAC7_3_KappaWarningThreshold:
    """AC7.3: Kappa < 0.61 triggers warning and exit code 2."""

    def test_kappa_warning_on_low_value(self):
        """Test that kappa.py emits WARNING and exits with code 2 when below threshold."""
        kappa_script = PLUGIN_ROOT / "scripts" / "kappa.py"
        assert kappa_script.exists(), f"kappa.py not found at {kappa_script}"

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
        """Test that kappa.py does not warn when kappa >= 0.61."""
        kappa_script = PLUGIN_ROOT / "scripts" / "kappa.py"

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

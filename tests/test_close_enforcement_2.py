"""
Integration tests for close-enforcement-2 design plan.

Phase 2: AC2.3 grep assertion (no dead literal generic-synchronic.md reference).
Note: AC2.3 will remain xfail until Phase 3 removes the dead references.
"""
from pathlib import Path
import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
GLOBAL_SYNC_SKILL = PLUGIN_ROOT / "skills" / "mpi-global-synchronic" / "SKILL.md"
CROSS_ANALYST_AGENT = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"


def test_no_literal_generic_synchronic_artifact_in_global_synchronic_skill():
    """AC2.3: Neither mpi-global-synchronic/SKILL.md nor mpi-cross-analyst.md should contain
    a literal reference to the non-existent cross-stage artifact 'generic-synchronic.md'.
    """
    dead_literals = ["generic-synchronic.md", "analyses/generic-synchronic.md"]

    for path in (GLOBAL_SYNC_SKILL, CROSS_ANALYST_AGENT):
        assert path.exists(), f"Expected file to exist: {path}"
        content = path.read_text(encoding="utf-8")
        for literal in dead_literals:
            assert literal not in content, (
                f"Dead literal {literal!r} found in {path.name}. "
                f"This reference must be replaced with the `inputs` verb "
                f"(mpi_step.py inputs --scope ... --stage ...) in Phase 3."
            )

"""
Integration tests for close-enforcement-2 design plan.

Phase 2: AC2.3 grep assertion (no dead literal generic-synchronic.md reference).
Note: AC2.3 will remain xfail until Phase 3 removes the dead references.

Phase 4: AC4.5 SKILL-claims-code parity sweep.
"""
from pathlib import Path
import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
GLOBAL_SYNC_SKILL = PLUGIN_ROOT / "skills" / "mpi-global-synchronic" / "SKILL.md"
CROSS_ANALYST_AGENT = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"
DIACHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
SYNCHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"
MPI_STEP_PY = PLUGIN_ROOT / "scripts" / "mpi_step.py"


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


# ---------------------------------------------------------------------------
# Phase 4: AC4.5 SKILL-claims-code parity sweep
# ---------------------------------------------------------------------------

def test_diachronic_skill_convergence_claim_has_code_path():
    """AC4.5: mpi-diachronic/SKILL.md mentions 'flagged'; mpi_step.py implements
    more_revision_needed downgrade and convergence_pending gate."""
    assert DIACHRONIC_SKILL.exists(), f"Expected {DIACHRONIC_SKILL}"
    assert MPI_STEP_PY.exists(), f"Expected {MPI_STEP_PY}"

    skill_content = DIACHRONIC_SKILL.read_text(encoding="utf-8")
    step_content = MPI_STEP_PY.read_text(encoding="utf-8")

    assert "flagged" in skill_content, (
        "mpi-diachronic/SKILL.md must mention 'flagged' to document the downgrade behaviour"
    )
    assert "more_revision_needed" in step_content, (
        "mpi_step.py must contain 'more_revision_needed' (criteria_revision downgrade logic)"
    )
    assert "convergence_pending" in step_content, (
        "mpi_step.py must contain 'convergence_pending' (gate ID for convergence downgrade)"
    )


def test_synchronic_skill_temporal_order_claim_has_code_path():
    """AC4.5: mpi-synchronic/SKILL.md mentions 'flagged'; mpi_step.py implements
    temporal_order_within_idu downgrade and temporal_order_pending gate."""
    assert SYNCHRONIC_SKILL.exists(), f"Expected {SYNCHRONIC_SKILL}"
    assert MPI_STEP_PY.exists(), f"Expected {MPI_STEP_PY}"

    skill_content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
    step_content = MPI_STEP_PY.read_text(encoding="utf-8")

    assert "flagged" in skill_content, (
        "mpi-synchronic/SKILL.md must mention 'flagged' to document the downgrade behaviour"
    )
    assert "temporal_order_within_idu" in step_content, (
        "mpi_step.py must contain 'temporal_order_within_idu' (theme_grouping downgrade logic)"
    )
    assert "temporal_order_pending" in step_content, (
        "mpi_step.py must contain 'temporal_order_pending' (gate ID for temporal order downgrade)"
    )


def test_idu_split_audit_event_claim_has_code_path():
    """AC4.5: mpi-synchronic/SKILL.md mentions 'idu_split_after_synchronic';
    mpi_step.py emits that event."""
    assert SYNCHRONIC_SKILL.exists(), f"Expected {SYNCHRONIC_SKILL}"
    assert MPI_STEP_PY.exists(), f"Expected {MPI_STEP_PY}"

    skill_content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
    step_content = MPI_STEP_PY.read_text(encoding="utf-8")

    assert "idu_split_after_synchronic" in skill_content, (
        "mpi-synchronic/SKILL.md must mention 'idu_split_after_synchronic' "
        "(the audit event documenting IDU split)"
    )
    assert "idu_split_after_synchronic" in step_content, (
        "mpi_step.py must contain 'idu_split_after_synchronic' (the audit event emission)"
    )

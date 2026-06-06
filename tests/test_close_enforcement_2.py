"""
Integration tests for close-enforcement-2 design plan.

Phase 2: AC2.3 grep assertion (no dead literal generic-synchronic.md reference).
Note: AC2.3 will remain xfail until Phase 3 removes the dead references.

Phase 4: AC4.5 SKILL-claims-code parity sweep.

hypothesis-evidence Phase 1: AC1.1, AC1.2 — Evidence inputs via `inputs` verb.
"""
import sys
from pathlib import Path
import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

HYPOTHESIS_SKILL = PLUGIN_ROOT / "skills" / "mpi-hypothesis" / "SKILL.md"
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


# ---------------------------------------------------------------------------
# hypothesis-evidence Phase 1: AC1.1, AC1.2 — Evidence inputs via `inputs` verb
# ---------------------------------------------------------------------------

def _make_manifest_with_all_three_stages() -> dict:
    """Build a minimal manifest with participants covering all three cross-participant stages.

    Key patterns:
    - event1-cat-high            -> generic_diachronic (has -cat-, no -gidu)
    - event1-cat-high-gidu1      -> generic_synchronic (has -cat- AND -gidu)
    - gidu1-cat-high             -> global_synchronic (starts with gidu)
    - p1s1                       -> transcript key (should be excluded from hypothesis resolution)
    """
    def _make_substep(paths, shas):
        return {"output_paths": paths, "artifact_shas": shas, "status": "done"}

    return {
        "study": {"event_groups": {"event1": ["p1s1"]}},
        "participants": {
            "event1-cat-high": {
                "stages": {
                    "generic_diachronic": {
                        "substeps": {
                            "cross_iv_contrast": _make_substep(
                                ["analyses/gd-event1-cat-high.json"],
                                {"analyses/gd-event1-cat-high.json": "sha-gd-1"},
                            )
                        }
                    }
                }
            },
            "event1-cat-high-gidu1": {
                "stages": {
                    "generic_synchronic": {
                        "substeps": {
                            "isu_second_level_grouping": _make_substep(
                                ["analyses/gs-event1-cat-high-gidu1.json"],
                                {"analyses/gs-event1-cat-high-gidu1.json": "sha-gs-1"},
                            )
                        }
                    }
                }
            },
            "gidu1-cat-high": {
                "stages": {
                    "global_synchronic": {
                        "substeps": {
                            "global_synchronic": _make_substep(
                                ["analyses/globs-gidu1-cat-high.json"],
                                {"analyses/globs-gidu1-cat-high.json": "sha-globs-1"},
                            )
                        }
                    }
                }
            },
            "p1s1": {
                "stages": {
                    "diachronic": {
                        "substeps": {
                            "idu_naming_ordering": _make_substep(
                                ["analyses/p1s1-diachronic.json"],
                                {"analyses/p1s1-diachronic.json": "sha-p1s1"},
                            )
                        }
                    }
                }
            },
        },
    }


def test_AC1_1_hypothesis_inputs_resolution_returns_all_three_stages():
    """AC1.1: inputs verb for hypothesis stage returns artifacts from all three
    cross-participant stages (generic_diachronic, generic_synchronic, global_synchronic)."""
    from mpi_step import _resolve_inputs

    manifest = _make_manifest_with_all_three_stages()
    result = _resolve_inputs(manifest, "hypothesis", "dv-automaticity")

    assert result is not None, "_resolve_inputs returned None for hypothesis stage"

    paths = [entry["path"] for entry in result]

    # Must include the generic_diachronic artifact
    assert any("gd-event1-cat-high" in p for p in paths), (
        f"generic_diachronic artifact not found in hypothesis inputs. Got: {paths}"
    )
    # Must include the generic_synchronic artifact
    assert any("gs-event1-cat-high-gidu1" in p for p in paths), (
        f"generic_synchronic artifact not found in hypothesis inputs. Got: {paths}"
    )
    # Must include the global_synchronic artifact
    assert any("globs-gidu1-cat-high" in p for p in paths), (
        f"global_synchronic artifact not found in hypothesis inputs. Got: {paths}"
    )


def test_AC1_1_hypothesis_inputs_resolution_excludes_transcript_keys():
    """AC1.1: Transcript-participant keys (pNsN) are not included in hypothesis resolution."""
    from mpi_step import _resolve_inputs

    manifest = _make_manifest_with_all_three_stages()
    result = _resolve_inputs(manifest, "hypothesis", "dv-automaticity")

    assert result is not None, "_resolve_inputs returned None for hypothesis stage"

    paths = [entry["path"] for entry in result]

    # Transcript-level artifact from p1s1 must NOT appear in hypothesis inputs
    assert not any("p1s1-diachronic" in p for p in paths), (
        f"Transcript key p1s1 artifact found in hypothesis inputs — it should be excluded. Got: {paths}"
    )


def test_AC1_2_skill_md_no_literal_global_synchronic_artifact():
    """AC1.2: mpi-hypothesis/SKILL.md contains no literal cross-stage artifact filename
    'global-synchronic.md' (the old hardcoded path), and cites the `inputs` verb."""
    assert HYPOTHESIS_SKILL.exists(), f"Expected file to exist: {HYPOTHESIS_SKILL}"
    content = HYPOTHESIS_SKILL.read_text(encoding="utf-8")

    assert "global-synchronic.md" not in content, (
        "Forbidden literal 'global-synchronic.md' found in mpi-hypothesis/SKILL.md. "
        "All literal cross-stage artifact paths must be removed and replaced with the `inputs` verb."
    )
    assert "inputs" in content, (
        "mpi-hypothesis/SKILL.md must cite the `inputs` verb "
        "(mpi_step.py inputs --stage hypothesis ...) in its context documents section."
    )

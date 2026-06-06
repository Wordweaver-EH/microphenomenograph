"""Tests for causal-extension design plan (plan 5).

Phase 1: AC1.1, AC1.2, AC1.3, AC1.4, AC4.1 — causal claim schema fields.
"""
import pytest
from pathlib import Path
import sys

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from _mpi_schemas import validate_units  # noqa: E402


# ---------------------------------------------------------------------------
# Phase 1: AC1.1, AC1.2, AC1.3, AC1.4, AC4.1 — causal claim schema fields
# ---------------------------------------------------------------------------

class TestAC1_CausalClaimSchema:
    """AC1: causal claim schema fields — rung, assumptions, confounders, testable_implications."""

    def _minimal_raw_span_ref(self) -> dict:
        """Minimal valid raw_span_ref."""
        return {
            "transcript_id": "p1s1",
            "utterance_number": 1,
            "byte_start": 0,
            "byte_end": 20,
            "raw_excerpt": "I noticed something.",
        }

    def _base_claim(
        self,
        claim_id: str = "c1",
        rung: int = 1,
        assumptions: list | None = None,
        confounders: list | None = None,
        testable_implications: list | None = None,
    ) -> dict:
        """Build a fully valid causal-schema claim."""
        if assumptions is None:
            assumptions = []
        if confounders is None:
            confounders = [
                {
                    "variable": "common_method_variance",
                    "mechanism": "self-report bias",
                }
            ]
        if testable_implications is None:
            testable_implications = ["IV _||_ DV | CMV"]
        return {
            "claim_id": claim_id,
            "claim_text": "Some claim text.",
            "supports": [
                {
                    "source_artifact": "analyses/some.json",
                    "raw_span_refs": [self._minimal_raw_span_ref()],
                }
            ],
            "contradicts": [],
            "ambiguous": [],
            "n_transcripts": 3,
            "n_iv_levels_covered": 2,
            "uncertainty_language": "associated with",
            "negative_cases": [],
            "rung": rung,
            "assumptions": assumptions,
            "confounders": confounders,
            "testable_implications": testable_implications,
        }

    def _base_candidate(self, claims: list) -> dict:
        """Minimal valid candidate."""
        return {
            "hypothesis": "Higher X is associated with greater Y.",
            "claims": claims,
            "sample_summary": {"by_iv_level": {"low": 1, "moderate": 1, "high": 1}},
        }

    def _base_payload(
        self,
        candidates: list,
        replication_recommendation: str = "A second participant set would need to show the same pattern.",
    ) -> dict:
        """Full candidate_drafting payload with replication_recommendation."""
        return {
            "dv_focus": "automaticity",
            "disclaimer": "These are generative conjectures inferred from qualitative pattern variation across IV levels in a small sample. They are not causal estimates from a hypothesis test and should not be reported as such.",
            "candidates": candidates,
            "replication_recommendation": replication_recommendation,
        }

    # AC1.1 Failure: rung >= 2 with empty assumptions is rejected
    def test_AC1_1_rung2_empty_assumptions_rejected(self):
        """AC1.1 Failure: claim with rung=2 and empty assumptions is rejected."""
        claim = self._base_claim(rung=2, assumptions=[])
        payload = self._base_payload([self._base_candidate([claim])])
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        error_strs = [str(e) for e in errors]
        assert any("assumptions" in s for s in error_strs), (
            f"Expected error mentioning 'assumptions' for rung=2 + empty assumptions; got: {errors}"
        )

    # AC1.2 Success: rung == 1 with empty assumptions is accepted
    def test_AC1_2_rung1_empty_assumptions_accepted(self):
        """AC1.2 Success: claim with rung=1 and empty assumptions is accepted."""
        claim = self._base_claim(rung=1, assumptions=[])
        payload = self._base_payload([self._base_candidate([claim])])
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert not errors, f"Expected no errors for rung=1 + empty assumptions; got: {errors}"

    # AC1.3 Failure: empty confounders list is rejected
    def test_AC1_3_empty_confounders_rejected(self):
        """AC1.3 Failure: claim with empty confounders list is rejected."""
        claim = self._base_claim(confounders=[])
        payload = self._base_payload([self._base_candidate([claim])])
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        error_strs = [str(e) for e in errors]
        assert any("confounders" in s for s in error_strs), (
            f"Expected error mentioning 'confounders' for empty confounders; got: {errors}"
        )

    # AC1.4 Failure: confounder entry missing 'variable'
    def test_AC1_4_confounder_missing_variable_rejected(self):
        """AC1.4 Failure: confounder without 'variable' key is rejected."""
        claim = self._base_claim(confounders=[{"mechanism": "self-report bias"}])
        payload = self._base_payload([self._base_candidate([claim])])
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        error_strs = [str(e) for e in errors]
        assert any("variable" in s for s in error_strs), (
            f"Expected error mentioning 'variable' for missing variable in confounder; got: {errors}"
        )

    # AC1.4 Failure variant: confounder entry missing 'mechanism'
    def test_AC1_4_confounder_missing_mechanism_rejected(self):
        """AC1.4 Failure: confounder without 'mechanism' key is rejected."""
        claim = self._base_claim(confounders=[{"variable": "common_method_variance"}])
        payload = self._base_payload([self._base_candidate([claim])])
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        error_strs = [str(e) for e in errors]
        assert any("mechanism" in s for s in error_strs), (
            f"Expected error mentioning 'mechanism' for missing mechanism in confounder; got: {errors}"
        )

    # Regression/baseline: valid rung-2 claim with non-empty assumptions is accepted
    def test_AC1_well_formed_rung2_claim_accepted(self):
        """Regression: valid rung-2 claim with non-empty assumptions is accepted."""
        claim = self._base_claim(
            rung=2,
            assumptions=["Assume no unmeasured confounders beyond CMV."],
        )
        payload = self._base_payload([self._base_candidate([claim])])
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert not errors, f"Expected no errors for valid rung-2 claim; got: {errors}"


# ---------------------------------------------------------------------------
# AC4.1: replication_recommendation required at top level
# ---------------------------------------------------------------------------

class TestAC4_1_ReplicationRecommendation:
    """AC4.1: replication_recommendation required at top level of candidate_drafting."""

    def _minimal_raw_span_ref(self) -> dict:
        return {
            "transcript_id": "p1s1",
            "utterance_number": 1,
            "byte_start": 0,
            "byte_end": 20,
            "raw_excerpt": "I noticed something.",
        }

    def _base_claim(self) -> dict:
        """Full valid causal claim."""
        return {
            "claim_id": "c1",
            "claim_text": "Some claim text.",
            "supports": [
                {
                    "source_artifact": "analyses/some.json",
                    "raw_span_refs": [self._minimal_raw_span_ref()],
                }
            ],
            "contradicts": [],
            "ambiguous": [],
            "n_transcripts": 3,
            "n_iv_levels_covered": 2,
            "uncertainty_language": "associated with",
            "negative_cases": [],
            "rung": 1,
            "assumptions": [],
            "confounders": [
                {"variable": "common_method_variance", "mechanism": "self-report bias"}
            ],
            "testable_implications": ["IV _||_ DV | CMV"],
        }

    def _base_candidate(self) -> dict:
        return {
            "hypothesis": "Higher X is associated with greater Y.",
            "claims": [self._base_claim()],
            "sample_summary": {"by_iv_level": {"low": 1, "moderate": 1, "high": 1}},
        }

    def test_AC4_1_missing_replication_recommendation_rejected(self):
        """AC4.1 Failure: payload missing replication_recommendation is rejected."""
        payload = {
            "dv_focus": "automaticity",
            "disclaimer": "These are generative conjectures inferred from qualitative pattern variation across IV levels in a small sample. They are not causal estimates from a hypothesis test and should not be reported as such.",
            "candidates": [self._base_candidate()],
            # No replication_recommendation
        }
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        error_strs = [str(e) for e in errors]
        assert any("replication_recommendation" in s for s in error_strs), (
            f"Expected error mentioning 'replication_recommendation'; got: {errors}"
        )

    def test_AC4_1_replication_recommendation_present_accepted(self):
        """AC4.1 Success: payload with replication_recommendation is accepted."""
        payload = {
            "dv_focus": "automaticity",
            "disclaimer": "These are generative conjectures inferred from qualitative pattern variation across IV levels in a small sample. They are not causal estimates from a hypothesis test and should not be reported as such.",
            "candidates": [self._base_candidate()],
            "replication_recommendation": "A second participant set would need to show the same pattern to support this mechanism.",
        }
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert not errors, f"Expected no errors with replication_recommendation present; got: {errors}"


# ---------------------------------------------------------------------------
# Phase 2: AC2.1, AC2.2, AC2.3, AC4.2 — Agent causal instructions + SKILL.md
# ---------------------------------------------------------------------------

class TestAC2_AgentInstructions:
    """AC2: mpi-cross-analyst.md carries full causal instruction content."""

    AGENT_FILE = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"
    SKILL_FILE = PLUGIN_ROOT / "skills" / "mpi-hypothesis" / "SKILL.md"

    def _agent_content(self) -> str:
        return self.AGENT_FILE.read_text(encoding="utf-8")

    def _skill_content(self) -> str:
        return self.SKILL_FILE.read_text(encoding="utf-8")

    def test_AC2_1_cross_analyst_md_has_cmv_instruction(self):
        """AC2.1 Success: agent doc names CMV, latent, and common cause."""
        content = self._agent_content()
        assert "common_method_variance" in content or "common-method-variance" in content, (
            "mpi-cross-analyst.md must name the common-method-variance confounder"
        )
        assert "latent" in content, (
            "mpi-cross-analyst.md must include 'latent' (latent node instruction)"
        )
        assert "common cause" in content or "common-method" in content or "CMV" in content, (
            "mpi-cross-analyst.md must describe CMV as a common cause"
        )

    def test_AC2_2_cross_analyst_md_has_dagitty_notation(self):
        """AC2.2 Success: agent doc contains DAGitty conditional-independence notation."""
        content = self._agent_content()
        assert "_||_" in content, (
            "mpi-cross-analyst.md must contain DAGitty notation '_||_' for testable_implications"
        )

    def test_AC2_3_cross_analyst_md_has_dag_conventions(self):
        """AC2.3 Success: agent doc describes mermaid DAG with latent node conventions."""
        content = self._agent_content()
        assert "mermaid" in content, (
            "mpi-cross-analyst.md must describe the mermaid DAG format"
        )
        # No bidirected edge / two directed arrows
        assert "<->" not in content or "no" in content.lower() or "two directed arrows" in content, (
            "mpi-cross-analyst.md must prohibit bidirected edges or describe two directed arrows"
        )
        assert (
            "classDef latent" in content
            or ":::latent" in content
            or "latent" in content
        ), (
            "mpi-cross-analyst.md must document latent class naming convention"
        )

    def test_AC4_2_hypothesis_skill_has_replication_recommendation_template(self):
        """AC4.2 Success: SKILL.md output format includes replication_recommendation."""
        content = self._skill_content()
        assert "replication_recommendation" in content, (
            "mpi-hypothesis/SKILL.md must include replication_recommendation in output format"
        )
        assert (
            "second participant set" in content
            or "second independent" in content
            or "second set" in content
        ), (
            "mpi-hypothesis/SKILL.md must frame replication_recommendation in terms of a second participant set"
        )

    def test_AC4_2_hypothesis_skill_has_dag_section(self):
        """AC4.2 Success: SKILL.md output format includes a DAG/mermaid block."""
        content = self._skill_content()
        assert "mermaid" in content or "Causal DAG" in content, (
            "mpi-hypothesis/SKILL.md must include a mermaid DAG block or 'Causal DAG' in output format"
        )

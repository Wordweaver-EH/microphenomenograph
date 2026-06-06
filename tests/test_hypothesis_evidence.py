"""Tests for hypothesis-evidence design plan (plan 4).

Phase 2: AC2.1, AC2.2, AC2.3, AC2.4 — claim_id + review coverage schema.
Phase 3: AC3.1, AC3.2, AC3.3, AC3.4 — review gate and agent instructions.
"""
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from _mpi_schemas import validate_units  # noqa: E402


class TestAC2_ClaimIdCoverage:
    """AC2: claim_id required on candidate_drafting; review coverage schema."""

    def _minimal_raw_span_ref(self) -> dict:
        """Minimal valid raw_span_ref."""
        return {
            "transcript_id": "p1s1",
            "utterance_number": 1,
            "byte_start": 0,
            "byte_end": 20,
            "raw_excerpt": "I noticed something.",
        }

    def _base_claim(self, claim_id="c1", **kwargs) -> dict:
        """Minimal valid claim with claim_id."""
        claim = {
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
        }
        claim.update(kwargs)
        return claim

    def _base_candidate(self, claims) -> dict:
        """Minimal valid candidate with disclaimer."""
        return {
            "hypothesis": "Higher X is associated with greater Y.",
            "claims": claims,
            "sample_summary": {"by_iv_level": {"low": 1, "moderate": 1, "high": 1}},
        }

    def _base_candidate_drafting_payload(self, candidates) -> dict:
        """Full candidate_drafting payload."""
        return {
            "dv_focus": "automaticity",
            "disclaimer": "These are generative conjectures inferred from qualitative pattern variation across IV levels in a small sample. They are not causal estimates from a hypothesis test and should not be reported as such.",
            "candidates": candidates,
        }

    def test_AC2_1_missing_claim_id_rejected(self):
        """AC2.1 Failure: claim without claim_id is rejected."""
        claim = self._base_claim()
        del claim["claim_id"]
        payload = self._base_candidate_drafting_payload(
            [self._base_candidate([claim])]
        )
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert any("claim_id" in e.field for e in errors), (
            f"Expected error mentioning claim_id field; got: {errors}"
        )

    def test_AC2_1_claim_id_present_passes_basic_schema(self):
        """Success: candidate_drafting claim with claim_id passes schema."""
        claim = self._base_claim(claim_id="c1")
        payload = self._base_candidate_drafting_payload(
            [self._base_candidate([claim])]
        )
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert not errors, f"Expected no errors; got: {errors}"

    def test_AC2_2_duplicate_claim_id_within_candidate_rejected(self):
        """AC2.2 Failure: two claims with same claim_id within one candidate are rejected."""
        claim1 = self._base_claim(claim_id="c1")
        claim2 = self._base_claim(claim_id="c1")  # duplicate in same candidate
        payload = self._base_candidate_drafting_payload(
            [self._base_candidate([claim1, claim2])]
        )
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert any("duplicate claim_id" in e.message for e in errors), (
            f"Expected 'duplicate claim_id' error; got: {errors}"
        )

    def test_AC2_2_duplicate_claim_id_across_candidates_rejected(self):
        """AC2.2 Failure: same claim_id in two different candidates is rejected.

        This verifies payload-wide (not per-candidate) uniqueness scope.
        """
        claim1 = self._base_claim(claim_id="c1")
        claim2 = self._base_claim(claim_id="c1")  # duplicate in different candidate
        candidate1 = self._base_candidate([claim1])
        candidate2 = self._base_candidate([claim2])
        payload = self._base_candidate_drafting_payload([candidate1, candidate2])
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert any("duplicate claim_id" in e.message for e in errors), (
            f"Expected 'duplicate claim_id' across-candidates error; got: {errors}"
        )

    def test_AC2_2_distinct_claim_ids_accepted(self):
        """Success: claims with distinct claim_ids pass schema."""
        claim1 = self._base_claim(claim_id="c1")
        claim2 = self._base_claim(claim_id="c2")
        payload = self._base_candidate_drafting_payload(
            [self._base_candidate([claim1, claim2])]
        )
        errors = validate_units("hypothesis", "candidate_drafting", payload)
        assert not errors, f"Expected no errors; got: {errors}"

    def test_AC2_3_review_missing_item_for_claim_id_rejected(self):
        """AC2.3 Failure: review with claim_ids=[c1,c2] but review_items only covering c1 is rejected."""
        review_item_c1 = {
            "claim_id": "c1",
            "checks": {
                "thin_support": False,
                "single_iv_level": False,
                "causal_language": False,
                "rung_appropriateness": {"stub": True},
            },
            "outcome": "pass",
        }
        payload = {
            "claim_ids": ["c1", "c2"],
            "review_items": [review_item_c1],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert errors, "Expected errors for missing review item for c2"
        assert any("c2" in e.message for e in errors), (
            f"Expected error mentioning 'c2' not covered; got: {errors}"
        )

    def test_AC2_4_empty_review_items_with_nonempty_claims_rejected(self):
        """AC2.4 Failure: review_items=[] with non-empty claim_ids is rejected."""
        payload = {
            "claim_ids": ["c1"],
            "review_items": [],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert errors, "Expected error for empty review_items with non-empty claim_ids"
        assert any("empty review_items" in e.message or "review_items" in e.field for e in errors), (
            f"Expected error about empty review_items; got: {errors}"
        )

    def test_AC2_valid_full_coverage_accepted(self):
        """Success: review payload with one review item per claim_id is accepted."""
        review_item_c1 = {
            "claim_id": "c1",
            "checks": {
                "thin_support": False,
                "single_iv_level": False,
                "causal_language": False,
                "rung_appropriateness": {"stub": True},
            },
            "outcome": "pass",
        }
        review_item_c2 = {
            "claim_id": "c2",
            "checks": {
                "thin_support": True,
                "single_iv_level": False,
                "causal_language": False,
                "rung_appropriateness": {"stub": True},
            },
            "outcome": "flagged",
            "notes": "Only 2 transcripts",
        }
        payload = {
            "claim_ids": ["c1", "c2"],
            "review_items": [review_item_c1, review_item_c2],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert not errors, f"Expected no errors for full coverage; got: {errors}"

    def test_AC2_review_missing_claim_ids_field_rejected(self):
        """The weak_evidence_review payload must have a claim_ids field."""
        payload = {
            "review_items": [],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert any("claim_ids" in e.field for e in errors), (
            f"Expected error for missing claim_ids field; got: {errors}"
        )

    def test_AC2_review_missing_review_items_field_rejected(self):
        """The weak_evidence_review payload must have a review_items field."""
        payload = {
            "claim_ids": [],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert any("review_items" in e.field for e in errors), (
            f"Expected error for missing review_items field; got: {errors}"
        )

    def test_AC2_review_item_missing_claim_id_rejected(self):
        """Review item without claim_id is rejected."""
        review_item = {
            "checks": {"thin_support": False},
            "outcome": "pass",
        }
        payload = {
            "claim_ids": ["c1"],
            "review_items": [review_item],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert any("claim_id" in e.field for e in errors), (
            f"Expected error for missing claim_id in review item; got: {errors}"
        )

    def test_AC2_review_item_invalid_outcome_rejected(self):
        """Review item with invalid outcome is rejected."""
        review_item = {
            "claim_id": "c1",
            "checks": {"thin_support": False},
            "outcome": "invalid_value",
        }
        payload = {
            "claim_ids": ["c1"],
            "review_items": [review_item],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert any("outcome" in e.field for e in errors), (
            f"Expected error for invalid outcome; got: {errors}"
        )

    def test_AC2_empty_claim_ids_with_empty_review_items_accepted(self):
        """Success: empty claim_ids and empty review_items is valid (no claims to review)."""
        payload = {
            "claim_ids": [],
            "review_items": [],
        }
        errors = validate_units("hypothesis", "weak_evidence_review", payload)
        assert not errors, f"Expected no errors for empty-empty; got: {errors}"

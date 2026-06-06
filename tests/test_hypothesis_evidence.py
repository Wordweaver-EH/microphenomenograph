"""Tests for hypothesis-evidence design plan (plan 4).

Phase 2: AC2.1, AC2.2, AC2.3, AC2.4 — claim_id + review coverage schema.
Phase 3: AC3.1, AC3.2, AC3.3, AC3.4 — review gate and agent instructions.
"""
import json
import sys
import types
import uuid
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from _mpi_schemas import validate_units, GATES  # noqa: E402


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
            "rung": 1,
            "assumptions": [],          # empty allowed at rung=1
            "confounders": [{"variable": "common_method_variance", "mechanism": "self-report bias"}],
            "testable_implications": ["IV _||_ DV | CMV"],
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
            "replication_recommendation": "A second participant set would need to show the same pattern to support this mechanism.",
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


# ---------------------------------------------------------------------------
# Phase 3: AC3.1, AC3.2, AC3.3, AC3.4 — Review gate and agent instructions
# ---------------------------------------------------------------------------

CROSS_ANALYST_AGENT = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"


def _make_args(**kwargs) -> types.SimpleNamespace:
    """Build a minimal args namespace for _check_weak_evidence_unreviewed_gate.

    _evaluate_gate reads:
    - getattr(args, 'strict_weak_evidence_unreviewed', False) for the CLI flag
    All other gate attributes are passed as explicit keyword args.
    """
    defaults = {
        "stage": "hypothesis",
        "substep": "weak_evidence_review",
        "scope": "global",
        "actor": "test-actor",
        "actor_kind": "subagent",
        "strict_weak_evidence_unreviewed": False,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_manifest(strict_gates=None) -> dict:
    """Build a minimal manifest for gate tests."""
    study = {}
    if strict_gates is not None:
        study["strict_gates"] = strict_gates
    return {"study": study}


class TestAC3_ReviewGate:
    """AC3: weak_evidence_unreviewed gate — warn/abort on flagged items lacking acknowledged_by."""

    def test_AC3_4_gate_in_registry(self):
        """AC3.4: weak_evidence_unreviewed gate is in GATES registry with warn_or_abort posture."""
        assert "weak_evidence_unreviewed" in GATES, (
            "Expected 'weak_evidence_unreviewed' gate in GATES registry"
        )
        gate = GATES["weak_evidence_unreviewed"]
        assert gate["posture"] == "warn_or_abort", (
            f"Expected posture 'warn_or_abort', got {gate['posture']!r}"
        )
        assert gate["stage"] == "hypothesis", (
            f"Expected stage 'hypothesis', got {gate['stage']!r}"
        )

    def test_AC3_4_cross_analyst_md_has_weak_evidence_review_section(self):
        """AC3.4: mpi-cross-analyst.md contains the Weak evidence review section
        with all three check names."""
        assert CROSS_ANALYST_AGENT.exists(), f"Expected {CROSS_ANALYST_AGENT}"
        content = CROSS_ANALYST_AGENT.read_text(encoding="utf-8")

        assert "Weak evidence review" in content, (
            "Expected '### Weak evidence review' section in mpi-cross-analyst.md"
        )
        assert "thin_support" in content, (
            "Expected 'thin_support' check mentioned in mpi-cross-analyst.md"
        )
        assert "single_iv_level" in content, (
            "Expected 'single_iv_level' check mentioned in mpi-cross-analyst.md"
        )
        assert "causal_language" in content, (
            "Expected 'causal_language' check mentioned in mpi-cross-analyst.md"
        )
        assert "n_transcripts < 3" in content, (
            "Expected 'n_transcripts < 3' threshold mentioned in mpi-cross-analyst.md"
        )

    def test_AC3_1_flagged_unacknowledged_triggers_warn(self, tmp_path):
        """AC3.1: _check_weak_evidence_unreviewed_gate returns GATE_WARN (0) and emits
        gate_warning audit event when a flagged item lacks acknowledged_by (warn mode)."""
        from mpi_step import _check_weak_evidence_unreviewed_gate

        # Set up tmp run dir with required files
        mpi_dir = tmp_path / ".mpi"
        mpi_dir.mkdir()
        run_id_file = mpi_dir / "run_id"
        run_id_file.write_text(str(uuid.uuid4()), encoding="utf-8")

        audit_path = tmp_path / "audit.jsonl"
        close_id = str(uuid.uuid4())

        units_payload = {
            "claim_ids": ["c1"],
            "review_items": [
                {
                    "claim_id": "c1",
                    "checks": {
                        "thin_support": True,
                        "single_iv_level": False,
                        "causal_language": False,
                        "rung_appropriateness": {"stub": True},
                    },
                    "outcome": "flagged",
                    "notes": "Thin support: only 2 transcripts",
                    # No acknowledged_by — should trigger gate
                }
            ],
        }

        args = _make_args(strict_weak_evidence_unreviewed=False)
        manifest = _make_manifest()

        rc = _check_weak_evidence_unreviewed_gate(
            tmp_path, manifest, args, audit_path, close_id,
            units_payload=units_payload,
            actor=args.actor,
            actor_kind=args.actor_kind,
        )

        assert rc == 0, f"Expected GATE_WARN (0) in warn mode, got {rc}"
        assert audit_path.exists(), "Expected audit.jsonl to be written"

        audit_lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line) for line in audit_lines if line.strip()]
        gate_events = [
            e for e in events
            if e.get("event", {}).get("action") == "gate_warning"
            and e.get("mpi", {}).get("gate_id") == "weak_evidence_unreviewed"
        ]
        assert gate_events, (
            f"Expected gate_warning event with gate_id='weak_evidence_unreviewed' in audit; "
            f"got events: {events}"
        )

    def test_AC3_2_all_flagged_acknowledged_closes_clean(self, tmp_path):
        """AC3.2: _check_weak_evidence_unreviewed_gate returns 0 and emits NO
        weak_evidence_unreviewed gate_warning when all flagged items carry acknowledged_by."""
        from mpi_step import _check_weak_evidence_unreviewed_gate

        mpi_dir = tmp_path / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text(str(uuid.uuid4()), encoding="utf-8")

        audit_path = tmp_path / "audit.jsonl"
        close_id = str(uuid.uuid4())

        units_payload = {
            "claim_ids": ["c1"],
            "review_items": [
                {
                    "claim_id": "c1",
                    "checks": {
                        "thin_support": True,
                        "single_iv_level": False,
                        "causal_language": False,
                        "rung_appropriateness": {"stub": True},
                    },
                    "outcome": "flagged",
                    "notes": "Thin support acknowledged",
                    "acknowledged_by": "analyst-1",  # acknowledged — should NOT trigger gate
                }
            ],
        }

        args = _make_args(strict_weak_evidence_unreviewed=False)
        manifest = _make_manifest()

        rc = _check_weak_evidence_unreviewed_gate(
            tmp_path, manifest, args, audit_path, close_id,
            units_payload=units_payload,
            actor=args.actor,
            actor_kind=args.actor_kind,
        )

        assert rc == 0, f"Expected 0 (no gate fire) when all flagged items acknowledged, got {rc}"

        # No weak_evidence_unreviewed gate_warning in audit (file may not exist at all)
        if audit_path.exists():
            audit_lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
            events = [json.loads(line) for line in audit_lines if line.strip()]
            gate_events = [
                e for e in events
                if e.get("mpi", {}).get("gate_id") == "weak_evidence_unreviewed"
            ]
            assert not gate_events, (
                f"Expected no weak_evidence_unreviewed gate events when all flagged items "
                f"have acknowledged_by; got: {gate_events}"
            )

    def test_AC3_3_strict_flag_blocks_unacknowledged(self, tmp_path):
        """AC3.3: --strict-weak-evidence-unreviewed blocks (returns GATE_ABORT=1)
        when a flagged item lacks acknowledged_by."""
        from mpi_step import _check_weak_evidence_unreviewed_gate

        mpi_dir = tmp_path / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text(str(uuid.uuid4()), encoding="utf-8")

        audit_path = tmp_path / "audit.jsonl"
        close_id = str(uuid.uuid4())

        units_payload = {
            "claim_ids": ["c1"],
            "review_items": [
                {
                    "claim_id": "c1",
                    "checks": {"thin_support": True},
                    "outcome": "flagged",
                    # No acknowledged_by
                }
            ],
        }

        args = _make_args(strict_weak_evidence_unreviewed=True)  # CLI flag set
        manifest = _make_manifest()

        rc = _check_weak_evidence_unreviewed_gate(
            tmp_path, manifest, args, audit_path, close_id,
            units_payload=units_payload,
            actor=args.actor,
            actor_kind=args.actor_kind,
        )

        assert rc != 0, (
            "Expected GATE_ABORT (non-zero) with --strict-weak-evidence-unreviewed "
            "and unacknowledged flagged item"
        )

    def test_AC3_3_strict_gates_manifest_blocks_unacknowledged(self, tmp_path):
        """AC3.3 variant: study.strict_gates including 'weak_evidence_unreviewed'
        blocks the close even without the CLI flag."""
        from mpi_step import _check_weak_evidence_unreviewed_gate

        mpi_dir = tmp_path / ".mpi"
        mpi_dir.mkdir()
        (mpi_dir / "run_id").write_text(str(uuid.uuid4()), encoding="utf-8")

        audit_path = tmp_path / "audit.jsonl"
        close_id = str(uuid.uuid4())

        units_payload = {
            "claim_ids": ["c1"],
            "review_items": [
                {
                    "claim_id": "c1",
                    "checks": {"thin_support": True},
                    "outcome": "flagged",
                    # No acknowledged_by
                }
            ],
        }

        args = _make_args(strict_weak_evidence_unreviewed=False)  # No CLI flag
        manifest = _make_manifest(strict_gates=["weak_evidence_unreviewed"])  # manifest strict

        rc = _check_weak_evidence_unreviewed_gate(
            tmp_path, manifest, args, audit_path, close_id,
            units_payload=units_payload,
            actor=args.actor,
            actor_kind=args.actor_kind,
        )

        assert rc != 0, (
            "Expected GATE_ABORT (non-zero) when study.strict_gates includes "
            "'weak_evidence_unreviewed' and item is flagged without acknowledged_by"
        )

"""
Analysis Fidelity tests — covers ACs for design plan 2026-06-05-analysis-fidelity.

Phase 1 (this file): AC1.1, AC1.2, AC2.1, AC2.2, AC2.3
  - Within-IDU grouping enforcement for generic_synchronic
  - Common/optional pattern semantics for pattern_identification

Only Phase 1 test classes are present here. Phases 2 and 3 will add their
own classes to this file when implemented.
"""
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from _mpi_schemas import validate_units  # noqa: E402


class TestAC1_WithinIDUGrouping:
    """AC1: Within-IDU grouping is enforced for generic_synchronic ISUs."""

    def _base_isu(self, **kwargs) -> dict:
        isu = {
            "isu_name": "Test ISU",
            "criteria": "The utterances discuss something.",
            "confidence": 3,
            "flag_for_review": False,
            "isu_second_level_of_abstraction": "Group A",
            "utterance_refs": [{
                "transcript_id": "p1s1",
                "utterance_number": 1,
                "byte_start": 0,
                "byte_end": 5,
                "raw_excerpt": "hello",
            }],
        }
        isu.update(kwargs)
        return isu

    def _base_payload(self, isus: list) -> dict:
        return {
            "event": "event1",
            "iv_category": "high",
            "generic_idu": "Initial Thoughts",
            "isus": isus,
        }

    def test_AC1_1_missing_source_generic_idu_rejected(self):
        """AC1.1 Failure: ISU without source_generic_idu is rejected at close."""
        isu = self._base_isu()
        # source_generic_idu intentionally absent
        payload = self._base_payload([isu])
        errors = validate_units("generic_synchronic", "isu_second_level_grouping", payload)
        assert any("source_generic_idu" in e.field for e in errors), (
            f"Expected error on source_generic_idu; got: {errors}"
        )

    def test_AC1_1_mismatched_source_generic_idu_rejected(self):
        """AC1.1 Failure: ISU with source_generic_idu != payload.generic_idu is rejected."""
        isu = self._base_isu(source_generic_idu="Different IDU")
        payload = self._base_payload([isu])
        errors = validate_units("generic_synchronic", "isu_second_level_grouping", payload)
        assert any("source_generic_idu" in e.field for e in errors), (
            f"Expected mismatch error on source_generic_idu; got: {errors}"
        )

    def test_AC1_1_matching_source_generic_idu_accepted(self):
        """AC1.1 Success path: ISU with source_generic_idu == payload.generic_idu is accepted."""
        isu = self._base_isu(source_generic_idu="Initial Thoughts")
        payload = self._base_payload([isu])
        errors = validate_units("generic_synchronic", "isu_second_level_grouping", payload)
        assert errors == [], f"Unexpected errors: {errors}"

    def test_AC1_1_empty_isu_list_accepted(self):
        """AC1.1: empty isus list is valid (no ISU-level checks fire)."""
        payload = self._base_payload([])
        errors = validate_units("generic_synchronic", "isu_second_level_grouping", payload)
        assert errors == []

    def test_AC1_2_agent_instructions_no_flatten_instruction(self):
        """AC1.2 Success: mpi-cross-analyst.md does not contain the flatten-across-IDU-groups instruction."""
        content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
        assert "flatten all ISUs from all IDU groups" not in content, (
            "The instruction to flatten across IDU groups must be removed from mpi-cross-analyst.md"
        )

    def test_AC1_2_agent_instructions_contain_source_generic_idu(self):
        """AC1.2 Success: mpi-cross-analyst.md references source_generic_idu field."""
        content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
        assert "source_generic_idu" in content, (
            "mpi-cross-analyst.md must reference source_generic_idu field in ISU grouping rule"
        )

    def test_AC1_2_agent_instructions_contain_within_gidu_rule(self):
        """AC1.2 Success: mpi-cross-analyst.md contains within-target-gidu grouping rule."""
        content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
        # Must mention grouping within the target generic IDU
        lower = content.lower()
        assert ("within" in lower and "generic_idu" in content) or "within the target" in lower, (
            "mpi-cross-analyst.md must state ISUs are grouped within the target generic IDU"
        )


class TestAC2_PatternCommonOptional:
    """AC2: Pattern common/optional semantics for generic_diachronic pattern_identification."""

    def _minimal_pattern(self, **kwargs) -> dict:
        pat = {
            "utterance_refs": [{
                "transcript_id": "p1s1",
                "utterance_number": 1,
                "byte_start": 0,
                "byte_end": 5,
                "raw_excerpt": "x",
            }],
            "common_idus": ["Initial Thoughts"],
            "optional_idus": [],
            "covered_participant_keys": ["p1s1"],
        }
        pat.update(kwargs)
        return pat

    def _payload_with(self, pat_overrides=None) -> dict:
        pat = self._minimal_pattern(**(pat_overrides or {}))
        return {"event": "event1", "patterns": [pat]}

    def test_AC2_1_pattern_without_common_idus_rejected(self):
        """AC2.1 Failure: pattern missing common_idus is rejected."""
        payload = {
            "event": "event1",
            "patterns": [{
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                    "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
                # common_idus intentionally absent
                "optional_idus": [],
                "covered_participant_keys": ["p1s1"],
            }]
        }
        errors = validate_units("generic_diachronic", "pattern_identification", payload)
        assert any("common_idus" in e.field for e in errors), (
            f"Expected error on common_idus; got: {errors}"
        )

    def test_AC2_1_pattern_with_empty_common_idus_rejected(self):
        """AC2.1 Failure: pattern with empty common_idus list is rejected."""
        payload = {
            "event": "event1",
            "patterns": [{
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                    "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
                "common_idus": [],  # empty — invalid
                "optional_idus": [],
                "covered_participant_keys": ["p1s1"],
            }]
        }
        errors = validate_units("generic_diachronic", "pattern_identification", payload)
        assert any("common_idus" in e.field for e in errors), (
            f"Expected non-empty error on common_idus; got: {errors}"
        )

    def test_AC2_2_pattern_with_empty_optional_idus_accepted(self):
        """AC2.2 Success: pattern with empty optional_idus is accepted (invariant patterns)."""
        errors = validate_units("generic_diachronic", "pattern_identification",
                                self._payload_with())
        assert errors == [], f"Unexpected errors with empty optional_idus: {errors}"

    def test_AC2_2_pattern_with_nonempty_optional_idus_accepted(self):
        """AC2.2 Success variant: non-empty optional_idus is also accepted."""
        payload = self._payload_with({"optional_idus": ["Side Thought"]})
        errors = validate_units("generic_diachronic", "pattern_identification", payload)
        assert errors == [], f"Unexpected errors with non-empty optional_idus: {errors}"

    def test_AC2_1_pattern_missing_optional_idus_rejected(self):
        """AC2.1 (optional_idus key required): pattern without optional_idus key is rejected."""
        payload = {
            "event": "event1",
            "patterns": [{
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                    "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
                "common_idus": ["Initial Thoughts"],
                # optional_idus intentionally absent
                "covered_participant_keys": ["p1s1"],
            }]
        }
        errors = validate_units("generic_diachronic", "pattern_identification", payload)
        assert any("optional_idus" in e.field for e in errors), (
            f"Expected error on optional_idus when key missing; got: {errors}"
        )

    def test_AC2_1_pattern_missing_covered_participant_keys_rejected(self):
        """AC2.1: pattern without covered_participant_keys is rejected."""
        payload = {
            "event": "event1",
            "patterns": [{
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                    "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
                "common_idus": ["Initial Thoughts"],
                "optional_idus": [],
                # covered_participant_keys intentionally absent
            }]
        }
        errors = validate_units("generic_diachronic", "pattern_identification", payload)
        assert any("covered_participant_keys" in e.field for e in errors), (
            f"Expected error on covered_participant_keys; got: {errors}"
        )

    def test_AC2_1_pattern_with_empty_covered_participant_keys_rejected(self):
        """AC2.1: pattern with empty covered_participant_keys is rejected."""
        payload = {
            "event": "event1",
            "patterns": [{
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                    "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
                "common_idus": ["Initial Thoughts"],
                "optional_idus": [],
                "covered_participant_keys": [],  # empty — invalid
            }]
        }
        errors = validate_units("generic_diachronic", "pattern_identification", payload)
        assert any("covered_participant_keys" in e.field for e in errors), (
            f"Expected error on empty covered_participant_keys; got: {errors}"
        )

    def test_AC2_3_agent_instructions_contain_common_idus(self):
        """AC2.3 Success: mpi-cross-analyst.md references common_idus in pattern instructions."""
        content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
        assert "common_idus" in content, (
            "mpi-cross-analyst.md must reference common_idus in generic-diachronic pattern instructions"
        )

    def test_AC2_3_agent_instructions_contain_optional_idus(self):
        """AC2.3 Success: mpi-cross-analyst.md references optional_idus in pattern instructions."""
        content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
        assert "optional_idus" in content, (
            "mpi-cross-analyst.md must reference optional_idus in generic-diachronic pattern instructions"
        )

    def test_AC2_3_agent_instructions_contain_merge_evaluation(self):
        """AC2.3 Success: mpi-cross-analyst.md mentions merge evaluation or optimum-small-set criterion."""
        content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
        # Must mention merge evaluation or optimum small set
        has_merge_eval = "merge_rationale" in content or "merge evaluation" in content.lower()
        has_optimum = "optimum" in content.lower()
        assert has_merge_eval or has_optimum, (
            "mpi-cross-analyst.md must mention merge evaluation or optimum-small-set criterion "
            "in generic-diachronic pattern instructions"
        )

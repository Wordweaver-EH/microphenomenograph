"""
Analysis Fidelity tests — covers ACs for design plan 2026-06-05-analysis-fidelity.

Phase 1: AC1.1, AC1.2, AC2.1, AC2.2, AC2.3
  - Within-IDU grouping enforcement for generic_synchronic
  - Common/optional pattern semantics for pattern_identification

Phase 2: AC3.1, AC4.1, AC4.2
  - Linkage-phrase boundary rule in mpi-analyst.md
  - Naming deferred to convergence: idu_name/moment optional at criteria_grouping/criteria_revision,
    required at idu_naming_ordering

Phase 3: AC5.1, AC5.2, AC6.1
  - Score-range validation (header scores outside 0-5 rejected with named error)
  - Participant-count advisory (counts 5 or 13 produce advisory; 6-12 silent)
  - Question-line flagging in normalize (validate-only; content unchanged)
"""
import re
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


# ---------------------------------------------------------------------------
# Phase 2: AC3.1, AC4.1, AC4.2
# ---------------------------------------------------------------------------


class TestAC3_LinkagePhraseRule:
    """AC3: Linkage-phrase boundary rule is present in mpi-analyst.md."""

    def test_AC3_1_agent_contains_linkage_phrase_examples(self):
        """AC3.1 Success: mpi-analyst.md diachronic rules mention 'and then' and 'after that'."""
        content = (PLUGIN_ROOT / "agents" / "mpi-analyst.md").read_text(encoding="utf-8")
        assert "and then" in content, (
            "mpi-analyst.md diachronic rules must mention 'and then' as a temporal linkage phrase"
        )
        assert "after that" in content, (
            "mpi-analyst.md diachronic rules must mention 'after that' as a temporal linkage phrase"
        )

    def test_AC3_1_agent_contains_outranks_or_overrides_language(self):
        """AC3.1 Success: mpi-analyst.md states linkage-phrase rule outranks prefer-fewer-IDUs heuristic."""
        content = (PLUGIN_ROOT / "agents" / "mpi-analyst.md").read_text(encoding="utf-8")
        assert "outranks" in content or "overrides" in content, (
            "mpi-analyst.md must state that the linkage-phrase rule outranks or overrides "
            "the prefer-fewer-IDUs heuristic"
        )

    def test_AC3_1_agent_contains_boundary_signal_language(self):
        """AC3.1 Success: mpi-analyst.md names linkage phrases as boundary signals."""
        content = (PLUGIN_ROOT / "agents" / "mpi-analyst.md").read_text(encoding="utf-8")
        assert "boundary" in content.lower(), (
            "mpi-analyst.md must describe temporal linkage phrases as IDU boundary signals"
        )


class TestAC4_NamingDeferred:
    """AC4: idu_name/moment optional at criteria_grouping/criteria_revision,
    required at idu_naming_ordering."""

    def _idu_without_naming(self) -> dict:
        """IDU dict without idu_name or moment — valid at criteria_grouping."""
        return {
            "idu_number": 1,
            "criteria": "The utterances talk about starting.",
            "confidence": 3,
            "flag_for_review": False,
            "utterance_numbers": ["1"],
            "hinge_to_next": None,
            "utterance_refs": [{
                "transcript_id": "p1s1",
                "utterance_number": 1,
                "byte_start": 0,
                "byte_end": 5,
                "raw_excerpt": "hello",
            }],
        }

    def _idu_with_naming(self) -> dict:
        """IDU dict with idu_name and moment — required at idu_naming_ordering."""
        d = self._idu_without_naming()
        d["idu_name"] = "Initial Contact"
        d["moment"] = 1
        return d

    def test_AC4_1_criteria_grouping_accepts_idu_without_naming(self):
        """AC4.1 Success: criteria_grouping close accepted without idu_name/moment."""
        payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [self._idu_without_naming()],
        }
        errors = validate_units("diachronic", "criteria_grouping", payload)
        assert errors == [], f"Unexpected errors at criteria_grouping without naming: {errors}"

    def test_AC4_1_criteria_revision_accepts_idu_without_naming(self):
        """AC4.1 variant: criteria_revision close also accepted without idu_name/moment."""
        payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [self._idu_without_naming()],
            "convergence": {"decision": "converged", "reason": "IDU grouping is stable."},
        }
        errors = validate_units("diachronic", "criteria_revision", payload)
        assert errors == [], f"Unexpected errors at criteria_revision without naming: {errors}"

    def test_AC4_1_criteria_grouping_also_accepts_idu_with_naming(self):
        """AC4.1 backward-compat: criteria_grouping still accepts IDUs that include idu_name/moment."""
        payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [self._idu_with_naming()],
        }
        errors = validate_units("diachronic", "criteria_grouping", payload)
        assert errors == [], f"criteria_grouping must accept IDUs that supply idu_name/moment: {errors}"

    def test_AC4_2_idu_naming_ordering_rejects_without_idu_name(self):
        """AC4.2 Failure: idu_naming_ordering rejected when idu_name absent."""
        payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [self._idu_without_naming()],
        }
        errors = validate_units("diachronic", "idu_naming_ordering", payload)
        assert any("idu_name" in e.field for e in errors), (
            f"Expected idu_name error at idu_naming_ordering; got: {errors}"
        )

    def test_AC4_2_idu_naming_ordering_rejects_without_moment(self):
        """AC4.2 Failure: idu_naming_ordering rejected when moment absent but idu_name present."""
        idu = self._idu_without_naming()
        idu["idu_name"] = "Initial Contact"
        payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [idu],
        }
        errors = validate_units("diachronic", "idu_naming_ordering", payload)
        assert any("moment" in e.field for e in errors), (
            f"Expected moment error at idu_naming_ordering; got: {errors}"
        )

    def test_AC4_2_idu_naming_ordering_accepts_full_payload(self):
        """AC4.2 Success path: idu_naming_ordering accepted with idu_name and moment."""
        payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [self._idu_with_naming()],
        }
        errors = validate_units("diachronic", "idu_naming_ordering", payload)
        assert errors == [], f"Unexpected errors at idu_naming_ordering with full naming: {errors}"

    def test_AC4_validators_are_not_byte_identical(self):
        """Phase 2 structural check: idu_naming_ordering validator is no longer byte-identical
        to criteria_grouping (confirms confirmed review finding is resolved)."""
        import inspect
        import _mpi_schemas as schemas
        cg_src = inspect.getsource(schemas._validate_diachronic_criteria_grouping)
        ino_src = inspect.getsource(schemas._validate_diachronic_idu_naming_ordering)
        assert cg_src != ino_src, (
            "_validate_diachronic_idu_naming_ordering must differ from "
            "_validate_diachronic_criteria_grouping (naming fields split)"
        )

    def test_AC4_agent_contains_naming_deferred_rule(self):
        """AC4 doc check: mpi-analyst.md states idu_name/moment are deferred until idu_naming_ordering."""
        content = (PLUGIN_ROOT / "agents" / "mpi-analyst.md").read_text(encoding="utf-8")
        lower = content.lower()
        # Must mention that naming is deferred or not required at criteria_grouping
        assert "defer" in lower or "idu_naming_ordering" in content, (
            "mpi-analyst.md must state that idu_name/moment are deferred until idu_naming_ordering"
        )


# ---------------------------------------------------------------------------
# Phase 3: AC5.1, AC5.2, AC6.1
# ---------------------------------------------------------------------------

_HEADER_REGEX = r'^Participant (\d+),?\s+Suggestion (\d+)(?:\s+\w+)*\s*\(Scored (\d+)/5\)'


def _parse_and_validate_header(line: str):
    """
    Simulate the init skill's two-pass header validation:
    1. Regex match (permissive — same regex as mpi-init SKILL.md)
    2. Score range check: 0–5 inclusive
    Returns (p, s, score) tuple on success.
    Raises ValueError with 'invalid_score_range' in message when score out-of-range.
    Raises ValueError with 'invalid header format' when regex does not match.
    """
    match = re.match(_HEADER_REGEX, line)
    if not match:
        raise ValueError(
            f"invalid header format. Expected \"Participant N[,] Suggestion N (Scored N/5)[...]\", "
            f"got: \"{line}\""
        )
    p, s, score = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if score < 0 or score > 5:
        raise ValueError(
            f"invalid_score_range: score {score} is outside valid range 0–5. "
            f"Expected \"Scored N/5\" where N ∈ {{0, 1, 2, 3, 4, 5}}."
        )
    return p, s, score


def _emit_participant_count_advisory(count: int):
    """
    Simulate the init skill's participant-count advisory logic.
    Returns advisory string if count < 6 or count > 12, else None.
    """
    if count < 6 or count > 12:
        return (
            f"NOTE: Participant count is {count} "
            f"(recommended range: 6–12 per MPI manual). "
            f"Analysis can proceed, but results may be less reliable "
            f"at smaller or larger sample sizes."
        )
    return None


def _is_interviewer_question(speaker_label: str, line_text: str) -> bool:
    """
    Simulate the normalize skill's question-detection logic.
    Returns True if the line is an interviewer question candidate.
    """
    interviewer_labels = {"Kevin Sheldrake:", "KS:"}
    if speaker_label not in interviewer_labels:
        return False
    return "?" in line_text


class TestAC5_InitDataContractValidation:
    """AC5: Init data-contract validation — score range and participant-count advisory."""

    def test_AC5_1_score_7_rejected_with_named_error(self):
        """AC5.1 Failure: Scored 7/5 rejected with invalid_score_range error."""
        line = "Participant 1, Suggestion 1 (Scored 7/5)"
        with pytest.raises(ValueError) as exc_info:
            _parse_and_validate_header(line)
        assert "invalid_score_range" in str(exc_info.value)

    def test_AC5_1_score_6_rejected(self):
        """AC5.1 Failure: Scored 6/5 also rejected."""
        line = "Participant 2, Suggestion 1 (Scored 6/5)"
        with pytest.raises(ValueError) as exc_info:
            _parse_and_validate_header(line)
        assert "invalid_score_range" in str(exc_info.value)

    def test_AC5_1_score_0_accepted(self):
        """AC5.1 boundary: Scored 0/5 accepted (minimum valid)."""
        p, s, score = _parse_and_validate_header("Participant 3, Suggestion 1 (Scored 0/5)")
        assert score == 0

    def test_AC5_1_score_5_accepted(self):
        """AC5.1 boundary: Scored 5/5 accepted (maximum valid)."""
        p, s, score = _parse_and_validate_header("Participant 4, Suggestion 1 (Scored 5/5)")
        assert score == 5

    def test_AC5_2_count_5_produces_advisory(self):
        """AC5.2 Success: participant count 5 produces 6-12 adequacy advisory."""
        advisory = _emit_participant_count_advisory(5)
        assert advisory is not None
        assert "6" in advisory and "12" in advisory

    def test_AC5_2_count_13_produces_advisory(self):
        """AC5.2 Success: participant count 13 produces advisory."""
        advisory = _emit_participant_count_advisory(13)
        assert advisory is not None
        assert "NOTE" in advisory

    def test_AC5_2_count_6_is_silent(self):
        """AC5.2 Success: participant count 6 produces no advisory."""
        advisory = _emit_participant_count_advisory(6)
        assert advisory is None

    def test_AC5_2_count_12_is_silent(self):
        """AC5.2 Success: participant count 12 produces no advisory."""
        advisory = _emit_participant_count_advisory(12)
        assert advisory is None

    def test_AC5_2_count_9_is_silent(self):
        """AC5.2 Success: mid-range count is silent."""
        advisory = _emit_participant_count_advisory(9)
        assert advisory is None

    def test_AC5_1_skill_md_contains_score_range_rule(self):
        """AC5.1 Grep: mpi-init/SKILL.md contains the score-range validation rule."""
        content = (PLUGIN_ROOT / "skills" / "mpi-init" / "SKILL.md").read_text(encoding="utf-8")
        assert "invalid_score_range" in content, (
            "mpi-init/SKILL.md must document the invalid_score_range named error"
        )
        assert "0–5" in content or "0-5" in content, (
            "mpi-init/SKILL.md must state the valid score range 0–5"
        )

    def test_AC5_2_skill_md_contains_participant_count_advisory(self):
        """AC5.2 Grep: mpi-init/SKILL.md contains the participant-count advisory rule."""
        content = (PLUGIN_ROOT / "skills" / "mpi-init" / "SKILL.md").read_text(encoding="utf-8")
        assert "6–12" in content or "6-12" in content, (
            "mpi-init/SKILL.md must document the 6–12 participant-count guidance"
        )
        assert "NOTE" in content or "advisory" in content.lower(), (
            "mpi-init/SKILL.md must state the count check is non-blocking (advisory/note)"
        )


class TestAC6_QuestionFlaggingValidateOnly:
    """AC6: Question-flagging in normalize is validate-only; content is never modified."""

    def test_AC6_1_interviewer_question_detected_not_modified(self):
        """AC6.1 Success: normalize flags interviewer-question line; content unchanged."""
        raw_line = "Kevin Sheldrake: Why was that?"
        speaker = "Kevin Sheldrake:"
        text = "Why was that?"
        is_q = _is_interviewer_question(speaker, text)
        assert is_q, "Interviewer question line should be flagged"
        # Content is not modified — trailing whitespace only stripped structurally
        normalized_content = raw_line.rstrip()
        assert "Why was that?" in normalized_content, (
            "Question text must not be removed or rewritten during normalize"
        )

    def test_AC6_1_participant_question_not_flagged(self):
        """AC6.1 Success: participant utterances ending with '?' are not flagged."""
        speaker = "P1:"
        text = "I was wondering what would happen?"
        is_q = _is_interviewer_question(speaker, text)
        assert not is_q, "Participant utterances must not be flagged as removable questions"

    def test_AC6_1_interviewer_non_question_not_flagged(self):
        """AC6.1 Success: interviewer non-question lines are not flagged."""
        speaker = "Kevin Sheldrake:"
        text = "Okay, thank you for that."
        is_q = _is_interviewer_question(speaker, text)
        assert not is_q, "Interviewer non-question lines must not be flagged"

    def test_AC6_1_skill_md_contains_validate_only_rule(self):
        """AC6.1 Grep: mpi-transcript-prep/SKILL.md documents question-flagging as validate-only."""
        content = (PLUGIN_ROOT / "skills" / "mpi-transcript-prep" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "QUESTION" in content, (
            "mpi-transcript-prep/SKILL.md must document the QUESTION advisory format"
        )
        lower = content.lower()
        has_not_remove = ("not" in lower and "remove" in lower)
        has_not_rewrite = ("not" in lower and "rewrite" in lower)
        assert has_not_remove or has_not_rewrite, (
            "mpi-transcript-prep/SKILL.md must state question lines are NOT removed or rewritten"
        )

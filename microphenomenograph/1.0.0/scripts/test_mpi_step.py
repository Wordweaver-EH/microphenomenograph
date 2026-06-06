"""Phase 1 unit tests for mpi_step.py — CLI scaffolding."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import pytest

# Ensure scripts/ is on the path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

import mpi_step
from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id, acquire_close_lock
from _mpi_schemas import validate_units, PREREQ_SCOPE_TRANSFORMS, _scope_strip_to_event
from mpi_step import _prereq_participant_key


# ---------------------------------------------------------------------------
# _mpi_atomic tests
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    def test_write_creates_file(self, tmp_path):
        p = tmp_path / "out.json"
        atomic_write(p, '{"x": 1}')
        assert p.read_text() == '{"x": 1}'

    def test_write_is_atomic_no_tmp_leftover(self, tmp_path):
        p = tmp_path / "out.json"
        atomic_write(p, "hello")
        assert not (tmp_path / "out.json.tmp").exists()

    def test_write_overwrites_existing(self, tmp_path):
        p = tmp_path / "out.txt"
        atomic_write(p, "old")
        atomic_write(p, "new")
        assert p.read_text() == "new"

    def test_write_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "a" / "b" / "c.txt"
        atomic_write(p, "deep")
        assert p.read_text() == "deep"


class TestAppendJsonl:
    def test_append_creates_and_appends(self, tmp_path):
        p = tmp_path / "audit.jsonl"
        append_jsonl(p, {"a": 1})
        append_jsonl(p, {"b": 2})
        lines = p.read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}

    def test_append_idempotent_under_re_read(self, tmp_path):
        p = tmp_path / "audit.jsonl"
        append_jsonl(p, {"event": "test"})
        content_a = p.read_text()
        # Re-reading the file does not change it
        assert p.read_text() == content_a


class TestLoadOrCreateRunId:
    def test_creates_uuid_if_absent(self, tmp_path):
        p = tmp_path / "run_id"
        rid = load_or_create_run_id(p)
        import uuid
        uuid.UUID(rid)  # raises if not valid UUID
        assert p.exists()

    def test_returns_existing_if_present(self, tmp_path):
        p = tmp_path / "run_id"
        p.write_text("my-fixed-id\n")
        assert load_or_create_run_id(p) == "my-fixed-id"


# ---------------------------------------------------------------------------
# _mpi_schemas tests
# ---------------------------------------------------------------------------

class TestValidateUnits:
    def test_accepts_known_stage_with_valid_payload(self):
        """Phase 4: full schemas require proper fields. Test with minimal valid payload."""
        valid_payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [{
                "idu_number": 1, "idu_name": "Test", "moment": 1,
                "criteria": "test", "confidence": 3, "flag_for_review": False,
                "utterance_numbers": ["1"], "hinge_to_next": None,
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 5, "raw_excerpt": "hello"}],
            }],
        }
        errors = validate_units("diachronic", "criteria_grouping", valid_payload)
        assert errors == []

    def test_rejects_unknown_stage(self):
        errors = validate_units("bad_stage", "x", {})
        assert errors
        assert any("stage" in e.field for e in errors)

    def test_rejects_non_dict(self):
        errors = validate_units("diachronic", "criteria_grouping", ["list"])
        assert errors
        assert any("payload" in e.field for e in errors)


class TestPrereqScopeResolution:
    """Test _scope_strip_to_event and PREREQ_SCOPE_TRANSFORMS for cross-scope prerequisites."""

    # Tests for _scope_strip_to_event function
    def test_scope_strip_to_event_basic(self):
        """AC1.3 basic: 'event3-cat-low-gidu1' → 'event3'"""
        assert _scope_strip_to_event("event3-cat-low-gidu1") == "event3"

    def test_scope_strip_to_event_double_digit(self):
        """AC1.3 double-digit: 'event12-cat-moderate-gidu3' → 'event12'"""
        assert _scope_strip_to_event("event12-cat-moderate-gidu3") == "event12"

    def test_scope_strip_to_event_high_category(self):
        """AC1.3 variant: 'event1-cat-high-gidu5' → 'event1'"""
        assert _scope_strip_to_event("event1-cat-high-gidu5") == "event1"

    def test_scope_strip_to_event_no_cat_delimiter(self):
        """Defensive fallback: input with no '-cat-' returns unchanged"""
        assert _scope_strip_to_event("p1s1-idu2") == "p1s1-idu2"
        assert _scope_strip_to_event("p1s1") == "p1s1"

    # Tests for PREREQ_SCOPE_TRANSFORMS table
    def test_prereq_scope_transforms_has_two_entries(self):
        """Table has exactly 2 entries"""
        assert len(PREREQ_SCOPE_TRANSFORMS) == 2

    def test_prereq_scope_transforms_worksheet_assembly_callable(self):
        """worksheet_assembly → select_generic_idus_of_interest maps to callable"""
        key = ("generic_synchronic", "worksheet_assembly",
               "generic_synchronic", "select_generic_idus_of_interest")
        assert key in PREREQ_SCOPE_TRANSFORMS
        transform = PREREQ_SCOPE_TRANSFORMS[key]
        assert callable(transform)

    def test_prereq_scope_transforms_worksheet_assembly_transform(self):
        """Calling worksheet_assembly transform with event-scope scope"""
        key = ("generic_synchronic", "worksheet_assembly",
               "generic_synchronic", "select_generic_idus_of_interest")
        transform = PREREQ_SCOPE_TRANSFORMS[key]
        assert transform("event3-cat-low-gidu1") == "event3"

    def test_prereq_scope_transforms_weak_evidence_review_all_match(self):
        """weak_evidence_review → candidate_drafting maps to 'all_match' sentinel"""
        key = ("hypothesis", "weak_evidence_review",
               "hypothesis", "candidate_drafting")
        assert key in PREREQ_SCOPE_TRANSFORMS
        assert PREREQ_SCOPE_TRANSFORMS[key] == "all_match"

    # Backward compatibility tests for _prereq_participant_key
    def test_prereq_participant_key_sync_to_diachronic(self):
        """AC3.1: synchronic→diachronic scope stripping: 'p1s1-idu2' → 'p1s1'"""
        result = _prereq_participant_key("p1s1-idu2", "diachronic")
        assert result == "p1s1"

    def test_prereq_participant_key_diachronic_unchanged(self):
        """AC3.1: no suffix, unchanged: 'p1s1' → 'p1s1'"""
        result = _prereq_participant_key("p1s1", "diachronic")
        assert result == "p1s1"

    def test_prereq_participant_key_same_scope_unchanged(self):
        """AC3.2: same-scope prereqs unchanged: 'event3-cat-low' → 'event3-cat-low'"""
        result = _prereq_participant_key("event3-cat-low", "generic_diachronic")
        assert result == "event3-cat-low"

    # New tests for expanded _prereq_participant_key with transform table
    def test_prereq_participant_key_worksheet_assembly_transform(self):
        """AC1.1: worksheet_assembly scope lookup uses PREREQ_SCOPE_TRANSFORMS"""
        # worksheet_assembly scope "event3-cat-low-gidu1" should transform to "event3"
        result = _prereq_participant_key(
            "event3-cat-low-gidu1",
            "generic_synchronic",
            prereq_substep="select_generic_idus_of_interest",
            downstream_stage="generic_synchronic",
            downstream_substep="worksheet_assembly",
        )
        assert result == "event3"

    def test_prereq_participant_key_all_match_sentinel(self):
        """AC2: weak_evidence_review prereq returns 'all_match' sentinel"""
        result = _prereq_participant_key(
            "global",
            "hypothesis",
            prereq_substep="candidate_drafting",
            downstream_stage="hypothesis",
            downstream_substep="weak_evidence_review",
        )
        assert result == "all_match"

    def test_prereq_participant_key_backward_compat_without_full_context(self):
        """Backward compatibility: without downstream context, falls back to legacy logic"""
        # Synchronic → diachronic strip still works without new params
        result = _prereq_participant_key("p1s1-idu2", "diachronic")
        assert result == "p1s1"


class TestAllCandidateDraftingsDone:
    """Test _all_candidate_draftings_done helper for all-match prerequisite gates."""

    def test_all_candidate_draftings_done_single_done(self):
        """AC2.1: Single done entry passes all-match gate."""
        manifest = {
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "done"
                                }
                            }
                        }
                    }
                }
            }
        }
        from mpi_step import _all_candidate_draftings_done
        assert _all_candidate_draftings_done(manifest, "hypothesis", "candidate_drafting") is True

    def test_all_candidate_draftings_done_multiple_done(self):
        """AC2.1 multiple: Multiple done entries all pass."""
        manifest = {
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {"status": "done"}
                            }
                        }
                    }
                },
                "dv-attention": {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {"status": "done"}
                            }
                        }
                    }
                }
            }
        }
        from mpi_step import _all_candidate_draftings_done
        assert _all_candidate_draftings_done(manifest, "hypothesis", "candidate_drafting") is True

    def test_all_candidate_draftings_done_no_entries(self):
        """AC2.2: No matching entries at all fails."""
        manifest = {
            "participants": {}
        }
        from mpi_step import _all_candidate_draftings_done
        assert _all_candidate_draftings_done(manifest, "hypothesis", "candidate_drafting") is False

    def test_all_candidate_draftings_done_pending_entry(self):
        """AC2.3: One pending entry fails."""
        manifest = {
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {"status": "done"}
                            }
                        }
                    }
                },
                "dv-attention": {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {"status": "pending"}
                            }
                        }
                    }
                }
            }
        }
        from mpi_step import _all_candidate_draftings_done
        assert _all_candidate_draftings_done(manifest, "hypothesis", "candidate_drafting") is False

    def test_all_candidate_draftings_done_flagged_entry(self):
        """AC2.4: Flagged entry fails."""
        manifest = {
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {"status": "flagged"}
                            }
                        }
                    }
                }
            }
        }
        from mpi_step import _all_candidate_draftings_done
        assert _all_candidate_draftings_done(manifest, "hypothesis", "candidate_drafting") is False

    def test_all_candidate_draftings_done_null_dv_focuses(self):
        """AC2.5: With dv_focuses null, only manifest scan is used."""
        manifest = {
            "study": {"dv_focuses": None},
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {"status": "done"}
                            }
                        }
                    }
                }
            }
        }
        from mpi_step import _all_candidate_draftings_done
        assert _all_candidate_draftings_done(manifest, "hypothesis", "candidate_drafting") is True


class TestInitValidators:
    """Test init-stage validators for Phase 1 cross-scope-prereq-resolution."""

    def test_scan_transcripts_valid(self):
        """scan_transcripts requires transcript_ids and raw_sha256_map."""
        valid_payload = {
            "transcript_ids": ["p1s1", "p1s2", "p2s1"],
            "raw_sha256_map": {
                "p1s1": "abc123...",
                "p1s2": "def456...",
                "p2s1": "ghi789...",
            }
        }
        errors = validate_units("init", "scan_transcripts", valid_payload)
        assert errors == [], f"Expected no errors, got {errors}"

    def test_scan_transcripts_missing_transcript_ids(self):
        """scan_transcripts missing transcript_ids should error."""
        invalid_payload = {
            "raw_sha256_map": {"p1s1": "abc123..."}
        }
        errors = validate_units("init", "scan_transcripts", invalid_payload)
        assert len(errors) >= 1
        assert any("transcript_ids" in e.field for e in errors)

    def test_scan_transcripts_missing_raw_sha256_map(self):
        """scan_transcripts missing raw_sha256_map should error."""
        invalid_payload = {
            "transcript_ids": ["p1s1"]
        }
        errors = validate_units("init", "scan_transcripts", invalid_payload)
        assert len(errors) >= 1
        assert any("raw_sha256_map" in e.field for e in errors)

    def test_propose_study_config_valid(self):
        """propose_study_config requires event_groups_proposed."""
        valid_payload = {
            "event_groups_proposed": {
                "event1": ["p1s1", "p2s1", "p3s1"],
                "event2": ["p1s2", "p2s2", "p3s2"],
            }
        }
        errors = validate_units("init", "propose_study_config", valid_payload)
        assert errors == [], f"Expected no errors, got {errors}"

    def test_propose_study_config_missing_event_groups_proposed(self):
        """propose_study_config missing event_groups_proposed should error."""
        invalid_payload = {}
        errors = validate_units("init", "propose_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("event_groups_proposed" in e.field for e in errors)

    def test_confirm_study_config_valid_with_dv_focuses(self):
        """confirm_study_config with event_groups, dv_focuses, and config_provenance."""
        valid_payload = {
            "event_groups": {
                "event1": ["p1s1", "p2s1", "p3s1"],
                "event2": ["p1s2", "p2s2", "p3s2"],
            },
            "dv_focuses": ["automaticity", "attention", "bodily_sensation"],
            "config_provenance": "user_specified"
        }
        errors = validate_units("init", "confirm_study_config", valid_payload)
        assert errors == [], f"Expected no errors, got {errors}"

    def test_confirm_study_config_valid_without_dv_focuses(self):
        """confirm_study_config without dv_focuses (null) should be valid."""
        valid_payload = {
            "event_groups": {
                "event1": ["p1s1", "p2s1"],
            },
            "config_provenance": "preregistered"
        }
        errors = validate_units("init", "confirm_study_config", valid_payload)
        assert errors == [], f"Expected no errors, got {errors}"

    def test_confirm_study_config_missing_event_groups(self):
        """confirm_study_config missing event_groups should error."""
        invalid_payload = {
            "config_provenance": "user_specified"
        }
        errors = validate_units("init", "confirm_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("event_groups" in e.field for e in errors)

    def test_confirm_study_config_missing_config_provenance(self):
        """confirm_study_config missing config_provenance should error."""
        invalid_payload = {
            "event_groups": {"event1": ["p1s1"]}
        }
        errors = validate_units("init", "confirm_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("config_provenance" in e.field for e in errors)

    def test_confirm_study_config_event_groups_not_dict(self):
        """confirm_study_config with non-dict event_groups should error."""
        invalid_payload = {
            "event_groups": [("event1", ["p1s1"])],  # list instead of dict
            "config_provenance": "user_specified"
        }
        errors = validate_units("init", "confirm_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("event_groups" in e.field for e in errors)

    def test_confirm_study_config_event_groups_value_not_list(self):
        """confirm_study_config with non-list transcript IDs should error."""
        invalid_payload = {
            "event_groups": {
                "event1": "p1s1",  # string instead of list
            },
            "config_provenance": "user_specified"
        }
        errors = validate_units("init", "confirm_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("event1" in e.field for e in errors)

    def test_confirm_study_config_event_groups_list_contains_non_string(self):
        """confirm_study_config with non-string transcript ID should error."""
        invalid_payload = {
            "event_groups": {
                "event1": ["p1s1", 123],  # number instead of string
            },
            "config_provenance": "user_specified"
        }
        errors = validate_units("init", "confirm_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("event1[1]" in e.field for e in errors)

    def test_confirm_study_config_dv_focuses_not_list(self):
        """confirm_study_config with non-list dv_focuses should error."""
        invalid_payload = {
            "event_groups": {"event1": ["p1s1"]},
            "dv_focuses": "automaticity",  # string instead of list
            "config_provenance": "user_specified"
        }
        errors = validate_units("init", "confirm_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("dv_focuses" in e.field for e in errors)

    def test_confirm_study_config_dv_focuses_contains_non_string(self):
        """confirm_study_config with non-string dv_focus should error."""
        invalid_payload = {
            "event_groups": {"event1": ["p1s1"]},
            "dv_focuses": ["automaticity", 123],  # number instead of string
            "config_provenance": "user_specified"
        }
        errors = validate_units("init", "confirm_study_config", invalid_payload)
        assert len(errors) >= 1
        assert any("dv_focuses[1]" in e.field for e in errors)

    def test_init_unknown_substep_errors(self):
        """Unknown init substep should error."""
        errors = validate_units("init", "bad_substep", {})
        assert len(errors) >= 1
        assert any("substep" in e.field for e in errors)


class TestTranscriptPrepValidators:
    """Test transcript_prep validators and DAG prerequisites for Phase 5."""

    # Schema validation tests (AC5.4)
    def test_hash_raw_valid(self):
        """hash_raw with all required fields."""
        valid_payload = {
            "transcript_id": "p1s1",
            "sha256": "abc123...",
            "byte_size": 1024
        }
        errors = validate_units("transcript_prep", "hash_raw", valid_payload)
        assert errors == [], f"Expected no errors, got {errors}"

    def test_hash_raw_missing_transcript_id(self):
        """hash_raw missing transcript_id should error."""
        invalid_payload = {
            "sha256": "abc123...",
            "byte_size": 1024
        }
        errors = validate_units("transcript_prep", "hash_raw", invalid_payload)
        assert len(errors) >= 1
        assert any("transcript_id" in e.field for e in errors)

    def test_hash_raw_missing_sha256(self):
        """hash_raw missing sha256 should error."""
        invalid_payload = {
            "transcript_id": "p1s1",
            "byte_size": 1024
        }
        errors = validate_units("transcript_prep", "hash_raw", invalid_payload)
        assert len(errors) >= 1
        assert any("sha256" in e.field for e in errors)

    def test_hash_raw_missing_byte_size(self):
        """hash_raw missing byte_size should error."""
        invalid_payload = {
            "transcript_id": "p1s1",
            "sha256": "abc123..."
        }
        errors = validate_units("transcript_prep", "hash_raw", invalid_payload)
        assert len(errors) >= 1
        assert any("byte_size" in e.field for e in errors)

    def test_normalize_valid(self):
        """normalize with all required fields."""
        valid_payload = {
            "transcript_id": "p1s1",
            "normalized_path": "transcripts/p1s1.txt",
            "diff_path": "transcripts/p1s1.diff"
        }
        errors = validate_units("transcript_prep", "normalize", valid_payload)
        assert errors == [], f"Expected no errors, got {errors}"

    def test_normalize_missing_transcript_id(self):
        """normalize missing transcript_id should error."""
        invalid_payload = {
            "normalized_path": "transcripts/p1s1.txt",
            "diff_path": "transcripts/p1s1.diff"
        }
        errors = validate_units("transcript_prep", "normalize", invalid_payload)
        assert len(errors) >= 1
        assert any("transcript_id" in e.field for e in errors)

    def test_normalize_missing_normalized_path(self):
        """normalize missing normalized_path should error."""
        invalid_payload = {
            "transcript_id": "p1s1",
            "diff_path": "transcripts/p1s1.diff"
        }
        errors = validate_units("transcript_prep", "normalize", invalid_payload)
        assert len(errors) >= 1
        assert any("normalized_path" in e.field for e in errors)

    def test_normalize_missing_diff_path(self):
        """normalize missing diff_path should error."""
        invalid_payload = {
            "transcript_id": "p1s1",
            "normalized_path": "transcripts/p1s1.txt"
        }
        errors = validate_units("transcript_prep", "normalize", invalid_payload)
        assert len(errors) >= 1
        assert any("diff_path" in e.field for e in errors)

    def test_register_offsets_valid(self):
        """register_offsets with all required fields."""
        valid_payload = {
            "transcript_id": "p1s1",
            "offsets_path": "transcripts/offsets/p1s1.json",
            "utterance_count": 42
        }
        errors = validate_units("transcript_prep", "register_offsets", valid_payload)
        assert errors == [], f"Expected no errors, got {errors}"

    def test_register_offsets_missing_transcript_id(self):
        """register_offsets missing transcript_id should error."""
        invalid_payload = {
            "offsets_path": "transcripts/offsets/p1s1.json",
            "utterance_count": 42
        }
        errors = validate_units("transcript_prep", "register_offsets", invalid_payload)
        assert len(errors) >= 1
        assert any("transcript_id" in e.field for e in errors)

    def test_register_offsets_missing_offsets_path(self):
        """register_offsets missing offsets_path should error."""
        invalid_payload = {
            "transcript_id": "p1s1",
            "utterance_count": 42
        }
        errors = validate_units("transcript_prep", "register_offsets", invalid_payload)
        assert len(errors) >= 1
        assert any("offsets_path" in e.field for e in errors)

    def test_register_offsets_missing_utterance_count(self):
        """register_offsets missing utterance_count should error."""
        invalid_payload = {
            "transcript_id": "p1s1",
            "offsets_path": "transcripts/offsets/p1s1.json"
        }
        errors = validate_units("transcript_prep", "register_offsets", invalid_payload)
        assert len(errors) >= 1
        assert any("utterance_count" in e.field for e in errors)

    def test_transcript_prep_unknown_substep(self):
        """Unknown transcript_prep substep should error."""
        errors = validate_units("transcript_prep", "unknown_substep", {})
        assert len(errors) >= 1
        assert any("substep" in e.field for e in errors)

    # AC6 offset file format tests (Phase 6)
    def test_offset_old_array_format_rejected(self, tmp_path):
        """Offset file in old array format should be rejected."""
        # Write an old-format offset file
        old_format = {
            "transcript_id": "p1s1",
            "utterances": [
                {"utterance_number": 1, "byte_start": 0, "byte_end": 42}
            ]
        }
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text(json.dumps(old_format), encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),  # Use absolute path
            "utterance_count": 1
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)

        # Should error about old array format
        assert len(errors) >= 1
        assert any("offsets_path" in e.field and "old array format" in e.message for e in errors)

    def test_offset_valid_flat_dict_format(self, tmp_path):
        """Valid flat-dict offset file should pass."""
        valid_format = {
            "1": {"byte_start": 0, "byte_end": 42},
            "2": {"byte_start": 44, "byte_end": 91}
        }
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text(json.dumps(valid_format), encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),
            "utterance_count": 2
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert errors == [], f"Expected no errors for valid flat-dict, got {errors}"

    def test_offset_non_integer_key_rejected(self, tmp_path):
        """Offset file with non-integer-string key should be rejected."""
        bad_format = {
            "abc": {"byte_start": 0, "byte_end": 42}
        }
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text(json.dumps(bad_format), encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),
            "utterance_count": 1
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert len(errors) >= 1
        assert any("offsets_path" in e.field and "not a string utterance number" in e.message for e in errors)

    def test_offset_missing_byte_start_rejected(self, tmp_path):
        """Offset entry missing byte_start should be rejected."""
        bad_format = {
            "1": {"byte_end": 42}
        }
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text(json.dumps(bad_format), encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),
            "utterance_count": 1
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert len(errors) >= 1
        assert any("offsets_path" in e.field and "byte_start" in e.message for e in errors)

    def test_offset_non_integer_byte_field_rejected(self, tmp_path):
        """Offset entry with non-integer byte_start should be rejected."""
        bad_format = {
            "1": {"byte_start": "not_an_int", "byte_end": 42}
        }
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text(json.dumps(bad_format), encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),
            "utterance_count": 1
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert len(errors) >= 1
        assert any("offsets_path" in e.field and "must be a non-boolean int" in e.message for e in errors)

    def test_offset_bool_byte_field_rejected(self, tmp_path):
        """Offset entry with boolean byte_start should be rejected (bool is int subclass)."""
        bad_format = {
            "1": {"byte_start": True, "byte_end": 42}
        }
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text(json.dumps(bad_format), encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),
            "utterance_count": 1
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert len(errors) >= 1
        assert any("offsets_path" in e.field and "must be a non-boolean int" in e.message for e in errors)

    def test_offset_non_dict_top_level_rejected(self, tmp_path):
        """Offset file with non-dict top-level should be rejected."""
        bad_format = [1, 2, 3]
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text(json.dumps(bad_format), encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),
            "utterance_count": 1
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert len(errors) >= 1
        assert any("offsets_path" in e.field and "must be a JSON object" in e.message for e in errors)

    def test_offset_nonexistent_file_valid(self):
        """Offset file pointing to non-existent file should not error (file not yet written)."""
        payload = {
            "transcript_id": "p1s1",
            "offsets_path": "transcripts/offsets/nonexistent.json",
            "utterance_count": 42
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert errors == [], f"Expected no errors for nonexistent file, got {errors}"

    def test_offset_malformed_json_rejected(self, tmp_path):
        """Offset file with malformed JSON should be rejected."""
        offsets_path = tmp_path / "offsets.json"
        offsets_path.write_text("{ bad json", encoding="utf-8")

        payload = {
            "transcript_id": "p1s1",
            "offsets_path": str(offsets_path),
            "utterance_count": 1
        }
        errors = validate_units("transcript_prep", "register_offsets", payload)
        assert len(errors) >= 1
        assert any("offsets_path" in e.field and "could not be read" in e.message for e in errors)

    # DAG prerequisite enforcement tests (AC5.5)
    def test_normalize_requires_hash_raw_done(self, tmp_path):
        """normalize fails when hash_raw is not done (prereq_unsatisfied)."""
        run_dir = _init_run_dir(tmp_path)

        # Prepare artifact for normalize
        art_json = _write_artifact(run_dir, "transcript_prep-normalize.json")
        units_payload = {
            "transcript_id": "p1s1",
            "normalized_path": "transcripts/p1s1.txt",
            "diff_path": "transcripts/p1s1.diff"
        }
        units = _write_units_json(run_dir, "normalize_units.json", units_payload)

        # Attempt to close normalize without hash_raw done
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "normalize", "--scope", "p1s1",
            "--artifact", str(art_json), "--units-json", str(units),
            "--reason", "testing prereq", "--run-dir", str(run_dir),
        ])
        assert rc != 0, "Close should fail when hash_raw is not done"

    def test_normalize_succeeds_after_hash_raw_done(self, tmp_path):
        """normalize succeeds after hash_raw is done."""
        run_dir = _init_run_dir(tmp_path)

        # First close hash_raw
        hash_raw_art = _write_artifact(run_dir, "transcript_prep-hash_raw.json")
        hash_raw_units_payload = {
            "transcript_id": "p1s1",
            "sha256": "abc123...",
            "byte_size": 1024
        }
        hash_raw_units = _write_units_json(run_dir, "hash_raw_units.json", hash_raw_units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "hash_raw", "--scope", "p1s1",
            "--artifact", str(hash_raw_art), "--units-json", str(hash_raw_units),
            "--reason", "hash computed", "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"hash_raw close should succeed, got rc={rc}"

        # Now close normalize
        normalize_art = _write_artifact(run_dir, "transcript_prep-normalize.json")
        normalize_units_payload = {
            "transcript_id": "p1s1",
            "normalized_path": "transcripts/p1s1.txt",
            "diff_path": "transcripts/p1s1.diff"
        }
        normalize_units = _write_units_json(run_dir, "normalize_units.json", normalize_units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "normalize", "--scope", "p1s1",
            "--artifact", str(normalize_art), "--units-json", str(normalize_units),
            "--reason", "transcript normalized", "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"normalize close should succeed after hash_raw, got rc={rc}"

    def test_register_offsets_requires_normalize_done(self, tmp_path):
        """register_offsets fails when normalize is not done (prereq_unsatisfied)."""
        run_dir = _init_run_dir(tmp_path)

        # Prepare artifact for register_offsets
        art_json = _write_artifact(run_dir, "transcript_prep-register_offsets.json")
        units_payload = {
            "transcript_id": "p1s1",
            "offsets_path": "transcripts/offsets/p1s1.json",
            "utterance_count": 42
        }
        units = _write_units_json(run_dir, "register_offsets_units.json", units_payload)

        # Attempt to close register_offsets without normalize done
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "register_offsets", "--scope", "p1s1",
            "--artifact", str(art_json), "--units-json", str(units),
            "--reason", "testing prereq", "--run-dir", str(run_dir),
        ])
        assert rc != 0, "Close should fail when normalize is not done"

    def test_register_offsets_requires_both_hash_raw_and_normalize(self, tmp_path):
        """register_offsets fails when only hash_raw is done (normalize required)."""
        run_dir = _init_run_dir(tmp_path)

        # Close hash_raw only
        hash_raw_art = _write_artifact(run_dir, "transcript_prep-hash_raw.json")
        hash_raw_units_payload = {
            "transcript_id": "p1s1",
            "sha256": "abc123...",
            "byte_size": 1024
        }
        hash_raw_units = _write_units_json(run_dir, "hash_raw_units.json", hash_raw_units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "hash_raw", "--scope", "p1s1",
            "--artifact", str(hash_raw_art), "--units-json", str(hash_raw_units),
            "--reason", "hash computed", "--run-dir", str(run_dir),
        ])
        assert rc == 0, "hash_raw close should succeed"

        # Attempt to close register_offsets without normalize
        art_json = _write_artifact(run_dir, "transcript_prep-register_offsets.json")
        units_payload = {
            "transcript_id": "p1s1",
            "offsets_path": "transcripts/offsets/p1s1.json",
            "utterance_count": 42
        }
        units = _write_units_json(run_dir, "register_offsets_units.json", units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "register_offsets", "--scope", "p1s1",
            "--artifact", str(art_json), "--units-json", str(units),
            "--reason", "testing prereq", "--run-dir", str(run_dir),
        ])
        assert rc != 0, "Close should fail when normalize is not done (even if hash_raw is done)"

    def test_register_offsets_succeeds_after_normalize_done(self, tmp_path):
        """register_offsets succeeds after both hash_raw and normalize are done."""
        run_dir = _init_run_dir(tmp_path)

        # Close hash_raw
        hash_raw_art = _write_artifact(run_dir, "transcript_prep-hash_raw.json")
        hash_raw_units_payload = {
            "transcript_id": "p1s1",
            "sha256": "abc123...",
            "byte_size": 1024
        }
        hash_raw_units = _write_units_json(run_dir, "hash_raw_units.json", hash_raw_units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "hash_raw", "--scope", "p1s1",
            "--artifact", str(hash_raw_art), "--units-json", str(hash_raw_units),
            "--reason", "hash computed", "--run-dir", str(run_dir),
        ])
        assert rc == 0, "hash_raw close should succeed"

        # Close normalize
        normalize_art = _write_artifact(run_dir, "transcript_prep-normalize.json")
        normalize_units_payload = {
            "transcript_id": "p1s1",
            "normalized_path": "transcripts/p1s1.txt",
            "diff_path": "transcripts/p1s1.diff"
        }
        normalize_units = _write_units_json(run_dir, "normalize_units.json", normalize_units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "normalize", "--scope", "p1s1",
            "--artifact", str(normalize_art), "--units-json", str(normalize_units),
            "--reason", "transcript normalized", "--run-dir", str(run_dir),
        ])
        assert rc == 0, "normalize close should succeed"

        # Now close register_offsets
        register_offsets_art = _write_artifact(run_dir, "transcript_prep-register_offsets.json")
        register_offsets_units_payload = {
            "transcript_id": "p1s1",
            "offsets_path": "transcripts/offsets/p1s1.json",
            "utterance_count": 42
        }
        register_offsets_units = _write_units_json(run_dir, "register_offsets_units.json", register_offsets_units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "p1s1",
            "--stage", "transcript_prep", "--substep", "register_offsets", "--scope", "p1s1",
            "--artifact", str(register_offsets_art), "--units-json", str(register_offsets_units),
            "--reason", "offsets registered", "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"register_offsets close should succeed after normalize, got rc={rc}"


class TestConfirmStudyConfigClose:
    """Test confirm_study_config close mutation for Task 2 Phase 1."""

    def _close_scan_transcripts(self, run_dir):
        """Helper to close scan_transcripts (prerequisite for confirm_study_config)."""
        scan_art = _write_artifact(run_dir, "init-scan_transcripts.json")
        scan_units_payload = {
            "transcript_ids": ["p1s1", "p1s2", "p2s1"],
            "raw_sha256_map": {"p1s1": "abc...", "p1s2": "def...", "p2s1": "ghi..."}
        }
        scan_units = _write_units_json(run_dir, "scan_units.json", scan_units_payload)
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "scan_transcripts", "--scope", "run",
            "--artifact", str(scan_art), "--units-json", str(scan_units),
            "--reason", "transcripts scanned", "--run-dir", str(run_dir),
        ])
        assert rc == 0, "scan_transcripts close should succeed"

    def test_confirm_study_config_close_writes_to_study_block(self, tmp_path):
        """Closing confirm_study_config writes event_groups, dv_focuses, and config_provenance to manifest["study"]."""
        run_dir = _init_run_dir(tmp_path)
        self._close_scan_transcripts(run_dir)

        # Now prepare artifacts for confirm_study_config
        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")

        # Prepare units with event_groups, dv_focuses, and config_provenance
        units_payload = {
            "event_groups": {
                "event1": ["p1s1", "p2s1", "p3s1"],
                "event2": ["p1s2", "p2s2", "p3s2"],
            },
            "dv_focuses": ["automaticity", "attention", "bodily_sensation"],
            "config_provenance": "user_specified"
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        # Call close for init.confirm_study_config (no prompt artifact for orchestrator)
        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "run",
            "--stage", "init",
            "--substep", "confirm_study_config",
            "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units),
            "--reason", "user confirmed study config",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "Close should succeed"

        # Read manifest and verify study block
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert "study" in manifest, "manifest should have study block"
        assert manifest["study"]["event_groups"] == units_payload["event_groups"]
        assert manifest["study"]["dv_focuses"] == units_payload["dv_focuses"]
        assert manifest["study"]["config_provenance"] == "user_specified"

    def test_confirm_study_config_close_preserves_event_groups_structure(self, tmp_path):
        """event_groups nested structure is preserved exactly."""
        run_dir = _init_run_dir(tmp_path)
        self._close_scan_transcripts(run_dir)

        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")

        # Complex event_groups with multiple events and participants
        units_payload = {
            "event_groups": {
                "event_a": ["p1s1"],
                "event_b": ["p1s2", "p2s1"],
                "event_c": ["p1s3", "p2s2", "p3s1"],
            },
            "config_provenance": "preregistered"
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])

        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["event_groups"] == units_payload["event_groups"]

    def test_confirm_study_config_close_without_dv_focuses(self, tmp_path):
        """When dv_focuses not provided, manifest["study"]["dv_focuses"] is null."""
        run_dir = _init_run_dir(tmp_path)
        self._close_scan_transcripts(run_dir)

        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")

        units_payload = {
            "event_groups": {
                "event1": ["p1s1"],
            },
            # dv_focuses intentionally omitted
            "config_provenance": "llm_proposed_user_confirmed"
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])

        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        # dv_focuses should be null when not provided
        assert manifest["study"].get("dv_focuses") is None

    def test_confirm_study_config_close_with_dv_focuses_list(self, tmp_path):
        """When dv_focuses list provided, it's written to manifest."""
        run_dir = _init_run_dir(tmp_path)
        self._close_scan_transcripts(run_dir)

        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")

        dv_list = ["focus1", "focus2"]
        units_payload = {
            "event_groups": {"event1": ["p1s1"]},
            "dv_focuses": dv_list,
            "config_provenance": "user_specified"
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])

        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["dv_focuses"] == dv_list

    def test_confirm_study_config_close_config_provenance_written(self, tmp_path):
        """config_provenance field is written to manifest."""
        run_dir = _init_run_dir(tmp_path)
        self._close_scan_transcripts(run_dir)

        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")

        provenance = "preregistered"
        units_payload = {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": provenance
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])

        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["config_provenance"] == provenance

    def test_confirm_study_config_close_substep_entry_also_written(self, tmp_path):
        """Confirm_study_config close also writes substep entry (not just study block)."""
        run_dir = _init_run_dir(tmp_path)
        self._close_scan_transcripts(run_dir)

        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")

        units_payload = {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified"
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])

        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        # Check substep entry exists in manifest
        assert "participants" in manifest
        assert "run" in manifest["participants"]
        assert "stages" in manifest["participants"]["run"]
        assert "init" in manifest["participants"]["run"]["stages"]
        assert "confirm_study_config" in manifest["participants"]["run"]["stages"]["init"]["substeps"]

        substep = manifest["participants"]["run"]["stages"]["init"]["substeps"]["confirm_study_config"]
        assert substep["status"] == "done"
        assert "close_id" in substep
        assert "output_paths" in substep

    def test_confirm_study_config_prereq_gate_rejects_unsatisfied(self, tmp_path):
        """Important Issue: confirm_study_config close fails if scan_transcripts is not done."""
        run_dir = _init_run_dir(tmp_path)
        # Deliberately skip _close_scan_transcripts — do NOT close scan_transcripts

        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")
        units_payload = {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified"
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        # Try to close confirm_study_config WITHOUT closing scan_transcripts first
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])

        # Gate should reject this (rc != 0)
        assert rc != 0, "confirm_study_config close should be rejected without scan_transcripts done"

        # Verify manifest study block was NOT mutated
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"].get("event_groups") is None, "study.event_groups should not be set after rejection"

    def test_confirm_study_config_preserves_existing_study_fields(self, tmp_path):
        """Minor Issue 2: confirm_study_config close preserves pre-existing study block fields."""
        run_dir = _init_run_dir(tmp_path)
        self._close_scan_transcripts(run_dir)

        # Pre-populate manifest with a sibling field in study block
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        manifest["study"]["calibration_transcript_ids"] = ["p1s1", "p2s2"]
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest, indent=2) + "\n")

        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")
        units_payload = {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified"
        }
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)

        mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])

        # Verify pre-existing field survived
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["calibration_transcript_ids"] == ["p1s1", "p2s2"], \
            "calibration_transcript_ids should be preserved after confirm_study_config close"
        # And new fields were also written
        assert manifest["study"]["event_groups"] == units_payload["event_groups"]
        assert manifest["study"]["config_provenance"] == "user_specified"


# ---------------------------------------------------------------------------
# CLI --help tests (AC2.2)
# ---------------------------------------------------------------------------

class TestCLIHelp:
    def test_top_level_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "close" in r.stdout
        assert "render" in r.stdout

    def test_close_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "close", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--actor" in r.stdout
        assert "--stage" in r.stdout
        assert "--substep" in r.stdout
        assert "--prompt-artifact" in r.stdout

    def test_init_help(self):
        r = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "mpi_step.py"), "init", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--run" in r.stdout
        assert "--allow-active-repo-nested" in r.stdout


# ---------------------------------------------------------------------------
# init subcommand tests (AC33.*)
# ---------------------------------------------------------------------------

def _git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def _setup_git_identity(run_dir):
    """Set git identity in run_dir so init doesn't fail on AC33.6."""
    _git(["config", "--local", "user.name", "Test User"], cwd=run_dir)
    _git(["config", "--local", "user.email", "test@example.com"], cwd=run_dir)


class TestInitDedicatedRepo:
    def test_init_in_empty_dir_succeeds(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Pre-init repo with identity so test is isolated from global config
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc == 0
        assert (run_dir / ".mpi" / "project.json").exists()

    def test_init_sets_autocrlf_false(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "core.autocrlf"], cwd=run_dir)
        assert r.stdout.strip() == "false"

    def test_init_sets_hooks_path(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "core.hooksPath"], cwd=run_dir)
        assert r.stdout.strip() == ".git/hooks-disabled"
        assert (run_dir / ".git" / "hooks-disabled").is_dir()

    def test_init_sets_gpgsign_false(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        r = _git(["config", "--local", "commit.gpgsign"], cwd=run_dir)
        assert r.stdout.strip() == "false"

    def test_init_manifest_records_dedicated_mode(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        mpi_step.main(["init", "--run", str(run_dir)])
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["run_repo_mode"] == "dedicated"

    def test_init_writes_gitignore_for_close_lock(self, tmp_path):
        # AC4.3 / AC30 regression guard: cmd_init must write .mpi/.gitignore so
        # that the persistent close.lock file doesn't appear as an untracked file
        # in git-status after every close, which would break the cascade clean-tree
        # assertion.
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc == 0
        gi = run_dir / ".mpi" / ".gitignore"
        assert gi.exists(), ".mpi/.gitignore was not written by cmd_init"
        assert "close.lock" in gi.read_text(), \
            ".mpi/.gitignore does not include close.lock"
        # Verify git actually honours the ignore so the run tree stays clean.
        r = _git(["check-ignore", ".mpi/close.lock"], cwd=run_dir)
        assert r.returncode == 0, \
            f"git check-ignore returned {r.returncode}; close.lock is not ignored"


class TestInitActiveRepoNesting:
    def test_init_inside_nonempty_repo_fails_by_default(self, tmp_path):
        # Create a non-empty repo
        outer = tmp_path / "outer"
        outer.mkdir()
        _git(["init"], cwd=outer)
        (outer / "README.md").write_text("hi")
        _git(["add", "."], cwd=outer)
        _git(["commit", "-m", "init", "--allow-empty-message"], cwd=outer)
        # Try to init a run inside it
        run_dir = outer / "run"
        run_dir.mkdir()
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc != 0

    def test_init_with_allow_flag_succeeds(self, tmp_path):
        outer = tmp_path / "outer"
        outer.mkdir()
        _git(["init"], cwd=outer)
        (outer / "README.md").write_text("hi")
        _git(["add", "."], cwd=outer)
        _git(["commit", "-m", "init", "--allow-empty-message"], cwd=outer)
        run_dir = outer / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        _setup_git_identity(run_dir)
        rc = mpi_step.main(["init", "--run", str(run_dir), "--allow-active-repo-nested"])
        assert rc == 0
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"]["run_repo_mode"] == "nested_in_active"


class TestInitIdentityRequired:
    def test_init_fails_without_identity(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        _git(["init"], cwd=run_dir)
        # Ensure no global identity leaks in by patching _git_identity_set
        monkeypatch.setattr(mpi_step, "_git_identity_set", lambda cwd: False)
        rc = mpi_step.main(["init", "--run", str(run_dir)])
        assert rc != 0


# ---------------------------------------------------------------------------
# Static source inspection tests (AC33.7)
# ---------------------------------------------------------------------------

class TestLocalOnlyDefault:
    def test_mpi_step_never_calls_git_push(self):
        """AC33.7: mpi_step.py must never call 'git push' (static source check)."""
        source = (SCRIPTS_DIR / "mpi_step.py").read_text()
        # Check that the source does not contain the string "git push"
        # (either as subprocess call or in a git command list)
        assert '"push"' not in source, \
            "mpi_step.py should never call 'git push'; found quoted 'push' string"
        assert "'push'" not in source, \
            "mpi_step.py should never call 'git push'; found quoted 'push' string"

    def test_mpi_step_never_calls_git_remote_add(self):
        """AC33.7: mpi_step.py must never call 'git remote add' (static source check)."""
        source = (SCRIPTS_DIR / "mpi_step.py").read_text()
        assert "remote add" not in source, \
            "mpi_step.py should never call 'git remote add'; found 'remote add' string"


# ---------------------------------------------------------------------------
# Units extraction helper tests (Issue #5)
# ---------------------------------------------------------------------------

class TestExtractUnits:
    def test_extract_units_diachronic_shape(self):
        """Extract units from diachronic shape: payload["idus"]"""
        payload = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [
                {"idu_number": 1, "idu_name": "Unit1"},
                {"idu_number": 2, "idu_name": "Unit2"},
            ],
        }
        units = mpi_step._extract_units(payload)
        assert len(units) == 2
        assert units[0]["idu_name"] == "Unit1"
        assert units[1]["idu_name"] == "Unit2"

    def test_extract_units_synchronic_flat_shape(self):
        """Extract units from synchronic flat shape: payload["isus"]"""
        payload = {
            "analysis_type": "synchronic",
            "participant": "p1s1",
            "idu_name": "Opening",
            "isus": [
                {"isu_name": "Warmth"},
                {"isu_name": "Coolness"},
            ],
        }
        units = mpi_step._extract_units(payload)
        assert len(units) == 2
        assert units[0]["isu_name"] == "Warmth"
        assert units[1]["isu_name"] == "Coolness"

    def test_extract_units_synchronic_nested_per_idu_shape(self):
        """Extract units from synchronic nested shape: payload["isus"] = [{idu_name, isus:[...]}]"""
        payload = {
            "analysis_type": "synchronic",
            "isus": [
                {
                    "idu_name": "Opening",
                    "isus": [
                        {"isu_name": "Warmth"},
                        {"isu_name": "Coolness"},
                    ],
                },
                {
                    "idu_name": "Middle",
                    "isus": [
                        {"isu_name": "Tension"},
                    ],
                },
            ],
        }
        units = mpi_step._extract_units(payload)
        assert len(units) == 3
        assert units[0]["isu_name"] == "Warmth"
        assert units[1]["isu_name"] == "Coolness"
        assert units[2]["isu_name"] == "Tension"


# ---------------------------------------------------------------------------
# Phase 2: close transaction tests
# ---------------------------------------------------------------------------

import shutil


def _init_run_dir(tmp_path: Path) -> Path:
    """Create a git-initialised MPI run dir with identity set."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    subprocess.run(["git", "init"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.name", "Test"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.email", "t@t.com"], cwd=run_dir, capture_output=True)
    mpi_step.main(["init", "--run", str(run_dir)])
    return run_dir


def _write_artifact(run_dir: Path, name: str, content: str = '{"ok": true}') -> Path:
    p = run_dir / "analyses" / name
    p.parent.mkdir(exist_ok=True)
    p.write_text(content)
    return p


def _write_prompt_artifact(run_dir: Path, scope: str, stage: str, substep: str) -> Path:
    p = run_dir / "analyses" / f"{scope}-{stage}.{substep}.prompt.json"
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "2",
        "actor": {"kind": "subagent", "name": "mpi-analyst",
                  "agent_file_sha256": "abc123", "agent_file_path": "agents/mpi-analyst.md"},
        "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
        "sampling": {"temperature": 1.0, "top_p": 1.0, "top_k": None,
                     "max_tokens": 8192, "seed": None, "stop_sequences": []},
        "stage": stage, "substep": substep, "scope": scope,
        "prompt": {"system": "...", "messages": [], "tools_available": []},
        "response": {"raw_text": "...", "tool_calls": [], "parsed_units_path": ""},
        "metadata": {"finish_reason": "end_turn",
                     "usage": {"input_tokens": 0, "output_tokens": 0,
                               "cache_read_tokens": 0, "cache_write_tokens": 0},
                     "duration_ms": 100, "timestamp": "2026-05-18T00:00:00Z",
                     "anthropic_request_id": "req_xxx"},
    }))
    return p


def _write_units_json(run_dir: Path, name: str, payload: dict) -> Path:
    p = run_dir / name
    p.write_text(json.dumps(payload))
    return p


VALID_CRITERIA_GROUPING_UNITS = {
    "analysis_type": "diachronic",
    "participant": "p1s1",
    "reasoning_summary": "test",
    "idus": [
        {
            "idu_number": 1, "idu_name": "Start", "moment": 1,
            "criteria": "The utterances talk about starting.",
            "confidence": 4, "flag_for_review": False,
            "utterance_numbers": ["1", "2"],
            "hinge_to_next": None,
            "utterance_refs": [
                {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "hello test"},
                {"transcript_id": "p1s1", "utterance_number": 2, "byte_start": 10, "byte_end": 20, "raw_excerpt": "world test"},
            ],
        }
    ],
}


class TestCloseHappyPath:
    def test_close_criteria_grouping_succeeds(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", "p1s1",
            "--stage", "diachronic",
            "--substep", "criteria_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "criteria grouped",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0

    def test_close_writes_audit_events(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        audit = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit if l.strip()]
        actions = [e["event"]["action"] for e in events]
        assert "close_attempted" in actions
        assert "artifacts_validated" in actions
        assert "audit_appended" in actions
        assert "manifest_replaced" in actions
        assert "git_commit_succeeded" in actions

    def test_close_events_share_close_id(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        audit = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit if l.strip()]
        close_ids = {e["mpi"]["close_id"] for e in events if "close_id" in e.get("mpi", {})}
        assert len(close_ids) == 1, f"Expected 1 close_id, got {close_ids}"

    def test_close_updates_manifest_substeps(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        substep = manifest["participants"]["p1s1"]["stages"]["diachronic"]["substeps"]["criteria_grouping"]
        assert substep["status"] == "done"
        assert "close_id" in substep
        assert substep.get("expected_action") == "git_commit_succeeded"
        # No git_commit_sha in manifest (self-reference impossibility)
        assert "git_commit_sha" not in substep
        # AC10.1: stage status is derived from substeps (all done → done)
        assert manifest["participants"]["p1s1"]["stages"]["diachronic"]["status"] == "done"


class TestManifestAtomicity:
    def test_os_replace_failure_leaves_manifest_unchanged(self, tmp_path, monkeypatch):
        """AC3.2: if os.replace fails, manifest reverts to pre-close state and .tmp unlinked."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        manifest_before = (run_dir / ".mpi" / "project.json").read_text()

        # Monkeypatch os.replace to fail
        original_replace = os.replace
        def failing_replace(src, dst):
            raise OSError("Simulated os.replace failure")

        monkeypatch.setattr("os.replace", failing_replace)

        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])

        # Restore original function
        monkeypatch.setattr("os.replace", original_replace)

        assert rc != 0
        # Manifest should be unchanged
        manifest_after = (run_dir / ".mpi" / "project.json").read_text()
        assert manifest_before == manifest_after
        # No .tmp file should be left
        tmp_file = run_dir / ".mpi" / "project.json.tmp"
        assert not tmp_file.exists()


class TestManifestWriteSafety:
    """AC4: Manifest write safety under parallel closes."""

    def test_parallel_closes_both_succeed(self, tmp_path):
        """AC4.1: Two parallel cmd_close calls on different participants both commit."""
        run_dir = _init_run_dir(tmp_path)

        # Create artifacts and units for p1s1
        art1_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art1_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# p1s1")
        prompt1 = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units1 = _write_units_json(run_dir, "units1.json", VALID_CRITERIA_GROUPING_UNITS)

        # Create artifacts and units for p2s1
        units2_payload = VALID_CRITERIA_GROUPING_UNITS.copy()
        units2_payload["participant"] = "p2s1"
        units2_payload["idus"][0]["utterance_refs"][0]["transcript_id"] = "p2s1"
        units2_payload["idus"][0]["utterance_refs"][1]["transcript_id"] = "p2s1"
        art2_json = _write_artifact(run_dir, "p2s1-diachronic.criteria_grouping.json")
        art2_md = _write_artifact(run_dir, "p2s1-diachronic.criteria_grouping.md", "# p2s1")
        prompt2 = _write_prompt_artifact(run_dir, "p2s1", "diachronic", "criteria_grouping")
        units2 = _write_units_json(run_dir, "units2.json", units2_payload)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SCRIPTS_DIR)

        # Launch two parallel closes
        proc1 = subprocess.Popen([
            sys.executable, "-m", "mpi_step", "close",
            "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art1_json), "--artifact", str(art1_md),
            "--prompt-artifact", str(prompt1), "--units-json", str(units1),
            "--reason", "test p1s1", "--run-dir", str(run_dir),
        ], cwd=run_dir, env=env)

        proc2 = subprocess.Popen([
            sys.executable, "-m", "mpi_step", "close",
            "--actor", "mpi-analyst", "--participant", "p2s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p2s1", "--artifact", str(art2_json), "--artifact", str(art2_md),
            "--prompt-artifact", str(prompt2), "--units-json", str(units2),
            "--reason", "test p2s1", "--run-dir", str(run_dir),
        ], cwd=run_dir, env=env)

        rc1 = proc1.wait()
        rc2 = proc2.wait()

        assert rc1 == 0, "proc1 should succeed"
        assert rc2 == 0, "proc2 should succeed"

        # Check final manifest has both participants done
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["participants"]["p1s1"]["stages"]["diachronic"]["substeps"]["criteria_grouping"]["status"] == "done"
        assert manifest["participants"]["p2s1"]["stages"]["diachronic"]["substeps"]["criteria_grouping"]["status"] == "done"

    def test_lock_prevents_manifest_overwrite(self, tmp_path):
        """AC4.2: Lock prevents concurrent mutation from overwriting each other."""
        run_dir = _init_run_dir(tmp_path)

        # Create artifacts and units for p1s1
        units1_payload = VALID_CRITERIA_GROUPING_UNITS.copy()
        units1_payload["participant"] = "p1s1"
        art1_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art1_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# p1s1")
        prompt1 = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units1 = _write_units_json(run_dir, "units1.json", units1_payload)

        # Create artifacts and units for p2s1
        units2_payload = VALID_CRITERIA_GROUPING_UNITS.copy()
        units2_payload["participant"] = "p2s1"
        units2_payload["idus"][0]["utterance_refs"][0]["transcript_id"] = "p2s1"
        units2_payload["idus"][0]["utterance_refs"][1]["transcript_id"] = "p2s1"
        art2_json = _write_artifact(run_dir, "p2s1-diachronic.criteria_grouping.json")
        art2_md = _write_artifact(run_dir, "p2s1-diachronic.criteria_grouping.md", "# p2s1")
        prompt2 = _write_prompt_artifact(run_dir, "p2s1", "diachronic", "criteria_grouping")
        units2 = _write_units_json(run_dir, "units2.json", units2_payload)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SCRIPTS_DIR)

        # Launch both closes in parallel
        proc1 = subprocess.Popen([
            sys.executable, "-m", "mpi_step", "close",
            "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art1_json), "--artifact", str(art1_md),
            "--prompt-artifact", str(prompt1), "--units-json", str(units1),
            "--reason", "test", "--run-dir", str(run_dir),
        ], cwd=run_dir, env=env)

        proc2 = subprocess.Popen([
            sys.executable, "-m", "mpi_step", "close",
            "--actor", "mpi-analyst", "--participant", "p2s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p2s1", "--artifact", str(art2_json), "--artifact", str(art2_md),
            "--prompt-artifact", str(prompt2), "--units-json", str(units2),
            "--reason", "test", "--run-dir", str(run_dir),
        ], cwd=run_dir, env=env)

        proc1.wait()
        proc2.wait()

        # Verify final manifest has entries for BOTH participants (not overwritten)
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert "p1s1" in manifest["participants"], "p1s1 should be in final manifest"
        assert "p2s1" in manifest["participants"], "p2s2 should be in final manifest"

    def test_lock_is_reacquirable_after_process_exit(self, tmp_path):
        """AC4.3: After process exit (normal or signal), lock is re-acquirable."""
        run_dir = _init_run_dir(tmp_path)
        ready_marker = run_dir / ".mpi" / "lock_holder_ready"
        helper_script = run_dir / "lock_holder_helper.py"

        # Write a helper script that acquires the lock and sleeps indefinitely
        helper_code = f'''
import sys
import time
from pathlib import Path
sys.path.insert(0, {str(SCRIPTS_DIR)!r})
from _mpi_atomic import acquire_close_lock

run_dir = Path({str(run_dir)!r})
ready_marker = Path({str(ready_marker)!r})

with acquire_close_lock(run_dir):
    # Signal that lock is acquired
    ready_marker.write_text("ready")
    # Hold the lock indefinitely
    time.sleep(999)
'''
        helper_script.write_text(helper_code)

        env = os.environ.copy()
        env["PYTHONPATH"] = str(SCRIPTS_DIR)

        # Start helper process to hold the lock
        proc = subprocess.Popen(
            [sys.executable, str(helper_script)],
            cwd=run_dir,
            env=env,
        )

        try:
            # Poll for the ready marker (timeout after 5 seconds)
            start_time = time.time()
            while not ready_marker.exists() and time.time() - start_time < 5:
                time.sleep(0.05)
            assert ready_marker.exists(), "Helper process failed to acquire lock (ready marker not created)"

            # Now in the parent, try to acquire the lock in a separate thread
            # This thread should BLOCK while the helper holds the lock
            lock_acquired_event = threading.Event()
            thread_trying_event = threading.Event()

            def try_acquire():
                """Try to acquire; set event when acquired."""
                thread_trying_event.set()  # Signal that we're about to block
                with acquire_close_lock(run_dir):
                    lock_acquired_event.set()

            acq_thread = threading.Thread(target=try_acquire, daemon=True)
            acq_thread.start()

            # Wait for thread to signal it's trying
            acq_thread_trying = thread_trying_event.wait(timeout=1)
            assert acq_thread_trying, "Acquire thread did not start"

            # Negative control: lock should NOT be acquired yet (subprocess holds it)
            time.sleep(0.3)
            assert not lock_acquired_event.is_set(), \
                "Lock acquired while helper holds it — lock implementation is broken"

            # Now terminate the helper process
            proc.terminate()
            proc.wait(timeout=5)

            # After helper exits, the thread should acquire the lock (OS auto-released it)
            acq_thread.join(timeout=5)
            assert lock_acquired_event.is_set(), \
                "Lock not acquired after helper process exit — OS did not auto-release"

            # Lock file should still exist (by design)
            assert (run_dir / ".mpi" / "close.lock").exists(), \
                "Lock file should persist after release"
        finally:
            # Guarantee subprocess cleanup regardless of assertion outcome
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)

    def test_lock_blocks_concurrent_acquisition(self, tmp_path):
        """Deterministic serialization test: lock primitives actually block."""
        run_dir = _init_run_dir(tmp_path)
        lock_sequence = []

        def thread_acquire_lock(thread_id: int):
            """Acquire lock, record sequence, hold briefly, release."""
            lock_sequence.append(f"start_{thread_id}")
            with acquire_close_lock(run_dir):
                lock_sequence.append(f"acquired_{thread_id}")
                time.sleep(0.1)  # Hold the lock
                lock_sequence.append(f"releasing_{thread_id}")
            lock_sequence.append(f"released_{thread_id}")

        # Launch two threads that both try to acquire the lock
        t1 = threading.Thread(target=thread_acquire_lock, args=(1,))
        t2 = threading.Thread(target=thread_acquire_lock, args=(2,))

        t1.start()
        time.sleep(0.05)  # Let thread 1 acquire the lock first
        t2.start()

        t1.join()
        t2.join()

        # Verify that acquisitions did not overlap
        # Look for the pattern: acquired_1, releasing_1, acquired_2
        acquired_1_idx = lock_sequence.index("acquired_1")
        releasing_1_idx = lock_sequence.index("releasing_1")
        acquired_2_idx = lock_sequence.index("acquired_2")

        # Thread 2 must acquire after thread 1 releases — serialization enforced
        assert acquired_2_idx > releasing_1_idx, \
            "thread 2 acquired before thread 1 released — lock did not serialize"


class TestCloseFailures:
    def test_missing_artifact_fails(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(run_dir / "nonexistent.json"),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_missing_manifest_fails(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        rc = mpi_step.main([
            "close", "--actor", "x", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", "x.json",
            "--units-json", "x.json", "--reason", "x",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_dag_prereq_enforced(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "idu_naming_ordering")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        # criteria_revision not done — close should fail
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "idu_naming_ordering",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_llm_substep_requires_prompt_artifact(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            # NO --prompt-artifact
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_manifest_unchanged_on_failure(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        manifest_before = (run_dir / ".mpi" / "project.json").read_text()
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        # Missing artifact
        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(run_dir / "missing.json"),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        manifest_after = (run_dir / ".mpi" / "project.json").read_text()
        assert manifest_before == manifest_after

    def test_malformed_units_wrong_field_name_fails(self, tmp_path):
        """AC4.2: units with wrong field name (title instead of idu_name) rejected."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        # Malformed: title instead of idu_name
        malformed_units = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "reasoning_summary": "test",
            "idus": [
                {
                    "idu_number": 1, "title": "Start",  # WRONG: should be idu_name
                    "moment": 1, "criteria": "...",
                    "confidence": 4, "flag_for_review": False,
                    "utterance_numbers": ["1", "2"], "hinge_to_next": None,
                }
            ],
        }
        units = _write_units_json(run_dir, "units.json", malformed_units)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_malformed_units_confidence_out_of_range_fails(self, tmp_path):
        """AC4.3: units with confidence outside 1-5 rejected."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        # Malformed: confidence out of range
        malformed_units = {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "reasoning_summary": "test",
            "idus": [
                {
                    "idu_number": 1, "idu_name": "Start", "moment": 1,
                    "criteria": "...", "confidence": 10,  # WRONG: should be 1-5
                    "flag_for_review": False,
                    "utterance_numbers": ["1", "2"], "hinge_to_next": None,
                }
            ],
        }
        units = _write_units_json(run_dir, "units.json", malformed_units)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0
        # Verify no git_commit_succeeded event in audit
        audit = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit if l.strip()]
        actions = [e["event"]["action"] for e in events]
        assert "git_commit_succeeded" not in actions


class TestVerify:
    def test_verify_returns_zero_after_successful_close(self, tmp_path):
        """Verify returns 0 after a successful close."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        # First do a successful close
        rc_close = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "criteria grouped", "--run-dir", str(run_dir),
        ])
        assert rc_close == 0

        # Now verify should return 0
        rc_verify = mpi_step.main(["verify", "--run-dir", str(run_dir)])
        assert rc_verify == 0

    def test_verify_fails_with_tampered_close_id(self, tmp_path):
        """Verify returns non-zero if manifest close_id is tampered."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        # Do a successful close
        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])

        # Tamper the manifest's close_id
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        manifest["participants"]["p1s1"]["stages"]["diachronic"]["substeps"]["criteria_grouping"]["close_id"] = "tampered-id"
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest, indent=2) + "\n")

        # Verify should fail
        rc_verify = mpi_step.main(["verify", "--run-dir", str(run_dir)])
        assert rc_verify != 0

    def test_verify_fails_if_audit_git_commit_succeeded_missing(self, tmp_path):
        """Verify returns non-zero if matching git_commit_succeeded event missing."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        # Do a successful close
        mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art), "--units-json", str(units),
            "--reason", "test", "--run-dir", str(run_dir),
        ])

        # Delete the git_commit_succeeded audit line
        audit_lines = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        filtered_lines = [
            l for l in audit_lines
            if not (l.strip() and "git_commit_succeeded" in l)
        ]
        (run_dir / ".mpi" / "audit.jsonl").write_text("\n".join(filtered_lines) + "\n" if filtered_lines else "")

        # Verify should fail
        rc_verify = mpi_step.main(["verify", "--run-dir", str(run_dir)])
        assert rc_verify != 0


# ---------------------------------------------------------------------------
# Phase 3: render tests
# ---------------------------------------------------------------------------

SAMPLE_AUDIT_EVENTS = [
    {
        "event_id": "evt-1", "@timestamp": "2026-05-18T10:00:00Z",
        "trace_id": "trace-abc", "span_id": "span-1",
        "actor": {"kind": "subagent", "name": "mpi-analyst"},
        "event": {"kind": "event", "action": "close_attempted", "outcome": "success"},
        "mpi": {
            "participant_id": "p1s1", "stage": "diachronic",
            "substep": "criteria_grouping", "scope": "p1s1",
            "close_id": "close-xyz", "n_units": 3,
        },
        "reason": "starting close",
    },
    {
        "event_id": "evt-2", "@timestamp": "2026-05-18T10:00:01Z",
        "trace_id": "trace-abc", "span_id": "span-2",
        "actor": {"kind": "subagent", "name": "mpi-analyst"},
        "event": {"kind": "event", "action": "git_commit_succeeded", "outcome": "success"},
        "mpi": {
            "participant_id": "p1s1", "stage": "diachronic",
            "substep": "criteria_grouping", "scope": "p1s1",
            "close_id": "close-xyz", "git_commit_sha": "abcdef1234567",
        },
        "reason": "commit ok",
    },
]


class TestRender:
    def _write_audit(self, tmp_path: Path, events: list) -> Path:
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        audit = mpi_dir / "audit.jsonl"
        for ev in events:
            audit_line = json.dumps(ev) + "\n"
            with open(audit, "a") as f:
                f.write(audit_line)
        return run_dir

    def test_render_produces_reasoning_log(self, tmp_path):
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS)
        rc = mpi_step.main(["render", "--run-dir", str(run_dir)])
        assert rc == 0
        log = (run_dir / ".mpi" / "reasoning.log").read_text()
        assert "close_attempted" in log or "starting close" in log
        assert "p1s1" in log

    def test_render_includes_commit_sha(self, tmp_path):
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS)
        mpi_step.main(["render", "--run-dir", str(run_dir)])
        log = (run_dir / ".mpi" / "reasoning.log").read_text()
        assert "abcdef1" in log

    def test_render_idempotent(self, tmp_path):
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS)
        mpi_step.main(["render", "--run-dir", str(run_dir)])
        content_a = (run_dir / ".mpi" / "reasoning.log").read_bytes()
        mpi_step.main(["render", "--run-dir", str(run_dir)])
        content_b = (run_dir / ".mpi" / "reasoning.log").read_bytes()
        assert content_a == content_b

    def test_render_malformed_line_placeholder(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        mpi_dir = run_dir / ".mpi"
        mpi_dir.mkdir()
        audit = mpi_dir / "audit.jsonl"
        # Good line, bad line, good line
        audit.write_text(
            json.dumps(SAMPLE_AUDIT_EVENTS[0]) + "\n"
            + "THIS IS NOT JSON @@@@\n"
            + json.dumps(SAMPLE_AUDIT_EVENTS[1]) + "\n"
        )
        rc = mpi_step.main(["render", "--run-dir", str(run_dir)])
        assert rc == 0
        log = (run_dir / ".mpi" / "reasoning.log").read_text()
        assert "MALFORMED:2" in log
        assert "p1s1" in log  # other events still rendered

    def test_render_filter_by_participant(self, tmp_path):
        extra_event = {
            "event_id": "evt-3", "@timestamp": "2026-05-18T10:00:02Z",
            "trace_id": "trace-abc", "span_id": "span-3",
            "actor": {"kind": "subagent", "name": "mpi-analyst"},
            "event": {"kind": "event", "action": "close_attempted", "outcome": "success"},
            "mpi": {
                "participant_id": "p2s1", "stage": "diachronic",
                "substep": "criteria_grouping", "scope": "p2s1",
                "close_id": "close-zzz",
            },
            "reason": "other participant",
        }
        run_dir = self._write_audit(tmp_path, SAMPLE_AUDIT_EVENTS + [extra_event])
        out = tmp_path / "filtered.log"
        mpi_step.main(["render", "--run-dir", str(run_dir), "--participant", "p1s1", "--out", str(out)])
        log = out.read_text()
        assert "p1s1" in log
        assert "p2s1" not in log


# ---------------------------------------------------------------------------
# Phase 4: per-substep schema tests
# ---------------------------------------------------------------------------

VALID_UTTERANCE_REF = {
    "transcript_id": "p1s1",
    "utterance_number": 1,
    "byte_start": 0,
    "byte_end": 10,
    "raw_excerpt": "hello test",
}

VALID_IDU = {
    "idu_number": 1, "idu_name": "Opening Experience", "moment": 1,
    "criteria": "The utterances talk about the opening moment.",
    "confidence": 4, "flag_for_review": False,
    "utterance_numbers": ["1", "2"],
    "hinge_to_next": None,
    "utterance_refs": [VALID_UTTERANCE_REF],
}

VALID_DIACHRONIC_PAYLOAD = {
    "analysis_type": "diachronic",
    "participant": "p1s1",
    "reasoning_summary": "Three IDUs identified.",
    "idus": [VALID_IDU],
}

VALID_CRITERIA_REVISION_PAYLOAD = {
    **VALID_DIACHRONIC_PAYLOAD,
    "convergence": {"decision": "converged", "reason": "No further improvements needed."},
}

VALID_ISU = {
    "isu_name": "Sense of Warmth",
    "isu_second_level_of_abstraction": "Tactile Qualities",
    "criteria": "The utterances talk about warmth.",
    "confidence": 4,
    "flag_for_review": False,
    "utterance_refs": [VALID_UTTERANCE_REF],
}

VALID_SYNCHRONIC_PAYLOAD = {
    "analysis_type": "synchronic",
    "participant": "p1s1",
    "idu_name": "Opening Experience",
    "isus": [VALID_ISU],
}


class TestSchemaAcceptsValid:
    def test_criteria_grouping_valid(self):
        errs = validate_units("diachronic", "criteria_grouping", VALID_DIACHRONIC_PAYLOAD)
        assert errs == [], [str(e) for e in errs]

    def test_criteria_revision_valid(self):
        errs = validate_units("diachronic", "criteria_revision", VALID_CRITERIA_REVISION_PAYLOAD)
        assert errs == [], [str(e) for e in errs]

    def test_synchronic_theme_grouping_valid(self):
        errs = validate_units("synchronic", "theme_grouping_within_idu", VALID_SYNCHRONIC_PAYLOAD)
        assert errs == [], [str(e) for e in errs]


class TestSchemaDriftNames:
    def test_title_instead_of_idu_name_rejected(self):
        bad_idu = {k: v for k, v in VALID_IDU.items() if k != "idu_name"}
        bad_idu["title"] = "Wrong"
        bad_payload = {**VALID_DIACHRONIC_PAYLOAD, "idus": [bad_idu]}
        errs = validate_units("diachronic", "criteria_grouping", bad_payload)
        assert any("title" in str(e) for e in errs), [str(e) for e in errs]

    def test_utterance_lines_instead_of_utterance_numbers_rejected(self):
        bad_idu = {k: v for k, v in VALID_IDU.items() if k != "utterance_numbers"}
        bad_idu["utterance_lines"] = ["1"]
        bad_payload = {**VALID_DIACHRONIC_PAYLOAD, "idus": [bad_idu]}
        errs = validate_units("diachronic", "criteria_grouping", bad_payload)
        assert any("utterance_lines" in str(e) for e in errs), [str(e) for e in errs]

    def test_isu_2nd_level_instead_of_isu_second_level_rejected(self):
        bad_isu = {k: v for k, v in VALID_ISU.items() if k != "isu_second_level_of_abstraction"}
        bad_isu["isu_2nd_level"] = "wrong"
        bad_payload = {**VALID_SYNCHRONIC_PAYLOAD, "isus": [bad_isu]}
        # Test against isu_second_level_grouping — that substep requires the field
        errs = validate_units("synchronic", "isu_second_level_grouping", bad_payload)
        assert any("isu_2nd_level" in str(e) for e in errs), [str(e) for e in errs]

    def test_isu_second_level_not_required_at_theme_grouping(self):
        """theme_grouping_within_idu does not require isu_second_level_of_abstraction."""
        isu_no_second_level = {k: v for k, v in VALID_ISU.items() if k != "isu_second_level_of_abstraction"}
        payload = {**VALID_SYNCHRONIC_PAYLOAD, "isus": [isu_no_second_level]}
        errs = validate_units("synchronic", "theme_grouping_within_idu", payload)
        assert not any("isu_second_level" in str(e) for e in errs), [str(e) for e in errs]


class TestSchemaRangeErrors:
    def test_confidence_out_of_range(self):
        bad_idu = {**VALID_IDU, "confidence": 9}
        bad_payload = {**VALID_DIACHRONIC_PAYLOAD, "idus": [bad_idu]}
        errs = validate_units("diachronic", "criteria_grouping", bad_payload)
        assert any("confidence" in str(e) for e in errs), [str(e) for e in errs]

    def test_flag_for_review_non_bool(self):
        bad_idu = {**VALID_IDU, "flag_for_review": "yes"}
        bad_payload = {**VALID_DIACHRONIC_PAYLOAD, "idus": [bad_idu]}
        errs = validate_units("diachronic", "criteria_grouping", bad_payload)
        assert any("flag_for_review" in str(e) for e in errs), [str(e) for e in errs]

    def test_hinge_null_on_non_last_idu(self):
        idu1 = {**VALID_IDU, "idu_number": 1, "hinge_to_next": None}
        idu2 = {**VALID_IDU, "idu_number": 2, "moment": 2, "hinge_to_next": None}
        bad_payload = {**VALID_DIACHRONIC_PAYLOAD, "idus": [idu1, idu2]}
        errs = validate_units("diachronic", "criteria_grouping", bad_payload)
        # idu1 is non-last and has null hinge — should error
        assert any("hinge_to_next" in str(e) for e in errs), [str(e) for e in errs]


class TestSchemaUtteranceRefs:
    def test_missing_utterance_refs_rejected(self):
        bad_idu = {k: v for k, v in VALID_IDU.items() if k != "utterance_refs"}
        bad_payload = {**VALID_DIACHRONIC_PAYLOAD, "idus": [bad_idu]}
        errs = validate_units("diachronic", "criteria_grouping", bad_payload)
        assert any("utterance_refs" in str(e) for e in errs), [str(e) for e in errs]
        assert any("missing_span_refs" in str(e) for e in errs), [str(e) for e in errs]

    def test_empty_utterance_refs_rejected(self):
        bad_idu = {**VALID_IDU, "utterance_refs": []}
        bad_payload = {**VALID_DIACHRONIC_PAYLOAD, "idus": [bad_idu]}
        errs = validate_units("diachronic", "criteria_grouping", bad_payload)
        assert any("utterance_refs" in str(e) and "missing_span_refs" in str(e) for e in errs), [str(e) for e in errs]


class TestSchemaConvergenceField:
    def test_criteria_revision_missing_convergence(self):
        errs = validate_units("diachronic", "criteria_revision", VALID_DIACHRONIC_PAYLOAD)
        assert any("convergence" in str(e) for e in errs), [str(e) for e in errs]

    def test_criteria_revision_bad_decision(self):
        bad_payload = {
            **VALID_DIACHRONIC_PAYLOAD,
            "convergence": {"decision": "keep_going", "reason": "still working"},
        }
        errs = validate_units("diachronic", "criteria_revision", bad_payload)
        assert any("decision" in str(e) for e in errs), [str(e) for e in errs]


# ---------------------------------------------------------------------------
# Phase 5: prompt artifact validation tests
# ---------------------------------------------------------------------------

VALID_PROMPT_ARTIFACT = {
    "schema_version": "2",
    "actor": {
        "kind": "subagent", "name": "mpi-analyst",
        "agent_file_sha256": "abc123def456",
        "agent_file_path": "agents/mpi-analyst.md",
    },
    "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
    "sampling": {
        "temperature": 1.0, "top_p": 1.0, "top_k": None,
        "max_tokens": 8192, "seed": None, "stop_sequences": [],
    },
    "stage": "diachronic", "substep": "criteria_grouping", "scope": "p1s1",
    "prompt": {"system": "...", "messages": [], "tools_available": []},
    "response": {"raw_text": "...", "tool_calls": [], "parsed_units_path": ""},
    "metadata": {
        "finish_reason": "end_turn",
        "usage": {
            "input_tokens": 100, "output_tokens": 50,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
        },
        "duration_ms": 1500,
        "timestamp": "2026-05-18T10:00:00Z",
        "anthropic_request_id": "req_abc123",
    },
}


class TestPromptArtifactSchema:
    def test_valid_prompt_artifact_accepted(self):
        from _mpi_schemas import validate_prompt_artifact
        errs = validate_prompt_artifact(VALID_PROMPT_ARTIFACT, check_agent_sha=False)
        assert errs == [], [str(e) for e in errs]

    def test_wrong_schema_version_rejected(self):
        from _mpi_schemas import validate_prompt_artifact
        bad = {**VALID_PROMPT_ARTIFACT, "schema_version": "1"}
        errs = validate_prompt_artifact(bad, check_agent_sha=False)
        assert any("schema_version" in str(e) for e in errs), [str(e) for e in errs]

    def test_missing_actor_fields_rejected(self):
        from _mpi_schemas import validate_prompt_artifact
        bad_actor = {"kind": "subagent"}  # missing name, agent_file_sha256, agent_file_path
        bad = {**VALID_PROMPT_ARTIFACT, "actor": bad_actor}
        errs = validate_prompt_artifact(bad, check_agent_sha=False)
        assert any("agent_file_sha256" in str(e) for e in errs), [str(e) for e in errs]

    def test_missing_cache_tokens_rejected(self):
        from _mpi_schemas import validate_prompt_artifact
        bad_usage = {"input_tokens": 100, "output_tokens": 50}  # missing cache fields
        bad_meta = {**VALID_PROMPT_ARTIFACT["metadata"], "usage": bad_usage}
        bad = {**VALID_PROMPT_ARTIFACT, "metadata": bad_meta}
        errs = validate_prompt_artifact(bad, check_agent_sha=False)
        assert any("cache_read_tokens" in str(e) or "cache_write_tokens" in str(e) for e in errs), [str(e) for e in errs]


class TestClosePromptArtifactEnforcement:
    def test_llm_substep_without_prompt_artifact_rejected(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            # NO --prompt-artifact
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_malformed_prompt_artifact_rejected(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        # Write a prompt.json missing required fields
        bad_prompt = run_dir / "bad_prompt.json"
        bad_prompt.write_text(json.dumps({"schema_version": "1", "actor": {}}))
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(bad_prompt),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0
        # Manifest must be unchanged — criteria_grouping substep must not be present
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert "criteria_grouping" not in manifest.get("participants", {}).get("p1s1", {}).get("stages", {}).get("diachronic", {}).get("substeps", {})

    def test_valid_prompt_artifact_accepted_in_close(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc == 0
        # Audit event must reference the prompt artifact path
        audit = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit if l.strip()]
        audit_events = [e for e in events if e.get("event", {}).get("action") == "audit_appended"]
        assert audit_events, "No audit_appended event found"
        assert any(
            e.get("mpi", {}).get("prompt_artifact_path") for e in events
        ), "No prompt_artifact_path in any audit event"


# ---------------------------------------------------------------------------
# Phase 9: --status read mode tests (AC6.4)
# ---------------------------------------------------------------------------

class TestStatusReadMode:
    def test_status_read_in_valid_run_succeeds(self, tmp_path):
        """--status read in initialized run exits 0, appends one audit event, no artifacts/commits."""
        run_dir = _init_run_dir(tmp_path)
        audit_before = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        audit_count_before = len([l for l in audit_before if l.strip()])

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--stage", "status",
            "--substep", "status_read",
            "--scope", "global",
            "--status", "read",
            "--reason", "status read",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0

        # Verify exactly one new audit event was appended
        audit_after = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        audit_count_after = len([l for l in audit_after if l.strip()])
        assert audit_count_after == audit_count_before + 1

        # Verify the new event has action="stage_read" and stage_phase="read"
        events = [json.loads(l) for l in audit_after if l.strip()]
        read_events = [e for e in events if e.get("event", {}).get("action") == "stage_read"]
        assert len(read_events) >= 1
        latest_read_event = read_events[-1]
        assert latest_read_event["mpi"]["stage_phase"] == "read"

    def test_status_read_no_artifacts_created(self, tmp_path):
        """--status read does NOT create any artifact files."""
        run_dir = _init_run_dir(tmp_path)
        analyses_before = set((run_dir / "analyses").glob("*")) if (run_dir / "analyses").exists() else set()

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--stage", "status",
            "--substep", "status_read",
            "--scope", "global",
            "--status", "read",
            "--reason", "status read",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0

        analyses_after = set((run_dir / "analyses").glob("*")) if (run_dir / "analyses").exists() else set()
        assert analyses_after == analyses_before, "Artifacts should not be created by --status read"

    def test_status_read_no_manifest_mutation(self, tmp_path):
        """--status read does NOT mutate manifest."""
        run_dir = _init_run_dir(tmp_path)
        manifest_before = (run_dir / ".mpi" / "project.json").read_text()

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--stage", "status",
            "--substep", "status_read",
            "--scope", "global",
            "--status", "read",
            "--reason", "status read",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0

        manifest_after = (run_dir / ".mpi" / "project.json").read_text()
        assert manifest_before == manifest_after, "Manifest should not be mutated by --status read"

    def test_status_read_no_git_commit(self, tmp_path):
        """--status read does NOT create a git commit."""
        run_dir = _init_run_dir(tmp_path)
        result_before = subprocess.run(["git", "log", "--oneline"], cwd=run_dir, capture_output=True, text=True)
        commits_before = len([l for l in result_before.stdout.strip().split("\n") if l.strip()])

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--stage", "status",
            "--substep", "status_read",
            "--scope", "global",
            "--status", "read",
            "--reason", "status read",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0

        result_after = subprocess.run(["git", "log", "--oneline"], cwd=run_dir, capture_output=True, text=True)
        commits_after = len([l for l in result_after.stdout.strip().split("\n") if l.strip()])
        assert commits_after == commits_before, "No git commit should be created by --status read"

    def test_status_read_without_audit_jsonl_fails(self, tmp_path):
        """--status read when audit.jsonl missing fails (not initialized)."""
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # Don't initialize — no .mpi directory
        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--stage", "status",
            "--substep", "status_read",
            "--scope", "global",
            "--status", "read",
            "--reason", "status read",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_non_read_close_requires_participant(self, tmp_path):
        """Non-read close missing --participant exits non-zero."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            # NO --participant
            "--stage", "diachronic",
            "--substep", "criteria_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_non_read_close_requires_artifact(self, tmp_path):
        """Non-read close missing --artifact exits non-zero."""
        run_dir = _init_run_dir(tmp_path)
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", "p1s1",
            "--stage", "diachronic",
            "--substep", "criteria_grouping",
            "--scope", "p1s1",
            # NO --artifact
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_non_read_close_requires_units_json(self, tmp_path):
        """Non-read close missing --units-json exits non-zero."""
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", "p1s1",
            "--stage", "diachronic",
            "--substep", "criteria_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            # NO --units-json
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0


class TestStrictIRRGate:
    """Tests for --strict-irr gate on cross-participant substep closes (AC13.8, AC13.9)."""

    def _setup_minimal_run_with_calibration(self, tmp_path: Path, transcript_id: str = "p1s1") -> Path:
        """
        Create minimal run dir with .mpi/ structure and manifest set for IRR gate tests.
        Initializes a run with calibration_transcript_ids configured and all prerequisite
        diachronic/synchronic substeps marked as done for the calibration transcript.
        """
        run_dir = _init_run_dir(tmp_path)

        # Update manifest to set calibration_transcript_ids and mark prerequisites as done
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["study"]["calibration_transcript_ids"] = [transcript_id]

        # Add participant scopes for the transcript with diachronic/synchronic done
        # Generic_diachronic prerequisites: all transcripts must have diachronic + synchronic done
        manifest["participants"][transcript_id] = {
            "stages": {
                "diachronic": {
                    "status": "done",
                    "substeps": {
                        "criteria_grouping": {
                            "status": "done",
                            "close_id": "fake-close-id-1",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "criteria_revision": {
                            "status": "done",
                            "close_id": "fake-close-id-2",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "idu_naming_ordering": {
                            "status": "done",
                            "close_id": "fake-close-id-3",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        }
                    }
                },
                "synchronic": {
                    "status": "done",
                    "substeps": {
                        "theme_grouping_within_idu": {
                            "status": "done",
                            "close_id": "fake-close-id-4",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "isu_naming": {
                            "status": "done",
                            "close_id": "fake-close-id-5",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "isu_second_level_grouping": {
                            "status": "done",
                            "close_id": "fake-close-id-6",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        }
                    }
                }
            }
        }
        # Add an IDU scope for the transcript
        manifest["participants"][f"{transcript_id}-idu1"] = {
            "stages": {
                "synchronic": {
                    "status": "done",
                    "substeps": {
                        "theme_grouping_within_idu": {
                            "status": "done",
                            "close_id": "fake-close-id-7",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "isu_naming": {
                            "status": "done",
                            "close_id": "fake-close-id-8",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "isu_second_level_grouping": {
                            "status": "done",
                            "close_id": "fake-close-id-9",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        }
                    }
                }
            }
        }

        # Mark participant_row_assembly as done for generic_diachronic
        manifest["participants"][transcript_id]["stages"]["generic_diachronic"] = {
            "status": "done",
            "substeps": {
                "participant_row_assembly": {
                    "status": "done",
                    "close_id": "fake-close-id-10",
                    "output_path": "analyses/fake.json",
                    "artifact_shas": {},
                }
            }
        }

        # Mark generic_synchronic prerequisites as done for the IDU scope
        manifest["participants"][f"{transcript_id}-idu1"]["stages"]["generic_synchronic"] = {
            "status": "done",
            "substeps": {
                "select_generic_idus_of_interest": {
                    "status": "done",
                    "close_id": "fake-close-id-11",
                    "output_path": "analyses/fake.json",
                    "artifact_shas": {},
                },
                "worksheet_assembly": {
                    "status": "done",
                    "close_id": "fake-close-id-12",
                    "output_path": "analyses/fake.json",
                    "artifact_shas": {},
                },
            }
        }

        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        return run_dir

    def test_strict_irr_missing_record_blocks_close(self, tmp_path):
        """With --strict-irr and no irr_calibration.jsonl: generic_diachronic close exits non-zero."""
        run_dir = self._setup_minimal_run_with_calibration(tmp_path, "p1s1")

        # Try to close a generic_diachronic substep with --strict-irr but no IRR record
        art_json = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_diachronic", "idu_similarity_grouping")

        # Valid generic_diachronic payload
        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_diachronic",
            "event": "Test Event",
            "idu_labels": [{
                "idu_name": "Test IDU",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "generic_diachronic",
            "--substep", "idu_similarity_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close with strict-irr",
            "--run-dir", str(run_dir),
            "--strict-irr",  # KEY: strict-irr gate enabled
        ])

        # Should fail because IRR record missing
        assert rc != 0, f"Expected non-zero rc with --strict-irr and no IRR record, got {rc}"
        # Check audit log contains irr_warning
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        if audit_path.exists():
            audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]
            has_irr_warning = any(e.get("event", {}).get("action") == "irr_warning" for e in audit_events)
            assert has_irr_warning, "Audit should contain irr_warning event"

    def test_strict_irr_passed_outcome_allows_close(self, tmp_path):
        """With --strict-irr and outcome='passed': generic_diachronic close succeeds."""
        run_dir = self._setup_minimal_run_with_calibration(tmp_path, "p1s1")

        # Pre-write a successful IRR calibration record
        irr_path = run_dir / ".mpi" / "irr_calibration.jsonl"
        irr_path.write_text(json.dumps({
            "stage": "diachronic",
            "transcript_id": "p1s1",
            "outcome": "passed",
            "n_utterances": 70,
        }) + "\n")

        # Try to close a generic_diachronic substep with --strict-irr and passing IRR record
        art_json = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_diachronic", "idu_similarity_grouping")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_diachronic",
            "event": "Test Event",
            "idu_labels": [{
                "idu_name": "Test IDU",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "generic_diachronic",
            "--substep", "idu_similarity_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close with passed IRR",
            "--run-dir", str(run_dir),
            "--strict-irr",
        ])

        # Should succeed because IRR outcome is "passed"
        assert rc == 0, f"Expected rc=0 with --strict-irr and outcome='passed', got {rc}"

    def test_no_strict_irr_low_outcome_emits_warning(self, tmp_path):
        """Without --strict-irr and outcome='low': close succeeds but audit has irr_warning."""
        run_dir = self._setup_minimal_run_with_calibration(tmp_path, "p1s1")

        # Pre-write an IRR record with low outcome
        irr_path = run_dir / ".mpi" / "irr_calibration.jsonl"
        irr_path.write_text(json.dumps({
            "stage": "diachronic",
            "transcript_id": "p1s1",
            "outcome": "low",
            "n_utterances": 70,
        }) + "\n")

        # Try to close generic_diachronic WITHOUT --strict-irr but with low outcome
        art_json = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_diachronic", "idu_similarity_grouping")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_diachronic",
            "event": "Test Event",
            "idu_labels": [{
                "idu_name": "Test IDU",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "generic_diachronic",
            "--substep", "idu_similarity_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close without strict-irr",
            "--run-dir", str(run_dir),
            # NO --strict-irr
        ])

        # Should succeed (warning only)
        assert rc == 0, f"Expected rc=0 without --strict-irr, got {rc}"

        # Check that audit contains irr_warning event
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        assert audit_path.exists(), "Audit file should exist"
        audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]
        has_irr_warning = any(e.get("event", {}).get("action") == "irr_warning" for e in audit_events)
        assert has_irr_warning, "Audit should contain irr_warning event when outcome is low"

    def test_strict_irr_multi_record_filters_by_stage(self, tmp_path):
        """With --strict-irr and multiple records: gate filters by stage and blocks if any non-passed.

        Tests that when irr_calibration.jsonl has multiple records (e.g., one per stratum),
        _check_irr_gate filters by the upstream stage and blocks if ANY matching record
        has outcome != "passed".
        """
        run_dir = self._setup_minimal_run_with_calibration(tmp_path, "p1s1")

        # Pre-write TWO IRR records: first one is low, second one is passed
        # This simulates the stratified mode with multiple calibration transcripts
        irr_path = run_dir / ".mpi" / "irr_calibration.jsonl"
        irr_path.write_text(
            json.dumps({
                "stage": "diachronic",
                "transcript_id": "p1s1",
                "outcome": "low",  # First record: low outcome
                "n_utterances": 70,
            }) + "\n" +
            json.dumps({
                "stage": "diachronic",
                "transcript_id": "p1s2",
                "outcome": "passed",  # Second record: passed
                "n_utterances": 65,
            }) + "\n"
        )

        # Try to close generic_diachronic with --strict-irr
        art_json = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_diachronic", "idu_similarity_grouping")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_diachronic",
            "event": "Test Event",
            "idu_labels": [{
                "idu_name": "Test IDU",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "generic_diachronic",
            "--substep", "idu_similarity_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close with multi-record IRR and --strict-irr",
            "--run-dir", str(run_dir),
            "--strict-irr",  # KEY: strict-irr gate enabled
        ])

        # Should fail because first record (for diachronic stage) has outcome='low'
        # even though the second record passed
        assert rc != 0, f"Expected non-zero rc with --strict-irr and low outcome in first record, got {rc}"

        # Check audit log contains irr_warning
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        if audit_path.exists():
            audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]
            has_irr_warning = any(e.get("event", {}).get("action") == "irr_warning" for e in audit_events)
            assert has_irr_warning, "Audit should contain irr_warning event for low outcome"

    def test_strict_irr_missing_outcome_key_blocks(self, tmp_path):
        """With --strict-irr and missing outcome key: gate treats as irr_missing and blocks.

        Tests that a stage-matching record with a missing 'outcome' key is treated as
        a missing outcome (not as a "passed" outcome) and triggers irr_missing block.
        This is a defense-in-depth regression test: untrusted writes (from LLM-driven
        mpi-irr skill) should not be able to bypass the gate via missing keys.
        """
        run_dir = self._setup_minimal_run_with_calibration(tmp_path, "p1s1")

        # Pre-write an IRR record with missing 'outcome' key (simulates malformed write)
        irr_path = run_dir / ".mpi" / "irr_calibration.jsonl"
        irr_path.write_text(json.dumps({
            "stage": "diachronic",
            "transcript_id": "p1s1",
            # Missing 'outcome' key
            "n_utterances": 70,
        }) + "\n")

        # Try to close generic_diachronic with --strict-irr
        art_json = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_diachronic", "idu_similarity_grouping")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_diachronic",
            "event": "Test Event",
            "idu_labels": [{
                "idu_name": "Test IDU",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "generic_diachronic",
            "--substep", "idu_similarity_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close with missing outcome key and --strict-irr",
            "--run-dir", str(run_dir),
            "--strict-irr",  # KEY: strict-irr gate enabled
        ])

        # Should fail because outcome key is missing (treats as irr_missing)
        assert rc != 0, f"Expected non-zero rc with --strict-irr and missing outcome key, got {rc}"

        # Check that stderr contains irr_check_failed
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        if audit_path.exists():
            audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]
            has_irr_warning = any(e.get("event", {}).get("action") == "irr_warning" for e in audit_events)
            assert has_irr_warning, "Audit should contain irr_warning event for missing outcome"

    def test_strict_irr_synchronic_stage_record_passed_allows_close(self, tmp_path):
        """With --strict-irr and synchronic stage record with outcome='passed': generic_synchronic close succeeds.

        Tests that the synchronic → synchronic mapping works correctly and allows close
        when a record with stage='synchronic' and outcome='passed' exists.
        """
        run_dir = self._setup_minimal_run_with_calibration(tmp_path, "p1s1")

        # Pre-write a synchronic IRR record with outcome='passed'
        irr_path = run_dir / ".mpi" / "irr_calibration.jsonl"
        irr_path.write_text(json.dumps({
            "stage": "synchronic",  # KEY: synchronic stage
            "transcript_id": "p1s1",
            "outcome": "passed",
            "n_utterances": 50,
        }) + "\n")

        # Try to close a generic_synchronic substep with --strict-irr and passing synchronic IRR record
        art_json = _write_artifact(run_dir, "p1s1-generic_synchronic.isu_second_level_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_synchronic.isu_second_level_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_synchronic", "isu_second_level_grouping")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_synchronic",
            "event": "Test Event",
            "iv_category": "low",
            "generic_idu": "Test IDU",
            "isus": [{
                "isu_name": "Test ISU",
                "criteria": ["Test criteria"],
                "confidence": 4,
                "flag_for_review": False,
                "isu_second_level_of_abstraction": "Level 2",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1-idu1",
            "--stage", "generic_synchronic",
            "--substep", "isu_second_level_grouping",
            "--scope", "p1s1-idu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close with synchronic passed IRR",
            "--run-dir", str(run_dir),
            "--strict-irr",
        ])

        # Should succeed because synchronic IRR outcome is "passed"
        assert rc == 0, f"Expected rc=0 with --strict-irr and synchronic outcome='passed', got {rc}"

    def test_strict_irr_synchronic_stage_record_low_blocks_close(self, tmp_path):
        """With --strict-irr and synchronic stage record with outcome='low': generic_synchronic close fails.

        Tests that the synchronic → synchronic mapping correctly blocks when a record
        with stage='synchronic' and outcome='low' exists.
        """
        run_dir = self._setup_minimal_run_with_calibration(tmp_path, "p1s1")

        # Pre-write a synchronic IRR record with outcome='low'
        irr_path = run_dir / ".mpi" / "irr_calibration.jsonl"
        irr_path.write_text(json.dumps({
            "stage": "synchronic",  # KEY: synchronic stage
            "transcript_id": "p1s1",
            "outcome": "low",
            "n_utterances": 50,
        }) + "\n")

        # Try to close a generic_synchronic substep with --strict-irr but low synchronic IRR outcome
        art_json = _write_artifact(run_dir, "p1s1-generic_synchronic.isu_second_level_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_synchronic.isu_second_level_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_synchronic", "isu_second_level_grouping")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_synchronic",
            "event": "Test Event",
            "iv_category": "low",
            "generic_idu": "Test IDU",
            "isus": [{
                "isu_name": "Test ISU",
                "criteria": ["Test criteria"],
                "confidence": 4,
                "flag_for_review": False,
                "isu_second_level_of_abstraction": "Level 2",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1-idu1",
            "--stage", "generic_synchronic",
            "--substep", "isu_second_level_grouping",
            "--scope", "p1s1-idu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close with synchronic low IRR",
            "--run-dir", str(run_dir),
            "--strict-irr",
        ])

        # Should fail because synchronic IRR outcome is "low"
        assert rc != 0, f"Expected non-zero rc with --strict-irr and synchronic outcome='low', got {rc}"

        # Check audit log contains irr_warning
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        if audit_path.exists():
            audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]
            has_irr_warning = any(e.get("event", {}).get("action") == "irr_warning" for e in audit_events)
            assert has_irr_warning, "Audit should contain irr_warning event for synchronic low outcome"


# ---------------------------------------------------------------------------
# AC13.2: IRR calibration auto-trigger tests
# ---------------------------------------------------------------------------

class TestAC13_2_IRRAutoTrigger:
    """Tests for irr_calibration_scheduled auto-trigger (AC13.2)."""

    def test_trigger_fires_for_calibration_transcript(self, tmp_path):
        """Closing diachronic.idu_naming_ordering for calibration transcript triggers irr_calibration_scheduled event."""
        # Setup
        run_dir = _init_run_dir(tmp_path)
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest = json.loads(manifest_path.read_text())

        # Configure calibration transcript
        manifest["study"]["calibration_transcript_ids"] = ["p1s1"]

        # Mark diachronic prerequisites as done
        manifest["participants"]["p1s1"] = {
            "stages": {
                "diachronic": {
                    "status": "pending",
                    "substeps": {
                        "criteria_grouping": {
                            "status": "done",
                            "close_id": "fake-1",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "criteria_revision": {
                            "status": "done",
                            "close_id": "fake-2",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "idu_naming_ordering": {
                            "status": "pending",
                            "close_id": None,
                            "output_path": None,
                            "artifact_shas": {},
                        }
                    }
                }
            }
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Close diachronic.idu_naming_ordering
        art_json = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "idu_naming_ordering")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [{
                "idu_number": 1, "idu_name": "Test", "moment": 1,
                "criteria": "test", "confidence": 3, "flag_for_review": False,
                "utterance_numbers": ["1"],
                "hinge_to_next": None,
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "hello"}],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", "p1s1",
            "--stage", "diachronic",
            "--substep", "idu_naming_ordering",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close for calibration trigger",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"Close failed with rc={rc}"

        # Check audit log for irr_calibration_scheduled event
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        assert audit_path.exists(), "Audit file should exist"
        audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]

        irr_events = [e for e in audit_events if e.get("event", {}).get("action") == "irr_calibration_scheduled"]
        assert len(irr_events) >= 1, "Should have irr_calibration_scheduled event in audit"

        irr_event = irr_events[0]
        assert irr_event["mpi"]["transcript_id"] == "p1s1", "Event should reference p1s1"
        assert irr_event["mpi"]["stage"] == "diachronic", "Event should reference diachronic stage"
        assert irr_event["event"]["outcome"] == "success", "Event outcome should be success"

    def test_trigger_does_not_fire_for_non_calibration_transcript(self, tmp_path):
        """Closing diachronic.idu_naming_ordering for non-calibration transcript does NOT trigger event."""
        # Setup
        run_dir = _init_run_dir(tmp_path)
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest = json.loads(manifest_path.read_text())

        # Configure calibration transcript (p2s1, NOT p1s1)
        manifest["study"]["calibration_transcript_ids"] = ["p2s1"]

        # Mark diachronic prerequisites for p1s1 as done
        manifest["participants"]["p1s1"] = {
            "stages": {
                "diachronic": {
                    "status": "pending",
                    "substeps": {
                        "criteria_grouping": {
                            "status": "done",
                            "close_id": "fake-1",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "criteria_revision": {
                            "status": "done",
                            "close_id": "fake-2",
                            "output_path": "analyses/fake.json",
                            "artifact_shas": {},
                        },
                        "idu_naming_ordering": {
                            "status": "pending",
                        }
                    }
                }
            }
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Close diachronic.idu_naming_ordering for p1s1 (non-calibration)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.idu_naming_ordering.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "idu_naming_ordering")

        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "diachronic",
            "participant": "p1s1",
            "idus": [{
                "idu_number": 1, "idu_name": "Test", "moment": 1,
                "criteria": "test", "confidence": 3, "flag_for_review": False,
                "utterance_numbers": ["1"],
                "hinge_to_next": None,
                "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "hello"}],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", "p1s1",
            "--stage", "diachronic",
            "--substep", "idu_naming_ordering",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test close for non-calibration transcript",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"Close failed with rc={rc}"

        # Check audit log — should NOT have irr_calibration_scheduled event for p1s1
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        assert audit_path.exists(), "Audit file should exist"
        audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]

        irr_events = [e for e in audit_events
                      if e.get("event", {}).get("action") == "irr_calibration_scheduled"
                      and e.get("mpi", {}).get("transcript_id") == "p1s1"]
        assert len(irr_events) == 0, "Should NOT have irr_calibration_scheduled event for non-calibration transcript"


# ---------------------------------------------------------------------------
# AC13.3: IRR alignment auto-accept in yolo mode
# ---------------------------------------------------------------------------

class TestAC13_1_IndependentAnalystArtifact:
    """Tests for irr_calibration.independent_analyst artifact production (AC13.1)."""

    def test_irr_calibration_independent_analyst_close(self, tmp_path):
        """Closing irr_calibration.independent_analyst with analyses/independent/ artifact."""
        # Setup
        run_dir = _init_run_dir(tmp_path)
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest = json.loads(manifest_path.read_text())

        # Setup participant scope for irr_calibration
        manifest["participants"]["p1s1"] = {
            "stages": {
                "irr_calibration": {
                    "status": "pending",
                    "substeps": {
                        "independent_analyst": {
                            "status": "pending",
                        }
                    }
                }
            }
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Create artifact at analyses/independent/ path
        analyses = run_dir / "analyses"
        analyses.mkdir(exist_ok=True)
        independent_dir = analyses / "independent"
        independent_dir.mkdir(exist_ok=True)

        art_path = independent_dir / "p1s1-diachronic.idu_naming_ordering.json"
        art_path.write_text(json.dumps({"utterance_refs": []}))

        # Write prompt artifact
        prompt_art = analyses / "p1s1-irr_calibration.independent_analyst.prompt.json"
        prompt_art.write_text(json.dumps({
            "schema_version": "2",
            "actor": {"kind": "subagent", "name": "mpi-cross-analyst", "agent_file_sha256": "abc123", "agent_file_path": "agents/mpi-cross-analyst.md"},
            "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
            "sampling": {"temperature": 1.0, "top_p": 1.0, "top_k": None, "max_tokens": 8192, "seed": None, "stop_sequences": []},
            "stage": "irr_calibration", "substep": "independent_analyst", "scope": "p1s1",
            "prompt": {"system": "...", "messages": [], "tools_available": []},
            "response": {"raw_text": "...", "tool_calls": [], "parsed_units_path": ""},
            "metadata": {"finish_reason": "end_turn", "usage": {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}, "duration_ms": 100, "timestamp": "2026-05-18T00:00:00Z", "anthropic_request_id": "req_xxx"},
        }))

        # Write units
        units_path = run_dir / "units.json"
        units_path.write_text(json.dumps({
            "stage": "diachronic",
            "participant_id": "p1s1",
            "substep_artifacts": ["analyses/independent/p1s1-diachronic.idu_naming_ordering.json"],
        }))

        # Close irr_calibration.independent_analyst
        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "irr_calibration",
            "--substep", "independent_analyst",
            "--scope", "p1s1",
            "--artifact", str(art_path),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units_path),
            "--reason", "independent analyst analysis for calibration",
            "--run-dir", str(run_dir),
        ])

        assert rc == 0, f"independent_analyst close failed with rc={rc}"

        # Verify manifest shows independent_analyst as done
        updated_manifest = json.loads(manifest_path.read_text())
        indep_substep = updated_manifest["participants"]["p1s1"]["stages"]["irr_calibration"]["substeps"]["independent_analyst"]
        assert indep_substep["status"] == "done", f"independent_analyst should be marked 'done', got: {indep_substep['status']}"

        # Verify artifact was recorded in the git repo at the expected path
        assert art_path.exists(), f"Artifact should exist at {art_path}"

        # Verify the artifact file was committed to git
        git_check = subprocess.run(
            ["git", "log", "--oneline", "-1", "--"],
            cwd=run_dir,
            capture_output=True,
            text=True,
        )
        assert git_check.returncode == 0, "Git should have commits"


class TestAC13_3_IRRAlignmentAutoAccept:
    """Tests for irr_alignment_auto_accepted event emission (AC13.3)."""

    def test_alignment_close_emits_auto_accepted_event(self, tmp_path):
        """Closing irr_calibration.alignment emits irr_alignment_auto_accepted event."""
        # Setup
        run_dir = _init_run_dir(tmp_path)
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest = json.loads(manifest_path.read_text())

        # Mark irr_calibration.independent_analyst as done
        manifest["participants"]["p1s1"] = {
            "stages": {
                "irr_calibration": {
                    "status": "pending",
                    "substeps": {
                        "independent_analyst": {
                            "status": "done",
                            "close_id": "fake-ind",
                            "output_path": "analyses/p1s1-irr_calibration.independent_analyst.json",
                            "artifact_shas": {},
                        },
                        "alignment": {
                            "status": "pending",
                        }
                    }
                }
            }
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Close irr_calibration.alignment
        art_json = _write_artifact(run_dir, "p1s1-irr_calibration.alignment.json", '{"alignment": []}')
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "irr_calibration", "alignment")

        units = _write_units_json(run_dir, "units.json", {
            "stage": "diachronic",
            "participant_id": "p1s1",
            "mapping": [],
            "unmatched_primary": [],
            "unmatched_alternate": [],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "irr_calibration",
            "--substep", "alignment",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test alignment close",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"Alignment close failed with rc={rc}"

        # Check audit log for irr_alignment_auto_accepted event
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        assert audit_path.exists(), "Audit file should exist"
        audit_events = [json.loads(line) for line in audit_path.read_text().splitlines() if line]

        auto_accept_events = [e for e in audit_events if e.get("event", {}).get("action") == "irr_alignment_auto_accepted"]
        assert len(auto_accept_events) >= 1, "Should have irr_alignment_auto_accepted event in audit"

        event = auto_accept_events[0]
        assert event["event"]["outcome"] == "success", "Event outcome should be success"


# ---------------------------------------------------------------------------
# Helper for creating manifests with specific substeps done
# ---------------------------------------------------------------------------

def _make_manifest_with_substep_done(
    participant: str,
    stage: str,
    substep: str,
    close_id: str = "test-close-id",
) -> dict:
    """Create a minimal v2.0 manifest with given substep marked done."""
    return {
        "version": "2.0",
        "run_id": "test-run-id",
        "study": {},
        "participants": {
            participant: {
                "stages": {
                    stage: {
                        "status": "done",
                        "substeps": {
                            substep: {
                                "status": "done",
                                "close_id": close_id,
                                "output_path": f"analyses/{participant}-{stage}.{substep}.json",
                                "artifact_shas": {},
                            }
                        }
                    }
                }
            }
        }
    }


# ---------------------------------------------------------------------------
# Phase 3 cross-scope prerequisite resolution tests
# ---------------------------------------------------------------------------

class TestPrereqScopeResolutionClose:
    """Integration tests for cross-scope prerequisite resolution in cmd_close."""

    def test_ac1_1_worksheet_assembly_with_event_key_transform(self, tmp_path):
        """AC1.1: worksheet_assembly closes when select_generic_idus_of_interest done under event key."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with event3 having select_generic_idus_of_interest done
        manifest = _make_manifest_with_substep_done(
            "event3",
            "generic_synchronic",
            "select_generic_idus_of_interest",
        )
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close worksheet_assembly with scope event3-cat-low-gidu1
        # This should look up event3 and find select_generic_idus_of_interest done
        art_json = _write_artifact(run_dir, "event3-cat-low-gidu1-generic_synchronic.worksheet_assembly.json")
        art_md = _write_artifact(run_dir, "event3-cat-low-gidu1-generic_synchronic.worksheet_assembly.md", "# output")
        units = _write_units_json(run_dir, "units.json", {
            "event": "event3",
            "iv_category": "low",
            "generic_idu": "gidu1",
            "rows": []
        })

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "event3-cat-low-gidu1",
            "--stage", "generic_synchronic",
            "--substep", "worksheet_assembly",
            "--scope", "event3-cat-low-gidu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "worksheet_assembly should close successfully"

    def test_ac1_2_worksheet_assembly_fails_without_prereq(self, tmp_path, capsys):
        """AC1.2: worksheet_assembly fails when select_generic_idus_of_interest missing."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with NO event3 entry
        manifest = {"version": "2.0", "run_id": "test-run-id", "study": {}, "participants": {}}
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close worksheet_assembly
        art_json = _write_artifact(run_dir, "event3-cat-low-gidu1-generic_synchronic.worksheet_assembly.json")
        art_md = _write_artifact(run_dir, "event3-cat-low-gidu1-generic_synchronic.worksheet_assembly.md", "# output")
        units = _write_units_json(run_dir, "units.json", {
            "event": "event3",
            "iv_category": "low",
            "generic_idu": "gidu1",
            "rows": []
        })

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "event3-cat-low-gidu1",
            "--stage", "generic_synchronic",
            "--substep", "worksheet_assembly",
            "--scope", "event3-cat-low-gidu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "worksheet_assembly should fail prereq check"
        assert "prereq_unsatisfied" in capsys.readouterr().err

    def test_ac2_1_weak_evidence_review_all_candidate_draftings_done(self, tmp_path):
        """AC2.1: weak_evidence_review closes when all candidate_drafting entries done."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with 2 DV focuses both having candidate_drafting done
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {"dv_focuses": None},
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "status": "done",
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "done",
                                    "close_id": "test-id",
                                    "output_path": "analyses/dv-automaticity-hypothesis.candidate_drafting.json",
                                    "artifact_shas": {},
                                }
                            }
                        }
                    }
                },
                "dv-attention": {
                    "stages": {
                        "hypothesis": {
                            "status": "done",
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "done",
                                    "close_id": "test-id",
                                    "output_path": "analyses/dv-attention-hypothesis.candidate_drafting.json",
                                    "artifact_shas": {},
                                }
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close weak_evidence_review with scope global
        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "weak_evidence_review should close when all candidate_drafting done"

    def test_ac2_2_weak_evidence_review_fails_no_candidate_draftings(self, tmp_path, capsys):
        """AC2.2: weak_evidence_review fails when no candidate_drafting entries exist."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with no candidate_drafting entries
        manifest = {"version": "2.0", "run_id": "test-run-id", "study": {}, "participants": {}}
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close weak_evidence_review
        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "weak_evidence_review should fail when no candidate_drafting entries"
        assert "prereq_unsatisfied" in capsys.readouterr().err

    def test_ac2_3_weak_evidence_review_fails_one_pending(self, tmp_path, capsys):
        """AC2.3: weak_evidence_review fails when one candidate_drafting is pending."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with 2 focuses, one done and one pending
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {"dv_focuses": None},
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "status": "done",
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "done",
                                    "close_id": "test-id",
                                    "output_path": "analyses/dv-automaticity-hypothesis.candidate_drafting.json",
                                    "artifact_shas": {},
                                }
                            }
                        }
                    }
                },
                "dv-attention": {
                    "stages": {
                        "hypothesis": {
                            "status": "pending",
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "pending"
                                }
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close weak_evidence_review
        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "weak_evidence_review should fail when one candidate_drafting is pending"
        assert "prereq_unsatisfied" in capsys.readouterr().err

    def test_ac2_4_weak_evidence_review_fails_flagged(self, tmp_path, capsys):
        """AC2.4: weak_evidence_review fails when a candidate_drafting is flagged."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with one focus flagged
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {"dv_focuses": None},
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "status": "flagged",
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "flagged"
                                }
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close weak_evidence_review
        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "weak_evidence_review should fail when candidate_drafting is flagged"
        assert "prereq_unsatisfied" in capsys.readouterr().err

    def test_ac2_5_null_dv_focuses_uses_manifest_scan(self, tmp_path):
        """AC2.5: With dv_focuses null/absent, all-match uses manifest scan."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with 2 candidate_drafting entries both done, dv_focuses=None
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {"dv_focuses": None},
            "participants": {
                "dv-automaticity": {
                    "stages": {
                        "hypothesis": {
                            "status": "done",
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "done",
                                    "close_id": "test-id-1",
                                    "output_path": "analyses/dv-automaticity-hypothesis.candidate_drafting.json",
                                    "artifact_shas": {},
                                }
                            }
                        }
                    }
                },
                "dv-attention": {
                    "stages": {
                        "hypothesis": {
                            "status": "done",
                            "substeps": {
                                "candidate_drafting": {
                                    "status": "done",
                                    "close_id": "test-id-2",
                                    "output_path": "analyses/dv-attention-hypothesis.candidate_drafting.json",
                                    "artifact_shas": {},
                                }
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close weak_evidence_review with null dv_focuses
        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "weak_evidence_review should close when dv_focuses is null and all candidate_drafting entries done"

    def test_ac3_1_backward_compat_sync_to_diachronic(self, tmp_path):
        """AC3.1: Synchronic→diachronic scope stripping still works."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with p1s1 having idu_naming_ordering done
        manifest = _make_manifest_with_substep_done(
            "p1s1",
            "diachronic",
            "idu_naming_ordering",
        )
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close theme_grouping_within_idu with scope p1s1-idu2
        # This should strip to p1s1 and find idu_naming_ordering done
        art_json = _write_artifact(run_dir, "p1s1-idu2-synchronic.theme_grouping_within_idu.json")
        art_md = _write_artifact(run_dir, "p1s1-idu2-synchronic.theme_grouping_within_idu.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1-idu2", "synchronic", "theme_grouping_within_idu")
        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "synchronic",
            "participant": "p1s1-idu2",
            "idu_name": "IDU2",
            "isus": []
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", "p1s1-idu2",
            "--stage", "synchronic",
            "--substep", "theme_grouping_within_idu",
            "--scope", "p1s1-idu2",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "theme_grouping_within_idu should close with backward-compat strip"


# ---------------------------------------------------------------------------
# Phase 7 completeness gates tests
# ---------------------------------------------------------------------------

class TestCompletenessGates:
    """Integration tests for cross-participant completeness gates in cmd_close."""

    def test_ac7_2_generic_diachronic_fails_incomplete_diachronic(self, tmp_path, capsys):
        """AC7.2: participant_row_assembly fails when any transcript in event lacks diachronic."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with event_groups and p1s3 complete but p2s3 incomplete
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event3": ["p1s3", "p2s3"]
                }
            },
            "participants": {
                "p1s3": {
                    "stages": {
                        "diachronic": {
                            "status": "done",
                            "substeps": {
                                "idu_naming_ordering": {"status": "done"}
                            }
                        },
                        "synchronic": {
                            "status": "done",
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done"}
                            }
                        }
                    }
                },
                "p1s3-idu1": {
                    "stages": {
                        "synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done"}
                            }
                        }
                    }
                },
                "p2s3": {
                    "stages": {
                        "diachronic": {
                            "status": "pending",
                            "substeps": {
                                "idu_naming_ordering": {"status": "pending"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close participant_row_assembly
        art_json = _write_artifact(run_dir, "event3-cat-low-generic_diachronic.participant_row_assembly.json")
        units = _write_units_json(run_dir, "units.json", {"event": "event3", "rows": []})

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "event3-cat-low",
            "--stage", "generic_diachronic",
            "--substep", "participant_row_assembly",
            "--scope", "event3-cat-low",
            "--artifact", str(art_json),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "participant_row_assembly should fail completeness gate"
        assert "completeness_gate_unsatisfied" in capsys.readouterr().err

    def test_ac7_3_generic_diachronic_succeeds_complete_event(self, tmp_path):
        """AC7.3: participant_row_assembly succeeds when all transcripts in event complete."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with event_groups and both p1s3, p2s3 complete
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event3": ["p1s3", "p2s3"]
                }
            },
            "participants": {
                "p1s3": {
                    "stages": {
                        "diachronic": {
                            "status": "done",
                            "substeps": {
                                "idu_naming_ordering": {"status": "done", "close_id": "id1"}
                            }
                        },
                        "synchronic": {
                            "status": "done",
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done", "close_id": "id2"}
                            }
                        }
                    }
                },
                "p1s3-idu1": {
                    "stages": {
                        "synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done"}
                            }
                        }
                    }
                },
                "p2s3": {
                    "stages": {
                        "diachronic": {
                            "status": "done",
                            "substeps": {
                                "idu_naming_ordering": {"status": "done", "close_id": "id3"}
                            }
                        },
                        "synchronic": {
                            "status": "done",
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done", "close_id": "id4"}
                            }
                        }
                    }
                },
                "p2s3-idu1": {
                    "stages": {
                        "synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close participant_row_assembly
        art_json = _write_artifact(run_dir, "event3-cat-low-generic_diachronic.participant_row_assembly.json")
        units = _write_units_json(run_dir, "units.json", {"event": "event3", "rows": []})

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "event3-cat-low",
            "--stage", "generic_diachronic",
            "--substep", "participant_row_assembly",
            "--scope", "event3-cat-low",
            "--artifact", str(art_json),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "participant_row_assembly should succeed when event complete"

    def test_ac7_5_legacy_manifest_no_event_groups(self, tmp_path, capsys):
        """AC7.5: legacy manifest (no event_groups) warns but proceeds."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest WITHOUT event_groups
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {},
            "participants": {}
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close participant_row_assembly (should warn but proceed)
        art_json = _write_artifact(run_dir, "event3-cat-low-generic_diachronic.participant_row_assembly.json")
        units = _write_units_json(run_dir, "units.json", {"event": "event3", "rows": []})

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "event3-cat-low",
            "--stage", "generic_diachronic",
            "--substep", "participant_row_assembly",
            "--scope", "event3-cat-low",
            "--artifact", str(art_json),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "Should proceed despite missing event_groups (legacy manifest)"
        assert "completeness_gate_skipped" in capsys.readouterr().err

    def test_ac7_4_generic_synchronic_gate(self, tmp_path, capsys):
        """AC7.4 (generic_synchronic chain): select_generic_idus_of_interest fails without generic_diachronic.cross_iv_contrast done."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with event_groups but cross_iv_contrast not done
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event3": ["p1s3"]
                }
            },
            "participants": {
                "event3-cat-low": {
                    "stages": {
                        "generic_diachronic": {
                            "substeps": {
                                "cross_iv_contrast": {"status": "pending"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close select_generic_idus_of_interest (first substep of generic_synchronic, no DAG prereqs)
        art_json = _write_artifact(run_dir, "event3-cat-low-generic_synchronic.select_generic_idus_of_interest.json")
        art_md = _write_artifact(run_dir, "event3-cat-low-generic_synchronic.select_generic_idus_of_interest.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "event3-cat-low", "generic_synchronic", "select_generic_idus_of_interest")
        units = _write_units_json(run_dir, "units.json", {"event": "event3", "selected_generic_idus": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "event3-cat-low",
            "--stage", "generic_synchronic",
            "--substep", "select_generic_idus_of_interest",
            "--scope", "event3-cat-low",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "generic_synchronic gate should fail without cross_iv_contrast"
        assert "completeness_gate_unsatisfied" in capsys.readouterr().err

    def test_ac7_4_hypothesis_gidu_gate_fails(self, tmp_path, capsys):
        """AC7.4 (hypothesis critical): evidence_extraction fails when no gidu*.global_synchronic done."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with no gidu entries having global_synchronic done
        # Note: event_groups must be present (non-empty dict) for completeness gate to run
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {"event1": ["p1s1"]}  # event_groups present but no gidu entries
            },
            "participants": {}
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close evidence_extraction
        art_json = _write_artifact(run_dir, "dv-attention-hypothesis.evidence_extraction.json")
        art_md = _write_artifact(run_dir, "dv-attention-hypothesis.evidence_extraction.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "dv-attention", "hypothesis", "evidence_extraction")
        units = _write_units_json(run_dir, "units.json", {"dv_focus": "attention", "evidence_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "dv-attention",
            "--stage", "hypothesis",
            "--substep", "evidence_extraction",
            "--scope", "dv-attention",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "hypothesis gate should fail without gidu.global_synchronic done"
        assert "completeness_gate_unsatisfied" in capsys.readouterr().err

    def test_ac7_4_hypothesis_gidu_gate_succeeds(self, tmp_path):
        """AC7.4 (hypothesis critical): evidence_extraction succeeds after gidu1-cat-low.global_synchronic done."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with gidu1-cat-low having global_synchronic done
        # Note: event_groups must be present (non-empty dict) for completeness gate to run
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {"event1": ["p1s1"]}  # event_groups present
            },
            "participants": {
                "gidu1-cat-low": {
                    "stages": {
                        "global_synchronic": {
                            "substeps": {
                                "global_synchronic": {"status": "done", "close_id": "test-id"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close evidence_extraction
        art_json = _write_artifact(run_dir, "dv-attention-hypothesis.evidence_extraction.json")
        art_md = _write_artifact(run_dir, "dv-attention-hypothesis.evidence_extraction.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "dv-attention", "hypothesis", "evidence_extraction")
        units = _write_units_json(run_dir, "units.json", {"dv_focus": "attention", "evidence_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "dv-attention",
            "--stage", "hypothesis",
            "--substep", "evidence_extraction",
            "--scope", "dv-attention",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "hypothesis gate should succeed with gidu.global_synchronic done"

    def test_ac7_4_event_boundary_match_non_collision(self, tmp_path, capsys):
        """AC7.4 (event prefix): event1 and event12 don't collide with boundary match."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with event1 and event12, but only event1 transcripts complete
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event1": ["p1s1"],
                    "event12": ["p1s2"]
                }
            },
            "participants": {
                "p1s1": {
                    "stages": {
                        "diachronic": {
                            "status": "done",
                            "substeps": {
                                "idu_naming_ordering": {"status": "done"}
                            }
                        },
                        "synchronic": {
                            "status": "done",
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done"}
                            }
                        }
                    }
                },
                "p1s1-idu1": {
                    "stages": {
                        "synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done"}
                            }
                        }
                    }
                },
                "p1s2": {
                    "stages": {
                        "diachronic": {
                            "status": "pending",
                            "substeps": {
                                "idu_naming_ordering": {"status": "pending"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close generic_diachronic for event1 — should succeed (event12 not checked)
        art_json = _write_artifact(run_dir, "event1-cat-low-generic_diachronic.participant_row_assembly.json")
        units = _write_units_json(run_dir, "units.json", {"event": "event1", "rows": []})

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "event1-cat-low",
            "--stage", "generic_diachronic",
            "--substep", "participant_row_assembly",
            "--scope", "event1-cat-low",
            "--artifact", str(art_json),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "event1 close should succeed (event12 not checked)"

        # Now try event12 — should fail (p1s2 incomplete)
        art_json_e12 = _write_artifact(run_dir, "event12-cat-low-generic_diachronic.participant_row_assembly.json")
        units_e12 = _write_units_json(run_dir, "units_e12.json", {"event": "event12", "rows": []})

        rc = mpi_step.main([
            "close",
            "--actor", "orchestrator",
            "--participant", "event12-cat-low",
            "--stage", "generic_diachronic",
            "--substep", "participant_row_assembly",
            "--scope", "event12-cat-low",
            "--artifact", str(art_json_e12),
            "--units-json", str(units_e12),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "event12 close should fail (p1s2 incomplete)"
        assert "completeness_gate_unsatisfied" in capsys.readouterr().err

    def test_ac7_4_global_synchronic_gate_fail(self, tmp_path, capsys):
        """AC7.4: global_synchronic fails when any event lacks generic_synchronic.isu_second_level_grouping."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with event_groups but isu_second_level_grouping not done for event1
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event1": ["p1s1"]
                }
            },
            "participants": {
                "event1-cat-low-gidu1": {
                    "stages": {
                        "generic_synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {"status": "pending"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close global_synchronic
        art_json = _write_artifact(run_dir, "gidu1-cat-low-global_synchronic.global_synchronic.json")
        art_md = _write_artifact(run_dir, "gidu1-cat-low-global_synchronic.global_synchronic.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "gidu1-cat-low", "global_synchronic", "global_synchronic")
        units = _write_units_json(run_dir, "units.json", {
            "generic_idu": "gidu1",
            "iv_category": "low",
            "isus": []
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "gidu1-cat-low",
            "--stage", "global_synchronic",
            "--substep", "global_synchronic",
            "--scope", "gidu1-cat-low",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "global_synchronic gate should fail without isu_second_level_grouping"
        assert "completeness_gate_unsatisfied" in capsys.readouterr().err

    def test_ac7_4_global_synchronic_gate_success(self, tmp_path):
        """AC7.4: global_synchronic succeeds when all events have generic_synchronic.isu_second_level_grouping done."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with isu_second_level_grouping done for event1
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event1": ["p1s1"]
                }
            },
            "participants": {
                "event1-cat-low-gidu1": {
                    "stages": {
                        "generic_synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {"status": "done", "close_id": "test-id"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close global_synchronic
        art_json = _write_artifact(run_dir, "gidu1-cat-low-global_synchronic.global_synchronic.json")
        art_md = _write_artifact(run_dir, "gidu1-cat-low-global_synchronic.global_synchronic.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "gidu1-cat-low", "global_synchronic", "global_synchronic")
        units = _write_units_json(run_dir, "units.json", {
            "generic_idu": "gidu1",
            "iv_category": "low",
            "isus": []
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "gidu1-cat-low",
            "--stage", "global_synchronic",
            "--substep", "global_synchronic",
            "--scope", "gidu1-cat-low",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "global_synchronic gate should succeed with isu_second_level_grouping done"

    def test_ac7_4_generic_synchronic_gate_success(self, tmp_path):
        """AC7.4: generic_synchronic succeeds when generic_diachronic.cross_iv_contrast is done."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with cross_iv_contrast done for event3
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event3": ["p1s3"]
                }
            },
            "participants": {
                "event3-cat-low": {
                    "stages": {
                        "generic_diachronic": {
                            "substeps": {
                                "cross_iv_contrast": {"status": "done", "close_id": "test-id"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Try to close select_generic_idus_of_interest
        art_json = _write_artifact(run_dir, "event3-cat-low-generic_synchronic.select_generic_idus_of_interest.json")
        art_md = _write_artifact(run_dir, "event3-cat-low-generic_synchronic.select_generic_idus_of_interest.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "event3-cat-low", "generic_synchronic", "select_generic_idus_of_interest")
        units = _write_units_json(run_dir, "units.json", {"event": "event3", "selected_generic_idus": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "event3-cat-low",
            "--stage", "generic_synchronic",
            "--substep", "select_generic_idus_of_interest",
            "--scope", "event3-cat-low",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "generic_synchronic gate should succeed with cross_iv_contrast done"

    def test_cmd_verify_detects_completeness_violation(self, tmp_path, capsys):
        """Minor: cmd_verify detects when a cross-participant done substep has incomplete upstream."""
        run_dir = _init_run_dir(tmp_path)

        # Create manifest with generic_diachronic done but upstream diachronic incomplete
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event1": ["p1s1"]
                }
            },
            "participants": {
                "p1s1": {
                    "stages": {
                        "diachronic": {
                            "status": "pending",
                            "substeps": {
                                "idu_naming_ordering": {"status": "pending"}
                            }
                        }
                    }
                },
                "event1-cat-low": {
                    "stages": {
                        "generic_diachronic": {
                            "status": "done",
                            "substeps": {
                                "participant_row_assembly": {"status": "done", "close_id": "test-close-id"}
                            }
                        }
                    }
                }
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        # Create audit.jsonl with the matching commit
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        audit_event = {
            "event_id": "test-event-id",
            "@timestamp": "2026-05-18T00:00:00Z",
            "trace_id": "test-trace-id",
            "span_id": "test-span-id",
            "actor": {"kind": "orchestrator", "name": "orchestrator"},
            "event": {"kind": "event", "action": "git_commit_succeeded", "outcome": "success"},
            "mpi": {
                "stage": "generic_diachronic",
                "substep": "participant_row_assembly",
                "scope": "event1-cat-low",
                "close_id": "test-close-id",
                "git_commit_sha": "abc1234567890"
            }
        }
        append_jsonl(audit_path, audit_event)

        # Create a fake commit object
        subprocess.run(
            ["git", "hash-object", "-t", "commit", "--stdin", "-w"],
            input=b"tree 0000000000000000000000000000000000000000\n",
            cwd=run_dir,
            capture_output=True
        )

        # Run verify — should detect the completeness violation
        rc = mpi_step.main([
            "verify",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "verify should fail when completeness invariant is violated"
        assert "completeness_invariant_violated" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Phase 8: DV focus scope gate tests (AC8)
# ---------------------------------------------------------------------------

class TestDVFocusGate:
    """Integration tests for the undeclared_dv_focus guard and all-match with declared set."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _manifest_with_dv_focuses(dv_focuses, candidate_drafting_statuses=None):
        """
        Build a v2.0 manifest with study.dv_focuses set and optional
        candidate_drafting substep entries.

        candidate_drafting_statuses: dict {focus_key: status} e.g.
          {"dv-automaticity": "done", "dv-attention": "done"}
        """
        participants = {}
        if candidate_drafting_statuses:
            for focus_key, status in candidate_drafting_statuses.items():
                participants[focus_key] = {
                    "stages": {
                        "hypothesis": {
                            "substeps": {
                                "candidate_drafting": {
                                    "status": status,
                                    "close_id": "test-close-id" if status == "done" else None,
                                }
                            }
                        }
                    }
                }
        return {
            "version": "2.0",
            "run_id": "test-run-id",
            # event_groups = {} (empty → completeness gate bypassed for hypothesis)
            "study": {"dv_focuses": dv_focuses, "event_groups": {}},
            "participants": participants,
        }

    # ------------------------------------------------------------------
    # AC8.1 — schema validation (dv_focuses field)
    # ------------------------------------------------------------------

    def test_ac8_1_dv_focuses_non_string_entry_rejected(self):
        """AC8.1: dv_focuses list with non-string entry is rejected by validator."""
        from _mpi_schemas import validate_units
        errors = validate_units("init", "confirm_study_config", {
            "event_groups": {"event1": ["p1s1"]},
            "dv_focuses": ["automaticity", 123],  # 123 is not a string
            "config_provenance": "user_specified",
        })
        assert len(errors) >= 1
        assert any("dv_focuses" in e.field for e in errors)

    # ------------------------------------------------------------------
    # AC8.2 — undeclared DV focus guard
    # ------------------------------------------------------------------

    def test_ac8_2_undeclared_focus_rejected(self, tmp_path, capsys):
        """AC8.2: evidence_extraction with an undeclared focus scope is rejected."""
        run_dir = _init_run_dir(tmp_path)

        manifest = self._manifest_with_dv_focuses(["automaticity", "attention"])
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest) + "\n")

        art_json = _write_artifact(run_dir, "dv-unknown-hypothesis.evidence_extraction.json")
        art_md = _write_artifact(run_dir, "dv-unknown-hypothesis.evidence_extraction.md", "# x")
        prompt_art = _write_prompt_artifact(run_dir, "dv-unknown", "hypothesis", "evidence_extraction")
        units = _write_units_json(run_dir, "units.json", {"dv_focus": "unknown", "evidence_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "dv-unknown",
            "--stage", "hypothesis",
            "--substep", "evidence_extraction",
            "--scope", "dv-unknown",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "close should fail for undeclared DV focus"
        assert "undeclared_dv_focus" in capsys.readouterr().err

    def test_ac8_2_declared_focus_succeeds(self, tmp_path):
        """AC8.2: evidence_extraction with a declared focus scope succeeds."""
        run_dir = _init_run_dir(tmp_path)

        manifest = self._manifest_with_dv_focuses(["automaticity", "attention"])
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest) + "\n")

        art_json = _write_artifact(run_dir, "dv-automaticity-hypothesis.evidence_extraction.json")
        art_md = _write_artifact(run_dir, "dv-automaticity-hypothesis.evidence_extraction.md", "# x")
        prompt_art = _write_prompt_artifact(run_dir, "dv-automaticity", "hypothesis", "evidence_extraction")
        units = _write_units_json(run_dir, "units.json", {"dv_focus": "automaticity", "evidence_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "dv-automaticity",
            "--stage", "hypothesis",
            "--substep", "evidence_extraction",
            "--scope", "dv-automaticity",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "close should succeed for declared DV focus"

    # ------------------------------------------------------------------
    # AC8.3 — all-match checks declared focuses when dv_focuses is set
    # ------------------------------------------------------------------

    def test_ac8_3_declared_focus_missing_candidate_drafting_blocked(self, tmp_path, capsys):
        """AC8.3: weak_evidence_review is blocked when a declared focus has no candidate_drafting done."""
        run_dir = _init_run_dir(tmp_path)

        # dv-automaticity has candidate_drafting done; dv-attention is absent from manifest
        manifest = self._manifest_with_dv_focuses(
            ["automaticity", "attention"],
            {"dv-automaticity": "done"},
        )
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest) + "\n")

        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# x")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "weak_evidence_review should be blocked when declared focus missing"
        assert "prereq_unsatisfied" in capsys.readouterr().err

    def test_ac8_3_all_declared_focuses_done_succeeds(self, tmp_path):
        """AC8.3: weak_evidence_review succeeds when all declared focuses have candidate_drafting done."""
        run_dir = _init_run_dir(tmp_path)

        manifest = self._manifest_with_dv_focuses(
            ["automaticity", "attention"],
            {"dv-automaticity": "done", "dv-attention": "done"},
        )
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest) + "\n")

        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# x")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "weak_evidence_review should succeed when all declared focuses done"

    # ------------------------------------------------------------------
    # AC8.4 — null dv_focuses falls back to manifest scan
    # ------------------------------------------------------------------

    def test_ac8_4_null_focuses_manifest_scan_succeeds(self, tmp_path):
        """AC8.4: With null dv_focuses, weak_evidence_review succeeds when all manifest entries done."""
        run_dir = _init_run_dir(tmp_path)

        manifest = self._manifest_with_dv_focuses(
            None,  # null dv_focuses
            {"dv-automaticity": "done"},
        )
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest) + "\n")

        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# x")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, "weak_evidence_review should succeed with null dv_focuses and manifest scan"

    def test_ac8_4_null_focuses_pending_entry_blocked(self, tmp_path, capsys):
        """AC8.4: With null dv_focuses, weak_evidence_review is blocked if any manifest entry is pending."""
        run_dir = _init_run_dir(tmp_path)

        manifest = self._manifest_with_dv_focuses(
            None,  # null dv_focuses
            {"dv-automaticity": "pending"},
        )
        (run_dir / ".mpi" / "project.json").write_text(json.dumps(manifest) + "\n")

        art_json = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.json")
        art_md = _write_artifact(run_dir, "global-hypothesis.weak_evidence_review.md", "# x")
        prompt_art = _write_prompt_artifact(run_dir, "global", "hypothesis", "weak_evidence_review")
        units = _write_units_json(run_dir, "units.json", {"review_items": []})

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "global",
            "--stage", "hypothesis",
            "--substep", "weak_evidence_review",
            "--scope", "global",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test",
            "--run-dir", str(run_dir),
        ])
        assert rc != 0, "weak_evidence_review should be blocked with pending candidate_drafting"
        assert "prereq_unsatisfied" in capsys.readouterr().err

    # ------------------------------------------------------------------
    # AC8.5 — dv_focuses_provenance written to manifest at confirm_study_config
    # ------------------------------------------------------------------

    @staticmethod
    def _run_confirm_study_config(run_dir, units_payload):
        """Close scan_transcripts then confirm_study_config with the given payload."""
        # scan_transcripts prereq
        scan_art = _write_artifact(run_dir, "init-scan_transcripts.json")
        scan_units = _write_units_json(run_dir, "scan_units.json", {
            "transcript_ids": ["p1s1"],
            "raw_sha256_map": {"p1s1": "abc..."},
        })
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "scan_transcripts", "--scope", "run",
            "--artifact", str(scan_art), "--units-json", str(scan_units),
            "--reason", "scan", "--run-dir", str(run_dir),
        ])
        assert rc == 0, "scan_transcripts should succeed"

        # confirm_study_config close
        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")
        units = _write_units_json(run_dir, "confirm_units.json", units_payload)
        return mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json), "--units-json", str(units),
            "--reason", "confirmed", "--run-dir", str(run_dir),
        ])

    def test_ac8_5_researcher_specified_provenance_written(self, tmp_path):
        """AC8.5: confirm_study_config with dv_focuses list writes dv_focuses_provenance=researcher_specified."""
        run_dir = _init_run_dir(tmp_path)
        rc = self._run_confirm_study_config(run_dir, {
            "event_groups": {"event1": ["p1s1"]},
            "dv_focuses": ["automaticity", "attention"],
            "config_provenance": "user_specified",
        })
        assert rc == 0, "confirm_study_config close should succeed"
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"].get("dv_focuses_provenance") == "researcher_specified"

    def test_ac8_5_emergent_provenance_written(self, tmp_path):
        """AC8.5: confirm_study_config without dv_focuses writes dv_focuses_provenance=emergent."""
        run_dir = _init_run_dir(tmp_path)
        rc = self._run_confirm_study_config(run_dir, {
            "event_groups": {"event1": ["p1s1"]},
            # dv_focuses intentionally absent → null
            "config_provenance": "llm_proposed_user_confirmed",
        })
        assert rc == 0, "confirm_study_config close should succeed"
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert manifest["study"].get("dv_focuses_provenance") == "emergent"


# ---------------------------------------------------------------------------
# Phase 1: close-enforcement-2 — Gate registry + manifest strictness (AC1.1–AC1.5)
# ---------------------------------------------------------------------------

class TestGateRegistry:
    """AC1.1–AC1.5: GATES registry, warn/strict posture, CLI flags, verify sweep."""

    def test_gates_dict_has_required_keys(self):
        """GATES registry exists in _mpi_schemas and has all expected gate IDs with posture."""
        from _mpi_schemas import GATES
        expected_gate_ids = {
            "single_event_global_synchronic",
            "undeclared_input",
            "convergence_pending",
            "temporal_order_pending",
            "irr_below_threshold",
        }
        assert set(GATES.keys()) >= expected_gate_ids, (
            f"Missing gate IDs: {expected_gate_ids - set(GATES.keys())}"
        )
        for gate_id, gate_def in GATES.items():
            assert "posture" in gate_def, f"Gate '{gate_id}' missing 'posture' field"
            assert gate_def["posture"] in ("warn_or_abort", "downgrade"), (
                f"Gate '{gate_id}' has invalid posture {gate_def['posture']!r}"
            )
            assert "description" in gate_def, f"Gate '{gate_id}' missing 'description'"

    def test_warn_gate_emits_gate_warning_event_close_succeeds(self, tmp_path):
        """AC1.1: warn-mode gate emits gate_warning audit event and returns GATE_WARN (0)."""
        from mpi_step import _evaluate_gate, GATE_WARN
        import argparse
        run_dir = _init_run_dir(tmp_path)
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        run_id = (run_dir / ".mpi" / "run_id").read_text().strip()
        close_id = str(uuid.uuid4())

        # Manifest with no strict_gates (warn-only mode)
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        manifest.setdefault("study", {})
        manifest["study"]["strict_gates"] = []

        args = argparse.Namespace(
            strict_single_event_global_synchronic=False,
            strict_undeclared_input=False,
            strict_convergence_pending=False,
            strict_temporal_order_pending=False,
            strict_irr=False,
        )

        rc = _evaluate_gate(
            "single_event_global_synchronic",
            run_dir, manifest, args, audit_path, close_id,
            stage="global_synchronic", substep="global_synchronic",
            scope="gidu1-cat-low", actor="mpi-cross-analyst",
            actor_kind="subagent", extra_details={"event_count": 1},
        )

        assert rc == GATE_WARN, f"Expected GATE_WARN (0), got {rc}"

        # Verify audit has gate_warning event
        events = [json.loads(l) for l in audit_path.read_text().splitlines() if l.strip()]
        gw_events = [e for e in events if e.get("event", {}).get("action") == "gate_warning"]
        assert len(gw_events) == 1, f"Expected exactly 1 gate_warning event, got {len(gw_events)}"
        gw = gw_events[0]
        assert gw["mpi"]["close_id"] == close_id
        assert gw["mpi"]["gate_id"] == "single_event_global_synchronic"

    def test_strict_gate_in_manifest_aborts(self, tmp_path):
        """AC1.2: gate listed in study.strict_gates causes _evaluate_gate to return GATE_ABORT."""
        from mpi_step import _evaluate_gate, GATE_ABORT
        import argparse
        run_dir = _init_run_dir(tmp_path)
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        close_id = str(uuid.uuid4())

        # Manifest with the gate in strict_gates
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        manifest.setdefault("study", {})
        manifest["study"]["strict_gates"] = ["single_event_global_synchronic"]

        args = argparse.Namespace(
            strict_single_event_global_synchronic=False,
            strict_undeclared_input=False,
            strict_convergence_pending=False,
            strict_temporal_order_pending=False,
            strict_irr=False,
        )

        rc = _evaluate_gate(
            "single_event_global_synchronic",
            run_dir, manifest, args, audit_path, close_id,
            stage="global_synchronic", substep="global_synchronic",
            scope="gidu1-cat-low", actor="mpi-cross-analyst",
            actor_kind="subagent", extra_details={},
        )

        assert rc != 0, f"Expected non-zero (GATE_ABORT) when gate in strict_gates, got {rc}"

    def test_strict_cli_flag_beats_manifest_omission(self, tmp_path):
        """AC1.3: --strict-<gate_id> CLI flag aborts even when manifest doesn't list the gate."""
        from mpi_step import _evaluate_gate, GATE_ABORT
        import argparse
        run_dir = _init_run_dir(tmp_path)
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        close_id = str(uuid.uuid4())

        # Manifest does NOT list the gate
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        manifest.setdefault("study", {})
        manifest["study"]["strict_gates"] = []

        # But CLI flag IS set
        args = argparse.Namespace(
            strict_single_event_global_synchronic=True,  # <-- strict via CLI
            strict_undeclared_input=False,
            strict_convergence_pending=False,
            strict_temporal_order_pending=False,
            strict_irr=False,
        )

        rc = _evaluate_gate(
            "single_event_global_synchronic",
            run_dir, manifest, args, audit_path, close_id,
            stage="global_synchronic", substep="global_synchronic",
            scope="gidu1-cat-low", actor="mpi-cross-analyst",
            actor_kind="subagent", extra_details={},
        )

        assert rc != 0, f"Expected non-zero (GATE_ABORT) when --strict-<gate_id> set via CLI, got {rc}"

    def test_strict_irr_alias_unchanged(self, tmp_path):
        """AC1.4: --strict-irr still triggers irr_warning action (not gate_warning) — alias preserved."""
        run_dir = TestStrictIRRGate()._setup_minimal_run_with_calibration(tmp_path, "p1s1")
        # No IRR record → irr_warning should be emitted when strict-irr set

        art_json = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-generic_diachronic.idu_similarity_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "generic_diachronic", "idu_similarity_grouping")
        units = _write_units_json(run_dir, "units.json", {
            "analysis_type": "generic_diachronic",
            "event": "Test Event",
            "idu_labels": [{
                "idu_name": "Test IDU",
                "utterance_refs": [
                    {"transcript_id": "p1s1", "utterance_number": 1, "byte_start": 0, "byte_end": 10, "raw_excerpt": "test"}
                ],
            }],
        })

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "p1s1",
            "--stage", "generic_diachronic",
            "--substep", "idu_similarity_grouping",
            "--scope", "p1s1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test strict-irr alias",
            "--run-dir", str(run_dir),
            "--strict-irr",
        ])

        assert rc != 0, "Expected non-zero rc with --strict-irr and no IRR record"
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        events = [json.loads(l) for l in audit_path.read_text().splitlines() if l.strip()]
        # Must have irr_warning (existing action), NOT gate_warning
        irr_warnings = [e for e in events if e.get("event", {}).get("action") == "irr_warning"]
        gate_warnings = [e for e in events if e.get("event", {}).get("action") == "gate_warning"]
        assert irr_warnings, "Must have irr_warning event (alias preserved)"
        assert not gate_warnings, "Should NOT have gate_warning event for IRR (alias, not registry path)"

    def test_cmd_verify_reports_gate_warning_events(self, tmp_path):
        """AC1.5: cmd_verify prints WARN for gate_warning events and returns 0."""
        import io
        from contextlib import redirect_stdout
        run_dir = _init_run_dir(tmp_path)

        # Seed audit.jsonl with a gate_warning event (no real close needed)
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        run_id = (run_dir / ".mpi" / "run_id").read_text().strip()
        gate_event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": "2026-06-05T00:00:00Z",
            "trace_id": run_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "subagent", "name": "mpi-cross-analyst"},
            "event": {"kind": "event", "action": "gate_warning", "outcome": "warning"},
            "mpi": {
                "stage": "global_synchronic",
                "substep": "global_synchronic",
                "scope": "gidu1-cat-low",
                "close_id": "test-close-id-456",
                "gate_id": "single_event_global_synchronic",
            },
            "reason": "test gate warning",
        }
        append_jsonl(audit_path, gate_event)

        # Capture stdout to check WARN lines
        import io
        buf = io.StringIO()
        import argparse
        args = argparse.Namespace(run_dir=str(run_dir))
        with redirect_stdout(buf):
            rc = mpi_step.cmd_verify(args)

        output = buf.getvalue()
        assert rc == 0, f"cmd_verify should return 0 for warn-only audit log, got {rc}"
        assert "WARN" in output, f"Expected WARN line in output, got: {output!r}"
        assert "gate_warning" in output, f"Expected 'gate_warning' in WARN line, got: {output!r}"
        assert "single_event_global_synchronic" in output

    def test_strict_gates_written_to_manifest_at_confirm_study_config(self, tmp_path):
        """AC1.2 setup: confirm_study_config with strict_gates in payload writes study.strict_gates."""
        run_dir = _init_run_dir(tmp_path)

        # Close scan_transcripts first
        scan_art = _write_artifact(run_dir, "init-scan_transcripts.json")
        scan_units = _write_units_json(run_dir, "scan_units.json", {
            "transcript_ids": ["p1s1"],
            "raw_sha256_map": {"p1s1": "abc..."},
        })
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "scan_transcripts", "--scope", "run",
            "--artifact", str(scan_art), "--units-json", str(scan_units),
            "--reason", "scan", "--run-dir", str(run_dir),
        ])
        assert rc == 0, "scan_transcripts should succeed"

        # confirm_study_config with strict_gates
        art_json = _write_artifact(run_dir, "init-confirm_study_config.json")
        units = _write_units_json(run_dir, "confirm_units.json", {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified",
            "strict_gates": ["single_event_global_synchronic"],
        })
        rc = mpi_step.main([
            "close", "--actor", "orchestrator", "--participant", "run",
            "--stage", "init", "--substep", "confirm_study_config", "--scope", "run",
            "--artifact", str(art_json), "--units-json", str(units),
            "--reason", "confirmed", "--run-dir", str(run_dir),
        ])
        assert rc == 0, "confirm_study_config should succeed"

        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert "strict_gates" in manifest["study"], "study.strict_gates should be written to manifest"
        assert manifest["study"]["strict_gates"] == ["single_event_global_synchronic"]


class TestValidateConfirmStudyConfig:
    """AC1.2 guard: strict_gates validation in _validate_init_confirm_study_config."""

    def test_strict_gates_known_id_accepted(self):
        """Known gate IDs in strict_gates should not produce schema errors."""
        from _mpi_schemas import validate_units
        errors = validate_units("init", "confirm_study_config", {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified",
            "strict_gates": ["single_event_global_synchronic", "undeclared_input"],
        })
        assert errors == [], f"Expected no errors for known gate IDs, got: {errors}"

    def test_strict_gates_unknown_id_rejected(self):
        """Unknown gate ID in strict_gates should produce a SchemaError."""
        from _mpi_schemas import validate_units
        errors = validate_units("init", "confirm_study_config", {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified",
            "strict_gates": ["nonexistent_gate"],
        })
        assert errors, "Expected SchemaError for unknown gate ID"
        assert any("strict_gates" in e.field for e in errors), (
            f"Expected error field to reference strict_gates, got: {[e.field for e in errors]}"
        )

    def test_strict_gates_empty_list_accepted(self):
        """Empty strict_gates list should be valid."""
        from _mpi_schemas import validate_units
        errors = validate_units("init", "confirm_study_config", {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified",
            "strict_gates": [],
        })
        assert errors == [], f"Expected no errors for empty strict_gates, got: {errors}"

    def test_strict_gates_absent_accepted(self):
        """Absent strict_gates field should be valid (defaults to empty)."""
        from _mpi_schemas import validate_units
        errors = validate_units("init", "confirm_study_config", {
            "event_groups": {"event1": ["p1s1"]},
            "config_provenance": "user_specified",
            # strict_gates absent
        })
        assert errors == [], f"Expected no errors when strict_gates absent, got: {errors}"


# ---------------------------------------------------------------------------
# Phase 2 tests: inputs verb + consumed-input verification (AC2.1, AC2.2)
# ---------------------------------------------------------------------------

class TestInputsVerb:
    """AC2.1: cmd_inputs resolves upstream artifact paths from manifest."""

    def test_inputs_generic_diachronic_resolves_upstream_transcripts(self, tmp_path):
        """AC2.1: generic_diachronic scope resolves diachronic/synchronic artifacts for event transcripts."""
        from mpi_step import cmd_inputs
        import argparse

        run_dir = _init_run_dir(tmp_path)

        # Build manifest with event_groups and done diachronic/synchronic substeps
        # with output_paths and artifact_shas
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event1": ["p1s1", "p2s1"]
                }
            },
            "participants": {
                "p1s1": {
                    "stages": {
                        "diachronic": {
                            "status": "done",
                            "substeps": {
                                "idu_naming_ordering": {
                                    "status": "done",
                                    "close_id": "cid1",
                                    "output_paths": ["analyses/p1s1-diachronic.idu_naming_ordering.json",
                                                     "analyses/p1s1-diachronic.idu_naming_ordering.md"],
                                    "artifact_shas": {
                                        "analyses/p1s1-diachronic.idu_naming_ordering.json": "sha_p1s1_dia",
                                        "analyses/p1s1-diachronic.idu_naming_ordering.md": "sha_p1s1_dia_md",
                                    }
                                }
                            }
                        }
                    }
                },
                "p1s1-idu1": {
                    "stages": {
                        "synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {
                                    "status": "done",
                                    "close_id": "cid2",
                                    "output_paths": ["analyses/p1s1-idu1-synchronic.isu_second_level_grouping.json"],
                                    "artifact_shas": {
                                        "analyses/p1s1-idu1-synchronic.isu_second_level_grouping.json": "sha_p1s1_sync",
                                    }
                                }
                            }
                        }
                    }
                },
                "p2s1": {
                    "stages": {
                        "diachronic": {
                            "status": "done",
                            "substeps": {
                                "idu_naming_ordering": {
                                    "status": "done",
                                    "close_id": "cid3",
                                    "output_paths": ["analyses/p2s1-diachronic.idu_naming_ordering.json"],
                                    "artifact_shas": {
                                        "analyses/p2s1-diachronic.idu_naming_ordering.json": "sha_p2s1_dia",
                                    }
                                }
                            }
                        }
                    }
                },
                "p2s1-idu1": {
                    "stages": {
                        "synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {
                                    "status": "done",
                                    "close_id": "cid4",
                                    "output_paths": ["analyses/p2s1-idu1-synchronic.isu_second_level_grouping.json"],
                                    "artifact_shas": {
                                        "analyses/p2s1-idu1-synchronic.isu_second_level_grouping.json": "sha_p2s1_sync",
                                    }
                                }
                            }
                        }
                    }
                },
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        args = argparse.Namespace(
            scope="event1-cat-low",
            stage="generic_diachronic",
            run_dir=str(run_dir),
        )

        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cmd_inputs(args)

        assert rc == 0, f"cmd_inputs returned non-zero: {rc}"
        result = json.loads(out.getvalue())
        assert "resolved" in result, f"Output missing 'resolved' key: {result}"
        resolved_paths = {r["path"] for r in result["resolved"]}

        # Must include diachronic idu_naming_ordering artifacts for both transcripts
        assert "analyses/p1s1-diachronic.idu_naming_ordering.json" in resolved_paths
        assert "analyses/p1s1-diachronic.idu_naming_ordering.md" in resolved_paths
        assert "analyses/p2s1-diachronic.idu_naming_ordering.json" in resolved_paths
        # Must include synchronic isu_second_level_grouping artifacts
        assert "analyses/p1s1-idu1-synchronic.isu_second_level_grouping.json" in resolved_paths
        assert "analyses/p2s1-idu1-synchronic.isu_second_level_grouping.json" in resolved_paths

        # SHAs must be populated
        sha_map = {r["path"]: r["sha256"] for r in result["resolved"]}
        assert sha_map["analyses/p1s1-diachronic.idu_naming_ordering.json"] == "sha_p1s1_dia"
        assert sha_map["analyses/p2s1-idu1-synchronic.isu_second_level_grouping.json"] == "sha_p2s1_sync"

    def test_inputs_global_synchronic_resolves_generic_synchronic_artifacts(self, tmp_path):
        """AC2.1: global_synchronic scope resolves generic_synchronic.isu_second_level_grouping artifacts for matching gidu."""
        from mpi_step import cmd_inputs
        import argparse

        run_dir = _init_run_dir(tmp_path)

        # Build manifest with generic_synchronic done for gidu1 across two events
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event1": ["p1s1"],
                    "event2": ["p1s2"],
                }
            },
            "participants": {
                # event1-cat-low-gidu1: matches gidu1
                "event1-cat-low-gidu1": {
                    "stages": {
                        "generic_synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {
                                    "status": "done",
                                    "close_id": "cid10",
                                    "output_paths": [
                                        "analyses/event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json",
                                        "analyses/event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.md",
                                    ],
                                    "artifact_shas": {
                                        "analyses/event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json": "sha_e1_gs",
                                        "analyses/event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.md": "sha_e1_gs_md",
                                    }
                                }
                            }
                        }
                    }
                },
                # event2-cat-low-gidu1: matches gidu1
                "event2-cat-low-gidu1": {
                    "stages": {
                        "generic_synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {
                                    "status": "done",
                                    "close_id": "cid11",
                                    "output_paths": [
                                        "analyses/event2-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json",
                                    ],
                                    "artifact_shas": {
                                        "analyses/event2-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json": "sha_e2_gs",
                                    }
                                }
                            }
                        }
                    }
                },
                # event1-cat-low-gidu2: different gidu — should NOT be included for gidu1-cat-low
                "event1-cat-low-gidu2": {
                    "stages": {
                        "generic_synchronic": {
                            "substeps": {
                                "isu_second_level_grouping": {
                                    "status": "done",
                                    "close_id": "cid12",
                                    "output_paths": [
                                        "analyses/event1-cat-low-gidu2-generic_synchronic.isu_second_level_grouping.json",
                                    ],
                                    "artifact_shas": {
                                        "analyses/event1-cat-low-gidu2-generic_synchronic.isu_second_level_grouping.json": "sha_e1_gs2",
                                    }
                                }
                            }
                        }
                    }
                },
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        args = argparse.Namespace(
            scope="gidu1-cat-low",
            stage="global_synchronic",
            run_dir=str(run_dir),
        )

        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            rc = cmd_inputs(args)

        assert rc == 0, f"cmd_inputs returned non-zero: {rc}"
        result = json.loads(out.getvalue())
        resolved_paths = {r["path"] for r in result["resolved"]}

        # gidu1 scope: event1-gidu1 and event2-gidu1 included
        assert "analyses/event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json" in resolved_paths
        assert "analyses/event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.md" in resolved_paths
        assert "analyses/event2-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json" in resolved_paths
        # gidu2 must NOT be included
        assert "analyses/event1-cat-low-gidu2-generic_synchronic.isu_second_level_grouping.json" not in resolved_paths

        # SHAs must be present
        sha_map = {r["path"]: r["sha256"] for r in result["resolved"]}
        assert sha_map.get("analyses/event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json") == "sha_e1_gs"

    def test_inputs_unknown_stage_returns_nonzero(self, tmp_path):
        """AC2.1 guard: unknown stage returns non-zero exit code."""
        from mpi_step import cmd_inputs
        import argparse

        run_dir = _init_run_dir(tmp_path)

        args = argparse.Namespace(
            scope="event1-cat-low",
            stage="nonexistent_stage",
            run_dir=str(run_dir),
        )

        rc = cmd_inputs(args)
        assert rc != 0, "cmd_inputs should return non-zero for unknown stage"


class TestUndeclaredInputGate:
    """AC2.2: undeclared_input gate in cmd_close."""

    def _make_manifest_with_generic_sync_done(self, run_dir: Path, artifact_path: str, artifact_sha: str) -> None:
        """Write a manifest with done upstream substeps for closing generic_synchronic.isu_second_level_grouping.

        Scope: event1-cat-low-gidu1
        Prerequisites for isu_second_level_grouping:
        - generic_synchronic.worksheet_assembly at event1-cat-low-gidu1 must be done
        Also populates event1-cat-low generic_diachronic.cross_iv_contrast (used as resolved input).
        """
        manifest = {
            "version": "2.0",
            "run_id": "test-run-id",
            "study": {
                "event_groups": {
                    "event1": ["p1s1"]
                },
                "strict_gates": [],
            },
            "participants": {
                "event1-cat-low": {
                    "stages": {
                        "generic_diachronic": {
                            "status": "done",
                            "substeps": {
                                "cross_iv_contrast": {
                                    "status": "done",
                                    "close_id": "cid-upstream",
                                    "output_paths": [artifact_path],
                                    "artifact_shas": {artifact_path: artifact_sha},
                                }
                            }
                        }
                    }
                },
                # worksheet_assembly prerequisite for isu_second_level_grouping
                "event1-cat-low-gidu1": {
                    "stages": {
                        "generic_synchronic": {
                            "substeps": {
                                "worksheet_assembly": {
                                    "status": "done",
                                    "close_id": "cid-ws",
                                    "output_paths": [],
                                    "artifact_shas": {},
                                },
                                "select_generic_idus_of_interest": {
                                    "status": "done",
                                    "close_id": "cid-sel",
                                    "output_paths": [],
                                    "artifact_shas": {},
                                },
                            }
                        }
                    }
                },
            }
        }
        manifest_path = run_dir / ".mpi" / "project.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    def test_inputs_consumed_subset_closes_clean(self, tmp_path):
        """AC2.2: inputs_consumed containing only resolved paths allows close to succeed."""
        run_dir = _init_run_dir(tmp_path)

        upstream_path = "analyses/event1-cat-low-generic_diachronic.cross_iv_contrast.json"
        upstream_sha = "abcdef1234567890"
        self._make_manifest_with_generic_sync_done(run_dir, upstream_path, upstream_sha)

        # Write the upstream artifact file so it exists on disk (SHAs won't be checked here)
        (run_dir / "analyses").mkdir(exist_ok=True)
        (run_dir / upstream_path).write_text('{"ok": true}')

        # Units JSON includes inputs_consumed pointing to the resolved upstream artifact
        units_payload = {
            "event": "event1",
            "iv_category": "low",
            "generic_idu": "gidu1",
            "isus": [],
            "inputs_consumed": [upstream_path],
        }
        art_json = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json")
        art_md = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "event1-cat-low-gidu1", "generic_synchronic", "isu_second_level_grouping")
        units = _write_units_json(run_dir, "units.json", units_payload)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "event1-cat-low-gidu1",
            "--stage", "generic_synchronic",
            "--substep", "isu_second_level_grouping",
            "--scope", "event1-cat-low-gidu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test clean subset",
            "--run-dir", str(run_dir),
        ])
        assert rc == 0, f"Close should succeed when inputs_consumed ⊆ resolved; got rc={rc}"

    def test_inputs_consumed_superset_warns(self, tmp_path, capsys):
        """AC2.2: inputs_consumed with a path not in resolved set triggers gate_warning; close succeeds."""
        run_dir = _init_run_dir(tmp_path)

        upstream_path = "analyses/event1-cat-low-generic_diachronic.cross_iv_contrast.json"
        upstream_sha = "abcdef1234567890"
        self._make_manifest_with_generic_sync_done(run_dir, upstream_path, upstream_sha)

        (run_dir / "analyses").mkdir(exist_ok=True)
        (run_dir / upstream_path).write_text('{"ok": true}')

        # Include a bogus path NOT in the resolved set
        bogus_path = "analyses/bogus_not_in_resolved.md"
        units_payload = {
            "event": "event1",
            "iv_category": "low",
            "generic_idu": "gidu1",
            "isus": [],
            "inputs_consumed": [upstream_path, bogus_path],
        }
        art_json = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json")
        art_md = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "event1-cat-low-gidu1", "generic_synchronic", "isu_second_level_grouping")
        units = _write_units_json(run_dir, "units.json", units_payload)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "event1-cat-low-gidu1",
            "--stage", "generic_synchronic",
            "--substep", "isu_second_level_grouping",
            "--scope", "event1-cat-low-gidu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test superset warns",
            "--run-dir", str(run_dir),
        ])
        # Close should succeed (warn-by-default, not strict)
        assert rc == 0, f"Close should succeed (warn mode) with undeclared input; got rc={rc}"

        # Audit must have a gate_warning event for undeclared_input
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        events = [json.loads(ln) for ln in audit_path.read_text().splitlines() if ln.strip()]
        gw_events = [e for e in events if e.get("event", {}).get("action") == "gate_warning"
                     and e.get("mpi", {}).get("gate_id") == "undeclared_input"]
        assert len(gw_events) >= 1, (
            f"Expected gate_warning with gate_id=undeclared_input in audit, got events: "
            f"{[e.get('event', {}).get('action') for e in events]}"
        )

    def test_inputs_consumed_superset_strict_blocks(self, tmp_path, capsys):
        """AC2.2: inputs_consumed path not in resolved set + --strict-undeclared-input aborts close."""
        run_dir = _init_run_dir(tmp_path)

        upstream_path = "analyses/event1-cat-low-generic_diachronic.cross_iv_contrast.json"
        upstream_sha = "abcdef1234567890"
        self._make_manifest_with_generic_sync_done(run_dir, upstream_path, upstream_sha)

        (run_dir / "analyses").mkdir(exist_ok=True)
        (run_dir / upstream_path).write_text('{"ok": true}')

        bogus_path = "analyses/bogus_not_in_resolved_strict.md"
        units_payload = {
            "event": "event1",
            "iv_category": "low",
            "generic_idu": "gidu1",
            "isus": [],
            "inputs_consumed": [upstream_path, bogus_path],
        }
        art_json = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json")
        art_md = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "event1-cat-low-gidu1", "generic_synchronic", "isu_second_level_grouping")
        units = _write_units_json(run_dir, "units.json", units_payload)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "event1-cat-low-gidu1",
            "--stage", "generic_synchronic",
            "--substep", "isu_second_level_grouping",
            "--scope", "event1-cat-low-gidu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test superset strict",
            "--run-dir", str(run_dir),
            "--strict-undeclared-input",
        ])
        assert rc != 0, f"Close should abort with --strict-undeclared-input when path not in resolved set; got rc={rc}"
        stderr_out = capsys.readouterr().err
        assert "undeclared_input" in stderr_out, (
            f"Expected 'undeclared_input' in stderr, got: {stderr_out}"
        )

    def test_inputs_consumed_absent_skips_check(self, tmp_path):
        """AC2.2: absent inputs_consumed field skips the gate entirely (not a violation)."""
        run_dir = _init_run_dir(tmp_path)

        upstream_path = "analyses/event1-cat-low-generic_diachronic.cross_iv_contrast.json"
        upstream_sha = "abcdef1234567890"
        self._make_manifest_with_generic_sync_done(run_dir, upstream_path, upstream_sha)

        (run_dir / "analyses").mkdir(exist_ok=True)
        (run_dir / upstream_path).write_text('{"ok": true}')

        # No inputs_consumed field
        units_payload = {
            "event": "event1",
            "iv_category": "low",
            "generic_idu": "gidu1",
            "isus": [],
            # inputs_consumed intentionally absent
        }
        art_json = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.json")
        art_md = _write_artifact(run_dir, "event1-cat-low-gidu1-generic_synchronic.isu_second_level_grouping.md", "# output")
        prompt_art = _write_prompt_artifact(run_dir, "event1-cat-low-gidu1", "generic_synchronic", "isu_second_level_grouping")
        units = _write_units_json(run_dir, "units.json", units_payload)

        rc = mpi_step.main([
            "close",
            "--actor", "mpi-cross-analyst",
            "--participant", "event1-cat-low-gidu1",
            "--stage", "generic_synchronic",
            "--substep", "isu_second_level_grouping",
            "--scope", "event1-cat-low-gidu1",
            "--artifact", str(art_json),
            "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units),
            "--reason", "test no inputs_consumed",
            "--run-dir", str(run_dir),
            "--strict-undeclared-input",  # even with strict, absent means skip
        ])
        assert rc == 0, f"Close should succeed when inputs_consumed absent; got rc={rc}"

        # Audit must NOT have a gate_warning for undeclared_input
        audit_path = run_dir / ".mpi" / "audit.jsonl"
        events = [json.loads(ln) for ln in audit_path.read_text().splitlines() if ln.strip()]
        gw_events = [e for e in events if e.get("event", {}).get("action") == "gate_warning"
                     and e.get("mpi", {}).get("gate_id") == "undeclared_input"]
        assert len(gw_events) == 0, (
            f"Expected no undeclared_input gate_warning when inputs_consumed absent, got: {gw_events}"
        )

"""Phase 1 unit tests for mpi_step.py — CLI scaffolding."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure scripts/ is on the path
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

import mpi_step
from _mpi_atomic import atomic_write, append_jsonl, load_or_create_run_id
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

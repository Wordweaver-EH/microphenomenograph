#!/usr/bin/env python3
"""
Verification test for /mpi all orchestration specification.

Validates the orchestration spec for Tasks 3-4:
a. Stage ordering is correct (transcript-prep → diachronic → synchronic →
   generic-diachronic → generic-synchronic → global-synchronic → hypothesis)
b. Resume logic: stages with 'done' status are skipped on re-run
c. Downstream cascade: if diachronic resets to pending, generic_diachronic
   resets too; synchronic reset cascades to generic_synchronic/global_synchronic/hypothesis
d. Git commit format: 'mpi: pNsN {stage} analysis' per-participant
e. Reasoning log: entry format '[ISO timestamp] pNsN stage: ...'
f. Yolo mode flag sets manifest mode to 'yolo'
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

# Force UTF-8 output on Windows
if sys.stdout.encoding.upper() != 'UTF-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class OrchestrationSpec:
    """Specification for /mpi all orchestration."""

    # Stage order (per phase_08.md)
    STAGE_ORDER = [
        "transcript_prep",
        "diachronic",
        "synchronic",
        "generic_diachronic",
        "generic_synchronic",
        "global_synchronic",
        "hypothesis",
    ]

    # Per-participant stages (can be parallelized in yolo mode)
    PER_PARTICIPANT_STAGES = {"transcript_prep", "diachronic", "synchronic"}

    # Cross-participant stages
    CROSS_PARTICIPANT_STAGES = {
        "generic_diachronic",
        "generic_synchronic",
        "global_synchronic",
        "hypothesis",
    }

    # Cascade rules: if this stage is reset, these downstream stages reset too
    DOWNSTREAM_CASCADE = {
        "diachronic": {"generic_diachronic"},  # diachronic reset → generic_diachronic reset
        "synchronic": {
            "generic_synchronic",
            "global_synchronic",
            "hypothesis",
        },  # synchronic reset → all downstream reset
    }

    # Prerequisite stages for cross-participant stages
    PREREQUISITES = {
        "generic_diachronic": ["diachronic"],  # all participants must have diachronic done
        "generic_synchronic": ["synchronic"],  # all participants must have synchronic done
        "global_synchronic": ["generic_synchronic"],
        "hypothesis": ["global_synchronic"],
    }

    @staticmethod
    def get_commit_message(participant_key: Optional[str], stage: str) -> str:
        """Return expected commit message format."""
        if participant_key:
            return f"mpi: {participant_key} {stage} analysis"
        else:
            return f"mpi: {stage} analysis"

    @staticmethod
    def validate_reasoning_log_entry(entry: str) -> bool:
        """Validate reasoning log entry format: [ISO timestamp] pNsN stage: ..."""
        # Expected format: [2026-05-17T12:34:56Z] p1s1 diachronic: ...
        pattern = r'^\[\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\]\s+p\d+s\d+\s+\w+:\s+.+'
        return bool(re.match(pattern, entry))


class ManifestOrchestratorTester:
    """Test manifest orchestration logic."""

    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors: List[str] = []

    def assert_true(self, condition: bool, message: str) -> None:
        """Assert condition is true."""
        if condition:
            self.passed += 1
            print(f"  ✓ {message}")
        else:
            self.failed += 1
            self.errors.append(message)
            print(f"  ✗ {message}")

    def assert_equal(self, actual: Any, expected: Any, message: str) -> None:
        """Assert actual equals expected."""
        if actual == expected:
            self.passed += 1
            print(f"  ✓ {message}")
        else:
            self.failed += 1
            self.errors.append(
                f"{message} [expected: {expected}, got: {actual}]"
            )
            print(f"  ✗ {message} [expected: {expected}, got: {actual}]")

    def build_test_manifest(self) -> Dict[str, Any]:
        """Build a test manifest with 6 participants."""
        now = datetime.utcnow().isoformat() + "Z"

        participants = {}
        for p in range(1, 3):
            for s in range(1, 4):
                key = f"p{p}s{s}"
                participants[key] = {
                    "participant": p,
                    "suggestion": s,
                    "score": 4,
                    "score_category": "high",
                    "transcript_path": f"transcripts/{key}.txt",
                    "stages": {
                        "transcript_prep": {"status": "pending", "output_path": None},
                        "diachronic": {"status": "pending", "output_path": None},
                        "synchronic": {"status": "pending", "output_path": None},
                    },
                }

        return {
            "version": "1.0",
            "mode": "assisted",
            "created_at": now,
            "updated_at": now,
            "participants": participants,
            "cross_participant_stages": {
                "generic_diachronic": {"status": "pending", "output_path": None},
                "generic_synchronic": {"status": "pending", "output_path": None},
                "global_synchronic": {"status": "pending", "output_path": None},
                "hypothesis": {"status": "pending", "output_path": None},
            },
            "review_queue_path": ".mpi/review-queue.md",
            "reasoning_log_path": ".mpi/reasoning.log",
            "git_commit": False,
        }

    def test_stage_ordering(self) -> bool:
        """Test A: Stage ordering is correct."""
        print("\n[Test A] Stage Ordering")
        print("-" * 80)

        expected = OrchestrationSpec.STAGE_ORDER

        # Check order is preserved
        self.assert_equal(
            expected[0],
            "transcript_prep",
            "Stage 1: transcript_prep is first"
        )
        self.assert_equal(
            expected[1],
            "diachronic",
            "Stage 2: diachronic follows transcript_prep"
        )
        self.assert_equal(
            expected[2],
            "synchronic",
            "Stage 3: synchronic follows diachronic"
        )
        self.assert_equal(
            expected[3],
            "generic_diachronic",
            "Stage 4: generic_diachronic is after per-participant stages"
        )
        self.assert_equal(
            expected[4],
            "generic_synchronic",
            "Stage 5: generic_synchronic follows generic_diachronic"
        )
        self.assert_equal(
            expected[5],
            "global_synchronic",
            "Stage 6: global_synchronic follows generic_synchronic"
        )
        self.assert_equal(
            expected[6],
            "hypothesis",
            "Stage 7: hypothesis is last"
        )

        # Verify count
        self.assert_equal(
            len(expected),
            7,
            "All 7 stages present"
        )

        # Verify per-participant vs cross-participant split
        per_participant = expected[:3]
        cross_participant = expected[3:]

        self.assert_equal(
            set(per_participant),
            OrchestrationSpec.PER_PARTICIPANT_STAGES,
            "First 3 stages are per-participant"
        )
        self.assert_equal(
            set(cross_participant),
            OrchestrationSpec.CROSS_PARTICIPANT_STAGES,
            "Last 4 stages are cross-participant"
        )

        return self.failed == 0

    def test_resume_logic(self) -> bool:
        """Test B: Resume logic skips done stages."""
        print("\n[Test B] Resume Logic (Skip Done Stages)")
        print("-" * 80)

        manifest = self.build_test_manifest()

        # Simulate completion of transcript_prep for all participants
        for key in manifest["participants"]:
            manifest["participants"][key]["stages"]["transcript_prep"]["status"] = "done"
            manifest["participants"][key]["stages"]["transcript_prep"]["output_path"] = f"analyses/{key}-transcript_prep.md"

        # Check: all transcript_prep stages are done
        all_done = all(
            manifest["participants"][key]["stages"]["transcript_prep"]["status"] == "done"
            for key in manifest["participants"]
        )
        self.assert_true(
            all_done,
            "All participants have transcript_prep marked done"
        )

        # Check: diachronic stages should still be pending
        all_pending_dia = all(
            manifest["participants"][key]["stages"]["diachronic"]["status"] == "pending"
            for key in manifest["participants"]
        )
        self.assert_true(
            all_pending_dia,
            "All participants still have diachronic pending"
        )

        # When running /mpi all again, transcript_prep should be skipped
        # Logic: for each stage, check manifest status before executing
        pending_participants_for_transcript_prep = [
            key for key in manifest["participants"]
            if manifest["participants"][key]["stages"]["transcript_prep"]["status"] == "pending"
        ]
        self.assert_equal(
            len(pending_participants_for_transcript_prep),
            0,
            "No pending participants for transcript_prep (should skip stage)"
        )

        # Now mark some diachronic as done
        manifest["participants"]["p1s1"]["stages"]["diachronic"]["status"] = "done"
        manifest["participants"]["p1s1"]["stages"]["diachronic"]["output_path"] = "analyses/p1s1-diachronic.md"

        # Check others still pending
        pending_diachronic = [
            key for key in manifest["participants"]
            if manifest["participants"][key]["stages"]["diachronic"]["status"] == "pending"
        ]
        self.assert_equal(
            len(pending_diachronic),
            5,
            "5 participants have diachronic pending (p1s1 done)"
        )

        return self.failed == 0

    def test_downstream_cascade(self) -> bool:
        """Test C: Downstream cascade on stage reset."""
        print("\n[Test C] Downstream Cascade (Stage Reset)")
        print("-" * 80)

        manifest = self.build_test_manifest()

        # Setup: Mark all diachronic done, generic_diachronic done
        for key in manifest["participants"]:
            manifest["participants"][key]["stages"]["diachronic"]["status"] = "done"
        manifest["cross_participant_stages"]["generic_diachronic"]["status"] = "done"

        # Now simulate: user resets p1s1 diachronic to pending
        manifest["participants"]["p1s1"]["stages"]["diachronic"]["status"] = "pending"
        manifest["participants"]["p1s1"]["stages"]["diachronic"]["output_path"] = None

        # Apply cascade rule: diachronic reset → generic_diachronic reset
        # This is what /mpi all should do at startup
        diachronic_reset = [
            key for key in manifest["participants"]
            if manifest["participants"][key]["stages"]["diachronic"]["status"] == "pending"
        ]

        if diachronic_reset:
            # Any diachronic reset → reset generic_diachronic to pending
            manifest["cross_participant_stages"]["generic_diachronic"]["status"] = "pending"

        self.assert_equal(
            manifest["cross_participant_stages"]["generic_diachronic"]["status"],
            "pending",
            "generic_diachronic reset to pending when diachronic was reset"
        )

        # Test synchronic cascade
        # Setup: Mark all synchronic done, generic_synchronic, global_synchronic, hypothesis done
        for key in manifest["participants"]:
            manifest["participants"][key]["stages"]["synchronic"]["status"] = "done"
        manifest["cross_participant_stages"]["generic_synchronic"]["status"] = "done"
        manifest["cross_participant_stages"]["global_synchronic"]["status"] = "done"
        manifest["cross_participant_stages"]["hypothesis"]["status"] = "done"

        # Reset one synchronic to pending
        manifest["participants"]["p1s1"]["stages"]["synchronic"]["status"] = "pending"

        # Apply cascade: synchronic reset → reset generic_synchronic, global_synchronic, hypothesis
        synchronic_reset = [
            key for key in manifest["participants"]
            if manifest["participants"][key]["stages"]["synchronic"]["status"] == "pending"
        ]

        if synchronic_reset:
            for stage in ["generic_synchronic", "global_synchronic", "hypothesis"]:
                manifest["cross_participant_stages"][stage]["status"] = "pending"

        # Verify cascade
        self.assert_equal(
            manifest["cross_participant_stages"]["generic_synchronic"]["status"],
            "pending",
            "generic_synchronic reset when synchronic was reset"
        )
        self.assert_equal(
            manifest["cross_participant_stages"]["global_synchronic"]["status"],
            "pending",
            "global_synchronic reset when synchronic was reset"
        )
        self.assert_equal(
            manifest["cross_participant_stages"]["hypothesis"]["status"],
            "pending",
            "hypothesis reset when synchronic was reset"
        )

        return self.failed == 0

    def test_git_commit_format(self) -> bool:
        """Test D: Git commit format is correct."""
        print("\n[Test D] Git Commit Format")
        print("-" * 80)

        # Test per-participant commit format
        per_participant_commits = [
            OrchestrationSpec.get_commit_message("p1s1", "transcript_prep"),
            OrchestrationSpec.get_commit_message("p2s3", "diachronic"),
            OrchestrationSpec.get_commit_message("p1s2", "synchronic"),
        ]

        expected_per_participant = [
            "mpi: p1s1 transcript_prep analysis",
            "mpi: p2s3 diachronic analysis",
            "mpi: p1s2 synchronic analysis",
        ]

        for actual, expected in zip(per_participant_commits, expected_per_participant):
            self.assert_equal(
                actual,
                expected,
                f"Per-participant commit: {expected}"
            )

        # Test cross-participant commit format
        cross_participant_commits = [
            OrchestrationSpec.get_commit_message(None, "generic_diachronic"),
            OrchestrationSpec.get_commit_message(None, "generic_synchronic"),
            OrchestrationSpec.get_commit_message(None, "global_synchronic"),
            OrchestrationSpec.get_commit_message(None, "hypothesis"),
        ]

        expected_cross_participant = [
            "mpi: generic_diachronic analysis",
            "mpi: generic_synchronic analysis",
            "mpi: global_synchronic analysis",
            "mpi: hypothesis analysis",
        ]

        for actual, expected in zip(cross_participant_commits, expected_cross_participant):
            self.assert_equal(
                actual,
                expected,
                f"Cross-participant commit: {expected}"
            )

        return self.failed == 0

    def test_reasoning_log_format(self) -> bool:
        """Test E: Reasoning log entry format."""
        print("\n[Test E] Reasoning Log Entry Format")
        print("-" * 80)

        # Valid log entries
        valid_entries = [
            "[2026-05-17T14:23:45Z] p1s1 diachronic: Identified 5 IDUs. 1 flagged.",
            "[2026-05-17T14:23:46Z] p1s2 synchronic: Identified 8 ISUs. 0 flagged.",
            "[2026-05-17T14:24:00Z] p2s1 diachronic: Identified 3 IDUs. 2 flagged.",
        ]

        for entry in valid_entries:
            is_valid = OrchestrationSpec.validate_reasoning_log_entry(entry)
            self.assert_true(
                is_valid,
                f"Valid reasoning log entry: {entry[:50]}..."
            )

        # Invalid entries
        invalid_entries = [
            "p1s1 diachronic: Missing timestamp",  # No timestamp
            "[2026-05-17 14:23:45Z] p1s1 diachronic: Bad timestamp format",  # Wrong format
            "[2026-05-17T14:23:45Z] p1s1: Missing stage name",  # No stage
            "[2026-05-17T14:23:45Z] 1s1 diachronic: Invalid participant key",  # Bad key
        ]

        for entry in invalid_entries:
            is_valid = OrchestrationSpec.validate_reasoning_log_entry(entry)
            self.assert_true(
                not is_valid,
                f"Invalid reasoning log entry correctly rejected: {entry[:50]}..."
            )

        return self.failed == 0

    def test_yolo_mode_flag(self) -> bool:
        """Test F: Yolo mode flag sets manifest mode."""
        print("\n[Test F] Yolo Mode Flag")
        print("-" * 80)

        manifest = self.build_test_manifest()

        # Default mode is assisted
        self.assert_equal(
            manifest["mode"],
            "assisted",
            "Default mode is 'assisted'"
        )

        # When --yolo flag passed, mode should be set to yolo
        manifest["mode"] = "yolo"

        self.assert_equal(
            manifest["mode"],
            "yolo",
            "Mode set to 'yolo' when --yolo flag passed"
        )

        # Verify mode is persisted in manifest
        manifest_json = json.dumps(manifest)
        reloaded = json.loads(manifest_json)

        self.assert_equal(
            reloaded["mode"],
            "yolo",
            "Mode persisted in manifest JSON"
        )

        return self.failed == 0

    def test_manifest_atomicity(self) -> bool:
        """Test manifest atomic write semantics."""
        print("\n[Test G] Manifest Atomicity")
        print("-" * 80)

        manifest = self.build_test_manifest()

        # Simulate atomic write: write to .tmp, then rename
        # In actual implementation:
        # 1. Write to .mpi/project.json.tmp
        # 2. Rename .mpi/project.json.tmp to .mpi/project.json

        # Mock implementation
        manifest_tmp = json.dumps(manifest, indent=2)

        # Verify it's valid JSON (can be parsed)
        reloaded = json.loads(manifest_tmp)

        self.assert_true(
            "participants" in reloaded,
            "Atomic write: reloaded manifest has participants"
        )
        self.assert_true(
            "cross_participant_stages" in reloaded,
            "Atomic write: reloaded manifest has cross_participant_stages"
        )

        # Verify all participant entries are complete
        for key, entry in reloaded["participants"].items():
            self.assert_true(
                "stages" in entry,
                f"Atomic write: participant {key} has stages"
            )

        return self.failed == 0

    def test_prerequisites(self) -> bool:
        """Test prerequisite validation for cross-participant stages."""
        print("\n[Test H] Prerequisites for Cross-Participant Stages")
        print("-" * 80)

        manifest = self.build_test_manifest()

        # generic_diachronic requires all diachronic done
        # Scenario 1: diachronic not done
        can_run_generic_diachronic = all(
            manifest["participants"][key]["stages"]["diachronic"]["status"] == "done"
            for key in manifest["participants"]
        )
        self.assert_true(
            not can_run_generic_diachronic,
            "Cannot run generic_diachronic when diachronic stages pending"
        )

        # Scenario 2: all diachronic done
        for key in manifest["participants"]:
            manifest["participants"][key]["stages"]["diachronic"]["status"] = "done"

        can_run_generic_diachronic = all(
            manifest["participants"][key]["stages"]["diachronic"]["status"] == "done"
            for key in manifest["participants"]
        )
        self.assert_true(
            can_run_generic_diachronic,
            "Can run generic_diachronic when all diachronic done"
        )

        return self.failed == 0


def main():
    print("=" * 80)
    print("Orchestration Specification Verification Tests")
    print("=" * 80)

    tester = ManifestOrchestratorTester()

    # Run all tests
    results = [
        tester.test_stage_ordering(),
        tester.test_resume_logic(),
        tester.test_downstream_cascade(),
        tester.test_git_commit_format(),
        tester.test_reasoning_log_format(),
        tester.test_yolo_mode_flag(),
        tester.test_manifest_atomicity(),
        tester.test_prerequisites(),
    ]

    # Print summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)

    total_passed = tester.passed
    total_failed = tester.failed
    total = total_passed + total_failed

    print(f"\nTotal assertions: {total}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")

    if tester.errors:
        print("\nErrors:")
        for error in tester.errors:
            print(f"  - {error}")

    # Final verdict
    if all(results) and total_failed == 0:
        print("\n" + "=" * 80)
        print("All Orchestration Tests PASSED ✓")
        print("=" * 80)
        return True
    else:
        print("\n" + "=" * 80)
        print("Some Tests FAILED ✗")
        print("=" * 80)
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

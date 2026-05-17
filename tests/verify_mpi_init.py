#!/usr/bin/env python3
"""
Verification test for mpi-init implementation.

Simulates what /mpi init would do:
1. Reads all .txt files from examples/transcripts/
2. Parses headers with the permissive regex
3. Builds the manifest
4. Validates all expected fields
5. Checks idempotency
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Force UTF-8 output on Windows
if sys.stdout.encoding.upper() != 'UTF-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# The regex defined in SKILL.md
HEADER_REGEX = r'^Participant (\d+),?\s+Suggestion (\d+)(?:\s+\w+)*\s*\(Scored (\d+)/5\)'


def get_score_category(score: int) -> str:
    """Map score (0-5) to category."""
    if score in (0, 1):
        return "low"
    elif score in (2, 3):
        return "moderate"
    else:  # 4, 5
        return "high"


def parse_header(line: str) -> Optional[Tuple[int, int, int]]:
    """Parse header line, return (participant, suggestion, score) or None."""
    match = re.match(HEADER_REGEX, line)
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    return None


def read_transcripts(transcript_dir: Path) -> Dict[str, Tuple[int, int, int]]:
    """
    Read all .txt files from transcripts directory.
    Returns mapping of pNsN -> (participant, suggestion, score).
    """
    result = {}
    errors = []

    txt_files = sorted(transcript_dir.glob("*.txt"))

    for filepath in txt_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                first_line = f.readline().rstrip("\n")

            parsed = parse_header(first_line)
            if parsed is None:
                errors.append(
                    f"ERROR: {filepath.name}: invalid header format. "
                    f"Expected \"Participant N[,] Suggestion N (Scored N/5)[...]\", "
                    f"got: \"{first_line}\""
                )
                continue

            p, s, score = parsed
            key = f"p{p}s{s}"
            result[key] = (p, s, score)
        except Exception as e:
            errors.append(f"ERROR: {filepath.name}: {e}")

    return result, errors


def build_manifest(
    participants: Dict[str, Tuple[int, int, int]],
    transcript_dir: str = "transcripts",
    existing_manifest: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build or update manifest.

    If existing_manifest provided:
    - Preserve stage statuses for participants with "done" status
    - Add new participants with all stages pending
    - Remove participants no longer in transcripts
    """
    now = datetime.utcnow().isoformat() + "Z"

    # If updating existing manifest
    if existing_manifest:
        created_at = existing_manifest.get("created_at", now)
        preserved_count = 0
    else:
        created_at = now
        preserved_count = 0

    # Build new participants
    new_participants = {}
    for key, (p, s, score) in participants.items():
        category = get_score_category(score)

        # Check if already exists with done stages
        if existing_manifest and key in existing_manifest.get("participants", {}):
            old_entry = existing_manifest["participants"][key]
            old_stages = old_entry.get("stages", {})

            # If any stage is done, preserve all statuses
            has_done = any(v.get("status") == "done" for v in old_stages.values())
            if has_done:
                preserved_count += 1
                # Preserve existing stages
                stages = {
                    stage_name: {
                        "status": old_stages.get(stage_name, {}).get("status", "pending"),
                        "output_path": old_stages.get(stage_name, {}).get("output_path", None),
                    }
                    for stage_name in ["transcript_prep", "diachronic", "synchronic"]
                }
            else:
                # Reset to pending
                stages = {
                    "transcript_prep": {"status": "pending", "output_path": None},
                    "diachronic": {"status": "pending", "output_path": None},
                    "synchronic": {"status": "pending", "output_path": None},
                }
        else:
            # New participant
            stages = {
                "transcript_prep": {"status": "pending", "output_path": None},
                "diachronic": {"status": "pending", "output_path": None},
                "synchronic": {"status": "pending", "output_path": None},
            }

        new_participants[key] = {
            "participant": p,
            "suggestion": s,
            "score": score,
            "score_category": category,
            "transcript_path": f"{transcript_dir}/{key}.txt",
            "stages": stages,
        }

    manifest = {
        "version": "1.0",
        "mode": "assisted",
        "created_at": created_at,
        "updated_at": now,
        "participants": new_participants,
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

    return manifest, preserved_count


def verify_manifest_fields(manifest: Dict[str, Any]) -> Tuple[bool, list]:
    """Verify manifest has all required fields."""
    errors = []

    # Check top-level fields
    required_fields = [
        "version", "mode", "created_at", "updated_at",
        "participants", "cross_participant_stages",
        "review_queue_path", "reasoning_log_path", "git_commit"
    ]
    for field in required_fields:
        if field not in manifest:
            errors.append(f"Missing top-level field: {field}")

    # Check version
    if manifest.get("version") != "1.0":
        errors.append(f"Expected version 1.0, got {manifest.get('version')}")

    # Check mode
    if manifest.get("mode") not in ("assisted", "yolo"):
        errors.append(f"Invalid mode: {manifest.get('mode')}")

    # Check participant structure
    for key, entry in manifest.get("participants", {}).items():
        required_participant_fields = [
            "participant", "suggestion", "score", "score_category",
            "transcript_path", "stages"
        ]
        for field in required_participant_fields:
            if field not in entry:
                errors.append(f"Participant {key} missing field: {field}")

        # Check stages
        for stage in ["transcript_prep", "diachronic", "synchronic"]:
            if stage not in entry.get("stages", {}):
                errors.append(f"Participant {key} missing stage: {stage}")
            else:
                stage_entry = entry["stages"][stage]
                if "status" not in stage_entry or "output_path" not in stage_entry:
                    errors.append(
                        f"Participant {key} stage {stage} missing status/output_path"
                    )

    # Check cross-participant stages
    for stage in [
        "generic_diachronic", "generic_synchronic", "global_synchronic", "hypothesis"
    ]:
        if stage not in manifest.get("cross_participant_stages", {}):
            errors.append(f"Missing cross-participant stage: {stage}")

    return len(errors) == 0, errors


def main():
    print("=" * 80)
    print("Verification Test for mpi-init Implementation")
    print("=" * 80)

    # Find transcripts directory
    # Note: This file is in tests/, so go up one level to repo root
    repo_root = Path(__file__).parent.parent
    transcript_dir = repo_root / "microphenomenograph" / "1.0.0" / "examples" / "transcripts"

    if not transcript_dir.exists():
        print(f"ERROR: Transcript directory not found: {transcript_dir}")
        return False

    print(f"\nReading transcripts from: {transcript_dir}")

    # Test 1: Read and parse all transcripts
    print("\n[Test 1] Parse all transcript headers")
    print("-" * 80)

    participants, errors = read_transcripts(transcript_dir)

    if errors:
        print("Parsing errors encountered:")
        for error in errors:
            print(f"  {error}")
        return False

    print(f"✓ Successfully parsed {len(participants)} transcripts")

    # Verify we got expected 39 participants
    if len(participants) != 39:
        print(f"✗ Expected 39 participants, got {len(participants)}")
        return False
    print("✓ Expected 39 participants found")

    # Test 2: Verify specific participant headers
    print("\n[Test 2] Verify specific header parsing")
    print("-" * 80)

    test_cases = [
        ("p1s1", 1, 1, 4, "high"),
        ("p1s2", 1, 2, None, None),  # Will check actual value
        ("p6s1", 6, 1, 4, "high"),  # Missing comma format
    ]

    for key, exp_p, exp_s, exp_score, exp_cat in test_cases:
        if key not in participants:
            print(f"✗ Missing participant: {key}")
            return False

        p, s, score = participants[key]

        if p != exp_p or s != exp_s:
            print(
                f"✗ {key}: expected p={exp_p} s={exp_s}, "
                f"got p={p} s={s}"
            )
            return False

        if exp_score and score != exp_score:
            print(
                f"✗ {key}: expected score={exp_score}, got {score}"
            )
            return False

        category = get_score_category(score)
        if exp_cat and category != exp_cat:
            print(
                f"✗ {key}: expected category={exp_cat}, got {category}"
            )
            return False

        print(f"✓ {key}: p={p}, s={s}, score={score}, category={category}")

    # Test 3: Build manifest
    print("\n[Test 3] Build manifest")
    print("-" * 80)

    manifest, preserved = build_manifest(participants)
    print(f"✓ Manifest built with {len(manifest['participants'])} participants")
    print(f"  - Preserved stages: {preserved}")

    # Test 4: Verify manifest structure
    print("\n[Test 4] Verify manifest structure and fields")
    print("-" * 80)

    valid, field_errors = verify_manifest_fields(manifest)

    if not valid:
        print("✗ Manifest validation failed:")
        for error in field_errors:
            print(f"  - {error}")
        return False

    print("✓ All required fields present and valid")

    # Test 5: Verify p1s1 specific fields
    print("\n[Test 5] Verify p1s1 specific fields")
    print("-" * 80)

    p1s1 = manifest["participants"]["p1s1"]

    checks = [
        ("participant", 1),
        ("suggestion", 1),
        ("score", 4),
        ("score_category", "high"),
    ]

    for field, expected in checks:
        actual = p1s1.get(field)
        if actual != expected:
            print(f"✗ p1s1.{field}: expected {expected}, got {actual}")
            return False
        print(f"✓ p1s1.{field} = {actual}")

    # Verify all stages pending
    all_pending = all(
        v["status"] == "pending"
        for v in p1s1["stages"].values()
    )
    if not all_pending:
        print("✗ p1s1: not all stages pending")
        return False
    print("✓ p1s1: all stages pending")

    # Test 6: Test malformed header detection
    print("\n[Test 6] Test malformed header detection")
    print("-" * 80)

    # Create temporary malformed transcript
    temp_dir = repo_root / ".mpi_test_temp"
    temp_dir.mkdir(exist_ok=True)
    temp_bad = temp_dir / "bad.txt"
    temp_bad.write_text("Bad header format\n")

    bad_parsed = parse_header("Bad header format")
    if bad_parsed is not None:
        print("✗ Malformed header was not rejected")
        temp_bad.unlink()
        temp_dir.rmdir()
        return False
    print("✓ Malformed header correctly rejected")

    # Test 7: Test idempotency
    print("\n[Test 7] Test idempotency (re-run preserves done stages)")
    print("-" * 80)

    # Mark p1s1 diachronic as done
    manifest["participants"]["p1s1"]["stages"]["diachronic"]["status"] = "done"

    # Re-build manifest with same participants
    manifest2, preserved2 = build_manifest(participants, existing_manifest=manifest)

    # Check p1s1 diachronic is still done
    p1s1_dia_status = manifest2["participants"]["p1s1"]["stages"]["diachronic"]["status"]
    if p1s1_dia_status != "done":
        print(f"✗ p1s1 diachronic: expected 'done', got '{p1s1_dia_status}'")
        return False
    print("✓ p1s1 diachronic status preserved as 'done'")

    # Check other stages still pending
    p1s1_prep_status = manifest2["participants"]["p1s1"]["stages"]["transcript_prep"]["status"]
    if p1s1_prep_status != "pending":
        print(f"✗ p1s1 transcript_prep: expected 'pending', got '{p1s1_prep_status}'")
        return False
    print("✓ p1s1 transcript_prep still 'pending'")

    # Check updated_at changed
    if manifest2["updated_at"] == manifest["updated_at"]:
        print("✗ updated_at should change on re-run")
        return False
    print("✓ updated_at timestamp updated")

    # Clean up
    temp_bad.unlink()
    temp_dir.rmdir()

    # Test 8: Verify score categories for all participants
    print("\n[Test 8] Verify score categories across all participants")
    print("-" * 80)

    category_counts = {"low": 0, "moderate": 0, "high": 0}
    for key, entry in manifest["participants"].items():
        category = entry["score_category"]
        score = entry["score"]

        # Verify category matches score
        expected_cat = get_score_category(score)
        if category != expected_cat:
            print(f"✗ {key}: score={score} but category={category}")
            return False

        category_counts[category] += 1

    print(f"✓ Score categories verified for all {len(manifest['participants'])} participants")
    print(f"  - Low (0-1): {category_counts['low']}")
    print(f"  - Moderate (2-3): {category_counts['moderate']}")
    print(f"  - High (4-5): {category_counts['high']}")

    # Final summary
    print("\n" + "=" * 80)
    print("All Tests Passed!")
    print("=" * 80)
    print(f"\nSummary:")
    print(f"  - Participants parsed: {len(participants)}")
    print(f"  - Manifest entries: {len(manifest['participants'])}")
    print(f"  - All required fields present: ✓")
    print(f"  - Header parsing (including variants): ✓")
    print(f"  - Malformed header detection: ✓")
    print(f"  - Idempotency (preserve done stages): ✓")
    print(f"  - Score categorization: ✓")

    return True


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)

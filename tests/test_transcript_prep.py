#!/usr/bin/env python3
"""
Test suite for mpi-transcript-prep functionality.

Tests BOM stripping, whitespace normalisation, speaker label capitalisation,
CRLF->LF conversion, header validation, and manifest updates.
"""

import json
import os
import tempfile
import shutil
import re
import sys
from pathlib import Path

# Set UTF-8 encoding for stdout on Windows
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


class TranscriptPrep:
    """Simulates the mpi-transcript-prep skill functionality."""

    def __init__(self, manifest_path: str, transcripts_dir: str):
        self.manifest_path = manifest_path
        self.transcripts_dir = transcripts_dir
        self.errors = []
        self.warnings = []

    def load_manifest(self) -> dict:
        """Load the manifest from project.json."""
        if not os.path.exists(self.manifest_path):
            raise FileNotFoundError(f"Manifest not found at {self.manifest_path}")
        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_manifest(self, manifest: dict):
        """Save the manifest to project.json."""
        with open(self.manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2)

    def validate_header(self, first_line: str) -> bool:
        r"""Validate that header matches expected format.

        Must match: ^Participant \d+, Suggestion \d+ \(Scored \d+/5\)$
        """
        pattern = r'^Participant \d+, Suggestion \d+ \(Scored \d+/5\)$'
        return bool(re.match(pattern, first_line))

    def normalize_speaker_label(self, label: str) -> str:
        """Normalize speaker label capitalisation.

        Examples:
        - 'kevin sheldrake:' -> 'Kevin Sheldrake:'
        - 'p1:' -> 'P1:'
        - 'Kevin Sheldrake:' -> 'Kevin Sheldrake:'
        """
        if label.lower() == 'kevin sheldrake:':
            return 'Kevin Sheldrake:'

        # Handle participant labels like p1:, p2:, etc.
        match = re.match(r'^(p\d+):$', label.lower())
        if match:
            return match.group(1).upper() + ':'

        # Return as-is if doesn't match known patterns
        return label

    def is_speaker_label(self, text: str) -> bool:
        """Check if text begins with a recognized speaker label."""
        # Remove leading whitespace for checking
        stripped = text.lstrip()

        # Check for Kevin Sheldrake: (case-insensitive)
        if re.match(r'^kevin sheldrake:', stripped, re.IGNORECASE):
            return True

        # Check for P#: pattern (case-insensitive)
        if re.match(r'^p\d+:', stripped, re.IGNORECASE):
            return True

        return False

    def normalize_line(self, line: str) -> str:
        """Normalize a single line: spacing and speaker label capitalisation."""
        # Replace double spaces with single space
        line = re.sub(r' {2,}', ' ', line)

        # Strip trailing whitespace
        line = line.rstrip()

        # Normalize speaker label if present
        if ':' in line:
            parts = line.split(':', 1)
            label = parts[0].strip() + ':'
            rest = ':' + parts[1] if len(parts) > 1 else ':'

            # Only normalize if this looks like a speaker label
            if self.is_speaker_label(label):
                label = self.normalize_speaker_label(label)
                line = label + rest[1:]  # Preserve content after colon

        return line

    def process_transcript(self, participant_key: str, transcript_path: str) -> bool:
        """Process a single transcript file.

        Returns True if successful (status set to done or will be set).
        Returns False if error (status remains pending).
        """
        self.errors = []
        self.warnings = []

        # Make transcript_path absolute if needed
        if not os.path.isabs(transcript_path):
            transcript_path = os.path.join(self.transcripts_dir, transcript_path)

        # Check file exists
        if not os.path.exists(transcript_path):
            self.errors.append(f"ERROR [{participant_key}]: transcript file not found at {transcript_path}")
            return False

        # Read transcript
        with open(transcript_path, 'rb') as f:
            content = f.read()

        # Decode (handle BOM)
        text = content.decode('utf-8-sig')  # utf-8-sig strips BOM if present

        # Normalize line endings first (handle CRLF)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.split('\n')

        # Validate header (line 1, non-empty)
        if not lines or not lines[0].strip():
            self.errors.append(f"ERROR [{participant_key}]: line 1 is empty")
            return False

        if not self.validate_header(lines[0]):
            self.errors.append(f"ERROR [{participant_key}]: line 1 does not match expected header format")
            return False

        # Process all lines: normalize spacing and speaker labels
        normalized_lines = []
        for i, line in enumerate(lines):
            if line.strip():  # Non-empty line
                normalized_line = self.normalize_line(line)
                normalized_lines.append(normalized_line)
            else:  # Empty line
                normalized_lines.append('')

        # Convert CRLF->LF (already done by split, but ensure on write)
        output = '\n'.join(normalized_lines)

        # Write cleaned transcript back
        with open(transcript_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(output)

        return True

    def prep(self, participant_key: str = None) -> dict:
        """Process transcript(s) and update manifest.

        If participant_key given, process that one.
        Otherwise, process all with transcript_prep status 'pending'.
        """
        manifest = self.load_manifest()

        # Determine which participants to process
        if participant_key:
            targets = [participant_key]
        else:
            targets = [
                pk for pk, pdata in manifest.get('participants', {}).items()
                if pdata.get('stages', {}).get('transcript_prep', {}).get('status') == 'pending'
            ]

        results = {}

        for pk in targets:
            if pk not in manifest['participants']:
                continue

            pdata = manifest['participants'][pk]
            transcript_path = pdata.get('transcript_path')

            if not transcript_path:
                self.errors.append(f"ERROR [{pk}]: no transcript_path in manifest")
                results[pk] = {'success': False, 'errors': self.errors.copy()}
                continue

            # Make path relative to transcripts_dir if needed
            full_path = os.path.join(self.transcripts_dir, transcript_path)
            if not os.path.exists(full_path):
                full_path = transcript_path  # Try as absolute

            success = self.process_transcript(pk, transcript_path)

            if success:
                # Update manifest to done
                if 'stages' not in pdata:
                    pdata['stages'] = {}
                if 'transcript_prep' not in pdata['stages']:
                    pdata['stages']['transcript_prep'] = {}

                pdata['stages']['transcript_prep']['status'] = 'done'
                pdata['stages']['transcript_prep']['output_path'] = transcript_path

                results[pk] = {
                    'success': True,
                    'warnings': self.warnings.copy(),
                    'status': 'done'
                }
            else:
                # Do NOT update manifest on error
                results[pk] = {
                    'success': False,
                    'errors': self.errors.copy()
                }

        # Save updated manifest
        self.save_manifest(manifest)

        return results


def test_bom_stripping():
    """Test that BOM characters are stripped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = os.path.join(tmpdir, 'project.json')
        transcripts_dir = os.path.join(tmpdir, 'transcripts')
        os.makedirs(transcripts_dir)

        # Create manifest
        manifest = {
            'participants': {
                'p1s1': {
                    'transcript_path': 'p1s1.txt',
                    'stages': {'transcript_prep': {'status': 'pending', 'output_path': None}}
                }
            }
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        # Create transcript with BOM
        transcript_path = os.path.join(transcripts_dir, 'p1s1.txt')
        with open(transcript_path, 'wb') as f:
            # Write UTF-8 BOM + header + content
            f.write(b'\xef\xbb\xbf')  # UTF-8 BOM
            f.write('Participant 1, Suggestion 1 (Scored 4/5)\n'.encode('utf-8'))
            f.write('Kevin Sheldrake: Test\n'.encode('utf-8'))

        # Process
        prep = TranscriptPrep(manifest_path, transcripts_dir)
        result = prep.prep('p1s1')

        # Verify BOM stripped
        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert not content.startswith('﻿'), "BOM should be stripped"
            assert content.startswith('Participant'), "Content should start with header"

        print("[PASS] test_bom_stripping passed")


def test_double_space_normalisation():
    """Test that double spaces are replaced with single spaces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = os.path.join(tmpdir, 'project.json')
        transcripts_dir = os.path.join(tmpdir, 'transcripts')
        os.makedirs(transcripts_dir)

        manifest = {
            'participants': {
                'p1s1': {
                    'transcript_path': 'p1s1.txt',
                    'stages': {'transcript_prep': {'status': 'pending', 'output_path': None}}
                }
            }
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        # Create transcript with double spaces
        transcript_path = os.path.join(transcripts_dir, 'p1s1.txt')
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write('Participant 1, Suggestion 1 (Scored 4/5)\n')
            f.write('Kevin Sheldrake:  This  has  double  spaces\n')

        prep = TranscriptPrep(manifest_path, transcripts_dir)
        result = prep.prep('p1s1')

        assert result['p1s1']['success'], "Should succeed"

        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read()
            assert '  ' not in content, "Double spaces should be removed"
            assert 'This has double spaces' in content, "Content should have single spaces"

        print("[PASS] test_double_space_normalisation passed")


def test_speaker_label_capitalisation():
    """Test that speaker labels are normalized to correct capitalisation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = os.path.join(tmpdir, 'project.json')
        transcripts_dir = os.path.join(tmpdir, 'transcripts')
        os.makedirs(transcripts_dir)

        manifest = {
            'participants': {
                'p1s1': {
                    'transcript_path': 'p1s1.txt',
                    'stages': {'transcript_prep': {'status': 'pending', 'output_path': None}}
                }
            }
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        transcript_path = os.path.join(transcripts_dir, 'p1s1.txt')
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write('Participant 1, Suggestion 1 (Scored 4/5)\n')
            f.write('kevin sheldrake: lowercase kevin\n')
            f.write('KEVIN SHELDRAKE: uppercase kevin\n')
            f.write('p1: lowercase p1\n')
            f.write('P1: already correct p1\n')

        prep = TranscriptPrep(manifest_path, transcripts_dir)
        result = prep.prep('p1s1')

        assert result['p1s1']['success'], "Should succeed"

        with open(transcript_path, 'r', encoding='utf-8') as f:
            content = f.read()
            lines = content.strip().split('\n')
            assert lines[1].startswith('Kevin Sheldrake:'), f"Expected 'Kevin Sheldrake:', got {lines[1]}"
            assert lines[2].startswith('Kevin Sheldrake:'), f"Expected 'Kevin Sheldrake:', got {lines[2]}"
            assert lines[3].startswith('P1:'), f"Expected 'P1:', got {lines[3]}"
            assert lines[4].startswith('P1:'), f"Expected 'P1:', got {lines[4]}"

        print("[PASS] test_speaker_label_capitalisation passed")


def test_crlf_to_lf():
    """Test that Windows line endings (CRLF) are converted to Unix (LF)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = os.path.join(tmpdir, 'project.json')
        transcripts_dir = os.path.join(tmpdir, 'transcripts')
        os.makedirs(transcripts_dir)

        manifest = {
            'participants': {
                'p1s1': {
                    'transcript_path': 'p1s1.txt',
                    'stages': {'transcript_prep': {'status': 'pending', 'output_path': None}}
                }
            }
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        transcript_path = os.path.join(transcripts_dir, 'p1s1.txt')
        with open(transcript_path, 'wb') as f:
            # Write with CRLF line endings
            f.write(b'Participant 1, Suggestion 1 (Scored 4/5)\r\n')
            f.write(b'Kevin Sheldrake: Test\r\n')
            f.write(b'P1: Response\r\n')

        prep = TranscriptPrep(manifest_path, transcripts_dir)
        result = prep.prep('p1s1')

        assert result['p1s1']['success'], "Should succeed"

        with open(transcript_path, 'rb') as f:
            content = f.read()
            assert b'\r\n' not in content, "CRLF should be converted to LF"
            assert b'\n' in content, "Should have LF line endings"

        print("[PASS] test_crlf_to_lf passed")


def test_malformed_header_error():
    """Test that malformed header produces ERROR and does not update manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = os.path.join(tmpdir, 'project.json')
        transcripts_dir = os.path.join(tmpdir, 'transcripts')
        os.makedirs(transcripts_dir)

        manifest = {
            'participants': {
                'p99s1': {
                    'transcript_path': 'p99s1.txt',
                    'stages': {'transcript_prep': {'status': 'pending', 'output_path': None}}
                }
            }
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        transcript_path = os.path.join(transcripts_dir, 'p99s1.txt')
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write('BROKEN HEADER\n')
            f.write('P99: some utterance\n')

        prep = TranscriptPrep(manifest_path, transcripts_dir)
        result = prep.prep('p99s1')

        # Should fail
        assert not result['p99s1']['success'], "Should fail with bad header"
        assert any('does not match expected header format' in e for e in result['p99s1']['errors']), \
            "Should have header format error"

        # Verify manifest NOT updated
        with open(manifest_path, 'r') as f:
            updated_manifest = json.load(f)

        assert updated_manifest['participants']['p99s1']['stages']['transcript_prep']['status'] == 'pending', \
            "Status should remain pending on ERROR"

        print("[PASS] test_malformed_header_error passed")


def test_valid_transcript_done_status():
    """Test that valid transcript produces done status in manifest."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_path = os.path.join(tmpdir, 'project.json')
        transcripts_dir = os.path.join(tmpdir, 'transcripts')
        os.makedirs(transcripts_dir)

        manifest = {
            'participants': {
                'p1s1': {
                    'transcript_path': 'p1s1.txt',
                    'stages': {'transcript_prep': {'status': 'pending', 'output_path': None}}
                }
            }
        }
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f)

        transcript_path = os.path.join(transcripts_dir, 'p1s1.txt')
        with open(transcript_path, 'w', encoding='utf-8') as f:
            f.write('Participant 1, Suggestion 1 (Scored 4/5)\n')
            f.write('Kevin Sheldrake: Test question?\n')
            f.write('P1: Test answer\n')

        prep = TranscriptPrep(manifest_path, transcripts_dir)
        result = prep.prep('p1s1')

        # Should succeed
        assert result['p1s1']['success'], "Should succeed with valid transcript"

        # Verify manifest updated to done
        with open(manifest_path, 'r') as f:
            updated_manifest = json.load(f)

        stage = updated_manifest['participants']['p1s1']['stages']['transcript_prep']
        assert stage['status'] == 'done', "Status should be 'done'"
        assert stage['output_path'] == 'p1s1.txt', "output_path should be set"

        print("[PASS] test_valid_transcript_done_status passed")


def run_all_tests():
    """Run all tests."""
    tests = [
        test_bom_stripping,
        test_double_space_normalisation,
        test_speaker_label_capitalisation,
        test_crlf_to_lf,
        test_malformed_header_error,
        test_valid_transcript_done_status,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"[FAIL] {test.__name__} failed: {e}")
        except Exception as e:
            failed += 1
            print(f"[ERROR] {test.__name__} error: {e}")

    print(f"\n{'='*60}")
    print(f"Test Results: {passed} passed, {failed} failed")
    print(f"{'='*60}")

    return failed == 0


if __name__ == '__main__':
    success = run_all_tests()
    exit(0 if success else 1)

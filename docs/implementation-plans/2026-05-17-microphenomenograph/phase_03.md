# Microphenomenograph Implementation Plan — Phase 3: Transcript Prep

**Goal:** Implement `mpi-transcript-prep` skill that validates and normalises raw transcripts into clean numbered-utterance format before analysis.

**Architecture:** The skill reads a transcript, validates its structure (header, line numbering, speaker labels, encoding), fixes common real-world issues (BOM, double spaces, inconsistent capitalisation), writes the cleaned transcript back, and updates the manifest stage to `done`. No Python code — pure Claude Code skill.

**Tech Stack:** Markdown skill

**Scope:** Phase 3 of 8

**Codebase verified:** 2026-05-17 — stub `skills/mpi-transcript-prep/SKILL.md` exists from Phase 1.

---

## Acceptance Criteria Coverage

This phase does not introduce new numbered ACs from the design. It is a prerequisite for Phase 4 (diachronic analysis). The design's "Done when" criterion is: OSF transcripts pass prep without errors; malformed transcript produces actionable error output; manifest updated correctly.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: mpi-transcript-prep SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md` (replace stub)

**Implementation:**

```markdown
---
name: mpi-transcript-prep
description: Use when running /mpi transcript-prep — validates and normalises transcript files; strips BOM, fixes spacing, confirms utterance numbering; updates manifest stage status to done
user-invocable: false
---
# mpi-transcript-prep

Validate and normalise one or more transcript files. Updates `.mpi/project.json` stage
`transcript_prep` to `done` for each successfully processed transcript.

## Input

Receives either:
- A specific participant key (`pNsN`) from the `/mpi transcript-prep pNsN` invocation
- No argument (process all participants with `transcript_prep` status `pending`)

Read transcript path from `.mpi/project.json` → `participants[pNsN].transcript_path`.

## Validation rules

**Header (line 1):** Must match `^Participant \d+, Suggestion \d+ \(Scored \d+/5\)$`

**Utterances:** Each non-blank line after the header must begin with either:
- A speaker label: `Kevin Sheldrake:` or `P<N>:` (case-insensitive: `kevin sheldrake:`, `p1:` etc.)
- Or be a continuation of the previous utterance (i.e., no new speaker label — treat as
  the same utterance)

**Utterance numbering:** The prep skill does NOT assign utterance numbers. In the OSF
transcripts each line is a separate utterance, and utterance numbers in analyses are
assigned by the analyst (not sequential file line numbers). The prep skill does not
modify or add utterance numbers.

Instead it:
1. Validates the header format
2. Strips BOM characters (`﻿`) if present at start of file
3. Normalises whitespace: replace double spaces with single space, strip trailing spaces
4. Normalises speaker label capitalisation: `kevin sheldrake:` → `Kevin Sheldrake:`,
   `p1:` → `P1:`
5. Removes Windows line endings (`\r\n` → `\n`)
6. Reports any lines that look malformed (contain neither a recognised speaker label
   nor appear to be continuation text)

## Error conditions

- Header mismatch: `ERROR [pNsN]: line 1 does not match expected header format`
- File not found: `ERROR [pNsN]: transcript file not found at <path>`
- Unrecognisable speaker label (warn, not error): `WARN [pNsN]: line N: unrecognised speaker label pattern`

On ERROR, do NOT update manifest — leave stage as `pending`. On WARN, proceed and update manifest.

## Output

Write cleaned transcript back to the same path (overwrite). Then update manifest:
```json
"transcript_prep": { "status": "done", "output_path": "<same transcript path>" }
```

Report per-transcript: `✓ pNsN: transcript cleaned (N warnings)`

## Steps

1. Load manifest from `.mpi/project.json`
2. For each target participant:
   a. Read transcript file
   b. Strip BOM if present
   c. Validate header (line 1)
   d. Normalise whitespace and speaker labels
   e. Write cleaned content back
   f. Update manifest stage to `done` (or leave `pending` on ERROR)
3. Write updated manifest
4. Print summary report
```

**Note:** This is a normalisation/validation skill. The OSF transcripts are already in good shape (they were used for published research). The primary value of this skill is for user-provided transcripts that may have encoding or formatting issues.
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify transcript prep on OSF data

**Prerequisite:** Phase 2 complete (`.mpi/project.json` exists in test working directory).

**Step 1: Run transcript prep on one participant**

In Claude Code with plugin installed, from the test working directory:
```
/mpi transcript-prep p1s1
```

Expected:
- No ERROR output
- Manifest updated: `p1s1.stages.transcript_prep.status == "done"`
- Transcript file unchanged in content (OSF transcripts are clean)

**Step 2: Verify manifest update**

```bash
python -c "
import json
with open('.mpi/project.json') as f:
    m = json.load(f)
stage = m['participants']['p1s1']['stages']['transcript_prep']
print('Status:', stage['status'])
print('Output path:', stage['output_path'])
"
```

Expected:
```
Status: done
Output path: transcripts/p1s1.txt
```

**Step 3: Test malformed transcript**

```bash
echo "BROKEN HEADER" > transcripts/p99s1.txt
echo "P99: some utterance" >> transcripts/p99s1.txt
```

Add p99s1 to manifest manually:
```bash
python -c "
import json
with open('.mpi/project.json') as f:
    m = json.load(f)
m['participants']['p99s1'] = {
    'participant': 99, 'suggestion': 1, 'score': 3, 'score_category': 'moderate',
    'transcript_path': 'transcripts/p99s1.txt',
    'stages': {
        'transcript_prep': {'status': 'pending', 'output_path': None},
        'diachronic': {'status': 'pending', 'output_path': None},
        'synchronic': {'status': 'pending', 'output_path': None}
    }
}
with open('.mpi/project.json', 'w') as f:
    json.dump(m, f, indent=2)
"
```

Run:
```
/mpi transcript-prep p99s1
```

Expected: `ERROR [p99s1]: line 1 does not match expected header format`. Manifest NOT updated (p99s1 transcript_prep remains `pending`).

**Step 4: Commit**

```bash
cd C:\microphenomenograph
git add microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md
git commit -m "feat: implement mpi-transcript-prep skill"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

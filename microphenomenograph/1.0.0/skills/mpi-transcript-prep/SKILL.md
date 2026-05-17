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

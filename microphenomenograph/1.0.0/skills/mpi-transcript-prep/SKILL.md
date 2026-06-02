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

Write cleaned transcript back to the same path (overwrite).

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

## Closure (mandatory)

Each transcript-prep substep closes its own four-part transaction via `mpi_step.py close`.
The orchestrator owns all three substeps (no LLM calls, no prompt artifact for any).

| Substep | Actor | Artifacts | Notes |
|---------|-------|-----------|-------|
| `transcript_prep.hash_raw` | orchestrator | SHA256 entry in manifest | Marks raw file read-only. SHA recorded as `study.transcripts[transcript_id].raw_sha256`. |
| `transcript_prep.normalize` | orchestrator | `transcripts/normalized/<transcript_id>.txt`, `transcripts/diff/<transcript_id>.diff` | Diff from raw → normalized is committed alongside for reviewability. |
| `transcript_prep.register_offsets` | orchestrator | `transcripts/offsets/<transcript_id>.json` | Maps normalized line numbers to raw byte ranges. SHA recorded in manifest. |

**Commit message format:** `mpi: orchestrator transcript_prep.<substep> <transcript_id>`

**Raw-immutability contract:** The raw file at `transcripts/raw/<transcript_id>.txt` is
never overwritten. `hash_raw` makes it read-only (`chmod 0444` on POSIX; read-only attribute
on Windows). Any subsequent close that detects SHA mismatch on the raw file exits with
`raw_transcript_mutated`. The normalised file is a derived artifact; only the raw is the
ground truth for `utterance_refs`.

**Note (divergence from pre-Plan-1 behaviour):** The pre-existing SKILL.md above specifies
"Write cleaned transcript back to the same path (overwrite)." This is superseded by the
new contract: the normalised output goes to `transcripts/normalized/<transcript_id>.txt`;
the raw is never overwritten. Executors should follow the Closure section, not the old
"Output" section above it.

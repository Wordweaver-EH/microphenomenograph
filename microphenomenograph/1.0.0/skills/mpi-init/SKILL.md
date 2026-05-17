---
name: mpi-init
description: Use when running /mpi init — scans transcripts/, parses participant headers, writes .mpi/project.json manifest
user-invocable: false
---
# mpi-init

Bootstrap a self-contained MPI run directory. Every pipeline run lives in its own
isolated folder containing its own transcripts, manifest, analyses, logs, and git
history. Runs never share state.

## Run directory contract

Each run is rooted at a `RUN_DIR` (e.g. `runs/phase1-2026-05-17/`). After init, its
layout is:

```
RUN_DIR/
├── transcripts/         # copied from source — never edited in place
├── analyses/            # all stage outputs land here
├── .mpi/
│   ├── project.json     # manifest
│   └── reasoning.log
└── .gitignore           # ignores .mpi/
```

All subsequent `/mpi <stage>` commands MUST be run from inside `RUN_DIR`. The manifest,
outputs, and git commits are all scoped to that directory.

## Init resolution

`/mpi init` accepts two optional flags:
- `--run <RUN_DIR>` — path (absolute or CWD-relative) to the run directory to create or
  resume. If omitted, prompt.
- `--transcripts <SRC>` — path to source transcripts to copy in. If omitted AND
  `RUN_DIR/transcripts/` is empty/missing, prompt.

Resolution algorithm:

1. **Determine `RUN_DIR`:**
   - If `--run` given: use it.
   - Else: prompt the user with AskUserQuestion:
     > "Name for this run directory (will be created if absent, e.g.
     > `runs/phase1-2026-05-17/`):"
   - If `RUN_DIR` already exists AND contains `.mpi/project.json`: this is a resume —
     skip the transcripts-copy step and re-scan the existing `transcripts/` only.
   - If `RUN_DIR` exists but has no manifest: treat as fresh init inside it.
   - If `RUN_DIR` does not exist: create it.

2. **Determine source transcripts (fresh init only):**
   - If `--transcripts` given: use it.
   - Else: prompt:
     > "Path to source directory of transcript `.txt` files (will be copied into
     > `RUN_DIR/transcripts/`):"
   - Validate: path exists, contains ≥1 `.txt` file. Re-prompt on failure with the
     specific reason.

3. **Copy transcripts:** create `RUN_DIR/transcripts/` if absent, copy every `.txt` from
   `SRC` into it. Do not modify originals.

4. **Refuse cross-contamination:** if the user supplies a `RUN_DIR` that already
   contains a non-empty `transcripts/` AND a different `--transcripts` source, STOP and
   ask whether to (a) overwrite, (b) skip copy and resume, or (c) abort. Never silently
   overwrite.

5. **Change working directory:** all remaining steps and all downstream `/mpi`
   subcommands operate with `RUN_DIR` as CWD. Print to the user:
   > "Run directory: <absolute RUN_DIR>. cd there before running further /mpi commands."

## Auto-created files

Inside `RUN_DIR`:
- `.mpi/` directory
- `.mpi/project.json` (manifest, see schema below)
- `.mpi/reasoning.log` (empty if new)
- `.gitignore` containing `.mpi/` (if not present)
- `analyses/` directory (empty, populated by later stages)

## Header format

Every transcript file MUST begin with a line that contains the participant number,
suggestion number, and score. The OSF data has two variant formats:

- **Standard** (most files): `Participant 1, Suggestion 2 (Scored 3/5)`
- **Missing comma** (p6, p7): `Participant 6 Suggestion 1 (Scored 4/5)` — no comma after participant number
- **Annotated** (p11s1, p11s2): `Participant 11, Suggestion 1 modified (Scored 0/5) [...]` — extra text after suggestion number and after score

Parse with the permissive regex:
```
^Participant (\d+),?\s+Suggestion (\d+)(?:\s+\w+)*\s*\(Scored (\d+)/5\)
```

For example: `Participant 1, Suggestion 2 (Scored 3/5)` → p=1, s=2, score=3.
Also: `Participant 6 Suggestion 1 (Scored 4/5)` → p=6, s=1, score=4.
Also: `Participant 11, Suggestion 1 modified (Scored 0/5) [...]` → p=11, s=1, score=0.

- If the header does not match even the permissive regex, produce a named error:
  `ERROR: <filename>: invalid header format. Expected "Participant N[,] Suggestion N (Scored N/5)[...]", got: "<first line>"`
  Do NOT silently produce wrong values. Do NOT continue processing this file.

## Manifest location

Write `RUN_DIR/.mpi/project.json`. All paths inside the manifest (`transcript_path`,
`output_path`) are relative to `RUN_DIR`.

## Manifest schema

```json
{
  "version": "1.0",
  "mode": "assisted",
  "created_at": "<ISO 8601 timestamp>",
  "updated_at": "<ISO 8601 timestamp>",
  "participants": {
    "p1s1": {
      "participant": 1,
      "suggestion": 1,
      "score": 4,
      "score_category": "high",
      "transcript_path": "transcripts/p1s1.txt",
      "stages": {
        "transcript_prep": { "status": "pending", "output_path": null },
        "diachronic": { "status": "pending", "output_path": null },
        "synchronic": { "status": "pending", "output_path": null }
      }
    }
  },
  "cross_participant_stages": {
    "generic_diachronic": { "status": "pending", "output_path": null },
    "generic_synchronic": { "status": "pending", "output_path": null },
    "global_synchronic": { "status": "pending", "output_path": null },
    "hypothesis": { "status": "pending", "output_path": null }
  },
  "review_queue_path": ".mpi/review-queue.md",
  "reasoning_log_path": ".mpi/reasoning.log",
  "git_commit": false
}
```

Score categories:
- 0–1 → "low"
- 2–3 → "moderate"
- 4–5 → "high"

## Mode flag

If `/mpi init --yolo` is passed, set `"mode": "yolo"` in manifest. Default is `"assisted"`.

## Reasoning log initialisation

Create `.mpi/reasoning.log` if it does not exist (empty file). Do not overwrite existing log.

## Re-run behaviour (idempotency)

If `.mpi/project.json` already exists:
1. Read existing manifest
2. For each transcript found:
   - If participant already in manifest AND any stage has `status: "done"`, **preserve** all stage statuses
   - If participant NOT in manifest, add with all stages `pending`
3. Remove participants from manifest that no longer have a transcript file
4. Update `updated_at` timestamp
5. Write updated manifest

This means running init twice never resets completed work.

## Steps

1. Resolve `RUN_DIR` per "Init resolution" (flag or prompt). Create if absent.
2. Resolve source transcripts (fresh init only) and copy `.txt` files into
   `RUN_DIR/transcripts/`.
3. Create `RUN_DIR/.mpi/`, `RUN_DIR/analyses/`, `RUN_DIR/.gitignore` (with `.mpi/`) if
   absent.
4. Load existing `RUN_DIR/.mpi/project.json` if present (resume case).
5. List all `.txt` files in `RUN_DIR/transcripts/`.
6. For each file, read line 1 and parse the header regex.
   - On parse failure: print error and skip this file (do not abort entire run).
7. Build the participant entry (new or merge with existing per idempotency rules).
8. Atomically write manifest: `RUN_DIR/.mpi/project.json.tmp` → rename to
   `RUN_DIR/.mpi/project.json`.
9. Report: "Initialised N participants in `<RUN_DIR>`. M already had completed stages
   (preserved). Run subsequent /mpi commands from `<RUN_DIR>`."

## Output

Report a table to terminal:

```
| Participant | Score | Category | Stages |
|---|---|---|---|
| p1s1 | 4 | high | all pending |
| p1s2 | 3 | moderate | all pending |
...
```

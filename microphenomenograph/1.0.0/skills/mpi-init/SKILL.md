---
name: mpi-init
description: Use when running /mpi init — scans transcripts/, parses participant headers, writes .mpi/project.json manifest
user-invocable: false
---
# mpi-init

Scan all `.txt` files in `transcripts/` (in the current working directory), parse their
headers, and write or update `.mpi/project.json`.

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

Write `.mpi/project.json` (relative to current working directory). Create `.mpi/` if it
does not exist. `.mpi/` is gitignored (see `.gitignore`).

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

1. Create `.mpi/` if not present
2. Check for existing `.mpi/project.json` and load it if present
3. List all `.txt` files in `transcripts/`
4. For each file, read line 1 and parse the header regex
   - On parse failure: print error and skip this file (do not abort entire run)
5. Build the participant entry (new or merge with existing)
6. Write updated manifest to `.mpi/project.json`
7. Report: "Initialised N participants. M already had completed stages (preserved)."

## Output

Report a table to terminal:

```
| Participant | Score | Category | Stages |
|---|---|---|---|
| p1s1 | 4 | high | all pending |
| p1s2 | 3 | moderate | all pending |
...
```

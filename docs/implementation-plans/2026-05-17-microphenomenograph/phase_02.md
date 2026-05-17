# Microphenomenograph Implementation Plan — Phase 2: Init, Status & Manifest

**Goal:** Implement `/mpi init` (parses transcript headers, writes `.mpi/project.json`) and `/mpi status` (renders progress table). Route both subcommands from `/mpi`.

**Architecture:** mpi-init skill reads all `.txt` files from `transcripts/`, parses the `Participant N, Suggestion N (Scored N/5)` header, builds and writes the manifest. mpi-status skill reads the manifest and renders a markdown table. The `/mpi` command routes subcommands to the appropriate skill.

**Tech Stack:** Markdown skills (interpreted by Claude Code), JSON manifest

**Scope:** Phase 2 of 8

**Codebase verified:** 2026-05-17 — stubs created in Phase 1; `microphenomenograph/1.0.0/` tree exists.

---

## Acceptance Criteria Coverage

This phase implements and tests:

### microphenomenograph.AC2: /mpi init parses transcripts and writes manifest
- **microphenomenograph.AC2.1 Success:** Header `"Participant 1, Suggestion 2 (Scored 3/5)"` parsed to p=1, s=2, score=3
- **microphenomenograph.AC2.2 Success:** All OSF transcripts produce valid `.mpi/project.json` with all stages `pending`
- **microphenomenograph.AC2.3 Failure:** Malformed header produces named error, not silent wrong value
- **microphenomenograph.AC2.4 Edge:** Re-running init on existing manifest preserves `done` stages, adds new participants

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: mpi-init SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md` (replace stub)

**Implementation:**

Replace the stub with:

```markdown
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
```

**Verifies:** microphenomenograph.AC2.1 (header parsing), microphenomenograph.AC2.2 (all transcripts → valid manifest), microphenomenograph.AC2.3 (malformed header error), microphenomenograph.AC2.4 (re-run preserves done stages)
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: mpi-status SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-status/SKILL.md` (replace stub)

**Implementation:**

```markdown
---
name: mpi-status
description: Use when running /mpi status — reads .mpi/project.json and renders a participant × stage completion table
user-invocable: false
---
# mpi-status

Read `.mpi/project.json` and render a progress overview.

## If no manifest exists

Print: `No .mpi/project.json found. Run /mpi init first.`

## Progress table format

Render a markdown table with one row per participant/suggestion, one column per stage.
Use symbols: ✓ (done), ⧖ (pending), ✗ (flagged).

```
| Participant | Score | Category | prep | diachronic | synchronic |
|---|---|---|---|---|---|
| p1s1 | 4 | high | ✓ | ✓ | ⧖ |
| p1s2 | 3 | moderate | ⧖ | ⧖ | ⧖ |
```

Then render cross-participant stages:

```
Cross-participant stages:
| Stage | Status |
|---|---|
| generic_diachronic | ⧖ |
| generic_synchronic | ⧖ |
| global_synchronic | ⧖ |
| hypothesis | ⧖ |
```

## Summary line

Print: `N/M stages complete across all participants. Review queue: K items.`

Count items in `.mpi/review-queue.md` if it exists (count `##` headers as items).
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Update /mpi command routing

**Files:**
- Modify: `microphenomenograph/1.0.0/commands/mpi.md` (replace stub)

**Implementation:**

```markdown
---
name: mpi
description: MPI analysis pipeline — orchestrates transcript preparation through hypothesis generation
---
# /mpi

Microphenomenological Interview (MPI) analysis pipeline.

## Usage

```
/mpi <subcommand> [options]
```

## Subcommands

| Subcommand | Description | Skill |
|---|---|---|
| `init` | Scan transcripts/, parse headers, write manifest | mpi-init |
| `status` | Show pipeline progress table | mpi-status |
| `transcript-prep [pNsN]` | Normalise transcript(s) | mpi-transcript-prep |
| `diachronic [pNsN]` | Run IDU analysis (per-participant) | mpi-diachronic |
| `synchronic [pNsN]` | Run ISU analysis (per-participant) | mpi-synchronic |
| `generic-diachronic` | Cross-participant diachronic aggregation | mpi-generic-diachronic |
| `generic-synchronic` | Cross-participant synchronic aggregation | mpi-generic-synchronic |
| `global-synchronic` | Global synchronic synthesis | mpi-global-synchronic |
| `hypothesis` | Generate causal research hypotheses | mpi-hypothesis |
| `kappa [dir1] [dir2]` | Compute Cohen's κ inter-rater reliability | mpi-kappa |
| `all` | Run full pipeline (respects mode setting) | orchestration logic |

## Mode

Default mode is `assisted` (human confirms each stage). Use `--yolo` to enable automated
parallel execution: `/mpi all --yolo`

## Routing

When the user runs `/mpi <subcommand>`, activate the corresponding skill listed above.

If the subcommand is unrecognised, print:

```
Unknown subcommand: '<subcommand>'

Usage: /mpi <subcommand> [options]

Available subcommands: init, status, transcript-prep, diachronic, synchronic,
generic-diachronic, generic-synchronic, global-synchronic, hypothesis, kappa, all
```

Subcommands `transcript-prep`, `diachronic`, and `synchronic` accept an optional
participant filter (`pNsN`). If no filter given, process all participants with
`pending` status for that stage.

## Prerequisites

All stages other than `init` require `.mpi/project.json` to exist. If missing, print:
`No .mpi/project.json found. Run /mpi init first.`
```

**Verifies:** microphenomenograph.AC1.3 (unknown subcommand produces usage message)
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify init and status on OSF transcripts

**Prerequisite:** Phase 1 complete (transcripts at `microphenomenograph/1.0.0/examples/transcripts/`).

**Step 1: Run `/mpi init` targeting the examples/transcripts directory**

Create a test working directory:
```bash
mkdir -p C:/Temp/mpi-test/transcripts
cp C:/microphenomenograph/microphenomenograph/1.0.0/examples/transcripts/*.txt C:/Temp/mpi-test/transcripts/
cd C:/Temp/mpi-test
```

Then in Claude Code with the plugin installed, run:
```
/mpi init
```

Expected:
- `.mpi/project.json` created
- 39 participants listed (p1s1–p7s3 and p8s1–p13s3)
- All stages `pending`
- Participant headers correctly parsed (check p1s1: score=4, category=high)

**Step 2: Verify manifest structure**

```bash
python -c "
import json
with open('.mpi/project.json') as f:
    m = json.load(f)
print('Version:', m['version'])
print('Participants:', len(m['participants']))
p = m['participants']['p1s1']
print('p1s1 participant:', p['participant'])
print('p1s1 suggestion:', p['suggestion'])
print('p1s1 score:', p['score'])
print('p1s1 category:', p['score_category'])
print('p1s1 transcript_path:', p['transcript_path'])
print('All stages pending:', all(v['status'] == 'pending' for v in p['stages'].values()))
"
```

Expected output:
```
Version: 1.0
Participants: 39
p1s1 participant: 1
p1s1 suggestion: 1
p1s1 score: 4
p1s1 category: high
p1s1 transcript_path: transcripts/p1s1.txt
All stages pending: True
```

**Step 3: Test malformed header detection**

Create a malformed transcript:
```bash
echo "Bad header format" > transcripts/p99s1.txt
echo "Some content" >> transcripts/p99s1.txt
```

Run `/mpi init` again.

Expected: Error message like `ERROR: transcripts/p99s1.txt: invalid header format...`. The manifest does NOT contain `p99s1`. Other participants still processed.

**Step 4: Test re-run idempotency**

Manually set one stage to done in the manifest:
```bash
python -c "
import json
with open('.mpi/project.json') as f:
    m = json.load(f)
m['participants']['p1s1']['stages']['diachronic']['status'] = 'done'
with open('.mpi/project.json', 'w') as f:
    json.dump(m, f, indent=2)
print('Set p1s1 diachronic to done')
"
```

Run `/mpi init` again.

Expected: p1s1 diachronic stage remains `done`. New participants added if any. Report mentions "M already had completed stages (preserved)."

**Step 5: Run `/mpi status`**

```
/mpi status
```

Expected: Progress table renders with p1s1 diachronic showing ✓, others showing ⧖.

**Step 6: Commit**

```bash
cd C:\microphenomenograph
git add microphenomenograph/1.0.0/skills/mpi-init/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-status/SKILL.md
git add microphenomenograph/1.0.0/commands/mpi.md
git commit -m "feat: implement mpi-init, mpi-status, and mpi command routing"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

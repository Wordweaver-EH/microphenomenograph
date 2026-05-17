# Microphenomenograph Implementation Plan — Phase 8: Full Pipeline Orchestration & Yolo Mode

**Goal:** Wire up `/mpi all` to run the complete pipeline; implement yolo mode with parallel subagent fan-out, per-stage git commits, resume logic, terminal progress table, and `.mpi/reasoning.log`.

**Architecture:** The `/mpi` command's `all` subcommand reads the manifest, determines which stages are pending, and orchestrates them in order. In yolo mode, per-participant stages (transcript-prep, diachronic, synchronic) are parallelised via simultaneous subagent calls. After each stage completes, the manifest is written atomically and git commits. Ctrl+C safety: manifest is only updated after successful commit, so an interrupted run leaves manifest consistent.

**Tech Stack:** Markdown command (Claude Code), manifest JSON state machine

**Scope:** Phase 8 of 8

**Codebase verified:** 2026-05-17 — all skills and agents implemented in Phases 2–7. `commands/mpi.md` routes subcommands. This phase upgrades it with `all` orchestration and finalises yolo/assisted mode logic.

---

## Acceptance Criteria Coverage

### microphenomenograph.AC8: Yolo mode is automated and resumable
- **microphenomenograph.AC8.1 Success:** `/mpi all` in yolo mode runs all stages without human input
- **microphenomenograph.AC8.2 Success:** One git commit per participant/stage completion with message `"mpi: pNsN {stage} analysis"`
- **microphenomenograph.AC8.3 Success:** Ctrl+C mid-run leaves manifest consistent; re-running `/mpi all` skips completed stages
- **microphenomenograph.AC8.4 Success:** `.mpi/reasoning.log` contains entry for every analysis decision
- **microphenomenograph.AC8.5 Success:** Terminal progress table renders with completion status and avg confidence per participant

### microphenomenograph.AC9: Assisted mode requires human confirmation
- **microphenomenograph.AC9.1 Success:** Each participant's output shown to human before next participant processed
- **microphenomenograph.AC9.2 Success:** Human rejection of an output re-runs that participant's stage, not the whole pipeline

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Update /mpi command with `all` orchestration

**Files:**
- Modify: `microphenomenograph/1.0.0/commands/mpi.md` (add `all` orchestration section)

**Add to `commands/mpi.md` after the routing table:**

```markdown
## /mpi all — Full pipeline orchestration

Running `/mpi all` executes the complete pipeline in dependency order:

### Stage order
1. `transcript-prep` — all participants with `pending` status (parallel in yolo)
2. `diachronic` — all participants with prep `done` (parallel in yolo)
3. `synchronic` — all participants with diachronic `done` (parallel in yolo)
4. `generic-diachronic` — after all diachronic stages done
5. `generic-synchronic` — after all synchronic stages done
6. `global-synchronic` — after generic-synchronic done
7. `hypothesis` — after global-synchronic done

### Resume logic
Read `.mpi/project.json` before each stage. Skip any stage where status is already `done`.
This means:
- Interrupted runs resume from where they left off
- Re-running `/mpi all` is safe and idempotent

**Downstream cascade on re-run:** If a per-participant stage (diachronic, synchronic) is
reset to `pending` (e.g., by the user manually or via assisted mode rejection), the
corresponding downstream cross-participant stages are also reset to `pending`:
- Any diachronic reset → `generic_diachronic` reset to `pending`
- Any synchronic reset → `generic_synchronic`, `global_synchronic`, `hypothesis` reset to `pending`

This cascade happens at the START of `/mpi all`: read manifest, check for `done`
per-participant stages, verify that all prerequisite stages for each `done` cross-participant
stage are still `done`. If not, reset the cross-participant stage to `pending`.

### Mode flag
- `/mpi all` — uses mode from manifest (default: `assisted`)
- `/mpi all --yolo` — override to yolo mode (updates manifest mode to `yolo`)

### Yolo mode execution

In yolo mode for per-participant stages (transcript-prep, diachronic, synchronic):

Emit multiple skill invocations in a SINGLE assistant turn — one per pending participant.
Do NOT wait for one to complete before starting the next. Claude Code will execute them
concurrently. After ALL subagents for a batch complete:
1. For each completed participant:
   a. Write output file
   b. Append to `.mpi/reasoning.log`
   c. `git add <output_file>`
   d. `git commit -m "mpi: pNsN {stage} analysis"`
   e. Update manifest entry to `done` with output path
2. Write manifest
3. Show progress table (see below)
4. Proceed to next stage

Ctrl+C safety: manifest is written ONLY after the git commit succeeds for a given
participant. If Ctrl+C interrupts after commit but before manifest write, the next run
will re-process that participant (producing a duplicate — acceptable). If Ctrl+C before
commit, the stage stays `pending` in the manifest — correct.

### Assisted mode execution

In assisted mode for per-participant stages, process one participant at a time:
1. Run the skill for participant N
2. Show output to user
3. Ask: "Accept this output and proceed to the next participant?"
   - If yes: commit + update manifest + proceed
   - If no: ask which specific change is needed, re-run ONLY this participant (not the whole stage)
4. After all participants in a stage, show progress table and confirm cross-participant stage

### Progress table

After each batch of per-participant completions, render:

```
MPI Pipeline Progress
=====================
| Participant | Score | prep | diachronic | synchronic | avg confidence |
|---|---|---|---|---|---|
| p1s1 | 4 (high) | ✓ | ✓ | ✓ | 4.2 |
| p1s2 | 3 (moderate) | ✓ | ✓ | ⧖ | 3.8 |
| p2s1 | 5 (high) | ✓ | ⧖ | ⧖ | — |
...

Cross-participant stages:
generic-diachronic: ⧖  generic-synchronic: ⧖  global-synchronic: ⧖  hypothesis: ⧖
```

Average confidence: computed from all IDU/ISU confidence scores in the diachronic/synchronic
output files. Parse the Confidence column from each `analyses/pNsN-diachronic.md` table.

### Reasoning log

Every analysis decision is appended to `.mpi/reasoning.log`. Each skill that invokes
mpi-analyst or mpi-cross-analyst appends:
```
[<ISO timestamp>] pNsN <stage>: <reasoning_summary>. N units identified. K flagged.
```

(This is already specified in Phases 4–6 skill implementations. Phase 8 confirms the
log must exist and contain entries for all completed stages.)

### Manifest atomicity

The manifest (`project.json`) is the source of truth. Rules:
- Each participant's stage entry is updated to `done` ONLY after its git commit succeeds
- Cross-participant stages updated to `done` ONLY after their commit succeeds
- The manifest is written as a complete JSON file (not append-only) — use atomic write:
  write to `.mpi/project.json.tmp` then rename to `.mpi/project.json`
```

**Verifies:** microphenomenograph.AC8.1, microphenomenograph.AC8.2, microphenomenograph.AC8.3, microphenomenograph.AC8.4, microphenomenograph.AC8.5, microphenomenograph.AC9.1, microphenomenograph.AC9.2
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update manifest mode field and reasoning log initialisation

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md` (add `--yolo` flag handling)

**Add to mpi-init SKILL.md** — after the manifest schema section:

```markdown
## Mode flag

If `/mpi init --yolo` is passed, set `"mode": "yolo"` in manifest. Default is `"assisted"`.

## Reasoning log initialisation

Create `.mpi/reasoning.log` if it does not exist (empty file). Do not overwrite existing log.
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Verify full pipeline on OSF data in yolo mode

**Prerequisite:** Phases 1–7 complete. Plugin installed. Fresh test working directory with OSF transcripts.

**Step 1: Setup**

```bash
mkdir -p C:/Temp/mpi-full-test
cd C:/Temp/mpi-full-test
mkdir -p transcripts
cp C:/microphenomenograph/microphenomenograph/1.0.0/examples/transcripts/p1s*.txt transcripts/
cp C:/microphenomenograph/microphenomenograph/1.0.0/examples/transcripts/p2s*.txt transcripts/
git init
```

**Step 2: Init in yolo mode**

In Claude Code from `C:/Temp/mpi-full-test`:
```
/mpi init --yolo
```

Expected:
- `.mpi/project.json` created with mode: yolo
- `.mpi/reasoning.log` created (empty)
- 6 participants listed (p1s1, p1s2, p1s3, p2s1, p2s2, p2s3)

**Step 3: Run full pipeline**

```
/mpi all
```

Expected sequence:
1. transcript-prep: 6 participants processed in parallel → 6 commits `mpi: pNsN transcript_prep analysis`
2. diachronic: 6 participants in parallel → 6 commits
3. synchronic: 6 participants in parallel → 6 commits
4. generic-diachronic → 1 commit
5. generic-synchronic → 1 commit
6. global-synchronic → 1 commit
7. hypothesis → 1 commit

**Verify commit log:**

```bash
git log --oneline
```

Expected: At least 21 commits (6+6+6+1+1+1), all with message format `mpi: pNsN <stage> analysis` (per-participant) or `mpi: <stage> analysis` (cross-participant).

**Step 4: Verify reasoning log has entries**

```bash
wc -l .mpi/reasoning.log
grep "diachronic" .mpi/reasoning.log | head -3
```

Expected: At least 12 entries (6 diachronic + 6 synchronic). Each entry has ISO timestamp.

**Step 5: Verify progress table renders**

The terminal progress table should have appeared after each stage batch. Verify manually during the run.

**Step 6: Test resume after interruption**

After step 3 completes, manually reset one participant:
```bash
python -c "
import json
with open('.mpi/project.json') as f:
    m = json.load(f)
m['participants']['p1s1']['stages']['synchronic']['status'] = 'pending'
m['participants']['p1s1']['stages']['synchronic']['output_path'] = None
with open('.mpi/project.json', 'w') as f:
    json.dump(m, f, indent=2)
print('Reset p1s1 synchronic to pending')
"
```

Run `/mpi all` again.

Expected:
- transcript-prep and diachronic stages SKIPPED (already done)
- synchronic runs for p1s1 only (the one reset to pending)
- Other synchronic stages SKIPPED
- Cross-participant stages SKIPPED (already done? No — re-run them since a per-participant stage changed)

Actually: the behaviour for cross-participant stages when a per-participant stage is re-run should be:
- If p1s1 synchronic was re-run, generic-synchronic should re-run (it's downstream)
- Set cross-participant stages to `pending` when any upstream stage is reset

Document this in the `all` command: "After re-running a per-participant stage, downstream cross-participant stages are also reset to pending."

**Step 7: Verify assisted mode confirmation**

Reset `C:/Temp/mpi-full-test` manifest mode to `assisted`. Run `/mpi all`. Expected: After p1s1 diachronic, user is shown the output and asked to confirm before p1s2 diachronic begins.

**Step 8: Commit all Phase 8 changes**

```bash
cd C:\microphenomenograph
git add microphenomenograph/1.0.0/commands/mpi.md
git add microphenomenograph/1.0.0/skills/mpi-init/SKILL.md
git commit -m "feat: implement /mpi all orchestration, yolo mode, resume logic, and progress table"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Final end-to-end verification on full OSF dataset

**Step 1: Run on all 39 OSF participants in yolo mode**

```bash
mkdir -p C:/Temp/mpi-osf-full
cd C:/Temp/mpi-osf-full
mkdir -p transcripts
cp C:/microphenomenograph/microphenomenograph/1.0.0/examples/transcripts/*.txt transcripts/
git init
```

In Claude Code:
```
/mpi init --yolo
/mpi all
```

Expected:
- All 39 participants processed
- `analyses/` directory contains: 39 diachronic files + 39 synchronic files + generic-diachronic + generic-synchronic + global-synchronic + hypotheses
- `.mpi/review-queue.md` contains entries for any flagged IDUs/ISUs
- git log shows per-participant commits

**Step 2: Verify no Phase 2 contamination in few-shot pool**

```bash
grep -r "phase2" .mpi/reasoning.log
```

Expected: No matches. Phase 2 analyses never appear in prompts.

**Step 3: Verify status display**

```
/mpi status
```

Expected: All 39 participants show ✓ for prep, diachronic, synchronic. All cross-participant stages show ✓.

**Step 4: Final commit**

```bash
cd C:\microphenomenograph
git add -A
git commit -m "feat: complete microphenomenograph plugin implementation"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

# Microphenomenograph Implementation Plan — Phase 5: Generic & Global Cross-Participant Analysis

**Goal:** Implement `mpi-cross-analyst` subagent and the three cross-participant skills: `mpi-generic-diachronic`, `mpi-generic-synchronic`, and `mpi-global-synchronic`.

**Architecture:** `mpi-cross-analyst` reads all per-participant markdown outputs for a stage, identifies common patterns across score categories (low/moderate/high), and produces a grouped output table. Each of the three skills invokes the cross-analyst with the appropriate stage's outputs.

**Tech Stack:** Markdown skills and agents (Claude Code)

**Scope:** Phase 5 of 8

**Codebase verified:** 2026-05-17 — stubs exist for all three skills and the mpi-cross-analyst agent.

---

## Acceptance Criteria Coverage

### microphenomenograph.AC5: Cross-participant stages aggregate correctly
- **microphenomenograph.AC5.1 Success:** Generic diachronic groups IDUs by score category across all participants
- **microphenomenograph.AC5.2 Success:** Global synchronic output references source participant and suggestion for each row
- **microphenomenograph.AC5.3 Failure:** Running `generic-diachronic` before all per-participant diachronic stages complete produces warning listing incomplete participants

---

<!-- START_SUBCOMPONENT_A (tasks 1-4) -->

<!-- START_TASK_1 -->
### Task 1: mpi-cross-analyst agent

**Files:**
- Modify: `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` (replace stub)

**Implementation:**

```markdown
---
name: mpi-cross-analyst
description: Cross-participant MPI aggregation subagent. Reads all per-participant markdown outputs for a stage, identifies common patterns across score categories, and produces grouped analyses.
tools: Read
model: sonnet
---
# mpi-cross-analyst

You are a qualitative researcher trained in Microphenomenological Interview (MPI) analysis.
You receive all per-participant outputs for a given stage and identify patterns common
across participants, grouped by score category (low, moderate, high).

## Score categories

- **Low:** Scored 0–1/5
- **Moderate:** Scored 2–3/5
- **High:** Scored 4–5/5

## Cross-participant analysis methodology

### Identifying common patterns

1. **Read all inputs for the stage before grouping.** Do not start grouping after reading
   the first two — patterns only emerge across the full set. Ignore the `## Diachronic
   Structure` (hinge) tables in diachronic outputs — hinges are within-participant
   transitions and do not aggregate across participants.
2. **Group by experiential similarity, not surface wording.** Two IDUs named differently
   ("hands moving on their own" vs "involuntary motion") may belong to the same pattern
   if they describe the same experiential phenomenon.
3. **Threshold**: A pattern is "common" if it appears in ≥ 2 participants within the same
   score category. Patterns appearing in only one participant are listed as "unique" rather
   than omitted.
4. **Score-category separation is primary**: Never merge a pattern from the high-response
   group with a pattern from the moderate group, even if superficially similar. Keep the
   groups strict.
5. **Cite sources explicitly**: Every grouped row must name which participants and
   suggestions contributed to it. This is verifiable traceability, not optional.
6. **Preserve nuance in criteria**: Copy the original criteria language, then add a
   synthesis sentence explaining what is invariant across the participants in the group.

### Reasoning requirement

Write a `## Reasoning` section before the `## Output` section:
- List each candidate pattern and the participants it spans
- Explain any borderline grouping decisions
- Note participants with atypical patterns that do not fit any group

## Your tasks

You will be told which type of cross-participant analysis to perform:

### Generic diachronic

**Note on OSF reference format:** The OSF `generic diachronic analysis pt1.xlsx` organizes
by suggestion (one sheet per suggestion), listing participants as rows and their IDUs as
horizontal columns. This plugin's output instead organizes by **score category**
(high/moderate/low), which is a deliberate design choice to surface score-correlated
patterns. The two formats are not directly comparable row-by-row, but both capture the same
underlying cross-participant IDU patterns. The OSF file serves as a qualitative reference,
not a strict structural benchmark.

Read all `pNsN-diachronic.md` outputs. For each score category:
1. List all IDUs across participants in that category
2. Identify common IDU patterns (similar names/criteria appearing in ≥2 participants)
3. Group common IDUs together
4. Note which participants and suggestions contribute to each group

Output format:
```markdown
## Generic Diachronic Analysis

### High Response Group (Scored 4–5/5)
#### Common IDU Pattern: <Pattern Name>
| Participant | IDU Name | Criteria |
|---|---|---|
| p1s1 | Initial thoughts | The utterances talk about... |
| p4s3 | First impressions | The utterances talk about... |

[Repeat for each pattern and each score category]

### Moderate Response Group (Scored 2–3/5)
...

### Low Response Group (Scored 0–1/5)
...
```

### Generic synchronic

Same as generic diachronic but operating on `pNsN-synchronic.md` outputs, grouping ISUs
across participants by score category.

**ISU grouping rule**: ISUs are grouped **by experiential similarity regardless of which
IDU group they came from**. Synchronic outputs nest ISUs inside `isu_groups` (one group
per IDU); when comparing across participants, flatten all ISUs from all IDU groups and
group them by semantic similarity. If two ISUs from different IDU groups describe the same
structural experience (e.g., "feeling watched" appearing in an "initial thoughts" IDU for
one participant and a "shift in attention" IDU for another), they may still form a common
ISU pattern. Document the IDU-group provenance in the source citation so the reader can
trace the original context.

### Global synchronic

Read all `pNsN-synchronic.md` outputs AND `generic-synchronic.md`. Produce a further
abstraction:
- For each generic ISU pattern, synthesise a global structural theme
- Reference source participant and suggestion for every row

Output format:
```markdown
## Global Synchronic Analysis

| Global Theme | ISU Pattern | Source Participant | Source Suggestion | Score Category |
|---|---|---|---|---|
| <theme> | <ISU name> | p1 | s1 | high |
...
```

Every row MUST include source participant and source suggestion — this is a hard requirement.

## Reasoning

Before your output, write a `## Reasoning` section explaining:
- Which patterns you identified and why
- Any borderline groupings
- Participants with unusual patterns worth noting

Then produce the output in a `## Output` section.
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: mpi-generic-diachronic SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md` (replace stub)

**Implementation:**

```markdown
---
name: mpi-generic-diachronic
description: Use when running /mpi generic-diachronic — aggregates per-participant diachronic outputs across score categories via mpi-cross-analyst; warns if any participant diachronic not complete
user-invocable: false
---
# mpi-generic-diachronic

Run cross-participant generic diachronic aggregation. Requires ALL participants to have
`diachronic: done` in the manifest.

## Completeness check

Before invoking the cross-analyst, check manifest for any participants with
`diachronic.status != "done"`. If any exist:

Print warning:
```
WARNING: Generic diachronic requires all per-participant diachronic analyses to be complete.
The following participants are not yet complete: p2s1, p3s2, ...
Run /mpi diachronic to complete them, then re-run /mpi generic-diachronic.
```

Do NOT abort — ask the user if they want to proceed with the available participants or
wait for the rest. If user says proceed, continue with available `done` outputs.

**Verifies:** microphenomenograph.AC5.3

## Invoking mpi-cross-analyst

Collect all `analyses/pNsN-diachronic.md` files for participants with `diachronic: done`.
Include score category info from manifest.

Pass to `mpi-cross-analyst`:
- Task type: `generic_diachronic`
- All diachronic outputs with their participant key and score category
- Instruction: "Group IDUs by score category, identify common patterns"

## Output

Write `analyses/generic-diachronic.md`.

Update manifest:
```json
"generic_diachronic": { "status": "done", "output_path": "analyses/generic-diachronic.md" }
```

Commit if yolo mode: `git commit -m "mpi: generic-diachronic analysis"`

**Verifies:** microphenomenograph.AC5.1
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: mpi-generic-synchronic and mpi-global-synchronic SKILL.md files

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md` (replace stub)
- Modify: `microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md` (replace stub)

**mpi-generic-synchronic implementation:**

```markdown
---
name: mpi-generic-synchronic
description: Use when running /mpi generic-synchronic — aggregates per-participant synchronic outputs across score categories via mpi-cross-analyst
user-invocable: false
---
# mpi-generic-synchronic

Run cross-participant generic synchronic aggregation. Requires ALL participants to have
`synchronic: done` in manifest. Same completeness warning as mpi-generic-diachronic.

Invoke `mpi-cross-analyst` with task type `generic_synchronic`, passing all
`analyses/pNsN-synchronic.md` files with their score category info.

Write `analyses/generic-synchronic.md`. Update manifest and commit if yolo.
```

**mpi-global-synchronic implementation:**

```markdown
---
name: mpi-global-synchronic
description: Use when running /mpi global-synchronic — produces global synchronic synthesis referencing source participant and suggestion for every row via mpi-cross-analyst
user-invocable: false
---
# mpi-global-synchronic

Produce global synchronic synthesis. Requires `generic_synchronic: done` in manifest.

Invoke `mpi-cross-analyst` with:
- Task type: `global_synchronic`
- All `analyses/pNsN-synchronic.md` files
- `analyses/generic-synchronic.md`

Every row in the output MUST reference source participant and suggestion.
**Verifies:** microphenomenograph.AC5.2

Write `analyses/global-synchronic.md`. Update manifest and commit if yolo.
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify cross-participant stages

**Prerequisite:** Phase 4 complete with at least 3 participants having diachronic/synchronic done.

**Step 1: Test completeness warning**

Ensure at least one participant has `diachronic: pending`. Run:
```
/mpi generic-diachronic
```

Expected: Warning listing incomplete participants. Does NOT crash. Asks user to proceed or wait.

**Step 2: Run with partial completion (user chooses to proceed)**

Expected: `analyses/generic-diachronic.md` created with groupings for available participants. Each IDU row includes participant and suggestion source.

**Step 3: Verify global synchronic references**

After running `/mpi global-synchronic`:
```bash
grep -c "|" analyses/global-synchronic.md
```

Open `analyses/global-synchronic.md`. Verify every data row has non-empty Source Participant and Source Suggestion columns.

**Verifies:** microphenomenograph.AC5.2

**Step 4: Commit**

```bash
cd C:\microphenomenograph
git add microphenomenograph/1.0.0/agents/mpi-cross-analyst.md
git add microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md
git commit -m "feat: implement mpi-cross-analyst and cross-participant analysis skills"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

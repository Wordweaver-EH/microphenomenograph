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
| `init [--run <dir>] [--transcripts <path>]` | Bootstrap self-contained run directory; copy transcripts, parse headers, write manifest | mpi-init |
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

## Options

| Flag | Applies to | Description |
|---|---|---|
| `--yolo` | `init`, `all`, per-stage subcommands | Automated parallel execution; no human confirmation |
| `--run <dir>` | `init` | Run directory to create or resume (prompted if omitted) |
| `--transcripts <path>` | `init` | Source directory to copy transcripts from (prompted if omitted on fresh init) |

**Example:**
```
/mpi init --yolo --run runs/phase1 --transcripts "osf-archive/Phase 1/transcripts"
cd runs/phase1
/mpi all --yolo
```

## Run directory contract

Every run is self-contained in a `RUN_DIR` chosen at init time. After init, all
subsequent `/mpi` subcommands MUST be invoked with `RUN_DIR` as CWD. The manifest
(`.mpi/project.json`), transcripts, analyses, reasoning log, and git history are all
local to that directory. Runs never share state.

If a subcommand is run from a directory without `.mpi/project.json`, print:
`No .mpi/project.json in CWD. cd into your run directory, or run /mpi init.`

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

## Prerequisites

All stages other than `init` require `.mpi/project.json` to exist in CWD. If missing,
print: `No .mpi/project.json in CWD. cd into your run directory, or run /mpi init.`

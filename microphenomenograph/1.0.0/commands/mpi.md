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

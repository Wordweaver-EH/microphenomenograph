# microphenomenograph

Claude Code CLI plugin implementing the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline.

## Installation

```bash
git clone <repo-url>
# In Claude Code:
/plugins install ./microphenomenograph/1.0.0
```

## Quickstart

```
/mpi init             # scan transcripts/, write .mpi/project.json
/mpi status           # view pipeline progress table
/mpi all              # run full pipeline (yolo mode)
```

## Stage reference

| Subcommand | Input | Output |
|---|---|---|
| `init` | `transcripts/*.txt` | `.mpi/project.json` |
| `transcript-prep` | transcripts | normalised transcripts |
| `diachronic` | transcript | `analyses/pNsN-diachronic.md` |
| `synchronic` | diachronic output | `analyses/pNsN-synchronic.md` |
| `generic-diachronic` | all diachronic outputs | `analyses/generic-diachronic.md` |
| `generic-synchronic` | all synchronic outputs | `analyses/generic-synchronic.md` |
| `global-synchronic` | generic synchronic | `analyses/global-synchronic.md` |
| `hypothesis` | global synchronic | `analyses/hypotheses.md` |
| `kappa` | two analysis dirs | κ report |
| `all` | everything | complete pipeline |

## Data

Real OSF data from Sheldrake & Dienes (2025) is bundled in `examples/`. Phase 1 (p1–p7) serves as few-shot examples; Phase 2 (p8–p13) is the held-out test set.

## Scope note: simplified approach

This plugin implements the **simplified analysis approach** from Sheldrake & Dienes (2025) as described in `manual_kev.md`. Specifically:

- IDU (diachronic), diachronic structure (hinges between adjacent IDUs), ISU (synchronic), and cross-participant aggregation are all implemented.
- **Diachronic phases (grouping IDUs into higher-level phases) are NOT implemented.** The simplified approach from `manual_kev.md` stops at the IDU + hinge level.

## Requirements

- Claude Code CLI
- Python 3.8+ (for kappa computation: `pip install scikit-learn`)

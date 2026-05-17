# microphenomenograph plugin

_Last updated: 2026-05-17_

Implements the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline as a Claude Code CLI plugin.

## Pipeline overview

Seven analysis stages, each producing a markdown table output:

1. **mpi-init** — scan transcripts, parse headers, write `.mpi/project.json` manifest
2. **mpi-transcript-prep** — normalise utterance numbering and speaker labels
3. **mpi-diachronic** — per-participant IDU coding (via `mpi-analyst` subagent)
4. **mpi-synchronic** — per-participant ISU coding (via `mpi-analyst` subagent)
5. **mpi-generic-diachronic** / **mpi-generic-synchronic** / **mpi-global-synchronic** — cross-participant aggregation (via `mpi-cross-analyst`)
6. **mpi-hypothesis** — causal hypothesis generation from global synchronic output
7. **mpi-kappa** — Cohen's κ inter-rater reliability between two analysis directories

## Data formats

### Transcript header (required)
```
Participant N, Suggestion N (Scored N/5)
```
Example: `Participant 1, Suggestion 2 (Scored 3/5)` → p=1, s=2, score=3

### Score categories
- Low: 0–1
- Moderate: 2–3
- High: 4–5

### Manifest (`.mpi/project.json`)
Runtime state file. Tracked keys per participant/suggestion:
- `stage_status`: `pending | done | flagged`
- `output_path`: path to stage output file
- `mode`: `yolo | assisted`

### Analysis output paths
- Per-participant: `analyses/pNsN-{stage}.md`
- Cross-participant: `analyses/{stage}.md`

## Examples

- `examples/transcripts/` — OSF Phase 1 & 2 transcripts (real data)
- `examples/analyses/phase1/` — OSF Phase 1 completed analyses (few-shot pool)
- `examples/analyses/phase2/` — OSF Phase 2 completed analyses (held-out test fixtures)

**Never inject phase2 analyses into prompts.** They are acceptance test fixtures only.

## Key files

- `agents/mpi-analyst.md` — per-participant subagent system prompt
- `agents/mpi-cross-analyst.md` — cross-participant subagent system prompt
- `bookowhy_rev.md` (repo root) — causal framing context used by mpi-hypothesis
- `osf-archive/Inter-rater Reliability/` — CSV files for kappa validation

## Execution modes

- **yolo** — fully automated, parallel subagent fan-out, git commits per stage
- **assisted** — human confirms each participant's output before proceeding

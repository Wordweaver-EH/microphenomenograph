# microphenomenograph plugin

_Last updated: 2026-05-18 (design ahead of implementation — see notice below)_

Implements the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline as a Claude Code CLI plugin.

## Design vs implementation

**This file describes the legacy v1.0.0 plugin layout. The current design of record is `docs/design-plans/2026-05-17-doc-as-done.md` (commit `fb65db5`, v3.22), which has not yet been implemented.** Implementation is split into two implementation plans:

- **Plan 1 (Phases 1, 2, 3, 4, 5, 6, 8):** helper CLI (`scripts/mpi_step.py`), per-substep schemas, prompt-capture artifacts, `mpi-analyst` self-persistence, per-transcript SKILL closure sweep.
- **Plan 2 (Phases 7, 9, 10, 11, 12, 13):** `mpi-cross-analyst` self-persistence, cross-participant SKILL closure sweep, anti-fabrication guards, E2E pipeline test, docs reconciliation, IRR calibration.

Until Plan 1 ships, the "Pipeline overview" / "Data formats" / "Execution modes" sections below describe the pre-design state. Read the design doc for the target architecture.

## Documentation-as-Done contract (target architecture)

Every pipeline step closes via `scripts/mpi_step.py` (not yet implemented) under a phased close protocol:

```
close_attempted
  → artifacts_validated
  → audit_appended
  → manifest_replaced
  → git_commit_succeeded   (or git_commit_failed → manifest_rolled_back)
```

All phase events share a single `close_id` (UUID4). The manifest records the close's identity (`close_id`, `parent_head_sha`, `artifact_shas`) but **NOT** the SHA of the same commit it sits inside (self-reference impossibility). The actual `git_commit_sha` lands in the post-commit audit event with matching `close_id`. A substep is `done` iff manifest status is `done` AND `audit.jsonl` has a matching `git_commit_succeeded` event AND the cited commit exists in `git log`.

Every analytic unit (IDU, ISU, GDU pattern, hypothesis claim) carries `utterance_refs: [{transcript_id, utterance_number, byte_start, byte_end, raw_excerpt}, ...]` validated against the immutable raw transcript via `transcripts/offsets/<transcript_id>.json`. Empty `utterance_refs` rejects close. Replay verifies call integrity; grounding verifies output groundedness. Both v1.

IRR calibration runs automatically after the calibration transcript's diachronic + synchronic complete, computing α + κ + αU + ARI with bootstrap 95% CIs (block bootstrap for αU; naive utterance bootstrap for α/κ/ARI). Default calibration strategy is `stratified` (one transcript per IV-level stratum); `first` available only as smoke-test mode (sets `study.calibration_mode = "smoke_test"` in manifest). Warning-by-default; opt-in `--strict-irr` blocks.

Hypothesis generation produces **candidate mechanism hypotheses, not causal estimates**. Every artifact carries a verbatim disclaimer. Each claim carries `{supports, contradicts, ambiguous, n_transcripts, n_iv_levels_covered, uncertainty_language, negative_cases}` with `raw_span_refs` on every support/contradict/ambiguous entry.

## Pipeline overview

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

- `examples/transcripts/` — OSF transcripts (real data)
- `examples/analyses/` — OSF completed analyses (acceptance test fixtures only; never inject into prompts)

## Key files

- `agents/mpi-analyst.md` — per-participant subagent system prompt
- `agents/mpi-cross-analyst.md` — cross-participant subagent system prompt
- `bookowhy_rev.md` (repo root) — causal framing context used by mpi-hypothesis
- `osf-archive/Inter-rater Reliability/` — CSV files for kappa validation

## Execution modes

- **yolo** — fully automated, parallel subagent fan-out, git commits per stage
- **assisted** — human confirms each participant's output before proceeding

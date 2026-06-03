# microphenomenograph plugin

_Last updated: 2026-06-03 (Plan 1 Phases 1–6 landed; Plan 2 Phases 7, 9–11 landed)_

Implements the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline as a Claude Code CLI plugin.

## Design vs implementation

The design of record is `docs/design-plans/2026-05-17-doc-as-done.md` (commit `fb65db5`, v3.22). Implementation is split into two implementation plans:

- **Plan 1 (Phases 1, 2, 3, 4, 5, 6, 8) — Phases 1–6 LANDED:** helper CLI (`scripts/mpi_step.py` with `init`/`close`/`render`/`verify`/`unlock`/`accept-head`), per-substep schemas (`scripts/_mpi_schemas.py` incl. `validate_prompt_artifact`), atomic file primitives (`scripts/_mpi_atomic.py`), prompt-capture artifacts, `mpi-analyst` self-persistence (Write/Bash tools, anti-fabrication), per-transcript SKILL closure sweep via the Closure subsections in `mpi-diachronic` / `mpi-synchronic` SKILL.md. Phase 8 (closure sweep generalisation) is pending. AC11.3 (prompt artifact SHA-mismatch enforcement via replay-grade path resolution) is Plan 2 scope; at close time only schema structure is enforced.
- **Plan 2 (Phases 7, 9–11) — LANDED; Phase 12 (docs) + Phase 13 (IRR) in progress:** `mpi-cross-analyst` self-persistence, cross-participant SKILL closure sweep, anti-fabrication guards for cross-analyst, E2E pipeline tests landed. Phase 12 (docs reconciliation) and Phase 13 (full IRR calibration module) in progress.

The "Substep DAG" / "Data formats" / "Execution modes" sections below describe stages that still run via the legacy paths until each phase's closure sweep lands; new artifacts already go through `mpi_step.py close`.

## Documentation-as-Done contract

Every pipeline step closes via `scripts/mpi_step.py` under a phased close protocol:

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

## Substep DAG

| Stage | Substeps | Iteration | Actor |
|---|---|---|---|
| `init` | `scan_transcripts` → `propose_study_config` → `confirm_study_config` | one-shot | orchestrator |
| `transcript_prep` | `hash_raw` → `normalize` → `register_offsets` | per transcript | orchestrator |
| `diachronic` | `criteria_grouping` → `criteria_revision` → `idu_naming_ordering` | per transcript | mpi-analyst (LLM) |
| `synchronic` | `theme_grouping_within_idu` → `isu_naming` → `isu_second_level_grouping` | per transcript × IDU | mpi-analyst (LLM) |
| `generic_diachronic` | `participant_row_assembly` (orch) → `idu_similarity_grouping` (LLM) → `pattern_identification` (LLM) → `cross_iv_contrast` (LLM) | per (event × IV category) | mpi-cross-analyst |
| `generic_synchronic` | `select_generic_idus_of_interest` (LLM) → `worksheet_assembly` (orch) → `isu_second_level_grouping` (LLM) | per (event × IV category × generic-IDU) | mpi-cross-analyst |
| `global_synchronic` | `global_synchronic` | per (generic-IDU × IV category) | mpi-cross-analyst (LLM) |
| `hypothesis` | `evidence_extraction` → `candidate_drafting` → `weak_evidence_review` | first two per DV focus; review global | mpi-cross-analyst (LLM) |
| `irr_calibration` | `independent_analyst` → `alignment` → `agreement_computation` (orch) | per calibration transcript | mpi-cross-analyst |

**Prerequisite gates** (enforced by `mpi_step.py close`):
- `generic_diachronic.*`: all transcripts for the event must have all diachronic + synchronic substeps `done`, with no pending split/merge flags
- `generic_synchronic.*`: matching `generic_diachronic.*` must be `done`
- `global_synchronic.*`: all matching `generic_synchronic.*` must be `done`
- `hypothesis.*`: all `generic_diachronic.*`, `generic_synchronic.*`, `global_synchronic.*` must be `done`

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
Runtime state file. Top-level structure:
- `version`: `"2.0"`
- `run_id`: UUID4 string
- `study`: `{run_repo_mode, git_remote_configured, calibration_mode?}`
- `participants`: dict keyed by participant scope (e.g. `p1s1`, `p1s1-idu1`), each with:
  - `stages`: dict keyed by stage name, each with:
    - `status`: `pending | done | flagged | error`
    - `substeps`: dict keyed by substep name, each with:
      - `status`: `pending | done | flagged | error`
      - `close_id`: UUID4 of the close that set this substep to `done`
      - `output_path`: path to primary artifact
      - `artifact_shas`: dict of artifact SHA-256 hashes


## Examples

- `examples/transcripts/` — OSF transcripts (real data)
- `examples/analyses/` — OSF completed analyses (acceptance test fixtures only; never inject into prompts)

## Key files

- `agents/mpi-analyst.md` — per-participant subagent system prompt
- `agents/mpi-cross-analyst.md` — cross-participant subagent system prompt
- `bookowhy_rev.md` (repo root) — causal framing context used by mpi-hypothesis
- `osf-archive/Inter-rater Reliability/` — CSV files for kappa validation

## Execution modes

- **yolo** — fully automated, strictly sequential substep-level closes; one `git commit` per substep (via `mpi_step.py close`)
- **assisted** — human confirms each substep's output before proceeding

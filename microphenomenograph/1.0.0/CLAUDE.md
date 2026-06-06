# microphenomenograph plugin

_Last updated: 2026-06-06 (review-remediation all 5 plans landed: GATES registry, inputs verb, IRR alignment fix + rater_kind, analysis-fidelity rules, hypothesis claim contract, causal extension)_

Implements the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline as a Claude Code CLI plugin.

## Design vs implementation

The design of record is `docs/design-plans/2026-05-17-doc-as-done.md` (commit `fb65db5`, v3.22). Implementation is split into two implementation plans:

- **Plan 1 (Phases 1, 2, 3, 4, 5, 6, 8) — LANDED:** helper CLI (`scripts/mpi_step.py` with `init`/`close`/`render`/`verify`/`unlock`/`accept-head`), per-substep schemas (`scripts/_mpi_schemas.py` incl. `validate_prompt_artifact`), atomic file primitives (`scripts/_mpi_atomic.py`), prompt-capture artifacts, `mpi-analyst` self-persistence (Write/Bash tools, anti-fabrication), per-transcript SKILL closure sweep via the Closure subsections in `mpi-diachronic` / `mpi-synchronic` SKILL.md. Phase 8 (closure sweep generalisation) is pending. AC11.3 (prompt artifact SHA-mismatch enforcement via replay-grade path resolution) is Plan 2 scope; at close time only schema structure is enforced.
- **Plan 2 (Phases 7, 9–13) — ALL LANDED:** `mpi-cross-analyst` self-persistence, cross-participant SKILL closure sweep, anti-fabrication guards for cross-analyst, E2E pipeline tests; Phase 12 (docs reconciliation); Phase 13 (full IRR calibration module with `scripts/irr.py` exposing Krippendorff α + Cohen κ + αU + ARI with bootstrap CIs, auto-trigger after calibration transcript closes, --strict-irr gate for cross-participant stages).

A second, distinct design — `docs/design-plans/2026-06-05-cross-scope-prereq-resolution.md` (the pipeline-correctness plan, **all 8 phases LANDED**) — hardens close-time enforcement on top of doc-as-done: `study.event_groups` / `study.dv_focuses` / `study.dv_focuses_provenance` manifest fields written at `confirm_study_config`; `PREREQ_SCOPE_TRANSFORMS` + `_scope_strip_to_event` for cross-scope prerequisite resolution in `cmd_close`; `COMPLETENESS_GATES` + `_check_completeness_gate` enforcing cross-participant coverage at close and swept by `cmd_verify`; DV-focus enforcement (undeclared-focus guard at `hypothesis.evidence_extraction`); `acquire_close_lock` serialising the `cmd_close` manifest block; `transcript_prep` substep registration (`hash_raw`/`normalize`/`register_offsets`); flat-dict offset-format enforcement. These mechanisms are documented in the Substep DAG, prerequisite gates, offset contract, and manifest sections below.

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

IRR calibration runs automatically after the calibration transcript's diachronic + synchronic complete, computing α + κ + αU + ARI with bootstrap 95% CIs (block bootstrap for αU; naive utterance bootstrap for α/κ/ARI). αU here is a **boundary-agreement approximation**, not the canonical length-weighted Krippendorff αU continuum formula (chance-corrected via the block bootstrap). Default calibration strategy is `stratified` (one transcript per IV-level stratum; `DEFAULT_CALIBRATION_MODE = "stratified"` in `scripts/irr.py`); `first` available only as smoke-test mode (sets `study.calibration_mode = "smoke_test"` in manifest). Warning-by-default; opt-in `--strict-irr` blocks.

The `--strict-irr` gate maps each cross-participant stage to its upstream IRR stage (`generic_diachronic` → `diachronic`; `generic_synchronic`, `global_synchronic`, and `hypothesis` → `synchronic`), filters `irr_calibration.jsonl` to records for that upstream stage, and blocks if **any** matching record has `outcome != "passed"` (a missing/None outcome routes to `irr_missing`, not pass). This checks all records for the upstream stage, not just the most recent one.

Hypothesis generation produces **candidate mechanism hypotheses, not causal estimates**. Every artifact carries a verbatim disclaimer. Each claim carries `{supports, contradicts, ambiguous, n_transcripts, n_iv_levels_covered, uncertainty_language, negative_cases}` with `raw_span_refs` on every support/contradict/ambiguous entry.

**Causal contract (causal-extension, plan 5 — all 3 phases landed).** Every `candidate_drafting` claim also carries four required causal fields:

- `rung` (int 1|2|3): Pearl ladder rung — 1 = association, 2 = intervention, 3 = counterfactual. Schema-enforced; any value outside {1, 2, 3} is rejected.
- `assumptions` (list of strings): causal assumptions licensing a higher-rung framing. Required to be non-empty when `rung >= 2` (DoWhy identify-discipline analogue); may be empty `[]` at rung 1. Schema-enforced.
- `confounders` (non-empty list of `{variable, mechanism}` objects): always required, always non-empty. Always includes the common-method-variance (CMV) latent factor: IV score and DV experience description are both self-reports from the same participant in the same session. Schema-enforced shape.
- `testable_implications` (non-empty list of strings): stated in DAGitty conditional-independence notation `X _||_ Y | Z` — what a second participant set would need to show if the mechanism is real.

Top-level artifact field: `replication_recommendation` (string; discharges manual §1.5 replication requirement — states what a second independent participant set would need to show). Required; schema-enforced.

**DAG convention.** Each candidate hypothesis in the markdown artifact includes one mermaid DAG: IV → mechanism components → DV focus, with confounders as explicit latent nodes carrying two directed arrows into IV and DV (no `<->` — mermaid has no bidirected edge). Latent nodes are marked with a distinct mermaid class (`classDef latent` or `:::latent`). DAG presence is validated at close time via the `dag_section_missing` gate (warn by default; abort with `--strict-dag-section-missing` or `study.strict_gates: ["dag_section_missing"]`). DAG syntax is not validated.

**`rung_appropriateness`** in `weak_evidence_review` is substantive: a claim coded as rung ≥ 2 over observational interview evidence (no experimental manipulation) is flagged as `{"flagged": true, "reason": "..."}`.

**No plugin version bump.** These fields extend the contract within an unreleased plugin — the plugin directory is pinned at `microphenomenograph/1.0.0/` only because it has not been released. These are schema additions within the same unreleased version.

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

**`transcript_prep` offset contract:** `transcripts/offsets/<id>.json` uses a flat-dict format keyed by string utterance number — `{"1": {"byte_start": N, "byte_end": N}, ...}`. The **raw** transcript file must already satisfy the single-line-per-utterance invariant (each utterance on one physical line); the `normalize` step produces an aligned normalized derivative but never rewrites the raw. The `register_offsets` validator rejects the old array format `{"utterances": [...]}`. Byte ranges are anchored to the **raw** transcript file (`transcripts/raw/<id>.txt`), not the normalized version.

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
- `study`: `{run_repo_mode, git_remote_configured, calibration_transcript_ids: [], calibration_mode?, event_groups?, dv_focuses?, dv_focuses_provenance?, config_provenance?}`
  - `calibration_transcript_ids`: list of transcript IDs selected for IRR calibration (e.g., `["p1s1", "p3s2"]` for stratified mode)
  - `calibration_mode`: optional string, either `"stratified"` (default, one per IV-level stratum) or `"smoke_test"` (first available)
  - `event_groups`: dict mapping event IDs (e.g. `"event1"`) to lists of transcript IDs. Written at `init.confirm_study_config` close. Study-design-agnostic — any string event ID, any transcript list. Required by completeness gates (Phase 7).
  - `dv_focuses`: optional list of researcher-declared dependent variable focus labels (e.g. `["automaticity", "attention"]`), or `null` when focuses are LLM-derived. Written at `init.confirm_study_config` close.
  - `dv_focuses_provenance`: `"researcher_specified"` when `study.dv_focuses` was declared; `"emergent"` when null. Written automatically at `confirm_study_config` close alongside `dv_focuses`.
  - `config_provenance`: how the study config was determined (`"preregistered"`, `"user_specified"`, `"llm_proposed_user_confirmed"`). Immutable after `confirm_study_config`.
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

- **yolo** — fully automated, parallel within-stage execution (all pending participants for a stage invoked concurrently in a single assistant turn), sequential across stages (next stage starts only after all closes for current stage complete); one `git commit` per substep (via `mpi_step.py close`). The within-stage concurrency makes the manifest write race reachable — see close lock (Issue 2).
- **assisted** — human confirms each substep's output before proceeding

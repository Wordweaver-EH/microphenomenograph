# Microphenomenograph Plugin Design

## Summary

The microphenomenograph plugin implements the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline as a Claude Code CLI plugin following ed3d conventions. It exposes a single `/mpi` slash command that orchestrates a seven-stage qualitative analysis workflow — from raw transcript preparation through diachronic coding, synchronic structuring, cross-participant aggregation, and causal hypothesis generation — with each stage also independently invokable as a named sub-skill.

The core design decision is a two-agent architecture: `mpi-analyst` handles per-participant analysis using few-shot chain-of-thought prompting with structured JSON output, while `mpi-cross-analyst` handles cross-participant aggregation. Prompt fidelity follows patterns validated in LLM qualitative coding research (LATA/GATOS), favouring few-shot CoT over zero-shot. Two execution modes govern human involvement: *yolo* mode parallelises analysis via subagent fan-out, commits each completed stage to git, and logs all reasoning decisions; *assisted* mode gates progression on human confirmation after each participant. Pipeline state is tracked in a manifest file (`.mpi/project.json`), making runs resumable and incremental. Inter-rater reliability is computed in Python (Cohen's kappa, matching the manual's `κ > .6` threshold) with no R dependency. The OSF dataset is split: Phase 1 analyses serve as few-shot examples; Phase 2 analyses are held out as acceptance test fixtures.

## Definition of Done

- A Claude Code CLI plugin (GitHub repo) following ed3d conventions, installable by anyone cloning the repo
- One primary `/mpi` slash command orchestrates the full MPI pipeline (transcript → diachronic → synchronic → generic diachronic → generic synchronic → global synchronic → hypothesis generation), with each stage also independently invokable as a sub-skill
- Two modes: **assisted** (human confirms each stage's output before proceeding) and **yolo** (fully automated, git-commits each stage, logs reasoning + confidence flags, rich terminal output with a future local web server dashboard)
- Outputs are Markdown tables; participant scores parsed from transcript file headers; Cohen's kappa implemented in Python/JS (no R dependency)
- The real OSF data (transcripts + completed analyses) is bundled as the example/test dataset

## Acceptance Criteria

### microphenomenograph.AC1: Plugin installs and is invokable
- **microphenomenograph.AC1.1 Success:** Repo clones; `/mpi` command is available in Claude Code CLI after install
- **microphenomenograph.AC1.2 Success:** Each sub-skill (`mpi-diachronic`, `mpi-synchronic`, etc.) is independently invokable
- **microphenomenograph.AC1.3 Failure:** Running `/mpi` with unknown subcommand produces helpful usage message

### microphenomenograph.AC2: /mpi init parses transcripts and writes manifest
- **microphenomenograph.AC2.1 Success:** Header `"Participant 1, Suggestion 2 (Scored 3/5)"` parsed to p=1, s=2, score=3
- **microphenomenograph.AC2.2 Success:** All OSF transcripts produce valid `.mpi/project.json` with all stages `pending`
- **microphenomenograph.AC2.3 Failure:** Malformed header produces named error, not silent wrong value
- **microphenomenograph.AC2.4 Edge:** Re-running init on existing manifest preserves `done` stages, adds new participants

### microphenomenograph.AC3: Diachronic analysis produces correct output
- **microphenomenograph.AC3.1 Success:** Each transcript produces `analyses/pNsN-diachronic.md` with IDU markdown table
- **microphenomenograph.AC3.2 Success:** IDU groupings are traceable to source utterance numbers
- **microphenomenograph.AC3.3 Success:** Confidence score 1–5 present for every IDU
- **microphenomenograph.AC3.4 Failure:** IDUs with confidence < 3 or `flag_for_review=true` appear in `.mpi/review-queue.md`
- **microphenomenograph.AC3.5 Edge:** Transcript with single IDU produces single-row table without error
- **microphenomenograph.AC3.6 Integrity:** Cohen's κ between `mpi-analyst` diachronic outputs on Phase 2 transcripts and Phase 2 reference analyses (per-utterance Moment assignment, same computation as Phase 7) ≥ 0.4; no Phase 2 analysis file present in the few-shot pool (enforced by `examples/analyses/phase1/` path constraint)

### microphenomenograph.AC4: Synchronic analysis produces correct output
- **microphenomenograph.AC4.1 Success:** Each diachronic output produces `analyses/pNsN-synchronic.md` with ISU table
- **microphenomenograph.AC4.2 Success:** ISU 2nd level of abstraction populated where grouping exists
- **microphenomenograph.AC4.3 Failure:** Missing diachronic prerequisite produces clear error, not empty output

### microphenomenograph.AC5: Cross-participant stages aggregate correctly
- **microphenomenograph.AC5.1 Success:** Generic diachronic groups IDUs by score category across all participants
- **microphenomenograph.AC5.2 Success:** Global synchronic output references source participant and suggestion for each row
- **microphenomenograph.AC5.3 Failure:** Running `generic-diachronic` before all per-participant diachronic stages complete produces warning listing incomplete participants

### microphenomenograph.AC6: Hypothesis output is structured and causal
- **microphenomenograph.AC6.1 Success:** Each hypothesis names IV, DV, pattern, Pearl ladder rung, and confidence
- **microphenomenograph.AC6.2 Success:** Each hypothesis references the source IDUs/ISUs it was derived from
- **microphenomenograph.AC6.3 Edge:** No cross-participant patterns found produces explicit "no hypothesis" output rather than empty file

### microphenomenograph.AC7: Kappa reports correct agreement
- **microphenomenograph.AC7.1 Success:** Diachronic κ and synchronic κ each match `kappa.Rmd` reference output within ±0.01 on OSF inter-rater data (2-rater, per-utterance category agreement)
- **microphenomenograph.AC7.2 Success:** κ reported separately for diachronic stage and synchronic stage (matching the two-stage structure of `kappa.Rmd`)
- **microphenomenograph.AC7.3 Failure:** Overall κ < 0.61 for any stage triggers a pipeline-level adequacy warning (manual threshold κ > .6 applies to the whole calibration set, not individual utterances)
- **microphenomenograph.AC7.4 Edge:** Missing utterance annotations in one analyst's file handled without crash

### microphenomenograph.AC8: Yolo mode is automated and resumable
- **microphenomenograph.AC8.1 Success:** `/mpi all` in yolo mode runs all stages without human input
- **microphenomenograph.AC8.2 Success:** One git commit per participant/stage completion with message `"mpi: pNsN {stage} analysis"`
- **microphenomenograph.AC8.3 Success:** Ctrl+C mid-run leaves manifest consistent; re-running `/mpi all` skips completed stages
- **microphenomenograph.AC8.4 Success:** `.mpi/reasoning.log` contains entry for every analysis decision
- **microphenomenograph.AC8.5 Success:** Terminal progress table renders with completion status and avg confidence per participant

### microphenomenograph.AC9: Assisted mode requires human confirmation
- **microphenomenograph.AC9.1 Success:** Each participant's output shown to human before next participant processed
- **microphenomenograph.AC9.2 Success:** Human rejection of an output re-runs that participant's stage, not the whole pipeline

## Glossary

- **MPI (Microphenomenological Interview)**: A structured research interview technique eliciting fine-grained first-person accounts of lived experience; the document implements the Sheldrake & Dienes (2025) variant.
- **IDU (Invariant Diachronic Unit)**: A discrete, temporally-ordered unit of experiential content identified within a single transcript during diachronic analysis; the primary output of per-participant coding.
- **ISU (Invariant Synchronic Unit)**: A structural theme extracted by abstracting across IDUs within a participant's account during synchronic analysis; the second level of qualitative coding.
- **Diachronic analysis**: Sequential, time-ordered coding of a transcript that traces how an experience unfolded moment by moment; produces IDUs.
- **Synchronic analysis**: Cross-sectional structural analysis of the diachronic output, grouping IDUs into thematic patterns independent of temporal order; produces ISUs.
- **Generic diachronic**: Cross-participant aggregation of IDUs grouped by score category; identifies patterns common across multiple participants at the diachronic level.
- **Generic synchronic**: Cross-participant aggregation of ISUs; identifies structural themes recurring across participants.
- **Global synchronic**: A further-abstracted synthesis of generic synchronic output referencing source participant and suggestion for every row; the final cross-participant structural stage before hypothesis generation.
- **Pearl ladder rung**: A level of causal reasoning from Judea Pearl's causal hierarchy (association, intervention, counterfactual); used to classify the causal strength of each generated hypothesis.
- **Cohen's kappa (κ)**: The inter-rater reliability statistic used throughout this pipeline; computed via Python `sklearn.metrics.cohen_kappa_score` on two-rater, per-utterance category assignments. The `kappa.Rmd` OSF reference computes one overall κ for diachronic and one for synchronic stages. The manual specifies κ > .6 as the adequacy threshold; overall stage κ below that triggers a pipeline-level warning.
- **CoT (Chain-of-Thought)**: A prompting technique instructing the model to produce explicit step-by-step reasoning before a final answer; used in the analyst agent to improve coding fidelity.
- **Confidence-Diversity routing**: Items with confidence ≥ 3 and `flag_for_review=false` are auto-accepted; others are diverted to `.mpi/review-queue.md` for human review.
- **OSF**: Open Science Framework; source of the bundled example/test dataset of real transcripts and completed analyses.
- **ed3d conventions**: Structural conventions for Claude Code CLI plugins: skills as `SKILL.md` files, agents as `.md` files, slash commands as thin wrappers, identity from directory naming.
- **Yolo mode**: Fully automated pipeline execution with parallel subagent fan-out, per-stage git commits, and no human confirmation steps.
- **Assisted mode**: Human-in-the-loop execution where each participant's output is shown for approval before proceeding.
- **`.mpi/project.json` (manifest)**: Runtime pipeline state file tracking stage status (`pending | done | flagged`), output paths, mode, and configuration.
- **`mpi-analyst`**: Per-participant subagent receiving a single transcript plus few-shot examples; returns structured IDU/ISU groupings with confidence scores.
- **`mpi-cross-analyst`**: Cross-participant subagent that reads all per-participant outputs for a stage and produces generic/global aggregated analyses.
- **Few-shot prompting**: Providing the model with worked examples before the task; used to anchor coding style to the OSF reference analyses.
- **LATA / GATOS**: Published LLM qualitative coding studies (CSCW 2025 / EDM 2025) validating the few-shot CoT architecture used here.
- **Score category**: Participant's self-reported rating parsed from transcript header (`Scored N/5`); groups participants in cross-participant analyses (low=0–1, moderate=2–3, high=4–5).

## Architecture

The microphenomenograph plugin is a Claude Code CLI plugin following ed3d conventions. It implements the Sheldrake & Dienes (2025) MPI analysis pipeline as a sequenced set of skills orchestrated by a single `/mpi` slash command.

**Plugin layout:**
```
microphenomenograph/1.0.0/
  commands/mpi.md
  skills/
    mpi-init/SKILL.md
    mpi-transcript-prep/SKILL.md
    mpi-diachronic/SKILL.md
    mpi-synchronic/SKILL.md
    mpi-generic-diachronic/SKILL.md
    mpi-generic-synchronic/SKILL.md
    mpi-global-synchronic/SKILL.md
    mpi-hypothesis/SKILL.md
    mpi-kappa/SKILL.md
    mpi-status/SKILL.md
  agents/
    mpi-analyst.md
    mpi-cross-analyst.md
  examples/
    transcripts/   (OSF Phase 1 & 2 .txt transcripts)
    analyses/
      phase1/      (OSF Phase 1 completed analyses — few-shot prompt pool)
      phase2/      (OSF Phase 2 completed analyses — held-out test fixtures only)
  CLAUDE.md
  README.md
```

**State:** `.mpi/project.json` is the pipeline manifest. It records mode, score categories, per-participant/suggestion stage status (`pending | done | flagged`), output file paths, git flag, and log path. `.mpi/reasoning.log` is an append-only record of every analysis decision and confidence score. `.mpi/review-queue.md` accumulates items flagged for human review.

**Analysis agents:**
- `mpi-analyst` — per-participant subagent. Receives a single transcript + few-shot examples, runs CoT + structured JSON output, returns IDU/ISU groupings with confidence scores.
- `mpi-cross-analyst` — cross-participant subagent. Reads all per-participant markdown outputs for a given stage, performs generic/global grouping, produces one output file per stage.

**Execution modes:**
- *Yolo*: parallel fan-out — one `mpi-analyst` subagent per participant, manifest updated and git-committed on each completion, rich terminal progress table, Ctrl+C safe.
- *Assisted*: iterative single-threaded — human confirms each participant's output before the next is processed.

**Output format:** All analysis outputs are Markdown tables at `analyses/pNsN-{stage}.md`. Score is parsed from transcript file headers (`Participant N, Suggestion N (Scored N/5)`).

## Existing Patterns

Investigation found no existing MPI analysis code in this project — this plugin is greenfield. The plugin structure follows ed3d conventions observed in `ed3d-plan-and-execute/1.11.0/`:
- Skills as `skills/<name>/SKILL.md`
- Agents as `agents/<name>.md`
- Slash commands as thin `commands/<name>.md` wrappers that delegate to skills
- No plugin manifest file — identity from directory naming and `installed_plugins.json`

The analysis prompt architecture follows patterns validated in published LLM qualitative coding research (LATA CSCW 2025, GATOS EDM 2025): few-shot + chain-of-thought + structured output schema. This diverges from zero-shot approaches, which show lower coding fidelity.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Plugin Scaffold
**Goal:** Establish the repository structure, ed3d plugin conventions, and manifest JSON schema.

**Components:**
- `microphenomenograph/1.0.0/` directory tree (all empty skill/agent/command stubs)
- `CLAUDE.md` — plugin purpose, pipeline overview, data format reference
- `README.md` — installation instructions, quickstart, stage reference
- `.mpi/` directory convention documented (gitignored runtime state, not committed)
- `examples/transcripts/` and `examples/analyses/` populated from OSF archive

**Dependencies:** None

**Done when:** Repo clones cleanly, directory structure matches spec, examples present
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Init, Status & Manifest
**Goal:** `/mpi init` scans transcripts, parses headers, writes `.mpi/project.json`; `/mpi status` renders a progress table.

**Components:**
- `commands/mpi.md` — routes `init` and `status` subcommands to skills
- `skills/mpi-init/SKILL.md` — scans `transcripts/`, parses `"Participant N, Suggestion N (Scored N/5)"` headers, writes manifest with all stages `pending`
- `skills/mpi-status/SKILL.md` — reads manifest, prints terminal table of participant × stage completion

**Dependencies:** Phase 1

**Done when:** `mpi init` on OSF transcripts produces valid manifest; `mpi status` renders correct table; malformed headers produce clear error
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Transcript Prep
**Goal:** Normalise raw transcripts into numbered utterance format ready for analysis.

**Components:**
- `skills/mpi-transcript-prep/SKILL.md` — validates line numbering, speaker labels, and header format; splits multi-utterance lines; writes cleaned transcript back; updates manifest stage to `done`

**Dependencies:** Phase 2

**Done when:** OSF transcripts pass prep without errors; a deliberately malformed transcript produces actionable error output; manifest updated correctly
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Diachronic & Synchronic Analysis
**Goal:** Per-participant IDU and ISU analysis via `mpi-analyst` subagent with few-shot CoT prompting and confidence routing.

**Components:**
- `agents/mpi-analyst.md` — system prompt with role, few-shot example slot, CoT instruction, structured JSON output schema: `{ reasoning, idus: [{ idu_number, name, criteria, confidence, flag_for_review, utterance_numbers }] }`; synchronic variant adds `isus` array with `isu_name`, `isu_2nd_level` fields
- `skills/mpi-diachronic/SKILL.md` — selects closest-length few-shot examples from `examples/analyses/phase1/` only (Phase 2 OSF analyses are held out as test fixtures; never used as prompting examples), invokes `mpi-analyst`, applies Confidence-Diversity routing (conf ≥ 3 and flag=false → accept; else → `.mpi/review-queue.md`), writes `analyses/pNsN-diachronic.md` markdown table, updates manifest
- `skills/mpi-synchronic/SKILL.md` — same pattern, operates on diachronic output, produces `analyses/pNsN-synchronic.md`
- Yolo: parallel fan-out with git commit per completion; assisted: iterative with human confirmation

**Dependencies:** Phase 3

**Done when:** All OSF participants produce diachronic and synchronic markdown tables; flagged items appear in review-queue; outputs match expected IDU/ISU structure from OSF reference analyses; tests cover confidence routing logic
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Generic & Global Cross-Participant Analysis
**Goal:** Aggregate per-participant outputs into generic diachronic, generic synchronic, and global synchronic analyses via `mpi-cross-analyst`.

**Components:**
- `agents/mpi-cross-analyst.md` — system prompt for cross-participant grouping; reads all per-participant markdown tables for a stage, identifies common IDU/ISU patterns across score categories, produces grouped output
- `skills/mpi-generic-diachronic/SKILL.md` — invokes cross-analyst on all diachronic outputs, writes `analyses/generic-diachronic.md`
- `skills/mpi-generic-synchronic/SKILL.md` — writes `analyses/generic-synchronic.md`
- `skills/mpi-global-synchronic/SKILL.md` — writes `analyses/global-synchronic.md`

**Dependencies:** Phase 4

**Done when:** Generic and global outputs produced from OSF data; cross-participant groupings are traceable to source participants; manifest updated; tests verify correct aggregation of participant outputs
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Hypothesis Generation
**Goal:** Translate global synchronic patterns into structured research hypotheses with causal framing.

**Components:**
- `skills/mpi-hypothesis/SKILL.md` — invokes `mpi-cross-analyst` with global synchronic outputs and `bookowhy_rev.md` causal framing context; produces `analyses/hypotheses.md` with structured entries: pattern, independent variable, dependent variable, Pearl ladder rung, confidence, suggested quantitative test

**Dependencies:** Phase 5

**Done when:** Hypothesis document produced for OSF data; each hypothesis references source IDUs/ISUs; Pearl ladder rung correctly assigned; tests verify output schema
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Inter-Rater Reliability (Cohen's Kappa)
**Goal:** Compare two analysts' outputs and report Cohen's κ per stage and per IDU/ISU, matching the manual's κ > .6 threshold.

**Components:**
- `skills/mpi-kappa/SKILL.md` — accepts two analysis directories, parses markdown tables by utterance number into per-utterance category label arrays (Moment for diachronic, ISUnum for synchronic), calls Python `sklearn.metrics.cohen_kappa_score`, reports overall κ per stage; emits pipeline-level warning if κ < 0.61
- Python helper script `scripts/kappa.py` — 2-rater, per-utterance κ; handles label alignment and missing utterances; output matches `Inter-rater Reliability/kappa.Rmd` (which also computes one κ per stage)

**Dependencies:** Phase 4 (needs analysis outputs to compare)

**Done when:** Diachronic κ and synchronic κ each match `kappa.Rmd` output within ±0.01; κ < 0.61 stages produce warning; missing annotations handled without crash
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Full Pipeline Orchestration & Yolo Mode
**Goal:** `/mpi all` runs the complete pipeline; yolo mode enables parallel fan-out, git commits, and rich terminal output.

**Components:**
- `commands/mpi.md` — complete subcommand routing for all stages + `all`
- Yolo orchestration in `skills/mpi-diachronic/SKILL.md` and `skills/mpi-synchronic/SKILL.md` — in yolo mode, the skill emits multiple Agent tool calls in a single assistant turn (one `mpi-analyst` subagent per pending participant), collects results as they complete, writes each output file, appends to `.mpi/reasoning.log`, runs `git add + git commit`, and updates the manifest — all before returning to the user; Ctrl+C safety comes from manifest atomicity (each participant's record written only after its commit succeeds)
- Git integration — `git add` + `git commit` per completed participant/stage; commit message format: `mpi: pNsN {stage} analysis`
- Resume logic — `/mpi all` skips stages already marked `done` in manifest

**Dependencies:** Phases 1–7

**Done when:** `/mpi all` on OSF data completes full pipeline; interrupted run resumes correctly from manifest; git log shows per-participant commits; review-queue populated with flagged items; terminal progress table renders correctly
<!-- END_PHASE_8 -->

## Additional Considerations

**Train/test split:** OSF Phase 1 analyses (`examples/analyses/phase1/`, 7 participants × 3 suggestions) are the few-shot pool for `mpi-analyst` prompts. OSF Phase 2 analyses (`examples/analyses/phase2/`, 6 participants × 3 suggestions) are held out and used exclusively as acceptance test fixtures — never injected into prompts. This prevents contamination when verifying that the pipeline produces analyses structurally consistent with the reference dataset.

**Transcript format tolerance:** Prep stage should handle minor real-world variations (double spaces, inconsistent speaker label capitalisation, BOM characters from Windows editors) without requiring manual fixes.

**Few-shot example selection:** Closest-length matching from `examples/analyses/` reduces token usage and improves relevance. If no example within 20% of transcript length exists, fall back to the longest available.

**Web server dashboard:** Rich terminal output is Phase 8. A local web server (`python -m http.server` serving a generated HTML file) is a post-v1.0 addition — not in scope for initial implementation.

**Implementation scoping:** This design has 8 phases at the hard limit. If scope expands (e.g. web dashboard, multi-study project support), create a second implementation plan for those additions.

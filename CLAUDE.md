# microphenomenograph repo

_Last updated: 2026-06-06 (review-remediation campaign: all 5 plans landed — irr-fidelity, close-enforcement-2, analysis-fidelity, hypothesis-evidence, causal-extension)_

Repository for the `microphenomenograph` Claude Code plugin — a CLI pipeline implementing Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis.

## Layout

| Path | Purpose |
|---|---|
| `microphenomenograph/1.0.0/` | The plugin itself (commands, agents, skills, scripts, examples). See its own `CLAUDE.md`. |
| `tests/` | Pytest suite validating plugin structure and skill/agent logic against acceptance criteria. |
| `osf-archive/` | Read-only source data from the OSF project (transcripts, R scripts, inter-rater CSVs, manual). |
| `docs/design-plans/` | Validated design docs. |
| `docs/implementation-plans/` | Phased implementation tasks (one folder per design). |
| `docs/test-plans/` | Acceptance-criteria test plans. |
| `docs/reviews/` | Adversarial review reports (e.g. `2026-06-05-adversarial-review-manual-kev.md`, the 22-finding review that drove the 2026-06-05 remediation design plans). |
| `bookowhy_rev.md` | Causal framing reference used by the `mpi-hypothesis` skill. |
| `manual_2018.md`, `manual_kev.md` | Microphenomenology methodology references. |
| `runs/` | MPI run directories (e.g. `runs/phase1-2026-05-17/` from Phase 1 exploration). Each run is its own git scope; see Operational requirements. |

## Plugin contracts

The plugin's own contracts (pipeline stages, data formats, manifest schema, execution modes) live in `microphenomenograph/1.0.0/CLAUDE.md`. Read that file before modifying plugin internals.

**Documentation-as-Done contract.** Every pipeline step closes via `scripts/mpi_step.py` (transactional close protocol: artifact + audit event + manifest mutation + git commit, all keyed by `close_id`). See `docs/design-plans/2026-05-17-doc-as-done.md` (`fb65db5`) for the full design — 13 implementation phases split across two implementation plans; 34 acceptance criteria; transcript-span grounding mandatory; replay-grade prompt capture; bootstrap CIs for IRR (Krippendorff α + Cohen κ + αU block-bootstrap + ARI). Walkthrough at `docs/design-plans/2026-05-17-doc-as-done.html`.

**Implementation status (all phases landed).** Plan 1 (Phases 1–6) landed: `scripts/mpi_step.py` exposes verbs `init`, `close`, `render`, `verify`, `unlock`, `accept-head`; `scripts/_mpi_schemas.py` carries per-substep schemas plus `validate_prompt_artifact`; `scripts/_mpi_atomic.py` provides atomic file primitives; `agents/mpi-analyst.md` declares Write/Bash tools, persistence rules, and anti-fabrication guards; `mpi-diachronic` / `mpi-synchronic` SKILL.md files include the Closure subsection that drives self-persisted artifacts. Plan 2 (Phases 7, 9–13) landed: `agents/mpi-cross-analyst.md` declares Write/Bash tools and anti-fabrication guards; cross-participant skills (`mpi-generic-diachronic`, `mpi-generic-synchronic`, `mpi-global-synchronic`) include Closure subsections for self-persisted artifact production; E2E pipeline tests (`test_mpi_orchestration.py`) pass; Phase 12 (docs reconciliation) completed; Phase 13 (full IRR calibration module with `scripts/irr.py`, Krippendorff α + Cohen κ + αU + ARI, bootstrap CIs, auto-trigger + --strict-irr gate) completed.

A separate pipeline-correctness design — `docs/design-plans/2026-06-05-cross-scope-prereq-resolution.md` (all 8 phases landed) — hardens close-time enforcement: `study.event_groups` / `study.dv_focuses` / `study.dv_focuses_provenance` manifest fields; `PREREQ_SCOPE_TRANSFORMS` cross-scope prerequisite resolution; `COMPLETENESS_GATES` enforced at close and swept by `verify`; DV-focus enforcement; `acquire_close_lock` serialising the close manifest mutation; `transcript_prep` substep registration; flat-dict offset-format enforcement. Plugin-internal contracts live in `microphenomenograph/1.0.0/CLAUDE.md`.

**Review-remediation campaign (2026-06-06, all 5 plans LANDED).** An adversarial review against `manual_kev.md` (`docs/reviews/2026-06-05-adversarial-review-manual-kev.md`, 22 verified findings) drove five design plans (`docs/design-plans/2026-06-05-{irr-fidelity,close-enforcement-2,analysis-fidelity,hypothesis-evidence,causal-extension}.md`), all implemented:

- **irr-fidelity** — fixed the `irr.py` alignment-map inversion (alignment maps now keyed alternate→primary; pre-fix calibration records are not comparable); IRR records carry required `rater_kind` (`intra_model` | `heterogeneous_model`) + verbatim `caveat` (same-model agreement is intra-model consistency / test-retest, not true IRR).
- **close-enforcement-2** — `GATES` registry in `_mpi_schemas.py` (warn-by-default; strictness via `study.strict_gates` manifest field at `confirm_study_config` or `--strict-<gate_id>` CLI; `gate_warning` audit events swept by `verify`); new `inputs` verb (`mpi_step.py inputs --stage <s> --scope <sc>`) resolves per-scope upstream artifacts (path+SHA) so SKILL prose never names cross-stage files; `inputs_consumed` ⊆ resolved checked at close (`undeclared_input` gate); convergence (`more_revision_needed`) and `temporal_order_within_idu` closes auto-downgrade to `flagged` (downgrade gates take no strict flag by design); `idu_split_after_synchronic` audit event emitted on diachronic re-close.
- **analysis-fidelity** — within-generic-IDU ISU grouping enforced via required `source_generic_idu`; pattern rows require `common_idus`/`optional_idus`/`covered_participant_keys`; temporal-linkage-phrase boundary rule in `mpi-analyst.md` (outranks prefer-fewer-IDUs); IDU naming deferred (`_IDU_BASE_REQUIRED` vs `_IDU_NAMING_REQUIRED`); score-range 0–5 validation + 6–12 participant advisory at init; question-line flagging (validate-only) in prep.
- **hypothesis-evidence** — `hypothesis` stage `inputs` fan-in covers all three cross-participant analyses; claims carry unique `claim_id`; `weak_evidence_review` requires per-claim coverage (`claim_ids` roster; empty reviews impossible) with `thin_support`/`single_iv_level`/`causal_language`/`rung_appropriateness` checks; `weak_evidence_unreviewed` gate.
- **causal-extension** — claims require `rung` (1|2|3; rung ≥ 2 ⇒ non-empty `assumptions`), `confounders` (`{variable, mechanism}`, non-empty; common-method-variance latent factor always instructed), `testable_implications` (DAGitty `X _||_ Y | Z` notation); artifact-level `replication_recommendation`; per-hypothesis mermaid DAG (latent confounders as explicit nodes with two directed arrows; presence checked by `dag_section_missing` gate, syntax not validated). Full contract in the plugin `CLAUDE.md`.

Caveat: schema/gate enforcement is test-verified; the prompt-rule changes (analyst behaviour) are instruction-level and have not yet been exercised by a live end-to-end run.

## Operational requirements

**MPI runs need a dedicated git repo.** A 21-transcript study produces ~100–200 commits (one per substep close). The pipeline's helper `mpi_step.py` refuses by default to initialise inside a non-empty active development worktree — pre-commit hooks, GPG signing, CI triggers, and branch protections would each fire per close. Point `/mpi init --run <dir>` at an empty directory; the helper will `git init` there. To make MPI runs visible from a parent project repo, add the run directory as a **git submodule**, not as a nested directory.

The helper sets in the run repo's local git config (never global): `core.autocrlf false`, `core.eol lf`, `core.hooksPath .git/hooks-disabled`, `commit.gpgsign false` (recommendation). Author identity is required (the helper refuses to invent one); set `user.name` and `user.email` locally per run if you don't have a global identity. The pipeline is local-only by default — never runs `git push` and never configures a remote.

## Tests

`tests/` runs against the installed plugin layout. Test files map roughly to phases:

- `test_plugin_structure.py` — manifest, agents, skills, commands exist and are well-formed
- `test_verify_mpi_init.py` — init skill and manifest schema
- `test_transcript_prep.py` — utterance/speaker normalisation
- `test_mpi_synchronic_logic.py` — ISU coding logic
- `test_cross_participant_analysis.py` — generic/global aggregation
- `test_hypothesis_generation.py` — causal hypothesis output
- `test_mpi_orchestration.py` — `/mpi all`, yolo mode, status
- `test_irr_calibration.py`, `test_irr_fidelity_docs.py` — IRR record schema, alignment regression, rater_kind labels
- `test_close_enforcement_2.py` — GATES registry, `inputs` verb, downgrade/abort postures
- `test_analysis_fidelity.py`, `test_hypothesis_evidence.py`, `test_causal_extension.py` — remediation-plan ACs (schema + doc-grep tests per AC)

Run with `pytest` from repo root.

## Scripts

Helper scripts live inside the plugin (`microphenomenograph/1.0.0/scripts/`):

- `irr.py` — IRR calibration module (Phase 13, landed); computes α/κ/αU/ARI with bootstrap CIs. Absorbs the former `kappa.py` Cohen's κ logic (grounded in `osf-archive/R/kappa.Rmd`). Note: αU here is a boundary-agreement approximation, not the canonical length-weighted Krippendorff αU continuum formula. Since 2026-06-06: alignment maps keyed alternate→primary (records from before the fix are not comparable); records carry `rater_kind` + `caveat` (same-model runs are labeled intra-model consistency, not IRR).
- `test_kappa.py` — legacy κ unit tests; skipped (logic merged into `irr.py` in Phase 13)
- `test_irr.py` — unit tests for `irr.py` metrics (α/κ/αU/ARI, sort keys, bootstrap)
- `convert_osf_analyses.py` — one-shot XLSX → markdown converter used to populate `examples/analyses/`

## Conventions

- Analysis is zero-shot — no examples are injected into prompts. OSF analyses in `examples/analyses/` are acceptance test fixtures only.
- Plugin version is pinned in `microphenomenograph/1.0.0/`; bump the directory name for new versions, do not edit in place after release.
- Freshness dates: always use `date +%Y-%m-%d` when updating CLAUDE.md files.

### HTML documentation

When writing HTML docs in `docs/design-plans/` (e.g. novice-reader walkthroughs of design plans), **do not inline CSS**. Link to the shared stylesheet:

```html
<link rel="stylesheet" href="style.css">
```

`docs/design-plans/style.css` provides the Gruvbox-light palette plus utility classes for the rest of the doc:

- Layout: `body` defaults, headings, `code`/`pre`, tables, links
- Callouts: `.callout`, `.callout-warning`, `.small`, `.step`
- TOC block: `.toc`
- Figures and SVG diagrams: `figure`, `figcaption`, plus SVG classes `.svg-box`, `.svg-box-{llm,orch,user,artifact,audit}`, `.svg-arrow`, `.svg-arrow-{dashed,derived}`, `.svg-text`, `.svg-text-{small,label}`, and legend classes `.legend`, `.l-{llm,orch,user,art,audit}`

For SVG diagrams that use `.svg-arrow*` classes, the HTML body must also include the arrow marker `<defs>` block (UUIDs `arrow`, `arrow-red`, `arrow-amber`) — see `2026-05-17-doc-as-done.html` for the canonical example.

Naming convention for HTML walkthroughs: `YYYY-MM-DD-<slug>.html`, same slug as the source design plan.

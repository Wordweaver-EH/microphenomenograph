# microphenomenograph repo

_Last updated: 2026-05-18 (design fb65db5; Plan 1 Phases 1–6 implemented)_

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
| `bookowhy_rev.md` | Causal framing reference used by the `mpi-hypothesis` skill. |
| `manual_2018.md`, `manual_kev.md` | Microphenomenology methodology references. |
| `runs/` | MPI run directories (e.g. `runs/phase1-2026-05-17/`). Each run is its own git scope; see Operational requirements. |

## Plugin contracts

The plugin's own contracts (pipeline stages, data formats, manifest schema, execution modes) live in `microphenomenograph/1.0.0/CLAUDE.md`. Read that file before modifying plugin internals.

**Documentation-as-Done contract.** Every pipeline step closes via `scripts/mpi_step.py` (transactional close protocol: artifact + audit event + manifest mutation + git commit, all keyed by `close_id`). See `docs/design-plans/2026-05-17-doc-as-done.md` (`fb65db5`) for the full design — 13 implementation phases split across two implementation plans; 34 acceptance criteria; transcript-span grounding mandatory; replay-grade prompt capture; bootstrap CIs for IRR (Krippendorff α + Cohen κ + αU block-bootstrap + ARI). Walkthrough at `docs/design-plans/2026-05-17-doc-as-done.html`.

**Implementation status (Plan 1).** Phases 1–6 are landed: `scripts/mpi_step.py` exposes verbs `init`, `close`, `render`, `verify`, `unlock`, `accept-head`; `scripts/_mpi_schemas.py` carries per-substep schemas plus `validate_prompt_artifact`; `scripts/_mpi_atomic.py` provides atomic file primitives; `agents/mpi-analyst.md` declares Write/Bash tools, persistence rules, and anti-fabrication guards; `mpi-diachronic` / `mpi-synchronic` SKILL.md files include the Closure subsection that drives self-persisted artifacts. Tests live alongside (`scripts/test_mpi_step.py`) and under `tests/test_mpi_analyst_contract.py`. Plan 2 (Phases 7, 9–13) is not yet implemented.

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

Run with `pytest` from repo root.

## Scripts

Helper scripts live inside the plugin (`microphenomenograph/1.0.0/scripts/`):

- `kappa.py` — Cohen's κ computation; backs the `mpi-kappa` skill
- `test_kappa.py` — unit tests for kappa, grounded in `osf-archive/R/kappa.Rmd`
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

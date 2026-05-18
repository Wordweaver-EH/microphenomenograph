# microphenomenograph repo

_Last updated: 2026-05-18_

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

## Plugin contracts

The plugin's own contracts (pipeline stages, data formats, manifest schema, execution modes) live in `microphenomenograph/1.0.0/CLAUDE.md`. Read that file before modifying plugin internals.

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

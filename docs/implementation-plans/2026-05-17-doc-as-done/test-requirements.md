# Plan 2 Test Requirements — Documentation-as-Done Contract

_Generated: 2026-06-02. Source of truth: `docs/design-plans/2026-05-17-doc-as-done.md` (design `fb65db5`) and the six Plan 2 implementation phases (`phase_07.md`, `phase_09.md`, `phase_10.md`, `phase_11.md`, `phase_12.md`, `phase_13.md`)._

## Scope and conventions

This document maps every acceptance criterion (AC) that **Plan 2** (Phases 7, 9, 10, 11, 12, 13) covers to either an automated test or a human-verification step. Plan 1 (Phases 1–6) is already implemented and out of scope; ACs verified only there (most of AC1.4, AC2.x, AC3.1–3.2, AC4.x, AC10.1–10.4, AC11.1–11.3, AC11.5–11.7, AC12.x, AC15.x, AC19.x, AC21.x, AC22.x, AC26.x, AC29.x, AC33.x, AC34.x) are not listed.

Plan 2 is **not yet implemented**. Test file paths and test function/class names below are therefore *proposed* targets derived from each task's `Verifies` line and `Testing` block. Names the implementation plan states verbatim are marked **(stated)**; names this document proposes are marked **(expected)**.

Path conventions used throughout:

- Plugin-internal unit tests live **inside the plugin**: `microphenomenograph/1.0.0/scripts/test_*.py` (e.g. `test_irr.py`, `test_kappa.py`, `test_mpi_step.py`).
- Suite-level tests live under `tests/` (e.g. `tests/test_e2e_pipeline.py`, `tests/test_plugin_structure.py`).

Status legend:

- **AUTOMATED** — a deterministic test (no live LLM call) fully asserts the criterion.
- **AUTOMATED (proxy)** — a test exists but asserts a weaker surrogate (string/structural presence) rather than the substantive behaviour.
- **HUMAN_VERIFIED** — the criterion requires human judgment or LLM-in-the-loop behaviour that no deterministic test can establish.
- **GAP** — no Plan 2 task creates a test for this criterion; a test is proposed here.

---

## Coverage table

| AC | Phase / Task | Type | Test file | Test (proposed unless noted) | Status |
|---|---|---|---|---|---|
| AC6.1 | 7 / T1–T2 | unit | `tests/test_mpi_cross_analyst_contract.py` | `test_tools_line_declares_read_write_bash` (expected) | AUTOMATED |
| AC6.2 | 7 / T1–T2 | unit | `tests/test_mpi_cross_analyst_contract.py` | `test_persistence_subsection_present` (expected) | AUTOMATED |
| AC10.5 | 7 / T1–T2 | unit | `tests/test_mpi_cross_analyst_contract.py` | `test_persistence_enumerates_llm_substeps` / `test_orchestrator_substeps_absent` (expected) | AUTOMATED |
| AC23.1 | 7 / T1, T4 | unit + integration | `tests/test_mpi_cross_analyst_contract.py` | `test_claim_level_schema_present` + hypothesis fixture close (expected) | AUTOMATED |
| AC23.2 | 7 / T1, T4 | unit + integration | `tests/test_mpi_cross_analyst_contract.py` | `test_raw_span_refs_present` + hypothesis fixture close (expected) | AUTOMATED |
| AC23.5 | 7 / T1, T4 | unit + integration | `tests/test_mpi_cross_analyst_contract.py` | hypothesis fixture asserts `sample_summary.by_iv_level` (expected) | AUTOMATED |
| AC28.5 | 7 / T1, T3, T4 | integration | `tests/test_mpi_cross_analyst_contract.py` | generic-diachronic + hypothesis fixture span-chain close (expected) | AUTOMATED (proxy) |
| AC6.3 | 9 / T1–T4, T6; 13 / T4 | unit | `tests/test_plugin_structure.py` | `test_every_skill_has_closure_subsection` (expected) | AUTOMATED |
| AC6.4 | 9 / T4, T5, T6 | unit + integration | `tests/test_plugin_structure.py`; `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `test_mpi_status_read_only_closure` (expected); `--status read` behaviour test | AUTOMATED |
| AC7.1 | 9 / T6 | unit | `tests/test_plugin_structure.py` | `test_no_skill_handspecs_manifest_or_commit_format` (expected) | AUTOMATED (proxy) |
| AC5.3 | 10 / T1–T3 | unit | `tests/test_plugin_structure.py` | `test_anti_fabrication_rule_in_generative_files` (expected) | AUTOMATED |
| AC5.4 | 10 / T1 | — | — | LLM-in-the-loop behavioural check | HUMAN_VERIFIED |
| AC1.1 | 11 / T2 | integration | `tests/test_e2e_pipeline.py` | phased-close event-sequence assertion (expected) | AUTOMATED |
| AC1.2 | 11 / T6 | integration | `tests/test_e2e_fail_fast.py` | commit-failure rollback assertion (expected) | AUTOMATED |
| AC1.3 | 11 / T6 | integration | `tests/test_e2e_fail_fast.py` | audit-append-failure assertion (expected) | AUTOMATED |
| AC1.5 | 11 / T2 | integration | `tests/test_e2e_pipeline.py` | three-way done join (manifest + audit + git tree) (expected) | AUTOMATED |
| AC7.2 | 11 / T2 | integration | `tests/test_e2e_pipeline.py` | audit-schema field assertion (expected) | AUTOMATED |
| AC7.3 | 11 / T2 | integration | `tests/test_e2e_pipeline.py` | constant `trace_id` / unique `event_id` (expected) | AUTOMATED |
| AC8.1 | 11 / T1, T2 | integration | `tests/test_e2e_pipeline.py` | every artifact exists + non-empty (expected) | AUTOMATED |
| AC8.2 | 11 / T1, T2 | integration | `tests/test_e2e_pipeline.py` | manifest/audit/git-log assertions (expected) | AUTOMATED |
| AC8.3 | 11 / T6 | integration | `tests/test_e2e_fail_fast.py` | malformed-unit / unknown-stage / no-half-write (expected) | AUTOMATED |
| AC11.4 | 11 / T2 | integration | `tests/test_e2e_pipeline.py` | `mpi.prompt_artifact_path` per LLM event (expected) | AUTOMATED |
| AC16.1 | 11 / T3 | integration | `tests/test_e2e_pipeline.py` | cascade reset single manifest write (expected) | AUTOMATED |
| AC16.2 | 11 / T3 | integration | `tests/test_e2e_pipeline.py` | `cascade_reset` event with `cascade_source` (expected) | AUTOMATED |
| AC20.6 | 11 / T2, T4 | integration | `tests/test_e2e_pipeline.py` | `run_lease_held` assertion (expected) | AUTOMATED |
| AC20.7 | 11 / T2, T4 | integration | `tests/test_e2e_pipeline.py` | `substep_reservation_held` assertion (expected) | AUTOMATED |
| AC28.3 | 11 / T5, T6 | integration | `tests/test_e2e_fail_fast.py` | `span_out_of_range` / `missing_span_refs` (expected) | AUTOMATED |
| AC28.4 | 11 / T5, T6 | integration | `tests/test_e2e_fail_fast.py` | `span_excerpt_mismatch` (expected) | AUTOMATED |
| AC30.1 | 11 / T2, T3 | integration | `tests/test_e2e_pipeline.py` | artifacts moved to `_superseded/<close_id>/` (expected) | AUTOMATED |
| AC30.2 | 11 / T2, T3 | integration | `tests/test_e2e_pipeline.py` | `tombstone.json` written (expected) | AUTOMATED |
| AC30.3 | 11 / T2, T3 | integration | `tests/test_e2e_pipeline.py` | status/render surfaces superseded count (expected) | AUTOMATED |
| AC9.1 | 12 / T1, T5 | — | (`pytest -q` green only) | no content-asserting test | HUMAN_VERIFIED |
| AC9.2 | 12 / T2, T5 | — | (`pytest -q` green only) | no content-asserting test | HUMAN_VERIFIED |
| AC13.1 | 13 / T6 | integration | `tests/test_irr_calibration.py` | calibrate writes `analyses/independent/` artifacts (expected) | AUTOMATED |
| AC13.2 | 13 / T5 | unit | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | auto-trigger after calibration substep close (expected) | AUTOMATED |
| AC13.3 | 13 / T5 | unit (yolo path only) | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `irr_alignment_auto_accepted` event (expected) | AUTOMATED (yolo) + HUMAN_VERIFIED (assisted) |
| AC13.4 | 13 / T1, T2 | unit | `microphenomenograph/1.0.0/scripts/test_irr.py` | union coincidence matrix / asymmetric marginals (expected) | AUTOMATED |
| AC13.5 | 13 / T1, T2 | unit | `microphenomenograph/1.0.0/scripts/test_irr.py` | four metrics + bootstrap CI (expected) | AUTOMATED |
| AC13.6 | 13 / T6 | integration | `tests/test_irr_calibration.py` | JSONL record schema fields (expected) | AUTOMATED |
| AC13.7 | 13 / T6 | integration | `tests/test_irr_calibration.py` | `outcome` rule on `alpha.ci_lo` (expected) | AUTOMATED |
| AC13.8 | 13 / T5, T6 | unit | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `irr_warning` on low/missing (expected) | AUTOMATED |
| AC13.9 | 13 / T5, T6 | unit | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `--strict-irr` → `irr_check_failed` (expected) | AUTOMATED |
| AC13.10 | 13 / T2 | unit | `microphenomenograph/1.0.0/scripts/test_irr.py` | identical→1 / random→0 / <2s / determinism / asymmetric (stated) | AUTOMATED |
| AC24.1 | 13 / T4 | — | mpi-irr SKILL.md only | strategy documented; init parsing untested | GAP |
| AC24.2 | 13 / T4 | — | mpi-irr SKILL.md only | stratified sampling untested | GAP |
| AC24.3 | 13 / T4 | — | mpi-irr SKILL.md only | empty-stratum refusal untested | GAP |
| AC24.4 | 13 / T6 | integration | `tests/test_irr_calibration.py` | stratified aggregate record (expected) | AUTOMATED |
| AC25.1 | 13 / T6 | integration | `tests/test_irr_calibration.py` | `metrics.alpha_pre_alignment` present (expected) | AUTOMATED |
| AC25.2 | 13 / T6 | integration | `tests/test_irr_calibration.py` | `metrics.alpha_sensitivity_low_conf_excluded` present (expected) | AUTOMATED |
| AC25.3 | 13 / T6 | integration | `tests/test_irr_calibration.py` | `alignment.confidence_distribution` present (expected) | AUTOMATED |
| AC31.1 | 13 / T6 | unit | `tests/test_irr_calibration.py` | default `"stratified"` via docstring/constant (stated proxy) | AUTOMATED (proxy) |
| AC31.2 | 13 / T4 | — | mpi-irr SKILL.md only | `stratified_unavailable` refusal untested | GAP |
| AC32.1 | 13 / T1, T2 | unit | `microphenomenograph/1.0.0/scripts/test_irr.py` | block bootstrap + `alpha_u_block_length` (expected) | AUTOMATED |
| AC32.2 | 13 / T1, T2 | unit | `microphenomenograph/1.0.0/scripts/test_irr.py` | `bootstrap.method` discloses scheme (expected) | AUTOMATED |
| AC32.3 | 13 / T2 | unit | `microphenomenograph/1.0.0/scripts/test_irr.py` | block-CI wider than naive on shuffled input (stated) | AUTOMATED |

Enumerated-AC count: 50 (AC6.1, 6.2, 6.3, 6.4, 5.3, 5.4, 7.1, 7.2, 7.3, 10.5, 23.1, 23.2, 23.5, 28.5, 1.1, 1.2, 1.3, 1.5, 8.1, 8.2, 8.3, 11.4, 16.1, 16.2, 20.6, 20.7, 28.3, 28.4, 30.1, 30.2, 30.3, 9.1, 9.2, 13.1–13.10, 24.1–24.4, 25.1–25.3, 31.1, 31.2, 32.1–32.3). All are present in the table above.

---

## Per-AC detail

### Phase 7 — `mpi-cross-analyst` self-persistence

**AC6.1 — tools line declares `Read, Write, Bash` — AUTOMATED.**
Scope: the *cross-analyst* half only (the analyst half was verified in Plan 1 / Phase 6). `tests/test_mpi_cross_analyst_contract.py` (Phase 7 Task 2) parses the frontmatter of `agents/mpi-cross-analyst.md` and asserts all three tool names are present. Pure string/frontmatter parse, no LLM.

**AC6.2 — "Persistence (mandatory before returning)" subsection — AUTOMATED.**
`tests/test_mpi_cross_analyst_contract.py` asserts the heading `## Persistence (mandatory before returning)` exists. Mirrors `tests/test_mpi_analyst_contract.py`. Structural string match.

**AC10.5 — Persistence enumerates all cross-analyst LLM substeps and excludes orchestrator-only ones — AUTOMATED.**
`tests/test_mpi_cross_analyst_contract.py` (Phase 7 Task 2) asserts presence of all 11 LLM substep names (`generic_diachronic.idu_similarity_grouping`, `…pattern_identification`, `…cross_iv_contrast`, `generic_synchronic.select_generic_idus_of_interest`, `…isu_second_level_grouping`, `global_synchronic`, `hypothesis.evidence_extraction`, `…candidate_drafting`, `…weak_evidence_review`, `irr_calibration.independent_analyst`, `…alignment`) AND absence of the three orchestrator-only names (`participant_row_assembly`, `worksheet_assembly`, `irr_calibration.agreement_computation`). Both presence and absence are string searches.

**AC23.1 — claim-level structure (`claims[]` with required keys) — AUTOMATED.**
Two layers: (a) Phase 7 Task 2 asserts the claim-level schema block exists in the agent file (string presence of `raw_span_refs`, disclaimer text); (b) Phase 7 Task 4 fixture (`tests/fixtures/cross_analyst/dv-automaticity.candidates.json`) is closed through `mpi_step.py close --stage hypothesis --substep candidate_drafting` and must satisfy the claim-level schema in `_mpi_schemas.py`, so a malformed shape is rejected at close. The negative test (missing `disclaimer` → rejected) is asserted here per Task 4 step 7.

**AC23.2 — raw-span anchoring on every `supports`/`contradicts`/`ambiguous` entry — AUTOMATED.**
Phase 7 Task 4 fixture carries `raw_span_refs` consistent with a minimal offset registry created in the tempdir, and closes successfully. Note the ORDERING constraint from Task 4 step 8: the `span_excerpt_mismatch` negative assertion is **deferred to Phase 11 Task 6** (`tests/test_e2e_fail_fast.py`) because `_validate_utterance_refs` does not exist until Phase 11 Task 5. A `# TODO Phase 11 Task 6` placeholder is left in `test_mpi_cross_analyst_contract.py`.

**AC23.5 — `sample_summary.by_iv_level` per candidate — AUTOMATED.**
Phase 7 Task 4 hypothesis fixture must include `sample_summary.by_iv_level`; the close validates it against the schema.

**AC28.5 — cross-stage span-ref chain followable to a transcript utterance — AUTOMATED (proxy).**
Phase 7 Tasks 3 and 4 close fixtures whose `utterance_refs` / `raw_span_refs` resolve against an offset registry in the tempdir. This proves the helper *validates* refs resolve to a transcript; it does not prove the *inheritance chain* from a generic/global/hypothesis unit back through its constituent per-transcript units is reconstructed end-to-end (no full upstream chain is built in the fixture). Treat the deeper chain-followability assertion as partially covered; the E2E pipeline (Phase 11) exercises a fuller chain but a dedicated chain-traversal assertion is not specified.

### Phase 9 — Skill closure sweep + read-only audit mode

**AC6.3 — every SKILL.md has a "Closure (mandatory)" subsection — AUTOMATED. Verified in TWO phases.**
Phase 9 Task 6 (`tests/test_plugin_structure.py`) iterates the 10 skills (`mpi-init`, `mpi-transcript-prep`, `mpi-diachronic`, `mpi-synchronic`, `mpi-generic-diachronic`, `mpi-generic-synchronic`, `mpi-global-synchronic`, `mpi-hypothesis`, `mpi-irr`, `mpi-status`) and asserts each contains `## Closure (mandatory)`. Phase 13 Task 4 fills the `mpi-irr` body but the task note keeps the Closure section unchanged, so AC6.3 for `mpi-irr` is re-affirmed there. Cross-reference both phases.

**AC6.4 — read-only skill declares "no artifact close" and emits `stage_phase: read` — AUTOMATED.**
Two parts. (a) Documentation: Phase 9 Task 6 asserts `mpi-status/SKILL.md` contains both `"no artifact close"` (or equivalent) and `"stage_phase: read"`. (b) Behaviour: Phase 9 Task 5 implements `--status read` in `mpi_step.py`; the behavioural assertion (emits one `stage_read` / `stage_phase: read` event, writes no artifact, no manifest mutation, no commit, exits 0) belongs in `microphenomenograph/1.0.0/scripts/test_mpi_step.py`. Phase 9 Task 5 has no explicit test sub-task — recommend adding the behavioural test alongside the implementation so AC6.4 is not documentation-only.

**AC7.1 — no SKILL.md hand-specifies manifest mutation, log format, or commit message format — AUTOMATED (proxy).**
Phase 9 Task 6 (`tests/test_plugin_structure.py`) does a string search asserting no SKILL.md contains `os.replace`, `project.json.tmp`, bare `reasoning.log` format prose, or hand-crafted `git commit -m "mpi:` lines outside a Closure code block. This is a blocklist-of-strings check, not semantic proof that no hand-specified contract remains; a newly-worded violation would pass. Acceptable proxy for pre-release, but flag as approximate.

### Phase 10 — Anti-fabrication sweep

**AC5.3 — verbatim anti-fabrication rule in all 6 generative SKILL.md + both agent files — AUTOMATED.**
Phase 10 Task 3 (`tests/test_plugin_structure.py`, `-k fabrication`) asserts the string `"Never generate placeholder or synthetic"` is present in the 6 generative skills and both agent files, AND absent from the 3 non-generative skills (`mpi-init`, `mpi-transcript-prep`, `mpi-status`), with no assertion either way for `mpi-irr`. The grep round-trip (Task 2) is the manual acceptance check; the pytest assertion is the durable one.

**AC5.4 — generative skill returns `ERROR` (not synthetic content) on empty/missing input — HUMAN_VERIFIED.**
The design states outright (AC5.4 text and Phase 10 Task description): *"behavioural verification deferred to LLM-in-the-loop testing outside the E2E test."* The deterministic twin is AC5.3 (string presence of the rule). The behaviour itself — that a live model, when handed empty upstream input, actually emits `ERROR <reason>` rather than fabricating — cannot be established by a fixture-driven test, because the E2E suite never invokes a model. A human (or a separate LLM-in-the-loop harness) must run a generative skill against deliberately empty/malformed upstream artifacts and confirm the agent returns an `ERROR` string and writes no synthetic artifact.

### Phase 11 — End-to-end pipeline + fail-fast

Two test files. `tests/test_e2e_pipeline.py` (Task 2) is the happy path; `tests/test_e2e_fail_fast.py` (Task 6) is the negative path. Task 2 must be committed AFTER Tasks 3–5 (cascade reset, lease/reservation, span resolution production code) so its assertions for AC20.6/20.7/30.x/28.x have backing code.

**AC1.1 — full phased-close event sequence sharing one `close_id` — AUTOMATED.**
`tests/test_e2e_pipeline.py` reads `audit.jsonl` and asserts the ordered sequence `close_attempted → artifacts_validated → audit_appended → manifest_replaced → git_commit_succeeded` with a shared `close_id`, and that `git_commit_succeeded` carries `mpi.git_commit_sha`.

**AC1.2 — commit-failure → `git_commit_failed` + `manifest_rolled_back` — AUTOMATED.**
`tests/test_e2e_fail_fast.py` (Task 6) installs a pre-commit hook that exits 1 (via `core.hooksPath`), runs `close`, asserts the manifest rolls back and a commit-failure / `commit_failed` event lands. Do NOT attribute this to the happy-path file: the Task-2 `Verifies` line lists AC1.1/AC1.5 only.

**AC1.3 — audit-append failure leaves manifest untouched — AUTOMATED.**
`tests/test_e2e_fail_fast.py` (Task 6) makes `.mpi/audit.jsonl` read-only, runs `close`, asserts exit non-zero and manifest untouched (no `manifest_replaced`). Restores permissions after.

**AC1.5 — three-way "done" join (manifest + audit + git tree) — AUTOMATED.**
`tests/test_e2e_pipeline.py` picks a sample closed substep, reads its `close_id` from the manifest, finds the matching `git_commit_succeeded` event, resolves `mpi.git_commit_sha` via `git show --name-only`, and asserts the manifest file is in that commit's tree.

**AC7.2 — audit events carry the documented schema fields — AUTOMATED.**
`tests/test_e2e_pipeline.py` parses each audit line and asserts presence of `event_id`, `@timestamp`, `trace_id`, `event.action` (and the per-event `mpi.*` payload). Field-presence check; exhaustive schema conformance to every documented ECS/OTel field is partial.

**AC7.3 — constant `trace_id`, globally unique `event_id` — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts all events share one `trace_id` and all `event_id`s are unique.

**AC8.1 — every expected `analyses/pNsN-<stage>.{md,json}` exists and is non-empty — AUTOMATED.**
`tests/test_e2e_pipeline.py` walks every `(scope, stage, substep)` and asserts the JSON exists with `getsize > 0`. Fixture corpus is 2 participants × 2 suggestions (Task 1).

**AC8.2 — manifest reflects every closure at substep granularity; audit validates; git log shows one commit per substep with canonical message — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts `substeps.<substep>.status == "done"` with non-empty `output_paths` for every transcript × substep, validates `audit.jsonl`, and counts `git log --oneline` against the expected commit count (e.g. 12 diachronic + 24 synchronic LLM closes plus orchestrator substep commits).

**AC8.3 — malformed unit / unknown stage → exit non-zero, manifest unchanged, no commit, no half-written artifact — AUTOMATED.**
`tests/test_e2e_fail_fast.py` (Task 6) feeds `confidence: 9` and `--stage fakeStage`, asserts named error, unchanged `pending` manifest, empty `git log`, and no `.tmp` leftover.

**AC11.4 — every LLM-substep audit event carries `mpi.prompt_artifact_path` — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts each LLM-substep close event has a non-empty `mpi.prompt_artifact_path`.

**AC16.1 — re-closing `diachronic.criteria_revision` resets downstream substeps in a single manifest write — AUTOMATED.**
`tests/test_e2e_pipeline.py` (Task 3 production code, Task 2 assertions) re-closes `criteria_revision` for `p1s1` and asserts `idu_naming_ordering`, all scoped `synchronic.*`, and all cross-participant substeps revert to `pending` in one write. (AC16.1/16.2 are added by Phase 11 Task 3 beyond the design "Done when" for Phase 11.)

**AC16.2 — each cascade reset emits a `cascade_reset` event with `mpi.cascade_source` — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts one `cascade_reset` event per reset substep, each referencing the revision's `event_id` as `cascade_source`.

**AC20.6 — second concurrent `/mpi all` errors `run_lease_held` immediately — AUTOMATED.**
`tests/test_e2e_pipeline.py` (Task 2/Task 4) holds `.mpi/run.lease` with a live PID and asserts a second run-lease acquisition returns `run_lease_held` without waiting. Production code in Phase 11 Task 4.

**AC20.7 — second `close` for same `(stage, substep, scope)` errors `substep_reservation_held` — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts the second concurrent reservation for an identical triple is refused. Reservation file written before LLM work, deleted on commit/rollback (Phase 11 Task 4).

**AC28.3 — span ref out of range → `span_out_of_range` (also `missing_span_refs`/`offset_registry_missing`) — AUTOMATED.**
`tests/test_e2e_fail_fast.py` (Task 6) feeds a ref pointing at a missing transcript / out-of-registry utterance / out-of-file byte range and asserts `span_out_of_range`, manifest unchanged. Backed by `_validate_utterance_refs` (Phase 11 Task 5). The `missing_span_refs` (empty `utterance_refs: []`) case is also asserted here.

**AC28.4 — `raw_excerpt` mismatch → `span_excerpt_mismatch` — AUTOMATED.**
`tests/test_e2e_fail_fast.py` (Task 6) feeds a ref whose excerpt does not match the resolved bytes and asserts `span_excerpt_mismatch` with both excerpts surfaced. This absorbs the deferred negative test from Phase 7 Task 4.

**AC30.1 — cascade moves affected artifacts to `analyses/_superseded/<close_id>/` — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts prior artifact triples are relocated under `_superseded/<revision_close_id>/`. Production in Phase 11 Task 3.

**AC30.2 — `tombstone.json` per `_superseded/<close_id>/` directory — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts the tombstone exists with `cascade_source`, `reset_at`, `reset_substeps`, `reason` and is committed.

**AC30.3 — `/mpi status` (and render) surface superseded counts — AUTOMATED.**
`tests/test_e2e_pipeline.py` asserts `mpi_step.py status` / `render` output mentions superseded close_id counts. Render-side count surfacing implemented in Phase 11 Task 3.

> Cross-reference (not a Plan 2 AC): **AC3.3** (render idempotency, a Plan 1 AC) is re-exercised by `tests/test_e2e_pipeline.py`'s render round-trip step (run `render` twice, assert byte-identical). Listed here only for traceability; no new Plan 2 entry.

### Phase 12 — Documentation alignment + test reconciliation

**AC9.1 — plugin CLAUDE.md has the contract section, documents the substep DAG, removes legacy output-path table + reasoning.log note — HUMAN_VERIFIED.**
Phase 12 Task 1 edits `microphenomenograph/1.0.0/CLAUDE.md`; Task 5 only runs `pytest -q` for a green suite. No task creates a test asserting CLAUDE.md content. A string-presence test could confirm the `## Substep DAG` heading exists and the old `analyses/pNsN-{stage}.md` table string is absent, but the substantive criteria — that the DAG table is *accurate*, that the legacy reasoning.log format note is genuinely gone (not merely reworded), and that nothing contradictory remains — require a human to read the file against the design. Recommend a human reviewer diffs the section against the design's Substep DAG table and confirms removals; optionally add a lightweight heading-presence/old-table-absence assertion as a partial guard.

**AC9.2 — top-level CLAUDE.md references the contract in one sentence under "Plugin contracts" — HUMAN_VERIFIED.**
Phase 12 Task 2 edits `C:\microphenomenograph\CLAUDE.md`. Same reasoning as AC9.1: no content-asserting test; whether the one-sentence reference is present and correctly describes both mpi-analyst and mpi-cross-analyst self-persistence is a human read. A heading/keyword-presence test is a weak partial guard.

### Phase 13 — IRR calibration (α + κ + αU + ARI with bootstrap CIs)

**AC13.1 — `mpi-irr calibrate` runs alternate-agent re-analysis writing `analyses/independent/` artifacts — AUTOMATED.**
`tests/test_irr_calibration.py` (Phase 13 Task 6) exercises the calibration flow with fixtures (no LLM) and asserts alternate artifacts land under `analyses/independent/<pNsN>-<stage>.<substep>.{json,md,prompt.json}`. The live alternate-agent dispatch (an actual independent model run) is itself not testable deterministically; the fixture asserts the orchestration and on-disk structure.

**AC13.2 — orchestrator auto-triggers calibration after diachronic and synchronic close — AUTOMATED.**
Backed by `_maybe_trigger_irr_calibration` (Phase 13 Task 5). `microphenomenograph/1.0.0/scripts/test_mpi_step.py` should assert that closing `diachronic.idu_naming_ordering` (and the last `synchronic.isu_second_level_grouping`) for a calibration transcript appends an `irr_calibration_scheduled` audit event, and that non-calibration transcripts do not trigger it.

**AC13.3 — alignment substep; yolo auto-accept emits `irr_alignment_auto_accepted`; assisted user accept/edit — AUTOMATED (yolo) + HUMAN_VERIFIED (assisted).**
The yolo path (auto-accept + `irr_alignment_auto_accepted` event) is deterministically testable in `microphenomenograph/1.0.0/scripts/test_mpi_step.py`. The assisted-mode path ("user accepts/edits the mapping before metrics run" via AskUserQuestion) is interactive and cannot be automated; a human must run a calibration in assisted mode and confirm the proposed mapping is surfaced and editable before metrics compute. Note: no Plan 2 task's `Verifies` line names AC13.3 directly — this is a coverage thinness to flag.

**AC13.4 — union-of-categories coincidence matrix per Krippendorff (2011) — AUTOMATED (with methodology caveat).**
`microphenomenograph/1.0.0/scripts/test_irr.py` (Task 2) exercises `compute_coincidence` including the asymmetric-marginal case (one rater uses more categories; only-one-rater categories appear with zero diagonal + nonzero marginal). The boundary tests prove the matrix is computable and honest about asymmetry; *fidelity of the formula to Krippendorff (2011) eq. 1–6* is ultimately a methodologist's review, not provable by identical/random boundary tests.

**AC13.5 — four metrics, each with 95% bootstrap CI (N=5000); shared indices for α/κ/ARI, block for αU — AUTOMATED.**
`microphenomenograph/1.0.0/scripts/test_irr.py` asserts all four metrics return `{point, ci_lo, ci_hi}`, that α/κ/ARI reuse the same bootstrap indices, and αU uses block resampling.

**AC13.6 — JSONL record matches the DoD #8 schema — AUTOMATED.**
`tests/test_irr_calibration.py` (Task 6) builds a record via `irr.compute_irr()` and asserts every required field: `stage`, `participant_id`, `transcript_id`, `primary_model`, `alternate_model`, `alignment`, `metrics.{alpha,kappa,alpha_u,ari}`, `n_utterances`, `n_bootstrap`, `bootstrap_seed`, `outcome`.

**AC13.7 — `outcome == "passed"` iff `alpha.ci_lo >= 0.6` — AUTOMATED.**
`tests/test_irr_calibration.py` asserts `passed` when `ci_lo >= 0.6` and `low` when `ci_lo < 0.6`.

**AC13.8 — cross-participant skills emit `irr_warning` if most-recent IRR is low/absent — AUTOMATED.**
`microphenomenograph/1.0.0/scripts/test_mpi_step.py` asserts that closing a `generic_diachronic.*` substep without `--strict-irr`, with `outcome: "low"` (or no IRR record), still succeeds (exit 0) and writes an `irr_warning` event. Backed by `_check_irr_gate` (Task 5).

**AC13.9 — `--strict-irr` with missing/low IRR exits with `irr_check_failed` before producing artifacts — AUTOMATED.**
`microphenomenograph/1.0.0/scripts/test_mpi_step.py` asserts `--strict-irr` + no/low IRR → exit non-zero with `irr_check_failed`, and `--strict-irr` + `outcome: "passed"` → exit 0.

**AC13.10 — `irr.py` unit tests: identical→1, random→0, <2s bootstrap, deterministic CIs, asymmetric marginals — AUTOMATED.**
`microphenomenograph/1.0.0/scripts/test_irr.py` (Task 2) — the test cases are stated verbatim in the plan (`time.monotonic()` < 2.0s for a 70-utterance fixture at N=5000; byte-identical repeat with fixed seed; etc.).

**AC24.1 — `study.calibration_transcript` set at init from `--calibration <strategy>` — GAP.**
Documented in `mpi-irr/SKILL.md` (Phase 13 Task 4) but no Plan 2 task creates a test that init parses `--calibration` and persists the field with the three valid strategies (`stratified`, specific id, `first` with `calibration_mode: smoke_test`). Proposed test: `tests/test_verify_mpi_init.py` asserting each strategy persists the correct `study.calibration_transcript` / `study.calibration_mode`.

**AC24.2 — `"stratified"` generates one transcript per (suggestion × IV-level) via seeded sampling; persists `calibration_transcript_ids` — GAP.**
No Plan 2 task tests the deterministic stratified sampling. Proposed test: `tests/test_irr_calibration.py` (or `test_verify_mpi_init.py`) seeds a small corpus and asserts the sampled `calibration_transcript_ids` list is deterministic and one-per-stratum.

**AC24.3 — `"stratified"` rejected when any stratum has zero transcripts (`stratified_unavailable`/named stratum) — GAP.**
No Plan 2 task tests this refusal. Proposed test: `tests/test_verify_mpi_init.py` builds a corpus with an empty stratum and asserts init refuses, naming the offending stratum. (Closely related to AC31.2.)

**AC24.4 — stratified produces per-stratum records + one aggregate summary per stage; aggregate `outcome` on pooled α CI — AUTOMATED.**
`tests/test_irr_calibration.py` (Task 6) builds two `record_type: "stratum"` records, pools their bootstrap distributions, and asserts the aggregate has `record_type: "aggregate"`, `n_strata: 2`, recomputed `metrics.*`, and `outcome` from the pooled α CI lower bound.

**AC25.1 — record includes `metrics.alpha_pre_alignment` — AUTOMATED.**
`tests/test_irr_calibration.py` asserts the field exists with a `point` value.

**AC25.2 — record includes `metrics.alpha_sensitivity_low_conf_excluded` — AUTOMATED.**
`tests/test_irr_calibration.py` asserts the field exists with a `point` value (α recomputed after dropping confidence < 0.7 mappings).

**AC25.3 — `alignment.confidence_distribution` = {min, p25, median, p75, max} — AUTOMATED.**
`tests/test_irr_calibration.py` asserts all five percentile keys are present.

**AC31.1 — default calibration is `"stratified"`; `"first"` is opt-in with smoke-test flag — AUTOMATED (proxy).**
Phase 13 Task 6 verifies this "via docstring or module-level constant" in `irr.py`. That checks the *documented default*, not the *init behaviour* (that running `/mpi init` with no `--calibration` actually persists `"stratified"`, and that `--calibration first` prompts and sets `calibration_mode: smoke_test`). Represented as a weak proxy; the behavioural half overlaps the AC24.1 gap and would be strengthened by the proposed `test_verify_mpi_init.py` test.

**AC31.2 — corpus too small for stratified refuses with `stratified_unavailable` and prompts for fallback — GAP.**
No Plan 2 task tests the refusal-and-prompt behaviour. Proposed test: `tests/test_verify_mpi_init.py` asserts init with an empty stratum refuses with `stratified_unavailable` and that the documented fallback (specific id or `first` + smoke-test) is offered. Overlaps AC24.3.

**AC32.1 — αU bootstrap uses contiguous block resampling (block length √N); records `bootstrap.alpha_u_block_length` — AUTOMATED.**
`microphenomenograph/1.0.0/scripts/test_irr.py` asserts αU's bootstrap is block-based and the block length (`max(1, round(n**0.5))`) is recorded.

**AC32.2 — α/κ/ARI use naive utterance resampling; `bootstrap.method` discloses scheme — AUTOMATED.**
`microphenomenograph/1.0.0/scripts/test_irr.py` asserts `bootstrap.method` is `"naive_utterance"` for α/κ/ARI and `"block_utterance"` for αU.

**AC32.3 — block bootstrap necessary, not cosmetic: on shuffled input, block-CI for αU is wider than naive-CI — AUTOMATED.**
`microphenomenograph/1.0.0/scripts/test_irr.py` (Task 2, stated) builds correlated-within-segment data (70 utterances, block length 8) and asserts the block-bootstrap CI for αU is strictly wider than the naive-bootstrap CI on the same data.

---

## Summary of human-verification and gap items

These are the entries that automated tests cannot fully establish and require human action.

| AC | Why automation is insufficient | What a human should check |
|---|---|---|
| AC5.4 | Behavioural; no live model in the deterministic suite (design defers it explicitly). | Run a generative skill against empty/malformed upstream artifacts in an LLM-in-the-loop harness; confirm it returns `ERROR <reason>` and writes no synthetic artifact. |
| AC9.1 | Phase 12 has no CLAUDE.md content-asserting test (only `pytest -q` green). | Read `microphenomenograph/1.0.0/CLAUDE.md`: confirm the contract section, an accurate substep DAG table, and removal (not rewording) of the legacy output-path table and reasoning.log note. |
| AC9.2 | Same; no content assertion. | Read top-level `CLAUDE.md`: confirm a one-sentence contract reference under "Plugin contracts" covering both subagents' self-persistence. |
| AC13.3 (assisted) | AskUserQuestion accept/edit is interactive; no task `Verifies` line names AC13.3. | Run a calibration in assisted mode; confirm the proposed alignment mapping is surfaced and editable before metrics compute. (Yolo auto-accept path is automated.) |
| AC13.4 / AC13.5 / AC32.x (formula fidelity) | Boundary tests prove computability and direction, not conformance to the cited literature formulae. | A methodologist reviews `irr.py` against Krippendorff (2011/2016), Hubert & Arabie (1985), Politis & Romano (1994). |
| AC24.1 / AC24.2 / AC24.3 / AC31.2 | No Plan 2 task creates init-behaviour tests for calibration-strategy parsing, stratified sampling, or empty-stratum refusal. | Add the proposed `tests/test_verify_mpi_init.py` (and/or `tests/test_irr_calibration.py`) tests; until then, a human exercises `/mpi init --calibration {stratified,<id>,first}` and the empty-stratum refusal path manually. |
| AC31.1 (behavioural half) | Task 6 checks only the documented default (docstring/constant), not init behaviour. | Confirm `/mpi init` with no `--calibration` persists `"stratified"`, and `--calibration first` sets `calibration_mode: smoke_test`. Covered by the proposed AC24.1 test. |
| AC6.4 (behavioural half) | Phase 9 Task 5 ships `--status read` with no explicit test sub-task. | Add a `--status read` behaviour test to `microphenomenograph/1.0.0/scripts/test_mpi_step.py` (one `stage_phase: read` event, no artifact/manifest/commit). |
| AC7.1 / AC28.5 (proxy entries) | Blocklist string search / partial chain coverage rather than semantic proof. | Spot-check that no hand-specified contract prose remains (AC7.1) and that a hypothesis claim's span chain is followable to a raw transcript utterance end-to-end (AC28.5). |

# Close Enforcement Round 2 (global-synchronic wiring + advertised-gate implementation) Design

## Summary

This design closes the gap between what the pipeline's skill documentation *claims* to enforce and what `mpi_step.py` actually enforces at close time. Two defects drove the work. First, the `mpi-global-synchronic` skill and the `mpi-cross-analyst` agent were referencing a non-existent artifact (`analyses/generic-synchronic.md`) as their input — meaning the global-synchronic stage was wired to a path that is never written by the pipeline. Second, several enforcement rules described in the diachronic and synchronic SKILL.md files (convergence check, temporal-order flag, IDU-split audit event) existed only as documentation, with no corresponding code in `cmd_close` to enforce them.

The plan delivers two cross-cutting mechanisms, then builds the specific fixes on top of them. The first mechanism is a declarative `GATES` registry in `_mpi_schemas.py`: each gate has an ID, a check function, and a default posture of warn-only (close succeeds but appends a `gate_warning` event to the audit log). Studies can opt individual gates into strict mode — either by listing them in the manifest at `confirm_study_config`, or by passing `--strict-<gate_id>` at the command line — making the enforcement regime part of the citable study methodology. The second mechanism is an `inputs` resolution verb (`mpi_step.py inputs --scope --stage`) that derives the correct upstream artifact paths from manifest records rather than having analysts guess or remember literal filenames; the analyst echoes back which inputs it consumed, and `cmd_close` verifies that set against what was resolved. The wiring fixes and enforcement rules (convergence downgrade, temporal-order block, global-synchronic provenance, event-count precondition, IDU-split audit event) are then implemented as registered gates and schema rules built on these two foundations.

## Definition of Done

All gates below follow the **warn-by-default** convention (consistent with `--strict-irr`): close succeeds with a structured warning; opt-in strict flags block. Artifact *shape* validation (schema fields) remains hard, per existing convention.

- **Global-synchronic wiring fixed**: `mpi-global-synchronic/SKILL.md` and `mpi-cross-analyst.md` reference the real per-scope generic-synchronic artifacts (`event<E>-cat-<C>-gidu<G>-generic_synchronic.isu_second_level_grouping.{json,md}`) instead of the non-existent `analyses/generic-synchronic.md`; the singular `global-synchronic.md` output path contradiction is resolved to the per-scope closure-table form.
- **≥2-events gate**: closing `global_synchronic` for a gidu that appears in fewer than 2 events emits a named warning (`global_synchronic_single_event`); a strict flag blocks.
- **Event provenance**: `source_event` is a required field on each global-synchronic ISU in `_validate_global_synchronic` (shape validation — hard).
- **Convergence enforcement**: a `criteria_revision` close with `decision == "more_revision_needed"` auto-downgrades the substep to `flagged` status (close succeeds, audit chain intact); downstream `idu_naming_ordering` is blocked while flagged; the 5-pass cap stays a SKILL/orchestrator convention.
- **Temporal-order flag enforcement**: `cmd_close` reads the `theme_grouping_within_idu` artifact; `temporal_order_within_idu: true` sets substep status `flagged`, blocking `isu_naming` until a diachronic re-close resolves it; co-presence rule: `temporal_order_within_idu: true` requires ≥1 ISU with `flag_for_review: true` (schema — hard).
- **Flag unification**: `mpi-analyst.md` synchronic rule 4 instructs setting both `flag_for_review` and `temporal_order_within_idu`.
- **Audit event**: `idu_split_after_synchronic` is emitted by `cmd_close` when a diachronic re-close follows a synchronic trigger, linking both span_ids — making the SKILL.md documentation true.
- Regression tests for each gate (warn path + strict-block path) pass; existing tests pass.

Out of scope: implementation of analysis-prompt fidelity fixes (plan 3); hypothesis-stage changes (plan 4); migration of existing `runs/` (disposable).

This plan is **second in sequence** (plan 2 of 5); plans 3+ may overlap but plan 4 hard-depends on the wiring fix here.

## Acceptance Criteria

### close-enforcement-2.AC1: Gate registry with manifest strictness
- **close-enforcement-2.AC1.1 Success:** A failing gate not in `study.strict_gates` lets close succeed and emits a `gate_warning` audit event carrying `close_id` and `gate_id`
- **close-enforcement-2.AC1.2 Success:** The same failing gate listed in `study.strict_gates` aborts the close before manifest mutation
- **close-enforcement-2.AC1.3 Success:** CLI `--strict-<gate_id>` enforces strictness when the manifest does not declare it
- **close-enforcement-2.AC1.4 Success:** `--strict-irr` behaves identically to the registry's `irr_below_threshold` strict mode (alias preserved)
- **close-enforcement-2.AC1.5 Success:** `mpi_step.py verify` reports every `gate_warning` event in the audit log

### close-enforcement-2.AC2: Helper-resolved input wiring
- **close-enforcement-2.AC2.1 Success:** `inputs --scope <s> --stage <st>` returns the correct per-scope upstream artifact paths + SHAs for each cross-participant stage (generic_diachronic, generic_synchronic, global_synchronic)
- **close-enforcement-2.AC2.2 Failure:** A close whose artifact's `inputs_consumed` is not a subset of the resolved set triggers the `undeclared_input` gate (warn default, abort strict)
- **close-enforcement-2.AC2.3 Success:** Grep of `mpi-global-synchronic/SKILL.md` and `mpi-cross-analyst.md` finds no literal cross-stage artifact filename (the dead `generic-synchronic.md` reference is gone)

### close-enforcement-2.AC3: Global-synchronic provenance and preconditions
- **close-enforcement-2.AC3.1 Failure:** A global-synchronic ISU without `source_event` is rejected at close (hard shape)
- **close-enforcement-2.AC3.2 Success:** Closing a `gidu<G>-cat-<C>` scope whose gidu appears in < 2 events triggers `single_event_global_synchronic` (warn default, abort strict); ≥ 2 events closes clean

### close-enforcement-2.AC4: Diachronic/synchronic enforcement
- **close-enforcement-2.AC4.1 Success:** A `criteria_revision` close with `decision == "more_revision_needed"` sets substep status `flagged`; `idu_naming_ordering` is blocked while flagged
- **close-enforcement-2.AC4.2 Success:** A `theme_grouping_within_idu` close with `temporal_order_within_idu: true` sets status `flagged`; `isu_naming` is blocked until a diachronic re-close resolves it
- **close-enforcement-2.AC4.3 Failure:** `temporal_order_within_idu: true` with zero `flag_for_review: true` ISUs is rejected by schema (co-presence, hard)
- **close-enforcement-2.AC4.4 Success:** A diachronic re-close following a synchronic temporal-order flag emits `idu_split_after_synchronic` linking both span_ids/close_ids
- **close-enforcement-2.AC4.5 Success:** Every enforcement claim in `mpi-diachronic/SKILL.md` and `mpi-synchronic/SKILL.md` maps to an implemented code path with a test (sweep assertion)

## Glossary

- **IDU (Incipient Diachronic Unit)**: A named temporal moment in a single participant's transcript, produced by diachronic analysis, in experienced order.
- **ISU (Incipient Synchronic Unit)**: A named theme within a single IDU, produced by synchronic analysis. ISUs within an IDU are concurrent (not sequentially ordered).
- **gidu (generic IDU)**: An IDU pattern recurring across participants in generic-diachronic analysis. Numbered `gidu<G>`; a scope key for generic-synchronic and global-synchronic stages.
- **Diachronic / synchronic analysis**: Per-transcript stages: diachronic groups utterances into temporally ordered IDUs; synchronic groups utterances within each IDU into concurrent themes. If synchronic reveals temporal order inside an IDU, the IDU must be split — triggering a return to diachronic.
- **Generic-diachronic / generic-synchronic / global-synchronic**: The cross-participant stages: shared IDU patterns per (event × IV category); ISU regrouping per generic IDU; aggregation of the same generic IDU across multiple events.
- **`cmd_close` / close transaction**: The helper verb (`mpi_step.py close`) that validates an artifact, appends an audit event, updates the manifest, and commits as one atomic sequence. All gating in this design runs inside it.
- **Substep status `flagged`**: Manifest status meaning the close succeeded but remediation is required before downstream steps proceed. Distinct from `error` and `done`.
- **`GATES` registry**: New declarative table in `_mpi_schemas.py` mapping `gate_id` → check function. Failing gates warn by default; strict gates abort before manifest mutation.
- **Warn-by-default / strict mode**: The convention (matching `--strict-irr`) where a failing quality check warns unless the gate is opted into strict — via `study.strict_gates` or `--strict-<gate_id>`.
- **`study.strict_gates`**: Manifest field written at `confirm_study_config` listing strict gate IDs — the enforcement regime becomes citable study methodology.
- **`gate_warning` audit event**: Structured `audit.jsonl` record emitted when a warn-mode gate fires; carries `close_id` + `gate_id`; swept by `mpi_step.py verify`.
- **`idu_split_after_synchronic` audit event**: Emitted when a diachronic re-close is triggered by a synchronic temporal-order flag, linking the span_ids/close_ids of both closes.
- **`inputs` verb**: New `mpi_step.py` subcommand (`inputs --scope <s> --stage <st>`) resolving upstream artifact paths + SHAs from manifest records. Replaces literal filenames in SKILL.md files.
- **`inputs_consumed`**: Field the analyst writes into its artifact listing the upstream paths it actually used; `cmd_close` verifies it is a subset of what `inputs` resolved (`undeclared_input` gate).
- **`PREREQ_SCOPE_TRANSFORMS`**: Existing lookup table mapping cross-participant substep keys to scope-stripping functions; the `inputs` resolution rules live beside it.
- **`source_event`**: Required field on each global-synchronic ISU recording which event (suggestion) the ISU came from. Hard-validated shape.
- **Co-presence rule**: Schema constraint that `temporal_order_within_idu: true` requires ≥1 ISU with `flag_for_review: true` in the same artifact.
- **`criteria_revision` convergence**: The diachronic substep where the analyst declares `more_revision_needed` or `converged`. This design downgrades a non-converged close to `flagged`, blocking `idu_naming_ordering` until re-closed converged.
- **`audit.jsonl` / `span_id` / `close_id`**: Append-only event log; `close_id` is shared across one close transaction's events; `span_id` identifies individual events, used to link related events across separate closes.
- **IV category**: The score grouping (Low 0–1, Moderate 2–3, High 4–5) appearing as `cat-<C>` in scope keys and artifact filenames.
- **`mpi-analyst` / `mpi-cross-analyst`**: The per-participant and cross-participant LLM subagents; both self-persist artifacts and run `mpi_step.py close`.
- **`irr_below_threshold` / `--strict-irr`**: The existing IRR gate, folded into the `GATES` registry with its CLI alias preserved.
- **SKILL-claims-code parity**: The goal that every enforcement claim in a SKILL.md corresponds to a real code path with a test — the absence of which caused this design.

## Architecture

Two cross-cutting mechanisms, then the gates and wiring fixes built on them.

**Gate registry.** `_mpi_schemas.py` gains a `GATES` registry — `{gate_id: {stage, description, check_fn}}` — declaring every warn-by-default gate: `single_event_global_synchronic`, `convergence_pending`, `temporal_order_pending`, `weak_evidence_unreviewed` (check lands in plan 4), `undeclared_input`, and the existing IRR gate folded in as `irr_below_threshold` (with `--strict-irr` kept as an alias). At `confirm_study_config` close the manifest gains `study.strict_gates: [<gate_id>, ...]` (default `[]`), recorded alongside `config_provenance` — the strictness regime is part of the study's citable methodology. `cmd_close` evaluates applicable gates: failure emits a structured `gate_warning` audit event (`close_id`, `gate_id`, details) and aborts only when the gate is strict (manifest or CLI `--strict-<gate_id>` override). `cmd_verify` sweeps all `gate_warning` events.

**Input resolution verb.** `mpi_step.py inputs --scope <scope> --stage <stage>` resolves the per-scope upstream artifact list (path + SHA) from manifest `output_path`/`artifact_shas` records; resolution rules live in code adjacent to `PREREQ_SCOPE_TRANSFORMS`. Orchestrator passes the verb's output verbatim into analyst prompts; analysts echo `inputs_consumed` in artifacts; `cmd_close` checks `inputs_consumed ⊆ resolved` (gate: `undeclared_input`). SKILL.md files reference the verb instead of naming literal artifact paths.

**Enforcement fixes.** `criteria_revision` closes with `decision == "more_revision_needed"` auto-downgrade to `flagged` (close succeeds, audit chain intact; downstream blocked while flagged; 5-pass cap stays SKILL convention). `cmd_close` reads `temporal_order_within_idu` from `theme_grouping_within_idu` artifacts → `flagged`. Schema co-presence rule (hard): `temporal_order_within_idu: true` requires ≥1 ISU with `flag_for_review: true`. `idu_split_after_synchronic` audit event emitted when a diachronic re-close follows a synchronic temporal-order flag, linking both close_ids/span_ids.

## Existing Patterns

- `COMPLETENESS_GATES` + `_check_completeness_gate` (`_mpi_schemas.py` ~735, `mpi_step.py` ~1229) established the close-time gate pattern; the `GATES` registry generalizes it with warn/strict posture.
- `study.*` manifest fields written at `confirm_study_config` (event_groups, dv_focuses, config_provenance) — `strict_gates` follows identically.
- Audit events keyed by `close_id` in `audit.jsonl` — `gate_warning` and `idu_split_after_synchronic` follow the existing event shape.
- `--strict-irr` flag semantics (warn-by-default, opt-in block) — generalized, alias preserved.
- Flagged-status machinery (`status: flagged` blocks `status != done` checks) — reused for convergence and temporal-order downgrades; no new status values.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Gate registry + manifest strictness
**Goal:** Declarative gate registry with manifest-declared, CLI-overridable strictness.

**Components:**
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — `GATES` registry; `study.strict_gates` schema in confirm_study_config validation
- `microphenomenograph/1.0.0/scripts/mpi_step.py` — gate evaluation in `cmd_close` (warn → `gate_warning` audit event; strict → abort); `--strict-<gate_id>` CLI flags; `--strict-irr` alias; `cmd_verify` gate-warning sweep
- `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md` — `strict_gates` declaration at study-config confirmation
- Tests: warn path emits event + close succeeds; strict path aborts; CLI override beats manifest; verify sweep reports warnings

**Dependencies:** None.

**Done when:** Registry-driven gates evaluate at close with correct posture; tests pass. Covers close-enforcement-2.AC1.*.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: `inputs` verb + consumed-input verification
**Goal:** Cross-stage input wiring is helper-resolved, machine-checkable data.

**Components:**
- `microphenomenograph/1.0.0/scripts/mpi_step.py` — `cmd_inputs` (`inputs --scope --stage`), resolution rules beside `PREREQ_SCOPE_TRANSFORMS`; `undeclared_input` gate check in `cmd_close`
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — `inputs_consumed` optional field accepted on cross-participant artifact payloads
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — echo-`inputs_consumed` rule
- Tests: resolution correctness per stage (generic_diachronic → per-transcript artifacts; global_synchronic → per-scope generic-synchronic artifacts; hypothesis → all three), subset check warn/strict behaviour

**Dependencies:** Phase 1 (gate registry).

**Done when:** `inputs` resolves correct per-scope artifact sets for every cross-participant stage; close verifies consumption; tests pass. Covers close-enforcement-2.AC2.*.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Global-synchronic wiring + gates
**Goal:** The stage runs on real inputs and warns on single-event scopes.

**Components:**
- `microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md` — input layer cites the `inputs` verb (kills dead `analyses/generic-synchronic.md` reference); output path per-scope form matching closure table
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — global-synchronic input instructions updated to match
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — required `source_event` on each global-synchronic ISU (hard shape); `single_event_global_synchronic` gate check (count distinct events with done generic_synchronic for the scoped gidu; warn if < 2)
- Tests: schema rejects ISUs without `source_event`; single-event scope warns / strict-blocks; multi-event closes clean

**Dependencies:** Phases 1–2.

**Done when:** No prose references to non-existent artifacts remain (grep-verified); gates behave; tests pass. Covers close-enforcement-2.AC3.*.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Diachronic/synchronic enforcement
**Goal:** The manual's feedback loop and convergence semantics are mechanically enforced.

**Components:**
- `microphenomenograph/1.0.0/scripts/mpi_step.py` — auto-downgrade to `flagged` on `more_revision_needed` close (`convergence_pending` gate); read `temporal_order_within_idu` at `theme_grouping_within_idu` close → `flagged` (`temporal_order_pending` gate); emit `idu_split_after_synchronic` audit event on diachronic re-close after a synchronic temporal-order flag
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — co-presence rule: `temporal_order_within_idu: true` ⇒ ≥1 ISU `flag_for_review: true` (hard)
- `microphenomenograph/1.0.0/agents/mpi-analyst.md` — synchronic rule 4 sets both flags
- `microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md`, `skills/mpi-synchronic/SKILL.md` — prose updated to describe actual (now-true) enforcement
- Tests: non-converged close → flagged + downstream blocked; temporal-order close → flagged + isu_naming blocked; re-close emits audit event linking span_ids; co-presence schema rejection

**Dependencies:** Phase 1.

**Done when:** Every enforcement claim in the two SKILL.md files has a corresponding code path and test; tests pass. Covers close-enforcement-2.AC4.*.
<!-- END_PHASE_4 -->

## Additional Considerations

**Doc-as-done audit chain:** all new aborts happen before `manifest_replaced`; `gate_warning` events carry the in-flight `close_id` so post-hoc audit can reconstruct every soft failure. No change to the phased close event sequence.

**SKILL-claims-code-parity:** this plan exists because SKILL.md promised enforcement the helper never implemented. Phase 4's done-when includes a sweep assertion (grep enforcement claims → code path + test) to prevent recurrence of that class.

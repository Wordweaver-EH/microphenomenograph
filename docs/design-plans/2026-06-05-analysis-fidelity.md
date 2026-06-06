# Analysis Fidelity (prompt-rule + schema fidelity fixes, no control-flow changes) Design

## Summary

This design addresses a set of correctness gaps found during review of the existing prompt rules and schema validators — cases where the agent instructions and field constraints diverged from the methodology described in the MPI manual. The fixes are confined to three actor files (`mpi-cross-analyst.md`, `mpi-analyst.md`, and the init/prep skills) and their corresponding schema validators; no control-flow logic in `cmd_close` or the gate registry is touched.

The approach works in three parallel-safe groups. First, the generic-synchronic grouping rule in `mpi-cross-analyst.md` is corrected: ISUs must be grouped within the target generic IDU rather than flattened across all IDU groups (cross-IDU synthesis belongs to global synchronic, not here). A required `source_generic_idu` field on each ISU makes cross-IDU contamination a machine-detectable schema failure rather than a silent analytic error. Alongside this, the `pattern_identification` schema is tightened to distinguish common IDUs (required, non-empty) from optional IDUs (may be empty), matching the manual's invariant-vs-optional pattern semantics. Second, `mpi-analyst.md` gains an explicit temporal linkage-phrase rule for diachronic analysis — phrases like "and then" or "after that" are boundary signals that outrank the prefer-fewer-IDUs heuristic — and the IDU naming timing is corrected so that `idu_name`/`moment` are optional at `criteria_grouping` (where convergence is still in progress) but required at `idu_naming_ordering`. Third, the init and transcript-prep skills gain two entry-point validations: header scores outside 0–5 are rejected with a named error, and a non-blocking advisory fires when participant count falls outside the manual's recommended 6–12 range.

## Definition of Done

- **Within-IDU grouping rewrite (C6)**: `mpi-cross-analyst.md` generic-synchronic rules direct ISU 2nd-level grouping strictly *within* the target generic IDU (cross-IDU synthesis belongs to global synchronic); a required `source_generic_idu` field on each ISU must match `payload.generic_idu` (machine-detectable contamination).
- **Common/optional pattern distinction (C5)**: `pattern_identification` schema requires `common_idus` (non-empty) and `optional_idus` (may be empty); agent instructions enumerate both per pattern and add the manual's optimum-small-set constraint (merge evaluation; justification when pattern count is high). `covered_participant_keys` is a non-empty string list (roster cross-referencing deferred to `verify`).
- **Score-range validation (C8)**: header parsing rejects scores outside 0–5 with a named error consistent with the existing invalid-header pattern.
- **Temporal-linkage-phrase rule (C8)**: `mpi-analyst.md` diachronic rules instruct scanning for linkage phrases ("and then", "after that", …) as moment-boundary signals, assigning different criteria before vs after each phrase; the prefer-fewer-IDUs heuristic is qualified so it cannot override a linkage-phrase boundary.
- **IDU naming timing (C8)**: `idu_name`/`moment` optional at `criteria_grouping`, required at `idu_naming_ordering`; `mpi-analyst.md` rules state naming is deferred until convergence; the two validators are no longer byte-identical.
- **Question-removal posture (C8)**: documented as researcher pre-step; `normalize` flags interviewer-turn lines that look like removable questions (validate-only, no content rewriting).
- **Participant-count note (C8)**: init emits an advisory when participant count falls outside the manual's 6–12 guidance (note-level, never blocks).
- Regression tests for each schema change and prompt-rule change pass; existing tests pass.

Out of scope: any `cmd_close`/gate logic (plan 2); hypothesis stage (plans 4–5).

This plan is **third in sequence** (plan 3 of 5); may be implemented in parallel with plan 2 (soft prompt-file conflicts only — different sections of `mpi-analyst.md` / `mpi-cross-analyst.md`).

## Acceptance Criteria

### analysis-fidelity.AC1: Within-IDU grouping is enforced
- **analysis-fidelity.AC1.1 Failure:** A generic-synchronic ISU whose `source_generic_idu` is missing or differs from `payload.generic_idu` is rejected at close
- **analysis-fidelity.AC1.2 Success:** `mpi-cross-analyst.md` contains the within-target-gidu grouping rule and no longer instructs flattening across IDU groups (grep)

### analysis-fidelity.AC2: Pattern common/optional semantics
- **analysis-fidelity.AC2.1 Failure:** A pattern without non-empty `common_idus` is rejected
- **analysis-fidelity.AC2.2 Success:** A pattern with empty `optional_idus` is accepted (invariant patterns representable)
- **analysis-fidelity.AC2.3 Success:** Agent instructions include the optimum-small-set/merge-evaluation criterion

### analysis-fidelity.AC3: Linkage-phrase boundary rule
- **analysis-fidelity.AC3.1 Success:** `mpi-analyst.md` diachronic rules include the temporal-linkage-phrase boundary rule, stated to outrank the prefer-fewer-IDUs heuristic

### analysis-fidelity.AC4: Naming deferred to convergence
- **analysis-fidelity.AC4.1 Success:** A `criteria_grouping` close without `idu_name`/`moment` is accepted
- **analysis-fidelity.AC4.2 Failure:** An `idu_naming_ordering` close without `idu_name`/`moment` on every IDU is rejected

### analysis-fidelity.AC5: Init data-contract validation
- **analysis-fidelity.AC5.1 Failure:** A header scoring outside 0–5 (e.g. `Scored 7/5`) is rejected with a named error and the file skipped
- **analysis-fidelity.AC5.2 Success:** Participant counts of 5 or 13 produce the 6–12 adequacy advisory (never blocking); counts 6–12 are silent

### analysis-fidelity.AC6: Question-flagging is validate-only
- **analysis-fidelity.AC6.1 Success:** Normalize flags interviewer-question lines without modifying any content (raw remains byte-identical; normalized differs only by existing structural rules)

## Glossary

- **IDU (Incipient Diachronic Unit)**: A discrete, temporally-ordered segment of a participant's reported experience, identified during diachronic analysis — one "moment" of experience in experienced order.
- **ISU (Incipient Synchronic Unit)**: A thematic structure within one IDU, identified during synchronic analysis.
- **Generic IDU**: A cross-participant IDU pattern identified by `mpi-cross-analyst` during generic diachronic analysis — an IDU abstraction recurring across participants in the same score category.
- **Diachronic analysis**: The first analytic stage, segmenting a transcript into temporally-ordered IDUs ("diachronic" = across time).
- **Synchronic analysis**: The second analytic stage, identifying thematic ISUs within each IDU ("synchronic" = at a single moment).
- **Generic synchronic**: The cross-participant counterpart for a specific generic IDU: ISUs from all participants grouped within that IDU.
- **Global synchronic**: A further abstraction over generic-synchronic outputs, synthesising themes across events.
- **`criteria_grouping`**: First diachronic substep — utterances clustered into candidate IDU groups with criteria sentences. IDU names are intentionally deferred here.
- **`criteria_revision`**: Second diachronic substep — groupings reviewed and refined before naming.
- **`idu_naming_ordering`**: Final diachronic substep — IDU names and moment numbers assigned and locked; `idu_name`/`moment` required here.
- **`pattern_identification`**: Generic-diachronic substep where cross-participant IDU patterns are recorded; this design adds the common-vs-optional element distinction.
- **`source_generic_idu`**: New field on each generic-synchronic ISU recording which generic IDU it derives from — a machine-checkable guard against cross-IDU contamination.
- **`normalize`**: The transcript-prep substep producing a structurally aligned derivative of the raw transcript. It never rewrites content; under this design it may flag (not remove) interviewer-question lines.
- **`close` / `verify`**: Pipeline verbs via `mpi_step.py`: atomic artifact validation + audit + manifest + commit; and the post-hoc sweep of closed substeps.
- **Zero-shot convention**: No worked examples from OSF analyses are injected into prompts. Examples from the manual itself (such as linkage phrases) are permitted.
- **Schema validator (`_validate_*`)**: Per-substep functions in `_mpi_schemas.py` using `_require_keys`/`SchemaError` to enforce payload shape at close time.
- **`_IDU_REQUIRED`**: Constant holding the required IDU fields, previously shared by all diachronic substeps; this design splits it into per-substep variants.
- **OSF (Open Science Framework)**: Source of the archived reference transcripts and inter-rater data; OSF analyses are acceptance-test fixtures only.
- **IV / DV**: The independent variable is the participant's subjective score (0–5, grouped low/moderate/high); the dependent variable is generated from the participant's experience descriptions.

## Architecture

Prompt-rule and schema-validator fidelity fixes with **no control-flow changes** — every change is either an agent-instruction edit, a schema field change, or an init/prep validation. Three groups by actor file:

**Cross-analyst (C5+C6).** `mpi-cross-analyst.md` generic-synchronic rules are rewritten to group ISUs strictly *within* the target generic IDU (the current "flatten all ISUs from all IDU groups" instruction is the defect; cross-IDU synthesis belongs to global synchronic). Schema: each generic-synchronic ISU carries required `source_generic_idu`, validated equal to `payload.generic_idu` — cross-IDU contamination becomes machine-detectable shape failure. `pattern_identification` schema requires `common_idus` (non-empty) and `optional_idus` (may be empty — invariant patterns are representable); agent instructions enumerate both per pattern and add the manual's optimisation criterion (merge evaluation; justification when pattern count is high). `covered_participant_keys` stays a non-empty string list (roster cross-referencing deferred to `verify`).

**Analyst (C8 diachronic).** `mpi-analyst.md` gains the temporal-linkage-phrase rule: scan for "and then" / "after that" / "at the beginning" / "right at the end" etc. as moment-boundary signals; utterances before vs after a linkage phrase get different criteria; the rule explicitly outranks the prefer-fewer-IDUs heuristic. Naming timing: `idu_name`/`moment` become optional at `criteria_grouping` and required at `idu_naming_ordering` (`_IDU_REQUIRED` splits into per-substep variants — the two validators stop being byte-identical); prompt rules state naming is deferred until convergence.

**Init/prep (C8).** `mpi-init/SKILL.md` header parsing rejects scores outside 0–5 (named error, consistent with the existing invalid-header pattern) and emits an advisory (never blocks) when participant count falls outside 6–12. `mpi-transcript-prep/SKILL.md` normalize flags interviewer-turn lines that look like removable questions (validate-only; content editing remains a documented researcher pre-step).

## Existing Patterns

- Schema validators: per-substep `_validate_*` functions in `_mpi_schemas.py` using `_require_keys`/`SchemaError` — all field changes follow this.
- Agent rule style: numbered rules with bold leads in `mpi-analyst.md`/`mpi-cross-analyst.md` — new rules match.
- Init error style: `ERROR: <filename>: <reason>` + skip-file (mpi-init SKILL.md ~97–99) — score-range error matches.
- Divergence note: splitting `_IDU_REQUIRED` into per-substep required-field sets diverges from the current single-constant pattern, justified because the byte-identical validators are themselves a confirmed review finding.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Cross-analyst grouping + pattern fidelity
**Goal:** Within-IDU grouping enforced; common/optional pattern semantics restored.

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — generic-synchronic within-IDU grouping rewrite (~lines 93–100); generic-diachronic pattern instructions (common + optional elements, optimum-small-set, merge evaluation) (~lines 62–66)
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — `source_generic_idu` required + equality check on generic-synchronic ISUs; `common_idus`/`optional_idus` in `_validate_generic_diachronic_pattern_identification` (~lines 221–230)
- Tests: schema rejects missing/mismatched `source_generic_idu`; rejects patterns without `common_idus`; accepts empty `optional_idus`

**Dependencies:** None.

**Done when:** Tests pass; existing cross-participant tests pass. Covers analysis-fidelity.AC1.*, AC2.*.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Diachronic analyst-rule fidelity
**Goal:** Linkage-phrase boundary detection; naming deferred to convergence.

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-analyst.md` — linkage-phrase rule (outranks prefer-fewer-IDUs); naming-deferred wording in diachronic rules
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — per-substep IDU required-field variants: `idu_name`/`moment` optional at `criteria_grouping`/`criteria_revision`, required at `idu_naming_ordering` (~lines 86–87, 136–168)
- Tests: criteria_grouping close accepted without `idu_name`/`moment`; idu_naming_ordering close rejected without them

**Dependencies:** None (parallel-safe with Phase 1; different file regions).

**Done when:** Tests pass; existing diachronic tests pass. Covers analysis-fidelity.AC3.*, AC4.*.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Init/prep validation fidelity
**Goal:** Data-contract violations surface at entry.

**Components:**
- `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md` — score 0–5 range validation (~line 89 regex + new check); 6–12 participant advisory
- `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md` — question-line flagging in normalize (validate-only)
- Tests: `Scored 7/5` rejected with named error; participant counts 5 and 13 produce advisory, 6–12 silent; question-flagging surfaces interviewer lines without modifying content

**Dependencies:** None.

**Done when:** Tests pass; `tests/test_verify_mpi_init.py` and `tests/test_transcript_prep.py` extended and passing. Covers analysis-fidelity.AC5.*, AC6.*.
<!-- END_PHASE_3 -->

## Additional Considerations

**Plan-2 overlap:** `mpi-analyst.md` is also edited by close-enforcement-2 Phase 4 (synchronic rule 4) — different rule sections; coordinate merge order but no design conflict. Schema edits here are disjoint from plan 2's gate registry.

**Zero-shot convention preserved:** linkage-phrase examples come from the manual itself, not from OSF analyses — no example injection.

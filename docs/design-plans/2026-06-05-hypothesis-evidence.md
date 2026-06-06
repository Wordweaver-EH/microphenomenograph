# Hypothesis Evidence (weak-evidence review substance + evidence inputs) Design

## Summary

This plan wires the hypothesis-generation stage to the full body of cross-participant evidence and gives its weak-evidence safeguard real analytical teeth. Today the `hypothesis.evidence_extraction` substep draws on only a single, wrongly-named analysis artifact; after this plan it will receive all three cross-participant outputs — generic-diachronic, generic-synchronic, and global-synchronic — resolved automatically through the `inputs` verb introduced in plan 2. Grounding the hypothesis analyst in the complete evidence base is a precondition for any trustworthy claim about what the data support.

The second and third pieces of the plan address a structural gap in the current weak-evidence review: the review array exists in the schema but is allowed to be empty, so the safeguard can be satisfied without any real checking. This plan closes that gap in two steps. First, every hypothesis claim is assigned a short deterministic `claim_id`, and the schema is changed so that a review item keyed to each `claim_id` is required — making an empty or partial review a hard schema violation rather than a silent omission. Second, the cross-analyst agent receives explicit instructions for what to check: whether a claim rests on fewer than three transcripts, covers only a single IV level, uses causal language ("causes", "leads to") for a finding that is only associational, or mismatches the rung of the causal ladder its framing implies. Flagged claims surface a `weak_evidence_unreviewed` warning at close by default; analysts can acknowledge them or, if the study's `strict_gates` setting is on, the close is blocked until each flagged item is resolved.

## Definition of Done

- **All-three-analyses evidence inputs**: `hypothesis.evidence_extraction` receives generic-diachronic, generic-synchronic, AND global-synchronic artifacts as context (per-scope paths resolved by the orchestrator, extending the path-resolution mechanism installed by plan 2); `mpi-hypothesis/SKILL.md` prerequisites and context-documents sections updated to match.
- **Weak-evidence review has substance**: `mpi-cross-analyst.md` gains a `### Weak evidence review` section instructing the LLM to flag claims with `n_transcripts < 3`, single-IV-level coverage, or causal verbs in `uncertainty_language`, and to verify rung-1 framing for observational findings.
- **Per-claim coverage is machine-checkable**: `candidate_drafting` claims carry a `claim_id`; `review_items` cross-reference claims by `claim_id`; the schema requires every claim to have a corresponding review item (shape validation — hard).
- **Review posture**: flag-only by default (review items noted, close succeeds) consistent with the warn-by-default convention; review items may carry `acknowledged_by`; a future strict flag can block on unresolved items.
- Regression tests pass; existing tests pass.

Out of scope: `replication_recommendation` / `testable_implications` (deferred to plan 5, which designs the field once); DAG/rung/confounder schema (plan 5).

This plan is **fourth in sequence** (plan 4 of 5); **hard-depends on plan 2** (close-enforcement-2) for the per-scope artifact path resolution.

## Acceptance Criteria

### hypothesis-evidence.AC1: Complete evidence inputs
- **hypothesis-evidence.AC1.1 Success:** `inputs --stage hypothesis` resolution returns all three cross-participant artifact sets (generic-diachronic, generic-synchronic, global-synchronic) for the scope
- **hypothesis-evidence.AC1.2 Success:** `mpi-hypothesis/SKILL.md` cites the `inputs` verb and contains no literal cross-stage artifact filename (grep)

### hypothesis-evidence.AC2: Claim traceability and review coverage
- **hypothesis-evidence.AC2.1 Failure:** A candidate_drafting claim without `claim_id` is rejected
- **hypothesis-evidence.AC2.2 Failure:** Duplicate `claim_id` values within one artifact are rejected
- **hypothesis-evidence.AC2.3 Failure:** A weak_evidence_review lacking a review item for any `claim_id` is rejected
- **hypothesis-evidence.AC2.4 Failure:** `review_items: []` with non-empty claims is rejected (the empty-shell defect is structurally impossible)

### hypothesis-evidence.AC3: Review substance and gate
- **hypothesis-evidence.AC3.1 Success:** A close with a `flagged` review item lacking `acknowledged_by` triggers `weak_evidence_unreviewed` (warn default)
- **hypothesis-evidence.AC3.2 Success:** All flagged items acknowledged → close clean, no warning
- **hypothesis-evidence.AC3.3 Success:** Gate in `study.strict_gates` → unacknowledged flagged item aborts close
- **hypothesis-evidence.AC3.4 Success:** `mpi-cross-analyst.md` review section instructs the thin-support (n_transcripts < 3), single-IV-level, and causal-language checks

## Glossary

- **candidate_drafting**: The hypothesis substep in which the cross-analyst drafts candidate hypothesis claims from the cross-participant analysis artifacts.
- **weak_evidence_review**: The hypothesis substep reviewing each drafted claim for evidentiary quality. Before this plan the review array could be empty; after this plan it must contain one item per `claim_id`.
- **claim_id**: A short, unique identifier (`c1`, `c2`, …) per claim within an artifact, used to cross-reference claims with review items — coverage becomes machine-checkable.
- **generic-diachronic / generic-synchronic / global-synchronic**: The three cross-participant analyses — temporal IDU patterns per (event × IV category), ISU regrouping per generic IDU, and aggregation of generic IDUs across events.
- **`inputs` verb**: `mpi_step.py inputs --scope … --stage …`, resolving which artifact files a stage receives as context. Introduced in plan 2; this plan is its first consumer requiring multi-stage fan-in.
- **Fan-in**: A single downstream step collecting outputs from multiple upstream stages — here, three analysis artifact sets feeding one hypothesis stage.
- **DV focus**: A dependent-variable focus label scoping hypothesis substeps (researcher-declared in `study.dv_focuses` or LLM-derived when null).
- **Rung / causal ladder**: Pearl's hierarchy: rung 1 association, rung 2 intervention, rung 3 counterfactual. Interview findings are observational (rung 1); the review checks that claim language does not imply a higher rung.
- **`n_transcripts`**: The count of transcripts supporting a claim; fewer than three flags thin support.
- **Single-IV-level coverage**: A claim whose evidence spans only one IV score category — a warning sign it may not contrast levels at all.
- **`uncertainty_language`**: The claim field carrying hedging/causal phrasing; checked for causal verbs ("causes", "leads to", "produces").
- **`acknowledged_by`**: Review-item field signalling a responsible analyst has seen and accepted a flagged finding; resolves the warning.
- **`weak_evidence_unreviewed` gate**: Gate (in plan 2's `GATES` registry) firing at close when a flagged review item lacks `acknowledged_by`. Warn-by-default; strict via `study.strict_gates`.
- **`study.strict_gates` / warn-by-default**: The manifest-declared strictness regime from plan 2: quality gates warn unless opted into blocking.
- **`rung_appropriateness`**: Review check recording whether a claim's rung framing matches its evidence. Stub in this plan; plan 5 makes it substantive.
- **`_mpi_schemas.py` / `mpi-cross-analyst.md` / `mpi-hypothesis/SKILL.md`**: The schema module, cross-participant agent prompt, and hypothesis skill file — the three files this plan changes.

## Architecture

Makes the hypothesis stage's evidence base complete and its weak-evidence safeguard real. Three pieces:

**Evidence inputs.** `hypothesis.evidence_extraction` consumes generic-diachronic, generic-synchronic, AND global-synchronic artifacts, resolved via plan 2's `inputs` verb (`mpi_step.py inputs --scope <dv-focus-scope> --stage hypothesis`) — this stage is the verb's first consumer needing multi-stage fan-in. `mpi-hypothesis/SKILL.md` prerequisites and context-documents sections cite the verb, replacing the current single (and wrongly named) `analyses/global-synchronic.md` reference.

**Claim traceability.** `candidate_drafting` claims gain required `claim_id` (short deterministic strings `c1`, `c2`, … unique within the artifact). `weak_evidence_review`'s schema changes from "a `review_items` array exists" (empty passes today) to: one review item per `claim_id`, full coverage validated at close (hard shape — coverage is structural, not judgment). Review item contract:

```
{ claim_id, checks: { thin_support, single_iv_level, causal_language, rung_appropriateness },
  outcome: "pass" | "flagged", notes }
```

(`rung_appropriateness` lands as a stub check here; plan 5 gives it teeth.)

**Review substance.** `mpi-cross-analyst.md` gains a `### Weak evidence review` section: flag claims with `n_transcripts < 3`; flag single-IV-level coverage; flag causal verbs ("causes", "leads to", "produces") in claims framed as rung-1 association. Outcome feeds the `weak_evidence_unreviewed` gate (registered in plan 2's `GATES`): any `flagged` item without `acknowledged_by` → warn-by-default at close, strict via `study.strict_gates`.

## Existing Patterns

- Hypothesis claim contract (`{supports, contradicts, ambiguous, n_transcripts, n_iv_levels_covered, uncertainty_language, negative_cases}` with `raw_span_refs`) — untouched; `claim_id` is additive.
- Plan 2's `inputs` verb + `GATES` registry — this plan consumes both rather than inventing parallel mechanisms (hard dependency).
- Per-substep validators in `_mpi_schemas.py` — coverage check extends `_validate_hypothesis_weak_evidence_review` (~lines 377–378).
- Warn-by-default + `acknowledged_by` resolution pathway mirrors the review-queue convention used for flagged analytic units.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Evidence inputs via `inputs` verb
**Goal:** Hypothesis drafting sees all three cross-participant analyses.

**Components:**
- `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md` — prerequisites + context documents cite `inputs` verb output (three artifact sets)
- `microphenomenograph/1.0.0/scripts/mpi_step.py` — `inputs` resolution rule for `hypothesis.*` scopes (fan-in: all generic_diachronic, generic_synchronic, global_synchronic artifacts for the study)
- Tests: resolution returns all three artifact sets; `undeclared_input` gate passes when analyst echoes them

**Dependencies:** close-enforcement-2 Phases 1–2 (gate registry, `inputs` verb).

**Done when:** Resolution tests pass; SKILL.md contains no literal cross-stage artifact paths. Covers hypothesis-evidence.AC1.*.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: claim_id + review coverage schema
**Goal:** Every claim is reviewable by id; empty reviews are structurally impossible.

**Components:**
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — `claim_id` required on candidate_drafting claims (unique within artifact); `_validate_hypothesis_weak_evidence_review` requires per-`claim_id` coverage with the review-item contract
- Tests: missing `claim_id` rejected; duplicate `claim_id` rejected; review missing any claim's item rejected; empty `review_items` with non-empty claims rejected

**Dependencies:** None (schema-only; parallel-safe with Phase 1).

**Done when:** Schema tests pass. Covers hypothesis-evidence.AC2.*.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Review instructions + gate
**Goal:** The safeguard has substance and a close-time consequence.

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — `### Weak evidence review` section (thin-support, single-IV-level, causal-language checks; rung_appropriateness stub)
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — `weak_evidence_unreviewed` gate check (flagged items lacking `acknowledged_by`)
- Tests: flagged-unacknowledged close warns; acknowledged closes clean; strict blocks

**Dependencies:** Phases 1–2; close-enforcement-2 Phase 1.

**Done when:** Gate behaves in both postures; tests pass; existing `tests/test_hypothesis_generation.py` extended and passing. Covers hypothesis-evidence.AC3.*.
<!-- END_PHASE_3 -->

## Additional Considerations

**Deferred to plan 5 (by design, to avoid double schema churn on `candidate_drafting`):** `replication_recommendation`, `rung`/`assumptions`/`confounders`/`testable_implications`, and the substantive `rung_appropriateness` check. The `claim_id` and review-item contract here are designed to accept those additions without reshaping.

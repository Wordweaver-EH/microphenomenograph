# Causal Extension (full-structural DAG/rung/confounder contract for hypothesis claims) Design

## Summary

This design adds a full-structural causal contract to the hypothesis generation stage of the MPI analysis pipeline. Currently, the `candidate_drafting` step produces candidate mechanism hypotheses but carries no formal machinery for distinguishing observational associations from claims about intervention or counterfactual effects, for naming confounding variables, or for encoding the causal graph implied by each hypothesis. The extension makes those elements required and schema-enforced: every claim must declare a Pearl "rung" (1 = association, 2 = intervention, 3 = counterfactual), must enumerate confounders as typed `{variable, mechanism}` objects (always including the common-method-variance latent factor specific to self-report study designs), and must state testable implications in DAGitty conditional-independence notation. Each hypothesis in the markdown artifact must include a mermaid DAG whose presence is validated at close time.

The approach is graded against Book of Why discipline rather than the existing MPI manual, which has no causal layer — this is a deliberate extension. Causal *estimation* remains explicitly out of scope: the pipeline produces candidate mechanisms only, and the existing verbatim disclaimer is unchanged. The DAGs are communication artifacts designed to make causal assumptions explicit and attackable; they are not computational objects and their syntax is not machine-validated. A `replication_recommendation` field at the artifact level discharges the manual's replication requirement by framing findings in terms of what a second participant set would corroborate. The work is implemented across three phases: schema additions, agent instruction updates, and close-time presence validation plus contract documentation.

## Definition of Done

Full-structural posture confirmed by user ("we will be better on that front"): causal fields are required schema (shape validation — hard), graded against Book of Why discipline rather than Kev's manual (which has no causal layer).

- **Rung guard**: every `candidate_drafting` claim carries a required `rung` field (1 | 2 | 3); any claim with `rung >= 2` requires a non-empty `assumptions` list (the causal assumptions licensing the higher-rung framing) — schema-enforced.
- **Confounder enumeration**: every claim carries a required non-empty `confounders` list of `{variable, mechanism}` objects; `mpi-cross-analyst.md` instructs always including the shared-method common cause (IV score and DV experience description are both self-reports from the same participant in the same session) with participant-specific mechanism wording.
- **Per-hypothesis DAG**: the markdown artifact includes a mermaid DAG per hypothesis (IV → mechanism components → DV focus, plus confounder nodes with arrows into both); presence validated at close (a `dag_present` boolean or section check), syntax not validated.
- **Testable implications as the replication hand-off**: every claim carries required `testable_implications` (what a second participant set would show if the mechanism is real); a top-level `replication_recommendation` field in `candidate_drafting` discharges the manual's replicate-with-second-set requirement (review finding §1.5).
- **Plan-4 weak-evidence integration**: the weak-evidence review checks rung/assumptions consistency (a rung-2 claim with empty assumptions is structurally impossible; the review flags rung-appropriateness of language).
- `mpi-hypothesis/SKILL.md`, `mpi-cross-analyst.md`, `_mpi_schemas.py`, and plugin `CLAUDE.md` (hypothesis contract section) updated coherently; no plugin version bump (nothing released; rationale documented in CLAUDE.md).
- Regression tests pass; existing tests pass.

Out of scope: causal *estimation* of any kind (the pipeline produces candidate mechanisms, never causal estimates — the existing verbatim disclaimer stands); do-calculus tooling; DAG syntax validation.

This plan is **fifth in sequence** (plan 5 of 5) and deferrable; soft dependencies on plans 3 and 4 (shared `candidate_drafting` schema churn — coordinate field additions once).

## Acceptance Criteria

### causal-extension.AC1: Causal claim schema
- **causal-extension.AC1.1 Failure:** A claim with `rung >= 2` and empty `assumptions` is rejected
- **causal-extension.AC1.2 Success:** A claim with `rung == 1` and empty `assumptions` is accepted
- **causal-extension.AC1.3 Failure:** A claim with empty `confounders` is rejected
- **causal-extension.AC1.4 Failure:** A confounder entry missing `variable` or `mechanism` is rejected

### causal-extension.AC2: Agent causal content
- **causal-extension.AC2.1 Success:** `mpi-cross-analyst.md` instructs always including the common-method-variance latent confounder (common cause of IV and DV) with participant-specific mechanism wording
- **causal-extension.AC2.2 Success:** `testable_implications` instructed in DAGitty conditional-independence notation (`X _||_ Y | Z`)
- **causal-extension.AC2.3 Success:** DAG conventions instructed: confounders as explicit latent nodes with two directed arrows, latent class marking (no faked bidirected edges)

### causal-extension.AC3: DAG presence and rung review
- **causal-extension.AC3.1 Posture:** A candidate_drafting markdown artifact missing the per-hypothesis DAG section triggers the gate (warn default, abort strict)
- **causal-extension.AC3.2 Success:** A fixture claim using rung-2 language over rung-1 evidence is flagged by the `rung_appropriateness` review check

### causal-extension.AC4: Replication hand-off
- **causal-extension.AC4.1 Failure:** A candidate_drafting artifact missing top-level `replication_recommendation` is rejected
- **causal-extension.AC4.2 Success:** The markdown template includes the replication recommendation framed as what a second participant set would show

### causal-extension.AC5: Contract documentation
- **causal-extension.AC5.1 Success:** Plugin `CLAUDE.md` hypothesis contract section describes the shipped fields, DAG convention, and no-version-bump rationale (reconciliation test)

## Glossary

- **Rung (ladder of causation)**: A level of causal reasoning from Pearl's *The Book of Why*. Rung 1 = association (correlation, no causal claim); rung 2 = intervention (what happens if I act?); rung 3 = counterfactual (what would have happened otherwise?). Every hypothesis claim must declare its rung.
- **DAG (Directed Acyclic Graph)**: A graph of nodes and one-way arrows with no cycles representing causal structure. Here each DAG connects IV → mechanism components → DV focus, plus confounder nodes.
- **Confounder**: A common cause of both IV and DV creating spurious association. Unrepresented confounders risk misattributing correlation as mechanism.
- **Common-method variance (CMV)**: Systematic bias when predictor and outcome are measured by the same method in the same session (here: self-report by the same participant). Acts as a latent common cause of the IV score and the DV experience description; required in every hypothesis DAG.
- **Latent node**: An unobserved variable in a causal graph. In mermaid DAGs, latent nodes get a distinct class and two directed arrows stand in for the bidirected edge DAGitty would use (mermaid has no bidirected syntax).
- **DAGitty**: Browser/R tool for drawing and analysing causal DAGs. The pipeline uses its conditional-independence notation (`X _||_ Y | Z`, "X independent of Y given Z") for `testable_implications`, keeping the field machine-parseable by `impliedConditionalIndependencies()`.
- **DoWhy identify-discipline**: The principle (from the DoWhy library's model→identify→estimate→refute workflow) that higher-rung claims require explicit identification assumptions. The `rung ≥ 2 → non-empty assumptions` rule is its qualitative analogue.
- **`candidate_drafting`**: The hypothesis substep in which `mpi-cross-analyst` drafts structured claims grounded in cross-participant pattern evidence; receives the new causal fields.
- **`weak_evidence_review`**: The hypothesis review substep; this design makes its `rung_appropriateness` check substantive (rung-2/3 language over rung-1 evidence gets flagged).
- **`mpi-cross-analyst`**: The cross-participant subagent running generic diachronic, generic synchronic, global synchronic, and hypothesis stages.
- **`_mpi_schemas.py`**: The schema registry defining per-substep validation; close-time rejection is enforced here.
- **IDU (Incipient Diachronic Unit)**: A named temporal segment of a participant's experience from diachronic analysis; generic diachronic groups them across participants.
- **ISU (Incipient Synchronic Unit)**: A named theme within an IDU from synchronic analysis; generic/global synchronic group them across participants.
- **IV / DV**: The IV is the participant's subjective score (0–5); the DV derives from the experience descriptions. `dv_focuses` label the specific DV aspect a hypothesis addresses.
- **Mermaid**: Markdown-embeddable diagram syntax; used for the per-hypothesis DAGs in the artifact markdown.
- **`replication_recommendation`**: Top-level artifact field stating what a second independent participant set would need to show — discharging the manual's replication recommendation.
- **Close-time validation**: The moment `mpi_step.py close` validates an artifact's schema before committing; rejection prevents `done` status and the commit.
- **Book of Why discipline**: The causal framework of Pearl & Mackenzie (2018), used as the grading standard for this extension in preference to the MPI manual, which has no causal layer.

## Architecture

Adds a full-structural causal contract to `candidate_drafting`, graded against Book of Why discipline (the manual has no causal layer — this is extension, not fidelity). Research-grounded conventions: DAGitty for notation, DoWhy's identify-assumptions discipline for the rung guard, common-method-variance literature for the default confounder.

**Claim contract additions (all required, hard shape):**

```
rung: 1 | 2 | 3
assumptions: [string, ...]        # non-empty REQUIRED when rung >= 2; may be empty at rung 1
confounders: [{variable, mechanism}, ...]   # non-empty always
testable_implications: [string, ...]        # DAGitty conditional-independence notation: "X _||_ Y | Z"
```

Plus top-level on the artifact: `replication_recommendation` (string; framed as what a second participant set would show — discharges the manual's §1.5 requirement once, here, not in plan 4).

**Agent instructions** (`mpi-cross-analyst.md` hypothesis section): always include the **common-rater/common-method-variance** confounder — IV score and DV experience description are self-reports from the same participant in the same session; represent it as a latent method factor that is a common cause of both, with participant-specific mechanism wording. Rung guidance follows the ladder monotonically: rung 1 needs no assumptions; rung ≥ 2 claims must state the causal assumptions licensing them (DoWhy identify-discipline analogue).

**DAG artifact.** One mermaid DAG per hypothesis in the markdown artifact: IV → mechanism components (from generic-IDU/ISU structure) → DV focus; confounders as **explicit latent nodes with two directed arrows** (`M --> IV`, `M --> DV`; mermaid has no bidirected edge — this keeps consistency with DAGitty's role conventions rather than faking `<->`); latent nodes marked with a distinct mermaid class. Presence validated at close (section/marker check); syntax not validated.

**Review teeth.** Plan 4's `rung_appropriateness` check becomes substantive: rung-2/3 language over rung-1 evidence → flagged; empty-assumptions-at-rung-≥2 is already structurally impossible (schema), so the review covers the semantic gap the schema can't.

## Existing Patterns

- `candidate_drafting` claim contract + `claim_id` + review-item contract from plan 4 — all additions slot into those shapes (hard dependency on plan 4's Phase 2).
- Verbatim not-causal-estimates disclaimer — unchanged, still schema-validated on every artifact.
- Conditional schema requirements (field X required when field Y has value Z) — precedent: `hinge_to_next` null-only-on-last-IDU (`_mpi_schemas.py` ~102–104); the rung/assumptions rule follows it.
- Markdown artifact section conventions from existing closure tables — the DAG section + presence check follow the same pattern as existing required sections.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Causal schema fields
**Goal:** The claim contract carries the full causal structure.

**Components:**
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — `rung`, `assumptions` (conditional non-empty at rung ≥ 2), `confounders` ({variable, mechanism} objects, non-empty), `testable_implications` on claims; top-level `replication_recommendation` in `_validate_hypothesis_candidate_drafting`
- Tests: rung-2 claim with empty assumptions rejected; rung-1 with empty assumptions accepted; empty confounders rejected; malformed confounder objects rejected; missing replication_recommendation rejected

**Dependencies:** hypothesis-evidence Phase 2 (claim_id contract).

**Done when:** Schema tests pass. Covers causal-extension.AC1.*, AC4.1.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Agent causal instructions + DAG conventions
**Goal:** The analyst produces well-formed causal content.

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — rung-ladder guidance; always-include CMV latent confounder rule with mechanism-wording guidance; `testable_implications` in `X _||_ Y | Z` notation; mermaid DAG conventions (latent nodes + two directed arrows, latent class marking)
- `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md` — output format gains the per-hypothesis DAG section; replication_recommendation in the markdown template
- Tests: prompt-artifact structure tests (instructions present); fixture-based output-shape validation

**Dependencies:** Phase 1.

**Done when:** Instruction and template tests pass. Covers causal-extension.AC2.*, AC4.2.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: DAG presence validation + substantive rung review + contract docs
**Goal:** Close-time checks and documentation match the new contract.

**Components:**
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — DAG-section presence check on the candidate_drafting markdown artifact (marker check, not syntax); substantive `rung_appropriateness` criteria in the weak-evidence review item contract
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — weak-evidence review section: rung-language-vs-evidence check
- `microphenomenograph/1.0.0/CLAUDE.md` (plugin) — hypothesis contract section updated (new fields, DAG convention, no-version-bump rationale)
- Tests: missing DAG section warns/rejects per posture; rung-2-language-rung-1-evidence fixture gets flagged; CLAUDE.md reconciliation check

**Dependencies:** Phases 1–2; hypothesis-evidence Phase 3 (review machinery).

**Done when:** All tests pass; plugin CLAUDE.md accurately describes the shipped contract. Covers causal-extension.AC3.*, AC5.*.
<!-- END_PHASE_3 -->

## Additional Considerations

**Scope discipline:** no do-calculus, no identification tooling, no DAG syntax validation — the DAG is a communication artifact making assumptions attackable, not a computational object. If a future design wants machine-checked implications, the `X _||_ Y | Z` field format is already DAGitty-compatible (`impliedConditionalIndependencies()`/`localTests()`).

**LLM schema-failure risk:** full-structural required fields raise close-rejection rates if the analyst emits malformed causal content. Mitigation: the agent instructions include one neutral structural example of each field shape (shapes are not analysis content — zero-shot convention preserved); rejection messages name the offending field precisely.

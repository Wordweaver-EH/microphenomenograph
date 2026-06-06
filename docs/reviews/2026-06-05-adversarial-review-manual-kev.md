# Adversarial Review: Implementation vs. Sheldrake & Dienes MPI Manual

_Date: 2026-06-05. Method: 60-agent adversarial workflow (9 dimension finders → per-finding adversarial verifiers → completeness critic → gap follow-up round). Spec: `manual_kev.md`. References: `manual_2018.md` (background only), `bookowhy_rev.md` (causal extension). Orchestrator spot-checked the three highest-stakes code claims independently._

## How to read this

The project **deliberately adapts and extends** Kev's manual — divergence alone is not a defect. Every raw finding (46) was adversarially verified with four checks: verbatim manual citation, implementation citation (searching the whole plugin before accepting an "omission"), scope (analysis-only LLM pipeline; spreadsheet mechanics don't count, functional equivalents do), and **intentionality** (documented + defensible → not a defect; documented but unsound → still a defect).

Outcome: **22 confirmed deviations** (10 major, 11 minor, 1 note), **26 refuted** (16 as documented intentional adaptations, 5 misreadings, 3 invalid citations, 2 out of scope). Completeness critic found 2 coverage gaps; both checked clean.

Verdict classes used below:

- **Defect** — fidelity loss that hurts the science, or advertised behaviour that doesn't exist
- **Neutral adaptation** — documented, defensible divergence
- **Improvement** — divergence that is *more* scientifically rigorous than the manual

---

## 1. Defects — fix these

### 1.1 Broken code (highest priority)

**[MAJOR] IRR alignment map is inverted — reconciliation is a no-op** (`scripts/irr.py`)
Two sites: `compute_coincidence` builds `alignment_map[primary_cat] = alternate_cat` (line 222) but looks up `cat_b` — an **alternate** label — at line 244; `compute_irr` repeats the inversion (lines 705/709). Alternate labels are never keys in a primary-keyed dict, so the LLM-proposed alignment is silently discarded and α/κ/αU/ARI measure surface-string identity. Since two independent LLM raters will essentially always use different free-text labels, every real calibration run collapses toward chance agreement. **Spot-checked and confirmed by the orchestrator.**
*Fix:* swap key/value at both sites (`alignment_map[alternate] = primary`), and add a regression test where primary/alternate use disjoint label sets with a full alignment — expected α = 1.0.

**Note the silver lining:** this bug *under*-reports agreement (fails noisily) rather than inflating it — but with warn-by-default IRR, a permanently-failing metric trains users to ignore the warning, which is worse than no metric.

### 1.2 Advertised-but-unimplemented enforcement (docs promise, code doesn't deliver)

**[MAJOR] Iterate-until-convergence loop has no implementation** (`skills/mpi-diachronic/SKILL.md` line 130 vs `mpi_step.py`)
SKILL.md promises: orchestrator re-dispatches while `convergence.decision == "more_revision_needed"`, capped at 5 passes. `grep more_revision_needed mpi_step.py` → zero hits; the only code touching it is the schema validator, which **accepts** a non-converged close as valid and marks the substep `done`. The manual's core diachronic mechanic — "iterate until no further improvements can be made" — is recorded as intent but never enforced; `idu_naming_ordering` proceeds on a non-converged grouping. **Spot-checked.**
*Fix:* reject (or set `flagged`, not `done`) a `criteria_revision` close whose decision is `more_revision_needed`, unless a `--force-converge` style override is passed at the pass-5 cap.

**[MAJOR] `temporal_order_within_idu` flag does not block downstream substeps** (`mpi_step.py`)
The manual's *only* inter-stage feedback loop: temporal order inside an IDU → split it → return to diachronic. SKILL.md says the helper blocks on the flag; `grep temporal_order_within_idu mpi_step.py` → zero hits. **Spot-checked.** Enforcement is indirect only (status==done checks), so a flagged artifact closed as `done` sails through.
*Fix:* in `cmd_close`, read the `theme_grouping_within_idu` artifact; if `temporal_order_within_idu: true`, set substep status `flagged` (not `done`) and block `isu_naming` until a diachronic re-close resolves it.

**[MAJOR] Two flag mechanisms, no cross-reference — the split signal can be lost** (`agents/mpi-analyst.md` lines 68–70)
The agent is told to set `flag_for_review: true` on detecting temporal order; the orchestrator (per SKILL.md) acts on `temporal_order_within_idu: true`. An analyst following its instructions emits the wrong signal.
*Fix:* instruct the analyst to set **both** fields; better, make the schema validator reject `temporal_order_within_idu: true` absent `flag_for_review: true`.

**[MINOR] `idu_split_after_synchronic` audit event documented, never emitted** (`skills/mpi-synchronic/SKILL.md` line 91)
The return-edge audit trail exists only as prose. Given doc-as-done's audit-trail-is-the-contract philosophy, this is a contract violation in miniature.

**[MINOR] SKILL.md describes a no-pending-flags gate condition the completeness gate doesn't check** (`skills/mpi-generic-diachronic/SKILL.md` line 53)
Gate code checks `status != done` only; safe **iff** flagged closes get `flagged` status — which 1.2's second item shows is not enforced. Fixing that fixes this.

### 1.3 Methodological distortions (the LLM is instructed to do the wrong analysis)

**[MAJOR] Generic synchronic ISU grouping flattens across generic-IDU boundaries** (`agents/mpi-cross-analyst.md` lines 93–100)
Manual: group ISUs *within each generic IDU* — the IDU is the containing bucket. Agent prose: "flatten all ISUs from all IDU groups and group them by semantic similarity." Cross-IDU synthesis is global synchronic's job; doing it here contaminates the within-IDU structure and pre-empts the next stage.
*Fix:* rewrite the grouping rule to stay inside the target generic IDU.

**[MAJOR] Pattern rows lack the common/optional element distinction** (`_mpi_schemas.py` lines 221–230; `mpi-cross-analyst.md` lines 62–66)
The manual's pattern mechanism — common elements + optional elements so one pattern "describes well a set of participant rows" — is absent from both schema and agent instructions. Patterns degrade to flat IDU lists with no coverage semantics.
*Fix:* require `common_idus` + `optional_idus` in the `pattern_identification` schema; mirror in agent instructions.

**[MAJOR] Global synchronic's defining precondition (same generic IDU in ≥2 events) unenforced** (`_mpi_schemas.py` COMPLETENESS_GATES lines 735–743)
The stage exists to synthesize *across events*; it closes happily on a single-event generic IDU, producing analytically meaningless output.
*Fix:* at close, count distinct events with a done `generic_synchronic.isu_second_level_grouping` for the scoped gidu; block if < 2.

**[MAJOR] `weak_evidence_review` substep has no LLM instructions and accepts `review_items: []`** (`_mpi_schemas.py` lines 377–378)
The pipeline's anti-overclaiming safeguard is an empty shell: no definition of "thin support" or "unsupported causal language," and an empty review passes validation.
*Fix:* add a `### Weak evidence review` section to `mpi-cross-analyst.md` (flag claims with n_transcripts < 3 or single IV level; flag causal verbs; verify rung-1 framing) and require each hypothesis claim to have a corresponding review item.

### 1.4 Broken wiring (file-name drift)

**[MAJOR] Global synchronic input cites a file that is never produced** (`skills/mpi-global-synchronic/SKILL.md` line 13; `mpi-cross-analyst.md` line 104)
Both direct the agent to read `analyses/generic-synchronic.md`; the actual artifacts are per-scope `event<E>-cat-<C>-gidu<G>-generic_synchronic.isu_second_level_grouping.{json,md}`. A repo-wide glob confirms no `generic-synchronic.md` exists anywhere. Under the anti-fabrication rules the agent must abort on missing input — the stage as documented cannot run.
*Fix:* orchestrator resolves and passes the per-scope paths explicitly; update both files.

**[MINOR] Same SKILL.md names a singular `global-synchronic.md` output that contradicts its own per-scope closure table** (line 18 vs line 33). Same fix family.

**[MINOR] `hypothesis.evidence_extraction` reads only the global synchronic artifact** (`skills/mpi-hypothesis/SKILL.md` lines 13–22)
The manual draws hypotheses from all three cross-participant analyses. Diachronic structural contrasts (IDU-ordering differences across IV levels) never reach the hypothesis stage — they are *not* recoverable from the global synchronic abstraction alone.
*Fix:* pass generic-diachronic and generic-synchronic artifacts as context, or document why the synthesis is sufficient.

### 1.5 Smaller fidelity losses

| Sev | Finding | Fix |
|---|---|---|
| MINOR | Header regex accepts out-of-range scores (`Scored 7/5` parses; category undefined) — `mpi-init/SKILL.md` line 89 | validate score ∈ 0–5, error + skip file |
| MINOR | Question-removal editing rule absent from `normalize` (manual's primary content-editing requirement) | document as researcher pre-step or add LLM-assisted removal pass with audit |
| MINOR | IDU names + moment numbers required by schema from substep 1; `idu_naming_ordering` validator is byte-identical to `criteria_grouping` — manual sequences naming *after* convergence | make `idu_name`/`moment` optional until the naming substep |
| MINOR | Temporal-linkage-phrase boundary detection ("and then", "after that") absent from analyst rules; "prefer fewer IDUs" heuristic actively works against boundary splits | add linkage-phrase scan rule to `mpi-analyst.md` |
| MINOR | "Optimum small set / none overly complex" pattern constraint absent; replaced by a bare ≥2-participant threshold | add merge-evaluation + justification step |
| MINOR | No required `event` field on global-synchronic ISUs — Event provenance is markdown-convention only | add `source_event` to `_validate_global_synchronic` |
| MINOR | Replication-with-second-set recommendation absent from hypothesis output | add mandatory `replication_recommendation` field |
| NOTE | No advisory when participant count falls outside the manual's 6–12 adequacy guidance | optional init-time note |

### 1.6 Methodologically unsound despite documentation

**[MAJOR] "Independent researcher" = same model, same system prompt, fresh session** (`skills/mpi-irr/SKILL.md` lines 47–49)
The manual's independent researcher exists to detect *bias*; two sessions of the same weights with the same prompt share every prior, so agreement is inflated by construction and systematic model bias is undetectable in principle. This is documented, but the documentation claims more than session isolation can deliver.
*Fix (either):* (a) require/encourage a different model family for the alternate analyst, recorded in the IRR manifest; (b) relabel the metric honestly as **intra-model consistency**, caveat it in SKILL.md and every IRR record, and treat true inter-rater reliability as requiring a human or heterogeneous-model rater. Also structurally block the alternate analyst from reading `analyses/`.

---

## 2. Neutral adaptations (verified as documented + defensible — no action needed)

- Per-(event × IV category) iteration in generic diachronic instead of one all-IV table per event — documented; `cross_iv_contrast` exists to restore the cross-level comparison (and the orchestrator notes this is a genuine design debate, not an oversight; see §4)
- Session splitting handled upstream of prep (header contract implies pre-split files)
- Utterance numbering owned by offsets registration rather than a spreadsheet column
- Speaker/verbatim-utterance columns replaced by `utterance_refs` span grounding (stronger traceability, different shape)
- Single-utterance-per-line as a validated precondition rather than an editing step the pipeline performs
- "Raw" vs "edited transcript" framing inversion — raw is the immutable anchor; manual's "preserve the edited transcripts" served audit, which the close protocol supersedes
- Score-category-first output organization (gap-check; documented deliberate choice)
- Superfluous-utterance removal — manual language is permissive ("can also be removed"), not mandatory
- **Hinge fields / "Diachronic Structure" table** (orchestrator-adjudicated after a finder/verifier conflict): hinges are transition criteria between *adjacent top-level IDUs* (N−1 for N IDUs) — not sub-phase decomposition, which `mpi-diachronic/SKILL.md` line 135 explicitly disclaims citing the manual. They articulate the same boundary logic the manual's linkage-phrase rule serves, so the addition is defensible. **One hazard:** the section name "Diachronic Structure" is the *exact term* the manual excludes ("does not include identifying the diachronic structure"); rename to e.g. "IDU Transitions" to stop the collision misleading readers and future reviewers

## 3. Improvements over the manual

These came out of the verification pass as *documented intentional* — and are scientifically better-grounded than Kev's version:

1. **IRR metric suite**: α + κ + αU + ARI with bootstrap 95% CIs and stratified calibration sampling vs the manual's single point-estimate Cohen's κ on one example. Gating on the **α CI lower bound** is more conservative and more defensible than κ > .6 point comparison. (Caveats: αU is a boundary-agreement approximation — already documented; and this is an improvement *in design* — at present the whole suite is defeated by the §1.1 alignment bug.)
2. **Span grounding as anti-fabrication**: mandatory `utterance_refs` with byte offsets against the immutable raw, empty refs rejecting close. The manual gets grounding for free from humans staring at spreadsheets; the pipeline makes it machine-checkable — a guard the manual has no analogue for.
3. **Structured weak-evidence contract**: `{supports, contradicts, ambiguous, n_transcripts, n_iv_levels_covered, uncertainty_language, negative_cases}` per claim is categorically stronger than the manual's one-sentence caveat — *once §1.3's empty-shell review substep is fixed*.
4. **Transactional close protocol**: close_id-keyed artifact + audit + manifest + commit chain gives provenance the manual's "preserve the edited transcripts" gestures at but cannot deliver.
5. **The κ→α substitution** for free-text segment labels: Cohen's κ assumes a fixed category set; Krippendorff α handles the open label space this data actually has. Kev's κ recommendation is the weaker choice for this data type. (Same present-tense caveat as #1: the §1.1 bug must land first.)

## 4. Causal extension (graded against Book of Why, not the manual)

The manual stops at "patterns that vary per IV level" — rung-1 association with a verbal caveat. The plugin's posture (candidate **mechanisms**, verbatim disclaimer, structured evidence) is the correct Pearl-honest framing for observational interview data. To make the extension live up to its ambition:

- **Rung labels need a guard, not removal.** The schema offers rung-2/3 labels; the verifier correctly noted Book of Why's actual thesis is that higher-rung claims are *legitimate given explicit causal assumptions*. So: require any claim labelled rung ≥ 2 to carry an `assumptions` field (the DAG fragment licensing it), else validation fails. Association-only claims stay rung 1.
- **No DAG artifact exists yet.** A candidate mechanism in prose hides its assumptions; a DAG makes them attackable. Add an optional-but-encouraged per-hypothesis DAG (nodes: IV, mechanism components from generic-IDU/ISU structure, DV focus; plus confounders) — even as mermaid/DOT in the markdown artifact.
- **The built-in confound should be drawn, not footnoted.** IV (self-reported score) and DV (self-reported experience) come from the same participant in the same session — shared-method variance and the participant's self-model are common causes. Any hypothesis DAG should carry `participant self-report disposition → score` and `→ experience description` arrows by default.
- **Confounder enumeration as a required field** in `candidate_drafting` (alternative explanations, selection effects), not free text.
- **Testable implications as the replication hand-off**: each hypothesis should state what pattern a second participant set would show if the mechanism is real (this also discharges the manual's replication recommendation, §1.5).

## 5. Priority order

1. `irr.py` alignment inversion (two-line fix + regression test) — every calibration run is currently wrong
2. Global synchronic input wiring (`generic-synchronic.md` does not exist) — stage cannot run as documented
3. `temporal_order_within_idu` blocking + flag unification + audit event — the manual's only feedback loop
4. Convergence-loop enforcement in `cmd_close`
5. ISU within-IDU grouping rule rewrite (one-paragraph prompt fix, large methodological effect)
6. Common/optional pattern schema; multiple-events gate; weak-evidence-review instructions
7. IRR independence relabel-or-heterogeneous-model decision
8. §1.5 table + §4 causal roadmap as a follow-on design phase

---

_Raw verified findings (22 confirmed with verifier reasoning, 26 refuted with refutation grounds): `docs/reviews/2026-06-05-adversarial-review-data.json`._

# IRR Fidelity (alignment fix + rater independence honesty) Design

## Summary

Inter-rater reliability (IRR) calibration in this pipeline works by having an alternate LLM analyst re-run the same analysis stage independently, then mapping its category labels to the primary analyst's labels via an LLM-proposed alignment, and finally computing four agreement metrics. This design plan fixes two related problems that together made those metrics unreliable. First, a map-orientation bug: the code builds a lookup from primary labels to alternate labels but then feeds it alternate labels at lookup time — so the alignment is never actually applied and the alternate analyst's categories are always compared as raw, un-remapped strings. Fixing this is a one-line swap at two call sites in `irr.py`. Second, when both the primary and alternate analyst are the same model (the common case), the resulting agreement score reflects how consistently the model reproduces its own outputs, not how well it agrees with an independent rater. This is technically valid as a test-retest reliability measure but is misleading if described as ordinary IRR, because two instances of the same model share systematic errors that inflate agreement. The plan addresses this by having the code derive and record a `rater_kind` field — `intra_model` when both analysts are the same model, `heterogeneous_model` when they differ — and attaching a verbatim caveat to every IRR record explaining what the metric does and does not mean in each case.

The two corrections ship as a single two-phase plan because they live in the same files. Phase 1 fixes the alignment bug and adds regression tests that use disjoint label sets to verify that full alignment now yields perfect agreement (α = 1.0). Phase 2 adds the `rater_kind`/`caveat` fields to the IRR record schema and updates the skill documentation to label same-model runs as intra-model consistency checks. Analyst isolation (ensuring the alternate analyst cannot read the primary analyst's outputs) is handled through skill-file instructions and a required isolation statement in the prompt artifact rather than through orchestration-code enforcement, which is explicitly out of scope for this plan.

## Definition of Done

- The `irr.py` alignment-map inversion is fixed at both sites (`compute_coincidence` line ~222, `compute_irr` line ~705) so LLM-proposed label alignments are actually applied; regression tests with disjoint primary/alternate label sets assert α = 1.0 under full alignment (unit level in `scripts/test_irr.py`, integration level through `compute_irr` in `tests/test_irr_calibration.py`).
- Same-model IRR is honestly relabeled as **intra-model consistency**: a `rater_kind` field (`intra_model` | `heterogeneous_model`) is recorded in every IRR record and required by the `agreement_computation` schema; `mpi-irr/SKILL.md` and the IRR record output carry the caveat that same-model agreement cannot detect systematic model bias.
- Optional heterogeneous-model alternate analyst support: `alternate_model` recorded in the manifest/IRR record when used; no hard requirement (calibration must remain runnable without second-model infra).
- The alternate analyst is structurally discouraged from contamination: SKILL.md instructs no reading of `analyses/`; the isolation claim is auditable (prose + record field, not orchestration changes).
- Existing tests pass; no close-protocol or manifest contract changes beyond the new IRR record fields.

Out of scope: changing the α-CI-lower-bound gate semantics; warn-by-default posture (unchanged); the canonical length-weighted αU formula.

This plan is **first in sequence** (plan 1 of 5): every calibration run before the alignment fix produces meaningless IRR metrics.

## Acceptance Criteria

### irr-fidelity.AC1: Label alignments are applied in agreement metrics
- **irr-fidelity.AC1.1 Success:** Disjoint primary/alternate label sets with full alignment yield α = 1.0 (±0.001) through `compute_coincidence`
- **irr-fidelity.AC1.2 Success:** Same data through `compute_irr` end-to-end yields `metrics.alpha.point` ≈ 1.0 and `outcome == "passed"`
- **irr-fidelity.AC1.3 Control:** Same data with `alignment=[]` yields α ≪ 1.0 (the test discriminates aligned from unaligned)
- **irr-fidelity.AC1.4 Success:** Partial alignment remaps only aligned categories; unaligned alternate labels stay distinct in the coincidence matrix

### irr-fidelity.AC2: Rater kind is honestly recorded
- **irr-fidelity.AC2.1 Success:** Absent or identical `alternate_model` produces `rater_kind == "intra_model"` with the verbatim intra-model caveat in the record
- **irr-fidelity.AC2.2 Success:** Differing `alternate_model` produces `rater_kind == "heterogeneous_model"` with its caveat
- **irr-fidelity.AC2.3 Failure:** An agreement_computation record missing `rater_kind` or `caveat` is rejected by schema validation

### irr-fidelity.AC3: Isolation and documentation
- **irr-fidelity.AC3.1 Success:** `mpi-irr/SKILL.md` and `mpi-cross-analyst.md` contain the no-reading-`analyses/` rule and the prompt-artifact isolation-statement requirement; SKILL.md labels same-model metrics "intra-model consistency" and never "self-consistency"
- **irr-fidelity.AC3.2 Success:** All pre-existing `test_irr.py`, `tests/test_irr_calibration.py`, and `tests/test_mpi_orchestration.py` tests pass unchanged in expectation (no pinned buggy-α values)

## Glossary

- **IRR (Inter-rater Reliability)**: A statistical measure of how consistently two independent raters assign the same categories to the same items. In this pipeline, the two raters are both LLM analysts — one primary, one alternate.
- **Krippendorff's α (alpha)**: A reliability coefficient that generalises across measurement scales and handles missing data. The primary headline metric; computed from a coincidence matrix over all utterance-category assignments.
- **Cohen's κ (kappa)**: A reliability coefficient that corrects agreement for chance. Secondary metric; matched to the published manual's literal calculation.
- **αU (alpha-unitizing)**: A boundary-agreement reliability metric for segmentation tasks. The implementation here is a block-bootstrap boundary-agreement approximation, not the full length-weighted Krippendorff αU continuum formula.
- **ARI (Adjusted Rand Index)**: A chance-corrected cluster-similarity statistic measuring how much two partitions overlap regardless of label names. Used as a label-permutation-invariant sanity check.
- **Bootstrap CI (Confidence Interval)**: An interval estimate produced by resampling utterances, recomputing the metric per resample, and taking empirical percentiles. Naive utterance bootstrap for α/κ/ARI; block bootstrap for αU.
- **Coincidence matrix**: A square matrix where rows are primary-rater categories, columns are alternate-rater categories, and cells count items assigned to that pair. The basis for computing α.
- **Alignment map**: An LLM-proposed mapping from alternate-analyst category names to primary-analyst category names, applied before building the coincidence matrix to merge categories that mean the same thing under different names.
- **Alignment-map inversion bug**: The defect this plan fixes. The map was constructed `primary → alternate` but used to look up alternate labels (requiring `alternate → primary`), so alignment was never applied.
- **`compute_coincidence` / `compute_irr`**: The two `irr.py` functions containing the inversion (matrix construction and the top-level metric runner whose output lands in `irr_calibration.jsonl`).
- **`rater_kind`**: New required IRR-record field: `intra_model` when both analysts are the same model, `heterogeneous_model` when they differ. Derived from `primary_model`/`alternate_model`.
- **Intra-model consistency / test-retest reliability**: What same-model IRR actually measures: how stably one model reproduces its own outputs. Distinct from true inter-rater reliability because both instances share systematic biases.
- **Correlated errors (in LLMs)**: The phenomenon (Correlated Errors in LLMs, ICML 2025) where instances of the same model make the same mistakes — agreement does not imply correctness.
- **Self-consistency**: Term deliberately avoided — it already means Wang et al.'s chain-of-thought majority-vote decoding in the LLM literature.
- **`caveat`**: Required IRR-record string carrying the verbatim explanation of what `rater_kind` implies for interpreting the metrics.
- **Alternate-analyst isolation**: Preventing the alternate analyst from reading the primary analyst's outputs (`analyses/`) so the two runs are genuinely independent; enforced via prose rule + required isolation statement in the prompt artifact.
- **Prompt artifact**: The retained record of the exact prompt supplied to an LLM call, kept for auditability and replay.
- **Warn-by-default posture**: The pipeline's default of warning (not blocking) on low/missing IRR; blocking requires `--strict-irr`. Unchanged by this plan.

## Architecture

Two independent corrections to the IRR calibration module, shipped together because both live in `microphenomenograph/1.0.0/scripts/irr.py` + `skills/mpi-irr/SKILL.md`.

**Alignment fix.** `compute_coincidence` builds `alignment_map[primary_cat] = alternate_cat` (line ~222) but looks up alternate labels (line ~244); `compute_irr` repeats the inversion (lines ~705/709). Both sites swap to `alignment_map[alternate] = primary`; lookups are already correct for that direction. The inline comment at line ~216 is updated to "alternate category → primary category". No other logic changes — the bug is purely map orientation.

**Honest rater labeling.** The IRR record (returned by `compute_irr`, validated by `_validate_irr_calibration_agreement_computation` in `_mpi_schemas.py`) gains:

```
rater_kind: "intra_model" | "heterogeneous_model"   (required)
alternate_model: string | null                       (optional metadata, already accepted)
caveat: string                                       (required; verbatim text per rater_kind)
```

`rater_kind` is derived: `heterogeneous_model` iff `alternate_model` is present and differs from `primary_model`, else `intra_model`. The intra-model caveat states: same-model/same-prompt agreement is **intra-model consistency (test-retest reliability)** — it measures stability, not validity; correlated errors inflate agreement (Correlated Errors in LLMs, ICML 2025); treat α ≥ threshold as necessary-but-not-sufficient. Thresholds remain the human Krippendorff conventions (0.667/0.8), explicitly documented as borrowed — no LLM-specific threshold exists in the literature. "Self-consistency" terminology is avoided (collides with the Wang et al. CoT decoding sense).

**Alternate-analyst isolation.** `mpi-irr/SKILL.md` instructs the alternate analyst must not read `analyses/`; the analyst's prompt artifact must include an isolation statement; no orchestration-code enforcement in this plan (prose + auditable record field).

## Existing Patterns

- Schema validators in `_mpi_schemas.py` follow `_require_keys(payload, [...], "payload")` — the `rater_kind`/`caveat` additions extend `_validate_irr_calibration_agreement_computation` the same way.
- `irr.py` already records `primary_model`/`alternate_model` as optional metadata (line ~836); `rater_kind` derivation builds on that.
- Regression tests follow the existing structure in `scripts/test_irr.py` (unit, with `if __name__ == '__main__'` runner list) and `tests/test_irr_calibration.py` (integration through `compute_irr`).
- Warning-by-default IRR posture is unchanged; the strict gate mapping in `mpi_step.py` is untouched by this plan.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Alignment inversion fix + regression tests
**Goal:** LLM-proposed label alignments are actually applied in all agreement metrics.

**Components:**
- `microphenomenograph/1.0.0/scripts/irr.py` — swap map direction at both sites (`compute_coincidence` ~line 222, `compute_irr` ~line 705); fix inline comment
- `microphenomenograph/1.0.0/scripts/test_irr.py` — `test_alignment_disjoint_labels_full_agreement`: disjoint label sets {A,B} vs {X,Y}, full alignment, assert α = 1.0 (±0.001); control assertion that α << 1.0 without alignment
- `tests/test_irr_calibration.py` — `test_compute_irr_with_disjoint_alignment`: end-to-end through `compute_irr` bootstrap path, assert `metrics.alpha.point` ≈ 1.0 and `outcome == "passed"`

**Dependencies:** None.

**Done when:** Both new tests pass; all existing `test_irr.py`, `tests/test_irr_calibration.py`, `tests/test_mpi_orchestration.py` tests pass. Covers irr-fidelity.AC1.*.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: rater_kind relabel + heterogeneous-model support + isolation rule
**Goal:** Same-model IRR is honestly labeled; heterogeneous-model runs are supported and recorded.

**Components:**
- `microphenomenograph/1.0.0/scripts/irr.py` — derive and emit `rater_kind` + `caveat` in the IRR record
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — `_validate_irr_calibration_agreement_computation` requires `rater_kind` and `caveat`
- `microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md` — relabel section (intra-model consistency / test-retest), necessary-but-not-sufficient caveat with citation, heterogeneous-model usage documentation, alternate-analyst no-`analyses/` isolation rule + prompt-artifact isolation statement
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — independent_analyst instructions updated to match (isolation statement requirement)
- Tests: `rater_kind` derivation (same model → `intra_model`; different → `heterogeneous_model`), schema rejection of records missing `rater_kind`/`caveat`

**Dependencies:** Phase 1 (same files; meaningful α values).

**Done when:** New schema/derivation tests pass; existing tests pass. Covers irr-fidelity.AC2.*, AC3.*.
<!-- END_PHASE_2 -->

## Additional Considerations

**Records created before the fix:** any IRR record produced before Phase 1 lands is not comparable to post-fix records (α was computed on unaligned labels). `runs/` is disposable per user direction — no migration; a note in SKILL.md advises re-running calibration if a pre-fix record exists.

**Version bump:** none. Nothing is released; rationale documented in plugin CLAUDE.md per portfolio decision.

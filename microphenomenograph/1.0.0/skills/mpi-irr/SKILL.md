---
name: mpi-irr
description: Use when running /mpi-irr calibrate — runs alternate-agent re-analysis for a calibration transcript, aligns categories via LLM, computes Krippendorff α + Cohen κ + αU + ARI with bootstrap 95% CIs. Writes structured record to .mpi/irr_calibration.jsonl.
user-invocable: true
---
# mpi-irr

## Overview

Automatic inter-rater reliability (IRR) check for model quality. Runs after the calibration
transcript's diachronic and synchronic stages complete. Warning-by-default; opt-in
`--strict-irr` blocks cross-participant stages.

When both analysts are the same model, the resulting score is intra-model consistency —
it measures stability, not validity, because both instances share systematic biases.

Two IRR checks per run:
1. After `diachronic.idu_naming_ordering` closes for each calibration transcript
2. After `synchronic.isu_second_level_grouping` (last IDU) closes for each calibration transcript

When `study.calibration_mode = "stratified"`, both checks fire once per calibration
transcript in `study.calibration_transcript_ids`, plus one aggregate summary record per stage.

## Calibration transcript strategy

Set at `/mpi init --calibration <strategy>`. Stored in manifest as:
- `study.calibration_transcript_ids`: list of transcript IDs selected for IRR calibration
- `study.calibration_mode`: string, either `"stratified"` (default) or `"smoke_test"`

Valid strategies:

| Strategy | Meaning | Notes |
|---|---|---|
| `stratified` | One transcript per (suggestion × IV-level) stratum (default) | Methodologically defensible; requires ≥1 transcript per stratum; populates `study.calibration_transcript_ids` |
| `<transcript_id>` | Specific transcript (e.g., `p1s1`) | Defensible if pre-chosen and documented; sets `study.calibration_transcript_ids = ["p1s1"]` |
| `first` | First transcript to complete (smoke-test mode) | Sets `study.calibration_mode = "smoke_test"` and `study.calibration_transcript_ids` dynamically |

If `stratified` is requested but any stratum has zero transcripts, init refuses with
`stratified_unavailable` and prompts the user to pick an alternative.

## Rater kind and caveats

Every IRR record carries a `rater_kind` field:

| `rater_kind` | Condition | Interpretation |
|---|---|---|
| `intra_model` | Both analysts are the same model (or `alternate_model` absent/equal to `primary_model`) | Intra-model consistency / test-retest reliability. Measures stability, not validity. Correlated errors inflate agreement (Correlated Errors in LLMs, ICML 2025). Treat α ≥ threshold as necessary but not sufficient. |
| `heterogeneous_model` | `alternate_model` differs from `primary_model` | Heterogeneous-model IRR. Reduces shared systematic bias. More indicative of genuine consensus, but model-specific biases may still inflate scores. |

Thresholds (α ≥ 0.667 tentative, ≥ 0.8 acceptable) are borrowed from Krippendorff's conventions for **human** analysts after training. No LLM-specific threshold exists in the literature; treat these as conventions, not evidence.

**Pre-fix records:** Any IRR record produced before the alignment-map fix (irr-fidelity plan 1) is not comparable to post-fix records — α was computed on unaligned labels. Re-run calibration if a pre-fix record exists in `.mpi/irr_calibration.jsonl`.

## Alternate-analyst isolation

The alternate analyst MUST NOT read any files under `analyses/` (primary analyst outputs).
Isolation is required for the two runs to be genuinely independent.

When writing the `irr_calibration.independent_analyst` prompt artifact, the analyst MUST
include an explicit isolation statement confirming that no primary-analyst artifacts were
read before producing this alternate analysis. Example:
```json
{
  "isolation_statement": "I did not read any files under analyses/ before producing this alternate analysis."
}
```

This field is auditable: the prompt artifact is retained with the close record.

## Calibration workflow

`mpi-irr calibrate --transcript <pNsN> --stage diachronic|synchronic` performs three steps:

### Step 1: `irr_calibration.independent_analyst` (LLM)

Run the alternate-agent analysis through the same substep DAG as the primary, writing
per-substep alternate artifacts to `analyses/independent/<scope>-<stage>.<substep>.{json,md,prompt.json}`.

The alternate agent is a fresh subagent invocation — same agent file (`mpi-analyst` for
per-transcript stages), different session context. It should produce its analysis
independently, without seeing the primary analysis.

### Step 2: `irr_calibration.alignment` (LLM)

A fresh `mpi-cross-analyst` subagent proposes a category mapping between primary and
alternate IDU/ISU sets. Output:
```json
{
  "mapping": [
    {
      "primary": "Initial Sensation",
      "alternate": "First Awareness",
      "confidence": 0.82,
      "rationale": "both describe the opening tactile moment before any imagery"
    }
  ],
  "unmatched_primary": [],
  "unmatched_alternate": []
}
```

In **assisted mode**: surface the proposed mapping via AskUserQuestion for accept/edit.
In **yolo**: auto-accept; emit `irr_alignment_auto_accepted` audit event.

Unmatched categories from either rater are retained in the union (canonical Krippendorff —
they contribute zero-diagonal cells with nonzero marginals, not "structural zeros").

### Step 3: `irr_calibration.agreement_computation` (orchestrator)

Call `scripts/irr.py:compute_irr()` with the aligned assignments. Caller MUST pass:
- `primary`, `alternate`: {utterance_id: category} dicts
- `alignment`: [{primary, alternate, confidence, rationale}, ...]
- `unmatched_primary`, `unmatched_alternate`: lists of unmatched categories
- `n_utterances`: total utterance count
- `stage`: **REQUIRED** — either `"diachronic"` or `"synchronic"` per the calibration stage
- `transcript_id`, `participant_id`, `primary_model`, `alternate_model`: optional metadata strings

Writes four metrics with 95% bootstrap CIs:

| Metric | Bootstrap | Notes |
|---|---|---|
| Nominal α | Naive utterance | Primary headline metric |
| Cohen's κ | Naive utterance | Secondary; matches manual literally |
| αU | Block (block_length ≈ sqrt(N)) | Segmentation metric, label-independent |
| ARI | Naive utterance | Label-permutation-invariant sanity check |

Append one structured record to `.mpi/irr_calibration.jsonl`. The `stage` field in the
record is set to the caller-provided value (either `"diachronic"` or `"synchronic"`), which
is used by the IRR gate to map cross-participant stages to their upstream IRR stage.

`outcome = "passed"` iff `alpha.ci_lo >= 0.6` (conservative against small-N noise).

## IRR warning gate (cross-participant skills)

At the start of each cross-participant stage (`mpi-generic-diachronic`, etc.):

1. Read `.mpi/irr_calibration.jsonl` and filter to records matching the upstream stage
2. If no matching records, or if **any** matching record has `outcome != "passed"`:
   - Emit `irr_warning` audit event with `mpi.blocked_reason: "irr_low|irr_missing"`
   - **Without `--strict-irr`**: proceed with a console warning
   - **With `--strict-irr`**: exit with `irr_check_failed` error before producing any artifact

## Literature thresholds (informational)

Thresholds below are calibrated for *human analysts after training*, not LLM raters.
Transfer to LLM-as-rater is by analogy — treat as convention, not evidence.

| Metric | Tentative | Acceptable | Source |
|---|---|---|---|
| α | ≥ 0.667 | ≥ 0.8 | Krippendorff 2018 |
| κ | ≥ 0.6 | ≥ 0.61 | Sheldrake & Dienes 2025; Landis & Koch 1977 |
| αU | ≥ 0.667 | ≥ 0.8 | Krippendorff 2016 |
| ARI | (no bright-line) | — | Hubert & Arabie 1985 |

## Operation

`mpi-irr calibrate --transcript <pNsN> --stage diachronic|synchronic`

Runs an automatic inter-rater reliability (IRR) check for the given calibration transcript
and stage. Three steps:
1. `irr_calibration.independent_analyst` — re-runs the stage's substep DAG through a fresh
   `mpi-cross-analyst` (or `mpi-analyst` for per-transcript stages) in the `analyses/independent/`
   directory.
2. `irr_calibration.alignment` — a fresh `mpi-cross-analyst` subagent proposes a category
   mapping between primary and alternate with per-pair confidence + rationale.
3. `irr_calibration.agreement_computation` — orchestrator builds the union-of-categories
   coincidence matrix and computes four metrics (α, κ, αU, ARI) with 95% bootstrap CIs
   (N=5000). Appends one structured record to `.mpi/irr_calibration.jsonl`.

Phase 13 implements `scripts/irr.py` which backs the agreement computation.

## Closure (mandatory)

`mpi-irr` is NOT a read-only skill. It produces alignment and agreement artifacts.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `irr_calibration.independent_analyst` | mpi-cross-analyst or mpi-analyst (LLM) | `analyses/independent/<scope>-<stage>.<substep>.{json,md,prompt.json}` for every substep of the shadowed stage | per-substep scope mirrors primary | Re-runs the full stage DAG through the alternate agent |
| `irr_calibration.alignment` | mpi-cross-analyst (LLM) | `analyses/irr_calibration.alignment.{json,md,prompt.json}` | `global` | In assisted mode: user accepts/edits the proposed mapping. In yolo: auto-accepted, emits `irr_alignment_auto_accepted` audit event |
| `irr_calibration.agreement_computation` | orchestrator | record appended to `.mpi/irr_calibration.jsonl` | `global` | Mechanical computation; no LLM, no prompt artifact. Writes four metrics with bootstrap CIs |

**Cross-participant warning gate:** Skills that follow IRR calibration in the pipeline
(`mpi-generic-diachronic`, etc.) emit an `irr_warning` audit event at stage start if
**any** IRR record for the upstream stage has outcome != "passed", or no records exist.
They proceed unless `--strict-irr` is passed, in which case they exit with a named ERROR.

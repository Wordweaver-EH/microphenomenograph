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

Two IRR checks per run:
1. After `diachronic.idu_naming_ordering` closes for the calibration transcript
2. After `synchronic.isu_second_level_grouping` (last IDU) closes for the calibration transcript

When `study.calibration_transcript = "stratified"`, both checks fire once per calibration
transcript, plus one aggregate summary record per stage.

## Calibration transcript strategy

Set at `/mpi init --calibration <strategy>`. Valid strategies:

| Strategy | Meaning | Notes |
|---|---|---|
| `stratified` | One transcript per (suggestion × IV-level) stratum (default) | Methodologically defensible; requires ≥1 transcript per stratum |
| `<transcript_id>` | Specific transcript (e.g., `p1s1`) | Defensible if pre-chosen and documented |
| `first` | First transcript to complete (smoke-test mode) | Sets `study.calibration_mode = "smoke_test"` in manifest; user must confirm |

If `stratified` is requested but any stratum has zero transcripts, init refuses with
`stratified_unavailable` and prompts the user to pick an alternative.

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

Call `scripts/irr.py:compute_irr()` with the aligned assignments. Writes four metrics with
95% bootstrap CIs:

| Metric | Bootstrap | Notes |
|---|---|---|
| Nominal α | Naive utterance | Primary headline metric |
| Cohen's κ | Naive utterance | Secondary; matches manual literally |
| αU | Block (block_length ≈ sqrt(N)) | Segmentation metric, label-independent |
| ARI | Naive utterance | Label-permutation-invariant sanity check |

Append one structured record to `.mpi/irr_calibration.jsonl`.

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

---
name: mpi-irr
description: Use when running /mpi-irr calibrate — runs alternate-agent re-analysis for a calibration transcript, aligns categories via LLM, computes Krippendorff α + Cohen κ + αU + ARI with bootstrap 95% CIs. Writes structured record to .mpi/irr_calibration.jsonl.
user-invocable: true
---
# mpi-irr

> **Implementation note (Phase 13):** The full operational body of this skill — the
> calibration workflow, alternate-agent dispatch, alignment substep, and agreement
> computation — is implemented in Phase 13. This file contains only the Closure contract
> and structural outline. Do not invoke this skill until Phase 13 is complete.

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
(`mpi-generic-diachronic`, etc.) emit an `irr_warning` audit event at stage start if the
most-recent IRR record's α CI lower bound is below 0.6 or no IRR record exists. They proceed
unless `--strict-irr` is passed, in which case they exit with a named ERROR.

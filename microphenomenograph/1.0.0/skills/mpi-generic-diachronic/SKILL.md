---
name: mpi-generic-diachronic
description: Use when running /mpi generic-diachronic — aggregates per-participant diachronic outputs across score categories via mpi-cross-analyst; warns if any participant diachronic not complete
user-invocable: false
---
# mpi-generic-diachronic

Run cross-participant generic diachronic aggregation. Requires ALL participants to have
`diachronic: done` in the manifest.

## Completeness check

Before invoking the cross-analyst, check manifest for any participants with
`diachronic.status != "done"`. If any exist:

Print warning:
```
WARNING: Generic diachronic requires all per-participant diachronic analyses to be complete.
The following participants are not yet complete: p2s1, p3s2, ...
Run /mpi diachronic to complete them, then re-run /mpi generic-diachronic.
```

Do NOT abort — ask the user if they want to proceed with the available participants or
wait for the rest. If user says proceed, continue with available `done` outputs.

**Verifies:** microphenomenograph.AC5.3

## Invoking mpi-cross-analyst

Collect all `analyses/pNsN-diachronic.md` files for participants with `diachronic: done`.
Include score category info from manifest.

Pass to `mpi-cross-analyst`:
- Task type: `generic_diachronic`
- All diachronic outputs with their participant key and score category
- Instruction: "Group IDUs by score category, identify common patterns"

## Output

Write `analyses/generic-diachronic.md`.

**Verifies:** microphenomenograph.AC5.1

## Anti-fabrication rule

If your input artifacts (transcripts, upstream substep outputs) are missing, empty, or
malformed, return `ERROR <reason>` and stop. Never generate placeholder or synthetic
content to make the pipeline appear to progress.

## Closure (mandatory)

Each generic-diachronic substep closes its own four-part transaction via `mpi_step.py close`.
The orchestrator closes `participant_row_assembly`; `mpi-cross-analyst` closes the three LLM substeps.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `generic_diachronic.participant_row_assembly` | orchestrator | `event<E>-cat-<C>-generic_diachronic.participant_row_assembly.{json,md}` | `event<E>-cat-<C>` | Mechanical reshape; no LLM, no prompt artifact |
| `generic_diachronic.idu_similarity_grouping` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.{json,md,prompt.json}` | `event<E>-cat-<C>` | LLM analytic judgment; colour/group label per IDU cell with rationale |
| `generic_diachronic.pattern_identification` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-generic_diachronic.pattern_identification.{json,md,prompt.json}` | `event<E>-cat-<C>` | Extracts common ordered patterns across IV-grouped rows |
| `generic_diachronic.cross_iv_contrast` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-generic_diachronic.cross_iv_contrast.{json,md,prompt.json}` | `event<E>-cat-<C>` | Explicit comparison of how patterns differ by IV level |

**Prerequisite gate:** `generic_diachronic.*` is blocked until all transcripts for the event have `diachronic.*` and `synchronic.*` all `done` with no pending `temporal_order_within_idu` or `concurrent_with_adjacent_idu` flags. The helper enforces this via `prereq_unsatisfied`.

**Commit message format:** `mpi: <actor> generic_diachronic.<substep> event<E>-cat-<C> (<N>units <K>flagged)`

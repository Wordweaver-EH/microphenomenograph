---
name: mpi-generic-synchronic
description: Use when running /mpi generic-synchronic — aggregates per-participant synchronic outputs across score categories via mpi-cross-analyst
user-invocable: false
---
# mpi-generic-synchronic

Run cross-participant generic synchronic aggregation. Requires ALL participants to have
`synchronic: done` in manifest. Same completeness warning as mpi-generic-diachronic.

Invoke `mpi-cross-analyst` with task type `generic_synchronic`, passing all
`analyses/pNsN-synchronic.md` files with their score category info.

Write `analyses/generic-synchronic.md`.

## Closure (mandatory)

Each generic-synchronic substep closes its own four-part transaction via `mpi_step.py close`.
The orchestrator closes `worksheet_assembly`; `mpi-cross-analyst` closes the two LLM substeps.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `generic_synchronic.select_generic_idus_of_interest` | mpi-cross-analyst (LLM) | `event<E>-generic_synchronic.select_generic_idus_of_interest.{json,md,prompt.json}` | `event<E>` | Reads pattern/cross-contrast outputs; selects generic-IDUs for downstream worksheets |
| `generic_synchronic.worksheet_assembly` | orchestrator | `event<E>-cat-<C>-gidu<G>-generic_synchronic.worksheet_assembly.{json,md}` | `event<E>-cat-<C>-gidu<G>` | Mechanical assembly per (event × IV category × selected generic-IDU); no LLM, no prompt artifact |
| `generic_synchronic.isu_second_level_grouping` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-gidu<G>-generic_synchronic.isu_second_level_grouping.{json,md,prompt.json}` | `event<E>-cat-<C>-gidu<G>` | ISU 2nd Level of Abstraction preserved as distinct column |

**Prerequisite gate:** `generic_synchronic.*` is blocked until the matching `generic_diachronic.*` outputs for the same (event, IV category) are `done`.

**Commit message format:** `mpi: <actor> generic_synchronic.<substep> <scope> (<N>units <K>flagged)`

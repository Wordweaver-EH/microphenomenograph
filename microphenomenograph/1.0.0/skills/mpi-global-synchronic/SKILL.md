---
name: mpi-global-synchronic
description: Use when running /mpi global-synchronic — produces global synchronic synthesis referencing source participant and suggestion for every row via mpi-cross-analyst
user-invocable: false
---
# mpi-global-synchronic

Produce global synchronic synthesis. Requires `generic_synchronic: done` in manifest.

Invoke `mpi-cross-analyst` with:
- Task type: `global_synchronic`
- Scope: `gidu<G>-cat-<C>`

**Resolving inputs:** Run the following to get the correct per-scope upstream generic-synchronic artifact paths before invoking the analyst:
```bash
python scripts/mpi_step.py inputs --scope gidu<G>-cat-<C> --stage global_synchronic --run-dir .
```
Pass the resolved `event<E>-cat-<C>-gidu<G>-generic_synchronic.isu_second_level_grouping.{json,md}` artifacts as inputs to the analyst.

Every row in the output MUST reference source participant and suggestion. Each ISU MUST include a `source_event` field naming which event (e.g. `"event1"`) the ISU came from.
**Verifies:** microphenomenograph.AC5.2

Write `analyses/gidu<G>-cat-<C>-global_synchronic.{json,md,prompt.json}` for the current scope (one artifact set per (generic-IDU × IV category) case — see the Closure table below).

## Anti-fabrication rule

If your input artifacts (transcripts, upstream substep outputs) are missing, empty, or
malformed, return `ERROR <reason>` and stop. Never generate placeholder or synthetic
content to make the pipeline appear to progress.

## Closure (mandatory)

The single global-synchronic substep closes its own four-part transaction via `mpi_step.py close`.
The `mpi-cross-analyst` subagent owns persistence.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `global_synchronic` | mpi-cross-analyst (LLM) | `gidu<G>-cat-<C>-global_synchronic.{json,md,prompt.json}` | `gidu<G>-cat-<C>` | ISU 2nd Level of Abstraction preserved as a distinct column |

**Prerequisite gate:** `global_synchronic.*` is blocked until `generic_synchronic.*` is `done` for every relevant (event × IV category × generic-IDU) triple.

**Commit message format:** `mpi: mpi-cross-analyst global_synchronic gidu<G>-cat-<C> (<N>units <K>flagged)`

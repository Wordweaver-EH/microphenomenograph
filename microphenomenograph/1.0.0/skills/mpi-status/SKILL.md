---
name: mpi-status
description: Use when running /mpi status — reads .mpi/project.json and renders a participant × stage completion table
user-invocable: false
---
# mpi-status

Read `.mpi/project.json` and render a progress overview.

## If no manifest exists

Print: `No .mpi/project.json found. Run /mpi init first.`

## Progress table format

Render a markdown table with one row per participant/suggestion, one column per stage.
Use symbols: ✓ (done), ⧖ (pending), ✗ (flagged).

```
| Participant | Score | Category | prep | diachronic | synchronic |
|---|---|---|---|---|---|
| p1s1 | 4 | high | ✓ | ✓ | ⧖ |
| p1s2 | 3 | moderate | ⧖ | ⧖ | ⧖ |
```

Then render cross-participant stages:

```
Cross-participant stages:
| Stage | Status |
|---|---|
| generic_diachronic | ⧖ |
| generic_synchronic | ⧖ |
| global_synchronic | ⧖ |
| hypothesis | ⧖ |
```

## Summary line

Print: `N/M stages complete across all participants. Review queue: K items.`

Count items in `.mpi/review-queue.md` if it exists (count `##` headers as items).

## Closure (mandatory)

`mpi-status` is a **read-only skill**. It produces no artifact and performs no close.

However, it MUST emit a read-only audit event for trace continuity:
```bash
python scripts/mpi_step.py close \
  --actor orchestrator \
  --stage status \
  --substep status_read \
  --scope global \
  --status read \
  --reason "status read" \
  --run-dir .
```
The `--status read` flag causes `mpi_step.py` to emit a `stage_phase: read` audit event
without writing any artifact, mutating the manifest, or creating a git commit. This keeps
the audit trail complete even for read-only operations.

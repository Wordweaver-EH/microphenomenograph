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

Update manifest:
```json
"generic_diachronic": { "status": "done", "output_path": "analyses/generic-diachronic.md" }
```

Commit if yolo mode: `git commit -m "mpi: generic-diachronic analysis"`

**Verifies:** microphenomenograph.AC5.1

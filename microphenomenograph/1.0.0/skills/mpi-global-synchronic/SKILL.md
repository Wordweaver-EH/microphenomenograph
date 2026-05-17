---
name: mpi-global-synchronic
description: Use when running /mpi global-synchronic — produces global synchronic synthesis referencing source participant and suggestion for every row via mpi-cross-analyst
user-invocable: false
---
# mpi-global-synchronic

Produce global synchronic synthesis. Requires `generic_synchronic: done` in manifest.

Invoke `mpi-cross-analyst` with:
- Task type: `global_synchronic`
- All `analyses/pNsN-synchronic.md` files
- `analyses/generic-synchronic.md`

Every row in the output MUST reference source participant and suggestion.
**Verifies:** microphenomenograph.AC5.2

Write `analyses/global-synchronic.md`. Update manifest and commit if yolo.

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

Write `analyses/generic-synchronic.md`. Update manifest and commit if yolo.

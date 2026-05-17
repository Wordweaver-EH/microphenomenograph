---
name: mpi-synchronic
description: Use when running /mpi synchronic — runs per-participant ISU synchronic analysis via mpi-analyst; requires diachronic stage done; routes low-confidence items to review queue
user-invocable: false
---
# mpi-synchronic

Run synchronic ISU analysis for one or more participants. Requires diachronic stage to
be `done`. Invokes `mpi-analyst` with the diachronic output as input.

## Prerequisites

- `.mpi/project.json` must exist
- `diachronic` stage must be `done` for target participant(s)
- If `diachronic` is NOT done: print error `ERROR: pNsN diachronic stage not complete. Run /mpi diachronic pNsN first.` Do NOT produce empty output.

## Input

Participant key (optional): `pNsN`. If omitted, process all with `synchronic: pending`
AND `diachronic: done`.

## Few-shot example selection

Same closest-length logic as mpi-diachronic, but using `examples/analyses/phase1/pNsN-synchronic.md` files. Never use phase2 files.

## Invoking mpi-analyst

Invoke `mpi-analyst` with:
1. Task type: `synchronic`
2. The diachronic output (full content of `analyses/pNsN-diachronic.md`)
3. Selected few-shot example(s):
   ```
   ## Example synchronic analysis (p3s2):
   [full content of examples/analyses/phase1/p3s2-synchronic.md]
   ```
4. "Now produce synchronic analysis for:"
5. The diachronic output

## Parsing and routing

Same confidence routing as mpi-diachronic. For flagged ISUs, append to `.mpi/review-queue.md`:

```markdown
## [pNsN] synchronic ISU in <IDU name> (confidence: <N>)
...
```

## Output file

Write `analyses/pNsN-synchronic.md`:

```markdown
# Participant N, Suggestion N (Scored N/5)

## Synchronic Analysis

| IDU Name | ISU Name | ISU 2nd Level | Utterance Numbers | Criteria | Confidence |
|---|---|---|---|---|---|
| Initial thoughts | Feeling watched | | 2, 3, 10, 16, 24 | The utterances talk about being watched | 5 |
|  | Feeling expectations | | | The utterances talk about felt expectations | 4 |
| Shift in attention | Noticing change | | 4, 17, 18 | The utterances talk about a shift in focus | 5 |
...
```

Note: **Utterance Numbers appear only on the first ISU row** for each IDU group; subsequent rows in the same group leave the cell blank. This matches the OSF reference data format (utterances are per-IDU-group, not per-ISU).

## Manifest update

```json
"synchronic": { "status": "done", "output_path": "analyses/pNsN-synchronic.md" }
```

If ALL ISUs for this participant were routed to review queue, set status to `"flagged"` (same logic as diachronic).

Append to `.mpi/reasoning.log`:
```
[<timestamp>] pNsN synchronic: <reasoning_summary>. N ISU groups identified. K flagged.
```

## Mode handling

Same as mpi-diachronic (assisted/yolo).

**Verifies:** microphenomenograph.AC4.1, microphenomenograph.AC4.2, microphenomenograph.AC4.3

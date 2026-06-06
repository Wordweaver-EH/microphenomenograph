---
name: mpi-synchronic
description: Use when running /mpi synchronic — runs per-participant ISU synchronic analysis via mpi-analyst (zero-shot); requires diachronic stage done; routes low-confidence items to review queue
user-invocable: false
---
# mpi-synchronic

Run synchronic ISU analysis for one or more participants. Requires diachronic stage to
be `done`. Invokes `mpi-analyst` with the diachronic output as input zero-shot (no examples).

## Prerequisites

- `.mpi/project.json` must exist
- `diachronic` stage must be `done` for target participant(s)
- If `diachronic` is NOT done: print error `ERROR: pNsN diachronic stage not complete. Run /mpi diachronic pNsN first.` Do NOT produce empty output.

## Input

Participant key (optional): `pNsN`. If omitted, process all with `synchronic: pending`
AND `diachronic: done`.

## Invoking mpi-analyst

Invoke `mpi-analyst` with:
1. Task type: `synchronic`
2. The diachronic output (full content of `analyses/pNsN-diachronic.md`)
3. "Now produce synchronic analysis for:"
4. The diachronic output

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

## Mode handling

Same as mpi-diachronic (assisted/yolo).

**Verifies:** microphenomenograph.AC4.1, microphenomenograph.AC4.2, microphenomenograph.AC4.3

## Anti-fabrication rule

If your input artifacts (transcripts, upstream substep outputs) are missing, empty, or
malformed, return `ERROR <reason>` and stop. Never generate placeholder or synthetic
content to make the pipeline appear to progress.

## Closure (mandatory)

Synchronic substeps iterate **per IDU within a transcript**, not per stage-level invocation.
Scope for each substep is `pNsN-iduN` (e.g., `p1s1-idu1`, `p1s1-idu2`).

| Substep | Actor | Artifacts | Notes |
|---------|-------|-----------|-------|
| `synchronic.theme_grouping_within_idu` | mpi-analyst (LLM) | `pNsN-iduN-synchronic.theme_grouping_within_idu.{json,md,prompt.json}` | First synchronic substep per IDU. If `temporal_order_within_idu: true`, `cmd_close` automatically downgrades to `flagged` (blocking `isu_naming`); `temporal_order_within_idu: true` also requires ≥1 ISU with `flag_for_review: true` (hard schema). Manifest records `idu_split_after_synchronic` audit event when a diachronic re-close follows this flag. |
| `synchronic.isu_naming` | mpi-analyst (LLM) | `pNsN-iduN-synchronic.isu_naming.{json,md,prompt.json}` | Requires `theme_grouping_within_idu` done for same IDU |
| `synchronic.isu_second_level_grouping` | mpi-analyst (LLM) | `pNsN-iduN-synchronic.isu_second_level_grouping.{json,md,prompt.json}` | Final synchronic substep per IDU |

**Output columns (all three substeps):** `criteria` (string) | `isu_name` (string) | `isu_second_level_of_abstraction` (string or empty). These three columns are preserved as distinct fields through all downstream aggregation.

**IDU-split-after-synchronic return edge:** If `theme_grouping_within_idu` flags `temporal_order_within_idu: true`, the orchestrator re-closes `diachronic.criteria_revision` for that transcript with the split context in the prompt. Manifest records `idu_split_after_synchronic` audit event linking both span_ids.

---
name: mpi-diachronic
description: Use when running /mpi diachronic — runs per-participant diachronic IDU analysis via mpi-analyst (zero-shot); routes low-confidence items to review queue
user-invocable: false
---
# mpi-diachronic

Run diachronic IDU analysis for one or more participants. Invokes `mpi-analyst` subagent
zero-shot (no examples).

## Prerequisites

- `.mpi/project.json` must exist (run `/mpi init` first)
- Transcript prep must be `done` for target participant(s), OR run prep automatically

## Input

Participant key (optional): `pNsN`. If omitted, process all with `diachronic: pending`.

## Invoking mpi-analyst

Invoke the `mpi-analyst` subagent with this context:

1. The task type: `diachronic`
2. The target transcript (full text)
3. The instruction: "Analyse the following transcript:"
4. The target transcript text

## Parsing the output

Parse the JSON from the `## Output` section of the agent's response.

Validate:
- Each IDU has `idu_number`, `idu_name`, `moment`, `criteria`, `confidence` (1–5),
  `flag_for_review` (boolean), `utterance_numbers` (non-empty list)
- `confidence` is integer 1–5
- `hinge_to_next` is a non-null string for all IDUs except the last; is `null` for the last IDU

## Confidence-Diversity routing

For each IDU:
- If `confidence >= 3` AND `flag_for_review == false`: **auto-accept**
- Otherwise: append to `.mpi/review-queue.md`:

```markdown
## [pNsN] diachronic IDU <N>: <IDU name> (confidence: <N>)
- **Participant:** pNsN
- **Stage:** diachronic
- **IDU number:** <N>
- **IDU name:** <name>
- **Confidence:** <N>/5
- **Flagged by analyst:** <true/false>
- **Utterances:** <utterance_numbers>
- **Criteria:** <criteria>
- **Hinge from previous IDU (if any):** <hinge_to_next of preceding IDU, or omit if first IDU>
- **Hinge to next IDU (if any):** <hinge_to_next of this IDU, or omit if last IDU>
- **Analyst reasoning:** <relevant excerpt>
```

## Output file

Write `analyses/pNsN-diachronic.md` (create `analyses/` if needed):

```markdown
# Participant N, Suggestion N (Scored N/5)

## Diachronic Analysis

| IDU # | IDU Name | Moment | Utterance Numbers | Criteria | Confidence |
|---|---|---|---|---|---|
| 1 | Initial thoughts | 1 | 2, 3, 10, 16, 24 | The utterances talk about initial thoughts | 5 |
| 2 | Avoiding unhelpful thoughts | 2 | 4, 17, 18, 20, 23 | The utterances talk about... | 4 |
...

## Diachronic Structure

| IDU | Hinge | IDU |
|---|---|---|
| Initial thoughts | Presence of unhelpful thoughts | Avoiding unhelpful thoughts |
| Avoiding unhelpful thoughts | Unhelpful thoughts no longer present | Relaxing |
...
```

The Diachronic Structure table has one row per adjacent IDU pair (N−1 rows for N IDUs).
Left column = IDU_n name, middle = hinge criterion, right = IDU_{n+1} name. This matches
the OSF reference format and enables benchmarking via Cohen's κ.

Include ALL IDUs (including flagged ones) in the output table. Flagged items also appear
in review-queue but are not omitted from the analysis.

## Manifest update

```json
"diachronic": { "status": "done", "output_path": "analyses/pNsN-diachronic.md" }
```

If ALL IDUs for this participant were routed to the review queue (every IDU had
`confidence < 3` or `flag_for_review: true`), set status to `"flagged"` instead:

```json
"diachronic": { "status": "flagged", "output_path": "analyses/pNsN-diachronic.md" }
```

This enables `/mpi status` to surface participants that need full human review before proceeding.

## Append to reasoning log

Append to `.mpi/reasoning.log`:

```
[<ISO timestamp>] pNsN diachronic: <reasoning_summary>. N IDUs identified. K flagged for review.
```

## Mode handling

- **Assisted:** After completing one participant, show the output table to the user and
  ask for confirmation before proceeding to the next. If user rejects, re-run ONLY that
  participant's analysis (do not re-run others).
- **Yolo:** Process all pending participants in parallel (multiple mpi-analyst subagent
  calls in a single turn). Commit each result as it completes:
  `git add analyses/pNsN-diachronic.md && git commit -m "mpi: pNsN diachronic analysis"`

**Verifies:** microphenomenograph.AC3.1, microphenomenograph.AC3.2, microphenomenograph.AC3.3, microphenomenograph.AC3.4, microphenomenograph.AC3.5

## Closure (mandatory)

Each diachronic substep closes its own four-part transaction via `mpi_step.py close`.
The `mpi-analyst` subagent owns persistence for all three LLM substeps.

| Substep | Actor | Artifacts | Notes |
|---------|-------|-----------|-------|
| `diachronic.criteria_grouping` | mpi-analyst (LLM) | `pNsN-diachronic.criteria_grouping.{json,md,prompt.json}` | First substep; no prerequisites |
| `diachronic.criteria_revision` | mpi-analyst (LLM) | `pNsN-diachronic.criteria_revision.{json,md,prompt.json}` | JSON must include `convergence: {decision, reason}`; orchestrator re-dispatches while `decision == "more_revision_needed"`, capped at 5 passes |
| `diachronic.idu_naming_ordering` | mpi-analyst (LLM) | `pNsN-diachronic.idu_naming_ordering.{json,md,prompt.json}` | Final diachronic substep; its close triggers synchronic eligibility |

**Commit message format:** `mpi: mpi-analyst diachronic.<substep> pNsN (<N>units <K>flagged)`

**Manual-native constraint:** Diachronic does NOT include sub-phase identification (`diachronic.phases`, `diachronic.du`, `diachronic.refined_du`). Substep names follow manual_kev.md (Sheldrake & Dienes 2025) verbatim.

**Anti-fabrication rule:** If transcript is missing, empty, or malformed, `mpi-analyst` returns `ERROR <reason>` and stops. Never synthesize placeholder content.

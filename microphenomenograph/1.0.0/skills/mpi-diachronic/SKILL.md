---
name: mpi-diachronic
description: Use when running /mpi diachronic — runs per-participant diachronic IDU analysis via mpi-analyst with few-shot CoT prompting; routes low-confidence items to review queue
user-invocable: false
---
# mpi-diachronic

Run diachronic IDU analysis for one or more participants. Invokes `mpi-analyst` subagent
with few-shot examples drawn from `examples/analyses/phase1/` only (never phase2).

## Prerequisites

- `.mpi/project.json` must exist (run `/mpi init` first)
- Transcript prep must be `done` for target participant(s), OR run prep automatically

## Input

Participant key (optional): `pNsN`. If omitted, process all with `diachronic: pending`.

## Few-shot example selection

Select 1–2 diachronic examples from `examples/analyses/phase1/` using closest-length
matching:
1. Count lines in the target transcript
2. For each phase1 transcript in `examples/transcripts/`, count lines
3. Select the example(s) whose line count is closest to the target
4. If no example is within 20% of target length, use the longest available example
5. Read the corresponding `examples/analyses/phase1/pNsN-diachronic.md`

**NEVER use any file from `examples/analyses/phase2/` as a few-shot example.** Phase 2
files are held-out acceptance test fixtures. Enforce by checking file path — if it
contains `phase2`, skip it.

## Invoking mpi-analyst

Invoke the `mpi-analyst` subagent with this context:

1. The task type: `diachronic`
2. The target transcript (full text)
3. The selected few-shot example(s) labelled clearly:
   ```
   ## Example analysis (p3s2):
   [full content of examples/analyses/phase1/p3s2-diachronic.md]
   ```
4. The instruction: "Now analyse the following transcript in the same style:"
5. The target transcript text

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

**Verifies:** microphenomenograph.AC3.1, microphenomenograph.AC3.2, microphenomenograph.AC3.3, microphenomenograph.AC3.4, microphenomenograph.AC3.5, microphenomenograph.AC3.6 (phase2 exclusion)

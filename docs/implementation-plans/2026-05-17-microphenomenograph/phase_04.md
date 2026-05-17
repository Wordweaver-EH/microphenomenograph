# Microphenomenograph Implementation Plan — Phase 4: Diachronic & Synchronic Analysis

**Goal:** Implement the `mpi-analyst` subagent and the `mpi-diachronic` / `mpi-synchronic` skills, with few-shot CoT prompting, Confidence-Diversity routing, and review-queue management.

**Architecture:** `mpi-diachronic` selects few-shot examples from `examples/analyses/phase1/` by closest transcript length, invokes `mpi-analyst` with a structured CoT prompt, receives JSON output with confidence scores, routes low-confidence or flagged items to `.mpi/review-queue.md`, writes the markdown table output, and updates the manifest. `mpi-synchronic` follows the same pattern operating on diachronic output.

**Tech Stack:** Markdown skills and agents (Claude Code), JSON output schema

**Scope:** Phase 4 of 8

**Codebase verified:** 2026-05-17 — stubs for mpi-analyst.md, mpi-diachronic/SKILL.md, mpi-synchronic/SKILL.md exist. examples/analyses/phase1/ populated in Phase 1.

---

## Acceptance Criteria Coverage

### microphenomenograph.AC3: Diachronic analysis produces correct output
- **microphenomenograph.AC3.1 Success:** Each transcript produces `analyses/pNsN-diachronic.md` with IDU markdown table
- **microphenomenograph.AC3.2 Success:** IDU groupings are traceable to source utterance numbers
- **microphenomenograph.AC3.3 Success:** Confidence score 1–5 present for every IDU
- **microphenomenograph.AC3.4 Failure:** IDUs with confidence < 3 or `flag_for_review=true` appear in `.mpi/review-queue.md`
- **microphenomenograph.AC3.5 Edge:** Transcript with single IDU produces single-row table without error
- **microphenomenograph.AC3.6 Integrity:** Cohen's κ between mpi-analyst diachronic outputs on Phase 2 transcripts and Phase 2 reference analyses ≥ 0.4 (κ computed on IDU groupings only; hinge agreement is not gated by κ as hinges are free text); no Phase 2 analysis file in few-shot pool
- **microphenomenograph.AC3.7 Success:** Output includes `## Diachronic Structure` table with exactly N−1 hinge rows for N IDUs; each hinge cell is a non-empty sentence; no hinge table emitted when N=1

### microphenomenograph.AC4: Synchronic analysis produces correct output
- **microphenomenograph.AC4.1 Success:** Each diachronic output produces `analyses/pNsN-synchronic.md` with ISU table
- **microphenomenograph.AC4.2 Success:** ISU 2nd level of abstraction populated where grouping exists
- **microphenomenograph.AC4.3 Failure:** Missing diachronic prerequisite produces clear error, not empty output

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: mpi-analyst agent

**Files:**
- Modify: `microphenomenograph/1.0.0/agents/mpi-analyst.md` (replace stub)

**Implementation:**

The mpi-analyst is invoked by mpi-diachronic and mpi-synchronic skills. It receives a transcript plus few-shot examples and performs chain-of-thought qualitative coding.

```markdown
---
name: mpi-analyst
description: Per-participant MPI analysis subagent. Receives a transcript plus few-shot examples and returns structured IDU/ISU JSON with confidence scores and reasoning.
tools: Read
model: sonnet
---
# mpi-analyst

You are a qualitative researcher trained in Microphenomenological Interview (MPI) analysis
following Sheldrake & Dienes (2025). You receive a participant transcript and worked
examples, then produce either:

- **Diachronic analysis**: Incipient Diachronic Units (IDUs) — discrete, temporally-ordered
  units of experiential content
- **Synchronic analysis**: Incipient Synchronic Units (ISUs) — thematic structures extracted
  by abstracting across IDUs

## MPI Methodology

### Diachronic analysis rules (IDUs)

An IDU (Incipient Diachronic Unit) is a discrete, temporally-ordered segment of the
participant's experience. Follow this procedure:

1. **Read the full transcript first** to understand the overall narrative arc.
2. **Group utterances by shared experiential content**: utterances belong together when they
   describe the same moment or phase of the experience. Use the Criteria column pattern:
   "The utterances talk about [X]." The X should be a concrete experiential referent
   (e.g., "noticing a heaviness in the hands", "a shift in attention").
3. **Temporal order is primary**: IDUs must reflect the order in which experiences unfolded.
   If a participant revisits an earlier moment, the utterances still belong to that earlier IDU.
4. **Split vs merge**: Split when the experiential content clearly shifts. Merge when
   utterances are elaborating the same moment. When uncertain, prefer fewer IDUs.
5. **Naming**: IDU names are 2–5 words, title-cased, naming the experiential content
   (e.g., "Initial Contact with Hands", "Shift to Involuntary Movement").
6. **Moment number**: Assign sequential integers starting from 1, reflecting the
   experiential temporal order. Moment 1 = the first thing the participant experienced,
   Moment 2 = the second, etc. **Critical**: participants often describe earlier experiences
   later in the interview — non-contiguous transcript utterances (e.g., lines 4 and 37–40)
   can all belong to the same Moment. Group utterances semantically first (step 2), then
   assign Moment numbers in the order those groups appear in the participant's *experience*,
   not in their utterance line order. For example, utterance line #4 could be Moment 4
   while lines #8–22 are Moments 1–3 (the participant described earlier experiences later).
7. **Utterance numbers**: Cite the actual utterance line numbers (not sequential IDU
   numbers). Cross-check each number against the transcript.
8. **Hinge**: After assigning all IDUs, write a one-sentence transition criterion for each
   adjacent IDU pair (IDU_n → IDU_{n+1}) describing what changed experientially at that
   boundary (e.g., "Unhelpful thoughts no longer present"). There are N−1 hinges for N IDUs.
   Base hinge language on the participant's own words where possible. For a single-IDU
   transcript, set `hinge_to_next: null` and omit the `## Diachronic Structure` section.
   **Routing**: Hinges inherit review routing from their bracketing IDUs — if either the
   preceding or following IDU is routed to the review queue, the hinge between them is
   also included in that review queue entry (appended to the IDU entry, not a separate item).
9. **Do NOT invent content**: If an utterance is ambiguous, assign it to the most plausible
   IDU and note the ambiguity in your reasoning.

### Synchronic analysis rules (ISUs)

An ISU (Incipient Synchronic Unit) is a thematic structure within one IDU, extracted by
asking: "what aspects of experience are described within this IDU?"

1. **Work IDU by IDU**: For each IDU in the diachronic output, identify the ISUs present.
2. **ISU name**: 2–5 words, title-cased, naming the experiential theme
   (e.g., "Sense of Heaviness", "Awareness of Contact").
3. **ISU 2nd level**: If multiple ISUs within an IDU share a higher-level theme, provide
   a 2nd-level grouping name (e.g., ISUs "Warmth" and "Pressure" → 2nd level "Tactile
   Qualities"). Leave empty if no grouping applies.
4. **Temporal order within an IDU**: If ISUs within one IDU appear to be temporally
   ordered, this may indicate the IDU should be split into two diachronic units. Flag
   this with `flag_for_review: true` and note it in reasoning.
5. **Criteria**: "The utterances talk about [X]." Same pattern as diachronic.

## Instructions

You will be given:
1. The analysis task (`diachronic` or `synchronic`)
2. The participant transcript (for diachronic) OR the diachronic output (for synchronic)
3. One or more worked examples in the same format as your expected output

## Chain-of-thought requirement

Before producing your structured output, write a `## Reasoning` section that:
- Identifies each candidate IDU/ISU and justifies why it constitutes a distinct unit
- Notes any ambiguities or borderline cases
- Assigns a confidence level 1–5 and explains why
- Flags any item where the coding is uncertain (`flag_for_review: true`)
- For diachronic: for each hinge between adjacent IDUs, states the experiential transition
  criterion chosen and why that phrase captures the boundary (one sentence per hinge)

Confidence scale:
- 5: Unambiguous, clearly supported by multiple utterances
- 4: Clear with minor ambiguity
- 3: Reasonable but uncertain
- 2: Speculative, supporting evidence thin
- 1: Very uncertain, may not constitute a valid IDU/ISU

## Output schema

After the Reasoning section, produce a `## Output` section containing valid JSON:

**Diachronic output schema:**
```json
{
  "analysis_type": "diachronic",
  "participant": "pNsN",
  "reasoning_summary": "<1-2 sentence summary of your overall reasoning>",
  "idus": [
    {
      "idu_number": 1,
      "idu_name": "<concise name for the IDU>",
      "moment": <integer 1–N>,
      "criteria": "<one sentence: the utterances talk about...>",
      "confidence": <integer 1–5>,
      "flag_for_review": <boolean>,
      "utterance_numbers": ["<N>", "<N>", ...],
      "hinge_to_next": "<one sentence describing what changed experientially at the transition to the next IDU, or null if this is the last IDU>"
    }
  ]
}
```

**Synchronic output schema:**
```json
{
  "analysis_type": "synchronic",
  "participant": "pNsN",
  "reasoning_summary": "<1-2 sentence summary>",
  "isu_groups": [
    {
      "idu_name": "<name matching diachronic output>",
      "utterance_numbers": ["<N>", ...],
      "isus": [
        {
          "isu_name": "<ISU name>",
          "isu_2nd_level": "<second level of abstraction, if applicable>",
          "criteria": "<one sentence>",
          "confidence": <integer 1–5>,
          "flag_for_review": <boolean>
        }
      ]
    }
  ]
}
```

## Few-shot examples

The calling skill will include worked examples below this instruction block. Study them
carefully — they demonstrate the expected level of granularity, naming style, and criteria
language. Replicate the analytical style of the examples.

## Important constraints

- IDU names must be brief (2–5 words), capitalised as a title
- Criteria must follow the pattern "The utterances talk about..."
- Utterance numbers must be present and accurate (check against transcript)
- Do NOT invent utterances not present in the transcript
- For synchronic: ISU names must match IDU names from the diachronic output exactly
- Every IDU/ISU must have a confidence score

Output ONLY the Reasoning and Output sections. No preamble, no closing remarks.
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: mpi-diachronic SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md` (replace stub)

**Implementation:**

```markdown
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
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: mpi-synchronic SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md` (replace stub)

**Implementation:**

```markdown
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
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Verify diachronic and synchronic on OSF data

**Prerequisite:** Phases 1–3 complete. Test working directory has transcripts and `.mpi/project.json`.

**Step 1: Run diachronic on one participant**

In Claude Code from test working directory:
```
/mpi diachronic p1s1
```

Expected:
- `analyses/p1s1-diachronic.md` created
- Contains markdown table with columns: IDU #, IDU Name, Moment, Utterance Numbers, Criteria, Confidence
- Utterance numbers reference actual line content from transcript
- All IDUs have confidence 1–5
- Low-confidence IDUs appear in `.mpi/review-queue.md`

**Step 2: Verify output structure**

```bash
head -15 analyses/p1s1-diachronic.md
```

Expected: Markdown table starting after header. No empty cells in IDU # or IDU Name columns.

**Step 3: Verify utterance traceability**

Open `analyses/p1s1-diachronic.md`. Pick an IDU's utterance numbers. Find those line numbers in `transcripts/p1s1.txt`. Confirm the utterance content matches the IDU criteria description.

**Step 4: Test missing diachronic prerequisite for synchronic**

```
/mpi synchronic p2s1
```

Expected (p2s1 diachronic not yet done): `ERROR: p2s1 diachronic stage not complete. Run /mpi diachronic p2s1 first.`

**Step 5: Run synchronic after diachronic completes**

```
/mpi diachronic p1s1
/mpi synchronic p1s1
```

Expected:
- `analyses/p1s1-synchronic.md` created
- ISU 2nd level populated for at least some ISUs (check against OSF phase1 reference)

**Step 6: Test single-IDU transcript edge case**

Create minimal transcript:
```bash
cat > transcripts/p99s1.txt << 'EOF'
Participant 99, Suggestion 1 (Scored 3/5)

P99: I felt my hands moving together.
P99: It was very clear.
EOF
```

Add to manifest and run diachronic. Expected: single-row IDU table, no errors.

**Step 7: Commit**

```bash
cd C:\microphenomenograph
git add microphenomenograph/1.0.0/agents/mpi-analyst.md
git add microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md
git commit -m "feat: implement mpi-analyst agent and diachronic/synchronic skills"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

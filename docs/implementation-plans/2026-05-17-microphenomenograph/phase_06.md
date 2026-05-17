# Microphenomenograph Implementation Plan — Phase 6: Hypothesis Generation

**Goal:** Implement `mpi-hypothesis` skill that translates global synchronic patterns into structured causal research hypotheses using Pearl's causal hierarchy framework.

**Architecture:** `mpi-hypothesis` invokes `mpi-cross-analyst` with the global synchronic output plus the contents of `bookowhy_rev.md` (causal framing context at repo root). The agent produces structured hypotheses with IV, DV, pattern, Pearl ladder rung, confidence, and source IDU/ISU traceability.

**Tech Stack:** Markdown skill (Claude Code), `bookowhy_rev.md` reference document

**Scope:** Phase 6 of 8

**Codebase verified:** 2026-05-17 — stub `skills/mpi-hypothesis/SKILL.md` exists. `bookowhy_rev.md` exists at `C:\microphenomenograph\bookowhy_rev.md`. This file will be referenced at path `../../../bookowhy_rev.md` relative to the plugin, or via absolute path at runtime.

---

## Acceptance Criteria Coverage

### microphenomenograph.AC6: Hypothesis output is structured and causal
- **microphenomenograph.AC6.1 Success:** Each hypothesis names IV, DV, pattern, Pearl ladder rung, and confidence
- **microphenomenograph.AC6.2 Success:** Each hypothesis references the source IDUs/ISUs it was derived from
- **microphenomenograph.AC6.3 Edge:** No cross-participant patterns found produces explicit "no hypothesis" output rather than empty file

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: mpi-hypothesis SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md` (replace stub)

**Implementation:**

```markdown
---
name: mpi-hypothesis
description: Use when running /mpi hypothesis — generates structured causal research hypotheses from global synchronic output using Pearl's causal hierarchy; requires global_synchronic done
user-invocable: false
---
# mpi-hypothesis

Generate structured research hypotheses from the global synchronic analysis. Requires
`global_synchronic: done` in manifest.

## Prerequisites

- `.mpi/project.json` must exist
- `global_synchronic.status == "done"` in manifest
- `analyses/global-synchronic.md` must exist
- `bookowhy_rev.md` must be readable (check: first look at `bookowhy_rev.md` relative
  to the current working directory, then at the repo root)

## Context documents

Read and pass to the cross-analyst:
1. `analyses/global-synchronic.md` — the patterns to hypothesise from
2. `bookowhy_rev.md` — causal framing context (Pearl's causal hierarchy: association,
   intervention, counterfactual)

## Invoking mpi-cross-analyst

Invoke `mpi-cross-analyst` with:
- Task type: `hypothesis_generation`
- Content of `analyses/global-synchronic.md`
- Content of `bookowhy_rev.md` labelled as "Causal framing context:"
- Instruction:
  ```
  Generate causal research hypotheses from the global synchronic patterns above.
  For each cross-participant pattern, produce a structured hypothesis entry.
  If no meaningful cross-participant patterns are present, produce an explicit
  "no hypothesis" output (do not produce an empty file).
  ```

The cross-analyst's hypothesis generation instructions (add to mpi-cross-analyst.md
in a `### Hypothesis generation` section):

```markdown
### Hypothesis generation

Read the global synchronic patterns and the causal framing context. For each pattern
that appears across multiple participants in the same score category:

1. Identify the independent variable (IV) — what varies (e.g., hypnotic suggestibility score)
2. Identify the dependent variable (DV) — what the pattern describes (e.g., felt sense of automaticity)
3. Describe the pattern — the qualitative relationship observed
4. Assign Pearl ladder rung:
   - Rung 1 (Association): "Participants who score high are more likely to report X"
   - Rung 2 (Intervention): "If we intervene to change X, Y would change"
   - Rung 3 (Counterfactual): "Had the participant not received the suggestion, they would not have experienced X"
5. Assign confidence 1–5
6. List source IDUs/ISUs (participant + IDU/ISU name)
7. Suggest a quantitative follow-up test

If no cross-participant patterns exist, write:
```markdown
## No Hypotheses Generated

No consistent cross-participant patterns were identified in the global synchronic analysis.
This may indicate: (a) high individual variation, (b) insufficient participants for pattern
detection, or (c) the patterns are idiosyncratic to individual experiences.

Suggested next step: Review the global synchronic analysis for qualitative themes that
did not meet the cross-participant threshold.
```
```

## Output format

Write `analyses/hypotheses.md`:

```markdown
# MPI Research Hypotheses

Generated from global synchronic analysis of N participants.

## Hypothesis 1: <Short title>

| Field | Value |
|---|---|
| Independent Variable | Hypnotic suggestibility score (0–5) |
| Dependent Variable | <DV description> |
| Pattern | <Description of the qualitative relationship> |
| Pearl Ladder Rung | <1 (Association) / 2 (Intervention) / 3 (Counterfactual)> |
| Confidence | <1–5>/5 |
| Suggested Test | <quantitative follow-up> |

**Source IDUs/ISUs:**
- p1s1: <IDU/ISU name>
- p4s3: <IDU/ISU name>
...

---
[Repeat for each hypothesis]
```

If no patterns: write the "no hypotheses" output above.

## Manifest update

```json
"hypothesis": { "status": "done", "output_path": "analyses/hypotheses.md" }
```

Commit if yolo: `git commit -m "mpi: hypothesis generation"`
```

**Verifies:** microphenomenograph.AC6.1, microphenomenograph.AC6.2, microphenomenograph.AC6.3
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update mpi-cross-analyst with hypothesis generation instructions

**Files:**
- Modify: `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` (add hypothesis section)

**Step 1: Add hypothesis generation section to the agent**

In `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`, after the `### Global synchronic` section, add:

```markdown
### Hypothesis generation

[content as specified in Task 1 above — the full hypothesis generation instructions]
```

**Step 2: Verify and test**

**Prerequisite:** Phases 1–5 complete with `global-synchronic.md` available.

Run:
```
/mpi hypothesis
```

Expected:
- `analyses/hypotheses.md` created
- Each hypothesis has: IV, DV, pattern, Pearl ladder rung (1/2/3), confidence 1–5
- Each hypothesis has source IDUs/ISUs listed with participant IDs
- Manifest updated: `hypothesis.status == "done"`

**Verify structure:**

```bash
python -c "
import re
with open('analyses/hypotheses.md') as f:
    content = f.read()
# Check for required fields in at least one hypothesis
fields = ['Independent Variable', 'Dependent Variable', 'Pattern', 'Pearl Ladder Rung', 'Confidence']
for f in fields:
    assert f in content, f'Missing field: {f}'
# Check for source references
assert 'p' in content.lower() and 's' in content.lower(), 'No participant references found'
print('Structure check passed')
"
```

**Test no-patterns edge case:**

Create a minimal global synchronic with one participant only (patterns won't generalise):
```
/mpi hypothesis
```
Expected: Either produces hypotheses (if patterns found) or the explicit "No Hypotheses Generated" section. Never an empty file.

**Step 3: Commit**

```bash
cd C:\microphenomenograph
git add microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md
git add microphenomenograph/1.0.0/agents/mpi-cross-analyst.md
git commit -m "feat: implement mpi-hypothesis skill and cross-analyst hypothesis generation"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

# Documentation-as-Done Contract — Plan 2 Implementation Plan

**Goal:** Give `mpi-cross-analyst` self-persistence by granting Write + Bash tools, adding a mandatory Persistence section enumerating every LLM-driven cross-analyst substep, and adding claim-level evidence requirements for hypothesis substeps.

**Architecture:** Mirror the mpi-analyst self-persistence pattern (already live). The agent receives its task, produces analysis, writes three artifacts (`<scope>-<stage>.<substep>.{json,md,prompt.json}`), calls `mpi_step.py close`, and returns a one-line status string. The orchestrator reads from disk.

**Tech Stack:** Python 3, stdlib only; markdown agent file edits; pytest for contract tests.

**Scope:** Phase 7 of 13 from original design (Plan 2, phase 1 of 6).

**Codebase verified:** 2026-06-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC6.1: Subagents own their persistence — tools declaration
- **doc-as-done.AC6.1 Success:** `agents/mpi-analyst.md` and `agents/mpi-cross-analyst.md` `tools:` line declares `Read, Write, Bash`.

### doc-as-done.AC6.2: Subagents own their persistence — Persistence subsection
- **doc-as-done.AC6.2 Success:** Both agent prompts contain a "Persistence (mandatory before returning)" subsection naming the exact files to Write and the `mpi_step.py close` invocation to make.

### doc-as-done.AC10.5: Substep granularity — cross-analyst Persistence enumeration
- **doc-as-done.AC10.5 Success:** `agents/mpi-cross-analyst.md` Persistence subsection enumerates all cross-analyst LLM substeps: `generic_diachronic.{idu_similarity_grouping, pattern_identification, cross_iv_contrast}` (per event); `generic_synchronic.{select_generic_idus_of_interest, isu_second_level_grouping}`; `global_synchronic`; `hypothesis.{evidence_extraction, candidate_drafting, weak_evidence_review}`; and `irr_calibration.{independent_analyst, alignment}`. Orchestrator-only substeps (`participant_row_assembly`, `worksheet_assembly`, `irr_calibration.agreement_computation`) are NOT enumerated in the agent file because the agent does not execute them.

### doc-as-done.AC23.1: Hypothesis evidence audit — claim-level structure
- **doc-as-done.AC23.1 Success:** Each candidate in `hypothesis.candidate_drafting` artifacts is an object with a `claims: [...]` array, each claim carrying `{claim_text, supports[], contradicts[], ambiguous[], n_transcripts, n_iv_levels_covered, uncertainty_language, negative_cases[]}`.

### doc-as-done.AC23.2: Hypothesis evidence audit — raw-span anchoring
- **doc-as-done.AC23.2 Success (raw-span anchoring):** Every entry in `supports`/`contradicts`/`ambiguous` carries `raw_span_refs: [{transcript_id, utterance_number, byte_start, byte_end, raw_excerpt}, ...]` (DoD #10 grounding contract). Helper rejects close if any ref doesn't resolve or its `raw_excerpt` doesn't match.

### doc-as-done.AC23.5: Hypothesis evidence audit — sample summary
- **doc-as-done.AC23.5 Success:** Each candidate also carries `sample_summary.by_iv_level: {<level>: <n_transcripts>, ...}` so a reviewer can immediately see the n behind every claim.

### doc-as-done.AC28.5: Cross-stage span ref chain
- **doc-as-done.AC28.5 Success (cross-stage chain):** Generic and global units inherit span refs from their constituent per-transcript units; helper validates the chain is followable from any hypothesis claim back to a specific transcript utterance via the manifest's per-transcript artifacts.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Update `mpi-cross-analyst.md` — tools, anti-fabrication, Persistence, claim-level evidence

**Verifies:** doc-as-done.AC6.1, doc-as-done.AC6.2, doc-as-done.AC10.5, doc-as-done.AC23.1, doc-as-done.AC23.2, doc-as-done.AC23.5, doc-as-done.AC28.5

**Files:**
- Modify: `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` (full rewrite — see below)

**Implementation:**

The file currently has `tools: Read` in the frontmatter and no Persistence section. It needs:
1. `tools: Read, Write, Bash` in frontmatter
2. Anti-fabrication rule section (verbatim text as in mpi-analyst.md)
3. Persistence (mandatory before returning) section enumerating all LLM-driven substeps
4. Claim-level evidence schema for hypothesis substeps (inside the existing `### Hypothesis generation` section)

**Rewrite the file as follows:**

Frontmatter change:
```
tools: Read, Write, Bash
```

Add after the existing content of the `## Your tasks` section (before the end of the file), these two new top-level sections:

**Anti-fabrication rule** (insert before `## Persistence`):
```markdown
## Anti-fabrication rule

If your input artifacts (upstream per-transcript or cross-participant substep outputs) are
missing, empty, or malformed, return `ERROR <reason>` and stop. Never generate placeholder
or synthetic content to make the pipeline appear to progress.
```

**Persistence section** — insert at end of file:
```markdown
## Persistence (mandatory before returning)

After producing your analysis, you MUST persist it yourself before returning. Return ONLY
the one-line status string below — never the analysis content itself. The orchestrator
reads from disk.

On success: `OK <scope> <stage>.<substep> <N>units <K>flagged`
On failure: `ERROR <scope> <stage>.<substep>: <reason>`

### Generic diachronic substeps (per event, scope = `event<E>-cat-<C>`)

Orchestrator-only substeps (`participant_row_assembly`) do NOT produce a prompt artifact
and are closed by the orchestrator, not this agent.

**`generic_diachronic.idu_similarity_grouping`**
```bash
Write analyses/event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.json
Write analyses/event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.md
Write analyses/event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.prompt.json

python scripts/mpi_step.py close \
  --actor mpi-cross-analyst \
  --stage generic_diachronic \
  --substep idu_similarity_grouping \
  --scope event<E>-cat-<C> \
  --artifact analyses/event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.json \
  --artifact analyses/event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.md \
  --prompt-artifact analyses/event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.prompt.json \
  --units-json analyses/event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.json \
  --reason "IDU similarity grouping complete for event<E> cat<C>" \
  --run-dir .
```

**`generic_diachronic.pattern_identification`** — same pattern; artifact names end in `.pattern_identification.*`.

**`generic_diachronic.cross_iv_contrast`** — same pattern; artifact names end in `.cross_iv_contrast.*`.

### Generic synchronic substeps

**`generic_synchronic.select_generic_idus_of_interest`** (per event, scope = `event<E>`)
```bash
Write analyses/event<E>-generic_synchronic.select_generic_idus_of_interest.json
Write analyses/event<E>-generic_synchronic.select_generic_idus_of_interest.md
Write analyses/event<E>-generic_synchronic.select_generic_idus_of_interest.prompt.json

python scripts/mpi_step.py close \
  --actor mpi-cross-analyst \
  --stage generic_synchronic \
  --substep select_generic_idus_of_interest \
  --scope event<E> \
  --artifact analyses/event<E>-generic_synchronic.select_generic_idus_of_interest.json \
  --artifact analyses/event<E>-generic_synchronic.select_generic_idus_of_interest.md \
  --prompt-artifact analyses/event<E>-generic_synchronic.select_generic_idus_of_interest.prompt.json \
  --units-json analyses/event<E>-generic_synchronic.select_generic_idus_of_interest.json \
  --reason "Generic IDU selection complete for event<E>" \
  --run-dir .
```

**`generic_synchronic.isu_second_level_grouping`** (per worksheet, scope = `event<E>-cat-<C>-gidu<G>`)
Same pattern; artifact names end in `.isu_second_level_grouping.*` with scope `event<E>-cat-<C>-gidu<G>`.

### Global synchronic substep

**`global_synchronic`** (per generic-IDU × IV category, scope = `gidu<G>-cat-<C>`)
```bash
Write analyses/gidu<G>-cat-<C>-global_synchronic.json
Write analyses/gidu<G>-cat-<C>-global_synchronic.md
Write analyses/gidu<G>-cat-<C>-global_synchronic.prompt.json

python scripts/mpi_step.py close \
  --actor mpi-cross-analyst \
  --stage global_synchronic \
  --substep global_synchronic \
  --scope gidu<G>-cat-<C> \
  --artifact analyses/gidu<G>-cat-<C>-global_synchronic.json \
  --artifact analyses/gidu<G>-cat-<C>-global_synchronic.md \
  --prompt-artifact analyses/gidu<G>-cat-<C>-global_synchronic.prompt.json \
  --units-json analyses/gidu<G>-cat-<C>-global_synchronic.json \
  --reason "Global synchronic complete for gidu<G> cat<C>" \
  --run-dir .
```

### Hypothesis substeps

**`hypothesis.evidence_extraction`** (per DV focus, scope = `dv-<focus>`)
```bash
Write hypotheses/dv-<focus>.evidence.json
Write hypotheses/dv-<focus>.evidence.md
Write hypotheses/dv-<focus>.evidence.prompt.json

python scripts/mpi_step.py close \
  --actor mpi-cross-analyst \
  --stage hypothesis \
  --substep evidence_extraction \
  --scope dv-<focus> \
  --artifact hypotheses/dv-<focus>.evidence.json \
  --artifact hypotheses/dv-<focus>.evidence.md \
  --prompt-artifact hypotheses/dv-<focus>.evidence.prompt.json \
  --units-json hypotheses/dv-<focus>.evidence.json \
  --reason "Evidence extraction complete for DV focus <focus>" \
  --run-dir .
```

**`hypothesis.candidate_drafting`** — same pattern; artifact names `dv-<focus>.candidates.*`.
Scope: `dv-<focus>`. JSON must include `claims` array per candidate (see AC23.1).

**`hypothesis.weak_evidence_review`** — scope: `global`; artifact names `review_summary.*`.
```bash
python scripts/mpi_step.py close \
  --actor mpi-cross-analyst \
  --stage hypothesis \
  --substep weak_evidence_review \
  --scope global \
  --artifact hypotheses/review_summary.json \
  --artifact hypotheses/review_summary.md \
  --prompt-artifact hypotheses/review_summary.prompt.json \
  --units-json hypotheses/review_summary.json \
  --reason "Weak evidence review complete" \
  --run-dir .
```

### IRR calibration substeps (LLM-driven only)

**`irr_calibration.independent_analyst`** — scope mirrors the primary substep being shadowed
(e.g., `p1s1` for diachronic; `p1s1-idu1` for synchronic). Artifacts written to
`analyses/independent/<scope>-<stage>.<substep>.{json,md,prompt.json}`.

**`irr_calibration.alignment`** — scope: `global`; artifact `analyses/irr_calibration.alignment.*`.

### Span grounding requirement

Every cross-participant analytic unit (GDU pattern, generic ISU, global ISU, hypothesis claim)
MUST carry a non-empty `utterance_refs` array tracing back through the upstream per-transcript
artifacts. For hypothesis claims, every entry in `supports`/`contradicts`/`ambiguous` MUST
carry `raw_span_refs`:
```json
"raw_span_refs": [
  {
    "transcript_id": "p1s1",
    "utterance_number": 3,
    "byte_start": 142,
    "byte_end": 198,
    "raw_excerpt": "I noticed a heaviness in my hands"
  }
]
```
The helper rejects closes with missing or empty `utterance_refs`. There is no "uncited claim" path.
```

**Update the `### Hypothesis generation` section** to add the claim-level output schema. Append after the existing hypothesis generation instructions:

```markdown
#### Claim-level evidence schema (mandatory for `hypothesis.candidate_drafting`)

Each candidate hypothesis in your JSON output MUST follow this shape:
```json
{
  "hypothesis": "<one-sentence hypothesis statement>",
  "claims": [
    {
      "claim_text": "<specific claim being made>",
      "supports": [
        {
          "source_artifact": "<path to upstream artifact>",
          "raw_span_refs": [
            {
              "transcript_id": "p1s1",
              "utterance_number": 12,
              "byte_start": 0,
              "byte_end": 80,
              "raw_excerpt": "<verbatim excerpt from raw transcript>"
            }
          ]
        }
      ],
      "contradicts": [],
      "ambiguous": [],
      "n_transcripts": <int>,
      "n_iv_levels_covered": <int>,
      "uncertainty_language": "associated with|tends to|may|...",
      "negative_cases": [{"transcript_id": "...", "note": "..."}]
    }
  ],
  "sample_summary": {
    "by_iv_level": {"low": <n>, "moderate": <n>, "high": <n>}
  }
}
```
A claim may not close without at least one of `supports` or `contradicts` being non-empty,
OR an explicit `not_applicable` field with rationale at the claim level.

Every hypothesis output MUST carry this verbatim disclaimer as a top-level field:
```json
"disclaimer": "These are generative conjectures inferred from qualitative pattern variation across IV levels in a small sample. They are not causal estimates from a hypothesis test and should not be reported as such."
```
```

**Commit:**
```bash
git add microphenomenograph/1.0.0/agents/mpi-cross-analyst.md
git commit -m "feat: add Write/Bash tools, Persistence, anti-fabrication, claim-level evidence to mpi-cross-analyst"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Contract tests for `mpi-cross-analyst` structure

**Verifies:** doc-as-done.AC6.1, doc-as-done.AC6.2, doc-as-done.AC10.5

**Files:**
- Create: `tests/test_mpi_cross_analyst_contract.py` (unit)

**Implementation:**

Mirror the pattern from `tests/test_mpi_analyst_contract.py`. Read `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` and assert:

**Testing:**

Tests must verify each AC listed above:
- doc-as-done.AC6.1: Parse frontmatter; assert `tools:` line contains `Read`, `Write`, and `Bash` — all three present.
- doc-as-done.AC6.2: Assert file contains a section heading `## Persistence (mandatory before returning)`.
- doc-as-done.AC10.5 (LLM substeps present): Assert the Persistence section text contains each of the following substep names:
  - `generic_diachronic.idu_similarity_grouping`
  - `generic_diachronic.pattern_identification`
  - `generic_diachronic.cross_iv_contrast`
  - `generic_synchronic.select_generic_idus_of_interest`
  - `generic_synchronic.isu_second_level_grouping`
  - `global_synchronic`
  - `hypothesis.evidence_extraction`
  - `hypothesis.candidate_drafting`
  - `hypothesis.weak_evidence_review`
  - `irr_calibration.independent_analyst`
  - `irr_calibration.alignment`
- doc-as-done.AC10.5 (orchestrator substeps absent): Assert the Persistence section does NOT contain:
  - `participant_row_assembly`
  - `worksheet_assembly`
  - `irr_calibration.agreement_computation`
- Anti-fabrication: Assert file contains the string `"Never generate placeholder or synthetic"`.
- Claim-level evidence: Assert file contains `"raw_span_refs"` (the span-grounding requirement for hypothesis claims).
- Disclaimer: Assert file contains `"not causal estimates from a hypothesis test"`.

Follow project testing patterns — look at `tests/test_mpi_analyst_contract.py` for the exact file-loading and assertion approach before writing.

**Verification:**
```
Run: pytest tests/test_mpi_cross_analyst_contract.py -v
Expected: All tests pass
```

**Commit:**
```bash
git add tests/test_mpi_cross_analyst_contract.py
git commit -m "test: add mpi-cross-analyst contract tests (AC6.1, AC6.2, AC10.5)"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Fixture for generic-diachronic substep E2E close

**Verifies:** doc-as-done.AC6.2, doc-as-done.AC10.5, doc-as-done.AC28.5

**Files:**
- Create: `tests/fixtures/cross_analyst/event1-cat-high-generic_diachronic.idu_similarity_grouping.json`
- Create: `tests/fixtures/cross_analyst/event1-cat-high-generic_diachronic.idu_similarity_grouping.md`
- Create: `tests/fixtures/cross_analyst/event1-cat-high-generic_diachronic.idu_similarity_grouping.prompt.json`
- Modify: `tests/test_mpi_cross_analyst_contract.py` — add fixture close test

**Implementation:**

Create minimal but valid fixture files for one generic-diachronic substep close:

The JSON fixture must satisfy the `generic_diachronic.idu_similarity_grouping` schema in `_mpi_schemas.py`. It must include `utterance_refs` on each GDU entry. Examine `_mpi_schemas.py` at `_validate_generic_diachronic_idu_similarity_grouping` (or equivalent) for the required fields before writing the fixture. The prompt.json fixture must conform to the schema_version 2 shape (see `validate_prompt_artifact` in `_mpi_schemas.py`).

**Testing:**

Add a test in `tests/test_mpi_cross_analyst_contract.py` that:
1. Creates a temp git repo (with identity set, hooks disabled)
2. Writes a minimal manifest directly (do not call `mpi_step.py init` — simpler and avoids init side effects)
3. **IMPORTANT — offset registry setup (required for span validation added in Phase 11):** For each `transcript_id` referenced in the fixture's `utterance_refs`, create a minimal `transcripts/raw/<transcript_id>.txt` file and a corresponding `transcripts/offsets/<transcript_id>.json` offset registry in the tempdir. The raw file must contain at least the bytes referenced by the fixture's `utterance_refs` (ensure `byte_start`, `byte_end`, and `raw_excerpt` are consistent). A 10-byte raw file with a single utterance at offsets 0–10 is sufficient; the fixture JSON must reference only those valid offsets.
4. Copies the fixture files into `analyses/` in the temp repo
5. Calls `mpi_step.py close --actor mpi-cross-analyst --stage generic_diachronic --substep idu_similarity_grouping --scope event1-cat-high --artifact ... --prompt-artifact ... --units-json ... --reason "fixture close" --run-dir <tempdir>`
6. Asserts the command exits 0
7. Asserts `audit.jsonl` contains a `git_commit_succeeded` event with matching `close_id`
8. Asserts manifest reflects `generic_diachronic.idu_similarity_grouping: done` for the event scope

Follow the pattern from existing fixture tests in `tests/test_mpi_analyst_contract.py` (the Phase 6 E2E fixture) — look at it first to understand the tempdir setup.

**Verification:**
```
Run: pytest tests/test_mpi_cross_analyst_contract.py -v -k fixture
Expected: All fixture tests pass
```

**Commit:**
```bash
git add tests/fixtures/cross_analyst/
git add tests/test_mpi_cross_analyst_contract.py
git commit -m "test: add Phase 7 generic-diachronic fixture close test for mpi-cross-analyst"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Fixture for hypothesis claim substep E2E close

**Verifies:** doc-as-done.AC23.1, doc-as-done.AC23.2, doc-as-done.AC23.5, doc-as-done.AC28.5

**Files:**
- Create: `tests/fixtures/cross_analyst/dv-automaticity.candidates.json`
- Create: `tests/fixtures/cross_analyst/dv-automaticity.candidates.md`
- Create: `tests/fixtures/cross_analyst/dv-automaticity.candidates.prompt.json`
- Modify: `tests/test_mpi_cross_analyst_contract.py` — add hypothesis fixture close test

**Implementation:**

Create minimal valid fixture for `hypothesis.candidate_drafting`. The JSON must satisfy the claim-level schema:
- Top-level `disclaimer` field with the verbatim text
- At least one candidate with `hypothesis`, `claims` array, `sample_summary.by_iv_level`
- At least one claim entry with `supports` containing at least one entry with `raw_span_refs`
- Each `raw_span_refs` entry with `transcript_id`, `utterance_number`, `byte_start`, `byte_end`, `raw_excerpt`

Use transcript `p1s1` as the source; any non-negative byte range that is self-consistent is acceptable for the fixture (actual offset validation happens against the real offset registry; for this fixture test, focus on schema structure).

**Testing:**

Add a test that:
1. Same tempdir setup as Task 3 — including the offset registry setup. The hypothesis candidate fixture's `raw_span_refs` must reference transcript bytes that actually exist in `transcripts/raw/<transcript_id>.txt` in the tempdir. Use the same minimal raw file from Task 3 (or a shared pytest fixture for it). The `raw_span_refs[].raw_excerpt` must match the bytes at the specified offset in the raw file — consistency is required because Phase 11 Task 5 adds offset validation.
2. Creates `hypotheses/` directory in tempdir
3. Copies `dv-automaticity.candidates.*` into `hypotheses/`
4. Calls `mpi_step.py close --stage hypothesis --substep candidate_drafting --scope dv-automaticity` with all required flags
5. Asserts exit 0
6. Asserts `audit.jsonl` contains a `git_commit_succeeded` event for this close
7. Add a negative test: a fixture missing the `disclaimer` field is rejected at close time (schema validation error). ✓ This can be asserted here.
8. **ORDERING NOTE — `span_excerpt_mismatch` negative test:** A fixture whose `raw_span_refs[].raw_excerpt` does not match the raw bytes should be rejected with `span_excerpt_mismatch` — but this error is emitted by `_validate_utterance_refs`, which is not implemented until Phase 11 Task 5. Do NOT add this negative assertion to this task's test. Instead, add it to `tests/test_e2e_fail_fast.py` in Phase 11 Task 6, alongside the other span-validation negative tests. Leave a `# TODO Phase 11 Task 6: add span_excerpt_mismatch test` comment in `test_mpi_cross_analyst_contract.py` as a placeholder.

**Verification:**
```
Run: pytest tests/test_mpi_cross_analyst_contract.py -v
Expected: All tests pass (both fixture substeps)
```

**Commit:**
```bash
git add tests/fixtures/cross_analyst/
git add tests/test_mpi_cross_analyst_contract.py
git commit -m "test: add Phase 7 hypothesis claim fixture close test (AC23.1, AC23.2, AC23.5)"
```
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

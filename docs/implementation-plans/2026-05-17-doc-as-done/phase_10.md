# Documentation-as-Done Contract — Plan 2 Implementation Plan

**Goal:** Add the verbatim anti-fabrication rule to every generative SKILL.md file (mpi-diachronic, mpi-synchronic, mpi-generic-diachronic, mpi-generic-synchronic, mpi-global-synchronic, mpi-hypothesis) and verify both agent files carry it. One-liner grep is the acceptance test.

**Architecture:** Text append to 6 SKILL.md files; no code changes. mpi-analyst.md already has the rule (Phase 6). mpi-cross-analyst.md gets it in Phase 7. This phase handles the 6 generative skills.

**Tech Stack:** Markdown edits; grep verification.

**Scope:** Phase 10 of 13 from original design (Plan 2, phase 3 of 6). Depends on Phase 9 (all Closure sections must exist before anti-fabrication sweep).

**Codebase verified:** 2026-06-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC5.3: Anti-fabrication rule in all generative files
- **doc-as-done.AC5.3 Success:** Every generative SKILL.md and both agent prompts contain the verbatim anti-fabrication rule.

### doc-as-done.AC5.4: Anti-fabrication behaviour
- **doc-as-done.AC5.4 Failure (anti-fabrication):** When given empty or missing upstream input, a generative skill returns an `ERROR` rather than producing synthetic content. (Verified at the agent prompt level; behavioural verification deferred to LLM-in-the-loop testing outside the E2E test.)

---

<!-- START_TASK_1 -->
### Task 1: Add anti-fabrication rule to all 6 generative SKILL.md files

**Verifies:** doc-as-done.AC5.3

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`

**Implementation:**

For each of the 6 files, append the following section immediately BEFORE the `## Closure (mandatory)` section (which was added in Phase 8/9). This keeps the anti-fabrication rule visible before the closure instructions.

Verbatim text to insert (do NOT paraphrase):
```markdown
## Anti-fabrication rule

If your input artifacts (transcripts, upstream substep outputs) are missing, empty, or
malformed, return `ERROR <reason>` and stop. Never generate placeholder or synthetic
content to make the pipeline appear to progress.
```

**Note on mpi-diachronic and mpi-synchronic:** These files already have Closure sections from Phase 8. Read each file first to find the exact position of `## Closure (mandatory)` and insert the anti-fabrication section before it.

**Note on cross-participant skills:** These files had their Closure sections added in Phase 9 (Task 2, 3). Same approach — read to find the position, insert before.

**Pre-check:** Before editing each file, confirm it does NOT already contain the string `"Never generate placeholder or synthetic"`. If it does (shouldn't happen, but check), skip that file.

**Commit:**
```bash
git add microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md
git commit -m "feat: add anti-fabrication rule to all 6 generative SKILL.md files (AC5.3)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Verify anti-fabrication coverage across all expected files

**Verifies:** doc-as-done.AC5.3

**Files:**
- No code changes — verification only

**Implementation:**

Run the acceptance-test grep:
```bash
grep -rl "Never generate placeholder" \
  microphenomenograph/1.0.0/skills/ \
  microphenomenograph/1.0.0/agents/
```

**Expected output must include exactly these 8 files:**
```
microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md
microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md
microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md
microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md
microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md
microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md
microphenomenograph/1.0.0/agents/mpi-analyst.md
microphenomenograph/1.0.0/agents/mpi-cross-analyst.md
```

If any file is missing from the output, add the anti-fabrication rule to it now. If any extra unexpected file appears, investigate — it may indicate a copy-paste error or a file that should not have the rule.

**Also verify the rule is verbatim in each file:**
```bash
grep -A2 "Never generate placeholder" microphenomenograph/1.0.0/agents/mpi-analyst.md
```
Expected: `"Never generate placeholder or synthetic content to make the pipeline appear to progress."`

**Commit:** (only if corrections were needed from the grep check)
```bash
git add <any corrected files>
git commit -m "fix: ensure anti-fabrication rule verbatim in all generative files"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Pytest assertion for anti-fabrication coverage

**Verifies:** doc-as-done.AC5.3

**Files:**
- Modify: `tests/test_plugin_structure.py`

**Implementation:**

Extend `tests/test_plugin_structure.py` with a test that:
1. Reads all SKILL.md files under `microphenomenograph/1.0.0/skills/` whose names are in the generative set: `mpi-diachronic`, `mpi-synchronic`, `mpi-generic-diachronic`, `mpi-generic-synchronic`, `mpi-global-synchronic`, `mpi-hypothesis`
2. For each, asserts the file content contains `"Never generate placeholder or synthetic"`
3. Reads `microphenomenograph/1.0.0/agents/mpi-analyst.md` and asserts the same
4. Reads `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` and asserts the same
5. Assert that non-generative, orchestrator-run skills (`mpi-init`, `mpi-transcript-prep`, `mpi-status`) do NOT contain `"Never generate placeholder or synthetic"` — they are orchestrator-run and must not carry the LLM anti-fabrication rule.
6. Do NOT assert either way for `mpi-irr` — it dispatches fresh agent instances rather than being a generative skill itself; its irr_calibration substeps (independent_analyst, alignment) are LLM-driven but the rule is authored into the subagent, not into this orchestration-level skill.

Follow the existing test patterns in `test_plugin_structure.py`.

**Verification:**
```
Run: pytest tests/test_plugin_structure.py -v -k fabrication
Expected: All anti-fabrication tests pass
```

**Commit:**
```bash
git add tests/test_plugin_structure.py
git commit -m "test: assert anti-fabrication rule present in all generative files (AC5.3)"
```
<!-- END_TASK_3 -->

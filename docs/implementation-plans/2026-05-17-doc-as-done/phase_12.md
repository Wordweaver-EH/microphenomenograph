# Documentation-as-Done Contract — Plan 2 Implementation Plan

**Goal:** Update both CLAUDE.md files to reference the Documentation-as-Done contract, and reconcile existing tests that hardcode the old stage-level write contracts. Ensure `pytest` from repo root is green after all Plan 2 phases land.

**Architecture:** Documentation edits + test file updates. No new production code. The existing test suite encodes some legacy assumptions (old manifest schema, old skill count, stage-level rather than substep-level assertions) that must be retargeted.

**Tech Stack:** Markdown, Python; pytest.

**Scope:** Phase 12 of 13 from original design (Plan 2, phase 5 of 6). Depends on all preceding phases (1–11) being implemented and tests passing.

**Codebase verified:** 2026-06-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC9.1: Plugin CLAUDE.md reflects the contract
- **doc-as-done.AC9.1 Success:** `microphenomenograph/1.0.0/CLAUDE.md` contains a "Documentation-as-Done Contract" section pointing to `scripts/mpi_step.py`, documents the substep DAG, and removes the old per-stage output-path table and reasoning.log format note.

### doc-as-done.AC9.2: Top-level CLAUDE.md references the contract
- **doc-as-done.AC9.2 Success:** Top-level `C:\microphenomenograph\CLAUDE.md` references the contract in its "Plugin contracts" section in one sentence.

---

<!-- START_TASK_1 -->
### Task 1: Update `microphenomenograph/1.0.0/CLAUDE.md`

**Verifies:** doc-as-done.AC9.1

**Files:**
- Modify: `microphenomenograph/1.0.0/CLAUDE.md`

**Implementation:**

Read the current file first. The existing file already has a "Documentation-as-Done contract" section (added in Plan 1). The task is to:

1. **Update the "Implementation status" note** in the header: Change "Plan 2 (Phases 7, 9–13) — NOT YET IMPLEMENTED" to "Plan 2 (Phases 7, 9–13) — LANDED" once Plan 2 phases are complete. *(Defer this final status update to after Phase 13 is implemented — do it in the same commit as Phase 13 or this phase's commit, whichever comes last.)*

2. **Add the substep DAG table** if not already present. Check whether the existing "Documentation-as-Done contract" section already contains a substep DAG table. If not, add after the phased close protocol block:

```markdown
## Substep DAG

| Stage | Substeps | Iteration | Actor |
|---|---|---|---|
| `init` | `scan_transcripts` → `propose_study_config` → `confirm_study_config` | one-shot | orchestrator (LLM optional on `propose_study_config`) |
| `transcript_prep` | `hash_raw` → `normalize` → `register_offsets` | per transcript | orchestrator |
| `diachronic` | `criteria_grouping` → `criteria_revision` → `idu_naming_ordering` | per transcript | mpi-analyst (LLM) |
| `synchronic` | `theme_grouping_within_idu` → `isu_naming` → `isu_second_level_grouping` | per transcript × per IDU | mpi-analyst (LLM) |
| `generic_diachronic` | `participant_row_assembly` (orch) → `idu_similarity_grouping` (LLM) → `pattern_identification` (LLM) → `cross_iv_contrast` (LLM) | per (event × IV category) | mpi-cross-analyst |
| `generic_synchronic` | `select_generic_idus_of_interest` (LLM) → `worksheet_assembly` (orch) → `isu_second_level_grouping` (LLM) | per (event × IV category × generic-IDU) | mpi-cross-analyst |
| `global_synchronic` | `global_synchronic` | per (generic-IDU × IV category) | mpi-cross-analyst (LLM) |
| `hypothesis` | `evidence_extraction` → `candidate_drafting` → `weak_evidence_review` | first two per DV focus; review global | mpi-cross-analyst (LLM) |
| `irr_calibration` | `independent_analyst` (LLM) → `alignment` (LLM) → `agreement_computation` (orch) | after calibration transcript's diachronic + synchronic | mpi-cross-analyst |

**Prerequisite gates** (enforced by `mpi_step.py close`):
- `generic_diachronic.*`: all transcripts for the event must have all diachronic + synchronic substeps `done`, with no pending split/merge flags
- `generic_synchronic.*`: matching `generic_diachronic.*` must be `done`
- `global_synchronic.*`: all matching `generic_synchronic.*` must be `done`
- `hypothesis.*`: all `generic_diachronic.*`, `generic_synchronic.*`, `global_synchronic.*` must be `done`
```

3. **Delete the old per-stage output-path table and reasoning.log format note** if they exist outside the Closure sections. Search for any table with columns like `analyses/pNsN-{stage}.md` that appears in prose (not inside a code block of a Closure section) and remove it. Search for any prose describing the `reasoning.log` line format (e.g., `[<ts>] pNsN stage: ...`) outside of the helper CLI section and remove it — `mpi_step.py render` owns this now.

4. **Update the implementation status date** at the top of the file: `_Last updated: <today's date>`.

**Commit:**
```bash
git add microphenomenograph/1.0.0/CLAUDE.md
git commit -m "docs: update plugin CLAUDE.md with substep DAG and remove legacy output-path table (AC9.1)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update top-level `CLAUDE.md` plugin contracts section

**Verifies:** doc-as-done.AC9.2

**Files:**
- Modify: `C:\microphenomenograph\CLAUDE.md` (top-level repo CLAUDE.md)

**Implementation:**

Read the current file. It currently has a "Plugin contracts" section. Add or update one sentence under that section to reference the Documentation-as-Done contract:

Locate the paragraph starting with `**Documentation-as-Done contract.**` It already exists (from Plan 1). Update it to reflect Plan 2 landing by changing:

```
**Implementation status (Plan 1).** Phases 1–6 are landed...
```

to:

```
**Implementation status (Plan 2).** All 13 phases landed (Plans 1 + 2)...
```

*(This final status flip should be done in this commit only after all Phase 13 tests pass. If Phase 13 is not yet complete when this phase is executed, defer the status flip to Phase 13's commit.)*

Ensure the sentence describing `mpi_step.py` in the "Plugin contracts" section covers both mpi-analyst and mpi-cross-analyst self-persistence.

Update the `_Last updated` date at the top of the file.

**Commit:**
```bash
git add CLAUDE.md
git commit -m "docs: update top-level CLAUDE.md plugin contracts section (AC9.2)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Reconcile `test_plugin_structure.py`

**Verifies:** (all tests pass after reconciliation)

**Files:**
- Modify: `tests/test_plugin_structure.py`

**Implementation:**

Read the current file. Key areas likely to need updating:

1. **Delete `mpi-kappa/` skill directory first.** The `mpi-kappa/` directory still exists on disk (Phase 9 created `mpi-irr/` but did not delete `mpi-kappa/`). Delete it NOW in this task so Phase 12 Task 5's green-suite check works:
   ```bash
   git rm -r microphenomenograph/1.0.0/skills/mpi-kappa/
   git commit -m "chore: remove mpi-kappa/ skill directory (replaced by mpi-irr/, Phase 9)"
   ```
   This must happen BEFORE editing `test_plugin_structure.py` so filesystem and test list are consistent.

2. **Skill count assertion** (`TestAC1_2_SkillsDiscoverable`): After deleting `mpi-kappa/`, update the `EXPECTED_SKILLS` list:
   - Remove: `"mpi-kappa"`
   - Add: `"mpi-irr"`

3. **AC3.6 assertion** (`TestAC3_6_Phase2ExclusionInDiachronicSkill` or similar): If this test asserts that diachronic/synchronic SKILLs do NOT mention "Phase 2" or "phases", check whether it still passes after adding the Closure sections. If it fails, update the assertion to target the specific old content that should be absent.

4. **AC7.3 kappa test** (`TestAC7_3_KappaWarning...`): This references `mpi-kappa`. After the rename to `mpi-irr`, update to reference `mpi-irr` and `irr.py` instead.

Run `pytest tests/test_plugin_structure.py -v` before and after editing. Fix only what fails — do not rewrite passing tests.

**Verification:**
```
Run: pytest tests/test_plugin_structure.py -v
Expected: All tests pass
```

**Commit:**
```bash
git add tests/test_plugin_structure.py
git commit -m "test: reconcile test_plugin_structure.py for Plan 2 (mpi-irr replaces mpi-kappa, updated skill list)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Reconcile `test_verify_mpi_init.py` and `test_mpi_orchestration.py`

**Verifies:** (all tests pass after reconciliation)

**Files:**
- Modify: `tests/test_verify_mpi_init.py`
- Modify: `tests/test_mpi_orchestration.py`

**Implementation:**

Read both files fully before editing.

**`test_verify_mpi_init.py`:**

This file tests init schema and manifest structure. Likely issues:
- The manifest schema in mpi-init SKILL.md (and thus these tests) uses the legacy format (no `substeps`, no `study` block). After Plan 2, the contract manifest schema has `stages.<stage>.substeps` entries.
- If the test asserts specific manifest keys that are now the legacy schema, update the assertions to match the new substep-aware schema in `_mpi_schemas.py`.
- Read `_mpi_schemas.py` to find the current manifest shape before editing.
- Do NOT rewrite the test to test things already covered elsewhere; only update assertions that now fail due to schema changes.

**`test_mpi_orchestration.py`:**

This file tests orchestration spec: stage ordering, commit format, reasoning log format, yolo mode. Key issues:
- **Commit format**: Tests assert `"mpi: pNsN {stage} analysis"` format. The new format (from the helper) is `"mpi: <actor> <stage>.<substep> <scope> (<N>units <K>flagged)"`. Update assertions to match the new format.
- **Reasoning log format**: Tests assert `"[ISO timestamp] pNsN stage: ..."` format. The new format is `"[<ts>] <actor> <participant> <stage>: <reason>. <N> units, <K> flagged. commit=<sha7>"`. Update assertions to the canonical format from the helper's `render` verb.
- **Yolo mode parallelism**: The spec in this file may assert that yolo runs stages in parallel fan-out. The new contract (Plan 2) requires STRICTLY SEQUENTIAL execution. Update any parallelism assertions to sequential-only assertions.
- **Stage-level vs substep-level**: Any assertion that a stage has `status: "done"` without substeps may need to be updated to check `substeps.<substep>.status`.

Run `pytest tests/test_mpi_orchestration.py -v` before editing to see exactly which tests fail. Fix only the failing assertions.

**Verify all existing logic tests still pass:**
```
Run: pytest tests/test_mpi_synchronic_logic.py tests/test_cross_participant_analysis.py tests/test_hypothesis_generation.py tests/test_transcript_prep.py -v
Expected: All pass (these tests should not need changes — they test logic, not write contracts)
```

**Commit:**
```bash
git add tests/test_verify_mpi_init.py tests/test_mpi_orchestration.py
git commit -m "test: reconcile init and orchestration tests for substep-level contract and sequential yolo (AC9.1, AC9.2)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Full test suite green check

**Verifies:** doc-as-done.AC9.1, doc-as-done.AC9.2 (and all preceding)

**Files:**
- No changes — verification only

**Implementation:**

```bash
pytest --tb=short -q
```

All tests must pass. If any fail:
- For failures in `test_mpi_synchronic_logic.py`, `test_cross_participant_analysis.py`, `test_hypothesis_generation.py`, or `test_transcript_prep.py`: these should NOT need changes after Plan 2. If they fail, investigate — it may indicate an unintended change to a production file.
- For failures in the new E2E tests (Phase 11): debug the fixture or test logic.
- For failures in structural tests (Phase 10): may need fixture corrections.

Do NOT suppress or skip failing tests. Fix the underlying issue.

**Commit:** (if any final fixups needed)
```bash
git add <fixed files>
git commit -m "fix: final test reconciliation for Plan 2 full suite pass"
```
<!-- END_TASK_5 -->

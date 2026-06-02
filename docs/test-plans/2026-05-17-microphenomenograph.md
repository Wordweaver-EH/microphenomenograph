# Human Test Plan — microphenomenograph

Generated from test-analyst pass on 2026-05-17.

Automated test coverage: 34 tests in `tests/`, 5 in `microphenomenograph/1.0.0/scripts/test_kappa.py`.
Criteria requiring LLM execution or interactive CLI are listed here as manual steps.

---

## Phase 1: Plugin Discovery & Initialisation

### Prerequisites
- Claude Code CLI installed
- `microphenomenograph` plugin installed: `claude code plugin install C:\microphenomenograph\microphenomenograph\1.0.0`
- OSF transcripts in `transcripts/` directory of a test working directory

### Test 1.1 — Plugin installs and `/mpi` is discoverable

1. Open Claude Code in a fresh working directory.
2. Run: `/mpi`
3. **Expected:** Usage block listing subcommands (init, status, transcript-prep, diachronic, synchronic, generic-diachronic, generic-synchronic, global-synchronic, hypothesis, kappa, all). No error.

### Test 1.2 — Unknown subcommand prints usage (AC1.3)

1. Run: `/mpi foobar`
2. **Expected:** Message containing `Unknown subcommand: 'foobar'` and the list of valid subcommands.

### Test 1.3 — `/mpi init` parses all OSF transcripts (AC2.1, AC2.2)

1. Create test directory with all OSF transcripts in `transcripts/`.
2. Run: `/mpi init`
3. **Expected:**
   - `.mpi/project.json` created.
   - 39 participants listed.
   - `p1s1`: score=4, category=high, all stages pending.
   - `p6s1`: score parsed correctly (no-comma header variant).
   - `p11s1`: score=0, category=low (annotated header variant).
   - Report: "Initialised 39 participants."

### Test 1.4 — Malformed header produces named error, not silent failure (AC2.3)

1. Create `transcripts/p99s1.txt` with first line `Bad header format`.
2. Run: `/mpi init`
3. **Expected:** Error message: `ERROR: transcripts/p99s1.txt: invalid header format`. Manifest does NOT contain `p99s1`. All valid participants still processed.

### Test 1.5 — Re-run preserves done stages (AC2.4)

1. After init, manually set `p1s1.stages.diachronic.status = "done"` in `.mpi/project.json`.
2. Run: `/mpi init` again.
3. **Expected:** `p1s1` diachronic stage remains `done`. Report mentions preserved stages.

### Test 1.6 — `/mpi status` renders progress table (AC1.2)

1. Run: `/mpi status`
2. **Expected:** Markdown table with ✓/⧖/✗ symbols, one row per participant. Cross-participant stages section follows. Summary line with counts.

---

## Phase 2: Diachronic Analysis

### Prerequisites
- `/mpi init` complete with ≥1 transcript.
- `/mpi transcript-prep p1s1` complete (or run it now).

### Test 2.1 — Transcript prep normalises a transcript (AC3.2)

1. Run: `/mpi transcript-prep p1s1`
2. **Expected:**
   - `analyses/p1s1-prep.md` created.
   - Utterances numbered (U001, U002, …).
   - Participant speech separated from researcher speech.
   - Manifest `p1s1.stages.transcript_prep.status = "done"`.

### Test 2.2 — Diachronic produces IDUs with confidence scores (AC3.1)

1. Run: `/mpi diachronic p1s1`
2. **Expected:**
   - `analyses/p1s1-diachronic.md` created.
   - At least 3 IDUs listed.
   - Each IDU has: name, criteria, moment range, confidence (1–5).
   - Hinge transitions table present.
   - Manifest updated to done.

### Test 2.3 — Low-confidence IDU routed to review queue (AC3.3)

1. If `p1s1-diachronic.md` has any IDU with confidence < 3 or `flag_for_review: true`, check `.mpi/review-queue.md`.
2. **Expected:** That IDU appears in review queue with participant key and stage.
3. If no low-confidence IDUs in p1s1, use a participant known to have uncertain IDUs (check OSF data).

### Test 2.4 — Single-IDU transcript handled gracefully (AC3.4)

1. Create a minimal transcript with only one clear temporal moment.
2. Run diachronic on it.
3. **Expected:** One IDU produced. No crash. Hinge table may be empty or note no transitions.

### Test 2.5 — Phase 2 transcripts never appear as few-shot examples (AC3.5, AC3.6)

1. Open `microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md` and `mpi-synchronic/SKILL.md`.
2. Search for any reference to phase2 transcript files (p8–p13 range).
3. **Expected:** No phase2 participant IDs in few-shot examples. Only phase1 participants (p1–p7) used as examples.

---

## Phase 3: Synchronic & Cross-Participant

### Test 3.1 — Synchronic produces ISU groups (AC4.1)

1. Run: `/mpi synchronic p1s1`
2. **Expected:**
   - `analyses/p1s1-synchronic.md` created.
   - ISU groups present, each with ISU name, criteria, utterance references.
   - Manifest updated.

### Test 3.2 — Generic diachronic warns on incomplete participants (AC5.3)

1. Ensure at least one participant has `diachronic: pending`.
2. Run: `/mpi generic-diachronic`
3. **Expected:** Warning listing incomplete participants. Does NOT crash. Asks user to proceed or wait.

### Test 3.3 — Generic diachronic groups IDUs by score category (AC5.1)

1. Have ≥3 participants with diachronic done across multiple score categories.
2. Proceed past the completeness warning (or have all complete).
3. **Expected:** `analyses/generic-diachronic.md` contains `### High Response Group`, `### Moderate Response Group`, `### Low Response Group`. Each pattern row cites participant key and suggestion.

### Test 3.4 — Global synchronic cites source participant and suggestion for every row (AC5.2)

1. Run full pipeline through global-synchronic.
2. Run: `grep -c "|" analyses/global-synchronic.md`
3. Open `analyses/global-synchronic.md`.
4. **Expected:** Every data row (non-header) has non-empty Source Participant and Source Suggestion columns.

---

## Phase 4: Yolo End-to-End

### Test 4.1 — `/mpi all --yolo` runs full pipeline unattended (AC8.1)

1. In a clean directory with all transcripts:
2. Run: `/mpi init && /mpi all --yolo`
3. **Expected:**
   - All per-participant stages complete without human prompts.
   - All cross-participant stages complete.
   - Manifest shows all stages done.
   - One git commit per stage (e.g., `mpi: p1s1 diachronic`, `mpi: generic-diachronic`).

### Test 4.2 — Parallel fan-out in yolo mode (AC8.2)

1. With ≥4 participants pending diachronic, run `/mpi diachronic --yolo`.
2. **Expected:** Multiple participants processed concurrently (check timing or log output for parallel dispatch).

### Test 4.3 — Resume skips done stages (AC8.4)

1. Run pipeline partway; kill it midway.
2. Run: `/mpi all --yolo` again.
3. **Expected:** Already-done stages skipped. Only pending stages executed. Manifest preserved.

---

## Phase 5: Interactive / Assisted Mode

### Test 5.1 — Assisted mode prompts before each stage (AC8.3)

1. Run: `/mpi all` (without --yolo)
2. **Expected:** Before each participant-stage, Claude asks for confirmation. Proceeding continues; declining skips.

### Test 5.2 — `/mpi status` after partial run shows mixed symbols (AC8.5)

1. After completing some but not all stages, run: `/mpi status`
2. **Expected:** ✓ for done stages, ⧖ for pending, ✗ for flagged. No crashes.

### Test 5.3 — Hypothesis output follows Pearl causal ladder (AC9.1)

1. Run: `/mpi hypothesis` after generic-synchronic is done.
2. **Expected:**
   - `analyses/hypothesis.md` created.
   - Contains Rung 1 (association), Rung 2 (intervention), Rung 3 (counterfactual) hypotheses.
   - Each hypothesis cites source IDU or ISU.

### Test 5.4 — Hypothesis suggests quantitative follow-up (AC9.2)

1. Inspect `analyses/hypothesis.md`.
2. **Expected:** At least one quantitative follow-up suggestion referencing a measurable construct from the synchronic analysis.

---

## Phase 6: End-to-End OSF Reproduction

### Test 6.1 — Full pipeline on all OSF phase2 transcripts

1. Place all 39 OSF transcripts in `transcripts/`.
2. Run `/mpi all --yolo`.
3. **Expected:**
   - 39 diachronic outputs in `analyses/`.
   - 39 synchronic outputs in `analyses/`.
   - `generic-diachronic.md`, `generic-synchronic.md`, `global-synchronic.md` all present.
   - `hypothesis.md` present.
   - All manifest stages done.

### Test 6.2 — Cohen's κ ≥ 0.61 on reference OSF annotations (AC7.1)

1. Place OSF annotation CSVs in accessible directory.
2. Run: `python microphenomenograph/1.0.0/scripts/kappa.py <dir1> <dir2>`
3. **Expected:**
   - Diachronic κ ≈ 0.82 (±0.01).
   - Synchronic κ ≈ 0.60 (±0.01).
   - Exit code 0 if both ≥ 0.61, exit code 2 if synchronic < threshold (expected for reference data).

---

## Acceptance Criteria Traceability

| AC | Description | Coverage |
|---|---|---|
| AC1.1 | Plugin installs, commands discoverable | `test_plugin_structure.py::TestAC1_1` |
| AC1.2 | Skills discoverable with valid frontmatter | `test_plugin_structure.py::TestAC1_2` |
| AC1.3 | Unknown subcommand → usage message | `test_plugin_structure.py::TestAC1_3` |
| AC2.1 | Header parsing (standard format) | `test_verify_mpi_init.py` |
| AC2.2 | All OSF transcripts → valid manifest | Manual: Test 1.3 |
| AC2.3 | Malformed header → named error | `test_verify_mpi_init.py` + Manual: Test 1.4 |
| AC2.4 | Re-run preserves done stages | `test_verify_mpi_init.py` + Manual: Test 1.5 |
| AC3.1 | Diachronic IDUs with confidence | Manual: Test 2.2 |
| AC3.2 | Transcript prep normalises utterances | `test_transcript_prep.py` |
| AC3.3 | Low-confidence → review queue | Manual: Test 2.3 |
| AC3.4 | Single-IDU transcript graceful | Manual: Test 2.4 |
| AC3.5 | Phase2 excluded from few-shot | `test_plugin_structure.py::TestAC3_6_ZeroShotPurity` |
| AC3.6 | Phase2 exclusion language in skills | `test_plugin_structure.py::TestAC3_6_ZeroShotPurity` |
| AC4.1 | Synchronic ISU groups produced | `test_mpi_synchronic_logic.py` |
| AC4.2 | ISU flattening across IDU groups | Manual: Test 3.1 qualitative check |
| AC5.1 | Generic diachronic groups by score category | `test_cross_participant_analysis.py` |
| AC5.2 | Global synchronic cites source per row | `test_cross_participant_analysis.py` + Manual: Test 3.4 |
| AC5.3 | Warning on incomplete participants | `test_cross_participant_analysis.py` + Manual: Test 3.2 |
| AC6.1 | Hypothesis on Pearl ladder | Manual: Test 5.3 |
| AC6.2 | Quantitative follow-up suggestion | Manual: Test 5.4 |
| AC7.1 | κ ≥ 0.61 on OSF data | `scripts/test_kappa.py` + Manual: Test 6.2 |
| AC7.2 | kappa skill invokes script correctly | `test_plugin_structure.py::TestAC7_3` (threshold) |
| AC7.3 | κ < 0.61 → WARNING + exit 2 | `test_plugin_structure.py::TestAC7_3` |
| AC8.1 | `/mpi all --yolo` runs unattended | Manual: Test 4.1 |
| AC8.2 | Parallel fan-out in yolo mode | Manual: Test 4.2 |
| AC8.3 | Assisted mode prompts per stage | Manual: Test 5.1 |
| AC8.4 | Resume skips done stages | `test_mpi_orchestration.py` + Manual: Test 4.3 |
| AC8.5 | Status table after partial run | Manual: Test 5.2 |
| AC9.1 | Hypothesis Pearl rung assignment | `test_hypothesis_generation.py` + Manual: Test 5.3 |
| AC9.2 | Hypothesis quantitative follow-up | Manual: Test 5.4 |

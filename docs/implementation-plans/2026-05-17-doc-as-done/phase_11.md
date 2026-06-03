# Documentation-as-Done Contract — Plan 2 Implementation Plan

**Goal:** Add a deterministic E2E pipeline test that drives the full substep DAG against recorded fixture responses and asserts every artifact, audit event, manifest entry, and git commit lands as expected. Add a companion fail-fast test for negative paths.

**Architecture:** Recorded fixture responses (JSON + MD + prompt.json per substep per scope) are fed directly to `mpi_step.py close` — no LLM calls during tests. The driver walks the substep DAG in the same order the orchestrator would, calling `mpi_step.py close` for each substep. Assertions are structural (file exists, non-empty, schema-valid, manifest updated, audit event present, git commit exists).

**Tech Stack:** Python 3, stdlib only; pytest; `mpi_step.py` via subprocess; `_mpi_schemas.py` for validation.

**Scope:** Phase 11 of 13 from original design (Plan 2, phase 4 of 6). Depends on all of Phases 1–10.

**Codebase verified:** 2026-06-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC1.1–AC1.3, AC1.5: Phased close protocol and done definition
- **doc-as-done.AC1.1 Success:** A successful `mpi_step.py close` emits the full event sequence in `.mpi/audit.jsonl`: `close_attempted` → `artifacts_validated` → `audit_appended` → `manifest_replaced` → `git_commit_succeeded`. All five share the same `close_id` (UUID4). The `git_commit_succeeded` event records `mpi.git_commit_sha`.
- **doc-as-done.AC1.2 Failure (commit):** If `git commit` fails, helper emits `git_commit_failed` followed by `manifest_rolled_back`.
- **doc-as-done.AC1.3 Failure (audit append):** If audit append fails before manifest mutation, manifest stays untouched.
- **doc-as-done.AC1.5 Success (done definition):** A substep is `done` iff (a) manifest status is `done`, (b) `audit.jsonl` has matching `git_commit_succeeded` event, AND (c) that commit's tree contains the manifest entry.

### doc-as-done.AC7.2–AC7.3: Audit schema and trace_id consistency
- **doc-as-done.AC7.2 Success:** Audit events follow the documented schema with all required fields.
- **doc-as-done.AC7.3 Success:** Within a run, `trace_id` is constant; `event_id`s are globally unique.

### doc-as-done.AC8.1–AC8.3: E2E test coverage
- **doc-as-done.AC8.1 Success:** `tests/test_e2e_pipeline.py` runs against a tiny fixture corpus (2 participants × 2 suggestions) and asserts every expected `analyses/pNsN-<stage>.{md,json}` exists and is non-empty.
- **doc-as-done.AC8.2 Success:** Same test asserts manifest reflects every closure at substep granularity with matching status and output_path; `audit.jsonl` validates; `git log --oneline` shows one commit per substep with canonical format.
- **doc-as-done.AC8.3 Failure-path:** `tests/test_e2e_fail_fast.py` feeds malformed units and asserts helper exits non-zero, manifest unchanged, no git commit, no half-written artifact.

### doc-as-done.AC11.4: Prompt artifact path in audit event
- **doc-as-done.AC11.4 Success:** Each audit event for an LLM-invoking substep carries `mpi.prompt_artifact_path` pointing at the on-disk prompt.json.

### doc-as-done.AC20.6–AC20.7: Run lease and substep reservation
- **doc-as-done.AC20.6 Failure:** Second concurrent `/mpi all` errors `run_lease_held` immediately.
- **doc-as-done.AC20.7 Failure:** Second close for same `(stage, substep, scope)` errors `substep_reservation_held`.

### doc-as-done.AC30.1–AC30.3: Cascade reset moves artifacts aside
- **doc-as-done.AC30.1 Success:** Cascade reset moves affected artifacts to `analyses/_superseded/<close_id>/`.
- **doc-as-done.AC30.2 Success:** `tombstone.json` written in each superseded directory.
- **doc-as-done.AC30.3 Success:** `/mpi status` surfaces superseded counts.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Create E2E fixture corpus

**Verifies:** doc-as-done.AC8.1, doc-as-done.AC8.2

**Files:**
- Create: `tests/fixtures/e2e/transcripts/p1s1.txt`
- Create: `tests/fixtures/e2e/transcripts/p1s2.txt`
- Create: `tests/fixtures/e2e/transcripts/p2s1.txt`
- Create: `tests/fixtures/e2e/transcripts/p2s2.txt`
- Create: `tests/fixtures/e2e/agent-responses/diachronic/criteria_grouping/p1s1.json`
- Create: `tests/fixtures/e2e/agent-responses/diachronic/criteria_grouping/p1s2.json`
- Create: `tests/fixtures/e2e/agent-responses/diachronic/criteria_grouping/p2s1.json`
- Create: `tests/fixtures/e2e/agent-responses/diachronic/criteria_grouping/p2s2.json`
- Create: `tests/fixtures/e2e/agent-responses/diachronic/criteria_revision/p1s1.json` (+ p1s2, p2s1, p2s2)
- Create: `tests/fixtures/e2e/agent-responses/diachronic/idu_naming_ordering/p1s1.json` (+ others)
- Create: `tests/fixtures/e2e/agent-responses/synchronic/theme_grouping_within_idu/p1s1-idu1.json` (+ per-IDU for each transcript)
- Create: `tests/fixtures/e2e/agent-responses/synchronic/isu_naming/p1s1-idu1.json` (+ per-IDU)
- Create: `tests/fixtures/e2e/agent-responses/synchronic/isu_second_level_grouping/p1s1-idu1.json` (+ per-IDU)
- Create: `tests/fixtures/e2e/prompts/diachronic/criteria_grouping/p1s1.prompt.json` (+ others)
- Create: `tests/fixtures/e2e/prompts/` — one `.prompt.json` per LLM substep per scope

**Implementation:**

**Transcripts:** 4 tiny transcripts (~10 utterances each). Each must have a valid header:
```
Participant 1, Suggestion 1 (Scored 4/5)
P1: I first noticed a heaviness in my hands.
Kevin Sheldrake: Can you say more about that?
P1: It came on gradually, starting at the fingertips.
P1: Then I felt a kind of pulling sensation.
Kevin Sheldrake: And then what happened?
P1: My hands began to move on their own.
P1: I was surprised but not alarmed.
Kevin Sheldrake: How did that feel?
P1: Like watching someone else's hands.
P1: Then the feeling faded.
```
Scores: p1s1=4 (high), p1s2=2 (moderate), p2s1=5 (high), p2s2=1 (low).

**Agent response fixtures (diachronic.criteria_grouping):** Minimal valid JSON satisfying `_validate_diachronic_criteria_grouping` schema. Read `_mpi_schemas.py` to find the exact required fields. Each transcript should have 2 IDUs for simplicity. Each IDU must have `utterance_refs` with at least one span ref pointing at a valid utterance number in the transcript.

**Agent response fixtures (diachronic.criteria_revision):** Same structure plus `convergence: {decision: "converged", reason: "No further changes needed"}`.

**Agent response fixtures (diachronic.idu_naming_ordering):** Final ordered IDU list.

**Agent response fixtures (synchronic — per IDU):** Each transcript produces per-IDU responses. With 2 IDUs per transcript × 4 transcripts = 8 synchronic fixture sets. Each synchronic fixture must satisfy the synchronic schema (has `idu_name` at top level, `isus` array; each ISU has `utterance_refs`).

**Prompt fixtures:** Minimal valid schema_version 2 prompt.json for each LLM substep. Must pass `validate_prompt_artifact`. Read `_mpi_schemas.py` → `validate_prompt_artifact` for required fields. The `actor.agent_file_sha256` field should be set to the actual SHA of `agents/mpi-analyst.md` at the time of writing (or use a 64-char hex placeholder for fixtures — but note that Phase 5's implementation verifies this SHA, so the fixture must have a valid-looking 64-char hex; use `"0" * 64` only if the test bypasses SHA verification, otherwise compute the actual SHA).

**Important:** Read `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` thoroughly before writing any fixture JSON. Every field name, type constraint, and required key must match exactly. The fixtures will be fed to `mpi_step.py close --units-json` so schema validation runs against them.

**Commit:**
```bash
git add tests/fixtures/e2e/
git commit -m "test: add E2E fixture corpus (2p × 2s, ~10 utterances each) for Phase 11"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `tests/test_e2e_pipeline.py` — happy-path E2E driver

**ORDERING NOTE: This task writes the test file. It must be committed AFTER Tasks 3, 4, and 5 have been committed (which implement cascade reset, run-lease/reservation, and span offset resolution in `mpi_step.py`). The test assertions for AC20.6, AC20.7, AC30.1–30.3, and AC28.3–28.4 will fail if the corresponding production code is absent.**

**Verifies:** doc-as-done.AC1.1, doc-as-done.AC1.5, doc-as-done.AC7.2, doc-as-done.AC7.3, doc-as-done.AC8.1, doc-as-done.AC8.2, doc-as-done.AC11.4, doc-as-done.AC20.6, doc-as-done.AC20.7, doc-as-done.AC30.1, doc-as-done.AC30.2, doc-as-done.AC30.3

**Files:**
- Create: `tests/test_e2e_pipeline.py` (integration)

**Implementation:**

**Setup (module-level fixture, `scope="module"`):**
1. Create a `tempfile.TemporaryDirectory` for the E2E run
2. Copy the 4 fixture transcripts into `<tmpdir>/transcripts/raw/`
3. Run `python scripts/mpi_step.py init --run-dir <tmpdir> --transcripts <tmpdir>/transcripts/raw/` (or call the init logic directly)
4. Set git identity locally: `git -C <tmpdir> config user.name "E2E Test"` and `user.email "test@test"`
5. Register offsets for each transcript (call `mpi_step.py` `transcript_prep.hash_raw`, `transcript_prep.normalize`, `transcript_prep.register_offsets` for each — using fixture responses or the orchestrator path)

**Substep DAG walk (one close per substep):**

For each transcript in order (`p1s1`, `p1s2`, `p2s1`, `p2s2`):
  For each diachronic substep (`criteria_grouping`, `criteria_revision`, `idu_naming_ordering`):
  1. Copy the fixture agent-response JSON to `<tmpdir>/analyses/<scope>-diachronic.<substep>.json`
  2. Write a minimal `.md` file at `<tmpdir>/analyses/<scope>-diachronic.<substep>.md`
  3. Copy the prompt fixture to `<tmpdir>/analyses/<scope>-diachronic.<substep>.prompt.json`
  4. Call `mpi_step.py close --actor mpi-analyst --stage diachronic --substep <S> --scope <scope> ...`
  5. Assert exit code 0

  For each IDU in the transcript (2 IDUs each):
    For each synchronic substep (`theme_grouping_within_idu`, `isu_naming`, `isu_second_level_grouping`):
    1-4. Same pattern with scope `<scope>-idu<N>`
    5. Assert exit code 0

**Assertions after all closes:**

- `doc-as-done.AC8.1`: For every `(scope, stage, substep)` combination, assert the analysis JSON exists and `os.path.getsize > 0`.
- `doc-as-done.AC8.2 (manifest)`: Load `<tmpdir>/.mpi/project.json`. For every transcript × diachronic substep: assert `substeps.<substep>.status == "done"` and `output_paths` is non-empty. For every synchronic IDU substep: assert same.
- `doc-as-done.AC7.2 (audit schema)`: Read `<tmpdir>/.mpi/audit.jsonl` line by line; parse each as JSON; assert each event has `event_id`, `@timestamp`, `trace_id`, `event.action`. Assert all `event_id`s are unique.
- `doc-as-done.AC7.3 (trace_id)`: Assert all events share the same `trace_id`.
- `doc-as-done.AC1.5 (done definition — three-way join)`: For a sample substep (e.g., `p1s1 diachronic.criteria_grouping`): find the manifest's `close_id`, find the matching `git_commit_succeeded` event in audit, resolve `mpi.git_commit_sha` via `git show <sha> --name-only`, assert the manifest JSON file appears in the commit tree.
- `doc-as-done.AC11.4`: For every LLM substep close event in audit.jsonl, assert the event contains `mpi.prompt_artifact_path` that is non-empty.
- `doc-as-done.AC8.2 (git log)`: Run `git -C <tmpdir> log --oneline`; count commit lines; assert count equals total LLM-substep closes (3 diachronic × 4 transcripts + 3 synchronic × 2 IDUs × 4 transcripts = 12 + 24 = 36 commits) plus orchestrator substep commits.

**Run lease test (AC20.6):** Before the E2E close loop, start a background `mpi_step.py` process that holds the run lease. Assert a second `/mpi all` invocation returns `run_lease_held`. (This can be a separate small test that doesn't need the full E2E setup — just a tempdir with a `.mpi/run.lease` file containing a live PID.)

**Substep reservation test (AC20.7):** With a valid run lease held, attempt two `close` calls for the same `(stage, substep, scope)`. Assert the second returns `substep_reservation_held`.

**Cascade reset test (AC30.1–AC30.3):** After the main E2E loop, re-run `mpi_step.py close --stage diachronic --substep criteria_revision --scope p1s1 ...` with a new fixture. Assert:
- Previous artifacts moved to `analyses/_superseded/<close_id>/`
- `tombstone.json` exists in that directory
- `mpi_step.py status --run-dir <tmpdir>` output (or render output) mentions superseded counts

**Render round-trip test:** After all closes, run `mpi_step.py render --run-dir <tmpdir>`. Assert the output `reasoning.log` is non-empty. Run it again; assert the second run produces byte-identical output (idempotency — AC3.3).

**Verification:**
```
Run: pytest tests/test_e2e_pipeline.py -v
Expected: All tests pass
Run time: Should complete in <60s (no LLM calls)
```

**Commit:**
```bash
git add tests/test_e2e_pipeline.py
git commit -m "test: add E2E happy-path pipeline test (AC1.1, AC1.5, AC7.2, AC7.3, AC8.1, AC8.2, AC11.4, AC20.6, AC20.7, AC30.1-30.3)"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-6) -->
<!-- Implementation tasks (3-5) add production code to mpi_step.py before the test task (6). -->

<!-- START_TASK_3 -->
### Task 3: Implement cascade reset in `mpi_step.py`

**Verifies:** doc-as-done.AC16.1, doc-as-done.AC16.2, doc-as-done.AC30.1, doc-as-done.AC30.2, doc-as-done.AC30.3

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

Read `mpi_step.py` fully. Add a `_cascade_reset` function called when `close` completes a `diachronic.criteria_revision` substep.

```python
def _cascade_reset(run_dir: Path, scope: str, revision_close_id: str, manifest: dict) -> dict:
    """
    Cascade reset for pNsN after a criteria_revision re-close:
    1. Move affected artifact files to analyses/_superseded/<revision_close_id>/
    2. Write tombstone.json in _superseded/<revision_close_id>/
    3. Reset affected substep statuses to 'pending' in manifest (single write)
    4. Emit one cascade_reset audit event per reset substep
    Returns updated manifest dict.
    """
```

**Cascade logic:**

Substeps to reset for transcript `pNsN` after `diachronic.criteria_revision` re-close:
- `diachronic.idu_naming_ordering` for `pNsN`
- All `synchronic.*` substeps for all `pNsN-iduN` scopes (all IDUs of that transcript)
- All cross-participant substeps (`generic_diachronic.*`, `generic_synchronic.*`, `global_synchronic.*`, `hypothesis.*`) — reset to `pending` since their inputs are now stale

**Artifact moves:** For each reset substep with status `done` (not `pending`), move all three artifact files (`<scope>-<stage>.<substep>.{json,md,prompt.json}`) from `analyses/` to `analyses/_superseded/<revision_close_id>/<scope>-<stage>.<substep>.*` using `os.rename()` (atomic per file). Create `analyses/_superseded/<revision_close_id>/` if absent.

**Tombstone:** After moving all files, write `analyses/_superseded/<revision_close_id>/tombstone.json`:
```json
{
  "cascade_source": "<revision_close_id>",
  "reset_at": "<RFC3339 UTC timestamp>",
  "reset_substeps": ["pNsN diachronic.idu_naming_ordering", ...],
  "reason": "diachronic.criteria_revision re-close triggered cascade"
}
```

**Manifest update:** In a single atomic write (`os.replace`), update all reset substep statuses to `pending` and clear their `output_paths`.

**Audit events:** Append one `cascade_reset` audit event per reset substep (with `mpi.cascade_source` = `revision_close_id`) to `audit.jsonl` BEFORE the manifest write.

**Integrate into `close` verb:** After `git_commit_succeeded` for `diachronic.criteria_revision`, check if any downstream substeps have `status == "done"`. If so, call `_cascade_reset`.

**Also add `mpi_step.py render` superseded-count surfacing (AC30.3):** In the `render` verb, after generating `reasoning.log`, append a summary line: `"_superseded/ contains N close_ids worth of artifacts"` if `analyses/_superseded/` has any subdirectories. Count by listing directories under `_superseded/`.

**Commit:**
```bash
git add microphenomenograph/1.0.0/scripts/mpi_step.py
git commit -m "feat: implement cascade reset with artifact moves to _superseded/ and tombstone (AC16.1, AC16.2, AC30.1-30.3)"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Implement run-lease and substep-reservation in `mpi_step.py`

**Verifies:** doc-as-done.AC20.6, doc-as-done.AC20.7

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

Add two locking mechanisms to `mpi_step.py`:

**Run-lease (AC20.6):**

```python
def _acquire_run_lease(run_dir: Path, run_id: str) -> None:
    """
    Write .mpi/run.lease = {pid, hostname, run_id, started_at, command}.
    If lease file exists and holder PID is alive on same host: exit with run_lease_held.
    If lease file exists and holder PID is dead: auto-reclaim (emit stale_lease_reclaimed event).
    Cross-host: refuse with cross_host_lease_unresolvable.
    """

def _release_run_lease(run_dir: Path) -> None:
    """Remove .mpi/run.lease. Called on normal exit and by signal handlers (SIGINT, SIGTERM)."""
```

Add `--acquire-lease` and `--release-lease` subcommands (or integrate into the `init` verb's `/mpi all` entry point). The lease is held for the duration of an orchestration run. The `close` verb itself does NOT acquire the run lease (close is called per-substep; lease wraps the whole run).

**Substep-reservation (AC20.7):**

```python
def _acquire_substep_reservation(run_dir: Path, stage: str, substep: str, scope: str, close_id: str) -> None:
    """
    Write analyses/<scope>-<stage>.<substep>.reservation.json = {close_id, pid, started_at, intended_artifact_paths}.
    If reservation file exists for same (stage, substep, scope): exit with substep_reservation_held.
    Called in close pre-checks, before any artifact write.
    """

def _release_substep_reservation(run_dir: Path, stage: str, substep: str, scope: str) -> None:
    """Remove the reservation file. Called on git_commit_succeeded or manifest_rolled_back."""
```

Integrate `_acquire_substep_reservation` into `close` pre-checks (after `artifacts_validated`). Integrate `_release_substep_reservation` into the `git_commit_succeeded` and `manifest_rolled_back` paths.

**Also add `--allow-active-repo-nested` flag** to `init` (AC33.2): the `init` verb already checks for nested active repos; add the `--allow-active-repo-nested` override flag if not present.

**Commit:**
```bash
git add microphenomenograph/1.0.0/scripts/mpi_step.py
git commit -m "feat: implement run-lease and substep-reservation in mpi_step.py (AC20.6, AC20.7)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Implement span offset resolution in `mpi_step.py close`

**Verifies:** doc-as-done.AC28.3, doc-as-done.AC28.4

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

Read `mpi_step.py`. In the `close` pre-checks (after schema validation), add span-ref resolution for all analytic units that carry `utterance_refs`.

```python
def _validate_utterance_refs(
    run_dir: Path,
    units_payload: dict,  # full payload dict from --units-json
    stage: str,
    substep: str,
    manifest: dict,
) -> list[str]:
    """
    Validate all utterance_refs in the units payload against the offset registry.
    Handles TWO payload shapes — the implementer MUST distinguish them by stage/substep:

    SHAPE A — per-transcript analytic units (diachronic, synchronic,
    generic_diachronic, generic_synchronic, global_synchronic):
      Each unit is a dict with a top-level 'utterance_refs' list.
      Units are at units_payload['idus'] (diachronic), units_payload['isus']
      (synchronic), etc. — consult _mpi_schemas.py per-substep schema for key.
      Check each unit: if utterance_refs is empty/missing → 'missing_span_refs'.
      Validate each ref (see step 1-4 below).

    SHAPE B — hypothesis candidates (hypothesis.candidate_drafting,
    hypothesis.evidence_extraction):
      Spans are nested: units_payload['candidates'][i]['claims'][j]
        ['{supports|contradicts|ambiguous}'][k]['raw_span_refs']
      Each raw_span_refs entry is a {transcript_id, utterance_number,
      byte_start, byte_end, raw_excerpt} object.
      If any claim has BOTH supports and contradicts empty AND no
      'not_applicable' field → 'missing_span_refs' for that claim.
      Validate each raw_span_refs entry (see step 1-4 below).

    For each ref object:
    1. Load transcripts/offsets/<transcript_id>.json
       → 'offset_registry_missing' if file absent
    2. Look up utterance_number → raw byte range
       → 'span_out_of_range' if utterance_number not in registry
    3. Read raw bytes from transcripts/raw/<transcript_id>.txt[byte_start:byte_end]
       → 'span_out_of_range' if byte range outside file
    4. Decode as UTF-8, compare to ref['raw_excerpt']
       → 'span_excerpt_mismatch' if mismatch (include both excerpts in message)

    Returns list of error strings (empty = all valid).
    """
```

**Integrate into `close` pre-checks:** After `validate_units()` passes and the units JSON is loaded, call `_validate_utterance_refs(run_dir, units_payload, stage, substep, manifest)`. If any errors are returned, write a `span_validation_failed` audit event and exit non-zero — manifest unchanged.

**Scope to LLM substeps only:** The `SUBSTEP_PREREQUISITES` / `LLM_SUBSTEPS` constant in `_mpi_schemas.py` already identifies which substeps invoke LLMs. Only those substeps require utterance_refs validation. Orchestrator-only substeps (`participant_row_assembly`, `worksheet_assembly`, `transcript_prep.*`) skip span validation.

**Handle missing offset registry gracefully:** If `transcripts/offsets/<transcript_id>.json` does not exist (e.g., `transcript_prep.register_offsets` hasn't run yet), emit `offset_registry_missing` error and exit non-zero. This enforces the prerequisite: offset registry must exist before any LLM substep can close.

**Commit:**
```bash
git add microphenomenograph/1.0.0/scripts/mpi_step.py
git commit -m "feat: implement span offset resolution and utterance_refs validation in mpi_step.py close (AC28.3, AC28.4)"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: `tests/test_e2e_fail_fast.py` — negative-path companion

**Note:** Tasks 3–5 above implement the production code (cascade reset, lease/reservation, span resolution) that this test file exercises.

**Verifies:** doc-as-done.AC1.2, doc-as-done.AC1.3, doc-as-done.AC8.3

**Files:**
- Create: `tests/test_e2e_fail_fast.py` (integration)

**Implementation:**

Each test case uses a fresh temp git repo with git identity and a minimal valid manifest. Reuse a shared `@pytest.fixture` for setup.

**Testing:**

- doc-as-done.AC8.3 (malformed units): Feed a `--units-json` with `confidence: 9` (out of range). Assert `mpi_step.py close` exits non-zero with a named error containing the offending field. Assert manifest status is unchanged (`pending`). Assert no git commit was created (`git log` returns empty or unchanged). Assert no half-written artifact exists (no `.tmp` file left on disk).

- doc-as-done.AC8.3 (unknown stage): Feed `--stage fakeStage`. Assert exit non-zero, manifest unchanged.

- doc-as-done.AC8.3 (missing prompt artifact): For an LLM substep, omit `--prompt-artifact`. Assert exit non-zero with `prompt_artifact_missing`, manifest unchanged, no commit.

- doc-as-done.AC1.3 (audit append failure): Simulate audit append failure by making `.mpi/audit.jsonl` read-only before the close, then call `mpi_step.py close`. Assert exit non-zero, manifest untouched. Restore file permissions after test.

- doc-as-done.AC1.2 (commit failure): Simulate commit failure by setting `core.hooksPath` to a directory containing a pre-commit hook that always exits 1, then call close. Assert manifest rolls back and `commit_failed` event is in audit.jsonl.

- Missing span refs: Feed a units JSON with an analytic unit that has `utterance_refs: []`. Assert exit non-zero with `missing_span_refs`, manifest unchanged.

- Span excerpt mismatch: Feed a units JSON with a span ref whose `raw_excerpt` does not match the bytes at the offset range. Assert exit non-zero with `span_excerpt_mismatch`.

**Verification:**
```
Run: pytest tests/test_e2e_fail_fast.py -v
Expected: All negative-path tests pass
```

**Commit:**
```bash
git add tests/test_e2e_fail_fast.py
git commit -m "test: add E2E fail-fast test suite (AC1.2, AC1.3, AC8.3)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_B -->

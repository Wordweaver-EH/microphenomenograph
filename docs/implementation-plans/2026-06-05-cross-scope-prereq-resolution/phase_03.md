# Pipeline Correctness Implementation Plan — Phase 3

**Goal:** Wire `PREREQ_SCOPE_TRANSFORMS` (from Phase 2) into `cmd_close`'s prereq loop: update `_prereq_participant_key()` to consult the table, add `_all_candidate_draftings_done()` helper, and update the prereq loop to handle both the deterministic and all-match cases.

**Architecture:** `cmd_close`'s prereq loop (lines 1251–1261) currently calls `_prereq_participant_key(participant, prereq_stage)` which only knows the synchronic→diachronic case. After this phase: (1) `_prereq_participant_key` also consults `PREREQ_SCOPE_TRANSFORMS` and returns the transformed key or the sentinel `"all_match"`; (2) the loop handles the sentinel by calling `_all_candidate_draftings_done` instead of `_get_substep_status`.

**Tech Stack:** Python 3, pytest.

**Scope:** Phase 3 of 8 (depends on Phase 2).

**Codebase verified:** 2026-06-05

**Investigator findings:**
- `cmd_close` prereq loop is at lines 1251–1261 of `mpi_step.py`.
- `_prereq_participant_key` is at lines 178–191; signature `(participant: str, prereq_stage: str) -> str`.
- `mpi_step.py` imports from `_mpi_schemas` at line 29: `from _mpi_schemas import validate_units, validate_prompt_artifact, SUBSTEP_PREREQUISITES, LLM_SUBSTEPS`. Must add `PREREQ_SCOPE_TRANSFORMS`.
- No existing `_all_candidate_draftings_done` function anywhere.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC1: Deterministic scope transform resolves worksheet_assembly prereq
- **cross-scope-prereq-resolution.AC1.1 Success:** `cmd_close` for `generic_synchronic.worksheet_assembly` (scope `event3-cat-low-gidu1`) succeeds when `select_generic_idus_of_interest` is done under participant key `event3`.
- **cross-scope-prereq-resolution.AC1.2 Failure:** Same close fails `prereq_unsatisfied` when no `select_generic_idus_of_interest` entry exists.

### cross-scope-prereq-resolution.AC2: All-match semantics gate weak_evidence_review correctly
- **cross-scope-prereq-resolution.AC2.1 Success:** Close for `hypothesis.weak_evidence_review` (scope `global`) succeeds when every `hypothesis.candidate_drafting` entry in the manifest has status `done`.
- **cross-scope-prereq-resolution.AC2.2 Failure:** Same close fails `prereq_unsatisfied` when no `candidate_drafting` entry exists at all.
- **cross-scope-prereq-resolution.AC2.3 Failure:** Close fails when all `candidate_drafting` entries are `done` except one which has status `pending`.
- **cross-scope-prereq-resolution.AC2.4 Failure:** Close fails when a `candidate_drafting` entry has status `flagged`.
- **cross-scope-prereq-resolution.AC2.5 Success:** With `study.dv_focuses` absent or null, all-match uses the manifest scan (AC2.1–AC2.4 semantics).

### cross-scope-prereq-resolution.AC3: Backward compatibility
- **cross-scope-prereq-resolution.AC3.1 Success:** Synchronic → diachronic scope stripping (`p1s1-idu2` → `p1s1`) still works.
- **cross-scope-prereq-resolution.AC3.2 Success:** Same-scope prereqs use the unchanged participant key.
- **cross-scope-prereq-resolution.AC3.3 Success:** All existing tests pass without modification.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Update import line and `_prereq_participant_key()` in `mpi_step.py`

**Verifies:** cross-scope-prereq-resolution.AC1.1, cross-scope-prereq-resolution.AC1.2, cross-scope-prereq-resolution.AC3.1, cross-scope-prereq-resolution.AC3.2

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

**Step 1: Update the import at line 29** to add `PREREQ_SCOPE_TRANSFORMS`:

```python
from _mpi_schemas import (
    validate_units, validate_prompt_artifact,
    SUBSTEP_PREREQUISITES, LLM_SUBSTEPS, PREREQ_SCOPE_TRANSFORMS,
)
```

**Step 2: Replace `_prereq_participant_key` (lines 178–191)** with the expanded version:

```python
def _prereq_participant_key(
    participant: str,
    prereq_stage: str,
    prereq_substep: str = "",
    downstream_stage: str = "",
    downstream_substep: str = "",
) -> str | None:
    """
    Derive the participant key for checking a prerequisite.

    Returns one of:
    - A string participant key (possibly transformed from the downstream key)
    - None  — caller should fall through to standard same-scope lookup
    - "all_match" sentinel — caller should use _all_candidate_draftings_done()

    Checks in order:
    1. PREREQ_SCOPE_TRANSFORMS table (new cross-participant edges)
    2. Legacy synchronic -> diachronic strip (preserved for backward compat)
    3. Default: return participant unchanged
    """
    # 1. Consult PREREQ_SCOPE_TRANSFORMS when enough context is provided
    if downstream_stage and downstream_substep and prereq_stage and prereq_substep:
        key = (downstream_stage, downstream_substep, prereq_stage, prereq_substep)
        transform = PREREQ_SCOPE_TRANSFORMS.get(key)
        if transform is not None:
            if transform == "all_match":
                return "all_match"
            # transform is a callable: apply it to the current participant scope
            return transform(participant)

    # 2. Legacy: synchronic -> diachronic scope strip
    if prereq_stage == "diachronic" and "-idu" in participant:
        idx = participant.rfind("-idu")
        if idx > 0:
            return participant[:idx]

    # 3. Default: unchanged
    return participant
```

Note: the new optional parameters have default values so all existing call sites continue to work without modification, satisfying AC3.1–AC3.3.

**Commit:** `feat: extend _prereq_participant_key to consult PREREQ_SCOPE_TRANSFORMS`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `_all_candidate_draftings_done()` helper to `mpi_step.py`

**Verifies:** cross-scope-prereq-resolution.AC2.1, AC2.2, AC2.3, AC2.4, AC2.5

**Note (Phase 8 pre-implementation):** The `dv_focuses` extension path at the end of `_all_candidate_draftings_done` (checking declared focuses when `study.dv_focuses` is non-null) is written here but tested in Phase 8 (AC8.3). This phase only tests the null-focuses manifest-scan path (AC2).

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

Add this function after `_get_substep_status` (currently at lines 193–198), before `_derive_stage_status`:

```python
def _all_candidate_draftings_done(
    manifest: dict,
    prereq_stage: str,
    prereq_substep: str,
) -> bool:
    """
    All-match gate: every manifest entry for (prereq_stage, prereq_substep)
    across all participant keys must have status 'done'.

    Returns False if:
    - No matching entries exist at all (nothing done yet)
    - Any matching entry has status other than 'done'

    When study.dv_focuses is non-null, additionally checks that every
    declared focus has a matching entry (not just present-in-manifest ones).
    This is the Phase 8 extension point; for now (Phases 1-7) dv_focuses
    is always null, so only the manifest-scan path is needed.
    """
    participants = manifest.get("participants", {})
    found_any = False
    dv_focuses = manifest.get("study", {}).get("dv_focuses")

    for pid, pdata in participants.items():
        stages = pdata.get("stages", {})
        stage_data = stages.get(prereq_stage, {})
        substeps = stage_data.get("substeps", {})
        if prereq_substep in substeps:
            found_any = True
            if substeps[prereq_substep].get("status") != "done":
                return False

    if not found_any:
        return False

    # Phase 8 extension: if dv_focuses is declared, check all are present
    if dv_focuses is not None:
        for focus in dv_focuses:
            focus_key = f"dv-{focus}"
            p = participants.get(focus_key, {})
            status = (p.get("stages", {})
                       .get(prereq_stage, {})
                       .get("substeps", {})
                       .get(prereq_substep, {})
                       .get("status"))
            if status != "done":
                return False

    return True
```

**Commit:** `feat: add _all_candidate_draftings_done helper to mpi_step.py`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update `cmd_close` prereq loop and add tests

**Verifies:** cross-scope-prereq-resolution.AC1.1, AC1.2, AC2.1, AC2.2, AC2.3, AC2.4, AC2.5, AC3.1, AC3.2, AC3.3

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (prereq loop, lines 1251–1261)
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py`

**Implementation — prereq loop:**

Replace lines 1251–1261:

```python
    # Check substep DAG prerequisites
    prereqs = SUBSTEP_PREREQUISITES.get((args.stage, args.substep), [])
    for prereq_stage, prereq_substep in prereqs:
        prereq_participant = _prereq_participant_key(args.participant, prereq_stage)
        status = _get_substep_status(manifest, prereq_participant, prereq_stage, prereq_substep)
        if status != "done":
            msg = (f"prereq_unsatisfied: ({prereq_stage}, {prereq_substep}) "
                   f"must be 'done' before closing ({args.stage}, {args.substep}); "
                   f"current status: {status}")
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)
```

With:

```python
    # Check substep DAG prerequisites
    prereqs = SUBSTEP_PREREQUISITES.get((args.stage, args.substep), [])
    for prereq_stage, prereq_substep in prereqs:
        prereq_participant = _prereq_participant_key(
            args.participant,
            prereq_stage,
            prereq_substep=prereq_substep,
            downstream_stage=args.stage,
            downstream_substep=args.substep,
        )
        if prereq_participant == "all_match":
            if not _all_candidate_draftings_done(manifest, prereq_stage, prereq_substep):
                msg = (f"prereq_unsatisfied: all ({prereq_stage}, {prereq_substep}) "
                       f"entries must be 'done' before closing ({args.stage}, {args.substep})")
                print(f"ERROR {msg}", file=sys.stderr)
                return _abort(msg)
        else:
            status = _get_substep_status(manifest, prereq_participant, prereq_stage, prereq_substep)
            if status != "done":
                msg = (f"prereq_unsatisfied: ({prereq_stage}, {prereq_substep}) "
                       f"must be 'done' before closing ({args.stage}, {args.substep}); "
                       f"current status: {status}")
                print(f"ERROR {msg}", file=sys.stderr)
                return _abort(msg)
```

**Testing — add class `TestPrereqScopeResolutionClose` to `test_mpi_step.py`:**

These are integration tests using `mpi_step.main(["close", ...])` with a temp run directory, real git init, and manifest fixtures. Follow the pattern of `TestCloseFailures` (line 538).

Tests must verify:

- **AC1.1:** Close for `generic_synchronic.worksheet_assembly` with scope `event3-cat-low-gidu1` succeeds when manifest has `event3 → generic_synchronic.select_generic_idus_of_interest status=done`.
- **AC1.2:** Same close fails `prereq_unsatisfied` when `event3` has no `select_generic_idus_of_interest` entry.
- **AC2.1:** Close for `hypothesis.weak_evidence_review` scope `global` succeeds when manifest has 2 DV focuses both with `candidate_drafting status=done`.
- **AC2.2:** Same close fails when no `candidate_drafting` entries exist at all.
- **AC2.3:** Close fails when one of 2 `candidate_drafting` entries has `status=pending`. **Important fixture note:** the manifest must contain a participant entry with `candidate_drafting` at `status=pending` (a present-but-pending entry). This is NOT the missing-entry case (no participant key at all for that focus). The missing-entry case (declared focus not yet run) is AC8.3's job and requires the `dv_focuses` list from Phase 8.
- **AC2.4:** Close fails when a `candidate_drafting` entry has `status=flagged`.
- **AC2.5:** All-match uses manifest scan when `study.dv_focuses` is null.
- **AC3.1:** Close for `synchronic.theme_grouping_within_idu` with scope `p1s1-idu2` correctly looks up `diachronic.idu_naming_ordering` under participant key `p1s1`.

Helper: add `_make_manifest_with_substep_done(participant, stage, substep)` fixture that creates a minimal v2.0 manifest with the given substep marked done.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestPrereqScopeResolutionClose -v
python -m pytest test_mpi_step.py -v   # AC3.3: full suite, no regressions
```
Expected: new tests pass; all existing tests still pass.

**Commit:** `feat: wire PREREQ_SCOPE_TRANSFORMS and all-match into cmd_close prereq loop; tests for AC1, AC2, AC3`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

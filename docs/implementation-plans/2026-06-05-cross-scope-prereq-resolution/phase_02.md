# Pipeline Correctness Implementation Plan — Phase 2

**Goal:** Add `PREREQ_SCOPE_TRANSFORMS` dict and `_scope_strip_to_event()` to `_mpi_schemas.py` to describe the two cross-scope prerequisite edges in the cross-participant DAG.

**Architecture:** `_mpi_schemas.py` already has `SUBSTEP_PREREQUISITES` (declarative DAG) and `LLM_SUBSTEPS` (declarative set). `PREREQ_SCOPE_TRANSFORMS` follows the same data-driven pattern: a dict mapping a 4-tuple `(downstream_stage, downstream_substep, prereq_stage, prereq_substep)` to either a transform function (deterministic key derivation) or the sentinel string `"all_match"`. Phase 3 wires this into `cmd_close`; this phase only adds the data structure and function.

**Tech Stack:** Python 3, pytest.

**Scope:** Phase 2 of 8 (independent — can be implemented in parallel with Phases 1, 4, 5).

**Codebase verified:** 2026-06-05

**Investigator findings (no discrepancies):**
- `PREREQ_SCOPE_TRANSFORMS` and `_scope_strip_to_event` confirmed absent — clean additions.
- No `__all__` exists in `_mpi_schemas.py`; new names are immediately importable.
- `_prereq_participant_key()` at lines 178–191 handles only the synchronic→diachronic case; Phase 2 does not modify it (Phase 3 does).
- The two target SUBSTEP_PREREQUISITES entries confirmed at lines 455 and 460.
- No existing tests for `_prereq_participant_key` directly; Phase 2 adds tests for the new table.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC1: Deterministic scope transform resolves worksheet_assembly prereq
- **cross-scope-prereq-resolution.AC1.1 Success:** `cmd_close` for `generic_synchronic.worksheet_assembly` (scope `event3-cat-low-gidu1`) succeeds when `select_generic_idus_of_interest` is done under participant key `event3`.
- **cross-scope-prereq-resolution.AC1.2 Failure:** Same close fails `prereq_unsatisfied` when no `select_generic_idus_of_interest` entry exists.
- **cross-scope-prereq-resolution.AC1.3 Edge:** `_scope_strip_to_event("event12-cat-moderate-gidu3")` returns `"event12"`.

### cross-scope-prereq-resolution.AC3: Backward compatibility
- **cross-scope-prereq-resolution.AC3.1 Success:** Synchronic → diachronic scope stripping (`p1s1-idu2` → `p1s1`) still works.
- **cross-scope-prereq-resolution.AC3.2 Success:** Same-scope prereqs use the unchanged participant key.
- **cross-scope-prereq-resolution.AC3.3 Success:** All existing tests pass without modification.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add `_scope_strip_to_event` and `PREREQ_SCOPE_TRANSFORMS` to `_mpi_schemas.py`

**Verifies:** cross-scope-prereq-resolution.AC1.3 (scope strip function), cross-scope-prereq-resolution.AC3.3 (no regressions)

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**Implementation:**

Add after the `LLM_SUBSTEPS` frozenset (after line 484, before the prompt artifact validator section at line 486):

```python
# ---------------------------------------------------------------------------
# Cross-scope prerequisite transforms
# ---------------------------------------------------------------------------

def _scope_strip_to_event(scope: str) -> str:
    """
    Extract the event ID from an event-category-gIDU scope string.

    Examples:
        "event3-cat-low-gidu1"      -> "event3"
        "event12-cat-moderate-gidu3" -> "event12"

    Safety: splits on "-cat-" which cannot appear in a valid event ID because
    event IDs match event\\d+ (enforced by the transcript header parser).
    If "-cat-" is not found, returns the scope unchanged (defensive fallback).
    """
    idx = scope.find("-cat-")
    if idx > 0:
        return scope[:idx]
    return scope


# Maps (downstream_stage, downstream_substep, prereq_stage, prereq_substep)
# to either:
#   - a callable(scope: str) -> str   : deterministic key derivation
#   - the sentinel "all_match"         : all matching entries in manifest must be done
#
# The cmd_close prereq loop (Phase 3) consults this table when SUBSTEP_PREREQUISITES
# lists a prereq whose scope differs from the downstream substep's scope.
PREREQ_SCOPE_TRANSFORMS: dict[tuple[str, str, str, str], object] = {
    # generic_synchronic.worksheet_assembly (scope: event<E>-cat-<C>-gidu<G>)
    # depends on select_generic_idus_of_interest (scope: event<E>)
    ("generic_synchronic", "worksheet_assembly",
     "generic_synchronic", "select_generic_idus_of_interest"): _scope_strip_to_event,

    # hypothesis.weak_evidence_review (scope: global)
    # depends on candidate_drafting (scope: dv-<focus>, one per DV focus)
    # Use all_match: every candidate_drafting entry in the manifest must be done.
    ("hypothesis", "weak_evidence_review",
     "hypothesis", "candidate_drafting"): "all_match",
}
```

**Verification:**
```python
# Quick sanity check (run in Python REPL from scripts/):
from _mpi_schemas import PREREQ_SCOPE_TRANSFORMS, _scope_strip_to_event
assert _scope_strip_to_event("event3-cat-low-gidu1") == "event3"
assert _scope_strip_to_event("event12-cat-moderate-gidu3") == "event12"
assert len(PREREQ_SCOPE_TRANSFORMS) == 2
```

**Commit:** `feat: add _scope_strip_to_event and PREREQ_SCOPE_TRANSFORMS to _mpi_schemas.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tests for `_scope_strip_to_event` and `PREREQ_SCOPE_TRANSFORMS`

**Verifies:** cross-scope-prereq-resolution.AC1.3, cross-scope-prereq-resolution.AC3.1, cross-scope-prereq-resolution.AC3.2, cross-scope-prereq-resolution.AC3.3

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py`
- Add import: `from _mpi_schemas import PREREQ_SCOPE_TRANSFORMS, _scope_strip_to_event` (alongside the existing `from _mpi_schemas import validate_units` at line 17)

**Implementation:**

Add class `TestPrereqScopeResolution` after the existing `TestValidateUnits` class. Tests:

- **`_scope_strip_to_event` function:**
  - `"event3-cat-low-gidu1"` → `"event3"` (AC1.3 basic)
  - `"event12-cat-moderate-gidu3"` → `"event12"` (AC1.3 double-digit event)
  - `"event1-cat-high-gidu5"` → `"event1"`
  - Input with no `-cat-` returns input unchanged (defensive fallback)

- **`PREREQ_SCOPE_TRANSFORMS` table:**
  - Table has exactly 2 entries
  - `worksheet_assembly → select_generic_idus_of_interest` entry maps to a callable
  - Calling that callable with `"event3-cat-low-gidu1"` returns `"event3"`
  - `weak_evidence_review → candidate_drafting` entry maps to `"all_match"`

- **Backward compat (`_prereq_participant_key` still works):**
  - `_prereq_participant_key("p1s1-idu2", "diachronic")` → `"p1s1"` (AC3.1)
  - `_prereq_participant_key("p1s1", "diachronic")` → `"p1s1"` (no suffix, unchanged)
  - `_prereq_participant_key("event3-cat-low", "generic_diachronic")` → `"event3-cat-low"` (AC3.2 — same-scope, unchanged)

Add import `from mpi_step import _prereq_participant_key` alongside existing mpi_step import.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestPrereqScopeResolution -v
```
Expected: all tests pass.

Run full suite to confirm AC3.3:
```
python -m pytest test_mpi_step.py -v
```
Expected: all previously-passing tests still pass.

**Commit:** `test: TestPrereqScopeResolution — _scope_strip_to_event, PREREQ_SCOPE_TRANSFORMS, backward compat`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

# Pipeline Correctness Implementation Plan — Phase 5

**Goal:** Register all three `transcript_prep` substeps (`hash_raw`, `normalize`, `register_offsets`) in `_mpi_schemas.py` so they can be closed via `cmd_close` like every other stage.

**Architecture:** Three new validator functions follow the same `_require_keys` pattern as all existing validators. Entries are added to `_VALIDATORS`, `SUBSTEP_PREREQUISITES` (enforcing `hash_raw → normalize → register_offsets`), and NOT to `LLM_SUBSTEPS` (all three are orchestrator-only). Phase 6 adds offset format enforcement on top of the `register_offsets` validator added here.

**Tech Stack:** Python 3, pytest.

**Scope:** Phase 5 of 8 (independent — can be implemented in parallel with Phases 1, 2, 4).

**Codebase verified:** 2026-06-05

**Investigator findings:**
- `transcript_prep` confirmed absent from `_VALIDATORS` (lines 396–417), `SUBSTEP_PREREQUISITES` (lines 443–464), `LLM_SUBSTEPS` (lines 466–484).
- Orchestrator-only exclusion pattern confirmed: `participant_row_assembly`, `worksheet_assembly`, `agreement_computation` are excluded from `LLM_SUBSTEPS`.
- SKILL.md payload fields not formally specified — designed here based on what each substep produces:
  - `hash_raw`: SHA256 of raw file → needs `transcript_id`, `sha256`, `byte_size`
  - `normalize`: produces normalized file + diff → needs `transcript_id`, `normalized_path`, `diff_path`
  - `register_offsets`: produces offset JSON → needs `transcript_id`, `offsets_path`, `utterance_count`
- `tests/test_transcript_prep.py` tests legacy behaviour (pre-Plan-1 path); does not test the close protocol.
- Zero coverage of `transcript_prep` in `test_mpi_step.py`.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC5: `transcript_prep` closes via `cmd_close`
- **cross-scope-prereq-resolution.AC5.1 Success:** `cmd_close --stage transcript_prep --substep hash_raw` with a valid units-json succeeds and commits.
- **cross-scope-prereq-resolution.AC5.2 Success:** `cmd_close --stage transcript_prep --substep normalize` succeeds with a valid normalized artifact path.
- **cross-scope-prereq-resolution.AC5.3 Success:** `cmd_close --stage transcript_prep --substep register_offsets` succeeds with a valid offsets JSON.
- **cross-scope-prereq-resolution.AC5.4 Failure:** Missing required fields in the units-json (e.g. no `transcript_id`) are rejected with `schema_validation_failed`.
- **cross-scope-prereq-resolution.AC5.5 Success:** Prerequisite ordering is enforced: `normalize` rejects until `hash_raw` is done; `register_offsets` rejects until `normalize` is done.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add `transcript_prep` validators to `_mpi_schemas.py`

**Verifies:** cross-scope-prereq-resolution.AC5.4 (schema validation)

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**Implementation:**

Add three validator functions after the `irr_calibration` validators (before the `_VALIDATORS` dict at line 396). Insert after the last `irr_calibration` validator function and before line 395 (`# ---------------------------------------------------------------------------`):

```python
def _validate_transcript_prep_hash_raw(payload: dict) -> list[SchemaError]:
    """hash_raw — records SHA256 and byte size of the immutable raw transcript."""
    return _require_keys(payload, ["transcript_id", "sha256", "byte_size"], "payload")


def _validate_transcript_prep_normalize(payload: dict) -> list[SchemaError]:
    """normalize — records paths of normalized transcript and diff file."""
    return _require_keys(payload, ["transcript_id", "normalized_path", "diff_path"], "payload")


def _validate_transcript_prep_register_offsets(payload: dict) -> list[SchemaError]:
    """register_offsets — records path of the utterance offset file and utterance count.
    Phase 6 adds offset format enforcement (flat-dict, byte alignment) on top of this.
    """
    return _require_keys(payload, ["transcript_id", "offsets_path", "utterance_count"], "payload")
```

**`_VALIDATORS` additions** — add after `("irr_calibration", "agreement_computation")` (line 416), before the closing `}` at line 417:

```python
    ("transcript_prep", "hash_raw"): _validate_transcript_prep_hash_raw,
    ("transcript_prep", "normalize"): _validate_transcript_prep_normalize,
    ("transcript_prep", "register_offsets"): _validate_transcript_prep_register_offsets,
```

**`SUBSTEP_PREREQUISITES` additions** — add after `("irr_calibration", "agreement_computation")` (line 463), before the closing `}` at line 464:

```python
    ("transcript_prep", "hash_raw"): [],
    ("transcript_prep", "normalize"): [("transcript_prep", "hash_raw")],
    # register_offsets depends on normalize (single-line-per-utterance invariant
    # enforced by normalize is assumed by the offset computation).
    ("transcript_prep", "register_offsets"): [("transcript_prep", "normalize")],
```

**`LLM_SUBSTEPS`** — no change needed. All three `transcript_prep` substeps are orchestrator-only and must NOT appear in `LLM_SUBSTEPS`. The existing frozenset remains unchanged.

**Verification (quick unit check):**
```python
from _mpi_schemas import validate_units
assert validate_units("transcript_prep", "hash_raw",
    {"transcript_id": "p1s3", "sha256": "abc123", "byte_size": 1024}) == []
assert validate_units("transcript_prep", "normalize",
    {"transcript_id": "p1s3", "normalized_path": "x.txt", "diff_path": "x.diff"}) == []
assert validate_units("transcript_prep", "register_offsets",
    {"transcript_id": "p1s3", "offsets_path": "x.json", "utterance_count": 42}) == []
# missing field:
errs = validate_units("transcript_prep", "hash_raw", {"sha256": "abc", "byte_size": 100})
assert any(e.field == "payload.transcript_id" for e in errs)
```

**Commit:** `feat: add transcript_prep validators (hash_raw, normalize, register_offsets) to _mpi_schemas.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Tests for `transcript_prep` validators and DAG prereq enforcement

**Verifies:** AC5.1, AC5.2, AC5.3, AC5.4, AC5.5

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py`

**Implementation:**

Add class `TestTranscriptPrepValidators` after `TestInitValidators`:

**Schema validation tests (AC5.4):**
- `validate_units("transcript_prep", "hash_raw", valid)` → `[]`
- Missing `transcript_id` from `hash_raw` payload → schema error with field `payload.transcript_id`
- Missing `sha256` from `hash_raw` → schema error
- Missing `byte_size` from `hash_raw` → schema error
- `validate_units("transcript_prep", "normalize", valid)` → `[]`
- Missing `diff_path` from `normalize` → schema error
- `validate_units("transcript_prep", "register_offsets", valid)` → `[]`
- Missing `utterance_count` from `register_offsets` → schema error
- `validate_units("transcript_prep", "unknown_substep", {})` → substep error
- `validate_units("unknown_stage", "hash_raw", {})` → stage error (proves `transcript_prep` is now a known stage)

**DAG prereq enforcement tests (AC5.5)** — integration tests using `mpi_step.main(["close", ...])` with a temp run directory:

- Close `normalize` when `hash_raw` is pending → fails `prereq_unsatisfied`
- Close `normalize` after `hash_raw` is done → succeeds
- Close `register_offsets` when `normalize` is pending → fails `prereq_unsatisfied`
- Close `register_offsets` after `hash_raw` done but `normalize` pending → fails `prereq_unsatisfied`
- Close `register_offsets` after both `hash_raw` and `normalize` done → succeeds

Use the same run-directory fixture pattern as `TestConfirmStudyConfigClose` (Phase 1): `_git()` + `_setup_git_identity()` helpers, create `.mpi/project.json` manually with substep pre-populated as done where needed.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestTranscriptPrepValidators -v
```
Expected: all tests pass.

```
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
```
Expected: full suite passes, including pre-existing `tests/test_transcript_prep.py` tests (which test the legacy normalisation class, unaffected by this phase).

**Commit:** `test: TestTranscriptPrepValidators — schema validation and DAG prereq enforcement (AC5)`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

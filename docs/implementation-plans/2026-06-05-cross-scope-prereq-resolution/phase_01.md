# Pipeline Correctness Implementation Plan — Phase 1

**Goal:** Add `study.event_groups` and `study.dv_focuses` fields to the manifest, written at `init.confirm_study_config` close; add all three init-stage validators to `_mpi_schemas.py`; update CLAUDE.md and mpi-init SKILL.md documentation.

**Architecture:** `cmd_close` currently writes only to `manifest["participants"][...]["stages"][...]["substeps"][...]`. For `init.confirm_study_config`, it must also write to `manifest["study"]` (event_groups, dv_focuses, config_provenance). This is a targeted post-validation hook within `cmd_close`. All three init substep validators follow the same `_require_keys` pattern as every existing stage.

**Tech Stack:** Python 3, pytest, JSON manifests.

**Scope:** Phase 1 of 8 (foundational — Phases 7 and 8 depend on the `event_groups` field this phase introduces).

**Codebase verified:** 2026-06-05

**Investigator discrepancies:**
- `confirm_study_config` close path does **not** exist in current code — `cmd_init` only writes the initial bootstrap manifest; no init substep close is wired. This phase implements it from scratch.
- The init stage (`scan_transcripts`, `propose_study_config`, `confirm_study_config`) is entirely absent from `_VALIDATORS`, `SUBSTEP_PREREQUISITES`, and `LLM_SUBSTEPS` in `_mpi_schemas.py`.
- `mpi-init/SKILL.md` contains a stale v1.0 manifest schema (`version: "1.0"`, `cross_participant_stages`, no `study` block) that differs from the v2.0 schema `cmd_init` actually writes. This phase corrects it.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC7: Event-group completeness gates enforced by `close`
- **cross-scope-prereq-resolution.AC7.1 Success:** `study.event_groups` is written to the manifest at `init.confirm_study_config` close; it maps event IDs to lists of transcript IDs (e.g. `{"event1": ["p1s1", "p2s1", "p3s1"]}`). The mapping is study-design-agnostic — any string event ID, any list of transcript IDs.

### cross-scope-prereq-resolution.AC8: Optional researcher-declared DV focuses
- **cross-scope-prereq-resolution.AC8.1 Success:** `init.confirm_study_config` accepts an optional `dv_focuses` list (e.g. `["automaticity", "attention", "bodily_sensation"]`); when provided it is written to `study.dv_focuses` in the manifest. When omitted, `study.dv_focuses` is `null`.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add init-stage validators to `_mpi_schemas.py`

**Verifies:** cross-scope-prereq-resolution.AC7.1 (schema validation gate), cross-scope-prereq-resolution.AC8.1 (dv_focuses optional field)

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**Implementation:**

Add three validator functions and register them in `_VALIDATORS`, `SUBSTEP_PREREQUISITES`. None are LLM substeps.

**Validator functions** — add after the `irr_calibration` validators (around line 390), before the `_VALIDATORS` dict:

```python
def _validate_init_scan_transcripts(payload: dict) -> list[SchemaError]:
    """scan_transcripts — records transcript IDs and their raw SHA256s."""
    return _require_keys(payload, ["transcript_ids", "raw_sha256_map"], "payload")


def _validate_init_propose_study_config(payload: dict) -> list[SchemaError]:
    """propose_study_config — optional LLM-proposed config; may be skipped."""
    return _require_keys(payload, ["event_groups_proposed"], "payload")


def _validate_init_confirm_study_config(payload: dict) -> list[SchemaError]:
    """confirm_study_config — human-confirmed study structure; writes event_groups."""
    errors = _require_keys(payload, ["event_groups", "config_provenance"], "payload")
    eg = payload.get("event_groups")
    if eg is not None:
        if not isinstance(eg, dict):
            errors.append(SchemaError("payload.event_groups", "must be a dict mapping event IDs to lists of transcript IDs"))
        else:
            for eid, tids in eg.items():
                if not isinstance(tids, list):
                    errors.append(SchemaError(f"payload.event_groups.{eid}", "must be a list of transcript ID strings"))
                else:
                    for i, tid in enumerate(tids):
                        if not isinstance(tid, str):
                            errors.append(SchemaError(f"payload.event_groups.{eid}[{i}]", "must be a string transcript ID"))
    dv = payload.get("dv_focuses")
    if dv is not None:
        if not isinstance(dv, list):
            errors.append(SchemaError("payload.dv_focuses", "must be a list of strings or null"))
        else:
            for i, f in enumerate(dv):
                if not isinstance(f, str):
                    errors.append(SchemaError(f"payload.dv_focuses[{i}]", "must be a string"))
    return errors
```

**`_VALIDATORS` additions** — add to the dispatch dict (after `irr_calibration` entries):

```python
    ("init", "scan_transcripts"): _validate_init_scan_transcripts,
    ("init", "propose_study_config"): _validate_init_propose_study_config,
    ("init", "confirm_study_config"): _validate_init_confirm_study_config,
```

**`SUBSTEP_PREREQUISITES` additions** — add to the dict (after `irr_calibration` entries):

```python
    ("init", "scan_transcripts"): [],
    ("init", "propose_study_config"): [("init", "scan_transcripts")],
    # confirm_study_config depends on scan_transcripts only — propose_study_config
    # is skippable (when config_provenance is preregistered/user_specified),
    # so it cannot be a hard prerequisite.
    ("init", "confirm_study_config"): [("init", "scan_transcripts")],
```

**`__all__`** — no change needed; `PREREQ_SCOPE_TRANSFORMS` (Phase 2) will be added there.

**Testing:**

Tests verify AC7.1 and AC8.1 schema validation paths:
- `validate_units("init", "confirm_study_config", valid_payload)` returns `[]`
- Missing `event_groups` key returns schema error
- `event_groups` with non-list value for an event key returns schema error
- `dv_focuses` as list of strings returns `[]`
- `dv_focuses` as `null` (omitted from payload) returns `[]`
- `dv_focuses` containing a non-string entry returns schema error
- `validate_units("init", "scan_transcripts", {...})` returns `[]` with correct fields
- `validate_units("init", "bad_substep", {})` returns substep error

Add class `TestInitValidators` to `microphenomenograph/1.0.0/scripts/test_mpi_step.py` following the same pattern as `TestValidateUnits`.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestInitValidators -v
```
Expected: all tests pass.

**Commit:** `feat: add init-stage validators (scan_transcripts, propose_study_config, confirm_study_config) to _mpi_schemas.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire `confirm_study_config` study-block mutation into `cmd_close`

**Verifies:** cross-scope-prereq-resolution.AC7.1, cross-scope-prereq-resolution.AC8.1

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (around line 1330 — Phase 4 manifest write section)

**Implementation:**

After the substep entry is written to `manifest["participants"]` (after line 1347 `stage_entry["status"] = _derive_stage_status(...)`) but BEFORE `_save_manifest(run_dir, manifest)` (line 1354), add the study-block mutation hook:

```python
    # --- Study-block mutation for init.confirm_study_config ---
    # When the orchestrator closes confirm_study_config, the validated payload
    # carries event_groups, dv_focuses, and config_provenance which must be
    # written to manifest["study"] (not just to the substep entry).
    if args.stage == "init" and args.substep == "confirm_study_config":
        manifest.setdefault("study", {})
        manifest["study"]["event_groups"] = units_payload.get("event_groups")
        manifest["study"]["dv_focuses"] = units_payload.get("dv_focuses")  # may be null
        manifest["study"]["config_provenance"] = units_payload.get("config_provenance")
```

This goes between line 1347 and the `manifest_backup = ...` line. The `units_payload` variable is already in scope (set at lines 1179-1185).

**Phase ordering note (Phase 4 interaction):** Phase 4 restructures `cmd_close` to re-read the manifest inside a lock block starting at line ~1251. When both Phase 1 and Phase 4 are implemented together, the study-block mutation hook must operate on the **in-lock fresh manifest** (the second read), not the line-1134 initial read. The Phase 4 lock block wraps from the fresh re-read through line 1527; this mutation hook at line ~1347 is inside that block and naturally operates on the fresh manifest. No additional change is needed when phases are applied in sequence, but implementers should be aware of this dependency.

**Testing:**

Add class `TestConfirmStudyConfigClose` to `test_mpi_step.py`. These are integration-level tests that call `mpi_step.main(["close", ...])` with a real temporary run directory. Use the same helper pattern as `TestInitDedicatedRepo` (lines 149-206) for git setup.

Tests must verify:
- `cmd_close` for `init.confirm_study_config` with a valid payload writes `event_groups` to `manifest["study"]`
- `event_groups` values are preserved exactly (keys, nested lists)
- `dv_focuses` is `null` in manifest when not provided in payload
- `dv_focuses` list is written to manifest when provided
- `config_provenance` is written to manifest

Test fixture helpers: reuse `_git()` and `_setup_git_identity()` already defined at lines 149-156.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestConfirmStudyConfigClose -v
```
Expected: all tests pass.

**Commit:** `feat: write event_groups and dv_focuses to manifest["study"] on confirm_study_config close`
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Update `microphenomenograph/1.0.0/CLAUDE.md` — manifest schema and glossary

**Verifies:** None (documentation)

**Files:**
- Modify: `microphenomenograph/1.0.0/CLAUDE.md`

**Implementation:**

**3a. Update the `study` block documentation** in the Manifest section. Find the current text:

```
- `study`: `{run_repo_mode, git_remote_configured, calibration_transcript_ids: [], calibration_mode?}`
  - `calibration_transcript_ids`: list of transcript IDs selected for IRR calibration (e.g., `["p1s1", "p3s2"]` for stratified mode)
  - `calibration_mode`: optional string, either `"stratified"` (default, one per IV-level stratum) or `"smoke_test"` (first available)
```

Replace with:

```
- `study`: `{run_repo_mode, git_remote_configured, calibration_transcript_ids: [], calibration_mode?, event_groups?, dv_focuses?, config_provenance?}`
  - `calibration_transcript_ids`: list of transcript IDs selected for IRR calibration (e.g., `["p1s1", "p3s2"]` for stratified mode)
  - `calibration_mode`: optional string, either `"stratified"` (default, one per IV-level stratum) or `"smoke_test"` (first available)
  - `event_groups`: dict mapping event IDs (e.g. `"event1"`) to lists of transcript IDs. Written at `init.confirm_study_config` close. Study-design-agnostic — any string event ID, any transcript list. Required by completeness gates (Phase 7).
  - `dv_focuses`: optional list of researcher-declared dependent variable focus labels (e.g. `["automaticity", "attention"]`), or `null` when focuses are LLM-derived. Written at `init.confirm_study_config` close.
  - `config_provenance`: how the study config was determined (`"preregistered"`, `"user_specified"`, `"llm_proposed_user_confirmed"`). Immutable after `confirm_study_config`.
```

**3b. Update the yolo definition** in the "Execution modes" section. Find:

```
- **yolo** — fully automated, strictly sequential substep-level closes; one `git commit` per substep (via `mpi_step.py close`)
```

Replace with:

```
- **yolo** — fully automated, parallel within-stage execution (all pending participants for a stage invoked concurrently in a single assistant turn), sequential across stages (next stage starts only after all closes for current stage complete); one `git commit` per substep (via `mpi_step.py close`). The within-stage concurrency makes the manifest write race reachable — see close lock (Issue 2).
```

**Verification:**
Read the file and confirm the updated sections appear correctly. No test needed for docs.

**Commit:** `docs: update CLAUDE.md — manifest study block (event_groups, dv_focuses), yolo parallel definition`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Update `mpi-init` SKILL.md — fix stale manifest schema and add event_groups prompt

**Verifies:** None (documentation)

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md`

**Implementation:**

**4a. Fix the stale manifest schema block** (lines 108-138 in current file). The SKILL.md shows a v1.0 schema that predates the actual v2.0 implementation. Replace the entire `## Manifest schema` section (the fenced JSON block) with:

```markdown
## Manifest schema

The init command writes `.mpi/project.json` using the v2.0 schema (same as `cmd_init`
bootstrap output, extended by `init.confirm_study_config` close):

```json
{
  "version": "2.0",
  "run_id": "<UUID4>",
  "study": {
    "run_repo_mode": "dedicated",
    "git_remote_configured": false,
    "calibration_transcript_ids": [],
    "event_groups": {
      "event1": ["p1s1", "p2s1", "p3s1"],
      "event2": ["p1s2", "p2s2", "p3s2"]
    },
    "dv_focuses": null,
    "config_provenance": "user_specified"
  },
  "participants": {
    "p1s1": {
      "stages": {
        "transcript_prep": { "status": "pending", "substeps": {} },
        "diachronic":      { "status": "pending", "substeps": {} },
        "synchronic":      { "status": "pending", "substeps": {} }
      }
    }
  }
}
```

`event_groups`, `dv_focuses`, and `config_provenance` are written by the
`init.confirm_study_config` close (not by the bootstrap `cmd_init` write).
```

**4b. Update the `confirm_study_config` row in the Closure table** (around line 205). Find:

```
| `init.confirm_study_config` | orchestrator | `init.confirm_study_config.json` (records final IV/DV) | Records `study.config_provenance` immutably; also records `study.calibration_transcript_ids` and `study.calibration_mode`. |
```

Replace with:

```
| `init.confirm_study_config` | orchestrator | `init.confirm_study_config.json` | Writes `study.event_groups` (event-to-transcript-ID mapping), `study.dv_focuses` (null unless researcher-specified), and `study.config_provenance` immutably to the manifest. The `confirm_study_config.json` payload must include `event_groups` (required) and may include `dv_focuses` (list or null) and `config_provenance` (string). |
```

**4c. Add event_groups confirmation step to the Steps section.** Find the `## Steps` section. After the step that lists transcript files and builds participant entries (around step 7), add a new step:

```markdown
9. **Confirm event grouping with user.** Present the auto-detected event grouping (derived from
   suggestion numbers in `Participant N, Suggestion M (Scored K/5)` headers — suggestion M → `eventM`):
   ```
   Detected event groups:
   event1: p1s1, p2s1, p3s1, p4s1, p5s1, p6s1, p7s1
   event2: p1s2, p2s2, p3s2, p4s2, p5s2, p6s2, p7s2
   event3: p1s3, p2s3, p3s3, p4s3, p5s3, p6s3, p7s3

   Note: "event" is abstract — for this study suggestion number = event.
   For other study designs (interoception, alcohol, etc.) the grouping
   may differ. Please confirm or correct before proceeding.
   ```
   Ask the user to confirm or provide corrections. Record the confirmed grouping as `event_groups`.

10. Close `init.confirm_study_config` via `mpi_step.py close`:
    - Write `init.confirm_study_config.json` with confirmed `event_groups`, `dv_focuses` (null unless specified), and `config_provenance`.
    - Run: `mpi_step.py close --stage init --substep confirm_study_config --participant run --units-json init.confirm_study_config.json --artifact init.confirm_study_config.json --actor <actor>`
```

**Verification:**
Read the file and confirm sections are correct. No automated test.

**Commit:** `docs: fix mpi-init SKILL.md — update to v2.0 manifest schema, add event_groups confirmation step`
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_B -->

## Phase 1 completion

**Run the full test suite to confirm no regressions:**
```
cd C:/microphenomenograph
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
```
Expected: all existing tests pass, new `TestInitValidators` and `TestConfirmStudyConfigClose` tests pass.

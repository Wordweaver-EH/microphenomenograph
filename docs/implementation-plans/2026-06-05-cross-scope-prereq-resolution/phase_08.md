# Pipeline Correctness Implementation Plan — Phase 8

**Goal:** Activate the `study.dv_focuses` field (schema support added in Phase 1): add a guard in `cmd_close` that rejects undeclared DV focus scopes, extend `_all_candidate_draftings_done` (Phase 3) to check against the declared set, update the hypothesis disclaimer template, and fix the missing `--participant` flag in the `mpi-cross-analyst.md` template.

**Architecture:** `study.dv_focuses` is written at `confirm_study_config` (Phase 1). Phase 8 adds runtime enforcement: inside the lock block, after prereq checks, `cmd_close` reads `manifest["study"]["dv_focuses"]` and, when non-null, validates the `hypothesis.evidence_extraction` scope against it. `_all_candidate_draftings_done` (Phase 3) is extended by an additional `dv_focuses` path that was already stubbed in.

**Tech Stack:** Python 3, pytest.

**Scope:** Phase 8 of 8 (depends on Phase 1 for `study.dv_focuses` in manifest; Phase 3 for `_all_candidate_draftings_done`).

**Codebase verified:** 2026-06-05

**Investigator findings:**
- No special-casing for `hypothesis.evidence_extraction` in `cmd_close`. `args.scope` is `"dv-<focus>"`.
- `mpi-cross-analyst.md` close template omits `--participant` for hypothesis closes — this must be fixed (close would fail at line 1121 without it).
- `_validate_hypothesis_evidence_extraction` at line 284 requires `dv_focus` and `evidence_items`.
- No `dv_focuses_provenance` in the hypothesis disclaimer template yet.
- `_all_candidate_draftings_done` has the `dv_focuses` extension path already stubbed with a comment (Phase 3 plan).
- No existing Phase 8 tests.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC8: Optional researcher-declared DV focuses
- **cross-scope-prereq-resolution.AC8.1 Success:** `init.confirm_study_config` accepts an optional `dv_focuses` list; when provided it is written to `study.dv_focuses` in the manifest. When omitted, `study.dv_focuses` is `null`. *(Implemented in Phase 1; verified here via integration.)*
- **cross-scope-prereq-resolution.AC8.2 Success:** When `study.dv_focuses` is non-null, a `cmd_close` for `hypothesis.evidence_extraction` whose scope `dv-<focus>` names a focus not in the declared list fails with `undeclared_dv_focus`.
- **cross-scope-prereq-resolution.AC8.3 Success:** When `study.dv_focuses` is non-null, `weak_evidence_review` blocks until `candidate_drafting` is `done` for every declared focus — not just every manifest-present entry.
- **cross-scope-prereq-resolution.AC8.4 Success:** When `study.dv_focuses` is null, all-match falls back to the manifest scan (AC2 semantics): all manifest-present `candidate_drafting` entries must be `done`.
- **cross-scope-prereq-resolution.AC8.5 Success:** `study.config_provenance` at `confirm_study_config` records `dv_focuses_provenance`: `"researcher_specified"` when the list was provided, `"emergent"` when null.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add undeclared DV focus guard to `cmd_close` and extend `_all_candidate_draftings_done`

**Verifies:** cross-scope-prereq-resolution.AC8.2, AC8.3, AC8.4

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation — undeclared focus guard:**

Inside the lock block in `cmd_close`, after the prereq check loop and before `_check_completeness_gate`, add:

```python
        # --- DV focus scope guard ---
        # When study.dv_focuses is declared, hypothesis.evidence_extraction must
        # only use scopes from the declared list.
        if args.stage == "hypothesis" and args.substep == "evidence_extraction":
            dv_focuses = manifest.get("study", {}).get("dv_focuses")
            if dv_focuses is not None:
                # Extract focus name from scope "dv-<focus>"
                if args.scope.startswith("dv-"):
                    focus_name = args.scope[len("dv-"):]
                else:
                    focus_name = args.scope
                if focus_name not in dv_focuses:
                    msg = (
                        f"undeclared_dv_focus: focus '{focus_name}' is not in "
                        f"study.dv_focuses {dv_focuses!r}. "
                        f"Either add it to the declared list at confirm_study_config "
                        f"or set dv_focuses to null to allow emergent focuses."
                    )
                    print(f"ERROR {msg}", file=sys.stderr)
                    return _abort(msg)
```

**Implementation — extend `_all_candidate_draftings_done`:**

The Phase 3 plan already stubbed the `dv_focuses` extension path inside `_all_candidate_draftings_done` with a comment. The `dv_focuses` variable is read from `manifest.get("study", {}).get("dv_focuses")` and the check at the end of the function uses it. That implementation is already correct as written in Phase 3 — the `if dv_focuses is not None:` block checks every declared focus and returns `False` if any is missing or not done.

**Verify the Phase 3 implementation is complete** — the relevant section of `_all_candidate_draftings_done` should read:

```python
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
```

If this block is not present in Phase 3's implementation, add it now.

**Commit:** `feat: add undeclared_dv_focus guard in cmd_close; activate dv_focuses path in _all_candidate_draftings_done`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update hypothesis SKILL.md disclaimer and fix agent template `--participant` bug

**Verifies:** cross-scope-prereq-resolution.AC8.5

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`
- Modify: `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`

**Implementation — add `dv_focuses_provenance` to disclaimer mandate:**

Find the "Disclaimer mandate" block in `mpi-hypothesis/SKILL.md` (lines 123–127):

```
**Disclaimer mandate:** Every `hypothesis.candidate_drafting` artifact MUST carry this verbatim field:
"disclaimer": "These are generative conjectures inferred from qualitative pattern variation across IV levels in a small sample. They are not causal estimates from a hypothesis test and should not be reported as such."
The schema validator enforces this field's presence.
```

Add after the disclaimer mandate block:

```markdown
**DV focus provenance field:** Every `hypothesis.candidate_drafting` artifact MUST also
carry a `dv_focuses_provenance` field whose value is:
- `"researcher_specified"` — when `study.dv_focuses` was declared at `confirm_study_config`
- `"emergent"` — when `study.dv_focuses` is null (focuses named by the LLM from analysis)

Read the provenance from `manifest["study"].get("config_provenance")` —
specifically the nested `dv_focuses_provenance` key if present, otherwise infer:
non-null `study.dv_focuses` → `"researcher_specified"`; null → `"emergent"`.

This field is for auditability: it makes explicit whether the hypothesis was constrained
to pre-declared DVs or emerged from the analysis.
```

**Implementation — fix missing `--participant` in close template:**

Find the `hypothesis.evidence_extraction` close command in `mpi-cross-analyst.md`. The current template (around line 296–306) omits `--participant`. Add it:

```bash
python scripts/mpi_step.py close \
  --actor mpi-cross-analyst \
  --stage hypothesis \
  --substep evidence_extraction \
  --participant dv-<focus> \      ← ADD THIS LINE
  --scope dv-<focus> \
  --artifact hypotheses/dv-<focus>.evidence.json \
  ...
```

Apply the same fix to `hypothesis.candidate_drafting` and `hypothesis.weak_evidence_review` close templates in the same file if they also omit `--participant`. For `weak_evidence_review`, use `--participant global --scope global`.

**Verification:**
Read the updated files. No automated test for doc changes.

**Commit:** `docs: add dv_focuses_provenance to hypothesis disclaimer; fix missing --participant in mpi-cross-analyst close templates`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Tests for AC8

**Verifies:** AC8.1, AC8.2, AC8.3, AC8.4, AC8.5

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py`

**Implementation:**

Add class `TestDVFocusGate` after `TestCompletenessGates`.

**Schema/validator tests (AC8.1):**
- `_validate_init_confirm_study_config` with `dv_focuses: ["automaticity", "attention"]` → `[]`
- Same with `dv_focuses: null` (key absent from payload) → `[]`
- With `dv_focuses: [123]` (non-string entry) → schema error

**Integration tests using `mpi_step.main(["close", ...])` with a temp run directory:**

Manifest fixture: v2.0 manifest with `study.dv_focuses: ["automaticity", "attention"]`.

- **AC8.2:** Close for `hypothesis.evidence_extraction` with scope `dv-unknown_focus` fails with error containing `undeclared_dv_focus`.
- **AC8.2 (declared):** Same close with scope `dv-automaticity` succeeds (focus is in declared list).
- **AC8.3:** Close for `hypothesis.weak_evidence_review` with `dv_focuses = ["automaticity", "attention"]` fails when `dv-attention` candidate_drafting is missing from manifest (declared but not done).
- **AC8.3 (complete):** Same close succeeds when both `dv-automaticity` and `dv-attention` have `candidate_drafting` done.
- **AC8.4:** With `study.dv_focuses = null`, close for `weak_evidence_review` with all manifest-present `candidate_drafting` entries done → succeeds (fallback to manifest scan).
- **AC8.4 (incomplete):** With null focuses and one `candidate_drafting` entry pending → fails prereq_unsatisfied.

Manifest fixture helper: `_make_manifest_with_dv_focuses(focuses_list_or_none, candidate_drafting_statuses)` — creates manifest with `study.dv_focuses` set and specified DV focuses with given candidate_drafting statuses.

**AC8.5 test:** Uses `TestConfirmStudyConfigClose` (Phase 1) as base. Extend to verify:
- Closing `confirm_study_config` with `dv_focuses: ["auto"]` and `config_provenance: "researcher_specified"` → `manifest["study"]["dv_focuses"] == ["auto"]` and `manifest["study"]["config_provenance"] == "researcher_specified"`.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestDVFocusGate -v
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
```
Expected: all AC8 tests pass; full suite passes.

**Commit:** `test: TestDVFocusGate — AC8 undeclared focus guard, all-match with declared set, provenance`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 8 completion — full pipeline verification

Run the complete test suite one final time:
```
cd C:/microphenomenograph
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
```
Expected: all 8 phases' tests pass. This is the baseline for the finalization code review.

# Implementation Plan: hypothesis-evidence (plan 4 of 5)

Design doc: `docs/design-plans/2026-06-05-hypothesis-evidence.md`
Branch: `remediation-2026-06-05`
Hard dependency: close-enforcement-2 (all 8 phases landed).

---

## Phase 1: Evidence inputs via `inputs` verb

**Goal:** `hypothesis.evidence_extraction` resolves all three cross-participant analysis artifact sets (generic-diachronic, generic-synchronic, global-synchronic) via `mpi_step.py inputs`. Currently, only `global_synchronic.global_synchronic` artifacts (scope: `gidu<G>-cat-<C>`) are resolved. This phase extends the resolution to also include `generic_diachronic.cross_iv_contrast` and `generic_synchronic.isu_second_level_grouping` artifacts, and updates the SKILL.md prerequisites to match.

**Covers:** hypothesis-evidence.AC1.1, hypothesis-evidence.AC1.2

---

### File: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Region:** `_resolve_inputs` function, `elif stage == "hypothesis":` branch (~lines 2258–2264).

**Current state:**
```python
elif stage == "hypothesis":
    # upstream = all global_synchronic.global_synchronic artifacts (gidu<G>-cat-<C> participants)
    result = []
    for pkey in participants:
        if pkey.startswith("gidu"):
            result.extend(_collect_artifacts(pkey, "global_synchronic", "global_synchronic"))
    return result
```

**Change:** Extend to collect from all three stages. Enumerate all participant keys in the manifest, selecting by prefix/structure:
- `generic_diachronic.cross_iv_contrast`: collect from keys that match `event*-cat-*` pattern (do NOT start with `gidu`; do NOT look like transcript ids `pNsN`). Use: `"-cat-" in pkey and not pkey.startswith("gidu") and not re.match(r'^p\d+s\d+', pkey) and not pkey.startswith("p")`.
- `generic_synchronic.isu_second_level_grouping`: collect from keys that match `event*-cat-*-gidu*` pattern. Use: `"-cat-" in pkey and "-gidu" in pkey`.
- `global_synchronic.global_synchronic`: collect from keys starting with `gidu`. Use: `pkey.startswith("gidu")`.

Implementation — replace the `elif stage == "hypothesis":` branch with:

```python
elif stage == "hypothesis":
    # Fan-in: all three cross-participant analysis artifact sets for the study.
    # generic_diachronic (keys: event<E>-cat-<C> — contain "-cat-", no "-gidu", no pNsN prefix)
    # generic_synchronic (keys: event<E>-cat-<C>-gidu<G> — contain "-cat-" AND "-gidu")
    # global_synchronic  (keys: gidu<G>-cat-<C> — start with "gidu")
    result = []
    for pkey in participants:
        if pkey.startswith("gidu"):
            # global_synchronic artifacts
            result.extend(_collect_artifacts(pkey, "global_synchronic", "global_synchronic"))
        elif "-cat-" in pkey and "-gidu" in pkey:
            # generic_synchronic artifacts (event<E>-cat-<C>-gidu<G> keys)
            result.extend(_collect_artifacts(pkey, "generic_synchronic", "isu_second_level_grouping"))
        elif "-cat-" in pkey:
            # generic_diachronic artifacts (event<E>-cat-<C> keys)
            result.extend(_collect_artifacts(pkey, "generic_diachronic", "cross_iv_contrast"))
    return result
```

Note: This is a fan-in that combines all three upstream stages. Order within the result list is deterministic (Python dict iteration order is insertion order in 3.7+). The `undeclared_input` gate (plan 2) checks that `inputs_consumed ⊆ resolved`; the expanded resolved set means consuming only global_synchronic paths is still valid (not a gate violation).

---

### File: `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`

**Current state (lines 11–30):**
- Line 11: `global_synchronic: done` in manifest
- Line 14: `global_synchronic.status == "done"` in manifest
- Line 15: `- \`analyses/global-synchronic.md\` must exist`
- Line 22: `1. \`analyses/global-synchronic.md\` — the patterns to hypothesise from`
- Line 30: `- Content of \`analyses/global-synchronic.md\``

**Forbidden literal:** `analyses/global-synchronic.md` — all occurrences must be removed/replaced.

**Change — Prerequisites section:** Replace the static file reference with `inputs` verb usage.

Old Prerequisites block (lines 11–17):
```markdown
## Prerequisites

- `.mpi/project.json` must exist
- `global_synchronic.status == "done"` in manifest
- `analyses/global-synchronic.md` must exist
- `bookowhy_rev.md` must be readable (check: first look at `bookowhy_rev.md` relative
  to the current working directory, then at the repo root)
```

New Prerequisites block:
```markdown
## Prerequisites

- `.mpi/project.json` must exist
- All `global_synchronic.*`, `generic_diachronic.*`, and `generic_synchronic.*` substeps `done` in manifest
- `bookowhy_rev.md` must be readable (check: first look at `bookowhy_rev.md` relative
  to the current working directory, then at the repo root)
```

**Change — Context documents section:** Replace static file reference with `inputs` verb.

Old Context documents block (lines 19–31):
```markdown
## Context documents

Read and pass to the cross-analyst:
1. `analyses/global-synchronic.md` — the patterns to hypothesise from
2. `bookowhy_rev.md` — causal framing context (Pearl's causal hierarchy: association,
   intervention, counterfactual)

## Invoking mpi-cross-analyst

Invoke `mpi-cross-analyst` with:
- Task type: `hypothesis_generation`
- Content of `analyses/global-synchronic.md`
- Content of `bookowhy_rev.md` labelled as "Causal framing context:"
```

New Context documents block:
```markdown
## Context documents

Resolve all upstream analysis artifacts using the `inputs` verb:
```bash
python scripts/mpi_step.py inputs --stage hypothesis --scope <dv-focus-scope> --run-dir .
```
This returns all three cross-participant artifact sets as a JSON list:
`{resolved: [{path, sha256}, ...]}` — includes `generic_diachronic.cross_iv_contrast`,
`generic_synchronic.isu_second_level_grouping`, and `global_synchronic.global_synchronic` artifacts.

Read and pass to the cross-analyst:
1. All resolved artifact paths from the `inputs` verb — the complete evidence base
2. `bookowhy_rev.md` — causal framing context (Pearl's causal hierarchy: association,
   intervention, counterfactual)

## Invoking mpi-cross-analyst

Invoke `mpi-cross-analyst` with:
- Task type: `hypothesis_generation`
- All resolved analysis artifacts (paths from `inputs` verb output)
- Content of `bookowhy_rev.md` labelled as "Causal framing context:"
```

**Verify post-edit:** `grep "global-synchronic.md" SKILL.md` must return zero matches.

---

### New tests

**File:** `tests/test_close_enforcement_2.py` (extend with new class or functions at bottom)

**Test functions:**

```python
def test_AC1_1_hypothesis_inputs_resolution_returns_all_three_stages():
    """AC1.1: inputs verb for hypothesis stage returns artifacts from all three
    cross-participant stages (generic_diachronic, generic_synchronic, global_synchronic)."""
```
- Build a manifest with participants covering all three key patterns: `event1-cat-high` (generic_diachronic), `event1-cat-high-gidu1` (generic_synchronic), `gidu1-cat-high` (global_synchronic), each with their respective substep `output_paths` and `artifact_shas`.
- Call `_resolve_inputs(manifest, "hypothesis", "dv-automaticity")`.
- Assert result contains entries from all three stages (check paths from each).

```python
def test_AC1_1_hypothesis_inputs_resolution_excludes_transcript_keys():
    """AC1.1: Transcript-participant keys (pNsN) are not included in hypothesis resolution."""
```
- Add a `p1s1` key to the manifest participants.
- Call `_resolve_inputs(manifest, "hypothesis", "dv-automaticity")`.
- Assert no returned path comes from `p1s1`.

```python
def test_AC1_2_skill_md_no_literal_global_synchronic_artifact():
    """AC1.2: mpi-hypothesis/SKILL.md contains no literal cross-stage artifact filename
    'global-synchronic.md' (the old hardcoded path)."""
```
- Load `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`.
- Assert `"global-synchronic.md"` not in content.
- Assert `"inputs"` in content (inputs verb cited).

---

## Phase 2: claim_id + review coverage schema

**Goal:** Every hypothesis claim carries a required `claim_id` (short, unique within artifact). The `weak_evidence_review` artifact must contain one review item per `claim_id` in `candidate_drafting` artifacts. The empty-review shell defect (empty `review_items` with non-empty claims passes today) is made structurally impossible.

**Covers:** hypothesis-evidence.AC2.1, hypothesis-evidence.AC2.2, hypothesis-evidence.AC2.3, hypothesis-evidence.AC2.4

**Architecture decision (A vs B):** This plan uses **Option A (payload-roster)**: The `review_summary` payload carries an explicit `claim_ids` field (the roster of all claim IDs being reviewed), and `review_items` is validated as covering every entry in that roster. This matches the existing `_validate_*(payload)` signature (payload-only, no manifest/file access) and the test style in `test_analysis_fidelity.py`. The circular risk (LLM controls roster) is accepted as the plan-level design choice; plan 5 (DAG/rung) can add a cross-artifact check if needed.

---

### File: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

#### Change 1: Add `claim_id` to `_validate_hypothesis_candidate_drafting`

**Region:** `_validate_hypothesis_candidate_drafting` (~lines 400–476), the claim loop inside the `for i, cand in enumerate(candidates)` → `for j, claim in enumerate(claims)` block.

Add `claim_id` to the `_require_keys` call on each claim. Currently (~line 433):
```python
errors.extend(_require_keys(claim, ["claim_text", "supports", "contradicts",
                                     "ambiguous", "n_transcripts",
                                     "n_iv_levels_covered", "uncertainty_language",
                                     "negative_cases"], cl_prefix))
```

Add `"claim_id"` to the required fields list:
```python
errors.extend(_require_keys(claim, ["claim_id", "claim_text", "supports", "contradicts",
                                     "ambiguous", "n_transcripts",
                                     "n_iv_levels_covered", "uncertainty_language",
                                     "negative_cases"], cl_prefix))
```

After the `_require_keys` call, add uniqueness check across all claims in the candidate:

After the claim loop closes (after the `for j, claim in enumerate(claims):` loop), add a per-candidate uniqueness check:
```python
# Uniqueness check: claim_id must be unique within the candidate
seen_claim_ids: set[str] = set()
for j, claim in enumerate(claims):
    if not isinstance(claim, dict):
        continue
    cid = claim.get("claim_id")
    if cid is not None:
        if cid in seen_claim_ids:
            errors.append(SchemaError(
                f"{c_prefix}.claims",
                f"duplicate claim_id {cid!r} — claim_id must be unique within the artifact"
            ))
        seen_claim_ids.add(cid)
```

Note: The uniqueness check is across the candidate's claims. The design says "unique within the artifact" — implement as unique within each candidate (a candidate = one hypothesis with multiple claims). If multiple candidates exist, each is independently checked; claim IDs like `c1` can repeat across candidates but not within one.

#### Change 2: Extend `_validate_hypothesis_weak_evidence_review`

**Region:** `_validate_hypothesis_weak_evidence_review` (~line 479–480). Currently:
```python
def _validate_hypothesis_weak_evidence_review(payload: dict) -> list[SchemaError]:
    return _require_keys(payload, ["review_items"], "payload")
```

Replace with a substantive validator:
```python
def _validate_hypothesis_weak_evidence_review(payload: dict) -> list[SchemaError]:
    """Validate weak_evidence_review payload.

    Requires:
    - review_items: list of review item objects
    - claim_ids: list of claim IDs that the review covers (the roster)
    - Every entry in claim_ids must have a corresponding review_item
    - Every review_item must have a claim_id, checks dict, and outcome
    - review_items must not be empty when claim_ids is non-empty (AC2.4)
    """
    errors = _require_keys(payload, ["review_items", "claim_ids"], "payload")

    claim_ids = payload.get("claim_ids", [])
    review_items = payload.get("review_items", [])

    # Validate claim_ids is a list
    if not isinstance(claim_ids, list):
        errors.append(SchemaError("payload.claim_ids", "must be a list of claim ID strings"))
        return errors

    # Validate review_items is a list
    if not isinstance(review_items, list):
        errors.append(SchemaError("payload.review_items", "must be a list"))
        return errors

    # AC2.4: if claim_ids is non-empty, review_items must not be empty
    if isinstance(claim_ids, list) and len(claim_ids) > 0 and len(review_items) == 0:
        errors.append(SchemaError(
            "payload.review_items",
            "empty review_items with non-empty claim_ids: every claim must have a review item"
        ))
        return errors

    # Validate each review item shape
    reviewed_claim_ids: set[str] = set()
    for i, item in enumerate(review_items):
        item_prefix = f"payload.review_items[{i}]"
        if not isinstance(item, dict):
            errors.append(SchemaError(item_prefix, "must be an object"))
            continue
        errors.extend(_require_keys(item, ["claim_id", "checks", "outcome"], item_prefix))
        cid = item.get("claim_id")
        if cid is not None:
            reviewed_claim_ids.add(cid)
        # Validate outcome is valid
        outcome = item.get("outcome")
        if outcome is not None and outcome not in ("pass", "flagged"):
            errors.append(SchemaError(
                f"{item_prefix}.outcome",
                f"must be 'pass' or 'flagged', got {outcome!r}"
            ))
        # Validate checks is a dict
        checks = item.get("checks")
        if checks is not None and not isinstance(checks, dict):
            errors.append(SchemaError(f"{item_prefix}.checks", "must be an object"))

    # AC2.3: every claim_id in the roster must have a review item
    for cid in claim_ids:
        if cid not in reviewed_claim_ids:
            errors.append(SchemaError(
                "payload.review_items",
                f"no review item found for claim_id {cid!r} — every claim must be reviewed"
            ))

    return errors
```

#### Change 3: Update `mpi-cross-analyst.md` claim-level evidence schema section

**Region:** `mpi-cross-analyst.md`, `#### Claim-level evidence schema` section (after line ~169, the `### Hypothesis generation` section). Add `claim_id` to the JSON schema block shown in the agent prompt.

In the existing claim JSON example (currently ~lines 175–204), add `claim_id` as first field:
```json
{
  "hypothesis": "<one-sentence hypothesis statement>",
  "claims": [
    {
      "claim_id": "c1",
      "claim_text": "<specific claim being made>",
      ...
    }
  ],
  ...
}
```

Add a prose note after the JSON block (before the "A claim may not close..." sentence):
```
Each claim MUST carry a `claim_id`: a short deterministic string (`c1`, `c2`, …) unique
within the candidate. The `weak_evidence_review` references claims by `claim_id`; the schema
rejects any candidate artifact missing `claim_id` or with duplicate `claim_id` values.
```

---

### New tests

**File:** `tests/test_hypothesis_evidence.py` (new file, following `test_analysis_fidelity.py` style)

```python
"""Tests for hypothesis-evidence design plan (plan 4).

Phase 2: AC2.1, AC2.2, AC2.3, AC2.4 — claim_id + review coverage schema.
Phase 3: AC3.1, AC3.2, AC3.3, AC3.4 — review gate and agent instructions.
"""
```

**Test class:** `class TestAC2_ClaimIdCoverage:`

```python
def _base_claim(self, claim_id="c1", **kwargs) -> dict:
    """Minimal valid claim with claim_id."""

def _base_candidate(self, claims) -> dict:
    """Minimal valid candidate with disclaimer."""

def _base_candidate_drafting_payload(self, candidates) -> dict:
    """Full candidate_drafting payload."""

def _minimal_raw_span_ref(self) -> dict:
    """Minimal valid raw_span_ref."""

def test_AC2_1_missing_claim_id_rejected(self):
    """AC2.1 Failure: claim without claim_id is rejected."""
    # Build payload with a claim missing claim_id
    # Call validate_units("hypothesis", "candidate_drafting", payload)
    # Assert errors contain claim_id field error

def test_AC2_2_duplicate_claim_id_rejected(self):
    """AC2.2 Failure: two claims with same claim_id in a candidate are rejected."""
    # Build two claims both with claim_id="c1"
    # Assert errors mention "duplicate claim_id"

def test_AC2_3_review_missing_item_for_claim_id_rejected(self):
    """AC2.3 Failure: review payload with claim_ids=["c1","c2"] but review_items
    only covering c1 is rejected."""
    # Build review payload with claim_ids=["c1","c2"], review_items=[{claim_id:"c1",...}]
    # Call validate_units("hypothesis", "weak_evidence_review", payload)
    # Assert error mentions c2 not covered

def test_AC2_4_empty_review_items_with_nonempty_claims_rejected(self):
    """AC2.4 Failure: review payload with non-empty claim_ids and empty review_items
    is rejected (the empty-shell defect is structurally impossible)."""
    # Build payload with claim_ids=["c1"] and review_items=[]
    # Assert error about empty review_items

def test_AC2_valid_full_coverage_accepted(self):
    """Success: review payload with one review item per claim_id is accepted."""
    # Build payload with claim_ids=["c1","c2"], two matching review_items

def test_AC2_1_claim_id_present_passes_basic_schema(self):
    """Success: candidate_drafting claim with claim_id passes schema."""
```

---

## Phase 3: Review instructions + gate

**Goal:** `mpi-cross-analyst.md` gains a `### Weak evidence review` section with explicit instructions for the three checks (thin-support, single-IV-level, causal-language). The `weak_evidence_unreviewed` gate is added to the `GATES` registry in `_mpi_schemas.py` and wired in `cmd_close` for `hypothesis.weak_evidence_review`: any `flagged` review item without `acknowledged_by` triggers the gate (warn-default; strict via `study.strict_gates` or `--strict-weak-evidence-unreviewed`).

**Covers:** hypothesis-evidence.AC3.1, hypothesis-evidence.AC3.2, hypothesis-evidence.AC3.3, hypothesis-evidence.AC3.4

**Dependencies:** Phases 1 and 2 (Phase 3 builds on the review payload structure from Phase 2 and the gate infrastructure from plan 2).

---

### File: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

#### Change 1: Add `weak_evidence_unreviewed` to GATES registry

**Region:** `GATES` dict (~lines 891–917), after the `irr_below_threshold` entry.

Add:
```python
"weak_evidence_unreviewed": {
    "stage": "hypothesis",
    "description": "weak_evidence_review has flagged items lacking acknowledged_by",
    "posture": "warn_or_abort",
},
```

---

### File: `microphenomenograph/1.0.0/scripts/mpi_step.py`

#### Change 1: Add `--strict-weak-evidence-unreviewed` CLI flag

**Region:** Argument registration block after `--strict-undeclared-input` (~line 2454–2456).

Add:
```python
p_close.add_argument("--strict-weak-evidence-unreviewed", action="store_true",
                     dest="strict_weak_evidence_unreviewed",
                     help="Block hypothesis.weak_evidence_review close when flagged items "
                          "lack acknowledged_by.")
```

Note: `dest` uses underscores → `_evaluate_gate` normalises gate_id `weak_evidence_unreviewed` to `strict_weak_evidence_unreviewed` via `gate_id.replace('-','_')` → matches this dest.

#### Change 2: Add `_check_weak_evidence_unreviewed_gate` function

**Region:** After `_check_single_event_global_synchronic_gate` function (~line 1390), before `_check_completeness_gate`.

```python
def _check_weak_evidence_unreviewed_gate(
    run_dir: Path,
    manifest: dict,
    args,
    audit_path: Path,
    close_id: str,
    units_payload: dict,
    actor: str,
    actor_kind: str,
) -> int:
    """AC3.1/AC3.3: Warn (or abort) when a weak_evidence_review close has flagged
    review items lacking acknowledged_by.

    Fires only for hypothesis.weak_evidence_review closes.
    Returns 0 (GATE_WARN or gate skipped) or 1 (GATE_ABORT in strict mode).
    """
    review_items = units_payload.get("review_items", [])
    if not isinstance(review_items, list):
        return 0
    unresolved = [
        item.get("claim_id", f"item[{i}]")
        for i, item in enumerate(review_items)
        if isinstance(item, dict)
        and item.get("outcome") == "flagged"
        and not item.get("acknowledged_by")
    ]
    if unresolved:
        return _evaluate_gate(
            "weak_evidence_unreviewed",
            run_dir, manifest, args, audit_path, close_id,
            stage="hypothesis", substep="weak_evidence_review",
            scope=getattr(args, "scope", "global"),
            actor=actor, actor_kind=actor_kind,
            extra_details={"unresolved_claim_ids": unresolved},
        )
    return 0
```

#### Change 3: Wire gate in `cmd_close` for `hypothesis.weak_evidence_review`

**Region:** `cmd_close`, after the `single_event_global_synchronic` gate block (~line 1794–1802).

Add:
```python
# AC3.1/AC3.3: weak_evidence_unreviewed gate — warn/abort on flagged items without acknowledged_by
if args.stage == "hypothesis" and args.substep == "weak_evidence_review":
    weu_rc = _check_weak_evidence_unreviewed_gate(
        run_dir, manifest, args, audit_path, close_id,
        units_payload=units_payload,
        actor=args.actor,
        actor_kind=getattr(args, "actor_kind", "subagent"),
    )
    if weu_rc != 0:
        return _abort("weak_evidence_unreviewed")
```

Note: `units_payload` is already loaded in `cmd_close` before this point (used by `undeclared_input` gate at ~line 1775). Confirm the variable name is `units_payload` at insertion point (it is, per line 1775 usage).

---

### File: `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`

**DO-NOT-TOUCH zones (plan 2):** `inputs_consumed` echo rule (lines ~232–239), isolation sections. **DO-NOT-TOUCH zones (plan 3):** generic-synchronic within-gidu grouping, generic-diachronic pattern sections.

**Region:** After the `#### Claim-level evidence schema` section (after the claim JSON example + prose note added in Phase 2, ~line 207+), before the `## Reasoning` section.

Add new `### Weak evidence review` section:

```markdown
### Weak evidence review

For `hypothesis.weak_evidence_review` (scope: `global`), you receive all
`candidate_drafting` artifacts (one per DV focus). For every claim across all candidates:

1. Look up the claim by `claim_id`.
2. Apply the four checks:

   **thin_support** — Flag if `n_transcripts < 3`. Fewer than three transcripts providing
   support is insufficient for a cross-participant pattern claim.

   **single_iv_level** — Flag if `n_iv_levels_covered < 2`. A claim spanning only one IV
   score category does not demonstrate level-dependence.

   **causal_language** — Flag if `uncertainty_language` contains causal verbs: "causes",
   "leads to", "produces", "results in". Interview findings are observational (Pearl rung 1:
   association); causal verbs imply intervention or counterfactual framing.

   **rung_appropriateness** — Stub: record whether the claim's rung label is consistent
   with its evidence type. Mark `"stub": true` for now; plan 5 gives this teeth.

3. Determine `outcome`: `"flagged"` if ANY check fired; `"pass"` otherwise.
4. If flagged, note the analyst's rationale in `notes`. If an analyst has acknowledged
   a flagged finding, record `acknowledged_by: "<analyst-id>"` in the review item.

Your JSON output (`hypotheses/review_summary.json`) MUST carry:
```json
{
  "claim_ids": ["c1", "c2", ...],   // full roster of all claim_ids reviewed
  "review_items": [
    {
      "claim_id": "c1",
      "checks": {
        "thin_support": true,
        "single_iv_level": false,
        "causal_language": false,
        "rung_appropriateness": {"stub": true}
      },
      "outcome": "flagged",
      "notes": "<rationale>",
      "acknowledged_by": "<analyst-id or omit if unacknowledged>"
    }
  ],
  "inputs_consumed": ["<path to each candidate artifact read>"]
}
```

Every `claim_id` listed in `claim_ids` must appear in `review_items` — the schema rejects
incomplete coverage. A close with any `flagged` item lacking `acknowledged_by` triggers the
`weak_evidence_unreviewed` gate (warn by default; strict if `study.strict_gates` includes
`"weak_evidence_unreviewed"` or `--strict-weak-evidence-unreviewed` is passed to `mpi_step.py close`).
```

---

### New tests (add to `tests/test_hypothesis_evidence.py`)

**Test class:** `class TestAC3_ReviewGate:` (using tmp_path + `_setup_cross_run_dir` fixture from `test_mpi_cross_analyst_contract.py`)

**Setup pattern:** Mirror `_setup_cross_run_dir` from `test_mpi_cross_analyst_contract.py` — create a tmp git repo with `.mpi/project.json` manifest pre-seeded with completed prerequisites (all generic_diachronic/generic_synchronic/global_synchronic done), then call `mpi_step.main()` or use subprocess to invoke `mpi_step.py close`. Alternatively, call `_check_weak_evidence_unreviewed_gate` directly if the function is importable.

**Approach:** Import `mpi_step._check_weak_evidence_unreviewed_gate` directly for unit-level gate testing, and use full `mpi_step.main` close invocations for integration tests.

```python
def test_AC3_1_flagged_unacknowledged_triggers_warn(tmp_path):
    """AC3.1 Success: close with flagged item lacking acknowledged_by emits
    weak_evidence_unreviewed gate_warning (warn mode — close succeeds)."""
    # Build a minimal run dir with all prerequisites done.
    # Write a review_summary.json with one flagged item, no acknowledged_by.
    # Call mpi_step close for hypothesis.weak_evidence_review.
    # Assert close exits 0 (warn mode) and audit.jsonl contains gate_warning with gate_id=weak_evidence_unreviewed.

def test_AC3_2_all_flagged_acknowledged_closes_clean(tmp_path):
    """AC3.2 Success: all flagged items carry acknowledged_by → close succeeds,
    no weak_evidence_unreviewed warning."""
    # Same setup but review_summary.json has acknowledged_by on flagged item.
    # Assert close exits 0, no gate_warning for weak_evidence_unreviewed in audit.

def test_AC3_3_strict_flag_blocks_unacknowledged(tmp_path):
    """AC3.3 Success: --strict-weak-evidence-unreviewed flag → close exits nonzero
    when flagged item lacks acknowledged_by."""
    # Same as AC3.1 but pass --strict-weak-evidence-unreviewed to close.
    # Assert exit code != 0.

def test_AC3_3_strict_gates_manifest_blocks_unacknowledged(tmp_path):
    """AC3.3 variant: study.strict_gates including 'weak_evidence_unreviewed'
    blocks the close."""
    # Same as AC3.3 but add {"weak_evidence_unreviewed"} to manifest study.strict_gates.
    # No CLI flag. Assert exit code != 0.

def test_AC3_4_cross_analyst_md_has_weak_evidence_review_section():
    """AC3.4 Success: mpi-cross-analyst.md contains the Weak evidence review section
    with the three check names."""
    # Load mpi-cross-analyst.md
    # Assert "Weak evidence review" section present
    # Assert "thin_support" in content
    # Assert "single_iv_level" in content
    # Assert "causal_language" in content
    # Assert "n_transcripts < 3" in content
```

**Additional contract test (extend `test_close_enforcement_2.py` or `test_hypothesis_evidence.py`):**

```python
def test_AC3_4_weak_evidence_unreviewed_gate_in_registry():
    """AC3.4: weak_evidence_unreviewed gate is in GATES registry with warn_or_abort posture."""
    from _mpi_schemas import GATES
    assert "weak_evidence_unreviewed" in GATES
    assert GATES["weak_evidence_unreviewed"]["posture"] == "warn_or_abort"
    assert GATES["weak_evidence_unreviewed"]["stage"] == "hypothesis"
```

---

## Baseline preservation

- Baseline test status: `python -m pytest tests/ -q` → 1 failed (test_verify_mpi_init.py::test_all, known environmental), 145 passed, 5 skipped.
- No new failures beyond the known baseline.
- Existing `tests/test_hypothesis_generation.py` tests (AC6.1–6.3, old numbering) must still pass — they test markdown structure, not JSON schema; `claim_id` addition does not break them.
- Plugin-internal tests: `python -m pytest microphenomenograph/1.0.0/scripts/ -q` must continue to pass.

## Deferred (out of scope)

Per design doc: `replication_recommendation`, `rung`/`assumptions`/`confounders`/`testable_implications`, substantive `rung_appropriateness` check — all deferred to plan 5.

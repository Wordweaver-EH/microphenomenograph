# IRR Fidelity Implementation Plan

_Design:_ `docs/design-plans/2026-06-05-irr-fidelity.md`
_Branch:_ `remediation-2026-06-05`
_Baseline:_ 1 known failure (`tests/test_verify_mpi_init.py::test_all`, environmental), 145 passed, 5 skipped. Green criterion: no new failures beyond this baseline.

---

## Terminology note (design typo)

The DoD (line 12 of design doc) says `same_model | heterogeneous_model`; the ACs, Glossary, and Architecture all say `intra_model | heterogeneous_model`. The ACs govern test assertions. Use **`intra_model`** everywhere. The DoD `same_model` is a typo.

---

## Phase 1: Alignment-inversion fix + regression tests

**Goal:** LLM-proposed label alignments are actually applied in all agreement metrics.
**ACs covered:** irr-fidelity.AC1.1, AC1.2, AC1.3, AC1.4
**Dependencies:** None.

### 1.1 Bug diagnosis

Two sites in `microphenomenograph/1.0.0/scripts/irr.py` build the alignment map with the wrong orientation:

**Site A — `compute_coincidence` (lines ~216–222):**
```python
# BUG: builds primary → alternate but looks up alternate labels
alignment_map[primary_cat] = alternate_cat   # wrong direction
...
if cat_b in alignment_map:                   # cat_b is alternate; lookup fails
```

**Site B — `compute_irr` (lines ~703–712):**
```python
# BUG: builds primary → alternate but looks up alternate labels  
alignment_map[entry.get("primary")] = entry.get("alternate")   # wrong direction
...
if label in alignment_map:     # label is alternate; lookup fails
```

Both must swap to `alignment_map[alternate_cat] = primary_cat` (alternate → primary). The lookup code at each site is already correct for the `alternate → primary` direction once the build is fixed.

### 1.2 Edits to `microphenomenograph/1.0.0/scripts/irr.py`

**Site A — `compute_coincidence`, update comment + map build:**

Region to change (lines ~216–222):
```python
# Build alignment mapping: primary category → alternate category
alignment_map = {}
for entry in alignment:
    primary_cat = entry.get("primary")
    alternate_cat = entry.get("alternate")
    if primary_cat and alternate_cat:
        alignment_map[primary_cat] = alternate_cat
```

Replace with:
```python
# Build alignment mapping: alternate category → primary category
alignment_map = {}
for entry in alignment:
    primary_cat = entry.get("primary")
    alternate_cat = entry.get("alternate")
    if primary_cat and alternate_cat:
        alignment_map[alternate_cat] = primary_cat
```

The lookup block at lines ~243–247 (`if cat_b in alignment_map: cat_b_aligned = alignment_map[cat_b]`) remains unchanged — it already reads correctly as "look up cat_b (alternate) to get the primary-namespace label".

**Site B — `compute_irr`, update map build in bootstrap section (lines ~703–705):**

Region to change:
```python
alignment_map = {}
for entry in alignment:
    alignment_map[entry.get("primary")] = entry.get("alternate")
```

Replace with:
```python
alignment_map = {}
for entry in alignment:
    alignment_map[entry.get("alternate")] = entry.get("primary")
```

The application block at lines ~707–712 (`if label in alignment_map: labels_alternate_aligned.append(alignment_map[label])`) remains unchanged.

No other logic changes. `alpha_sensitivity` at line ~801 calls `compute_coincidence` with `high_conf_alignment`, so it picks up the fix automatically.

### 1.3 Pre-existing test behavior

The existing tests in `microphenomenograph/1.0.0/scripts/test_irr.py` and `tests/test_irr_calibration.py` use:
- **Empty alignment** (`alignment=[]`): unaffected by the map direction fix.
- **Symmetric alignment** (`"primary": "cat0", "alternate": "cat0"` — same string): in `alignment_map[cat0] = cat0`; both directions are identical.

No existing test pins a post-alignment α value that the fix would flip. AC3.2 is therefore safe with the fix.

### 1.4 New tests in `microphenomenograph/1.0.0/scripts/test_irr.py`

Add two new test functions:

---

**`test_alignment_disjoint_labels_full_agreement`** (covers AC1.1, AC1.3)

Purpose: Disjoint label sets (primary uses {A, B}, alternate uses {X, Y}) with full alignment (X→A, Y→B) where utterance assignments are identical in structure. After alignment, every alternate label maps to the matching primary label, so all (primary, aligned_alternate) pairs land on the diagonal → α = 1.0.

Fixture:
```python
# 10 utterances; primary uses A/B; alternate uses X/Y for same structure
primary    = {"1":"A","2":"A","3":"A","4":"A","5":"A",
              "6":"B","7":"B","8":"B","9":"B","10":"B"}
alternate  = {"1":"X","2":"X","3":"X","4":"X","5":"X",
              "6":"Y","7":"Y","8":"Y","9":"Y","10":"Y"}
# Full alignment: X→A, Y→B
alignment  = [{"primary":"A","alternate":"X","confidence":0.9,"rationale":"same"},
              {"primary":"B","alternate":"Y","confidence":0.9,"rationale":"same"}]
```

Assertions:
1. `categories, matrix = compute_coincidence(primary, alternate, alignment, [], [])` → `alpha_nominal(categories, matrix)` ≈ 1.0 (±0.001) — **AC1.1**
2. Control: `categories0, matrix0 = compute_coincidence(primary, alternate, [], [], [])` → `alpha_nominal(categories0, matrix0)` ≪ 1.0 (assert < 0.2, since all 10 alternate labels are in wrong namespace) — **AC1.3**

---

**`test_alignment_partial_keeps_unaligned_distinct`** (covers AC1.4)

Purpose: Partial alignment — only one pair mapped, unaligned alternate label stays distinct in the coincidence matrix.

Fixture:
```python
# 6 utterances; primary {A,B}; alternate {X,Y,Z}
# Only X is aligned to A; Y and Z are unaligned
primary   = {"1":"A","2":"A","3":"A","4":"B","5":"B","6":"B"}
alternate = {"1":"X","2":"X","3":"X","4":"Y","5":"Y","6":"Z"}
alignment = [{"primary":"A","alternate":"X","confidence":0.9,"rationale":""}]
unmatched_alternate = ["Y", "Z"]
```

Assertions:
1. After `compute_coincidence(primary, alternate, alignment, [], unmatched_alternate)`:
   - "Y" IS in `sorted_categories` (unaligned, stays distinct)
   - "Z" IS in `sorted_categories` (unaligned, stays distinct)
   - `matrix[("A","A")]` == 3.0 (utterances 1-3: primary A, X remapped to A)
   - `matrix[("B","Y")]` == 2.0 (utterances 4-5: primary B, alternate Y unaligned)
   - `matrix[("B","Z")]` == 1.0 (utterance 6: primary B, alternate Z unaligned)
   - X stays in `sorted_categories` as a zero-marginal phantom (the category set is built before remapping); assert all `matrix[(c,"X")]` and `matrix[("X",c)]` sum to 0.0 across all c

---

**`test_compute_irr_with_disjoint_alignment`** — add to `tests/test_irr_calibration.py` (covers AC1.2)

Purpose: End-to-end through `compute_irr` bootstrap path with disjoint full-alignment fixture.

```python
primary   = {"1":"A","2":"A","3":"A","4":"A","5":"A",
             "6":"B","7":"B","8":"B","9":"B","10":"B"}
alternate = {"1":"X","2":"X","3":"X","4":"X","5":"X",
             "6":"Y","7":"Y","8":"Y","9":"Y","10":"Y"}
alignment = [{"primary":"A","alternate":"X","confidence":0.9,"rationale":"same"},
             {"primary":"B","alternate":"Y","confidence":0.9,"rationale":"same"}]
```

Call: `compute_irr(primary, alternate, alignment, [], [], n_utterances=10, bootstrap_seed=42, n_bootstrap=500)`

Assertions:
1. `record["metrics"]["alpha"]["point"]` ≈ 1.0 (±0.001) — **AC1.2 headline**
2. `record["outcome"] == "passed"` — **AC1.2 outcome**
3. Control: same call with `alignment=[]` → `alpha_point` < 0.5 (discriminates aligned from unaligned)

Note: use `n_bootstrap=500` (not 5000) for test speed; the fixture is deterministic.

### 1.5 Update `__name__ == "__main__"` runner lists

In `microphenomenograph/1.0.0/scripts/test_irr.py`, add both new test functions to the `tests` list at line ~343.

In `tests/test_irr_calibration.py`, add `test_compute_irr_with_disjoint_alignment` to the `tests` list at line ~403.

### 1.6 Done when

- Both new tests in `test_irr.py` pass.
- `test_compute_irr_with_disjoint_alignment` in `tests/test_irr_calibration.py` passes.
- All previously passing tests still pass (AC3.2 — no existing test pins a buggy-α value that changes).

---

## Phase 2: rater_kind relabeling + heterogeneous-model support + isolation rule

**Goal:** Same-model IRR is honestly labeled; schema enforces `rater_kind` + `caveat`; SKILL.md and agent doc carry isolation rules.
**ACs covered:** irr-fidelity.AC2.1, AC2.2, AC2.3, AC3.1, AC3.2
**Dependencies:** Phase 1 (same files; meaningful α values required for caveat to be non-misleading; no hard code dependency).

### 2.1 Constants to add in `microphenomenograph/1.0.0/scripts/irr.py`

Add module-level constants immediately after `DEFAULT_CALIBRATION_MODE`:

```python
RATER_KIND_INTRA = "intra_model"
RATER_KIND_HETERO = "heterogeneous_model"

CAVEAT_INTRA_MODEL = (
    "This agreement score is intra-model consistency (test-retest reliability): "
    "both analysts are the same model and share systematic biases, so agreement "
    "measures stability, not validity. Correlated errors inflate agreement "
    "(Correlated Errors in LLMs, ICML 2025). Treat alpha >= threshold as "
    "necessary but not sufficient for quality. Thresholds (0.667/0.8) are "
    "borrowed from human-analyst Krippendorff conventions; no LLM-specific "
    "threshold exists in the literature."
)

CAVEAT_HETEROGENEOUS_MODEL = (
    "This agreement score reflects heterogeneous-model inter-rater reliability: "
    "the two analysts are different models, reducing shared systematic bias. "
    "Agreement is more indicative of genuine consensus than intra-model runs, "
    "but model-specific biases may still inflate scores. Thresholds (0.667/0.8) "
    "are borrowed from human-analyst Krippendorff conventions."
)
```

These are the verbatim strings that land in the record and are asserted by tests. Having them as module constants prevents brittle literal duplication between `irr.py` and tests.

### 2.2 Derive `rater_kind` + `caveat` in `compute_irr`

In `compute_irr`, after the parameters are received and before building the record, add derivation logic:

```python
# Derive rater_kind and caveat
if alternate_model and alternate_model != primary_model:
    rater_kind = RATER_KIND_HETERO
    caveat = CAVEAT_HETEROGENEOUS_MODEL
else:
    rater_kind = RATER_KIND_INTRA
    caveat = CAVEAT_INTRA_MODEL
```

Add `rater_kind` and `caveat` to the returned `record` dict (alongside existing fields):

```python
record = {
    ...
    "rater_kind": rater_kind,
    "caveat": caveat,
    ...
}
```

### 2.3 Schema update in `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

`_validate_irr_calibration_agreement_computation` currently requires `["stage", "participant_id", "metrics", "outcome"]`.

Extend to require `rater_kind` and `caveat`:

```python
def _validate_irr_calibration_agreement_computation(payload: dict) -> list[SchemaError]:
    return _require_keys(
        payload,
        ["stage", "participant_id", "metrics", "outcome", "rater_kind", "caveat"],
        "payload"
    )
```

**Scope note:** `aggregate_stratum_records` output is appended directly to `irr_calibration.jsonl` without going through `mpi_step.py close`, so this validator is never called for aggregate records. No change needed in `aggregate_stratum_records`.

**Impact on existing tests:** `test_mpi_step.py` pre-writes raw IRR records directly to `irr_calibration.jsonl` (not through `mpi_step.py close --stage irr_calibration --substep agreement_computation`), so those records bypass the validator — no breakage. The `test_irr_calibration.py::test_irr_jsonl_schema` test needs updating (see §2.5).

### 2.4 New unit tests in `microphenomenograph/1.0.0/scripts/test_irr.py`

Add two test functions:

---

**`test_rater_kind_intra_model`** (covers AC2.1)

Verifies that absent or equal `alternate_model` produces `rater_kind == "intra_model"` with the correct caveat.

```python
primary   = {"1":"A","2":"A","3":"B","4":"B"}
alternate = {"1":"A","2":"A","3":"B","4":"B"}
```

Case 1: `compute_irr(..., primary_model="claude-sonnet-4-5", alternate_model="")` →
- `record["rater_kind"] == "intra_model"`
- `record["caveat"] == CAVEAT_INTRA_MODEL`

Case 2: `compute_irr(..., primary_model="claude-sonnet-4-5", alternate_model="claude-sonnet-4-5")` →
- `record["rater_kind"] == "intra_model"`
- `record["caveat"] == CAVEAT_INTRA_MODEL`

Case 3: `compute_irr(..., primary_model="", alternate_model="")` →
- `record["rater_kind"] == "intra_model"`

---

**`test_rater_kind_heterogeneous_model`** (covers AC2.2)

Verifies that differing `alternate_model` produces `rater_kind == "heterogeneous_model"`.

```python
primary   = {"1":"A","2":"A","3":"B","4":"B"}
alternate = {"1":"A","2":"A","3":"B","4":"B"}
record = compute_irr(
    ..., primary_model="claude-sonnet-4-5", alternate_model="claude-opus-4",
    n_bootstrap=100
)
```

Assertions:
- `record["rater_kind"] == "heterogeneous_model"`
- `record["caveat"] == CAVEAT_HETEROGENEOUS_MODEL`

Note: Do NOT assert `"intra" not in record["caveat"]` — `CAVEAT_HETEROGENEOUS_MODEL` contains the phrase "intra-model runs" for comparison purposes, so that substring check would fail. The equality assertion `record["caveat"] == CAVEAT_HETEROGENEOUS_MODEL` is the definitive check.

---

Also add `CAVEAT_INTRA_MODEL` and `CAVEAT_HETEROGENEOUS_MODEL` to the import list at the top of `test_irr.py`:
```python
from irr import (
    ...,
    RATER_KIND_INTRA, RATER_KIND_HETERO,
    CAVEAT_INTRA_MODEL, CAVEAT_HETEROGENEOUS_MODEL,
)
```

### 2.5 Schema-rejection test in `tests/test_irr_calibration.py`

**Update `test_irr_jsonl_schema`:** Add `"rater_kind"` and `"caveat"` to the `required_fields` list and assert both are present in `compute_irr`'s return value.

**Add `test_agreement_computation_schema_rejects_missing_rater_kind`** (covers AC2.3):

```python
def test_agreement_computation_schema_rejects_missing_rater_kind():
    """AC2.3: Schema validator rejects agreement_computation record missing rater_kind or caveat."""
    from _mpi_schemas import validate_units
    
    # Valid payload missing rater_kind
    payload_no_rk = {
        "stage": "diachronic",
        "participant_id": "p1s1",
        "metrics": {"alpha": {"point": 0.8}},
        "outcome": "passed",
        "caveat": "some caveat",
        # rater_kind deliberately omitted
    }
    errors = validate_units("irr_calibration", "agreement_computation", payload_no_rk)
    assert any("rater_kind" in str(e) for e in errors), (
        f"Expected schema error for missing rater_kind, got: {errors}"
    )
    
    # Valid payload missing caveat
    payload_no_caveat = {
        "stage": "diachronic",
        "participant_id": "p1s1",
        "metrics": {"alpha": {"point": 0.8}},
        "outcome": "passed",
        "rater_kind": "intra_model",
        # caveat deliberately omitted
    }
    errors2 = validate_units("irr_calibration", "agreement_computation", payload_no_caveat)
    assert any("caveat" in str(e) for e in errors2), (
        f"Expected schema error for missing caveat, got: {errors2}"
    )
    
    # Full valid payload (both fields present) passes
    payload_valid = {
        "stage": "diachronic",
        "participant_id": "p1s1",
        "metrics": {"alpha": {"point": 0.8}},
        "outcome": "passed",
        "rater_kind": "intra_model",
        "caveat": "some caveat text",
    }
    errors3 = validate_units("irr_calibration", "agreement_computation", payload_valid)
    assert errors3 == [], f"Valid payload should have no errors, got: {errors3}"
    
    print("[PASS] agreement_computation schema rejects missing rater_kind/caveat")
```

Note: `_mpi_schemas` is importable from `tests/` because `scripts/` is on `sys.path` via conftest or the path manipulation in the test file (follow the same pattern as existing `tests/test_irr_calibration.py`).

### 2.6 Edits to `microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md` (covers AC3.1)

Add/revise the following sections. Do NOT introduce the term "self-consistency".

**Revise "Overview" paragraph** to describe the calibration as "intra-model consistency (test-retest reliability)" when both analysts are the same model. Add a sentence: "When both analysts are the same model, the resulting score is intra-model consistency — it measures stability, not validity, because both instances share systematic biases."

**Add "Rater kind and caveats" section** (new section after Overview):

```markdown
## Rater kind and caveats

Every IRR record carries a `rater_kind` field:

| `rater_kind` | Condition | Interpretation |
|---|---|---|
| `intra_model` | Both analysts are the same model (or `alternate_model` absent/equal to `primary_model`) | Intra-model consistency / test-retest reliability. Measures stability, not validity. Correlated errors inflate agreement (Correlated Errors in LLMs, ICML 2025). Treat α ≥ threshold as necessary but not sufficient. |
| `heterogeneous_model` | `alternate_model` differs from `primary_model` | Heterogeneous-model IRR. Reduces shared systematic bias. More indicative of genuine consensus, but model-specific biases may still inflate scores. |

Thresholds (α ≥ 0.667 tentative, ≥ 0.8 acceptable) are borrowed from Krippendorff's conventions for **human** analysts after training. No LLM-specific threshold exists in the literature; treat these as conventions, not evidence.

**Pre-fix records:** Any IRR record produced before the alignment-map fix (irr-fidelity plan 1) is not comparable to post-fix records — α was computed on unaligned labels. Re-run calibration if a pre-fix record exists in `.mpi/irr_calibration.jsonl`.
```

**Add "Alternate-analyst isolation" section:**

```markdown
## Alternate-analyst isolation

The alternate analyst MUST NOT read any files under `analyses/` (primary analyst outputs).
Isolation is required for the two runs to be genuinely independent.

When writing the `irr_calibration.independent_analyst` prompt artifact, the analyst MUST
include an explicit isolation statement confirming that no primary-analyst artifacts were
read before producing this alternate analysis. Example:
```json
{
  "isolation_statement": "I did not read any files under analyses/ before producing this alternate analysis."
}
```

This field is auditable: the prompt artifact is retained with the close record.
```

### 2.7 Edits to `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` (covers AC3.1)

In the "IRR calibration substeps" section (under `irr_calibration.independent_analyst`), add:

```markdown
**Isolation requirement:** Before producing the alternate analysis, do NOT read any files
under `analyses/` (primary analyst outputs). The prompt artifact for this substep MUST
include an `isolation_statement` field confirming no primary-analyst artifacts were read.
```

### 2.8 Documentation assertion test in `tests/test_mpi_cross_analyst_contract.py` or new `tests/test_irr_fidelity_docs.py` (covers AC3.1)

Add a test file `tests/test_irr_fidelity_docs.py` with:

```python
def test_skill_md_contains_intra_model_label():
    """AC3.1: mpi-irr SKILL.md uses 'intra-model consistency' terminology."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert "intra-model consistency" in content, (
        "SKILL.md must label same-model metrics 'intra-model consistency'"
    )
    assert "self-consistency" not in content, (
        "SKILL.md must not use 'self-consistency' (collides with Wang et al. CoT decoding)"
    )

def test_skill_md_contains_isolation_rule():
    """AC3.1: mpi-irr SKILL.md contains alternate-analyst no-analyses-dir rule."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert "must not read" in content.lower() or "MUST NOT read" in content, (
        "SKILL.md must contain no-reading-analyses/ isolation rule"
    )
    assert "isolation_statement" in content, (
        "SKILL.md must require isolation_statement in prompt artifact"
    )

def test_cross_analyst_contains_isolation_rule():
    """AC3.1: mpi-cross-analyst.md contains alternate-analyst isolation instruction."""
    content = CROSS_ANALYST.read_text(encoding="utf-8")
    assert "isolation" in content.lower(), (
        "mpi-cross-analyst.md must contain isolation instruction for independent_analyst substep"
    )
    assert "isolation_statement" in content, (
        "mpi-cross-analyst.md must require isolation_statement field in prompt artifact"
    )
```

### 2.9 Update `__name__ == "__main__"` runner lists

In `microphenomenograph/1.0.0/scripts/test_irr.py`, add `test_rater_kind_intra_model` and `test_rater_kind_heterogeneous_model` to the `tests` list.

In `tests/test_irr_calibration.py`, add `test_agreement_computation_schema_rejects_missing_rater_kind` to the `tests` list.

### 2.10 Done when

- `test_rater_kind_intra_model` and `test_rater_kind_heterogeneous_model` pass.
- `test_irr_jsonl_schema` still passes (updated to include `rater_kind`/`caveat` assertions).
- `test_agreement_computation_schema_rejects_missing_rater_kind` passes.
- `test_irr_fidelity_docs.py` tests pass.
- All previously passing tests still pass.

---

## File index

| File | Phase | Edit type |
|---|---|---|
| `microphenomenograph/1.0.0/scripts/irr.py` | 1 + 2 | Fix alignment map at 2 sites (Ph1); add constants + `rater_kind`/`caveat` derivation + record fields (Ph2) |
| `microphenomenograph/1.0.0/scripts/test_irr.py` | 1 + 2 | Add `test_alignment_disjoint_labels_full_agreement`, `test_alignment_partial_keeps_unaligned_distinct` (Ph1); add `test_rater_kind_intra_model`, `test_rater_kind_heterogeneous_model` (Ph2) |
| `tests/test_irr_calibration.py` | 1 + 2 | Add `test_compute_irr_with_disjoint_alignment` (Ph1); update `test_irr_jsonl_schema`, add `test_agreement_computation_schema_rejects_missing_rater_kind` (Ph2) |
| `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` | 2 | Add `rater_kind`, `caveat` to `_validate_irr_calibration_agreement_computation` |
| `microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md` | 2 | Add rater-kind table, intra-model caveat, isolation rule, pre-fix warning |
| `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` | 2 | Add isolation instruction + `isolation_statement` requirement to `independent_analyst` section |
| `tests/test_irr_fidelity_docs.py` | 2 | New file: doc-string assertions for AC3.1 |

---

## AC coverage matrix

| AC | Test | Phase |
|---|---|---|
| AC1.1 | `test_irr.py::test_alignment_disjoint_labels_full_agreement` (α≈1.0 assertion) | 1 |
| AC1.2 | `test_irr_calibration.py::test_compute_irr_with_disjoint_alignment` | 1 |
| AC1.3 | `test_irr.py::test_alignment_disjoint_labels_full_agreement` (control: α≪1.0 without alignment) | 1 |
| AC1.4 | `test_irr.py::test_alignment_partial_keeps_unaligned_distinct` | 1 |
| AC2.1 | `test_irr.py::test_rater_kind_intra_model` | 2 |
| AC2.2 | `test_irr.py::test_rater_kind_heterogeneous_model` | 2 |
| AC2.3 | `test_irr_calibration.py::test_agreement_computation_schema_rejects_missing_rater_kind` | 2 |
| AC3.1 | `tests/test_irr_fidelity_docs.py::test_skill_md_contains_intra_model_label`, `test_skill_md_contains_isolation_rule`, `test_cross_analyst_contains_isolation_rule` | 2 |
| AC3.2 | Confirmed: no existing test pins a post-alignment α that changes under the fix (all existing alignment-bearing tests use empty or symmetric alignment). Verified by inspection of `test_irr.py` and `test_irr_calibration.py`. | Implicit |

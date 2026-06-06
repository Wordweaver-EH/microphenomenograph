# Implementation Plan: analysis-fidelity

_Design doc:_ `docs/design-plans/2026-06-05-analysis-fidelity.md`
_Branch:_ `remediation-2026-06-05`
_Date:_ 2026-06-06

## Summary

Three parallel-safe phases, each addressing a distinct actor file group. No control-flow
changes anywhere. Phase 1 covers `mpi-cross-analyst.md` + its schema validators (AC1, AC2).
Phase 2 covers `mpi-analyst.md` + diachronic schema (AC3, AC4). Phase 3 covers
`mpi-init/SKILL.md` and `mpi-transcript-prep/SKILL.md` (AC5, AC6) — both are
markdown-documented, orchestrator-executed steps, so tests use simulation harnesses
(same pattern as `test_verify_mpi_init.py` and `test_transcript_prep.py`).

All new tests go in `tests/test_analysis_fidelity.py` (single file, class-per-AC).
Schema tests import `_mpi_schemas` via `sys.path.insert` (same as `test_mpi_step.py`).
Plugin-internal unit tests (`microphenomenograph/1.0.0/scripts/test_mpi_step.py`) receive
no new tests from this plan — only `tests/` is extended.

---

## Phase 1: Cross-analyst grouping + pattern fidelity

**Goal:** Enforce within-IDU grouping for generic-synchronic; add common/optional semantics
to generic-diachronic pattern_identification schema; update agent instructions.

**Covers:** AC1.1, AC1.2, AC2.1, AC2.2, AC2.3

### 1A. Agent instruction edit — `mpi-cross-analyst.md`

File: `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`

**Generic synchronic (lines 88–101 — the "ISU grouping rule" block):**
- Remove the current instruction that says to "flatten all ISUs from all IDU groups" and
  group by semantic similarity regardless of source IDU.
- Replace with: ISUs are grouped **within** the target generic IDU (`payload.generic_idu`);
  cross-IDU synthesis belongs to global synchronic, not here. Each ISU in the JSON output
  MUST include `source_generic_idu` (string) equal to the scope's generic IDU identifier;
  the schema rejects any ISU where it is absent or mismatched.
- Preserve the existing source-citation documentation note (participant + suggestion tracing).

**Generic diachronic pattern instructions (lines 62–86 — the tabular output section):**
- Add after the per-category output format block: each pattern entry in JSON MUST include:
  - `common_idus`: non-empty list — IDUs that appear in ≥ 2 participants for this pattern
    (invariant elements)
  - `optional_idus`: list (may be empty) — IDUs appearing in some but not all participants
    (optional elements)
  - `covered_participant_keys`: non-empty list of strings (e.g. `["p1s1", "p3s1"]`)
  - Merge-evaluation criterion: when two candidate patterns are structurally similar, merge
    them; add `merge_rationale` to the pattern record. When pattern count exceeds 5, add
    `high_count_justification`.

### 1B. Schema edit — `_mpi_schemas.py`

File: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**`_validate_generic_synchronic_isu_second_level` (lines 274–283):**

Extend the per-ISU loop to also check `source_generic_idu`:
```python
# after existing _validate_isu call:
generic_idu = payload.get("generic_idu")
if "source_generic_idu" not in isu:
    errors.append(SchemaError(
        f"payload.isus[{i}].source_generic_idu",
        "required field missing"
    ))
elif generic_idu is not None and isu["source_generic_idu"] != generic_idu:
    errors.append(SchemaError(
        f"payload.isus[{i}].source_generic_idu",
        f"must equal payload.generic_idu ({generic_idu!r}), "
        f"got {isu['source_generic_idu']!r}"
    ))
```

**`_validate_generic_diachronic_pattern_identification` (lines 233–242):**

Extend the per-pattern loop to validate `common_idus`, `optional_idus`,
`covered_participant_keys`:
```python
# after existing _check_utterance_refs call:
# common_idus: required, non-empty list
common = pat.get("common_idus")
if common is None:
    errors.append(SchemaError(
        f"payload.patterns[{i}].common_idus",
        "required field missing (non-empty list of common IDU labels)"
    ))
elif not isinstance(common, list) or len(common) == 0:
    errors.append(SchemaError(
        f"payload.patterns[{i}].common_idus",
        "must be a non-empty list"
    ))
# optional_idus: required, may be empty
if "optional_idus" not in pat:
    errors.append(SchemaError(
        f"payload.patterns[{i}].optional_idus",
        "required field missing (list, may be empty)"
    ))
elif not isinstance(pat["optional_idus"], list):
    errors.append(SchemaError(
        f"payload.patterns[{i}].optional_idus",
        "must be a list"
    ))
# covered_participant_keys: required, non-empty list of strings
cpk = pat.get("covered_participant_keys")
if cpk is None:
    errors.append(SchemaError(
        f"payload.patterns[{i}].covered_participant_keys",
        "required field missing (non-empty list of participant key strings)"
    ))
elif not isinstance(cpk, list) or len(cpk) == 0:
    errors.append(SchemaError(
        f"payload.patterns[{i}].covered_participant_keys",
        "must be a non-empty list"
    ))
else:
    for j, k in enumerate(cpk):
        if not isinstance(k, str):
            errors.append(SchemaError(
                f"payload.patterns[{i}].covered_participant_keys[{j}]",
                "must be a string participant key"
            ))
```

### 1C. Tests — `tests/test_analysis_fidelity.py`

New test file. Import pattern:
```python
import sys
from pathlib import Path
PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
from _mpi_schemas import validate_units
```

**Class `TestAC1_WithinIDUGrouping`:**

```python
def test_AC1_1_missing_source_generic_idu_rejected(self):
    """AC1.1 Failure: ISU without source_generic_idu rejected."""
    payload = {
        "event": "event1", "iv_category": "high", "generic_idu": "Initial Thoughts",
        "isus": [{
            "isu_name": "Test", "criteria": "The utterances...",
            "confidence": 3, "flag_for_review": False,
            "isu_second_level_of_abstraction": "Group",
            "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                "byte_start": 0, "byte_end": 5, "raw_excerpt": "hello"}],
            # source_generic_idu intentionally absent
        }]
    }
    errors = validate_units("generic_synchronic", "isu_second_level_grouping", payload)
    assert any("source_generic_idu" in e.field for e in errors)

def test_AC1_1_mismatched_source_generic_idu_rejected(self):
    """AC1.1 Failure: ISU source_generic_idu != payload.generic_idu rejected."""
    payload = {
        "event": "event1", "iv_category": "high", "generic_idu": "Initial Thoughts",
        "isus": [{
            "isu_name": "Test", "criteria": "The utterances...",
            "confidence": 3, "flag_for_review": False,
            "isu_second_level_of_abstraction": "Group",
            "source_generic_idu": "Different IDU",  # mismatch
            "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                "byte_start": 0, "byte_end": 5, "raw_excerpt": "hello"}],
        }]
    }
    errors = validate_units("generic_synchronic", "isu_second_level_grouping", payload)
    assert any("source_generic_idu" in e.field for e in errors)

def test_AC1_1_matching_source_generic_idu_accepted(self):
    """AC1.1 Success path: ISU source_generic_idu == payload.generic_idu accepted."""
    payload = {
        "event": "event1", "iv_category": "high", "generic_idu": "Initial Thoughts",
        "isus": [{
            "isu_name": "Test", "criteria": "The utterances...",
            "confidence": 3, "flag_for_review": False,
            "isu_second_level_of_abstraction": "Group",
            "source_generic_idu": "Initial Thoughts",  # matches
            "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                "byte_start": 0, "byte_end": 5, "raw_excerpt": "hello"}],
        }]
    }
    errors = validate_units("generic_synchronic", "isu_second_level_grouping", payload)
    assert errors == []

def test_AC1_2_agent_instructions_contain_within_gidu_rule(self):
    """AC1.2 Success: mpi-cross-analyst.md contains within-IDU grouping rule; no flatten instruction."""
    content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
    assert "flatten all ISUs from all IDU groups" not in content, (
        "The instruction to flatten across IDU groups must be removed"
    )
    assert "source_generic_idu" in content, (
        "mpi-cross-analyst.md must reference source_generic_idu field"
    )
```

**Class `TestAC2_PatternCommonOptional`:**

```python
def _minimal_pattern_payload(self, extra_fields=None):
    """Helper: valid pattern_identification payload with required new fields."""
    pat = {
        "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                            "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
        "common_idus": ["Initial Thoughts"],
        "optional_idus": [],
        "covered_participant_keys": ["p1s1"],
    }
    if extra_fields:
        pat.update(extra_fields)
    return {"event": "event1", "patterns": [pat]}

def test_AC2_1_pattern_without_common_idus_rejected(self):
    """AC2.1 Failure: pattern missing common_idus rejected."""
    payload = {
        "event": "event1",
        "patterns": [{
            "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
            # common_idus absent
            "optional_idus": [],
            "covered_participant_keys": ["p1s1"],
        }]
    }
    errors = validate_units("generic_diachronic", "pattern_identification", payload)
    assert any("common_idus" in e.field for e in errors)

def test_AC2_1_pattern_with_empty_common_idus_rejected(self):
    """AC2.1 Failure: pattern with empty common_idus rejected."""
    payload = {
        "event": "event1",
        "patterns": [{
            "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                                "byte_start": 0, "byte_end": 5, "raw_excerpt": "x"}],
            "common_idus": [],  # empty — invalid
            "optional_idus": [],
            "covered_participant_keys": ["p1s1"],
        }]
    }
    errors = validate_units("generic_diachronic", "pattern_identification", payload)
    assert any("common_idus" in e.field for e in errors)

def test_AC2_2_pattern_with_empty_optional_idus_accepted(self):
    """AC2.2 Success: pattern with empty optional_idus accepted (invariant patterns)."""
    errors = validate_units("generic_diachronic", "pattern_identification",
                            self._minimal_pattern_payload())
    assert errors == [], f"Unexpected errors: {errors}"

def test_AC2_2_pattern_with_optional_idus_populated_accepted(self):
    """AC2.2 Success variant: pattern with non-empty optional_idus also accepted."""
    payload = self._minimal_pattern_payload({"optional_idus": ["Side Note"]})
    errors = validate_units("generic_diachronic", "pattern_identification", payload)
    assert errors == []

def test_AC2_3_agent_instructions_contain_merge_criterion(self):
    """AC2.3 Success: mpi-cross-analyst.md mentions optimum-small-set/merge criterion."""
    content = (PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md").read_text(encoding="utf-8")
    # Either "merge" evaluation language or "optimum" small-set constraint
    assert ("merge" in content.lower() or "optimum" in content.lower()), (
        "mpi-cross-analyst.md must mention merge evaluation or optimum-small-set criterion"
    )
    assert "common_idus" in content, (
        "mpi-cross-analyst.md must reference common_idus in pattern instructions"
    )
    assert "optional_idus" in content, (
        "mpi-cross-analyst.md must reference optional_idus in pattern instructions"
    )
```

**Done when:** `pytest tests/test_analysis_fidelity.py::TestAC1_WithinIDUGrouping tests/test_analysis_fidelity.py::TestAC2_PatternCommonOptional -q` passes with no errors; existing `tests/test_cross_participant_analysis.py` still passes.

---

## Phase 2: Diachronic analyst-rule fidelity

**Goal:** Linkage-phrase boundary rule added to `mpi-analyst.md`; `idu_name`/`moment` made
optional at `criteria_grouping`/`criteria_revision` and required at `idu_naming_ordering`
(splitting the shared `_IDU_REQUIRED`).

**Covers:** AC3.1, AC4.1, AC4.2

### 2A. Agent instruction edit — `mpi-analyst.md`

File: `microphenomenograph/1.0.0/agents/mpi-analyst.md`

**Diachronic rule 4 (lines ~31–34, the "Split vs merge" / prefer-fewer-IDUs rule):**

Insert after rule 4 (before rule 5 "Naming") a new rule:
> **5. Temporal linkage phrases signal IDU boundaries.** Before applying the prefer-fewer-IDUs
> heuristic (rule 4), scan for explicit temporal-linkage phrases such as "and then",
> "after that", "at the beginning", "right at the end", "and then suddenly", "before
> that". When a phrase of this type appears in a participant utterance, treat it as a
> strong boundary signal: the experiential content described before the phrase belongs to
> a different IDU than the content described after it, and each segment should receive its
> own criteria sentence. This rule outranks the prefer-fewer-IDUs heuristic — do not merge
> across a linkage-phrase boundary even if the content seems superficially similar.
> Examples from the manual: "and then I noticed…" (start of new IDU), "right at the
> beginning…" (signals return to earlier moment).

Renumber the subsequent rules accordingly (current rules 5–9 become 6–10).

**Naming-deferred wording in the (now renumbered) "Naming" rule:**

Amend rule 6 (was rule 5, "Naming: IDU names are 2–5 words…") to add:
> **Defer naming until convergence.** At the `criteria_grouping` substep, `idu_name` and
> `moment` may be left blank or omitted — they are not required until `idu_naming_ordering`.
> Focus at `criteria_grouping` on grouping utterances and writing criteria sentences; do
> not commit to names prematurely. At `idu_naming_ordering`, every IDU MUST have `idu_name`
> and `moment` populated.

### 2B. Schema edit — `_mpi_schemas.py`

File: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**Split `_IDU_REQUIRED` into per-substep constants (lines 86–87):**

Replace the single constant with two:
```python
# Fields required at ALL diachronic substeps
_IDU_BASE_REQUIRED = ["idu_number", "criteria", "confidence",
                       "flag_for_review", "utterance_numbers", "hinge_to_next",
                       "utterance_refs"]

# Additional fields required ONLY at idu_naming_ordering (naming must be locked)
_IDU_NAMING_REQUIRED = ["idu_name", "moment"]
```

**Update `_validate_idu` to accept a `require_naming` flag:**
```python
def _validate_idu(idu: dict, prefix: str, is_last: bool = False,
                  require_naming: bool = True) -> list[SchemaError]:
    required = _IDU_BASE_REQUIRED + (_IDU_NAMING_REQUIRED if require_naming else [])
    errors = _require_keys(idu, required, prefix)
    errors.extend(_reject_drift_keys(idu, set(required), _IDU_DRIFT_ALIASES, prefix))
    errors.extend(_check_confidence(idu, prefix))
    errors.extend(_check_flag_for_review(idu, prefix))
    errors.extend(_check_utterance_refs(idu, prefix))
    if not is_last and "hinge_to_next" in idu and idu["hinge_to_next"] is None:
        errors.append(SchemaError(f"{prefix}.hinge_to_next",
                      "must be a string for non-last IDU (null only allowed on last IDU)"))
    return errors
```

**Update the three diachronic validators:**

- `_validate_diachronic_criteria_grouping`: pass `require_naming=False` to `_validate_idu`
- `_validate_diachronic_criteria_revision`: delegates to criteria_grouping, which now passes
  `require_naming=False`
- `_validate_diachronic_idu_naming_ordering`: use its own loop, passing `require_naming=True`
  (STOP delegating to `_validate_diachronic_criteria_grouping`; this makes it diverge):

```python
def _validate_diachronic_idu_naming_ordering(payload: dict) -> list[SchemaError]:
    errors = _require_keys(payload, ["analysis_type", "participant", "idus"], "payload")
    idus = payload.get("idus", [])
    if not isinstance(idus, list):
        errors.append(SchemaError("payload.idus", "must be a list"))
        return errors
    for i, idu in enumerate(idus):
        is_last = (i == len(idus) - 1)
        errors.extend(_validate_idu(idu, f"payload.idus[{i}]",
                                    is_last=is_last, require_naming=True))
    return errors
```

**Backward compatibility note:** the existing `VALID_CRITERIA_GROUPING_UNITS` in
`test_mpi_step.py` (line 1494) includes `idu_name` and `moment` in each IDU — these
remain valid (optional fields that are present are still accepted). No existing test breaks.

### 2C. Tests — `tests/test_analysis_fidelity.py`

**Class `TestAC3_LinkagePhraseRule`:**

```python
def test_AC3_1_agent_contains_linkage_phrase_rule(self):
    """AC3.1 Success: mpi-analyst.md contains temporal-linkage-phrase boundary rule."""
    content = (PLUGIN_ROOT / "agents" / "mpi-analyst.md").read_text(encoding="utf-8")
    # Must mention linkage phrases
    assert "and then" in content, (
        "mpi-analyst.md diachronic rules must mention 'and then' as a linkage phrase"
    )
    assert "after that" in content, (
        "mpi-analyst.md diachronic rules must mention 'after that' as a linkage phrase"
    )
    # Must state it outranks the prefer-fewer-IDUs heuristic
    assert "outranks" in content or "overrides" in content, (
        "mpi-analyst.md must state that the linkage-phrase rule outranks prefer-fewer-IDUs"
    )
```

**Class `TestAC4_NamingDeferred`:**

```python
def _idu_no_naming(self):
    """IDU payload without idu_name or moment (valid at criteria_grouping)."""
    return {
        "idu_number": 1,
        "criteria": "The utterances talk about starting.",
        "confidence": 3, "flag_for_review": False,
        "utterance_numbers": ["1"],
        "hinge_to_next": None,
        "utterance_refs": [{"transcript_id": "p1s1", "utterance_number": 1,
                            "byte_start": 0, "byte_end": 5, "raw_excerpt": "hello"}],
    }

def _idu_with_naming(self):
    """IDU payload with idu_name and moment (valid at idu_naming_ordering)."""
    d = self._idu_no_naming()
    d["idu_name"] = "Initial Contact"
    d["moment"] = 1
    return d

def test_AC4_1_criteria_grouping_accepts_idu_without_naming(self):
    """AC4.1 Success: criteria_grouping close accepted without idu_name/moment."""
    payload = {
        "analysis_type": "diachronic", "participant": "p1s1",
        "idus": [self._idu_no_naming()]
    }
    errors = validate_units("diachronic", "criteria_grouping", payload)
    assert errors == [], f"Unexpected errors: {errors}"

def test_AC4_1_criteria_revision_accepts_idu_without_naming(self):
    """AC4.1 variant: criteria_revision close also accepted without idu_name/moment."""
    payload = {
        "analysis_type": "diachronic", "participant": "p1s1",
        "idus": [self._idu_no_naming()],
        "convergence": {"decision": "converged", "reason": "IDU grouping is stable."}
    }
    errors = validate_units("diachronic", "criteria_revision", payload)
    assert errors == [], f"Unexpected errors: {errors}"

def test_AC4_2_idu_naming_ordering_rejects_without_idu_name(self):
    """AC4.2 Failure: idu_naming_ordering close rejected when idu_name absent."""
    payload = {
        "analysis_type": "diachronic", "participant": "p1s1",
        "idus": [self._idu_no_naming()]
    }
    errors = validate_units("diachronic", "idu_naming_ordering", payload)
    assert any("idu_name" in e.field for e in errors), (
        f"Expected idu_name error; got: {errors}"
    )

def test_AC4_2_idu_naming_ordering_rejects_without_moment(self):
    """AC4.2 Failure: idu_naming_ordering close rejected when moment absent."""
    idu = self._idu_no_naming()
    idu["idu_name"] = "Initial Contact"  # provide idu_name but not moment
    payload = {
        "analysis_type": "diachronic", "participant": "p1s1",
        "idus": [idu]
    }
    errors = validate_units("diachronic", "idu_naming_ordering", payload)
    assert any("moment" in e.field for e in errors), (
        f"Expected moment error; got: {errors}"
    )

def test_AC4_2_idu_naming_ordering_accepts_full_payload(self):
    """AC4.2 Success path: idu_naming_ordering accepted with idu_name and moment."""
    payload = {
        "analysis_type": "diachronic", "participant": "p1s1",
        "idus": [self._idu_with_naming()]
    }
    errors = validate_units("diachronic", "idu_naming_ordering", payload)
    assert errors == [], f"Unexpected errors: {errors}"

def test_AC4_validators_are_not_byte_identical(self):
    """Phase 2 structural check: idu_naming_ordering validator is no longer byte-identical
    to criteria_grouping (confirms the confirmed review finding is resolved)."""
    import inspect
    import _mpi_schemas as schemas
    cg_src = inspect.getsource(schemas._validate_diachronic_criteria_grouping)
    ino_src = inspect.getsource(schemas._validate_diachronic_idu_naming_ordering)
    assert cg_src != ino_src, (
        "_validate_diachronic_idu_naming_ordering must differ from "
        "_validate_diachronic_criteria_grouping (naming fields split)"
    )
```

**Done when:** `pytest tests/test_analysis_fidelity.py::TestAC3_LinkagePhraseRule tests/test_analysis_fidelity.py::TestAC4_NamingDeferred -q` passes; existing `test_mpi_step.py::TestCloseHappyPath::test_close_criteria_grouping_succeeds` still passes (unchanged — its payload supplies idu_name/moment which remain valid optional fields).

---

## Phase 3: Init/prep validation fidelity

**Goal:** Score-range rejection at init; participant-count advisory; question-line flagging
in normalize. All three are SKILL.md-documented rules executed by the orchestrator/LLM,
not in `mpi_step.py`. Tests use simulation harnesses.

**Covers:** AC5.1, AC5.2, AC6.1

### 3A. SKILL.md edit — `mpi-init/SKILL.md`

File: `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md`

**Score-range validation (append to the Header format section after line 99):**

Add a new bullet under the header-parsing rules:
> - If the parsed score (`N` in `Scored N/5`) is outside the range 0–5 (e.g. `Scored 7/5`),
>   produce a named error and skip the file:
>   `ERROR: <filename>: invalid_score_range: score N is outside valid range 0–5.
>   Expected "Scored N/5" where N ∈ {0, 1, 2, 3, 4, 5}.`
>   Do NOT silently clamp or coerce out-of-range scores. Do NOT continue processing
>   this file. This check runs after the header regex matches (the regex passes because
>   `\d+` matches any non-negative integer; the range check is a second-pass validation).

**Participant-count advisory (append to the Steps section, step 8, after building the manifest):**

Add a new step 8a:
> **8a. Participant-count adequacy advisory.** After scanning all transcripts, count the
>   number of unique participant IDs. If the count is outside the range 6–12 (per the
>   manual's recommended sample size), emit an advisory note (never an error, never blocks):
>   ```
>   NOTE: Participant count is N (recommended range: 6–12 per MPI manual). Analysis can
>   proceed, but results may be less reliable at smaller or larger sample sizes.
>   ```
>   Counts 6–12 (inclusive) are silent. This advisory is informational only and does not
>   affect manifest writing or any subsequent close.

### 3B. SKILL.md edit — `mpi-transcript-prep/SKILL.md`

File: `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md`

**Question-line flagging in normalize (append to the Validation rules section):**

Add a new sub-rule under the normalize description:
> **Question-line flagging (validate-only, no content edit):** During normalize, identify
> interviewer-turn lines (lines where the speaker label is `Kevin Sheldrake:` or the
> equivalent interviewer label) that appear to be removable clarifying questions — lines
> ending with `?` or containing only a short interrogative phrase (e.g. "Why was that?",
> "Can you say more?", "What happened then?"). Flag each such line in the normalize report:
> `QUESTION [pNsN]: line N: interviewer question line (candidate for researcher pre-removal): "<line text>"`
> Do NOT remove or rewrite these lines. The raw file and normalized file remain byte-identical
> on content for question lines — the normalized file differs only by existing structural
> rules (BOM strip, whitespace, CRLF). Removal of interviewer questions is a documented
> researcher pre-step, not a pipeline operation.

Append to the Closure section normalize row Notes column:
> Normalize also emits `QUESTION` advisories for interviewer-question lines (flagging only;
> no content modification; raw remains byte-identical on question lines).

### 3C. Tests — `tests/test_analysis_fidelity.py`

These tests simulate the init and transcript-prep skill logic using the same simulation-
harness pattern as `test_verify_mpi_init.py` (which defines its own `parse_header`) and
`test_transcript_prep.py` (which defines its own `TranscriptPrep` class).

**Class `TestAC5_InitDataContractValidation`:**

```python
import re

HEADER_REGEX = r'^Participant (\d+),?\s+Suggestion (\d+)(?:\s+\w+)*\s*\(Scored (\d+)/5\)'

def _parse_and_validate_header(self, line: str):
    """
    Simulate the init skill's two-pass header validation:
    1. Regex match (permissive)
    2. Score range check 0–5
    Returns (p, s, score) on success, raises ValueError with named-error message on failure.
    """
    match = re.match(HEADER_REGEX, line)
    if not match:
        raise ValueError(
            f"invalid header format. Expected \"Participant N[,] Suggestion N (Scored N/5)[...]\", "
            f"got: \"{line}\""
        )
    p, s, score = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if score < 0 or score > 5:
        raise ValueError(
            f"invalid_score_range: score {score} is outside valid range 0–5. "
            f"Expected \"Scored N/5\" where N ∈ {{0, 1, 2, 3, 4, 5}}."
        )
    return p, s, score

def test_AC5_1_score_7_rejected_with_named_error(self):
    """AC5.1 Failure: Scored 7/5 rejected with invalid_score_range error."""
    line = "Participant 1, Suggestion 1 (Scored 7/5)"
    with pytest.raises(ValueError) as exc_info:
        self._parse_and_validate_header(line)
    assert "invalid_score_range" in str(exc_info.value)

def test_AC5_1_score_6_rejected(self):
    """AC5.1 Failure: Scored 6/5 also rejected."""
    line = "Participant 2, Suggestion 1 (Scored 6/5)"
    with pytest.raises(ValueError) as exc_info:
        self._parse_and_validate_header(line)
    assert "invalid_score_range" in str(exc_info.value)

def test_AC5_1_score_0_accepted(self):
    """AC5.1 boundary: Scored 0/5 accepted (minimum valid)."""
    p, s, score = self._parse_and_validate_header(
        "Participant 3, Suggestion 1 (Scored 0/5)"
    )
    assert score == 0

def test_AC5_1_score_5_accepted(self):
    """AC5.1 boundary: Scored 5/5 accepted (maximum valid)."""
    p, s, score = self._parse_and_validate_header(
        "Participant 4, Suggestion 1 (Scored 5/5)"
    )
    assert score == 5

def _emit_participant_count_advisory(self, count: int) -> str | None:
    """
    Simulate the init skill's participant-count advisory logic.
    Returns advisory string if out-of-range (< 6 or > 12), else None.
    """
    if count < 6 or count > 12:
        return (
            f"NOTE: Participant count is {count} "
            f"(recommended range: 6–12 per MPI manual). "
            f"Analysis can proceed, but results may be less reliable "
            f"at smaller or larger sample sizes."
        )
    return None

def test_AC5_2_count_5_produces_advisory(self):
    """AC5.2 Success: participant count 5 produces 6-12 adequacy advisory."""
    advisory = self._emit_participant_count_advisory(5)
    assert advisory is not None
    assert "6–12" in advisory or "6-12" in advisory

def test_AC5_2_count_13_produces_advisory(self):
    """AC5.2 Success: participant count 13 produces advisory."""
    advisory = self._emit_participant_count_advisory(13)
    assert advisory is not None
    assert "NOTE" in advisory

def test_AC5_2_count_6_is_silent(self):
    """AC5.2 Success: participant count 6 produces no advisory."""
    advisory = self._emit_participant_count_advisory(6)
    assert advisory is None

def test_AC5_2_count_12_is_silent(self):
    """AC5.2 Success: participant count 12 produces no advisory."""
    advisory = self._emit_participant_count_advisory(12)
    assert advisory is None

def test_AC5_2_count_9_is_silent(self):
    """AC5.2 Success: mid-range count is silent."""
    advisory = self._emit_participant_count_advisory(9)
    assert advisory is None

def test_AC5_1_skill_md_contains_score_range_rule(self):
    """AC5.1 Grep: mpi-init/SKILL.md contains the score-range validation rule."""
    content = (PLUGIN_ROOT / "skills" / "mpi-init" / "SKILL.md").read_text(encoding="utf-8")
    assert "invalid_score_range" in content, (
        "mpi-init/SKILL.md must document the invalid_score_range named error"
    )
    assert "0–5" in content or "0-5" in content, (
        "mpi-init/SKILL.md must state the valid score range 0–5"
    )

def test_AC5_2_skill_md_contains_participant_count_advisory(self):
    """AC5.2 Grep: mpi-init/SKILL.md contains the participant-count advisory rule."""
    content = (PLUGIN_ROOT / "skills" / "mpi-init" / "SKILL.md").read_text(encoding="utf-8")
    assert "6–12" in content or "6-12" in content, (
        "mpi-init/SKILL.md must document the 6–12 participant-count guidance"
    )
    assert "NOTE" in content or "advisory" in content.lower(), (
        "mpi-init/SKILL.md must state the count check is non-blocking (advisory/note)"
    )
```

**Class `TestAC6_QuestionFlaggingValidateOnly`:**

```python
def _is_interviewer_question(self, speaker_label: str, line_text: str) -> bool:
    """
    Simulate the normalize skill's question-detection logic.
    Returns True if the line is an interviewer question candidate.
    """
    interviewer_labels = {"Kevin Sheldrake:", "KS:"}
    if speaker_label not in interviewer_labels:
        return False
    # Check for question marker: ends with '?' in the content part
    return "?" in line_text

def test_AC6_1_interviewer_question_detected_not_modified(self):
    """AC6.1 Success: normalize flags interviewer-question line; content unchanged."""
    raw_line = "Kevin Sheldrake: Why was that?"
    speaker = "Kevin Sheldrake:"
    text = "Why was that?"
    is_q = self._is_interviewer_question(speaker, text)
    assert is_q, "Interviewer question line should be flagged"
    # Content is not modified — the raw line equals normalized line (content-wise)
    # (structural normalisation: whitespace/crlf only)
    normalized_content = raw_line.rstrip()  # only trailing whitespace stripped
    assert "Why was that?" in normalized_content, (
        "Question text must not be removed or rewritten during normalize"
    )

def test_AC6_1_participant_question_not_flagged(self):
    """AC6.1 Success: participant utterances ending with '?' are not flagged."""
    speaker = "P1:"
    text = "I was wondering what would happen?"
    is_q = self._is_interviewer_question(speaker, text)
    assert not is_q, "Participant utterances must not be flagged as removable questions"

def test_AC6_1_interviewer_non_question_not_flagged(self):
    """AC6.1 Success: interviewer non-question lines are not flagged."""
    speaker = "Kevin Sheldrake:"
    text = "Okay, thank you for that."
    is_q = self._is_interviewer_question(speaker, text)
    assert not is_q, "Interviewer non-question lines must not be flagged"

def test_AC6_1_skill_md_contains_validate_only_rule(self):
    """AC6.1 Grep: mpi-transcript-prep/SKILL.md documents question-flagging as validate-only."""
    content = (PLUGIN_ROOT / "skills" / "mpi-transcript-prep" / "SKILL.md").read_text(encoding="utf-8")
    assert "QUESTION" in content, (
        "mpi-transcript-prep/SKILL.md must document the QUESTION advisory format"
    )
    assert "not" in content.lower() and ("remove" in content.lower() or "rewrite" in content.lower()), (
        "mpi-transcript-prep/SKILL.md must state question lines are NOT removed or rewritten"
    )
```

**Done when:** `pytest tests/test_analysis_fidelity.py::TestAC5_InitDataContractValidation tests/test_analysis_fidelity.py::TestAC6_QuestionFlaggingValidateOnly -q` passes; `tests/test_verify_mpi_init.py` and `tests/test_transcript_prep.py` still pass (no conflicts — these add new test classes, not modifications).

---

## Regression gate

After all three phases, run full test suites:

```bash
python -m pytest tests/ -q
python -m pytest microphenomenograph/1.0.0/scripts/ -q
```

Expected: no new failures beyond the pre-existing known failure
(`tests/test_verify_mpi_init.py::test_all` — KNOWN ENVIRONMENTAL, missing
`examples/transcripts/` fixture dir).

## Dependency / ordering notes

- Phase 1 and Phase 2 are parallel-safe (disjoint file regions: different agent files and
  different schema functions).
- Phase 3 is parallel-safe with both (SKILL.md files only; no schema edits).
- All three phases may be implemented concurrently or in any order.
- Plan 2 (close-enforcement-2) overlap: `mpi-analyst.md` was edited by that plan's
  Phase 4 (synchronic rule 4 — lines 68–73 of the current file). This plan's edits
  target the DIACHRONIC rules section (~lines 22–55) and are in a different region.
  Coordinate during merge to avoid contextual conflicts.

## File change summary

| File | Phase | Change type |
|---|---|---|
| `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` | 1 | Edit: generic-synchronic grouping rule rewrite; generic-diachronic pattern instructions |
| `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` | 1 | Edit: `_validate_generic_synchronic_isu_second_level` + `source_generic_idu` check; `_validate_generic_diachronic_pattern_identification` + `common_idus`/`optional_idus`/`covered_participant_keys` |
| `microphenomenograph/1.0.0/agents/mpi-analyst.md` | 2 | Edit: linkage-phrase rule (new rule 5 in diachronic section); naming-deferred wording |
| `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` | 2 | Edit: `_IDU_REQUIRED` → `_IDU_BASE_REQUIRED` + `_IDU_NAMING_REQUIRED`; `_validate_idu` `require_naming` flag; `_validate_diachronic_idu_naming_ordering` own implementation |
| `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md` | 3 | Edit: score-range error rule; participant-count advisory |
| `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md` | 3 | Edit: question-line flagging in normalize (validate-only) |
| `tests/test_analysis_fidelity.py` | 1+2+3 | New: all AC tests |

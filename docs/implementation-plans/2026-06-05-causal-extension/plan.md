# Causal Extension — Implementation Plan

Design document: `docs/design-plans/2026-06-05-causal-extension.md`
Branch: `remediation-2026-06-05`

---

## Overview

Three phases implement the full-structural causal contract for `hypothesis.candidate_drafting`:

| Phase | Goal | ACs |
|---|---|---|
| 1 | Schema fields for claims and artifact | AC1.1–1.4, AC4.1 |
| 2 | Agent instructions + SKILL.md output format | AC2.1–2.3, AC4.2 |
| 3 | DAG gate, rung_appropriateness teeth, CLAUDE.md docs | AC3.1, AC3.2, AC5.1 |

**Green criterion:** `python -m pytest tests/ -q` must not add failures beyond the single known baseline failure (`tests/test_verify_mpi_init.py::test_all`). Because Phase 1 adds required fields to `_validate_hypothesis_candidate_drafting`, the `_base_claim` / `_base_candidate_drafting_payload` helpers in `tests/test_hypothesis_evidence.py` and the fixture file `tests/fixtures/cross_analyst/dv-automaticity.candidates.json` must also be updated in Phase 1 to remain valid under the extended contract.

---

## Phase 1: Causal schema fields

**Goal:** The claim contract carries the full causal structure: `rung`, `assumptions`, `confounders`, `testable_implications` on every claim; `replication_recommendation` at the artifact level. Schema-enforced, hard rejection.

**Files to edit:**

### `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

Inside `_validate_hypothesis_candidate_drafting`, in the per-claim validation block that starts at (approximately) `cl_prefix = f"{c_prefix}.claims[{j}]"`:

1. **Add to the `_require_keys` call** for each claim: append `"rung"`, `"assumptions"`, `"confounders"`, `"testable_implications"` to the list of required keys (currently `["claim_id", "claim_text", "supports", "contradicts", "ambiguous", "n_transcripts", "n_iv_levels_covered", "uncertainty_language", "negative_cases"]`).

2. **After the `_require_keys` call**, add conditional rung≥2 → non-empty assumptions check (precedent: `hinge_to_next` null-check, lines 113–115):
   ```python
   rung = claim.get("rung")
   if rung is not None and isinstance(rung, int) and rung >= 2:
       assumptions = claim.get("assumptions", [])
       if not isinstance(assumptions, list) or len(assumptions) == 0:
           errors.append(SchemaError(
               f"{cl_prefix}.assumptions",
               f"must be a non-empty list when rung >= 2 (rung={rung}); "
               "state the causal assumptions licensing the higher-rung framing"
           ))
   ```

3. **After the rung check**, add confounder shape validation:
   ```python
   confounders = claim.get("confounders")
   if confounders is not None:
       if not isinstance(confounders, list) or len(confounders) == 0:
           errors.append(SchemaError(
               f"{cl_prefix}.confounders",
               "must be a non-empty list of {variable, mechanism} objects"
           ))
       else:
           for ci, cf in enumerate(confounders):
               cf_prefix = f"{cl_prefix}.confounders[{ci}]"
               if not isinstance(cf, dict):
                   errors.append(SchemaError(cf_prefix, "must be an object with 'variable' and 'mechanism'"))
               else:
                   if "variable" not in cf:
                       errors.append(SchemaError(f"{cf_prefix}.variable", "required field missing"))
                   if "mechanism" not in cf:
                       errors.append(SchemaError(f"{cf_prefix}.mechanism", "required field missing"))
   ```
   Note: `confounders` is already required via `_require_keys`; this block validates shape when present.

4. **Validate `rung` value**: after the `_require_keys` call, check `rung` is int 1, 2, or 3:
   ```python
   if rung is not None and rung not in (1, 2, 3):
       errors.append(SchemaError(f"{cl_prefix}.rung", f"must be 1, 2, or 3 (Pearl rung), got {rung!r}"))
   ```

5. **Validate `testable_implications`**: non-empty list of strings (no DAGitty syntax check — shape only):
   ```python
   ti = claim.get("testable_implications")
   if ti is not None:
       if not isinstance(ti, list) or len(ti) == 0:
           errors.append(SchemaError(f"{cl_prefix}.testable_implications",
                                     "must be a non-empty list of strings (DAGitty notation)"))
   ```

6. **Add `replication_recommendation` to the top-level required keys** in `_validate_hypothesis_candidate_drafting`. The current top-level `_require_keys` call is:
   ```python
   errors = _require_keys(payload, ["dv_focus", "disclaimer", "candidates"], "payload")
   ```
   Change to:
   ```python
   errors = _require_keys(payload, ["dv_focus", "disclaimer", "candidates", "replication_recommendation"], "payload")
   ```

### `tests/test_hypothesis_evidence.py`

The `_base_claim` helper (class `TestAC2_ClaimIdCoverage`, approximately lines 33–51) and `_base_candidate_drafting_payload` (approximately lines 62–68) must be updated so that existing passing tests stay green under the extended schema. **Do not modify the existing test methods themselves — only the helpers.**

1. **`_base_claim`**: add new required fields with valid defaults:
   ```python
   "rung": 1,
   "assumptions": [],          # empty allowed at rung=1
   "confounders": [{"variable": "common_method_variance", "mechanism": "self-report bias"}],
   "testable_implications": ["IV _||_ DV | CMV"],
   ```

2. **`_base_candidate_drafting_payload`**: add top-level `replication_recommendation`:
   ```python
   "replication_recommendation": "A second participant set would need to show the same pattern to support this mechanism.",
   ```

### `tests/fixtures/cross_analyst/dv-automaticity.candidates.json`

The E2E fixture close test (`TestAC23_1_HypothesisCandidateFixtureClose.test_hypothesis_candidate_fixture_close` in `tests/test_mpi_cross_analyst_contract.py`, approximately line 352) loads this fixture and calls `mpi_step.py close`, which invokes schema validation. The fixture must pass the extended schema:

1. Add `"replication_recommendation"` at the top level.
2. Add `"rung"`, `"assumptions"`, `"confounders"`, `"testable_implications"` to the single claim object inside `candidates[0].claims[0]`.

Example additions:
```json
"replication_recommendation": "A second participant set would need to replicate the association between suggestibility score and automaticity reports.",
```
And in the claim:
```json
"rung": 1,
"assumptions": [],
"confounders": [{"variable": "common_method_variance", "mechanism": "IV score and DV description both self-reported by same participant in same session"}],
"testable_implications": ["automaticity _||_ session_order | suggestibility"]
```

**New test file: `tests/test_causal_extension.py`**

Create this file. Do NOT extend `test_hypothesis_evidence.py` (DO-NOT-TOUCH zone for plan-4 tests).

```python
"""Tests for causal-extension design plan (plan 5).

Phase 1: AC1.1, AC1.2, AC1.3, AC1.4, AC4.1 — causal claim schema fields.
"""
import pytest
from pathlib import Path
import sys

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))

from _mpi_schemas import validate_units
```

Implement the following test functions:

**`test_AC1_1_rung2_empty_assumptions_rejected`** — AC1.1 Failure  
Build a minimal valid `candidate_drafting` payload using the updated helpers pattern. Set `claim["rung"] = 2` and `claim["assumptions"] = []`. Call `validate_units("hypothesis", "candidate_drafting", payload)`. Assert errors contain a mention of `assumptions`.

**`test_AC1_2_rung1_empty_assumptions_accepted`** — AC1.2 Success  
Set `claim["rung"] = 1` and `claim["assumptions"] = []`. Assert `not errors`.

**`test_AC1_3_empty_confounders_rejected`** — AC1.3 Failure  
Set `claim["confounders"] = []`. Assert errors contain `confounders`.

**`test_AC1_4_confounder_missing_variable_rejected`** — AC1.4 Failure  
Set `claim["confounders"] = [{"mechanism": "self-report bias"}]` (missing `variable`). Assert errors contain `variable`.

**`test_AC1_4_confounder_missing_mechanism_rejected`** — AC1.4 Failure (variant)  
Set `claim["confounders"] = [{"variable": "common_method_variance"}]` (missing `mechanism`). Assert errors contain `mechanism`.

**`test_AC1_well_formed_rung2_claim_accepted`** — Regression/baseline  
Valid rung-2 claim with non-empty `assumptions`. Assert `not errors`.

**`test_AC4_1_missing_replication_recommendation_rejected`** — AC4.1 Failure  
Build a full payload missing `replication_recommendation`. Assert errors contain `replication_recommendation`.

**`test_AC4_1_replication_recommendation_present_accepted`** — AC4.1 Success  
Full payload with `replication_recommendation`. Assert `not errors`.

Helper methods pattern (analogous to `TestAC2_ClaimIdCoverage`):
- `_minimal_raw_span_ref()` — same as plan-4 pattern
- `_base_claim(claim_id="c1", rung=1, assumptions=None, confounders=None, testable_implications=None)` — builds a fully valid causal-schema claim
- `_base_candidate(claims)` — same structure
- `_base_payload(candidates, replication_recommendation="...")` — full payload with `replication_recommendation`

**Done when:** `python -m pytest tests/test_causal_extension.py -q` passes all Phase-1 tests; `python -m pytest tests/test_hypothesis_evidence.py -q` still passes all existing tests; `python -m pytest tests/test_mpi_cross_analyst_contract.py::TestAC23_1_HypothesisCandidateFixtureClose -q` passes.

**Covers:** causal-extension.AC1.1, AC1.2, AC1.3, AC1.4, AC4.1.

---

## Phase 2: Agent causal instructions + SKILL.md output format

**Goal:** The agent produces well-formed causal content. Agent instructions make all four new field shapes concrete; SKILL.md output format shows the per-hypothesis DAG section and `replication_recommendation` in the markdown template.

**Dependencies:** Phase 1 must be landed first (the agent instructions reference the schema).

**Files to edit:**

### `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`

**DO-NOT-TOUCH zones (from prior plans):** `inputs_consumed`/`isolation` sections (plan 2), generic-synchronic/generic-diachronic sections (plan 3), and the weak-evidence `thin_support`/`single_iv_level`/`causal_language` checks (plan 4). Edit ONLY:

1. **Hypothesis generation section** (`### Hypothesis generation`): extend the numbered list (currently items 1–7) to include causal field instructions. After item 4 (Assign Pearl ladder rung), insert or expand:

   - **Rung guard**: If rung ≥ 2, `assumptions` must be a non-empty list of strings stating the causal assumptions that license the higher-rung framing (DoWhy identify-discipline analogue). At rung 1, `assumptions` may be empty `[]`.
   - **Confounders** (always required, non-empty): enumerate `{variable, mechanism}` objects. ALWAYS include the common-method-variance (CMV) factor: the IV score and DV experience description are both self-reports from the same participant in the same session. This is a latent common cause of both. Mechanism wording should be participant-specific (e.g., "P3's automaticity rating and their description of hand movement were both produced in the same interview session"). One-sentence instruction: always include CMV even when you believe it is unlikely to confound.
   - **Testable implications** (non-empty list): state each in DAGitty conditional-independence notation `X _||_ Y | Z` ("X is independent of Y given Z"). Example: `"suggestibility _||_ session_fatigue | automaticity"`.
   - **Per-hypothesis mermaid DAG** (required in markdown artifact): IV → mechanism components → DV focus; confounder nodes with two directed arrows into IV and DV (no `<->` — mermaid has no bidirected edge). Latent nodes (e.g., CMV) get a distinct mermaid class (`:::latent` or `class CMV latent`). One DAG per candidate hypothesis, preceding or following the claims table.

2. **Claim-level evidence schema block** (`#### Claim-level evidence schema (mandatory for hypothesis.candidate_drafting)`): extend the JSON example to show the four new fields. Add after `"negative_cases"`:
   ```json
   "rung": 1,
   "assumptions": [],
   "confounders": [
     {
       "variable": "common_method_variance",
       "mechanism": "IV score and DV experience description both self-reported by participant in same session — shared method creates spurious correlation"
     }
   ],
   "testable_implications": ["DV _||_ session_order | IV"]
   ```

3. **Top-level artifact additions**: in the same schema block, show `replication_recommendation` as a required top-level field (peer of `disclaimer`, `dv_focus`, `candidates`):
   ```json
   "replication_recommendation": "A second independent participant set would need to show the same direction of association between [IV] and [DV] to support this mechanism."
   ```

4. **`### Weak evidence review` section — ONLY the `rung_appropriateness` bullet**: replace the existing stub bullet:
   > `rung_appropriateness` — Stub: record whether the claim's rung label is consistent with its evidence type. Mark `"stub": true` for now; plan 5 gives this teeth.

   With the substantive check:
   > `rung_appropriateness` — Flag if the claim's `rung` value is inconsistent with its evidence type. Qualitative cross-participant pattern data is observational (rung 1 — association); a claim coded as rung 2 (intervention) or rung 3 (counterfactual) over such evidence is structurally mislabelled. Rule: if `rung >= 2` AND all evidence in `supports`/`contradicts`/`ambiguous` comes from observational interview transcripts (i.e., no experimental manipulation is described), flag as `rung_appropriateness: {"flagged": true, "reason": "<explanation>"}`. If rung 1 or genuinely experimental evidence, pass as `rung_appropriateness: {"flagged": false}`. Do NOT set `"stub": true`.

   Also update the JSON example in the `### Weak evidence review` output block to show the new `rung_appropriateness` shape (remove `{"stub": true}`; show `{"flagged": false}` for a passing claim).

### `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`

1. **Output format section**: extend the markdown template to include:
   - `replication_recommendation` field in the per-hypothesis table (or as a paragraph after the table):
     ```markdown
     **Replication recommendation:** A second participant set would need to show [X] to corroborate this mechanism.
     ```
   - A per-hypothesis DAG block:
     ```markdown
     **Causal DAG:**
     ```mermaid
     graph LR
       IV[Suggestibility score] --> M[Mechanism component]
       M --> DV[DV focus]
       CMV[Common-method variance]:::latent --> IV
       CMV --> DV
       classDef latent fill:#f5f5f5,stroke:#999,stroke-dasharray:5 5
     ```
     ```
   This section should appear once per hypothesis, after the claims table.

2. The SKILL.md already cites the `inputs` verb (not literal artifact paths) — do not change this.

**New tests in `tests/test_causal_extension.py`** (Phase 2 additions):

Add a class `TestAC2_AgentInstructions` with:

**`test_AC2_1_cross_analyst_md_has_cmv_instruction`** — AC2.1 Success  
Read `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`. Assert it contains `common_method_variance` or `common-method-variance` (agent must name CMV). Assert it contains `latent` (latent node instruction). Assert it contains "common cause" or "common-method" or "CMV".

**`test_AC2_2_cross_analyst_md_has_dagitty_notation`** — AC2.2 Success  
Assert the file contains the DAGitty notation marker `_||_` (used in testable_implications instruction).

**`test_AC2_3_cross_analyst_md_has_dag_conventions`** — AC2.3 Success  
Assert the file contains `mermaid` (DAG format). Assert it contains language describing two directed arrows or no bidirected edge (`<->` prohibition or "two directed arrows"). Assert it contains `classDef latent` or `:::latent` or a `latent` class naming convention.

**`test_AC4_2_hypothesis_skill_has_replication_recommendation_template`** — AC4.2 Success  
Read `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`. Assert it contains `replication_recommendation`. Assert it contains `second participant set` or "second independent" or "second set".

**`test_AC4_2_hypothesis_skill_has_dag_section`** — AC4.2 Success  
Assert the SKILL.md file contains a DAG block (look for `mermaid` in the output format section or `Causal DAG`).

**Done when:** `python -m pytest tests/test_causal_extension.py -q` passes all Phase-2 tests; no regression in `python -m pytest tests/ -q` beyond the known baseline failure.

**Covers:** causal-extension.AC2.1, AC2.2, AC2.3, AC4.2.

---

## Phase 3: DAG presence gate + rung review + contract docs

**Goal:** Close-time checks and documentation match the new contract. DAG presence validated at close for `hypothesis.candidate_drafting` (gate, not syntax check). Rung-appropriateness substantive check confirmed by fixture test. Plugin `CLAUDE.md` updated.

**Dependencies:** Phases 1–2 must be landed; plan-4 Phase 3 review machinery already exists (DO-NOT-TOUCH).

**Files to edit:**

### `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

Add `dag_section_missing` to the `GATES` registry (after the `weak_evidence_unreviewed` entry):

```python
"dag_section_missing": {
    "stage": "hypothesis",
    "description": "candidate_drafting markdown artifact missing per-hypothesis DAG section",
    "posture": "warn_or_abort",
},
```

### `microphenomenograph/1.0.0/scripts/mpi_step.py`

1. **New function `_check_dag_section_missing_gate`** — modeled on `_check_weak_evidence_unreviewed_gate` (lines ~1393–1428). Place immediately after `_check_weak_evidence_unreviewed_gate`:

   ```python
   def _check_dag_section_missing_gate(
       run_dir: Path,
       manifest: dict,
       args,
       audit_path: Path,
       close_id: str,
       actor: str,
       actor_kind: str,
   ) -> int:
       """AC3.1: Warn (or abort) when a hypothesis.candidate_drafting markdown artifact
       is missing the per-hypothesis DAG section (mermaid marker absent).
   
       Fires only for hypothesis.candidate_drafting closes.
       Returns 0 (GATE_WARN or gate skipped) or 1 (GATE_ABORT in strict mode).
       """
       # Locate the .md artifact among args.artifact
       md_path = None
       for art in getattr(args, "artifact", []) or []:
           if str(art).endswith(".md"):
               md_path = Path(art)
               break
       if md_path is None or not md_path.exists():
           return 0  # No markdown artifact — skip gate (artifact validation handles presence)
   
       content = md_path.read_text(encoding="utf-8")
       # Presence check: look for the mermaid code fence marker
       if "```mermaid" not in content:
           return _evaluate_gate(
               "dag_section_missing",
               run_dir, manifest, args, audit_path, close_id,
               stage="hypothesis", substep="candidate_drafting",
               scope=getattr(args, "scope", "unknown"),
               actor=actor, actor_kind=actor_kind,
           )
       return 0
   ```

2. **Wire the gate into `cmd_close`**: immediately after the `weu_rc` block (~line 1843–1851), add:

   ```python
   # AC3.1: dag_section_missing gate — warn/abort when candidate_drafting markdown lacks DAG
   if args.stage == "hypothesis" and args.substep == "candidate_drafting":
       dag_rc = _check_dag_section_missing_gate(
           run_dir, manifest, args, audit_path, close_id,
           actor=args.actor,
           actor_kind=getattr(args, "actor_kind", "subagent"),
       )
       if dag_rc != 0:
           return _abort("dag_section_missing")
   ```

3. **Add CLI flag** in the `p_close` argument parser block (after `--strict-weak-evidence-unreviewed`, ~line 2519):
   ```python
   p_close.add_argument("--strict-dag-section-missing", action="store_true",
                        dest="strict_dag_section_missing",
                        help="Block hypothesis.candidate_drafting close when markdown "
                             "artifact is missing per-hypothesis mermaid DAG section.")
   ```

### `microphenomenograph/1.0.0/CLAUDE.md` (plugin internal)

In the hypothesis section of the CLAUDE.md (currently: "Hypothesis generation produces **candidate mechanism hypotheses, not causal estimates**. Every artifact carries a verbatim disclaimer. Each claim carries..."), extend the existing paragraph to document:

- The four new claim-level causal fields: `rung` (int 1|2|3, Pearl ladder), `assumptions` (non-empty list required when rung ≥ 2), `confounders` (non-empty list of `{variable, mechanism}` objects; always includes CMV latent factor), `testable_implications` (non-empty list of strings in DAGitty `X _||_ Y | Z` notation).
- Top-level `replication_recommendation` field (string; discharges manual §1.5 replication requirement — states what a second participant set would need to show).
- DAG convention: each candidate hypothesis in the markdown artifact includes one mermaid DAG (IV → mechanism → DV, confounders as explicit latent nodes with two directed arrows — no `<->` — latent class marking). DAG presence validated at close (`dag_section_missing` gate, warn by default; strict with `--strict-dag-section-missing` or `study.strict_gates: ["dag_section_missing"]`); DAG syntax not validated.
- No plugin version bump: these fields extend the contract within an unreleased plugin; no plugin version bump is made. Rationale: the plugin directory is pinned at `microphenomenograph/1.0.0/` only because it has not been released; these are schema additions within the same unreleased version.
- `rung_appropriateness` in `weak_evidence_review` is now substantive: rung ≥ 2 over observational evidence → flagged.

**New tests in `tests/test_causal_extension.py`** (Phase 3 additions):

Add a class `TestAC3_GateAndReview`:

**`test_AC3_1_dag_gate_fires_when_mermaid_absent`** — AC3.1 Posture (warn)  
Use a `tmp_path` fixture. Set up a minimal run dir (same pattern as `test_AC3_1_flagged_unacknowledged_triggers_warn` in `test_hypothesis_evidence.py`). Create a `hypotheses/` dir. Write a minimal JSON artifact (valid schema with all new fields) and a `.md` artifact WITHOUT a `mermaid` fence. Write a minimal `.prompt.json`. Call `mpi_step.main(["close", ..., "--stage", "hypothesis", "--substep", "candidate_drafting", ...])`. Assert `rc == 0` (warn mode, not strict). Assert `audit.jsonl` contains a `gate_warning` event with `gate_id == "dag_section_missing"`.

**`test_AC3_1_dag_gate_passes_when_mermaid_present`** — AC3.1 Posture (passes)  
Same setup but write a `.md` artifact that DOES contain ` ```mermaid `. Assert `rc == 0` and NO `dag_section_missing` gate event in audit.

**`test_AC3_1_dag_gate_strict_blocks_when_mermaid_absent`** — AC3.1 Posture (strict abort)  
Pass `"--strict-dag-section-missing"` to `mpi_step.main(...)`. Assert `rc != 0`.

**`test_AC3_2_rung_appropriateness_substantive_shape_accepted`** — AC3.2 Success (validator permissive)  
Build a `weak_evidence_review` payload where a review item carries:
```python
"rung_appropriateness": {"flagged": True, "reason": "rung-2 language over observational evidence"}
```
and `"outcome": "flagged"`. Call `validate_units("hypothesis", "weak_evidence_review", payload)`. Assert `not errors` (the validator accepts the substantive shape without error — it only checks `checks` is a dict).

**`test_AC3_2_rung_appropriateness_stub_still_accepted`** — AC3.2 Regression (plan-4 compat)  
`"rung_appropriateness": {"stub": True}` also passes the validator. Assert `not errors`.

**`test_AC5_1_plugin_claude_md_has_causal_contract`** — AC5.1 Success  
Read `microphenomenograph/1.0.0/CLAUDE.md`. Assert all of the following strings are present:
- `"rung"` (field name documented)
- `"assumptions"` (field name documented)
- `"confounders"` (field name documented)
- `"testable_implications"` (field name documented)
- `"replication_recommendation"` (field name documented)
- `"dag_section_missing"` (gate ID documented)
- `"no plugin version bump"` OR `"no version bump"` OR `"unreleased"` (no-version-bump rationale)
- `"latent"` (DAG convention — latent nodes)

**Done when:** All Phase-3 tests pass; `python -m pytest tests/ -q` still shows only the known baseline failure. Plugin CLAUDE.md accurately describes the shipped contract.

**Covers:** causal-extension.AC3.1, AC3.2, AC5.1.

---

## Execution order

1. Phase 1 — schema + fixture updates (allows all Phase-1 tests to pass)
2. Phase 2 — agent + SKILL.md (instruction-check tests rely on Phase-1 fixtures remaining valid)
3. Phase 3 — gate + docs (gate implementation can only be verified against the mpi_step.py structure from Phase 1 wiring)

Run after each phase: `python -m pytest tests/ -q && python -m pytest microphenomenograph/1.0.0/scripts/ -q`

---

## DO-NOT-TOUCH summary (from prior plans)

- `mpi-cross-analyst.md`: `inputs_consumed`/`isolation` sections, generic-synchronic sections, generic-diachronic sections, `thin_support`/`single_iv_level`/`causal_language` check text in `### Weak evidence review` — ONLY the `rung_appropriateness` bullet is modified.
- `irr.py` and `mpi-irr` — off limits.
- `test_hypothesis_evidence.py` — only `_base_claim` and `_base_candidate_drafting_payload` helpers are touched (to keep existing tests green under the extended schema). No test method logic is changed.

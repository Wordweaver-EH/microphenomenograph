# Close Enforcement Round 2 — Implementation Plan

_Design:_ `docs/design-plans/2026-06-05-close-enforcement-2.md`
_Branch:_ `remediation-2026-06-05`
_Date:_ 2026-06-05

## As-built notes (authoritative over design-doc wording)

- `mpi_step.py` manifest field is `output_paths` (plural, line 1618), not `output_path`.
- `irr_warning` is the existing audit-event action string for the IRR gate (asserted by
  `test_mpi_step.py::TestStrictIRRGate`). Do NOT rename it. `gate_warning` is the new
  action string for general non-IRR gates.
- `cmd_verify` must print `gate_warning` events as `WARN` lines (not added to `failures`)
  so that warn-mode closes do not make verify return non-zero.
- Downgrade-posture gates (`convergence_pending`, `temporal_order_pending`) override
  `args.status` at the manifest-build site (~line 1616); they do NOT abort close. This is
  distinct from abort-posture gates (`undeclared_input`, `single_event_global_synchronic`)
  which follow warn-or-abort.
- Downstream blocking after downgrade is free: the existing prereq loop (~1488–1510)
  requires `status == "done"`; `flagged != done` so blocking needs no new code.
- `source_event` required field is added only inside `_validate_global_synchronic` (~line
  274), NOT in the shared `_validate_isu` (which backs per-transcript and generic_synchronic).
- `idu_split_after_synchronic` detection: scan manifest for `synchronic.theme_grouping_within_idu`
  substeps whose participant key matches `pNsN-iduK` pattern for the same transcript (derived
  from the criteria_revision scope `pNsN`); check if their status is `flagged` (temporal-order
  downgrade); read their `close_id`; emit the linking audit event. Integrate after the
  existing cascade-reset block (~1771+).
- `inputs` resolution reuses `COMPLETENESS_GATES` table scope-to-event mapping and
  `output_paths`/`artifact_shas` from manifest participant entries; does not write new
  parallel mapping logic.
- `inputs_consumed` absent from artifact = skip subset check (not a violation). Present
  and not ⊆ resolved = `undeclared_input` fires.
- `study.strict_gates` written alongside `dv_focuses_provenance` at confirm_study_config
  close (~line 1637).

## Test file placement

| File | What lands there |
|---|---|
| `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | Gate-registry unit tests, close warn/strict, `inputs` verb, audit-event assertions, downgrade-status tests, temporal-order co-presence, `source_event` schema |
| `tests/test_close_enforcement_2.py` | Integration: AC2.3 grep assertion (no dead literal), AC4.5 SKILL-claims-code parity sweep |

Green criterion: no new failures beyond known `test_verify_mpi_init.py::test_all` under
both `pytest tests/ -q` and `pytest microphenomenograph/1.0.0/scripts/ -q`.

---

## Phase 1: Gate registry + manifest strictness

**ACs covered:** close-enforcement-2.AC1.1 – AC1.5

### Goal

Add a declarative `GATES` registry to `_mpi_schemas.py`. Teach `cmd_close` to evaluate
gates and emit `gate_warning` audit events or abort. Add `--strict-<gate_id>` CLI handling
(keeping `--strict-irr` as an alias). Add `study.strict_gates` manifest field written at
`confirm_study_config`. Teach `cmd_verify` to report `gate_warning` events.

### Files and edits

**`microphenomenograph/1.0.0/scripts/_mpi_schemas.py`**

1. Add `GATES` registry constant near `COMPLETENESS_GATES` (~line 718):
   ```python
   GATES: dict[str, dict] = {
       "single_event_global_synchronic": {
           "stage": "global_synchronic",
           "description": "Global-synchronic scope covers < 2 events",
           "posture": "warn_or_abort",
       },
       "undeclared_input": {
           "stage": None,  # all cross-participant
           "description": "inputs_consumed contains path not in resolved set",
           "posture": "warn_or_abort",
       },
       "convergence_pending": {
           "stage": "diachronic",
           "description": "criteria_revision closed with more_revision_needed",
           "posture": "downgrade",
       },
       "temporal_order_pending": {
           "stage": "synchronic",
           "description": "theme_grouping_within_idu flagged temporal_order_within_idu",
           "posture": "downgrade",
       },
       "irr_below_threshold": {
           "stage": None,  # cross-participant; handled by existing _check_irr_gate
           "description": "IRR outcome is missing or low",
           "posture": "warn_or_abort",
       },
   }
   ```
   - `posture` field: `"warn_or_abort"` (emit `gate_warning` + optionally abort) vs
     `"downgrade"` (force substep status to `flagged`, close still succeeds).

2. In `_validate_init_confirm_study_config` (~line 508): accept optional `strict_gates`
   field as a list of strings; if present, validate each entry is a known key in `GATES`.
   Return errors for unknown gate IDs.

3. Export `GATES` in the import list at the top of `mpi_step.py`.

**`microphenomenograph/1.0.0/scripts/mpi_step.py`**

4. Import `GATES` from `_mpi_schemas`.

5. Add helper `_evaluate_gate(gate_id, run_dir, manifest, args, audit_path, close_id, stage, substep, scope, actor, actor_kind, extra_details)`:
   - Reads `study.strict_gates` from manifest + checks `getattr(args, f"strict_{gate_id}", False)`.
   - If strict: print `ERROR gate_failed: {gate_id}` to stderr, returns `GATE_ABORT`.
   - If warn: emits `gate_warning` audit event with fields `{close_id, gate_id, details}`,
     returns `GATE_WARN`.
   - `GATE_ABORT = 1`, `GATE_WARN = 0` (sentinel pair).

6. In `cmd_close`, inside `acquire_close_lock` block after completeness gate check (~line
   1546) and before reservation (~1549): add placeholder call site for `warn_or_abort`
   gates (Phase 2 and 3 gates will plug in here).

7. In `cmd_close`, manifest-build site (~line 1616): add hook to compute effective status:
   ```python
   effective_status = args.status
   # Downgrade gates override effective_status before manifest write (Phases 4)
   stage_entry["substeps"][args.substep] = {
       "status": effective_status,
       ...
   }
   ```

8. In `cmd_close` confirm_study_config mutation block (~line 1630): write
   `study.strict_gates`:
   ```python
   manifest["study"]["strict_gates"] = units_payload.get("strict_gates", [])
   ```

9. In `build_parser`, `close` subparser: add `--strict-<gate_id>` generic handling.
   Because gate IDs are known at import time, add explicit flags for each non-IRR gate:
   `--strict-single-event-global-synchronic`, `--strict-undeclared-input`,
   `--strict-convergence-pending`, `--strict-temporal-order-pending`.
   Keep `--strict-irr` as an existing flag with `dest="strict_irr"` (no change).
   For `_evaluate_gate`, normalise gate_id to `strict_<gate_id.replace("-","_")}` for
   getattr lookup (e.g. `strict_single_event_global_synchronic`).

10. In `cmd_verify`: after the manifest three-way join loop (~line 1991), add a sweep over
    all audit events whose `event.action == "gate_warning"`. Print each as
    `WARN gate_warning: {gate_id} at {stage}.{substep} scope={scope}` to stdout
    (not stderr, not added to `failures`). Ensure verify returns 0 when only warnings exist.

**`microphenomenograph/1.0.0/skills/mpi-init/SKILL.md`**

11. In the `init.confirm_study_config` substep row of the Closure table, add:
    `strict_gates` (optional list of gate IDs) accepted in the confirm payload;
    defaults to `[]` when absent.

### New tests (`test_mpi_step.py`)

- `TestGateRegistry::test_gates_dict_has_required_keys` — GATES has expected gate IDs,
  each with `posture` field. (AC1.1 setup)
- `TestGateRegistry::test_warn_gate_emits_gate_warning_event_close_succeeds` — call
  `_evaluate_gate` with a `warn_or_abort` gate not in `strict_gates`; audit has
  `gate_warning`; returns 0. (AC1.1)
- `TestGateRegistry::test_strict_gate_in_manifest_aborts` — gate in `study.strict_gates`;
  `_evaluate_gate` returns non-zero. (AC1.2)
- `TestGateRegistry::test_strict_cli_flag_beats_manifest_omission` — gate NOT in manifest
  but `--strict-<gate_id>` CLI flag set; close aborts. (AC1.3)
- `TestGateRegistry::test_strict_irr_alias_unchanged` — `--strict-irr` still blocks as
  before (assert existing `irr_warning` event action unchanged). (AC1.4)
- `TestGateRegistry::test_cmd_verify_reports_gate_warning_events` — run_dir has audit.jsonl
  with a `gate_warning` event; `cmd_verify` prints WARN line; returns 0. (AC1.5)
- `TestGateRegistry::test_strict_gates_written_to_manifest_at_confirm_study_config` —
  close `confirm_study_config` with `strict_gates: ["single_event_global_synchronic"]`;
  manifest has `study.strict_gates`. (AC1.2 setup)
- `TestValidateConfirmStudyConfig::test_strict_gates_unknown_id_rejected` — unknown gate ID
  in `strict_gates` produces SchemaError. (AC1.2 guard)

---

## Phase 2: `inputs` verb + consumed-input verification

**ACs covered:** close-enforcement-2.AC2.1 – AC2.3 (partial; AC2.3 grep in
`test_close_enforcement_2.py`)

**Dependency:** Phase 1.

### Goal

Add `mpi_step.py inputs --scope --stage` subcommand that resolves upstream artifact paths
and SHAs from the manifest. Add `inputs_consumed` optional field to cross-participant
schema validators. Wire `undeclared_input` gate in `cmd_close`. Update
`mpi-cross-analyst.md` to echo `inputs_consumed`.

### Files and edits

**`microphenomenograph/1.0.0/scripts/mpi_step.py`**

1. Add `cmd_inputs(args)` function:
   - Reads `run_dir/.mpi/project.json` manifest.
   - Dispatches to resolution rules (see step 2) to get `{path: sha256}` dict.
   - Prints JSON to stdout: `{"resolved": [{"path": "...", "sha256": "..."}, ...]}`.
   - Returns 0 on success, 1 if stage/scope unknown.

2. Add resolution rules adjacent to `COMPLETENESS_GATES` usage. Reuse the
   `COMPLETENESS_GATES` table's `required_cross_participant` entries to identify upstream
   `(stage, substep)` pairs; then scan manifest participants for matching entries and read
   their `output_paths` + `artifact_shas`. Resolution rules by stage:

   - `generic_diachronic`: scope is `event<E>-cat-<C>`; upstream = all `diachronic.idu_naming_ordering`
     and all `synchronic.isu_second_level_grouping` artifacts for transcripts in `event_groups[event_id]`.
   - `generic_synchronic`: scope is `event<E>-cat-<C>-gidu<G>`; upstream = `generic_diachronic.cross_iv_contrast`
     artifact for scope `event<E>-cat-<C>`.
   - `global_synchronic`: scope is `gidu<G>-cat-<C>`; upstream = all
     `generic_synchronic.isu_second_level_grouping` artifacts whose scope matches
     `*-gidu<G>` (i.e. all events for that gidu).
   - `hypothesis`: upstream = all `global_synchronic.global_synchronic` artifacts.

3. In `cmd_close`, after completeness gate and before reservation (~line 1546): add
   `undeclared_input` gate check:
   - Load `inputs_consumed` from `units_payload.get("inputs_consumed")`.
   - If absent: skip (not a violation).
   - If present: resolve the upstream set for `(args.stage, args.scope)`.
   - Check `set(inputs_consumed) ⊆ set(resolved_paths)`.
   - If not subset: call `_evaluate_gate("undeclared_input", ...)` with the unlisted paths.
   - If `_evaluate_gate` returns non-zero (strict mode): `return _abort("undeclared_input")`.

4. In `build_parser`: add `inputs` subparser with `--scope`, `--stage`, `--run-dir`.

**`microphenomenograph/1.0.0/scripts/_mpi_schemas.py`**

5. In `_validate_generic_synchronic_isu_second_level`, `_validate_global_synchronic`,
   `_validate_generic_diachronic_cross_iv_contrast`, and `_validate_hypothesis_*`
   validators: accept (do not reject) `inputs_consumed` as an optional field of type list.
   No validation on its contents (path strings); presence vs absence checked by `cmd_close`.

**`microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`**

6. In the Persistence section, add a note under each cross-participant LLM substep:
   "Include `inputs_consumed: [<path>, ...]` in the JSON output listing the artifact paths
   you read. This enables `cmd_close` to verify your inputs are a subset of the resolved
   upstream set."

### New tests (`test_mpi_step.py`)

- `TestInputsVerb::test_inputs_generic_diachronic_resolves_upstream_transcripts` — manifest
  has event_groups + done diachronic/synchronic substeps; `cmd_inputs` returns their
  output_paths. (AC2.1)
- `TestInputsVerb::test_inputs_global_synchronic_resolves_generic_synchronic_artifacts` —
  manifest has done `generic_synchronic.isu_second_level_grouping`; `cmd_inputs` returns
  their output_paths. (AC2.1)
- `TestInputsVerb::test_inputs_unknown_stage_returns_nonzero` — unknown stage returns
  non-zero. (AC2.1 guard)
- `TestUndeclaredInputGate::test_inputs_consumed_subset_closes_clean` — close with
  `inputs_consumed` containing paths that are in the resolved set; close succeeds. (AC2.2)
- `TestUndeclaredInputGate::test_inputs_consumed_superset_warns` — `inputs_consumed` path
  not in resolved set, gate not strict; close succeeds with `gate_warning`. (AC2.2)
- `TestUndeclaredInputGate::test_inputs_consumed_superset_strict_blocks` — same but gate
  strict; close aborts. (AC2.2)
- `TestUndeclaredInputGate::test_inputs_consumed_absent_skips_check` — no `inputs_consumed`
  field; close proceeds without gate firing. (AC2.2)

### New tests (`tests/test_close_enforcement_2.py`)

- `test_no_literal_generic_synchronic_artifact_in_global_synchronic_skill` — read
  `mpi-global-synchronic/SKILL.md` and `mpi-cross-analyst.md`; assert neither contains
  the string `"generic-synchronic.md"` or `"analyses/generic-synchronic.md"`. (AC2.3)
  _(Note: this test will FAIL until Phase 3 edits land; that is intentional — it is a
  red-green gate.)_

---

## Phase 3: Global-synchronic wiring + gates

**ACs covered:** close-enforcement-2.AC2.3 (green), close-enforcement-2.AC3.1 – AC3.2

**Dependencies:** Phases 1–2.

### Goal

Fix the dead `analyses/generic-synchronic.md` references in `mpi-global-synchronic/SKILL.md`
and `mpi-cross-analyst.md`. Add `source_event` required field to `_validate_global_synchronic`.
Register and wire `single_event_global_synchronic` gate in `cmd_close`.

### Files and edits

**`microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md`**

1. Replace the "Input" section (lines 10–14):
   - Remove: `analyses/pNsN-synchronic.md` files and `analyses/generic-synchronic.md` references.
   - Replace with: "Run `python scripts/mpi_step.py inputs --scope gidu<G>-cat-<C> --stage global_synchronic --run-dir .` to resolve the correct upstream generic-synchronic artifact paths for this scope. Pass the resolved paths as inputs." Then reference the per-scope artifact form: `event<E>-cat-<C>-gidu<G>-generic_synchronic.isu_second_level_grouping.{json,md}`.

2. Fix the output path claim: The closure table already lists the correct per-scope form
   (`gidu<G>-cat-<C>-global_synchronic.{json,md,prompt.json}`). Remove any reference to
   `analyses/global-synchronic.md` as an output.

**`microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`**

3. In the "Global synchronic" task section (~line 102–117): replace
   `Read all pNsN-synchronic.md outputs AND generic-synchronic.md` with
   `Run \`mpi_step.py inputs --scope gidu<G>-cat-<C> --stage global_synchronic\` and
   read the resolved upstream generic-synchronic artifacts.`

4. In the Persistence / global_synchronic substep bash block (~line 267–285): no change to
   the `mpi_step.py close` call (already correct); add note above it:
   "Each ISU in your JSON output MUST include a `source_event` field naming which event
   (e.g. `"event1"`) the ISU came from."

**`microphenomenograph/1.0.0/scripts/_mpi_schemas.py`**

5. In `_validate_global_synchronic` (~line 274): after the ISU loop, add a per-ISU check:
   ```python
   for i, isu in enumerate(isus):
       if isinstance(isu, dict):
           if "source_event" not in isu:
               errors.append(SchemaError(
                   f"payload.isus[{i}].source_event",
                   "required field missing (must name the event this ISU came from)"
               ))
   ```
   This is a hard schema error (not a gate); close aborts on missing field. (AC3.1)

**`microphenomenograph/1.0.0/scripts/mpi_step.py`**

6. Add `_check_single_event_global_synchronic_gate` helper:
   - Only fires when `stage == "global_synchronic"`.
   - Parses `gidu<G>` from scope (split on `-cat-`, then from the gidu segment).
   - Counts distinct events in manifest that have a done
     `generic_synchronic.isu_second_level_grouping` substep whose scope matches `*-gidu<G>`.
   - If count < 2: call `_evaluate_gate("single_event_global_synchronic", ...)`.
   - Returns 0 or 1.

7. In `cmd_close`, gate evaluation site (after completeness gate, before reservation): call
   `_check_single_event_global_synchronic_gate` and propagate abort.

### New tests (`test_mpi_step.py`)

- `TestGlobalSynchronicSourceEvent::test_missing_source_event_rejected` — global_synchronic
  units JSON with ISU lacking `source_event`; `validate_units` returns SchemaError. (AC3.1)
- `TestGlobalSynchronicSourceEvent::test_source_event_present_accepted` — ISU with
  `source_event: "event1"` passes. (AC3.1)
- `TestSingleEventGate::test_single_event_scope_warns` — manifest has only 1 done
  generic_synchronic scope for gidu1; gate fires warn; close succeeds with `gate_warning`.
  (AC3.2)
- `TestSingleEventGate::test_single_event_scope_strict_blocks` — same but strict; close
  aborts. (AC3.2)
- `TestSingleEventGate::test_two_event_scope_closes_clean` — 2 distinct events done for
  gidu1; no gate warning. (AC3.2)

### Updated tests (`tests/test_close_enforcement_2.py`)

- `test_no_literal_generic_synchronic_artifact_in_global_synchronic_skill` — now passes
  (green gate from Phase 2). (AC2.3)

---

## Phase 4: Diachronic/synchronic enforcement

**ACs covered:** close-enforcement-2.AC4.1 – AC4.5

**Dependency:** Phase 1 (gate registry and downgrade mechanism).

### Goal

Implement all SKILL.md-claimed enforcement rules as real code. (1) Auto-downgrade
`criteria_revision` close to `flagged` when `decision == "more_revision_needed"`.
(2) Auto-downgrade `theme_grouping_within_idu` close to `flagged` when
`temporal_order_within_idu: true`. (3) Add schema co-presence rule: `temporal_order_within_idu: true`
requires ≥1 ISU with `flag_for_review: true`. (4) Emit `idu_split_after_synchronic` audit
event on diachronic re-close that follows a synchronic temporal-order flag. (5) Update
`mpi-analyst.md` synchronic rule 4. (6) Update SKILL.md prose to match actual enforcement.

### Files and edits

**`microphenomenograph/1.0.0/scripts/_mpi_schemas.py`**

1. In `_validate_synchronic_theme_grouping` (~line 171): add co-presence rule after the
   ISU loop:
   ```python
   flag = payload.get("temporal_order_within_idu")
   if flag is True:
       isus = payload.get("isus", [])
       any_flagged = any(
           isinstance(isu, dict) and isu.get("flag_for_review") is True
           for isu in isus
       )
       if not any_flagged:
           errors.append(SchemaError(
               "payload.temporal_order_within_idu",
               "co-presence rule: temporal_order_within_idu=true requires "
               "at least one ISU with flag_for_review=true"
           ))
   ```
   This is a hard schema error (AC4.3). Note: `_validate_synchronic_isu_naming` reuses
   `_validate_synchronic_theme_grouping`; the co-presence rule applies there too (same
   artifact shape — acceptable).

**`microphenomenograph/1.0.0/scripts/mpi_step.py`**

2. Add `_compute_effective_status(args, units_payload)` function:
   - If `stage == "diachronic"` and `substep == "criteria_revision"`:
     - Check `units_payload.get("convergence", {}).get("decision") == "more_revision_needed"`.
     - If so: return `"flagged"` and emit `convergence_pending` note (logged, not an audit event).
     - The gate is posture `"downgrade"` — `cmd_close` writes `"flagged"` as status.
   - If `stage == "synchronic"` and `substep == "theme_grouping_within_idu"`:
     - Check `units_payload.get("temporal_order_within_idu") is True`.
     - If so: return `"flagged"`.
   - Otherwise: return `args.status`.

3. In `cmd_close`, manifest-build site (~line 1616): replace
   `"status": args.status` with `"status": _compute_effective_status(args, units_payload)`.
   This implements AC4.1 (criteria_revision → flagged) and AC4.2 (theme_grouping → flagged).
   The downgrade is silent (no abort); close succeeds with status `flagged`.
   Downstream blocking is automatic via existing prereq loop (flagged ≠ done).

4. Add `_emit_idu_split_after_synchronic(run_dir, manifest, scope, close_id, audit_path, actor, actor_kind)` helper:
   - `scope` here is `pNsN` (the criteria_revision scope, i.e. the transcript key).
   - Scan `manifest["participants"]` for keys matching `{scope}-idu` prefix
     (i.e. `p1s1-idu1`, `p1s1-idu2`, etc.).
   - For each such key, check if
     `stages.synchronic.substeps.theme_grouping_within_idu.status == "flagged"`.
   - If any match: extract their `close_id` values.
   - Emit one `idu_split_after_synchronic` audit event per triggering close_id, with fields:
     ```json
     {
       "event": {"action": "idu_split_after_synchronic"},
       "mpi": {
         "triggering_close_id": "<theme_grouping close_id>",
         "reclose_close_id": "<current criteria_revision close_id>",
         "scope": "<pNsN>"
       }
     }
     ```

5. In `cmd_close`, after the existing cascade-reset block for `criteria_revision` (~line
   1795+): call `_emit_idu_split_after_synchronic(...)` when
   `stage == "diachronic"` and `substep == "criteria_revision"`.
   The helper self-guards (emits nothing if no flagged IDU-scoped synchronic entries found).
   (AC4.4)

**`microphenomenograph/1.0.0/agents/mpi-analyst.md`**

6. In synchronic analysis rule 4 (~line 69): update wording to:
   "**Temporal order within an IDU**: If ISUs within one IDU appear to be temporally
   ordered, this indicates the IDU should be split. You MUST set BOTH `flag_for_review: true`
   AND `temporal_order_within_idu: true` on the artifact. `cmd_close` will automatically
   downgrade this substep to `flagged` status and block `isu_naming` until a
   `diachronic.criteria_revision` re-close resolves the split." (AC4.2 + flag-unification AC)

**`microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md`**

7. In the `criteria_revision` substep row of the Closure table: update Notes to:
   "JSON must include `convergence: {decision, reason}`; if `decision == 'more_revision_needed'`,
   `cmd_close` automatically sets substep status to `flagged` (blocking `idu_naming_ordering`
   until a converged re-close); orchestrator re-dispatches, capped at 5 passes."

**`microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md`**

8. In the `theme_grouping_within_idu` substep row: update Notes to:
   "If `temporal_order_within_idu: true`, `cmd_close` automatically downgrades to `flagged`
   (blocking `isu_naming`); `temporal_order_within_idu: true` also requires ≥1 ISU with
   `flag_for_review: true` (hard schema). Manifest records `idu_split_after_synchronic`
   audit event when a diachronic re-close follows this flag."

### New tests (`test_mpi_step.py`)

- `TestConvergenceDowngrade::test_more_revision_needed_sets_flagged` — close
  `criteria_revision` with `convergence.decision == "more_revision_needed"`; manifest
  substep status is `flagged`, close returns 0. (AC4.1)
- `TestConvergenceDowngrade::test_converged_sets_done` — `decision == "converged"`;
  status is `done`. (AC4.1)
- `TestConvergenceDowngrade::test_idu_naming_blocked_while_criteria_revision_flagged` —
  attempt `idu_naming_ordering` close when `criteria_revision` is `flagged`; prereq check
  blocks (rc != 0). (AC4.1 downstream blocking)
- `TestTemporalOrderDowngrade::test_temporal_order_true_sets_flagged` — close
  `theme_grouping_within_idu` with `temporal_order_within_idu: true` and ≥1 flagged ISU;
  substep status `flagged`, close rc 0. (AC4.2)
- `TestTemporalOrderDowngrade::test_temporal_order_false_sets_done` — `temporal_order_within_idu:
  false`; status `done`. (AC4.2)
- `TestTemporalOrderDowngrade::test_isu_naming_blocked_while_theme_grouping_flagged` —
  attempt `isu_naming` when `theme_grouping_within_idu` is `flagged`; blocked. (AC4.2)
- `TestCoPresenceSchema::test_temporal_order_true_requires_flag_for_review` — call
  `validate_units("synchronic", "theme_grouping_within_idu", ...)` with
  `temporal_order_within_idu: true` but all ISUs `flag_for_review: false`; SchemaError
  returned. (AC4.3)
- `TestCoPresenceSchema::test_temporal_order_true_with_flagged_isu_accepted` — same but
  one ISU has `flag_for_review: true`; no schema error. (AC4.3)
- `TestIduSplitAuditEvent::test_reclose_after_temporal_flag_emits_idu_split_event` — set
  up manifest with `p1s1-idu1.synchronic.theme_grouping_within_idu.status = "flagged"`;
  close `diachronic.criteria_revision` for `p1s1`; audit.jsonl contains
  `idu_split_after_synchronic` event with `triggering_close_id` matching the stored
  `close_id` of the flagged substep. (AC4.4)
- `TestIduSplitAuditEvent::test_no_idu_split_event_without_prior_flag` — criteria_revision
  re-close with no flagged synchronic substeps; no `idu_split_after_synchronic` event. (AC4.4)

### New tests (`tests/test_close_enforcement_2.py`)

- `test_diachronic_skill_convergence_claim_has_code_path` — grep
  `mpi-diachronic/SKILL.md` for `"flagged"`; grep `mpi_step.py` for
  `"more_revision_needed"` and `"convergence_pending"`; both present. (AC4.5 parity)
- `test_synchronic_skill_temporal_order_claim_has_code_path` — grep
  `mpi-synchronic/SKILL.md` for `"flagged"`; grep `mpi_step.py` for
  `"temporal_order_within_idu"` and `"temporal_order_pending"`; both present. (AC4.5)
- `test_idu_split_audit_event_claim_has_code_path` — grep
  `mpi-synchronic/SKILL.md` for `"idu_split_after_synchronic"`; grep `mpi_step.py` for
  `"idu_split_after_synchronic"`; both present. (AC4.5)

---

## Dependency graph

```
Phase 1 (GATES registry + manifest strictness)
    └── Phase 2 (inputs verb + undeclared_input gate)
            └── Phase 3 (global-synchronic wiring + single_event gate)
Phase 1
    └── Phase 4 (diachronic/synchronic enforcement)
```

Phase 4 is independent of Phases 2–3 and may be implemented in parallel with Phase 2
once Phase 1 is done.

## Incremental test-run strategy

After each phase, run:
```
pytest microphenomenograph/1.0.0/scripts/ -q
pytest tests/ -q
```

Expected baseline: 1 known failure (`test_verify_mpi_init.py::test_all`). No new failures
introduced. The `test_no_literal_generic_synchronic_artifact_in_global_synchronic_skill`
test in `tests/test_close_enforcement_2.py` will fail until Phase 3 edits land (that is
the intended red-green gate for AC2.3).

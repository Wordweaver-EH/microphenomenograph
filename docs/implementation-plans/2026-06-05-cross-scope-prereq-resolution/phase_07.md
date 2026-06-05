# Pipeline Correctness Implementation Plan — Phase 7

**Goal:** Add `COMPLETENESS_GATES` table to `_mpi_schemas.py` and `_check_completeness_gate()` to `mpi_step.py`; call it from `cmd_close` between the IRR gate check and substep reservation; clean up the advisory warning in `mpi-generic-diachronic` SKILL.md; add a completeness invariant check to `cmd_verify`.

**Architecture:** Modelled exactly on `_check_irr_gate` (lines 1011–1082 of `mpi_step.py`): a function that reads `manifest["study"]["event_groups"]`, extracts the event ID from the scope key (via `_scope_strip_to_event` — already added in Phase 2), iterates the relevant transcript IDs, and verifies all required upstream substeps are `done`. The insert point is between line 1269 (end of IRR gate block) and line 1271 (start of substep reservation). Legacy manifests (no `event_groups`) emit a warning and proceed.

**Tech Stack:** Python 3, pytest.

**Scope:** Phase 7 of 8 (depends on Phase 1 for `study.event_groups`; also uses `_scope_strip_to_event` from Phase 2).

**Codebase verified:** 2026-06-05

**Investigator findings:**
- `_check_irr_gate` signature: `(run_dir, stage, substep, scope, args, audit_path) -> int` at line 1011.
- IRR gate call site: lines 1263–1269; `_check_completeness_gate` inserts at line 1270.
- `cmd_verify` checks manifest-audit integrity only; no cross-participant completeness logic.
- `COMPLETENESS_GATES` and `_scope_strip_to_event` confirmed absent (will be added by Phases 2 and 7 respectively; note: in a real implementation, Phase 2 must land before Phase 7).
- `mpi-generic-diachronic` completeness warning (lines 11-26): advisory, does not abort.
- No existing completeness gate tests.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC7: Event-group completeness gates enforced by `close`
- **cross-scope-prereq-resolution.AC7.1 Success:** `study.event_groups` is written to the manifest at `init.confirm_study_config` close; it maps event IDs to lists of transcript IDs (e.g. `{"event1": ["p1s1", "p2s1", "p3s1"]}`). The mapping is study-design-agnostic — any string event ID, any list of transcript IDs. *(Implemented in Phase 1; verified here via integration.)*
- **cross-scope-prereq-resolution.AC7.2 Failure:** `cmd_close` for `generic_diachronic.participant_row_assembly` (scope `event3-cat-low`) fails `completeness_gate_unsatisfied` when any transcript in `event_groups["event3"]` has `diachronic.idu_naming_ordering` or any synchronic substep not `done`.
- **cross-scope-prereq-resolution.AC7.3 Success:** Same close succeeds once all transcripts in `event_groups["event3"]` have all required upstream substeps `done`.
- **cross-scope-prereq-resolution.AC7.4 Success:** All four cross-participant gate chains are enforced in turn: `generic_synchronic.*` gates on `generic_diachronic.*` done for the event; `global_synchronic.*` gates on `generic_synchronic.*` done; `hypothesis.*` gates on all cross-participant stages done.
- **cross-scope-prereq-resolution.AC7.5 Degraded:** A manifest that pre-dates this change (no `event_groups` key) emits a `completeness_gate_skipped: event_groups_missing` warning and proceeds rather than hard-blocking.
- **cross-scope-prereq-resolution.AC7.6 Cleanup:** The advisory completeness warning in `mpi-generic-diachronic` SKILL.md is removed or downgraded to a pre-flight UX hint; `close` is now the enforcement point.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add `COMPLETENESS_GATES` to `_mpi_schemas.py`

**Verifies:** cross-scope-prereq-resolution.AC7.2, AC7.3, AC7.4 (data structure only; logic in Phase 7 Task 2)

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**Implementation:**

Add after `PREREQ_SCOPE_TRANSFORMS` (added in Phase 2), before the prompt artifact validator section:

```python
# ---------------------------------------------------------------------------
# Cross-participant completeness gates
# ---------------------------------------------------------------------------
# Maps each cross-participant stage to the upstream substeps that must be
# done for ALL transcripts in the event before a close can proceed.
#
# Structure:
#   stage -> {
#     "scope_to_event": callable(scope: str) -> str | None,
#       # Returns the event ID to look up in event_groups.
#       # Returns None to check ALL events (global stages).
#     "required_per_transcript": list[tuple[str, str]]
#       # (stage, substep) pairs that must be done for each transcript ID
#       # in the event. For IDU-scoped stages (synchronic), the check scans
#       # all pNsN-iduK keys for that transcript.
#     "required_cross_participant": list[tuple[str | None, str, str]]
#       # (key_prefix, stage, substep) — for stages where the prereq scope is not
#       # transcript-level. Each entry: check that ANY participant key matching
#       # key_prefix has that stage/substep done.
#       # key_prefix=None → use the event ID from events_to_check (e.g. "event1")
#       # key_prefix="global" → match the literal "global" key (global_synchronic)
#       # Empty list if not applicable.
#   }
#
# Note: _scope_strip_to_event is defined in this module (Phase 2).

def _scope_to_event_all(_scope: str) -> None:  # type: ignore[return]
    """Sentinel: check ALL events (for global-scope stages)."""
    return None


COMPLETENESS_GATES: dict[str, dict] = {
    "generic_diachronic": {
        # scope: event<E>-cat-<C>
        "scope_to_event": _scope_strip_to_event,   # defined in Phase 2
        "required_per_transcript": [
            ("diachronic", "idu_naming_ordering"),
            # synchronic: all IDU scopes for the transcript must have
            # isu_second_level_grouping done — checked by scanning pNsN-iduK keys
            ("synchronic", "isu_second_level_grouping"),
        ],
        "required_cross_participant": [],
    },
    "generic_synchronic": {
        # scope: event<E>-cat-<C>-gidu<G>
        "scope_to_event": _scope_strip_to_event,
        "required_per_transcript": [],
        "required_cross_participant": [
            # key_prefix=None → match pids starting with the event ID (e.g. "event1-cat-...")
            (None, "generic_diachronic", "cross_iv_contrast"),
        ],
    },
    "global_synchronic": {
        # scope: global (or per generic-IDU × IV category)
        "scope_to_event": _scope_to_event_all,
        "required_per_transcript": [],
        "required_cross_participant": [
            # key_prefix=None → match pids starting with each event ID
            (None, "generic_synchronic", "isu_second_level_grouping"),
        ],
    },
    "hypothesis": {
        # scope: dv-<focus> or global
        "scope_to_event": _scope_to_event_all,
        "required_per_transcript": [],
        "required_cross_participant": [
            # key_prefix="gidu" → match gidu<G>-cat-<C> participant keys.
            # global_synchronic.global_synchronic is recorded under scope gidu<G>-cat-<C>
            # (confirmed: mpi-global-synchronic SKILL.md line 33; mpi-cross-analyst.md).
            # Do NOT use key_prefix=None (event-ID prefix) — gidu keys are NOT prefixed
            # by event ID.
            # Do NOT use key_prefix="global" — no participant key is literally "global".
            ("gidu", "global_synchronic", "global_synchronic"),
        ],
    },
}
```

**Commit:** `feat: add COMPLETENESS_GATES table to _mpi_schemas.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add `_check_completeness_gate()` to `mpi_step.py` and wire into `cmd_close`

**Verifies:** AC7.2, AC7.3, AC7.4, AC7.5

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation — update import:**

Add `COMPLETENESS_GATES` to the import at line 29:
```python
from _mpi_schemas import (
    validate_units, validate_prompt_artifact,
    SUBSTEP_PREREQUISITES, LLM_SUBSTEPS, PREREQ_SCOPE_TRANSFORMS, COMPLETENESS_GATES,
)
```

**Implementation — add `_check_completeness_gate` function:**

Add after `_check_irr_gate` (after ~line 1082), modelled on `_check_irr_gate`'s structure:

```python
def _check_completeness_gate(
    run_dir: Path,
    manifest: dict,
    stage: str,
    scope: str,
    args,
    audit_path: Path,
) -> int:
    """
    For cross-participant stages, verify that all required upstream substeps are done
    for all relevant transcripts in the event group.

    Reads study.event_groups from the manifest. If absent (legacy manifest), emits a
    completeness_gate_skipped warning and returns 0.

    Returns 0 to proceed, 1 to block.
    """
    gate = COMPLETENESS_GATES.get(stage)
    if gate is None:
        return 0  # Stage has no completeness gate

    study = manifest.get("study", {})
    event_groups = study.get("event_groups")

    if not event_groups:
        # Legacy manifest without event_groups — warn and proceed
        run_id = load_or_create_run_id(run_dir / ".mpi" / "run_id")
        warn_event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": datetime.now(timezone.utc).isoformat(),  # datetime/timezone already imported
            "trace_id": run_id,
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "orchestrator", "name": "orchestrator"},
            "event": {"kind": "event", "action": "completeness_gate_skipped",
                      "outcome": "warning"},
            "mpi": {"stage": stage, "scope": scope},
            "reason": "completeness_gate_skipped: event_groups_missing in study block",
        }
        append_jsonl(audit_path, warn_event)
        print(
            f"WARNING completeness_gate_skipped: event_groups not in manifest; "
            f"completeness gate for {stage} bypassed",
            file=sys.stderr,
        )
        return 0

    # Determine which events to check
    scope_to_event_fn = gate.get("scope_to_event")
    event_id = scope_to_event_fn(scope) if scope_to_event_fn else None

    if event_id is not None:
        events_to_check = {event_id: event_groups.get(event_id, [])}
    else:
        events_to_check = event_groups  # all events

    participants = manifest.get("participants", {})
    required_per_transcript = gate.get("required_per_transcript", [])
    required_cross_participant = gate.get("required_cross_participant", [])

    for evt_id, transcript_ids in events_to_check.items():
        # Check per-transcript requirements
        for transcript_id in transcript_ids:
            for req_stage, req_substep in required_per_transcript:
                if req_stage == "synchronic":
                    # Synchronic is IDU-scoped: check all pNsN-iduK keys for this transcript
                    idu_prefix = f"{transcript_id}-idu"
                    found_any_idu = False
                    for pid, pdata in participants.items():
                        if not pid.startswith(idu_prefix):
                            continue
                        found_any_idu = True
                        status = (pdata.get("stages", {})
                                       .get(req_stage, {})
                                       .get("substeps", {})
                                       .get(req_substep, {})
                                       .get("status"))
                        if status != "done":
                            print(
                                f"ERROR completeness_gate_unsatisfied: "
                                f"{transcript_id} {req_stage}.{req_substep} "
                                f"status={status!r} (event {evt_id})",
                                file=sys.stderr,
                            )
                            return 1
                    if not found_any_idu:
                        print(
                            f"ERROR completeness_gate_unsatisfied: "
                            f"no IDU scopes found for {transcript_id} "
                            f"— {req_stage}.{req_substep} not done (event {evt_id})",
                            file=sys.stderr,
                        )
                        return 1
                else:
                    # Transcript-scoped: look up directly by transcript_id
                    status = (participants.get(transcript_id, {})
                                         .get("stages", {})
                                         .get(req_stage, {})
                                         .get("substeps", {})
                                         .get(req_substep, {})
                                         .get("status"))
                    if status != "done":
                        print(
                            f"ERROR completeness_gate_unsatisfied: "
                            f"{transcript_id} {req_stage}.{req_substep} "
                            f"status={status!r} (event {evt_id})",
                            file=sys.stderr,
                        )
                        return 1

        # Check cross-participant requirements for this event
        # Each entry is a 3-tuple: (key_prefix, req_stage, req_substep)
        # key_prefix=None → match participant keys for this specific event:
        #   pid == evt_id OR pid.startswith(evt_id + "-")
        #   (the "+"-" boundary prevents event1 from matching event12, event13 etc.)
        # key_prefix=str  → match pids that startswith that literal string
        for key_prefix, req_stage, req_substep in required_cross_participant:
            found_done = False
            for pid, pdata in participants.items():
                if key_prefix is None:
                    # Event-ID boundary match: exact equality OR evt_id + "-" prefix
                    if not (pid == evt_id or pid.startswith(evt_id + "-")):
                        continue
                else:
                    if not pid.startswith(key_prefix):
                        continue
                status = (pdata.get("stages", {})
                               .get(req_stage, {})
                               .get("substeps", {})
                               .get(req_substep, {})
                               .get("status"))
                if status == "done":
                    found_done = True
                    break
            if not found_done:
                eff = f"{evt_id}(-)" if key_prefix is None else key_prefix
                print(
                    f"ERROR completeness_gate_unsatisfied: "
                    f"no {req_stage}.{req_substep} done "
                    f"(prefix={eff!r}, event={evt_id})",
                    file=sys.stderr,
                )
                return 1

    return 0
```

**Implementation — wire into `cmd_close`:**

After the IRR gate block (line 1269), before `_acquire_substep_reservation` (line 1271), add:

```python
    # --- Completeness gate check ---
    # For cross-participant stages, verify all upstream transcripts are complete.
    # Reads study.event_groups; legacy manifests (no event_groups) warn and proceed.
    if args.stage in cross_participant_stages:
        completeness_rc = _check_completeness_gate(
            run_dir, manifest, args.stage, args.scope, args, audit_path
        )
        if completeness_rc != 0:
            return _abort("completeness_gate_unsatisfied")
```

Note: `cross_participant_stages` is already defined at line 1265; reuse it.

**Commit:** `feat: add _check_completeness_gate and wire into cmd_close for cross-participant stages`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Cleanup SKILL.md advisory warning + cmd_verify + tests

**Verifies:** AC7.5, AC7.6

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (`cmd_verify`)
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py`

**3a. Update mpi-generic-diachronic SKILL.md:**

Replace the "Completeness check" section (lines 11-26) with a lighter pre-flight note:

```markdown
## Pre-flight note

Before invoking the cross-analyst, `mpi_step.py close` will enforce completeness: all
transcripts in the event must have `diachronic.*` and `synchronic.*` done. If any are
missing, the close will fail with `completeness_gate_unsatisfied`.

You can check current status with `/mpi status` before proceeding.
```

Remove the `Do NOT abort — ask the user...` instruction and the `Verifies: microphenomenograph.AC5.3` note (the gate is now enforced by `close`, not by the skill).

**3b. Add completeness invariant to `cmd_verify`:**

Find `cmd_verify` (~line 1622). After the three-way join checks (manifest + audit + git), add a completeness invariant sweep:

```python
    # Completeness invariant: cross-participant done substeps should not have
    # incomplete upstream entries.
    event_groups = manifest.get("study", {}).get("event_groups")
    if event_groups:
        for stage, gate in COMPLETENESS_GATES.items():
            # Find all done substeps for this stage in the manifest
            for pid, pdata in manifest.get("participants", {}).items():
                for substep_name, substep_data in (
                    pdata.get("stages", {}).get(stage, {}).get("substeps", {}).items()
                ):
                    if substep_data.get("status") == "done":
                        # Re-run completeness check for this scope
                        rc = _check_completeness_gate(
                            run_dir, manifest, stage, pid, args, audit_path
                        )
                        if rc != 0:
                            failures.append(  # cmd_verify uses `failures`, not `issues` (line 1654)
                                f"completeness_invariant_violated: {stage} "
                                f"{substep_name} is done under {pid} but upstream "
                                f"transcripts are incomplete"
                            )
                            break
```

Note: `cmd_verify` builds a `failures` list (not `issues` — confirmed at line 1654) and reports them at the end. Follow the existing pattern. The snippet passes `pid` as the `scope` argument and the `args` namespace from `cmd_verify` directly to `_check_completeness_gate`. This is safe because `_check_completeness_gate` reads `args` only for IRR-like features we don't use here; it does not read `args.scope` when called from verify. State this explicitly in a comment at the call site.

**3c. Add tests `TestCompletenessGates` to `test_mpi_step.py`:**

Integration tests using `mpi_step.main(["close", ...])` with a temp run directory that has `study.event_groups` populated.

Tests must verify:

- **AC7.2:** Close for `generic_diachronic.participant_row_assembly` scope `event3-cat-low` fails `completeness_gate_unsatisfied` when `event_groups["event3"]` lists `p1s3` and `p2s3` but `p2s3.diachronic.idu_naming_ordering` is pending.
- **AC7.3:** Same close succeeds when both `p1s3` and `p2s3` have `diachronic.idu_naming_ordering` done and all synchronic IDU substeps done.
- **AC7.5:** Close succeeds (with warning on stderr) when manifest has no `event_groups` key.
- **AC7.4 (generic_synchronic chain):** Close for `generic_synchronic.*` fails when `generic_diachronic.cross_iv_contrast` is not done for the event.
- **AC7.4 (hypothesis chain — critical coverage):** Close for `hypothesis.evidence_extraction` (scope `dv-attention`) fails when no `gidu1-cat-low.global_synchronic.global_synchronic` entry is `done`. Same close SUCCEEDS after a `gidu1-cat-low` entry has `global_synchronic.global_synchronic` status=`done`. This test is required because the hypothesis gate uses `key_prefix="gidu"` matching, which was a defect in the prior plan version; this test would catch a regression.
- **AC7.4 (event prefix non-collision):** Manifest has both `event1` and `event12` in `event_groups`. Close for `generic_diachronic.*` scope `event1-cat-low` only checks `event1` transcripts, not `event12` transcripts (boundary match `evt_id + "-"` enforced).

Use a manifest fixture helper that creates a v2.0 manifest with `study.event_groups` populated and the specified substeps pre-marked as done.

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py::TestCompletenessGates -v
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
```
Expected: new AC7 tests pass; full suite passes.

**Commit:** `feat: completeness gate cleanup — SKILL.md advisory removed, verify integration, tests for AC7`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

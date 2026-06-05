# Test Requirements — Pipeline Correctness (Cross-Scope Prereq Resolution)

Source design: `docs/design-plans/2026-06-05-cross-scope-prereq-resolution.md`
Implementation plans: `docs/implementation-plans/2026-06-05-cross-scope-prereq-resolution/phase_01.md` … `phase_08.md`

This document maps every acceptance criterion (AC1–AC8, with sub-criteria) to its automated
test coverage and, where automation cannot fully verify the criterion, to a human-verification
approach with justification.

## Conventions and classification rules

Tests are classified against the implementation decisions, not against criterion text alone:

- **unit** — the test calls a pure function directly with in-memory inputs; no run directory,
  no git, no `main()`. Applies to schema validators (`validate_units()`, the `_validate_*`
  functions) and the pure scope/key helpers (`_scope_strip_to_event()`,
  `_prereq_participant_key()`).
- **integration** — the test calls `mpi_step.main(["close", ...])` or `["verify", ...]`
  against a real temporary run directory with `git init`, exercising the full close protocol
  (validate → audit → manifest mutation → commit) or verify three-way join.
- **integration (subprocess/concurrency)** — AC4 only: tests launch concurrent
  `mpi_step.py close` processes via `subprocess.Popen`, plus an in-process threading test that
  proves the lock blocks deterministically.

File-path placement:

- Per-substep validator tests and close/verify integration tests live in
  `microphenomenograph/1.0.0/scripts/test_mpi_step.py`.
- Suite-level structural / documentation-content checks live in `tests/`.

A criterion is marked **human verification** when a Python test cannot assert its substance —
specifically when the property under test is produced by a skill/LLM (offset byte computation,
disclaimer output text) or is documentation prose. The phase plans claim coverage broadly; the
discriminator applied below is "does the named test actually assert this property, or only an
adjacent structural one."

---

## AC1: Deterministic scope transform resolves `worksheet_assembly` prereq

Phases: 2 (table + helper), 3 (wire into `cmd_close`).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC1.1 — close for `generic_synchronic.worksheet_assembly` (scope `event3-cat-low-gidu1`) succeeds when `select_generic_idus_of_interest` is done under key `event3` | integration | `TestPrereqScopeResolutionClose::test_worksheet_assembly_succeeds_when_event_prereq_done` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC1.2 — same close fails `prereq_unsatisfied` when no `select_generic_idus_of_interest` entry exists | integration | `TestPrereqScopeResolutionClose::test_worksheet_assembly_fails_when_event_prereq_missing` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC1.3 — `_scope_strip_to_event("event12-cat-moderate-gidu3")` returns `"event12"` | unit | `TestPrereqScopeResolution::test_scope_strip_to_event_double_digit` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |

Notes: AC1.3 is a pure-function unit test (Phase 2 Task 2) covering single-digit, double-digit,
and the no-`-cat-` defensive-fallback cases. AC1.1/AC1.2 are integration tests driving the
prereq loop after `PREREQ_SCOPE_TRANSFORMS` is wired in (Phase 3 Task 3).

**Human verification:** none required.

---

## AC2: All-match semantics gate `weak_evidence_review` correctly

Phases: 2 (`"all_match"` sentinel), 3 (`_all_candidate_draftings_done` + loop).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC2.1 — close for `hypothesis.weak_evidence_review` (scope `global`) succeeds when every `candidate_drafting` entry is `done` | integration | `TestPrereqScopeResolutionClose::test_weak_evidence_review_succeeds_when_all_draftings_done` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC2.2 — same close fails `prereq_unsatisfied` when no `candidate_drafting` entry exists at all | integration | `TestPrereqScopeResolutionClose::test_weak_evidence_review_fails_when_no_draftings` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC2.3 — close fails when all `candidate_drafting` entries are `done` except one `pending` | integration | `TestPrereqScopeResolutionClose::test_weak_evidence_review_fails_on_one_pending` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC2.4 — close fails when a `candidate_drafting` entry has status `flagged` | integration | `TestPrereqScopeResolutionClose::test_weak_evidence_review_fails_on_flagged` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC2.5 — with `study.dv_focuses` absent/null, all-match uses the manifest scan (AC2.1–AC2.4 semantics) | integration | `TestPrereqScopeResolutionClose::test_weak_evidence_review_manifest_scan_when_dv_focuses_null` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |

Notes: AC2.3's fixture must contain a present-but-`pending` `candidate_drafting` participant
entry (per Phase 3 Task 3); the missing-entry case for a declared focus is AC8.3 and belongs to
Phase 8. AC2.5 pins the null-`dv_focuses` fallback path; the non-null path is AC8.3.

**Human verification:** none required.

---

## AC3: Backward compatibility

Phases: 2 (unit), 3 (integration + full suite).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC3.1 — synchronic → diachronic scope stripping (`p1s1-idu2` → `p1s1`) still works | unit | `TestPrereqScopeResolution::test_prereq_key_synchronic_to_diachronic_strip` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC3.1 (integration) — close for `synchronic.theme_grouping_within_idu` scope `p1s1-idu2` resolves `diachronic.idu_naming_ordering` under key `p1s1` | integration | `TestPrereqScopeResolutionClose::test_synchronic_resolves_diachronic_prereq` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC3.2 — same-scope prereqs use the unchanged participant key | unit | `TestPrereqScopeResolution::test_prereq_key_same_scope_unchanged` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC3.3 — all existing tests pass without modification | meta (full-suite regression) | — (no discrete new test; see below) | `tests/` + `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |

Notes on AC3.3: this is a meta-criterion verified by running the full suite, not by a new test
function. Verification command:

```
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py
```

Expected: every pre-existing test passes unchanged. The optional-parameter defaults on
`_prereq_participant_key` (Phase 3 Task 1) are the mechanism that preserves all existing call
sites.

**Human verification:** none required. AC3.3 is automated as a regression run; no manual step.

---

## AC4: Manifest write safety under parallel closes

Phase: 4 (`acquire_close_lock` + lock-wrapped `cmd_close`).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC4.1 — two parallel closes on different participants both commit; both entries show `done` | integration (subprocess concurrency) | `TestManifestWriteSafety::test_parallel_closes_both_commit` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC4.2 — a close acquiring the lock reads the manifest after prior holders write/commit; no mutation silently overwritten | integration (subprocess concurrency) | `TestManifestWriteSafety::test_both_participants_present_after_parallel_closes` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC4.3 — a lock-holding process interrupted (SIGTERM / `terminate()`) leaves the lock file re-lockable; subsequent `acquire_close_lock` succeeds without blocking | integration (subprocess) + unit (context manager) | `TestManifestWriteSafety::test_lock_relockable_after_interrupt` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC4 (lock correctness, supporting) — the lock deterministically blocks a second acquirer until the first releases | integration (in-process threading) | `TestManifestWriteSafety::test_lock_serializes_concurrent_acquirers` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |

Notes: AC4.1/AC4.2 use `subprocess.Popen` to launch two simultaneous `mpi_step.py close`
processes (`p1s1` and `p2s1`, both `diachronic.criteria_grouping`) and assert both exit 0 and
both manifest entries are `done`. AC4.3 asserts **re-lockability**, not file absence — the lock
file persists by design. Use `process.terminate()` for cross-platform portability (no native
`SIGTERM` on Windows). The serialization test is a deterministic correctness test (not a
timing/race-winning test); it works on both POSIX `fcntl.flock` and Windows `LockFileEx`.

**Human verification:** none required for the acceptance criteria. Optional advisory note —
the supporting concurrency tests are timing-adjacent; if the subprocess tests prove flaky in CI,
the in-process serialization test (`test_lock_serializes_concurrent_acquirers`) is the
authoritative deterministic proof of the lock contract and should be treated as the gate.

---

## AC5: `transcript_prep` closes via `cmd_close`

Phase: 5 (validators + prereq chain + dispatch).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC5.1 — `close --stage transcript_prep --substep hash_raw` with valid units-json succeeds and commits | integration | `TestTranscriptPrepValidators::test_close_hash_raw_succeeds` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC5.2 — `close --substep normalize` succeeds with valid normalized artifact path | integration | `TestTranscriptPrepValidators::test_close_normalize_succeeds_after_hash_raw` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC5.3 — `close --substep register_offsets` succeeds with valid offsets JSON | integration | `TestTranscriptPrepValidators::test_close_register_offsets_succeeds_after_normalize` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC5.4 — missing required fields in units-json (e.g. no `transcript_id`) rejected with `schema_validation_failed` | unit | `TestTranscriptPrepValidators::test_hash_raw_missing_transcript_id_rejected` (plus `_missing_sha256`, `_missing_byte_size`, `normalize_missing_diff_path`, `register_offsets_missing_utterance_count`, `unknown_substep`, `unknown_stage`) | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC5.5 — prereq ordering enforced: `normalize` rejects until `hash_raw` done; `register_offsets` rejects until `normalize` done | integration | `TestTranscriptPrepValidators::test_normalize_rejected_before_hash_raw`, `test_register_offsets_rejected_before_normalize`, `test_register_offsets_rejected_with_only_hash_raw_done` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |

Notes: AC5.4 is a set of pure `validate_units("transcript_prep", ..., payload)` unit tests
(Phase 5 Task 2 schema block), including the `unknown_stage` case that proves `transcript_prep`
is now a recognized stage. AC5.5 is integration: it drives the DAG prereq loop through real
closes against a temp run directory.

**Human verification:** none required.

---

## AC6: Offset files use flat-dict format aligned to utterance boundaries

Phase: 6 (format guard in `_validate_transcript_prep_register_offsets`; SKILL.md byte-range spec).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC6.1 — offset file is a flat dict keyed by string utterance number `{"1": {"byte_start": N, "byte_end": N}, ...}` | unit | `TestOffsetFileFormat::test_valid_flat_dict_accepted` (plus `test_non_integer_key_rejected`, `test_entry_missing_byte_start_rejected`, `test_non_dict_entry_rejected`, `test_nonexistent_path_no_error`) | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC6.2 — `byte_start` is the first char of the speaker label; `byte_end` is the last char before the line ending; one physical line per utterance | **human verification** (partial automation possible via golden fixture) | `TestOffsetFileFormat::test_golden_fixture_byte_ranges_resolve` (optional, supporting only) | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC6.3 — `utterance_refs` citing utterance 3 use `byte_start`/`byte_end` that match the full text of utterance 3 in the raw file | **human verification** (partial automation possible via golden fixture) | `TestOffsetFileFormat::test_golden_fixture_utterance_ref_round_trips` (optional, supporting only) | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC6.4 — an old array-format offset file (`{"transcript_id": ..., "utterances": [...]}`) causes `cmd_close` to reject with a descriptive error | unit | `TestOffsetFileFormat::test_old_array_format_rejected` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |

Notes: AC6.1 and AC6.4 are pure validator unit tests — the Phase 6 guard checks **structural
shape only** (keys int-castable, entries carry `byte_start`/`byte_end`, top-level
`"utterances"` key rejected). These are fully automated.

**Human verification (AC6.2, AC6.3):** the validator does **not** assert that `byte_start`
actually points at the first character of the speaker label, nor that a `utterance_refs` byte
range round-trips to the exact raw text of utterance 3. Those properties belong to the
*skill-produced* offset computation, not to the format guard. Phase 6 attributes AC6.2 to a
documentation task (the SKILL.md byte-range definition), not to a test assertion — confirming it
is not behaviorally automated.

- Justification: byte-offset correctness is a property of LLM/orchestrator-generated artifacts.
  No code in this design computes or recomputes offsets at close time; it only checks format.
- Manual approach: on a real run, take one raw transcript, pick utterance 3, and confirm that
  `offsets["3"]["byte_start"]`/`["byte_end"]` slice the raw file (`raw[byte_start:byte_end+1]`)
  to exactly the full text of utterance 3 including the speaker label. Cross-check one
  diachronic/synchronic `utterance_refs` entry against the same slice.
- Optional partial automation: a hand-built golden fixture (a fixed raw transcript + a correct
  offset file + a `utterance_refs` artifact) can assert round-trip equality. If added, document
  explicitly that this exercises the **span validator's** matching logic, not the skill's offset
  computation — it does not close the gap for offsets produced by a real run.

---

## AC7: Event-group completeness gates enforced by `close`

Phases: 1 (`event_groups` written at `confirm_study_config`), 7 (`COMPLETENESS_GATES` +
`_check_completeness_gate` + verify integration + SKILL.md cleanup).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC7.1 — `study.event_groups` written to manifest at `init.confirm_study_config` close; maps event IDs to transcript-ID lists | integration | `TestConfirmStudyConfigClose::test_event_groups_written_to_manifest` (plus `test_event_groups_values_preserved_exactly`) | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC7.1 (schema gate) — `confirm_study_config` requires `event_groups`; malformed shapes rejected | unit | `TestInitValidators::test_confirm_study_config_valid`, `test_confirm_study_config_missing_event_groups_rejected`, `test_event_groups_non_list_value_rejected` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC7.2 — close for `generic_diachronic.participant_row_assembly` (scope `event3-cat-low`) fails `completeness_gate_unsatisfied` when any transcript in `event_groups["event3"]` has upstream substeps not `done` | integration | `TestCompletenessGates::test_generic_diachronic_blocks_on_incomplete_transcript` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC7.3 — same close succeeds once all transcripts in `event_groups["event3"]` have required upstream substeps `done` | integration | `TestCompletenessGates::test_generic_diachronic_succeeds_when_event_complete` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC7.4 — all four cross-participant gate chains enforced (`generic_synchronic` on `generic_diachronic`; `global_synchronic` on `generic_synchronic`; `hypothesis` on global_synchronic) | integration | `TestCompletenessGates::test_generic_synchronic_gates_on_generic_diachronic`, `test_hypothesis_gates_on_global_synchronic_gidu_prefix`, `test_hypothesis_gate_succeeds_after_gidu_done`, `test_event_prefix_non_collision_event1_vs_event12` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC7.5 — legacy manifest (no `event_groups`) emits `completeness_gate_skipped: event_groups_missing` warning and proceeds | integration | `TestCompletenessGates::test_legacy_manifest_warns_and_proceeds` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC7.6 — advisory completeness warning removed/downgraded in `mpi-generic-diachronic` SKILL.md | **human verification** (structural check automatable in `tests/`) | `test_generic_diachronic_skill_has_no_advisory_abort` (optional structural) | `tests/test_plugin_structure.py` |

Notes:

- AC7.1's manifest-write half is integration (Phase 1 Task 2, `TestConfirmStudyConfigClose`);
  the schema-validation half is unit (Phase 1 Task 1, `TestInitValidators`).
- AC7.4's hypothesis chain test is explicitly called out by Phase 7 as critical-coverage: it
  pins the `key_prefix="gidu"` matching (a defect in a prior plan version) — it must verify both
  the blocked case and the success-after-`gidu1-cat-low.global_synchronic` case. The
  `event1`-vs-`event12` non-collision test pins the `evt_id + "-"` boundary match.
- Phase 7 Task 3 also adds a completeness-invariant sweep to `cmd_verify`. A `TestVerify`-style
  integration test (`TestCompletenessGates::test_verify_flags_completeness_invariant_violation`)
  should assert that a manifest with a cross-participant `done` substep over incomplete upstream
  coverage is flagged by `mpi_step verify`. Automated, integration.

**Human verification (AC7.6):** removing the advisory "Do NOT abort" prose from
`mpi-generic-diachronic` SKILL.md has no behavioral test path — it is a documentation change.

- Justification: the enforcement moved into `close` (covered by AC7.2/7.3/7.4); AC7.6 only
  asserts the now-redundant skill prose is gone. Skill text is not exercised by the Python
  pipeline tests.
- Manual approach: read `microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md` and
  confirm the "Completeness check" section and the `Do NOT abort — ask the user...` instruction
  are removed (or downgraded to a non-binding pre-flight note).
- Optional automation: a suite-level structural assertion in `tests/test_plugin_structure.py`
  that reads the SKILL.md and asserts the "Do NOT abort" string is absent. Per the file-path
  rule, any such doc-content check belongs in `tests/`, not in `test_mpi_step.py`.

---

## AC8: Optional researcher-declared DV focuses

Phases: 1 (`dv_focuses` schema + manifest write), 3 (`_all_candidate_draftings_done` declared-set
path), 8 (undeclared-focus guard, provenance, agent-template fix).

| Criterion | Test type | Test class / function | File |
|---|---|---|---|
| AC8.1 — `confirm_study_config` accepts optional `dv_focuses` list; written to `study.dv_focuses`; `null` when omitted | unit + integration | unit: `TestDVFocusGate::test_confirm_study_config_dv_focuses_valid`, `test_dv_focuses_null_valid`, `test_dv_focuses_non_string_entry_rejected`; integration: `TestConfirmStudyConfigClose::test_dv_focuses_null_when_omitted`, `test_dv_focuses_list_written_to_manifest` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC8.2 — with non-null `dv_focuses`, close for `hypothesis.evidence_extraction` scope `dv-<focus>` naming an undeclared focus fails `undeclared_dv_focus` | integration | `TestDVFocusGate::test_undeclared_focus_rejected`, `test_declared_focus_accepted` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC8.3 — with non-null `dv_focuses`, `weak_evidence_review` blocks until `candidate_drafting` is `done` for every declared focus (not just manifest-present entries) | integration | `TestDVFocusGate::test_weak_evidence_review_blocks_on_declared_but_absent_focus`, `test_weak_evidence_review_succeeds_when_all_declared_done` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC8.4 — with null `dv_focuses`, all-match falls back to manifest scan (AC2 semantics) | integration | `TestDVFocusGate::test_null_focuses_manifest_scan_succeeds`, `test_null_focuses_one_pending_fails` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC8.5 (manifest record) — `config_provenance` records `dv_focuses_provenance`: `"researcher_specified"` when list provided, `"emergent"` when null | integration | `TestDVFocusGate::test_provenance_researcher_specified_recorded`, `test_provenance_emergent_recorded` | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` |
| AC8.5 (disclaimer output) — `dv_focuses_provenance` field appears in the hypothesis disclaimer output | **human verification** | — | — |

Notes: AC8.1's schema half is unit (Phase 1 Task 1 validator + Phase 8 Task 3 cases); the
manifest-write half is integration (`TestConfirmStudyConfigClose`). AC8.3 must include the
declared-but-absent case (a declared focus with no `candidate_drafting` participant entry yet) —
this is the case AC2.3 deliberately excludes. AC8.4 pins the null-focuses fallback to the AC2
manifest scan.

**Human verification (AC8.5, disclaimer-output half):** the manifest-record half is fully
automated above. The clause "this field appears in the hypothesis disclaimer **output**" refers
to a `dv_focuses_provenance` field emitted in a skill-produced `candidate_drafting` artifact
(Phase 8 Task 2 adds the mandate to `mpi-hypothesis/SKILL.md`).

- Justification: the disclaimer text is produced by the LLM following the skill mandate; no
  Python code injects it. The schema validator could (separately) be extended to require the
  field's presence, but verifying the *value* is correct for a given run is an LLM-output
  property.
- Manual approach: on a real run, open a produced `hypotheses/dv-<focus>.candidate_drafting.json`
  artifact and confirm it carries `dv_focuses_provenance` with the value matching the run's
  `study.dv_focuses` state (`"researcher_specified"` when declared, `"emergent"` when null).
- Optional partial automation: if a schema validator field-presence check is added to
  `_validate_hypothesis_candidate_drafting`, a unit test could assert presence is required — but
  that verifies presence, not value correctness, and is not part of the current phase scope.

---

## Summary: criteria requiring human verification

| Criterion | Reason automation is insufficient | Manual approach |
|---|---|---|
| AC6.2 | Validator checks offset-file *format* only; byte-range alignment to the speaker label is a skill-produced property | On a real run, slice the raw file by `offsets["3"]` and confirm it equals utterance 3's full text incl. speaker label |
| AC6.3 | Round-trip of `utterance_refs` byte ranges to exact raw text is a property of skill-generated artifacts, not of the close-time format guard | Cross-check one diachronic/synchronic `utterance_refs` entry against the raw-file slice |
| AC7.6 | Documentation change (advisory prose removal); enforcement already covered by AC7.2–7.4 | Read `mpi-generic-diachronic/SKILL.md`; confirm "Do NOT abort" / "Completeness check" prose removed. Optional structural assertion in `tests/test_plugin_structure.py` |
| AC8.5 (disclaimer-output half) | `dv_focuses_provenance` appears in LLM-produced `candidate_drafting` artifact; value correctness is an output property | Open a produced `candidate_drafting.json` and confirm the field value matches the run's `study.dv_focuses` state |

All other sub-criteria (AC1.1–AC1.3, AC2.1–AC2.5, AC3.1–AC3.2, AC4.1–AC4.3, AC5.1–AC5.5,
AC6.1, AC6.4, AC7.1–AC7.5, AC8.1–AC8.4, and the manifest-record half of AC8.5) are fully
automated. AC3.3 is a meta-criterion verified by the full-suite regression run, not a discrete
test function.

## Full-suite verification command

```
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
```

Expected after all 8 phases: every pre-existing test passes (AC3.3), and the new classes
`TestInitValidators`, `TestConfirmStudyConfigClose`, `TestPrereqScopeResolution`,
`TestPrereqScopeResolutionClose`, `TestManifestWriteSafety`, `TestTranscriptPrepValidators`,
`TestOffsetFileFormat`, `TestCompletenessGates`, and `TestDVFocusGate` pass.

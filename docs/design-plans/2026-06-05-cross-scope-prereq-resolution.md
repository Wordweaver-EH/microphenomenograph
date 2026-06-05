# Pipeline Correctness: Prereq Scope, Manifest Safety, Offset Registration, Completeness Gates, and DV Focus Registration

## Summary

The pipeline's `mpi_step.py close` command is a transactional close protocol: every completed
analysis substep must be validated, appended to an audit log, recorded in the run manifest
(`.mpi/project.json`), and committed to git before it is considered done. Six issues prevent
a correct end-to-end run.

**Issue 1 — Cross-scope prerequisite resolution.** The prereq-checking logic handles one
scope transition (synchronic IDU scope → diachronic transcript scope) but not the two
additional scope changes in the cross-participant stages, nor the semantic shift from
any-match to all-match needed for the global-scope `weak_evidence_review` gate.

**Issue 2 — Parallel manifest write race.** In yolo mode the pipeline emits one skill
invocation per pending participant in a single assistant turn; Claude Code executes them
concurrently. Concurrent `mpi_step.py close` calls for different participants in the same
run share a read-modify-write cycle on `.mpi/project.json`, creating a race that silently
discards one close's manifest mutation.

**Issue 3 — `transcript_prep` on the legacy path.** The three `transcript_prep` substeps
(`hash_raw`, `normalize`, `register_offsets`) are not registered in `_mpi_schemas.py` and
cannot be closed via `cmd_close`.

**Issue 4 — Offset file format mismatch.** Offset files (which map utterance numbers to byte
ranges for span validation) are produced in an old array format the span validator rejects.
Byte ranges are also computed as sequential windows rather than per-utterance-line ranges.

**Issue 5 — Completeness gates absent from `close`.** The plugin CLAUDE.md says
`mpi_step.py close` enforces event-level completeness gates (e.g. all transcripts for an
event must have diachronic + synchronic done before `generic_diachronic` can close).
Verified: these gates are entirely absent from `cmd_close`. No code scans other participants'
substep status. The only gating is in the `/mpi all` orchestrator (stage ordering) and in the
`mpi-generic-diachronic` skill (advisory, bypassable). Direct `mpi_step.py close` invocations
bypass both. A deterministic Python gate at close time is more robust and consistent with how
`SUBSTEP_PREREQUISITES` and `_check_irr_gate` already work.

**Issue 6 — DV focuses are always LLM-derived.** The hypothesis stage runs `evidence_extraction`
and `candidate_drafting` per DV focus, but focuses are named by the LLM from global synchronic
output — the researcher has no mechanism to declare them upfront. This is post-hoc DV
identification. Even for exploratory work, researcher-specified DVs are better practice and
enable exact completeness gating on the declared set.

## Definition of Done

- `_prereq_participant_key()` resolves prereq keys correctly for all cross-participant DAG
  scope transitions; `weak_evidence_review` blocks until all `candidate_drafting` entries in
  the manifest are done.
- Parallel `cmd_close` calls for different participants in the same run both commit their
  changes; neither is silently lost.
- `transcript_prep` substeps close via `cmd_close` like all other stages.
- Offset files use the flat-dict format the span validator expects, with byte ranges aligned
  to utterance line boundaries.
- `cmd_close` enforces event-level completeness gates for cross-participant stages by reading
  `study.event_groups` from the manifest; the manifest's `event_groups` is populated at
  `confirm_study_config` and is study-design-agnostic.
- `confirm_study_config` optionally accepts a researcher-declared list of DV focuses; when
  present, the hypothesis stage is constrained to those focuses and `weak_evidence_review`
  gates against the declared set rather than the manifest scan.

## Acceptance Criteria

### pipeline-correctness.AC1: Deterministic scope transform resolves worksheet_assembly prereq

- **AC1.1 Success:** `cmd_close` for `generic_synchronic.worksheet_assembly`
  (scope `event3-cat-low-gidu1`) succeeds when `select_generic_idus_of_interest` is done
  under participant key `event3`.
- **AC1.2 Failure:** Same close fails `prereq_unsatisfied` when no
  `select_generic_idus_of_interest` entry exists.
- **AC1.3 Edge:** `_scope_strip_to_event("event12-cat-moderate-gidu3")` returns `"event12"`.

### pipeline-correctness.AC2: All-match semantics gate weak_evidence_review correctly

- **AC2.1 Success:** Close for `hypothesis.weak_evidence_review` (scope `global`) succeeds
  when every `hypothesis.candidate_drafting` entry in the manifest has status `done`.
- **AC2.2 Failure:** Same close fails `prereq_unsatisfied` when no `candidate_drafting`
  entry exists at all.
- **AC2.3 Failure:** Close fails when all `candidate_drafting` entries are `done` except
  one which has status `pending`.
- **AC2.4 Failure:** Close fails when a `candidate_drafting` entry has status `flagged`.
- **AC2.5 Success:** With `study.dv_focuses` absent or null, all-match uses the manifest
  scan (AC2.1–AC2.4 semantics). With `study.dv_focuses` populated, see AC8.

### pipeline-correctness.AC3: Backward compatibility

- **AC3.1 Success:** Synchronic → diachronic scope stripping (`p1s1-idu2` → `p1s1`) still
  works.
- **AC3.2 Success:** Same-scope prereqs use the unchanged participant key.
- **AC3.3 Success:** All existing tests pass without modification.

### pipeline-correctness.AC4: Manifest write safety under parallel closes

- **AC4.1 Success:** Two parallel `cmd_close` calls on different participants in the same
  run both commit their changes; both manifest entries show `done` when both finish.
- **AC4.2 Success:** A close that acquires the run lock always reads the manifest after all
  prior lock-holders have written and committed; no mutation is silently overwritten.
- **AC4.3 Success:** A `cmd_close` process that holds a run lock and is then interrupted
  (SIGTERM / KeyboardInterrupt) leaves the lock file behind in an unlocked state; a
  subsequent `acquire_close_lock(run_dir)` call succeeds without blocking. The test asserts
  re-lockability, not file absence.

### pipeline-correctness.AC5: `transcript_prep` closes via `cmd_close`

- **AC5.1 Success:** `cmd_close --stage transcript_prep --substep hash_raw` with a valid
  units-json succeeds and commits.
- **AC5.2 Success:** `cmd_close --stage transcript_prep --substep normalize` succeeds with
  a valid normalized artifact path.
- **AC5.3 Success:** `cmd_close --stage transcript_prep --substep register_offsets` succeeds
  with a valid offsets JSON.
- **AC5.4 Failure:** Missing required fields in the units-json (e.g. no `transcript_id`)
  are rejected with `schema_validation_failed`.
- **AC5.5 Success:** Prerequisite ordering is enforced: `normalize` rejects until `hash_raw`
  is done; `register_offsets` rejects until `normalize` is done.

### pipeline-correctness.AC6: Offset files use flat-dict format aligned to utterance boundaries

- **AC6.1 Success:** `transcripts/offsets/<id>.json` is a flat dict keyed by string
  utterance number: `{"1": {"byte_start": N, "byte_end": N}, ...}`.
- **AC6.2 Success:** Each entry's `byte_start` is the byte offset of the first character of
  the speaker label on that utterance line; `byte_end` is the last character before the line
  ending. Each utterance occupies exactly one physical line — the `normalize` step enforces
  this invariant; `register_offsets` may assume it.
- **AC6.3 Success:** `utterance_refs` in diachronic/synchronic artifacts that cite utterance
  3 use `byte_start`/`byte_end` values that correspond exactly to the full text of utterance
  3 in the raw file.
- **AC6.4 Failure:** An offset file in the old array format (`{"transcript_id": ...,
  "utterances": [...]}`) causes `cmd_close` to reject with a descriptive error.

### pipeline-correctness.AC7: Event-group completeness gates enforced by `close`

- **AC7.1 Success:** `study.event_groups` is written to the manifest at
  `init.confirm_study_config` close; it maps event IDs to lists of transcript IDs
  (e.g. `{"event1": ["p1s1", "p2s1", "p3s1"]}`). The mapping is study-design-agnostic —
  any string event ID, any list of transcript IDs.
- **AC7.2 Failure:** `cmd_close` for `generic_diachronic.participant_row_assembly`
  (scope `event3-cat-low`) fails `completeness_gate_unsatisfied` when any transcript in
  `event_groups["event3"]` has `diachronic.idu_naming_ordering` or any synchronic substep
  not `done`.
- **AC7.3 Success:** Same close succeeds once all transcripts in `event_groups["event3"]`
  have all required upstream substeps `done`.
- **AC7.4 Success:** All four cross-participant gate chains are enforced in turn:
  `generic_synchronic.*` gates on `generic_diachronic.*` done for the event;
  `global_synchronic.*` gates on `generic_synchronic.*` done;
  `hypothesis.*` gates on all cross-participant stages done.
- **AC7.5 Degraded:** A manifest that pre-dates this change (no `event_groups` key) emits
  a `completeness_gate_skipped: event_groups_missing` warning and proceeds rather than
  hard-blocking, to preserve backward compatibility with existing run directories.
- **AC7.6 Cleanup:** The advisory completeness warning in `mpi-generic-diachronic` SKILL.md
  is removed or downgraded to a pre-flight UX hint; `close` is now the enforcement point.

### pipeline-correctness.AC8: Optional researcher-declared DV focuses

- **AC8.1 Success:** `init.confirm_study_config` accepts an optional `dv_focuses` list
  (e.g. `["automaticity", "attention", "bodily_sensation"]`); when provided it is written to
  `study.dv_focuses` in the manifest. When omitted, `study.dv_focuses` is `null`.
- **AC8.2 Success:** When `study.dv_focuses` is non-null, a `cmd_close` for
  `hypothesis.evidence_extraction` whose scope `dv-<focus>` names a focus not in the
  declared list fails with `undeclared_dv_focus`.
- **AC8.3 Success:** When `study.dv_focuses` is non-null, `weak_evidence_review` blocks
  until `candidate_drafting` is `done` for every declared focus — not just every
  manifest-present entry.
- **AC8.4 Success:** When `study.dv_focuses` is null, all-match falls back to the manifest
  scan (AC2 semantics): all manifest-present `candidate_drafting` entries must be `done`.
- **AC8.5 Success:** `study.config_provenance` at `confirm_study_config` records
  `dv_focuses_provenance`: `"researcher_specified"` when the list was provided, `"emergent"`
  when null. This field appears in the hypothesis disclaimer output.

## Glossary

- **close protocol**: The transactional sequence `mpi_step.py close` executes for every
  completed substep: validate artifact → append audit event → update manifest → git commit.
  All four steps share a `close_id` (UUID4).
- **manifest** (`.mpi/project.json`): Runtime state file for a run. Records each substep's
  `status`, `close_id`, `output_path`, and artifact SHA-256 hashes.
- **yolo mode**: The fully-automated execution mode where `/mpi all` emits one skill
  invocation per pending participant in a single assistant turn; Claude Code executes them
  concurrently within a stage. Stage transitions are sequential (all diachronic completes
  before synchronic starts). This within-stage concurrency makes the manifest write race
  reachable.
- **substep / stage**: A pipeline stage (e.g. `diachronic`) contains a fixed ordered list
  of substeps (e.g. `criteria_grouping → criteria_revision → idu_naming_ordering`).
  `cmd_close` operates at the substep level.
- **participant key / scope**: The string key used to index the manifest's `participants`
  dict. Format depends on stage: transcript scope (`p1s1`), IDU scope (`p1s1-idu2`),
  event-category-gIDU scope (`event3-cat-low-gidu1`), DV-focus scope (`dv-<focus>`), or
  `global`.
- **scope transform**: A function that derives the prerequisite's participant key from the
  downstream substep's participant key when the two operate at different scopes.
- **`PREREQ_SCOPE_TRANSFORMS`**: Data-driven table in `_mpi_schemas.py` mapping a four-tuple
  `(downstream_stage, downstream_substep, prereq_stage, prereq_substep)` to either a named
  deterministic transform function or `None` (all-match).
- **any-match**: A prereq resolution rule where the prereq is satisfied if *any* manifest
  entry for that stage/substep has status `done`. Correct only for the
  `worksheet_assembly → select_generic_idus_of_interest` edge where a specific event-scope
  key is deterministically derivable.
- **all-match**: A prereq resolution rule where the prereq is satisfied only when *all*
  relevant manifest entries have status `done`. Required for `weak_evidence_review` (all
  `candidate_drafting` entries must be done) and for completeness gates (all transcripts in
  an event must have upstream substeps done).
- **`_any_substep_done`**: Renamed in this design to `_all_substeps_done` for the
  `weak_evidence_review` edge; see Architecture section.
- **cross-participant DAG**: The portion of the pipeline that aggregates across transcripts:
  `generic_diachronic`, `generic_synchronic`, `global_synchronic`, `hypothesis`.
- **event**: The grouping dimension used for cross-participant analysis. Abstract —
  independent of participant key naming. In the OSF suggestion study, event = suggestion
  number; in an interoception study, event = condition; in an alcohol study, event = dosage.
  What "event" means is study-design knowledge, not derivable from key naming conventions.
- **`study.event_groups`**: Manifest field populated at `confirm_study_config`. Maps event
  IDs to the list of transcript IDs that belong to that event. Ground truth for completeness
  gates. Human-confirmed once, enforced deterministically forever after.
- **`study.dv_focuses`**: Optional manifest field. When populated by the researcher at
  `confirm_study_config`, lists the dependent variables the hypothesis stage will investigate.
  Constrains `evidence_extraction` scope names and enables exact all-match gating. When null,
  DV focuses emerge from the LLM's reading of the global synchronic output.
- **`COMPLETENESS_GATES`**: Data-driven table in `_mpi_schemas.py` mapping cross-participant
  stages to the upstream substeps that must be done for all transcripts in an event before
  a close can proceed. Models on `SUBSTEP_PREREQUISITES`. Read alongside `study.event_groups`.
- **completeness gate**: A close-level check for cross-participant stages: extract the event
  ID from the scope key (via `_scope_strip_to_event`), look up `event_groups[event_id]`,
  verify all required upstream substeps are `done` for every listed transcript. Implemented
  in `_check_completeness_gate()`, modelled on `_check_irr_gate`.
- **IDU** (Incipient Diachronic Unit): A discrete temporal segment identified during
  diachronic analysis of a single transcript.
- **ISU** (Incipient Synchronic Unit): A cross-sectional structural feature identified
  within one IDU during synchronic analysis.
- **gIDU** (generic IDU): A cross-participant grouping of similar IDUs produced by
  `generic_diachronic.idu_similarity_grouping`.
- **`transcript_prep`**: The three-substep orchestrator stage (`hash_raw → normalize →
  register_offsets`) that prepares a raw transcript before LLM analysis.
- **offset file** (`transcripts/offsets/<id>.json`): Flat dict mapping string utterance
  numbers to `{byte_start, byte_end}` pairs in the raw transcript. Used by the span
  validator. Single-line-per-utterance invariant enforced by `normalize`.
- **utterance_refs**: Required grounding field on every analytic unit. Each ref includes
  `transcript_id`, `utterance_number`, `byte_start`, `byte_end`, `raw_excerpt`.
- **span validator**: Checks `utterance_refs` byte ranges against the offset file.
- **read-modify-write race**: Concurrency hazard where two processes each read, mutate, and
  write the same file; the second write discards the first's changes.
- **advisory file lock**: Cooperative lock (`fcntl.flock` on POSIX, `msvcrt`/`CreateFile`
  on Windows) that serialises concurrent writers. On process exit the OS releases the lock;
  the lock *file* persists and is re-lockable. The correct test for interrupt safety is
  re-lockability, not file absence.
- **`close_id`**: UUID4 generated at the start of each `cmd_close` call. Ties together the
  manifest entry, audit event, and git commit.
- **`config_provenance`**: Immutable manifest field set at `confirm_study_config`. Records
  how the study config was determined (`preregistered`, `user_specified`,
  `llm_proposed_user_confirmed`) and, when applicable, `dv_focuses_provenance`
  (`researcher_specified` or `emergent`).

---

## Architecture

### Issue 1: Cross-scope prerequisite resolution

`_prereq_participant_key()` handles one scope transform (synchronic `pNsN-iduN` →
diachronic `pNsN`). Two further cross-scope edges exist in the cross-participant DAG:

| Prereq | Prereq scope | Downstream | Downstream scope |
|---|---|---|---|
| `generic_synchronic.select_generic_idus_of_interest` | `event<E>` | `generic_synchronic.worksheet_assembly` | `event<E>-cat-<C>-gidu<G>` |
| `hypothesis.candidate_drafting` | `dv-<focus>` | `hypothesis.weak_evidence_review` | `global` |

**Fix for the first edge (deterministic transform):** `PREREQ_SCOPE_TRANSFORMS` dict in
`_mpi_schemas.py` maps the four-tuple
`(downstream_stage, downstream_substep, prereq_stage, prereq_substep)` to a named transform
function. For `worksheet_assembly → select_generic_idus_of_interest`:
`_scope_strip_to_event("event<E>-cat-<C>-gidu<G>") → "event<E>"` (split on `"-cat-"`;
safe as long as event IDs match `event\d+`, which is enforced by the header parser).

**Fix for the second edge (all-match, not any-match):** `hypothesis.weak_evidence_review`
is a global review of *all* candidate hypotheses. The prereq is satisfied only when every
`hypothesis.candidate_drafting` entry in the manifest has status `done`. Any-match
(previous design) would allow closure while some DV focuses are still pending.

`PREREQ_SCOPE_TRANSFORMS` maps this edge to a sentinel value (e.g. `"all_match"`) instead
of a transform function. The `cmd_close` prereq loop, on encountering `"all_match"`, calls
`_all_candidate_draftings_done(manifest)` rather than `_get_substep_status`.

When `study.dv_focuses` is non-null (Issue 6), `_all_candidate_draftings_done` additionally
verifies that every declared focus has an entry, not just the manifest-present ones.

### Issue 2: Parallel manifest write race

**Motivation (corrected):** `mpi.md` lines 85–88 and 115–119 specify that yolo mode emits
multiple skill invocations in a single assistant turn, one per pending participant, and
states "Do NOT wait for one to complete before starting the next." The glossary and CLAUDE.md
previously said "strictly sequential" — those descriptions are wrong and will be corrected.
The race is live.

**Fix:** Advisory per-run-directory lock on `.mpi/close.lock` held for the entire
read → mutate → atomic_write → git-commit cycle. On POSIX: `fcntl.flock`. On Windows:
`msvcrt.locking` or `CreateFile` exclusive. Released in a `finally` block; on abnormal exit
the OS releases the lock automatically. The file persists and is re-lockable — the next
`acquire_close_lock` call always succeeds. The test for interrupt safety asserts
re-lockability, not file absence.

The exclusive lock is the sole correctness mechanism for Issue 2. There is no separate
"detect stale read and retry" path — the lock makes stale reads unreachable. AC4.2 tests
positive correctness (both closes commit) not a retry scenario.

### Issue 3: `transcript_prep` on the legacy path

`validate_units()` does not handle `transcript_prep` substeps. Any close returns
`schema_validation_failed: unknown stage`.

**Fix:** Three validator functions in `_mpi_schemas.py` using `_require_keys`:

| Substep | Required payload fields |
|---|---|
| `hash_raw` | `transcript_id`, `sha256`, `byte_size` |
| `normalize` | `transcript_id`, `normalized_path`, `diff_path` |
| `register_offsets` | `transcript_id`, `offsets_path`, `utterance_count` |

None are LLM substeps (no `--prompt-artifact` required). Prereq chain:
`hash_raw → normalize → register_offsets` added to `SUBSTEP_PREREQUISITES`.

### Issue 4: Offset file format and utterance-boundary alignment

**Precondition enforced by `normalize`:** Each utterance occupies exactly one physical line,
identified by its speaker-label prefix. The `normalize` step enforces this invariant;
`register_offsets` may assume it.

**Fix:** `mpi-transcript-prep` SKILL.md and the `register_offsets` validator specify the
flat-dict format: `{"1": {"byte_start": N, "byte_end": N}}` keyed by string utterance number,
where `byte_start` = first byte of the speaker label, `byte_end` = last byte before the
newline. A format guard in `_validate_transcript_prep_register_offsets` rejects any payload
whose `offsets_path` file contains the old array structure (`{"utterances": [...]}`).

### Issue 5: Event-group completeness gates

**Study-structure block in the manifest** (foundational change used by Issues 5 and 6):

`confirm_study_config` writes a `study` block that includes `event_groups` (and, if
Issue 6 is in scope, `dv_focuses`). Example:

```json
"study": {
  "event_groups": {
    "event1": ["p1s1", "p2s1", "p3s1", "p4s1"],
    "event2": ["p1s2", "p2s2", "p3s2", "p4s2"],
    "event3": ["p1s3", "p2s3", "p3s3", "p4s3"]
  },
  "dv_focuses": null,
  "config_provenance": "user_specified",
  "calibration_transcript_ids": ["p2s2", "p5s1"],
  "calibration_mode": "stratified"
}
```

`event_groups` is study-design-agnostic: any string event ID, any list of transcript IDs.
The mpi-init skill auto-suggests groupings from parsed headers (for the OSF data, suggestion
number = event), but the human confirms the final structure at `confirm_study_config`.

**`COMPLETENESS_GATES` table** in `_mpi_schemas.py`:

```python
COMPLETENESS_GATES = {
    "generic_diachronic": {
        "scope_to_event": _scope_strip_to_event,   # reuses Issue 1 function
        "required_upstream": [
            ("diachronic", "idu_naming_ordering"),
            ("synchronic", "isu_second_level_grouping"),   # all IDU scopes for transcript
        ],
    },
    "generic_synchronic": {
        "scope_to_event": _scope_strip_to_event,
        "required_upstream": [("generic_diachronic", "cross_iv_contrast")],
    },
    "global_synchronic": {
        "scope_to_event": lambda _: None,  # global; check all events
        "required_upstream": [("generic_synchronic", "isu_second_level_grouping")],
    },
    "hypothesis": {
        "scope_to_event": lambda _: None,
        "required_upstream": [("global_synchronic", "global_synchronic")],
    },
}
```

**`_check_completeness_gate()`** in `mpi_step.py`, modelled on `_check_irr_gate`:

1. Look up the stage in `COMPLETENESS_GATES`. If absent, return 0 (no gate for this stage).
2. Derive the event ID from the scope (or `None` = all events).
3. Read `manifest["study"]["event_groups"]`. If absent: emit
   `completeness_gate_skipped: event_groups_missing` warning and return 0 (backward compat
   for legacy run directories).
4. For each transcript ID in the relevant event group(s): check all required upstream
   substeps have status `done` in the manifest. Handles synchronic's IDU-scoped keys by
   scanning all `<transcript_id>-idu*` participant keys.
5. If any check fails: `return _abort("completeness_gate_unsatisfied: ...")`.

Called in `cmd_close` after `_check_irr_gate`, before substep reservation.

**Skill advisory check removed:** The bypassable completeness warning in
`mpi-generic-diachronic` SKILL.md is removed; `close` now owns enforcement. An event-filtered
UX hint ("Note: running generic_diachronic for event3") may remain in the skill.

**`verify` integration:** `mpi_step.py verify`'s three-way join should flag any manifest
state where a cross-participant substep is `done` but `event_groups` shows incomplete
upstream coverage — the completeness invariant should hold at verify time too.

### Issue 6: Optional researcher-declared DV focuses

`confirm_study_config` is extended to accept an optional `dv_focuses` list. When the
researcher knows upfront which DVs they are investigating (e.g. `["automaticity",
"attention"]`), they provide this list. It is stored in `study.dv_focuses` and is immutable
after `confirm_study_config` closes.

**When `dv_focuses` is non-null:**
- `cmd_close` for `hypothesis.evidence_extraction` validates that the scope `dv-<focus>`
  names a focus in the declared list; undeclared focuses are rejected with
  `undeclared_dv_focus`.
- `_all_candidate_draftings_done` checks against the declared set rather than manifest
  entries — if a declared focus has no `candidate_drafting` entry yet, it is treated as
  pending.
- `config_provenance` records `dv_focuses_provenance: "researcher_specified"`. This is
  surfaced in the hypothesis disclaimer output.

**When `dv_focuses` is null:**
- The LLM names focuses freely from the global synchronic output (current behaviour).
- All-match falls back to manifest scan: all manifest-present `candidate_drafting` entries
  must be `done`.
- `config_provenance` records `dv_focuses_provenance: "emergent"`.

## Existing Patterns

`_prereq_participant_key()` already performs scope stripping for the synchronic → diachronic
case. `PREREQ_SCOPE_TRANSFORMS` extends this with a data-driven approach, consistent with
how `SUBSTEP_PREREQUISITES` and `LLM_SUBSTEPS` are declared in `_mpi_schemas.py`.

`_check_irr_gate()` already follows the pattern: cross-participant stage → scan
manifest/jsonl → block if any record fails. `_check_completeness_gate()` is the same shape:
cross-participant stage → scan event_groups + participants → block if any upstream is
pending.

`_mpi_atomic.py`'s `atomic_write()` uses `os.replace` for atomic file rename. The close lock
wraps this at a coarser granularity (full read-modify-write-commit cycle).

`_mpi_schemas.py` validators for existing stages use the same `_require_keys(payload, [...],
"payload")` pattern. `transcript_prep` validators follow identically.

## Implementation Phases

**Phase dependency DAG:**

```
Phase 1 (study structure) ─────────────────────┬──► Phase 7 (completeness gates)
                                                └──► Phase 8 (DV focuses)

Phase 2 (PREREQ_SCOPE_TRANSFORMS) ─────────────► Phase 3 (wire into cmd_close)

Phase 4 (close lock)          [independent]
Phase 5 (transcript_prep)  ─────────────────────► Phase 6 (offset format)
```

Phases 1, 2, 4, 5 are fully independent and may be implemented in parallel.

<!-- START_PHASE_1 -->
### Phase 1: Study-structure block in manifest and `cmd_init`

**Goal:** Persist `event_groups` (and the `dv_focuses` placeholder) in the manifest at
`confirm_study_config` close. Foundational for Phases 7 and 8.

**Components:**
- Manifest schema: add `study.event_groups` and `study.dv_focuses` fields; document in
  `microphenomenograph/1.0.0/CLAUDE.md` data-format section
- `cmd_init` in `mpi_step.py`: update `confirm_study_config` close path to write
  `event_groups` from the confirmed study config payload; `dv_focuses` defaults to `null`
- `_validate_init_confirm_study_config` validator in `_mpi_schemas.py`: require
  `event_groups` field (dict of string → list); add `dv_focuses` as optional list-or-null
- Update `mpi-init` SKILL.md: at `confirm_study_config` step, present the auto-detected
  event grouping for human confirmation before writing; document that "event" is abstract
  (not tied to suggestion number)
- Glossary: define `event` abstractly in CLAUDE.md; update yolo definition to "parallel
  within-stage, sequential across stages"

**Dependencies:** None

**Done when:** `study.event_groups` appears in the manifest after `confirm_study_config`
closes; the field is populated with the correct transcript-ID lists; unit tests cover
correct write and schema validation.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: `PREREQ_SCOPE_TRANSFORMS` in `_mpi_schemas.py`

**Goal:** Define the scope-transform table for the two broken cross-participant edges.

**Components:**
- `_scope_strip_to_event(scope: str) -> str` — named transform in `_mpi_schemas.py`
- `PREREQ_SCOPE_TRANSFORMS: dict[tuple, ...]` — exported constant with entries for
  `worksheet_assembly → select_generic_idus_of_interest` (deterministic transform) and
  `weak_evidence_review → candidate_drafting` (`"all_match"` sentinel); add to `__all__`

**Dependencies:** None

**Done when:** Import succeeds; table has 2 entries; `_scope_strip_to_event` returns correct
values for `event<N>-cat-<C>-gidu<G>` inputs; unit tests cover AC1.1–AC1.3 and AC3.1–AC3.2.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Wire transforms and all-match into `cmd_close` prereq loop

**Goal:** Activate the transforms and fix `weak_evidence_review` gating.

**Components:**
- `_prereq_participant_key()` in `mpi_step.py` — consult `PREREQ_SCOPE_TRANSFORMS`; return
  `Optional[str]` (transform result) or `"all_match"` sentinel
- `_all_candidate_draftings_done(manifest, prereq_stage, prereq_substep, dv_focuses) -> bool`
  — scans all manifest participants for matching done entries; also checks against declared
  `dv_focuses` when non-null
- `cmd_close()` prereq loop — handle transform result; on `"all_match"` sentinel call
  `_all_candidate_draftings_done` instead of `_get_substep_status`

**Dependencies:** Phase 2

**Done when:** AC1, AC2, AC3 pass; no regression on existing prereq tests.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Per-run-directory close lock

**Goal:** Prevent parallel manifest write races.

**Components:**
- `acquire_close_lock(run_dir: Path) -> ContextManager` in `_mpi_atomic.py` —
  cross-platform advisory lock on `<run_dir>/.mpi/close.lock` using `fcntl.flock` (POSIX)
  or `msvcrt` (Windows), wrapped in a context manager with `finally` release
- `cmd_close()` in `mpi_step.py` — wrap the read → mutate → atomic_write → git-commit
  block with `with acquire_close_lock(run_dir):`

**Dependencies:** None (independent of Phases 1–3)

**Done when:** AC4.1, AC4.2, AC4.3 pass; two subprocess closes launched simultaneously
for different participants both show `done` in the manifest; a SIGTERM during a close leaves
the lock file re-lockable by the next caller.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: `transcript_prep` validators in `_mpi_schemas.py`

**Goal:** Bring `transcript_prep` onto the standard validator path.

**Components:**
- `_validate_transcript_prep_hash_raw`, `_validate_transcript_prep_normalize`,
  `_validate_transcript_prep_register_offsets` — three validators using `_require_keys`
- Entries in `SUBSTEP_PREREQUISITES` for the `hash_raw → normalize → register_offsets` chain
- Dispatch entries in `validate_units()` and `LLM_SUBSTEPS` (all three are non-LLM)

**Dependencies:** None (independent)

**Done when:** AC5.1–AC5.5 pass; `validate_units('transcript_prep', 'hash_raw', {'transcript_id':
'p1s3', 'sha256': 'abc', 'byte_size': 100})` returns `[]`; missing-field cases return schema
errors.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Offset format enforcement and SKILL.md correction

**Goal:** Enforce flat-dict offset format with single-line-per-utterance byte ranges.

**Components:**
- `_validate_offset_file_format(path: Path) -> Optional[str]` in `_mpi_atomic.py` or
  inline in `_validate_transcript_prep_register_offsets` — returns error string if the file
  is not a flat dict keyed by string utterance numbers
- `mpi-transcript-prep/SKILL.md` — update Closure section and Steps section to specify
  flat-dict format, correct byte-range computation, and the single-line-per-utterance
  precondition that `normalize` must enforce
- `microphenomenograph/1.0.0/CLAUDE.md` — add note under `transcript_prep` about offset
  format contract and single-line invariant

**Dependencies:** Phase 5 (substep must be registered before format check fires at close)

**Done when:** AC6.1–AC6.4 pass; array-format offset file is rejected with a descriptive
error; correctly-formatted file with proper byte ranges succeeds.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Completeness gates in `cmd_close`

**Goal:** Enforce event-level completeness for cross-participant stages at close time.

**Components:**
- `COMPLETENESS_GATES` dict in `_mpi_schemas.py` — data-driven table mapping cross-participant
  stages to required upstream substeps and scope-to-event function
- `_check_completeness_gate(run_dir, manifest, stage, scope, args, audit_path) -> int` in
  `mpi_step.py` — modelled on `_check_irr_gate`; reads `event_groups`, iterates transcripts,
  checks all required substeps; emits `completeness_gate_skipped` warning for legacy manifests
- `cmd_close()` — call `_check_completeness_gate` after `_check_irr_gate` for
  cross-participant stages
- `mpi-generic-diachronic/SKILL.md` — remove bypassable advisory completeness warning;
  replace with lightweight pre-flight UX note
- `mpi_step.py verify` — add completeness-invariant check to three-way join

**Dependencies:** Phase 1 (requires `event_groups` in manifest)

**Done when:** AC7.1–AC7.6 pass; existing tests pass; legacy manifest (no `event_groups`)
emits warning and proceeds.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Optional researcher-declared DV focuses

**Goal:** Allow researchers to pre-specify DV focuses at `confirm_study_config`.

**Components:**
- `confirm_study_config` validator in `_mpi_schemas.py` — `dv_focuses` is optional
  list-or-null (already present as null from Phase 1)
- `mpi-init/SKILL.md` — add `confirm_study_config` prompt: "Optionally list the dependent
  variables this study investigates (leave blank to let the analysis identify them):"
- `_all_candidate_draftings_done()` (from Phase 3) — extend to check declared focus list
  when `study.dv_focuses` is non-null
- `cmd_close()` — for `hypothesis.evidence_extraction`, validate scope against declared
  list when non-null; emit `undeclared_dv_focus` on mismatch
- Hypothesis disclaimer template — include `dv_focuses_provenance` field

**Dependencies:** Phase 1 (requires `study.dv_focuses` in manifest schema); Phase 3
(extends `_all_candidate_draftings_done`)

**Done when:** AC8.1–AC8.5 pass; with declared focuses, undeclared scope rejected; with
null focuses, manifest-scan all-match applies unchanged.
<!-- END_PHASE_8 -->

## Additional Considerations

**Yolo parallelism documentation:** CLAUDE.md and the former glossary entry incorrectly
described yolo as "strictly sequential substep-level closes." The correct description (per
`mpi.md` lines 85–88, 115–119) is: within-stage parallel (all pending participants for a
stage are invoked concurrently), cross-stage sequential (the next stage starts only after
all closes for the current stage complete). Update CLAUDE.md and the glossary accordingly.

**`_scope_strip_to_event` safety:** Splits on `"-cat-"`. Safe for all current event IDs
(`event\d+`) since digits cannot form `"-cat-"`. The constraint is: event IDs must match
`event\d+`. This is enforced by the transcript header parser, so no additional guard is
needed. If a future study uses free-form event names, replace the split with an anchored
regex `^(event[^-]+)`.

**Manifest race scope:** The race only manifests for concurrent closes within the same stage
(e.g., multiple participants' diachronic in yolo mode). Same-participant serial closes
(assisted mode) are unaffected. The lock is cheap (200ms hold per close) and always held —
no conditional needed.

**Lock file lifecycle:** `.mpi/close.lock` is created on first `acquire_close_lock` call and
persists. It is intentionally left in place after process exit (re-lockable). It must not
be added to `.gitignore` in the `.mpi/` block, since `.mpi/` is already ignored. No
maintenance required.

**`event_groups` and cascade-reset:** Knowing which transcripts belong to an event would
allow cascade-reset to be event-precise (reset only affected-event cross-participant stages
rather than all). This is a deliberate non-goal for this design — cascade-reset is working
code and the improvement is separable.

**Testing bar for Phase 1:** `event_groups` is a hard dependency for Phase 7. A wrong
mapping hard-blocks the pipeline (no close for that stage can succeed). The unit tests for
Phase 1 must cover: correct grouping written, legacy-manifest degradation, and the case where
`event_groups` lists a transcript ID that does not exist in `participants` (no substep records
yet — should not cause a crash in Phase 7's scan, only an "upstream not done" result).

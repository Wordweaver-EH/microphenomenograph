# Pipeline Correctness: Prereq Scope, Manifest Safety, and Offset Registration

## Summary

The pipeline's `mpi_step.py close` command is a transactional close protocol: every completed analysis substep must be validated, appended to an audit log, recorded in the run manifest (`.mpi/project.json`), and committed to git before it is considered done. For this to work correctly across the full pipeline, the close command must be able to check that each substep's prerequisites are satisfied — but the prerequisite-checking logic only understood one scope transition (synchronic IDU scope → diachronic transcript scope), not the two additional scope changes that occur in the cross-participant stages. Separately, running parallel closes for different participants in the same run creates a read-modify-write race on the manifest file, and three early-pipeline substeps (`hash_raw`, `normalize`, `register_offsets` under `transcript_prep`) were never registered with validators and could not be closed at all.

This document covers four targeted fixes that unblock a clean end-to-end run without bridging workarounds. The prerequisite-scope gaps are closed by adding a data-driven transform table (`PREREQ_SCOPE_TRANSFORMS`) that maps each cross-scope edge to either a deterministic key-derivation function or an any-match rule. The manifest race is eliminated by wrapping the read-modify-write-commit cycle in a per-run-directory advisory file lock. The `transcript_prep` substeps are brought onto the same `_mpi_schemas.py` validator path as every other stage, and an additional format guard enforces that offset files (which map utterance numbers to byte ranges in the raw transcript) use the flat-dict format the span validator expects rather than the legacy array format.

## Definition of Done

- `_prereq_participant_key()` resolves prereq keys correctly for all cross-participant DAG scope transitions — no bridging re-closes needed in a standard run.
- Parallel `cmd_close` calls for different participants in the same run cannot overwrite each other's manifest updates.
- `transcript_prep` substeps (`hash_raw`, `normalize`, `register_offsets`) are registered in `_mpi_schemas.py` and can be closed via `cmd_close` like all other stages.
- Offset files (`transcripts/offsets/<id>.json`) are produced in the flat-dict format the span validator expects, with byte ranges that align to complete utterance lines.

## Acceptance Criteria

### pipeline-correctness.AC1: Deterministic scope transform resolves worksheet_assembly prereq
- **pipeline-correctness.AC1.1 Success:** `cmd_close` for `generic_synchronic.worksheet_assembly` (scope `event3-cat-low-gidu1`) succeeds when `select_generic_idus_of_interest` is done under participant key `event3`.
- **pipeline-correctness.AC1.2 Failure:** Same close fails `prereq_unsatisfied` when no `select_generic_idus_of_interest` entry exists.
- **pipeline-correctness.AC1.3 Edge:** `_scope_strip_to_event("event12-cat-moderate-gidu3")` returns `"event12"`.

### pipeline-correctness.AC2: Any-match semantics resolve weak_evidence_review prereq
- **pipeline-correctness.AC2.1 Success:** Close for `hypothesis.weak_evidence_review` (scope `global`) succeeds when any `hypothesis.candidate_drafting` entry in the manifest is `done`.
- **pipeline-correctness.AC2.2 Failure:** Same close fails when no `candidate_drafting` is `done` anywhere.
- **pipeline-correctness.AC2.3 Edge:** Fails even when `candidate_drafting` exists but has status `flagged`.

### pipeline-correctness.AC3: Backward compatibility
- **pipeline-correctness.AC3.1 Success:** Synchronic → diachronic scope stripping (`p1s1-idu2` → `p1s1`) still works.
- **pipeline-correctness.AC3.2 Success:** Same-scope prereqs use the unchanged participant key.
- **pipeline-correctness.AC3.3 Success:** All existing tests pass without modification.

### pipeline-correctness.AC4: Manifest write safety under parallel closes
- **pipeline-correctness.AC4.1 Success:** Two parallel `cmd_close` calls on different participants in the same run both commit their changes; neither is silently lost.
- **pipeline-correctness.AC4.2 Success:** If a second close reads an outdated manifest (written before the first close's commit), it retries the manifest read and re-applies its mutation rather than overwriting the first close's result.
- **pipeline-correctness.AC4.3 Success:** A `cmd_close` that holds a run lock and is then interrupted (SIGTERM / KeyboardInterrupt) does not leave the lock file behind; subsequent closes can proceed.

### pipeline-correctness.AC5: `transcript_prep` closes via `cmd_close`
- **pipeline-correctness.AC5.1 Success:** `cmd_close --stage transcript_prep --substep hash_raw` with a valid units-json succeeds and commits.
- **pipeline-correctness.AC5.2 Success:** `cmd_close --stage transcript_prep --substep normalize` succeeds with a valid normalized artifact path.
- **pipeline-correctness.AC5.3 Success:** `cmd_close --stage transcript_prep --substep register_offsets` succeeds with a valid offsets JSON.
- **pipeline-correctness.AC5.4 Failure:** Missing required fields in the units-json (e.g. no `transcript_id`) are rejected with `schema_validation_failed`.
- **pipeline-correctness.AC5.5 Success:** Prerequisite ordering is enforced: `normalize` rejects until `hash_raw` is done; `register_offsets` rejects until `normalize` is done.

### pipeline-correctness.AC6: Offset files use flat-dict format aligned to utterance boundaries
- **pipeline-correctness.AC6.1 Success:** `transcripts/offsets/<id>.json` produced by `mpi-transcript-prep` is a flat dict keyed by string utterance number: `{"1": {"byte_start": N, "byte_end": N}, ...}`.
- **pipeline-correctness.AC6.2 Success:** Each entry's `byte_start` is the byte offset of the first character of the speaker label on that utterance line; `byte_end` is the last character before the line ending.
- **pipeline-correctness.AC6.3 Success:** `utterance_refs` in diachronic/synchronic artifacts that cite utterance 3 for a transcript use `byte_start`/`byte_end` values that correspond exactly to the full text of utterance 3 in the raw file.
- **pipeline-correctness.AC6.4 Failure:** An offset file in the old array format (`{"transcript_id": ..., "utterances": [...]}`) causes `cmd_close` to reject the close with a descriptive error.

## Glossary

- **close protocol**: The transactional sequence `mpi_step.py close` executes for every completed substep: validate artifact → append audit event → update manifest → git commit. All four steps share a `close_id` (UUID4); the substep is only considered `done` once all four succeed.
- **manifest** (`.mpi/project.json`): The runtime state file for a run. Records each substep's `status` (`pending | done | flagged | error`), `close_id`, `output_path`, and artifact SHA-256 hashes under a hierarchy of participant scope → stage → substep.
- **substep / stage**: A pipeline stage (e.g. `diachronic`, `generic_synchronic`) contains a fixed ordered list of substeps (e.g. `criteria_grouping → criteria_revision → idu_naming_ordering`). `cmd_close` operates at the substep level.
- **participant key / scope**: The string key used to index into the manifest's `participants` dict. The format depends on the pipeline stage: transcript scope (`p1s1`), IDU scope (`p1s1-idu2`), event–category–gIDU scope (`event3-cat-low-gidu1`), DV-focus scope (`dv-<focus>`), or `global`.
- **scope transform**: A function that derives the prerequisite's participant key from the downstream substep's participant key when the two substeps operate at different scopes (e.g. `event3-cat-low-gidu1` → `event3`).
- **`PREREQ_SCOPE_TRANSFORMS`**: The proposed data-driven table in `_mpi_schemas.py` mapping a four-tuple `(downstream_stage, downstream_substep, prereq_stage, prereq_substep)` to either a named transform function (deterministic) or `None` (any-match).
- **any-match semantics**: A prerequisite resolution rule where the prereq is satisfied if *any* manifest entry for that stage/substep, across all participant keys, has status `done`. Used when the downstream substep operates at `global` scope with no deterministic mapping back to a specific upstream key.
- **cross-participant DAG**: The portion of the analysis pipeline that aggregates across multiple transcripts: `generic_diachronic`, `generic_synchronic`, `global_synchronic`, and `hypothesis` stages, each of which depends on substeps in a different scope than its own.
- **IDU** (Incipient Diachronic Unit): A discrete temporal segment of experience identified during diachronic analysis of a single transcript, with a defined beginning, end, and optional hinge to the next segment. Each IDU gets its own synchronic scope key (`p1s1-idu2`).
- **ISU** (Incipient Synchronic Unit): A cross-sectional structural feature or quality of experience identified within one IDU during synchronic analysis.
- **gIDU** (generic IDU): A cross-participant grouping of similar IDUs produced by `generic_diachronic.idu_similarity_grouping`; `generic_synchronic` then selects and works with these groupings per (event × IV category × gIDU).
- **`transcript_prep`**: The three-substep pipeline stage (`hash_raw → normalize → register_offsets`) that prepares a raw transcript file before LLM analysis begins. Orchestrator-only (no LLM calls).
- **offset file** (`transcripts/offsets/<id>.json`): A file mapping string utterance numbers to `{byte_start, byte_end}` pairs in the raw transcript file. Used by the span validator to verify that `utterance_refs` in analytic artifacts point to real text in the immutable source.
- **utterance_refs**: The required grounding field on every analytic unit (IDU, ISU, pattern, hypothesis claim). Each ref includes `transcript_id`, `utterance_number`, `byte_start`, `byte_end`, and `raw_excerpt`; the span validator checks the byte range against the offset file.
- **span validator**: The component that checks `utterance_refs` byte ranges against the offset file to confirm analytic units are grounded in the actual transcript text.
- **read-modify-write race**: A concurrency hazard where two processes each read the same file, apply independent mutations, and write back — the second write silently discards the first process's changes.
- **advisory file lock**: A cooperative locking mechanism (`fcntl.flock` on POSIX, `msvcrt`/`CreateFile` on Windows) that serialises concurrent access to a resource — effective only when all participants honour the lock. Adequate here because all writers are co-operative pipeline processes on the same machine.
- **`fcntl.flock`**: POSIX system call for advisory file locking; the lock is automatically released by the OS if the holding process exits abnormally, so no manual cleanup is needed on crash.
- **`msvcrt.locking` / `CreateFile`**: Windows equivalents used for the same advisory-lock purpose on the Windows code path.
- **atomic write / `os.replace`**: Writing to a temporary file and then renaming it over the target in a single OS call, so readers never see a partially-written file. Already used by `_mpi_atomic.py`'s `atomic_write()`; the close lock wraps this at a coarser granularity.
- **`_require_keys`**: Internal helper in `_mpi_schemas.py` that checks a dict for the presence of required fields and returns a list of `SchemaError`s. All stage validators are built on this pattern.
- **yolo mode**: The fully-automated execution mode where the pipeline runs all substeps sequentially without human confirmation, with one git commit per substep close. Parallel participant closes can occur in this mode, making the manifest race reachable.
- **`close_id`**: A UUID4 generated at the start of each `cmd_close` call. Ties together the manifest entry, audit log event, and git commit for a single substep close, enabling replay and verification.

---

## Architecture

### Issue 1: Cross-scope prerequisite resolution

`_prereq_participant_key()` in `mpi_step.py` handles one scope transform (synchronic `pNsN-iduN` → diachronic `pNsN`). Two more scope changes exist in the cross-participant DAG:

| Prereq | Prereq scope | Downstream | Downstream scope |
|---|---|---|---|
| `generic_synchronic.select_generic_idus_of_interest` | `event<E>` | `generic_synchronic.worksheet_assembly` | `event<E>-cat-<C>-gidu<G>` |
| `hypothesis.candidate_drafting` | `dv-<focus>` | `hypothesis.weak_evidence_review` | `global` |

**Fix:** `PREREQ_SCOPE_TRANSFORMS` dict in `_mpi_schemas.py` maps the four-tuple `(downstream_stage, downstream_substep, prereq_stage, prereq_substep)` to either a named transform function (deterministic derivation) or `None` (any-match: pass if any manifest entry for the prereq is `done`).

`cmd_close()` prereq loop is extended: when `_prereq_participant_key()` returns `None`, scan all manifest participants for any matching done substep via `_any_substep_done()`.

### Issue 2: Parallel manifest write race

`cmd_close` has a read-modify-write cycle on `.mpi/project.json`:
1. Read manifest
2. Apply mutation (mark substep done)
3. Atomic-write manifest
4. Git commit

Two concurrent closes on the same run directory (parallel participants in yolo mode) can both read the same manifest version, each apply their own mutation, and the second write silently discards the first close's mutation — leaving a substep marked `pending` even though it committed to git.

**Fix:** An advisory per-run-directory lock using a `.mpi/close.lock` file held for the duration of steps 1–4. On POSIX: `fcntl.flock`. On Windows: `msvcrt.locking` or `CreateFile` with exclusive share mode. The lock is acquired before step 1 and released after step 4 (in a `finally` block). On abnormal exit the OS releases the file lock automatically; the lock file itself is left in place but harmless (re-lockable). Maximum lock hold time: the duration of one git commit (~200ms typical); no risk of starvation in practice with the pipeline's linear-per-participant model.

### Issue 3: `transcript_prep` on the legacy path

`_mpi_schemas.py`'s `validate_units()` does not handle `transcript_prep` substeps. Any close for `transcript_prep.*` returns `schema_validation_failed: unknown stage`. The three substeps (`hash_raw`, `normalize`, `register_offsets`) need validators and prerequisite entries.

**Minimal payload schemas:**

| Substep | Required payload fields |
|---|---|
| `hash_raw` | `transcript_id`, `sha256`, `byte_size` |
| `normalize` | `transcript_id`, `normalized_path`, `diff_path` |
| `register_offsets` | `transcript_id`, `offsets_path`, `utterance_count` |

None are LLM substeps (no `--prompt-artifact` required). Prerequisite chain: `hash_raw` → `normalize` → `register_offsets`.

### Issue 4: Offset file format and utterance-boundary alignment

The offset format the span validator expects is a flat dict: `{"1": {"byte_start": N, "byte_end": N}}` (keyed by string utterance number). The transcript-prep implementation in the test run wrote the old array format `{"transcript_id": ..., "utterances": [...]}`, which the validator rejects. Additionally, the byte ranges straddled utterance boundaries (computed as sequential byte windows rather than per-line ranges).

**Fix:** The `mpi-transcript-prep` skill's SKILL.md (and any orchestrator script) must specify the flat-dict format with byte ranges computed as: `byte_start = byte index of the first character of the speaker label on that line; byte_end = byte index of the last character before the newline`. An additional format guard in `validate_units('transcript_prep', 'register_offsets', ...)` rejects payloads whose `offsets_path` file is in the old array format.

## Existing Patterns

`_prereq_participant_key()` already performs scope stripping for the synchronic → diachronic case. `PREREQ_SCOPE_TRANSFORMS` extends this with a data-driven approach, consistent with how `SUBSTEP_PREREQUISITES` and `LLM_SUBSTEPS` are declared in `_mpi_schemas.py`.

The advisory lock pattern (`fcntl.flock`) is used by `atomic_write()` in `_mpi_atomic.py` (which uses `os.replace` for atomic rename). The close-lock is coarser — it wraps the full read-modify-write-commit cycle rather than a single file write.

`_mpi_schemas.py` validators for `diachronic`, `synchronic`, and `irr_calibration` substeps follow the same `_require_keys(payload, [...], "payload")` pattern. `transcript_prep` validators follow the identical pattern.

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: `PREREQ_SCOPE_TRANSFORMS` in `_mpi_schemas.py`

**Goal:** Define the scope-transform table for the two broken cross-participant edges.

**Components:**
- `_scope_strip_to_event(scope: str) -> str` — named transform in `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`
- `PREREQ_SCOPE_TRANSFORMS: dict[tuple, ...]` — exported constant with 2 entries; add to `__all__` alongside `SUBSTEP_PREREQUISITES`

**Dependencies:** None

**Done when:** Import succeeds; table has 2 entries; `_scope_strip_to_event` returns correct values; unit test in `test_mpi_step.py` covers `TestPrereqScopeResolution` (6 tests — see AC1–AC3).
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Update `_prereq_participant_key()` and `cmd_close()` prereq loop

**Goal:** Wire the transforms into the close command.

**Components:**
- `_prereq_participant_key()` in `microphenomenograph/1.0.0/scripts/mpi_step.py` — add 3 new optional parameters; consult `PREREQ_SCOPE_TRANSFORMS`; return `Optional[str]`
- `_any_substep_done(manifest, stage, substep) -> bool` — helper function
- `cmd_close()` prereq loop (~line 1253) — updated call site; handle `None` return with `_any_substep_done`

**Dependencies:** Phase 1

**Done when:** AC1, AC2, AC3 pass; no regression on existing prereq tests.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Per-run-directory close lock

**Goal:** Prevent parallel manifest write races.

**Components:**
- `acquire_close_lock(run_dir: Path) -> ContextManager` in `microphenomenograph/1.0.0/scripts/_mpi_atomic.py` — cross-platform advisory lock on `<run_dir>/.mpi/close.lock` using `fcntl.flock` (POSIX) or `msvcrt` (Windows), wrapped in a context manager
- `cmd_close()` in `mpi_step.py` — wrap the read → mutate → atomic_write → git-commit block with `with acquire_close_lock(run_dir):`

**Dependencies:** None (independent of Phases 1–2)

**Done when:** AC4.1, AC4.2, AC4.3 pass; two subprocess closes launched simultaneously for different participants both commit successfully and both manifest entries show `done` after both finish.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: `transcript_prep` validators in `_mpi_schemas.py`

**Goal:** Bring `transcript_prep` off the legacy path so `cmd_close` can handle it.

**Components:**
- `_validate_transcript_prep_hash_raw`, `_validate_transcript_prep_normalize`, `_validate_transcript_prep_register_offsets` — three validator functions in `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` using `_require_keys`
- Entries in `SUBSTEP_PREREQUISITES` for the `hash_raw → normalize → register_offsets` chain
- Dispatch entries in `validate_units()`

**Dependencies:** None (independent)

**Done when:** AC5.1–AC5.5 pass; `validate_units('transcript_prep', 'hash_raw', {'transcript_id': 'p1s3', 'sha256': 'abc', 'byte_size': 100})` returns `[]`; missing-field cases return schema errors.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Offset format enforcement and SKILL.md correction

**Goal:** Enforce flat-dict offset format and fix utterance-boundary alignment.

**Components:**
- `_validate_offset_file_format(path: Path) -> Optional[str]` in `microphenomenograph/1.0.0/scripts/_mpi_atomic.py` (or inline in `_validate_transcript_prep_register_offsets`) — returns error string if file is not flat-dict keyed by string utterance numbers
- `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md` — update the Closure section and "Steps" section to specify flat-dict format and correct byte-range computation (start of speaker label to end of text before newline)
- `microphenomenograph/1.0.0/CLAUDE.md` — add note under "transcript_prep" about offset format contract

**Dependencies:** Phase 4 (registers the substep so the format check fires during close)

**Done when:** AC6.1–AC6.4 pass; a close with an array-format offset file is rejected with a descriptive error message; a close with a correctly-formatted offset file succeeds.
<!-- END_PHASE_5 -->

## Additional Considerations

**Phase ordering:** Phases 1+2 (prereq scope) and Phase 3 (lock) are independent and can be implemented in parallel. Phase 4 must precede Phase 5 (offset format enforcement requires the substep to be registered).

**transcript_prep lock-file location:** `.mpi/close.lock` is a dot-file inside `.mpi/`, consistent with the `audit.jsonl`, `run_id`, and `project.json` pattern.

**Scope of the manifest race:** The race only manifests when parallel agents close substeps for *different* participants in the same run. Same-participant serial closes (the normal assisted-mode path) are unaffected. The lock is cheap enough to always hold — no performance concern at the 200ms commit granularity.

**`_scope_strip_to_event` fragility:** The function splits on `"-cat-"`. If a future event name contains the substring `cat` (e.g., `event-category3`), this would produce a wrong result. The transform table can be extended with a more robust regex at that point; for the current scope format (`event<N>-cat-<level>-gidu<N>`) the simple split is correct.

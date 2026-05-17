# Documentation-as-Done Contract Design

## Summary

This design introduces a "Documentation-as-Done Contract" — a disciplined rule that no pipeline step may declare itself complete unless it has produced four artifacts together: an output file on disk, a structured audit event appended to `.mpi/audit.jsonl`, an updated manifest entry in `.mpi/project.json`, and a git commit binding all three. The contract is enforced by a single stdlib-only Python helper (`scripts/mpi_step.py`) with two verbs: `close`, which performs the four-artifact transaction with rollback semantics if any step fails, and `render`, which regenerates the human-readable `.mpi/reasoning.log` from the authoritative JSONL audit trail on demand.

The driving motivation is a class of failures observed in the current pipeline where subagents returned analysis content through conversation context rather than writing it to disk themselves, creating fragile implicit assumptions about who persists what. The fix gives both subagents (`mpi-analyst` and `mpi-cross-analyst`) `Write` and `Bash` tool grants so they can self-persist artifacts and call the helper directly, collapsing their return value from a large JSON blob to a short status string (`OK` or `ERROR`). Every generative substep also gains an explicit anti-fabrication rule: if upstream artifacts are missing or malformed the substep must return an error rather than synthesizing plausible-looking replacement content. Schema validation inside the helper catches field-name drift (the `idu_name` vs. `title` class of bug) at write time rather than silently propagating it.

Two granularity decisions distinguish this design from the previous stage-level model. First, the unit of "step" is the methodology's natural **substep**, not a stage — diachronic decomposes into segment / DU / refined-DU / phases; synchronic into thematic-groups / ISUs / structure per phase; generic-diachronic into compare / GDUs / structure; generic-synchronic into SSS-grouping / GSS-definition per GDU. This matches the granularity used by the µ-PATH pipeline (Wordweaver-EH/upath) and enables substep-grained resume after partial failures. Second, every LLM-invoking substep writes a **prompt-capture artifact** (`<scope>-<stage>.<substep>.prompt.json`) containing the exact prompt, response, model id, finish reason, and token counts. Audit events reference this file by path so any analytic decision can be replayed offline. Fabrication becomes detectable by replay rather than merely rule-violating.

## Definition of Done

1. Every step in the MPI pipeline (subagent or orchestrator) writes its own artifact, updates the manifest, and git-commits before claiming done; a step that does not complete all four is `pending`, never silently `done`.
2. `mpi-analyst` and `mpi-cross-analyst` agents gain `Write` and self-persist their artifacts plus their log entries.
3. Per-analytic-unit decisions (each IDU/ISU coding call, manifest mutation, commit, flag) are logged to a structured `.mpi/audit.jsonl`; `.mpi/reasoning.log` is rendered on demand from the JSONL by `mpi_step.py render`.
4. An end-to-end pipeline test runs `/mpi all` on a tiny fixture corpus and asserts every expected on-disk artifact lands.
5. Downstream skills fail-fast when upstream artifacts are missing/malformed — never synthesize replacements.
6. **Step granularity matches the methodology's natural substeps.** Diachronic decomposes into segment → DU → refined-DU → phase identification (4 substeps); synchronic into thematic groups → ISUs → structure (3 substeps, per phase); generic-diachronic into RDU compare → GDU clustering → generic structure (3 substeps); generic-synchronic into SSS-grouping → GSS-definition (2 substeps, per GDU). Each substep closes its own four-part transaction.
7. **Every LLM call is captured as a replayable artifact.** Each substep that invokes an LLM writes `analyses/pNsN-<substep>.prompt.json` containing the exact prompt, response, model id, finish reason, and token counts. Audit events reference this file by path so the analytic decision can be replayed offline.

## Acceptance Criteria

### doc-as-done.AC1: Every step closes with all four artifacts or stays `pending`
- **doc-as-done.AC1.1 Success:** After a successful `mpi_step.py close`, the artifact file(s), `.mpi/audit.jsonl` append, `.mpi/project.json` update, and a git commit referencing all three all exist.
- **doc-as-done.AC1.2 Failure:** If git commit fails, the manifest is left untouched (still `pending`) and an audit event with `event.outcome: failure` plus a `close_aborted` event are appended.
- **doc-as-done.AC1.3 Failure:** If audit append fails (e.g., disk full simulated), the manifest is left untouched and the helper exits non-zero.
- **doc-as-done.AC1.4 Success (subagent):** `mpi-analyst` writes `analyses/pNsN-<stage>.json` and `.md` itself before invoking the helper.
- **doc-as-done.AC1.5 Failure (subagent):** A subagent that fails to write artifacts returns `ERROR <participant> <stage>: <reason>` and never returns analysis content as a substitute.

### doc-as-done.AC2: Helper CLI exposes the contract as one verb
- **doc-as-done.AC2.1 Success:** `python scripts/mpi_step.py close --actor ... --participant ... --stage ... --artifact ... --reason ... --units-json ...` succeeds end-to-end in a clean git repo with valid inputs.
- **doc-as-done.AC2.2 Success:** `python scripts/mpi_step.py --help` and `mpi_step.py close --help` print usage with all required and optional flags.
- **doc-as-done.AC2.3 Failure:** Missing `--artifact` path, missing `.mpi/project.json`, or empty artifact file causes the helper to exit non-zero with a named error and zero state mutation.

### doc-as-done.AC3: Manifest mutation is atomic
- **doc-as-done.AC3.1 Success:** Manifest writes use `.tmp` → `os.replace` so concurrent readers see either the old or the new manifest, never a partial one.
- **doc-as-done.AC3.2 Failure:** A simulated `os.replace` failure leaves the manifest at its previous state and the `.tmp` file unlinked.
- **doc-as-done.AC3.3 Success:** Re-running `mpi_step.py render` is idempotent — running it twice produces byte-identical `reasoning.log`.

### doc-as-done.AC4: Schema validation rejects malformed units at write time
- **doc-as-done.AC4.1 Success:** A well-formed units payload (all required fields, no unknown keys, correct types) is accepted.
- **doc-as-done.AC4.2 Failure:** A units payload using `title` instead of `idu_name`, or `utterance_lines` instead of `utterance_numbers`, is rejected with a named error pointing at the offending field.
- **doc-as-done.AC4.3 Failure:** `confidence` outside 1–5, non-boolean `flag_for_review`, or missing `hinge_to_next` on a non-last IDU is rejected.

### doc-as-done.AC5: Audit trail is the single source of truth for logs
- **doc-as-done.AC5.1 Success:** `mpi_step.py render` reads `.mpi/audit.jsonl` and produces `.mpi/reasoning.log` containing one line per event in the canonical format.
- **doc-as-done.AC5.2 Failure-tolerance:** A malformed JSONL line in the middle of the file emits a `MALFORMED:<lineno>` placeholder in the rendered output but does not abort rendering.
- **doc-as-done.AC5.3 Success:** Every generative SKILL.md and both agent prompts contain the verbatim anti-fabrication rule.
- **doc-as-done.AC5.4 Failure (anti-fabrication):** When given empty or missing upstream input, a generative skill returns an `ERROR` rather than producing synthetic content. (Verified at the agent prompt level; behavioural verification deferred to LLM-in-the-loop testing outside the E2E test.)

### doc-as-done.AC6: Subagents own their persistence
- **doc-as-done.AC6.1 Success:** `agents/mpi-analyst.md` and `agents/mpi-cross-analyst.md` `tools:` line declares `Read, Write, Bash`.
- **doc-as-done.AC6.2 Success:** Both agent prompts contain a "Persistence (mandatory before returning)" subsection naming the exact files to Write and the `mpi_step.py close` invocation to make.
- **doc-as-done.AC6.3 Success:** Every SKILL.md contains a "Closure (mandatory)" subsection naming the responsible actor and the artifacts that close the step.
- **doc-as-done.AC6.4 Success:** Read-only skills (`mpi-kappa`, `mpi-status`) explicitly state "no artifact close" and emit a `stage_phase: read` audit event for trace continuity.

### doc-as-done.AC7: Old hand-written contracts removed
- **doc-as-done.AC7.1 Success:** No SKILL.md hand-specifies manifest mutation prose, log line format, or git commit message format — all three are owned by the helper.
- **doc-as-done.AC7.2 Success:** Audit events follow the documented schema: `event_id` (UUID4), `@timestamp` (RFC3339 UTC), `trace_id`, `span_id`, `actor.{kind,name,model}`, `event.{kind,category,action,outcome}`, `mpi.{participant,stage,unit,manifest_status,artifact_paths,git_commit_sha}`, `reason`.
- **doc-as-done.AC7.3 Success:** Within a single pipeline run, `trace_id` is constant across all audit events; `event_id`s are globally unique.

### doc-as-done.AC8: End-to-end pipeline test verifies on-disk outcomes
- **doc-as-done.AC8.1 Success:** `tests/test_e2e_pipeline.py` runs `/mpi all` against a tiny fixture corpus (2 participants × 2 suggestions) and asserts every expected `analyses/pNsN-<stage>.{md,json}` exists and is non-empty.
- **doc-as-done.AC8.2 Success:** The same test asserts the manifest reflects every closure with matching `status` and `output_path`, that `audit.jsonl` validates and contains the expected stage_completed + per-unit events, and that `git log --oneline` shows one commit per stage with the canonical message format.
- **doc-as-done.AC8.3 Failure-path:** `tests/test_e2e_fail_fast.py` feeds a malformed unit (e.g., `confidence: 9`, unknown stage) and asserts the helper exits non-zero, the manifest is unchanged, no git commit is created, and no half-written artifact exists.

### doc-as-done.AC9: Plugin documentation reflects the new contract
- **doc-as-done.AC9.1 Success:** `microphenomenograph/1.0.0/CLAUDE.md` contains a "Documentation-as-Done Contract" section pointing to `scripts/mpi_step.py`, documents the substep DAG, and removes the old per-stage output-path table and reasoning.log format note.
- **doc-as-done.AC9.2 Success:** Top-level `C:\microphenomenograph\CLAUDE.md` references the contract in its "Plugin contracts" section in one sentence.

### doc-as-done.AC10: Substep granularity replaces stage granularity
- **doc-as-done.AC10.1 Success:** The manifest's per-participant `stages.<stage>` entry contains a `substeps: {<substep>: {status, output_paths[]}}` map; stage `status` is derived from substep statuses (all done → done; any flagged → flagged; any error → error).
- **doc-as-done.AC10.2 Success:** `mpi_step.py close --substep <S2>` enforces the substep DAG — closing `diachronic.refined_du` is rejected if `diachronic.du` is not `done`.
- **doc-as-done.AC10.3 Success:** Each (stage, substep) pair has its own schema in `_mpi_schemas.py`; helper invokes the schema matching the `--substep` flag.
- **doc-as-done.AC10.4 Success:** `agents/mpi-analyst.md` Persistence subsection enumerates all 7 mpi-analyst substeps (4 diachronic + 3 synchronic) with per-substep artifact paths.
- **doc-as-done.AC10.5 Success:** `agents/mpi-cross-analyst.md` Persistence subsection enumerates all 7 cross-analyst substeps (3 generic_diachronic + 2 generic_synchronic per GDU + global_synchronic + hypothesis).
- **doc-as-done.AC10.6 Success:** Every SKILL.md Closure subsection enumerates its substeps and the responsible actor for each.

### doc-as-done.AC11: Every LLM call is captured as a replayable artifact
- **doc-as-done.AC11.1 Success:** For every LLM-invoking substep close, a `<scope>-<stage>.<substep>.prompt.json` artifact exists on disk containing the exact prompt, response, model id, finish reason, and token counts.
- **doc-as-done.AC11.2 Failure:** A `close` invocation for an LLM-invoking substep without `--prompt-artifact` is rejected with a named error.
- **doc-as-done.AC11.3 Failure:** A malformed `prompt.json` (missing required keys, wrong schema_version) is rejected at pre-check time; manifest unchanged.
- **doc-as-done.AC11.4 Success:** Each audit event for an LLM-invoking substep carries `mpi.prompt_artifact_path` pointing at the on-disk prompt.json.

## Glossary

- **MPI (Microphenomenological Interview)**: A structured qualitative research method, formalised by Sheldrake & Dienes (2025), for eliciting fine-grained first-person experiential accounts. The pipeline in this repo automates its multi-stage coding analysis.
- **IDU (Incipient Diachronic Unit)**: The unit of analysis produced by the diachronic (temporal) coding stage — a discrete segment of experience with a defined beginning, end, and optional hinge to the next segment.
- **ISU (Incipient Synchronic Unit)**: The unit of analysis produced by the synchronic (structural) coding stage — a cross-sectional feature or quality present within an IDU.
- **Manifest / `.mpi/project.json`**: The single authoritative state file for a pipeline run. Tracks the `status` (`pending` / `done` / `flagged` / `error`) and `output_path` for every participant × stage combination.
- **`.mpi/audit.jsonl`**: An append-only structured log file where every analytic decision, manifest mutation, and commit is recorded as one JSON object per line. It is the source of truth from which the human-readable reasoning log is derived.
- **`.mpi/reasoning.log`**: A human-readable text file regenerated on demand from `audit.jsonl` by `mpi_step.py render`. Because it is derived rather than written directly, it cannot drift from the audit trail.
- **`mpi_step.py close`**: The transactional verb of the helper CLI. Validates pre-conditions, appends an audit event, atomically updates the manifest, and creates a git commit — or rolls back and exits non-zero if any step fails.
- **`mpi_step.py render`**: The read-only verb that regenerates `reasoning.log` from `audit.jsonl`, with optional filtering by participant, stage, or time range.
- **Atomic manifest write (`.tmp` → `os.replace`)**: A technique where the new manifest is written to a temporary file and then renamed over the old one in a single OS call, so concurrent readers never see a partial write.
- **ECS (Elastic Common Schema)**: A field-naming convention from the Elastic stack used here to structure audit event fields — `event.kind`, `event.action`, `event.outcome`, `actor.*` — for interoperability with log tooling.
- **OpenTelemetry conventions**: Distributed tracing conventions (`trace_id`, `span_id`) used to correlate all audit events within a single pipeline run under one trace identifier.
- **Anti-fabrication rule**: A verbatim instruction added to every generative skill and both agent prompts requiring the LLM to return `ERROR` rather than synthesizing placeholder content when upstream inputs are absent or malformed.
- **Subagent**: A Claude agent instance (`mpi-analyst` or `mpi-cross-analyst`) dispatched by the orchestrator to perform per-participant or cross-participant analysis. Previously read-only; this design gives them `Write` and `Bash` so they own their own persistence.
- **Yolo mode**: The pipeline's fully-automated execution mode (invoked via `/mpi all`) in which git commits are created without user confirmation after each stage.
- **`trace_id` / `span_id`**: Identifiers propagated across all audit events in a single pipeline run. `trace_id` is constant for the run; each event gets a unique `event_id` (UUID4).
- **Substep**: The methodology's natural unit of analytic work, finer than a stage. E.g., `diachronic` decomposes into `segment`, `du`, `refined_du`, `phases`. Substep IDs follow the form `<stage>.<substep>`. Each substep closes its own four-part transaction and is independently resumable.
- **Substep DAG**: The directed graph of substep prerequisites (e.g., `diachronic.refined_du` requires `diachronic.du: done`). Encoded in `_mpi_schemas.py` and enforced by `mpi_step.py close` pre-checks.
- **Prompt-capture artifact (`.prompt.json`)**: Per-substep file containing the exact LLM prompt, response, model id, finish reason, and token counts. Enables offline replay of any analytic decision; fabrication becomes detectable by comparison rather than only by rule.
- **µ-PATH (Wordweaver-EH/upath)**: A same-domain microphenomenological analysis pipeline whose substep granularity (P1.1 / P1.2 / P1.3 / P1.4 etc.) and per-step JSON-output convention informed this design's substep model.

## Architecture

Every MPI pipeline step — whether executed by a subagent or by the orchestrator — closes by producing four artifacts atomically: an output file on disk, one or more audit events appended to `.mpi/audit.jsonl`, an atomic manifest mutation, and a single git commit binding the three together. A step that does not close all four is `pending` in the manifest. No partial credit; no implicit `done`.

**Substep granularity.** The unit of "step" is the methodology's natural substep, not a stage. This matches the granularity used by the µ-PATH pipeline (Wordweaver-EH/upath) which splits diachronic into segment / DU / refined DU / phases, synchronic into thematic-groups / ISUs / structure per phase, and so on. Concretely:

| Stage | Substeps | Iteration |
|---|---|---|
| `transcript_prep` | one | per participant |
| `diachronic` | `segment`, `du`, `refined_du`, `phases` | per participant |
| `synchronic` | `groups`, `isus`, `structure` | per participant × per phase |
| `generic_diachronic` | `compare`, `gdus`, `structure` | global |
| `generic_synchronic` | `sss_grouping`, `gss_definition` | global × per GDU |
| `global_synchronic` | one | global |
| `hypothesis` | one | global |

Substep IDs follow the form `<stage>.<substep>` (e.g., `diachronic.refined_du`). Each substep closes its own four-part transaction; failed substeps are resumable independently.

**Per-substep artifacts.** Each substep that produces analytic content writes three files into `analyses/`:
- `<scope>-<stage>.<substep>.json` — structured output (the raw analyst result)
- `<scope>-<stage>.<substep>.md` — human-readable spec-format markdown
- `<scope>-<stage>.<substep>.prompt.json` — exact LLM prompt + response + model id + finish reason + token counts (replay artifact)

Where `<scope>` is `pNsN` for per-participant work, `pNsN-phN` for per-phase synchronic substeps, `gduN` for per-GDU generic-synchronic substeps, and `global` for global substeps.

**Audit + reasoning sinks.** `.mpi/audit.jsonl` is the source of truth (ECS-flavoured JSON, one event per analytic decision; every event references the `.prompt.json` path that produced it). `.mpi/reasoning.log` is *derived* on demand by `mpi_step.py render`, eliminating the drift mode where one sink lags the other.

**Helper.** Closure logic lives in a single stdlib-only helper `scripts/mpi_step.py` with two verbs: `close` (transactional artifact + audit + manifest + commit) and `render` (regenerate `.mpi/reasoning.log` from JSONL). The `close` verb accepts `--substep`, `--scope`, `--prompt-artifact`, `--units-json`, plus the previously-specified flags.

**Subagent self-persistence.** Subagents (`mpi-analyst`, `mpi-cross-analyst`) gain `Write` and `Bash` so they can self-persist artifacts and invoke the helper directly, eliminating the lossy round-trip through conversation context that caused the originating failure. Each agent's return value collapses from "all analysis content" to one of two short status strings: `OK <scope> <substep> <N>units <K>flagged` or `ERROR <scope> <substep>: <reason>`.

**Anti-fabrication.** Every generative substep gains an explicit anti-fabrication rule: missing or malformed upstream artifacts → return `ERROR`, never synthesize. The helper enforces the same rule mechanically by validating `--units-json` against per-substep schemas and rejecting unknown keys (fixes today's `idu_name` vs `title` schema drift at write time). The `.prompt.json` artifact additionally lets reviewers re-run the same prompt against the same model and compare — fabrication becomes detectable, not just rule-violating.

## Existing Patterns

Investigation found 10 skills, 2 subagents, 1 command, and 3 scripts under `microphenomenograph/1.0.0/`. Current state:

- **Tool grants:** Both `agents/mpi-analyst.md` and `agents/mpi-cross-analyst.md` declare `tools: Read` only — they cannot persist artifacts. All writing happens in the orchestrator skill.
- **Writer ambiguity:** `mpi-diachronic` and `mpi-synchronic` SKILL.md files instruct "write `analyses/pNsN-<stage>.md`" without specifying who; with read-only subagents this implicitly falls to the orchestrator.
- **Log format inconsistency:** `mpi-diachronic` and `mpi-synchronic` specify slightly divergent one-line formats; other skills do not specify a format at all.
- **Fail-fast guards:** Present in `mpi-init` (header parse) and `mpi-transcript-prep` (ERROR/WARN taxonomy). Absent in `mpi-diachronic`, `mpi-synchronic`, all cross-participant skills, and `mpi-hypothesis`. No skill contains the strings "fabricate", "do not invent", or "fail-fast".
- **Manifest writes:** `mpi-init` is the only skill that currently writes the manifest atomically (`.tmp` → rename). Other skills mutate the manifest in prose but do not specify atomicity.
- **Git commits:** Specified for yolo mode in `mpi-diachronic`, `mpi-synchronic`, `mpi-generic-*`, `mpi-global-synchronic`, `mpi-hypothesis` — but with five slightly different message formats.
- **Tests:** Seven test files under `tests/` cover plugin structure, init schema, transcript prep, synchronic logic, cross-participant analysis, hypothesis generation, and orchestration. No end-to-end pipeline test exists.

This design unifies the above into one contract executed by one helper, called from every skill in the same way. The helper itself follows the existing atomic-write pattern from `mpi-init` (write tmp → `os.replace`). Audit event field naming follows ECS / OpenTelemetry conventions (`event.kind`, `event.action`, `event.outcome`; `trace_id` + `span_id`; namespaced `mpi.*` payload).

## Implementation Phases

This design has **12 phases** total. The writing-plans skill limits implementation plans to 8 phases — Phases 1–8 form the first implementation plan, Phases 9–12 the second. See Additional Considerations for sequencing.

<!-- START_PHASE_1 -->
### Phase 1: Helper CLI scaffolding

**Goal:** Stand up `scripts/mpi_step.py` with stdlib-only deps, argument parsing, run-id management, and atomic file primitives. No business logic yet.

**Components:**
- `microphenomenograph/1.0.0/scripts/mpi_step.py` — entry point, `argparse` for `close` and `render` subcommands, `--actor`, `--participant`, `--stage`, `--artifact`, `--reason`, `--units-json`, `--status` flags
- `microphenomenograph/1.0.0/scripts/_mpi_atomic.py` — internal module providing `atomic_write(path, content)`, `append_jsonl(path, obj)`, `load_or_create_run_id(.mpi/run_id)`
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — per-stage JSON schemas for `--units-json` validation, written in plain Python dicts (no jsonschema dep)
- `microphenomenograph/1.0.0/scripts/test_mpi_step.py` — unit tests covering atomic write, JSONL append idempotency, run-id load/create, schema rejection of unknown keys

**Dependencies:** None.

**Done when:** `python scripts/mpi_step.py --help` prints usage, all unit tests in `test_mpi_step.py` pass, schema validation rejects malformed payloads with named errors. Verifies `doc-as-done.AC2.1`, `doc-as-done.AC2.2`, `doc-as-done.AC4.1`.
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Helper `close` transaction (substep-aware)

**Goal:** Implement the transactional `close` verb at substep granularity: pre-checks → audit append → atomic manifest update → git commit, with rollback semantics on failure.

**Components:**
- `mpi_step.py close` function — accepts `--stage`, `--substep`, `--scope`, `--artifact` (json + md + prompt.json), `--units-json`, `--reason`, `--status`; performs pre-checks (manifest exists, all three artifact files exist + non-empty, upstream substep prerequisites done, units-json validates), then audit append, then manifest write, then `git add` + `git commit`
- Per-(stage, substep) prerequisite DAG hardcoded in `_mpi_schemas.py` — `diachronic.du` requires `diachronic.segment: done`; `synchronic.groups` per phase requires `diachronic.phases: done`; etc.
- Manifest schema extended: each participant entry's `stages.<stage>` now contains a `substeps: {<substep>: {status, output_paths[]}}` map; stage `status` is derived (all substeps done → stage done, any flagged → stage flagged)
- Commit message format: `mpi: <actor> <stage>.<substep> <scope> (<N>units <K>flagged)`
- Test cases in `test_mpi_step.py`: happy path per substep, missing artifact rejection, malformed units rejection, missing-upstream-substep rejection, partial-failure cleanup

**Dependencies:** Phase 1.

**Done when:** `mpi_step.py close` succeeds end-to-end in a tempdir git repo for every substep in the DAG; fails fast on every documented bad input with a named error; leaves the manifest untouched on any failure after pre-checks. Verifies `doc-as-done.AC1.1`, `doc-as-done.AC1.2`, `doc-as-done.AC1.3`, `doc-as-done.AC2.3`, `doc-as-done.AC3.1`, `doc-as-done.AC3.2`, `doc-as-done.AC4.2`, `doc-as-done.AC4.3`, `doc-as-done.AC10.1`, `doc-as-done.AC10.2`.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: Helper `render` verb + canonical log format

**Goal:** Regenerate `.mpi/reasoning.log` from `.mpi/audit.jsonl` with optional filtering. Canonical one-line human-readable format replaces all previous hand-written formats.

**Components:**
- `mpi_step.py render` function — reads JSONL, filters by `--from`, `--to`, `--participant`, `--stage`, writes one human-readable line per event to `--out` (default `.mpi/reasoning.log`)
- Canonical line format: `[<ts>] <actor> <participant> <stage>: <reason>. <N> units, <K> flagged. commit=<sha7>`
- Malformed-line handling: emit `MALFORMED:<lineno>: <raw>` placeholder, never abort
- Test cases: round-trip (events in → reasoning.log out matches expected), filter slicing, malformed-line resilience

**Dependencies:** Phase 2 (JSONL writer must exist to test render).

**Done when:** `mpi_step.py render` produces canonical reasoning.log from a known JSONL fixture; filter flags correctly slice output; a malformed JSONL line does not abort rendering. Verifies `doc-as-done.AC3.3`, `doc-as-done.AC5.1`, `doc-as-done.AC5.2`.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Per-substep schema definitions

**Goal:** Pin a JSON schema for every substep's `--units-json` payload so schema drift (today's `idu_name` vs `title` bug class) is rejected at write time.

**Components:**
- `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` — expanded module exporting one schema per `(stage, substep)`. Schemas use plain Python dicts (no jsonschema dep); fields enumerate required keys, allowed types, and value bounds.
- Coverage: `transcript_prep` (one); `diachronic.{segment,du,refined_du,phases}`; `synchronic.{groups,isus,structure}`; `generic_diachronic.{compare,gdus,structure}`; `generic_synchronic.{sss_grouping,gss_definition}`; `global_synchronic`; `hypothesis`.
- Validator function `validate_units(stage, substep, payload) -> list[Error]` returns named errors on missing required keys, unknown keys (strict mode), bad types, out-of-range values, or schema-version mismatch.
- Test cases: each schema accepts a canonical positive fixture and rejects a curated set of malformed fixtures (drift names, type errors, range errors).

**Dependencies:** Phase 1.

**Done when:** Every substep has a schema; validator function passes all positive fixtures and rejects every malformed fixture with a named error pointing at the offending field. Verifies `doc-as-done.AC4.1`, `doc-as-done.AC4.2`, `doc-as-done.AC4.3`, `doc-as-done.AC10.3`.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Prompt-capture artifact contract

**Goal:** Every LLM call that produces analytic content writes a replayable `<scope>-<stage>.<substep>.prompt.json` artifact. Audit events reference it.

**Components:**
- Prompt-artifact schema (single shape across all substeps):
  ```json
  {
    "schema_version": "1",
    "actor": {"kind": "subagent|orchestrator", "name": "mpi-analyst", "model": "claude-haiku-4-5"},
    "stage": "diachronic", "substep": "refined_du", "scope": "p1s1",
    "prompt": {"system": "...", "user": "...", "tools_available": [...]},
    "response": {"raw_text": "...", "parsed_units_path": "analyses/p1s1-diachronic.refined_du.json"},
    "metadata": {"finish_reason": "end_turn", "usage": {"input_tokens": 0, "output_tokens": 0}, "duration_ms": 0, "timestamp": "..."}
  }
  ```
- Helper accepts `--prompt-artifact <path>` (required for substeps that invoke an LLM; absent for orchestrator-only substeps like `transcript_prep`). The path is recorded in the audit event under `mpi.prompt_artifact_path`.
- Helper validates the prompt.json against its schema during pre-checks.
- A small replay verifier `scripts/mpi_replay.py` (out of scope for the contract; deferred to a later plan) reads a prompt.json and re-invokes the model to compare outputs — design notes the hook but does not implement.

**Dependencies:** Phase 2 (close transaction must exist), Phase 4 (validator infra).

**Done when:** Helper rejects a `close` invocation that names an LLM-invoking substep without `--prompt-artifact`; rejects a malformed prompt.json; accepts a well-formed one and writes the path into the audit event. Verifies `doc-as-done.AC11.1`, `doc-as-done.AC11.2`, `doc-as-done.AC11.3`.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Subagent contract — `mpi-analyst`

**Goal:** `mpi-analyst` self-persists per substep across the diachronic and synchronic stages (segment, du, refined_du, phases; groups, isus, structure per phase).

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-analyst.md` — `tools:` changes from `Read` to `Read, Write, Bash`
- New "Persistence (mandatory before returning)" subsection enumerating the per-substep persistence sequence: write `<scope>-<stage>.<substep>.{json,md,prompt.json}`, then invoke `python scripts/mpi_step.py close --stage <S> --substep <S2> --scope <pNsN[-phN]> --artifact <paths> --prompt-artifact <path> --units-json <path> --reason ...`, then return `OK <scope> <stage>.<substep> <N>units <K>flagged` or `ERROR <scope> <stage>.<substep>: <reason>` only
- Anti-fabrication clause added (verbatim, see Phase 10)
- Per-substep markdown table contract (column order, header) pinned in each `skills/mpi-<stage>/SKILL.md` so agent has a single source for output shape

**Dependencies:** Phase 2, Phase 4, Phase 5.

**Done when:** Agent declares `Read, Write, Bash`; the Persistence subsection enumerates all 7 mpi-analyst substeps (4 diachronic + 3 synchronic per phase); fixture-driven test exercises one diachronic substep end-to-end producing all three artifacts plus a clean `close`. Verifies `doc-as-done.AC1.4`, `doc-as-done.AC1.5`, `doc-as-done.AC6.1`, `doc-as-done.AC6.2`, `doc-as-done.AC10.4`.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Subagent contract — `mpi-cross-analyst`

**Goal:** `mpi-cross-analyst` self-persists per substep across the generic-diachronic, generic-synchronic, global-synchronic, and hypothesis stages.

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — `tools:` changes from `Read` to `Read, Write, Bash`
- "Persistence (mandatory before returning)" subsection enumerates: `generic_diachronic.{compare,gdus,structure}` (global scope); `generic_synchronic.{sss_grouping,gss_definition}` (per-GDU scope); `global_synchronic` (global); `hypothesis` (global)
- Anti-fabrication clause added
- Per-substep markdown table contract pinned in each cross-participant SKILL.md

**Dependencies:** Phase 2, Phase 4, Phase 5.

**Done when:** Agent declares `Read, Write, Bash`; Persistence subsection enumerates all cross-analyst substeps; fixture-driven test exercises one generic-diachronic substep end-to-end. Verifies `doc-as-done.AC6.1`, `doc-as-done.AC6.2`, `doc-as-done.AC10.5`.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Skill closure sweep — per-participant skills

**Goal:** Per-participant SKILL.md files (`mpi-init`, `mpi-transcript-prep`, `mpi-diachronic`, `mpi-synchronic`) gain a "Closure (mandatory)" subsection per substep naming the responsible actor and the substep's artifact set.

**Components:**
- `skills/mpi-init/SKILL.md` — orchestrator closes (`init` is a single substep; artifact is the manifest itself plus the empty `audit.jsonl`/`reasoning.log`)
- `skills/mpi-transcript-prep/SKILL.md` — orchestrator closes once per participant
- `skills/mpi-diachronic/SKILL.md` — mpi-analyst closes 4 substeps per participant (`segment`, `du`, `refined_du`, `phases`), each with its own artifact set and its own commit
- `skills/mpi-synchronic/SKILL.md` — mpi-analyst closes 3 substeps per phase per participant (`groups`, `isus`, `structure`); phase list comes from the participant's `diachronic.phases` output
- Each SKILL.md table-format spec is updated to one row per substep (replaces today's single-stage table)
- All existing yolo-commit prose blocks deleted in favour of the helper's canonical message

**Dependencies:** Phase 6.

**Done when:** Each per-participant SKILL.md contains a Closure subsection enumerating its substeps; no SKILL.md hand-specifies manifest mutation, log format, or git commit message format. Verifies `doc-as-done.AC6.3`, `doc-as-done.AC7.1`, `doc-as-done.AC10.6`.
<!-- END_PHASE_8 -->

<!-- START_PHASE_9 -->
### Phase 9: Skill closure sweep — cross-participant and read-only skills

**Goal:** Cross-participant SKILL.md files and read-only skills gain the same closure contract.

**Components:**
- `skills/mpi-generic-diachronic/SKILL.md` — mpi-cross-analyst closes 3 substeps globally (`compare`, `gdus`, `structure`)
- `skills/mpi-generic-synchronic/SKILL.md` — mpi-cross-analyst closes 2 substeps per GDU (`sss_grouping`, `gss_definition`); GDU list comes from `generic_diachronic.gdus` output
- `skills/mpi-global-synchronic/SKILL.md` — single substep, global scope, mpi-cross-analyst closes
- `skills/mpi-hypothesis/SKILL.md` — single substep, global scope, mpi-cross-analyst closes
- `skills/mpi-kappa/SKILL.md`, `skills/mpi-status/SKILL.md` — read-only; closure section explicitly states "no artifact close" but emits a `stage_phase: read` audit event for trace continuity

**Dependencies:** Phase 7.

**Done when:** Each cross-participant SKILL.md contains a Closure subsection; read-only skills explicitly declare their exemption and emit read-only audit events. Verifies `doc-as-done.AC6.3`, `doc-as-done.AC6.4`, `doc-as-done.AC7.1`.
<!-- END_PHASE_9 -->

<!-- START_PHASE_10 -->
### Phase 10: Anti-fabrication guards across all generative substeps

**Goal:** Every generative substep carries the verbatim anti-fabrication rule in prose form.

**Components:**
- Rule text (verbatim across files): "If your input artifacts (transcripts, upstream substep outputs) are missing, empty, or malformed, return `ERROR <reason>` and stop. Never generate placeholder or synthetic content to make the pipeline appear to progress."
- Added to every generative SKILL.md (diachronic, synchronic, generic_diachronic, generic_synchronic, global_synchronic, hypothesis)
- Added to both agent files (verify consistency with Phases 6 and 7)

**Dependencies:** Phases 8, 9.

**Done when:** `grep -l "Never generate placeholder"` across the plugin returns all six generative SKILL.md files plus both agent files. Verifies `doc-as-done.AC5.3`, `doc-as-done.AC5.4`.
<!-- END_PHASE_10 -->

<!-- START_PHASE_11 -->
### Phase 11: End-to-end pipeline test

**Goal:** Deterministic E2E test exercises the full pipeline against a tiny fixture corpus and asserts every substep artifact, audit event, and commit lands as expected.

**Components:**
- `tests/fixtures/e2e/transcripts/` — 4 fixture transcripts (2 participants × 2 suggestions, ~20 utterances each)
- `tests/fixtures/e2e/agent-responses/<stage>/<substep>/<scope>.json` — recorded structured responses keyed by stage, substep, and scope
- `tests/fixtures/e2e/prompts/<stage>/<substep>/<scope>.prompt.json` — recorded prompt-artifact fixtures (so the close call sees a valid prompt.json)
- `tests/test_e2e_pipeline.py` — driver: init in tempdir, walk the substep DAG, feed each fixture response to `mpi_step.py close` directly, assert artifacts + manifest + audit + commits + prompt-artifact references at substep granularity
- `tests/test_e2e_fail_fast.py` — negative-path companion: malformed unit, missing prompt-artifact, missing upstream substep → assert helper exits non-zero, manifest unchanged, no commit, no half-written artifact

**Dependencies:** Phases 1–10.

**Done when:** Both E2E tests pass. Coverage: every expected scope × substep × (json, md, prompt.json) triple exists and is non-empty; manifest reflects every closure at substep granularity; `audit.jsonl` validates, has unique `event_id`s, constant `trace_id`, and every event has a `mpi.prompt_artifact_path` for LLM-invoking substeps; `git log --oneline` shows one commit per substep with the canonical message; `mpi_step.py render` regenerates a reasoning.log that round-trips. Verifies `doc-as-done.AC7.2`, `doc-as-done.AC7.3`, `doc-as-done.AC8.1`, `doc-as-done.AC8.2`, `doc-as-done.AC8.3`, `doc-as-done.AC11.4`.
<!-- END_PHASE_11 -->

<!-- START_PHASE_12 -->
### Phase 12: Documentation alignment + existing-test reconciliation

**Goal:** Update both CLAUDE.md files and reconcile any existing tests broken by the new contract.

**Components:**
- `microphenomenograph/1.0.0/CLAUDE.md` — gains "Documentation-as-Done Contract" section pointing to `scripts/mpi_step.py`; substep DAG documented; the old per-stage output-path table and reasoning.log format note are deleted
- Top-level `C:\microphenomenograph\CLAUDE.md` — one-line summary added under "Plugin contracts"
- `tests/test_plugin_structure.py`, `tests/test_verify_mpi_init.py`, `tests/test_mpi_orchestration.py` — updated where they hardcoded the old write contracts; assertions retargeted to substep granularity
- Existing logic tests (`test_mpi_synchronic_logic.py`, `test_cross_participant_analysis.py`, `test_hypothesis_generation.py`, `test_transcript_prep.py`) — verified to still pass; updated only if they encoded the old contract

**Dependencies:** Phases 1–11.

**Done when:** `pytest` from repo root is green; both CLAUDE.md files reference `mpi_step.py`, the substep DAG, and the prompt-capture contract. Verifies `doc-as-done.AC9.1`, `doc-as-done.AC9.2`.
<!-- END_PHASE_12 -->

## Additional Considerations

**Implementation scoping: 12 phases require two implementation plans.** The writing-plans skill caps implementation plans at 8 phases. Recommended split:

- **Plan 1 (Phases 1–8): Foundation and per-participant pipeline.** Builds the helper CLI (Phases 1–3), pins per-substep schemas and prompt-capture contract (Phases 4–5), updates the mpi-analyst agent and per-participant skills (Phases 6, 8). After this plan, transcript_prep + diachronic + synchronic run end-to-end on the new contract; cross-participant skills still use the old contract.
- **Plan 2 (Phases 7, 9–12): Cross-participant pipeline, anti-fabrication, tests, docs.** Updates the mpi-cross-analyst agent (Phase 7 can live here since it has no per-participant dependency beyond Phases 2/4/5) and cross-participant skills (Phase 9), sweeps anti-fabrication guards (Phase 10), adds E2E tests (Phase 11), reconciles docs (Phase 12).

The split keeps each plan focused and within the 8-phase budget. Plan 1 leaves the pipeline in a working but incomplete state — the cross-participant skills still pass JSON over the wire as today — so users should not run `/mpi all` between the two plans; only `/mpi diachronic` and `/mpi synchronic` are upgraded after Plan 1.

**Shell-quoting risk.** Subagents invoking `python scripts/mpi_step.py close --units-json '<huge json blob>'` would be fragile on Windows. Mitigation: helper accepts `--units-json -` to read from stdin, and accepts `--units-json path/to/file.json` to read from disk. Agent prompt instructs the latter (write `analyses/pNsN-<stage>.units.json` first, then pass the path).

**JSONL corruption from partial writes.** Each append is a single `open('a'); write(line); fsync(); close()` with the line constructed entirely in memory. `mpi_step.py render` flags malformed lines as `MALFORMED:<lineno>` rather than aborting the render — keeps human visibility intact even when the JSONL has a damaged tail.

**Helper as single point of failure.** It's stdlib-only (~300 LOC estimated), runs locally, has unit tests that exercise it without LLM calls, and is the same Python interpreter that already runs `kappa.py`. No new install step.

**`/mpi all` orchestration interaction.** The orchestrator (Claude in the main loop, executing the `mpi` command's routing logic) is itself an actor and must also call `mpi_step.py close` for orchestration-level events (cascade resets, stage dispatches). Phase 5 enumerates the orchestrator's close-points.

**Backwards compatibility.** Pre-release per the repo CLAUDE.md — edits land in `microphenomenograph/1.0.0/` directly with no shim. Any extant `runs/*/` directories from prior pipeline runs are not migrated; users start fresh.

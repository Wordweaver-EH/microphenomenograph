# Documentation-as-Done Contract Design

## Summary

This design introduces a "Documentation-as-Done Contract" — a disciplined rule that no pipeline step may declare itself complete unless it has produced four artifacts together: an output file on disk, a structured audit event appended to `.mpi/audit.jsonl`, an updated manifest entry in `.mpi/project.json`, and a git commit binding all three. The contract is enforced by a single stdlib-only Python helper (`scripts/mpi_step.py`) with two verbs: `close`, which performs the four-artifact transaction with rollback semantics if any step fails, and `render`, which regenerates the human-readable `.mpi/reasoning.log` from the authoritative JSONL audit trail on demand.

The driving motivation is a class of failures observed in the current pipeline where subagents returned analysis content through conversation context rather than writing it to disk themselves, creating fragile implicit assumptions about who persists what. The fix gives both subagents (`mpi-analyst` and `mpi-cross-analyst`) `Write` and `Bash` tool grants so they can self-persist artifacts and call the helper directly, collapsing their return value from a large JSON blob to a short status string (`OK` or `ERROR`). Every generative substep also gains an explicit anti-fabrication rule: if upstream artifacts are missing or malformed the substep must return an error rather than synthesizing plausible-looking replacement content. Schema validation inside the helper catches field-name drift (the `idu_name` vs. `title` class of bug) at write time rather than silently propagating it.

Three granularity and fidelity decisions distinguish this design from the previous stage-level model. First, the unit of "step" is the methodology's natural **substep**, not a stage — and the substep names follow manual_kev.md (Sheldrake & Dienes 2025) literally rather than the µ-PATH pipeline (Wordweaver-EH/upath, which encodes a different and less-simplified procedure). Diachronic decomposes into criteria-grouping → criteria-revision → IDU-naming-ordering with no sub-phase identification (the manual explicitly excludes it). Synchronic decomposes into theme-grouping-within-IDU → ISU-naming → ISU-2nd-level-grouping, iterated **per IDU**. Generic and global stages preserve the manual's IV-category × event × generic-IDU worksheet structure. Second, every LLM-invoking substep writes a **prompt-capture artifact** (`<scope>-<stage>.<substep>.prompt.json`) containing the exact prompt, response, model id, finish reason, and token counts. Audit events reference this file by path so any analytic decision can be replayed offline; fabrication becomes detectable by replay rather than merely rule-violating. Third, Cohen's κ is promoted from status utility to a **one-shot setup calibration**: a single `mpi-kappa calibrate` invocation runs an alternate-agent analysis on one chosen (participant, stage) pair, appends a record to `.mpi/kappa_calibration.jsonl`, and emits a `kappa_warning` audit event at cross-participant stage start if κ < 0.6 or calibration is absent. The default is warn-only — yolo runs proceed regardless — matching the manual's "an example … continue training until κ > .6" framing as a training-time check, not a per-transcript gate. Strict blocking is opt-in via `--strict-kappa`.

## Definition of Done

1. Every step in the MPI pipeline (subagent or orchestrator) writes its own artifact, updates the manifest, and git-commits before claiming done; a step that does not complete all four is `pending`, never silently `done`.
2. `mpi-analyst` and `mpi-cross-analyst` agents gain `Write` and self-persist their artifacts plus their log entries.
3. Per-analytic-unit decisions (each IDU/ISU coding call, manifest mutation, commit, flag) are logged to a structured `.mpi/audit.jsonl`; `.mpi/reasoning.log` is rendered on demand from the JSONL by `mpi_step.py render`.
4. An end-to-end pipeline test runs `/mpi all` on a tiny fixture corpus and asserts every expected on-disk artifact lands.
5. Downstream skills fail-fast when upstream artifacts are missing/malformed — never synthesize replacements.
6. **Step granularity matches the manual_kev.md (Sheldrake & Dienes 2025) simplified procedure, and each substep is LLM-atomic.** LLM substeps are sized to fit one focused subagent call; purely mechanical reshape operations (parse/copy/sort) are orchestrator-only and do NOT invoke the LLM or produce a prompt-capture artifact. Diachronic: `criteria_grouping` (LLM, per participant), `criteria_revision` (LLM, per participant, **one revision pass per close** — convergence decision is an explicit artifact field), `idu_naming_ordering` (LLM, per participant). Synchronic: `theme_grouping_within_idu` (LLM, **per IDU**), `isu_naming` (LLM, per IDU), `isu_second_level_grouping` (LLM, per IDU). Generic diachronic: `participant_row_assembly` (orchestrator, per event), `idu_similarity_grouping` (LLM, per event — analytic judgment of which IDUs across participants describe similar moments; emits a colour/group label per IDU cell), `pattern_identification` (LLM, per event — extracts common ordered patterns across the IV-grouped rows for that event), `cross_iv_contrast` (LLM, per event — explicit comparison of how the identified patterns differ by IV level, the manual's actual analytic goal). Generic synchronic: `select_generic_idus_of_interest` (LLM, per event — picks which generic IDUs from `generic_diachronic` warrant per-IV synchronic analysis, citing pattern membership), `worksheet_assembly` (orchestrator, per event × IV category × selected generic-IDU), `isu_second_level_grouping` (LLM, per worksheet). Global synchronic: one LLM substep per (generic-IDU × IV category). Hypothesis generation: three substeps (see DoD #9). Every substep — LLM or orchestrator — closes its own four-part transaction.
7. **Every LLM call is captured as a replayable artifact.** Each substep that invokes an LLM writes `analyses/<scope>-<stage>.<substep>.prompt.json` containing the exact prompt, response, model id, finish reason, and token counts. Audit events reference this file by path so the analytic decision can be replayed offline.

8. **Cohen's κ is a one-shot setup sanity check, not a per-run gate.** Per manual_kev.md, κ > 0.6 is a training-time check on **one sample** between the primary analyst and an independent second analyst; the manual says "an example should be used to compare the analyses … continue training until κ > .6", not "block every production run". The pipeline reflects this: each `mpi-kappa calibrate` invocation produces an independent second analysis of one selected (participant, stage) pair using an alternate agent, computes κ, and **appends** a record to `.mpi/kappa_calibration.jsonl` (history, not single file — "continue training" implies repeatable attempts). Cross-participant stages emit a **warning** if the most-recent calibration is `low` or absent, but do not block — yolo runs to completion regardless. Users who want strict blocking can pass `--strict-kappa` to opt in.

9. **Hypothesis generation is three substeps, not one.** The manual frames hypothesis generation as patterns varying by IV level across **all three** of generic diachronic, generic synchronic, and global synchronic outputs — synthesis, framing, and evidence audit are distinct cognitive loads that should not share a single LLM call. The three substeps: `hypothesis.evidence_extraction` (LLM, per DV focus — gathers pattern variations from **all three upstream sources**: `generic_diachronic.cross_iv_contrast` outputs for IV-level pattern differences, `generic_synchronic.isu_second_level_grouping` outputs for theme variations within generic IDUs, AND `global_synchronic` outputs for cross-event theme patterns; preserves full traceability with citation paths to every source artifact), `hypothesis.candidate_drafting` (LLM, per DV focus — drafts causal hypotheses framed against IV-level differences; cites evidence artifact paths), `hypothesis.weak_evidence_review` (LLM, global — flags hypotheses whose supporting evidence is thin given the participant count, mirroring the manual's "small number of participants … only provides weak evidence" guidance). Output: one `hypotheses/dv-<focus>.{evidence,candidates}.md` per DV focus plus a global `hypotheses/review_summary.md`.

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
- **doc-as-done.AC7.2 Success:** Audit events follow the documented schema: `event_id` (UUID4), `@timestamp` (RFC3339 UTC), `trace_id`, `span_id`, `actor.{kind,name,model}`, `event.{kind,category,action,outcome, duration_ms}`, `mpi.{participant,stage,unit,manifest_status,artifact_paths,artifact_sha256,prompt_artifact_path,git_commit_sha}`, `reason`. The `event.duration_ms` field is populated by `stage_completed` events (the holder records its full lock-held duration there, providing on-disk visibility of long-running closes that the waiting-process stderr warning only signalled ephemerally).
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
- **doc-as-done.AC10.2 Success:** `mpi_step.py close --substep <S2>` enforces the substep DAG — closing `diachronic.idu_naming_ordering` is rejected if `diachronic.criteria_revision` is not `done`.
- **doc-as-done.AC10.3 Success:** Each (stage, substep) pair has its own schema in `_mpi_schemas.py`; helper invokes the schema matching the `--substep` flag.
- **doc-as-done.AC10.4 Success:** `agents/mpi-analyst.md` Persistence subsection enumerates all 6 mpi-analyst substeps (3 diachronic per participant + 3 synchronic per IDU) with per-substep artifact paths and the manual-native substep names (`criteria_grouping`, `criteria_revision`, `idu_naming_ordering`, `theme_grouping_within_idu`, `isu_naming`, `isu_second_level_grouping`).
- **doc-as-done.AC10.5 Success:** `agents/mpi-cross-analyst.md` Persistence subsection enumerates all cross-analyst LLM substeps: `generic_diachronic.{idu_similarity_grouping, pattern_identification, cross_iv_contrast}` (per event); `generic_synchronic.{select_generic_idus_of_interest, isu_second_level_grouping}`; `global_synchronic`; `hypothesis.{evidence_extraction, candidate_drafting, weak_evidence_review}`; and `kappa_calibration.independent_analyst`. Orchestrator-only substeps (`participant_row_assembly`, `worksheet_assembly`) are NOT enumerated in the agent file because the agent does not execute them.
- **doc-as-done.AC10.6 Success:** Every SKILL.md Closure subsection enumerates its substeps and the responsible actor for each.

### doc-as-done.AC11: Every LLM call is captured as a replayable artifact
- **doc-as-done.AC11.1 Success:** For every LLM-invoking substep close, a `<scope>-<stage>.<substep>.prompt.json` artifact exists on disk containing the exact prompt, response, model id, finish reason, and token counts.
- **doc-as-done.AC11.2 Failure:** A `close` invocation for an LLM-invoking substep without `--prompt-artifact` is rejected with a named error.
- **doc-as-done.AC11.3 Failure:** A malformed `prompt.json` (missing required keys, wrong schema_version) is rejected at pre-check time; manifest unchanged.
- **doc-as-done.AC11.4 Success:** Each audit event for an LLM-invoking substep carries `mpi.prompt_artifact_path` pointing at the on-disk prompt.json.

### doc-as-done.AC12: Manual-native methodology fidelity
- **doc-as-done.AC12.1 Success:** Synchronic substeps iterate **per IDU within a participant**, not per phase. There is no `diachronic.phases` substep, no `diachronic.du`, no `diachronic.refined_du`, no `generic_synchronic.sss_grouping`, no `generic_synchronic.gss_definition`. Substep names match manual_kev.md verbatim.
- **doc-as-done.AC12.2 Success:** Synchronic schema preserves three distinct fields per ISU row: `criteria` (string), `isu_name` (string), `isu_second_level_of_abstraction` (string or empty). Generic-synchronic and global-synchronic schemas preserve `isu_second_level_of_abstraction` as a distinct column through aggregation.
- **doc-as-done.AC12.3 Success:** If `synchronic.theme_grouping_within_idu` flags `temporal_order_within_idu: true`, the orchestrator schedules `diachronic.criteria_revision` re-close for that participant; manifest records `idu_split_after_synchronic` audit event linking both span_ids.
- **doc-as-done.AC12.4 Success:** If `synchronic.theme_grouping_within_idu` flags `concurrent_with_adjacent_idu: {idu_id, rationale}` AND `--allow-synchronic-merge` is enabled, the orchestrator schedules `diachronic.criteria_revision` re-close with merge context in the prompt; manifest records `idu_merge_after_synchronic` audit event linking both span_ids. Without the flag, a `concurrent_with_adjacent_idu` finding is logged as a `merge_candidate_ignored` audit event (advisory only — for human inspection) and no re-close is scheduled.
- **doc-as-done.AC12.5 Success:** Both `synchronic.theme_grouping_within_idu` artifact schemas (`temporal_order_within_idu`, `concurrent_with_adjacent_idu`) are distinct, optional fields; default values are `false` and `null` respectively.

### doc-as-done.AC13: Kappa calibration is one-shot setup evidence (not a per-run gate)
- **doc-as-done.AC13.1 Success:** `mpi-kappa calibrate` runs on a single chosen `(participant, stage)` pair, produces the alternate analysis under `analyses/independent/<pNsN>-<stage>.{json,md,prompt.json}` plus `.mpi/kappa_calibration.jsonl`, and emits one `kappa_calibration` audit event.
- **doc-as-done.AC13.2 Success:** Cross-participant skills emit a `kappa_warning` audit event at stage start if `.mpi/kappa_calibration.jsonl` is missing or its `outcome == "low"`. They proceed and produce their artifacts normally — no blocking.
- **doc-as-done.AC13.3 Success:** When `/mpi all --strict-kappa` is passed and calibration is missing or low, cross-participant stages exit with a named ERROR before producing any artifacts.
- **doc-as-done.AC13.4 Success:** `kappa_calibration.jsonl` contains `{participant, stage, primary_model, alternate_model, kappa, ci_lower, ci_upper, n_units, threshold: 0.6, outcome: "passed"|"low", timestamp}`.

### doc-as-done.AC14: Yolo execution is fully auditable on disk
- **doc-as-done.AC14.1 Success:** A skipped substep emits a `stage_blocked` audit event with `mpi.blocked_reason` and the upstream `event_id`; absence of an artifact alone is never the only trace.
- **doc-as-done.AC14.2 Success:** Each `/mpi all` run has a single `trace_id` (UUID4) persisted at `.mpi/run_id`; resumed runs reuse it.
- **doc-as-done.AC14.3 Failure:** Helper refuses to `close` when the worktree has uncommitted files outside `analyses/` and `.mpi/`; emits `dirty_worktree_refused` and exits non-zero.
- **doc-as-done.AC14.4 Failure:** A simulated `git commit` failure after audit + manifest write triggers a manifest rollback and a `commit_failed` audit event; artifact files remain, manifest reverts, next run re-closes.
- **doc-as-done.AC14.5 Failure:** A close invocation missing `--prompt-artifact` for an LLM substep, or with a prompt.json that fails schema validation, is rejected before any state mutation.

### doc-as-done.AC15: LLM substeps and orchestrator substeps are clearly distinguished
- **doc-as-done.AC15.1 Success:** Each substep schema declares `actor_kind: "subagent"|"orchestrator"`. Subagent substeps require `--prompt-artifact`; orchestrator substeps reject `--prompt-artifact` (the audit event records `actor.kind: orchestrator` and no `mpi.prompt_artifact_path`).
- **doc-as-done.AC15.2 Success:** `generic_diachronic.participant_row_assembly` and `generic_synchronic.worksheet_assembly` execute without LLM calls (no prompt artifact, no model field in audit). `generic_diachronic.{idu_similarity_grouping, pattern_identification, cross_iv_contrast}`, `generic_synchronic.{select_generic_idus_of_interest, isu_second_level_grouping}`, `global_synchronic`, and all three `hypothesis.*` substeps execute via subagent with prompt-capture artifacts.
- **doc-as-done.AC15.3 Success:** `diachronic.criteria_revision` artifact JSON contains a `convergence: {decision, reason}` field. Orchestrator dispatches further `criteria_revision` substeps only while `decision == "more_revision_needed"`, capped at 5 passes (emits `revision_cap_reached` if hit).

### doc-as-done.AC16: Cascade reset preserves cross-substep consistency
- **doc-as-done.AC16.1 Success:** Re-closing `diachronic.criteria_revision` for `pNsN` resets `diachronic.idu_naming_ordering` for `pNsN`, every `synchronic.*` substep scoped to affected `pNsN-iduN`, and all cross-participant substeps to `pending` in a single manifest write.
- **doc-as-done.AC16.2 Success:** Each reset emits a `cascade_reset` audit event with `mpi.cascade_source` referencing the revision's `event_id`.
- **doc-as-done.AC16.3 Failure:** Cross-participant skills invoked between cascade-reset write and downstream re-close exit with `upstream_pending` error and produce no artifacts.
- **doc-as-done.AC16.4 Failure (generic_diachronic gate):** `generic_diachronic.*` substep close is rejected with `prereq_unsatisfied` if any participant assigned to the event has pending diachronic or synchronic substeps, OR if any synchronic artifact for that participant carries an unresolved `temporal_order_within_idu: true` or `concurrent_with_adjacent_idu` flag (no follow-up `criteria_revision` close has been done).
- **doc-as-done.AC16.5 Failure (hypothesis gate):** `hypothesis.evidence_extraction` close is rejected with `prereq_unsatisfied` unless `generic_diachronic.*`, `generic_synchronic.*`, AND `global_synchronic.*` are all `done` for the manifest's full event × IV × generic-IDU coverage. Verified by helper pre-check against the manifest.
- **doc-as-done.AC16.6 Success (hypothesis evidence sources):** Each `hypothesis.evidence_extraction` artifact JSON contains citation paths covering at least one source from each of the three upstream stages (`generic_diachronic`, `generic_synchronic`, `global_synchronic`) per DV focus. The helper schema validates that `evidence_sources.{generic_diachronic, generic_synchronic, global_synchronic}` are all non-empty arrays.

### doc-as-done.AC17: Hypothesis is three substeps with traceability
- **doc-as-done.AC17.1 Success:** `hypothesis.evidence_extraction` runs once per DV focus and writes `hypotheses/dv-<focus>.evidence.{json,md,prompt.json}`; the JSON cites source artifact paths for every claim.
- **doc-as-done.AC17.2 Success:** `hypothesis.candidate_drafting` runs once per DV focus, reads only the matching evidence artifact, writes `hypotheses/dv-<focus>.candidates.{json,md,prompt.json}`.
- **doc-as-done.AC17.3 Success:** `hypothesis.weak_evidence_review` runs once globally, reads all candidate artifacts, writes `hypotheses/review_summary.{json,md,prompt.json}` flagging hypotheses whose support is thin.
- **doc-as-done.AC17.4 Success:** Each candidate hypothesis carries the IDs of the evidence claims it cites; broken citations are flagged in the review.

### doc-as-done.AC18: Generic diachronic enforces cross-IV contrast
- **doc-as-done.AC18.1 Success:** `generic_diachronic.idu_similarity_grouping` is an LLM substep (not a deterministic colour heuristic); produces a colour/group label per IDU cell with one-sentence rationale per label.
- **doc-as-done.AC18.2 Success:** `generic_diachronic.cross_iv_contrast` runs per event after `pattern_identification`; output explicitly enumerates how identified patterns differ across IV levels (or notes "no observed contrast").
- **doc-as-done.AC18.3 Success:** `generic_synchronic.select_generic_idus_of_interest` runs per event, reads pattern/cross-contrast outputs, and writes the list of generic-IDUs that downstream worksheet substeps will scope to.

### doc-as-done.AC19: Study configuration is user-driven and validated
- **doc-as-done.AC19.1 Success:** `init.propose_study_config` produces an `ivs` + `dvs` proposal with rationale; `init.confirm_study_config` presents it via AskUserQuestion and persists the final answer into `study: {ivs, dvs}` in the manifest.
- **doc-as-done.AC19.2 Failure:** IV levels with overlapping numeric ranges are rejected by the schema validator unless `--allow-overlap` is passed with a non-empty `overlap_rationale`.
- **doc-as-done.AC19.3 Failure:** IV levels that do not cover the full observed score range are rejected unless `excluded_scores` is explicitly declared.
- **doc-as-done.AC19.4 Success:** The `study` block becomes immutable after `init.confirm_study_config` closes; `mpi-init --force-reconfigure` is the only path to change it, emits `study_reconfigured`, archives `analyses/` to `analyses.archived-<ts>/`, and resets every substep to `pending`.

### doc-as-done.AC20: Extended yolo audit semantics
- **doc-as-done.AC20.1 Success:** A second concurrent `mpi_step.py close` invocation acquires `.mpi/close.lock`; if blocked over 30s, errors `concurrent_close_blocked` with the holding pid.
- **doc-as-done.AC20.2 Success:** Every close audit event records `mpi.artifact_sha256: {path: sha256, ...}` and `git.{branch, head_sha}`.
- **doc-as-done.AC20.3 Failure:** Resuming with HEAD different from the manifest's last recorded commit SHA emits `head_mismatch` and refuses to close until resolved.
- **doc-as-done.AC20.4 Success:** A stale lock is auto-reclaimed **only** when the holder PID is verifiably not running on the same host (POSIX: `os.kill(pid, 0)` raises ESRCH; Windows: `OpenProcess` returns null); emits `stale_lock_reclaimed`. Long-running closes never trigger reclaim regardless of age. Cross-host locks (different hostname in lock file) refuse to reclaim and error `cross_host_lock_unresolvable`. Manual override path `mpi_step.py unlock --reason ...` emits `manual_unlock` with the reason and is the documented recovery for PID-reuse, frozen processes, or shared-filesystem cases.

### doc-as-done.AC21: IV overlap has deterministic tie-resolution semantics
- **doc-as-done.AC21.1 Success:** Without `--allow-overlap`, overlapping IV bins are rejected. With `--allow-overlap` and `tie_resolution: "upper"|"lower"`, each ambiguous score is deterministically assigned to one level; downstream worksheets show the participant in exactly that level's rows.
- **doc-as-done.AC21.2 Success:** With `tie_resolution: "duplicate"`, the participant appears in both overlapping levels' generic-diachronic rows; every event mentioning this participant carries `mpi.duplicate_assignment: true`; downstream cross-IV contrast counts the participant once per assignment.
- **doc-as-done.AC21.3 Success:** `tie_resolution` is recorded **per overlapping level pair** in `study.ivs[i].overlaps: [{lower_level, upper_level, shared_values, tie_resolution, rationale}]`, not per-IV. The manifest's `overlaps` array is empty if no overlaps exist.

### doc-as-done.AC22: DV foci are attention hints, not filters
- **doc-as-done.AC22.1 Success:** `synchronic.{theme_grouping_within_idu, isu_naming}` artifacts contain coding decisions for every utterance in their IDU regardless of DV-focus match; no utterance is dropped for being off-focus.
- **doc-as-done.AC22.2 Success:** `hypothesis.evidence_extraction` produces one artifact per DV focus, scoped; `hypothesis.candidate_drafting` produces one candidates artifact per DV focus, framed against that focus.

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
- **Substep**: The methodology's natural unit of analytic work, finer than a stage. E.g., `diachronic` decomposes into `criteria_grouping`, `criteria_revision`, `idu_naming_ordering`. Substep IDs follow the form `<stage>.<substep>`. Each substep closes its own four-part transaction and is independently resumable.
- **Substep DAG**: The directed graph of substep prerequisites (e.g., `diachronic.idu_naming_ordering` requires `diachronic.criteria_revision: done`). Encoded in `_mpi_schemas.py` and enforced by `mpi_step.py close` pre-checks.
- **Prompt-capture artifact (`.prompt.json`)**: Per-substep file containing the exact LLM prompt, response, model id, finish reason, and token counts. Enables offline replay of any analytic decision; fabrication becomes detectable by comparison rather than only by rule.
- **µ-PATH (Wordweaver-EH/upath)**: A same-domain microphenomenological analysis pipeline whose substep granularity and per-step JSON-output convention inspired this design's substep model. µ-PATH itself encodes the Valenzuela-Moguillansky & Vásquez-Rosati 2019 procedure, which differs from manual_kev.md (used here) in important ways — µ-PATH produces phases/sub-phases and DU/refined-DU/SSS/GSS outputs that this manual deliberately excludes.
- **manual_kev.md**: The Sheldrake & Dienes (2025) simplified procedure used as this pipeline's source of truth. Defines IDU, ISU, ISU 2nd Level of Abstraction as the analytic columns; excludes diachronic sub-phase identification; requires Cohen's κ > 0.6 against an independent second analyst before relying on results.
- **IDU 2nd Level of Abstraction grouping**: A substep that surveys ISUs within an IDU (or across IDUs in generic/global synchronic) for higher-level themes and assigns a 2nd-level name. Preserved as a distinct column throughout synchronic-family substeps.
- **Kappa calibration**: A one-shot setup utility (NOT a per-run gate). Produces an independent-analyst pass (alternate model or prompt variant) on one chosen (participant, stage) pair, computes Cohen's κ, and appends the result to `.mpi/kappa_calibration.jsonl`. Cross-participant stages emit a warning if κ < 0.6 or calibration is absent but proceed regardless; strict blocking requires the `--strict-kappa` flag.
- **IDU-split-after-synchronic return edge**: A re-close of `diachronic.criteria_revision` triggered when a `synchronic.theme_grouping_within_idu` finding reveals temporal order within an IDU. Encoded as an `idu_split_after_synchronic` audit event linking the two substep span_ids.

## Architecture

Every MPI pipeline step — whether executed by a subagent or by the orchestrator — closes by producing four artifacts atomically: an output file on disk, one or more audit events appended to `.mpi/audit.jsonl`, an atomic manifest mutation, and a single git commit binding the three together. A step that does not close all four is `pending` in the manifest. No partial credit; no implicit `done`.

**Substep granularity (manual-native).** The unit of "step" is the substep named after the operation manual_kev.md actually prescribes. The µ-PATH pipeline (Wordweaver-EH/upath) inspired the *idea* of substep granularity but encodes a different methodology (Valenzuela-Moguillansky & Vásquez-Rosati 2019, with sub-phase identification and DU/refined-DU/SSS/GSS terminology). manual_kev.md is a deliberately simplified variant that **omits** sub-phase identification and uses IDU/ISU/ISU-2nd-level-of-abstraction as the analytic columns. The substep map below follows the manual literally.

| Stage | Substeps | Iteration |
|---|---|---|
| `init` | `scan_transcripts`, `propose_study_config`, `confirm_study_config` | one-shot at init |
| `transcript_prep` | one | per participant |
| `diachronic` | `criteria_grouping`, `criteria_revision`, `idu_naming_ordering` | per participant |
| `synchronic` | `theme_grouping_within_idu`, `isu_naming`, `isu_second_level_grouping` | per participant × **per IDU** |
| `kappa_calibration` | `independent_analyst` (LLM, alternate agent), `agreement_computation` (orch) | one-shot setup utility — NOT a per-run gate; warning-by-default |
| `generic_diachronic` | `participant_row_assembly` (orch), `idu_similarity_grouping` (LLM), `pattern_identification` (LLM), `cross_iv_contrast` (LLM) | assembly+grouping per event; pattern_id per event; cross_iv per event |
| `generic_synchronic` | `select_generic_idus_of_interest` (LLM, per event), `worksheet_assembly` (orch), `isu_second_level_grouping` (LLM) | per (event × IV category × generic-IDU-of-interest) |
| `global_synchronic` | one | per (generic-IDU × IV category) |
| `hypothesis` | `evidence_extraction` (LLM), `candidate_drafting` (LLM), `weak_evidence_review` (LLM) | first two per DV focus; review global |

Substep IDs follow the form `<stage>.<substep>` (e.g., `diachronic.idu_naming_ordering`). Each substep closes its own four-part transaction; failed substeps are resumable independently. The substep DAG enforces methodological order: `synchronic.theme_grouping_within_idu` per (participant × IDU) requires `diachronic.idu_naming_ordering` for that participant to be `done`. `kappa_calibration` is **not** a prerequisite — it is a setup utility that emits warnings (or, with `--strict-kappa`, errors) but does not gate the DAG.

**Important deviations from a stage-level model.** Synchronic iterates **per IDU within a participant**, not "per phase" — manual_kev.md does not produce phases. The diachronic ↔ synchronic feedback is asymmetric in the manual:

- *Within* `diachronic.criteria_revision` (manual line 59): both directions are explicit — utterances "grouped by a single temporal criterion actually represent two or more moments" (split), or "two or more moments actually appear to happen concurrently and not sequentially" (merge). Both are handled inside the revision loop already; the substep's job is to revise criteria, which can split or merge groups.
- *From synchronic back to diachronic* (manual line 67): only split is named explicitly — "If synchronic analysis has revealed themes within an IDU that exhibit temporal order, then this indicates that the IDU represents more than a single IDU and should be split."

The substep DAG supports both feedback directions via two distinct flag fields in the `synchronic.theme_grouping_within_idu` artifact: `temporal_order_within_idu: bool` (manual-licensed split signal) and `concurrent_with_adjacent_idu: {idu_id, rationale} | null` (extension beyond the manual's literal wording — flags merge candidates when synchronic reveals that two adjacent IDUs share themes and aren't really temporally distinct). The orchestrator re-closes `diachronic.criteria_revision` with the relevant flag context in its prompt; the revision substep itself does the split-or-merge work and emits one of two audit events: `idu_split_after_synchronic` or `idu_merge_after_synchronic`. The merge variant is opt-in (`--allow-synchronic-merge`) since it extends the manual's wording; default behaviour is split-only.

**Cascade reset on revision.** Re-closing `diachronic.criteria_revision` for participant `pNsN` triggers an automatic cascade in the manifest: `diachronic.idu_naming_ordering` for `pNsN` resets to `pending`; every `synchronic.*` substep scoped to a `pNsN-iduN` whose IDU was affected resets to `pending`; **all cross-participant substeps** (`generic_diachronic.*`, `generic_synchronic.*`, `global_synchronic.*`, `hypothesis.*`) reset to `pending` because their inputs are no longer current. The cascade itself emits one `cascade_reset` audit event per reset substep, with `mpi.cascade_source` referencing the triggering revision's `event_id`. The orchestrator MUST process these resets in a single manifest write before re-dispatching downstream work; otherwise yolo would happily run cross-participant analysis on inconsistent inputs.

**Explicit prerequisite gates** (enforced by `mpi_step.py close` pre-checks; refusal emits `prereq_unsatisfied` error):

- **`generic_diachronic.*` (any event)** requires, for every participant assigned to that event: (a) all three `diachronic.*` substeps `done`, (b) all `synchronic.*` substeps for every IDU of that participant `done`, AND (c) **no pending `temporal_order_within_idu: true` or `concurrent_with_adjacent_idu` flag** that hasn't been resolved by a follow-up `diachronic.criteria_revision` re-close. Manual: *"Due to the possibility of the synchronic analysis identifying issues with the diachronic analysis, it is not recommended to conduct generic diachronic analysis until the synchronic analysis has been completed."* This gate makes that recommendation a hard precondition.
- **`generic_synchronic.*`** requires the matching `generic_diachronic.*` outputs for the same (event, IV category).
- **`global_synchronic.*`** requires `generic_synchronic.*` for every relevant (event × IV category × generic-IDU) triple.
- **`hypothesis.*`** requires `generic_diachronic.*`, `generic_synchronic.*`, AND `global_synchronic.*` to all be `done`. Manual: *"By developing generic diachronic analyses, generic synchronic analyses, and global synchronic analyses, it is now possible to look for patterns that vary per independent score level..."* — hypothesis evidence draws on all three.

**Study configuration is user-driven, orchestrator-proposed.** IV categories (e.g., response-score bins `low=0–1, moderate=2–3, high=4–5`) and DV foci (e.g., `cognition, emotion, sensations, imagination`) are study-specific. Per manual_kev.md, the IV is paired with the experimental design (in the example study, a Likert score grouped into low/moderate/high) and the DV focus shapes interview probes and downstream analysis attention. The pipeline does NOT hardcode these. `init` runs three substeps:

1. `init.scan_transcripts` (orchestrator) — copy transcripts into the run directory, parse headers (`Participant N, Suggestion N (Scored N/M)`), enumerate participants, suggestions, score values.
2. `init.propose_study_config` (LLM, single subagent call) — given the parsed headers and a small sample of utterances per transcript, propose an IV scheme (categories + numeric ranges) and a DV focus list. Output schema: `{ivs: [{name, levels: [{name, range: [lo, hi]}]}], dvs: [{name, description, example_terms: [...]}], rationale: "..."}`.
3. `init.confirm_study_config` (orchestrator + user) — present the proposal via `AskUserQuestion`; user accepts, edits, or replaces. Final answer persisted into the manifest under `study: {ivs, dvs}`. All downstream substeps that need to scope per (event × IV category) read from this manifest section. DV foci are **attention hints**, not filters — they shape what `synchronic.isu_naming` and the `hypothesis.*` substeps emphasise, but never drop utterances or evidence from the analysis (see DV-focus caveat in Additional Considerations).

The manifest's `study` block is immutable after `init.confirm_study_config` closes; changing it requires `mpi-init --force-reconfigure` (see Yolo auditability). DV foci shape `synchronic.isu_naming` (subagent is told which thematic dimensions matter most) and `hypothesis` substeps (causal hypotheses are framed per DV focus, by IV level).

**IV bin schema.** Each IV's `levels` array must be non-overlapping by default — distinct closed integer ranges with no shared value. The validator rejects overlaps unless the user passes `--allow-overlap`, in which case `study.ivs[i].overlaps` becomes a required array: each overlap entry names the `lower_level`, `upper_level`, `shared_values` (the integer set in both bins), a `tie_resolution` in `{"upper", "lower", "duplicate"}`, and a free-text `rationale`. `"upper"` assigns ambiguous scores to the higher level; `"lower"` to the lower; `"duplicate"` assigns to BOTH levels (the participant appears in both generic-diachronic rows; downstream cross-IV contrast counts the participant once per assignment with `mpi.duplicate_assignment: true` audit annotation). Multi-level overlaps (three or more bins covering the same value) are explicitly rejected — they require a real category redesign, not a tie-resolution choice. The user's example bins `low 1-2 / med 3-4 / high 4-5` overlap at value 4: without `--allow-overlap`, rejected; with `overlaps: [{lower_level: "med", upper_level: "high", shared_values: [4], tie_resolution: "upper", rationale: "..."}]`, value 4 → high. Bins must also cover the full observed score range across the corpus or explicitly declare excluded scores via `study.ivs[i].excluded_scores: [...]`.

**DV-focus scope (caveat).** DV foci are **attention hints**, not filters. `synchronic.isu_naming` receives the DV foci in its prompt so the agent prefers naming themes that intersect with study focus, but the manual's IDU/ISU coding still operates on the full transcript content — never drop utterances because they don't match a DV focus. The DV foci have their real bite in `hypothesis.evidence_extraction` (one extraction artifact per DV focus, scoped) and `hypothesis.candidate_drafting` (causal hypotheses framed per DV focus). This preserves the manual's stance that the DV "was generated from the utterances the participant made during the interview" — i.e., it emerges from data, with study focus shaping the framing not the data.

**Per-substep artifacts.** Each substep that produces analytic content writes three files into `analyses/`:
- `<scope>-<stage>.<substep>.json` — structured output (the raw analyst result)
- `<scope>-<stage>.<substep>.md` — human-readable spec-format markdown
- `<scope>-<stage>.<substep>.prompt.json` — exact LLM prompt + response + model id + finish reason + token counts (replay artifact)

Scope identifiers (`<scope>`):
- `pNsN` — per-participant work (transcript_prep, diachronic substeps)
- `pNsN-iduN` — per-IDU synchronic substeps (replaces an earlier draft's per-phase scoping; the manual is per-IDU)
- `event<E>-cat-<C>` — per (event × IV category) generic_diachronic substeps
- `event<E>-cat-<C>-gidu<G>` — per (event × IV category × generic-IDU-of-interest) for generic_synchronic worksheets
- `gidu<G>-cat-<C>` — per (generic-IDU × IV category) for global_synchronic
- `global` — for the `weak_evidence_review` substep of hypothesis and for `kappa_calibration`

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

The substep map follows manual_kev.md (Sheldrake & Dienes 2025) literally. An earlier draft of this design borrowed substep names from the µ-PATH pipeline (Wordweaver-EH/upath), but that pipeline encodes the Valenzuela-Moguillansky & Vásquez-Rosati 2019 procedure — a different, less-simplified methodology that produces phases/sub-phases, DU/refined-DU, and SSS/GSS outputs which manual_kev.md explicitly excludes. The current substep names (`criteria_grouping`, `idu_naming_ordering`, `theme_grouping_within_idu`, `isu_second_level_grouping`, etc.) are the operations the manual prescribes verbatim. ISU and ISU 2nd Level of Abstraction remain distinct analytic columns throughout, preserved by the per-stage schemas.

## Implementation Phases

This design has **13 phases** total. The writing-plans skill limits implementation plans to 8 phases — Phases 1–8 form the first implementation plan, Phases 9–13 the second. See Additional Considerations for sequencing.

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
- Per-(stage, substep) prerequisite DAG hardcoded in `_mpi_schemas.py` — `diachronic.criteria_revision` requires `diachronic.criteria_grouping: done`; `diachronic.idu_naming_ordering` requires `diachronic.criteria_revision: done`; `synchronic.theme_grouping_within_idu` per IDU requires `diachronic.idu_naming_ordering: done` for that participant; etc.
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
- Coverage: `init.{scan_transcripts, propose_study_config, confirm_study_config}`; `transcript_prep`; `diachronic.{criteria_grouping, criteria_revision, idu_naming_ordering}`; `synchronic.{theme_grouping_within_idu, isu_naming, isu_second_level_grouping}` iterated per IDU; `generic_diachronic.{participant_row_assembly, idu_similarity_grouping, pattern_identification, cross_iv_contrast}` per event; `generic_synchronic.{select_generic_idus_of_interest, worksheet_assembly, isu_second_level_grouping}` per (event × IV category × generic-IDU); `global_synchronic`; `hypothesis.{evidence_extraction, candidate_drafting, weak_evidence_review}`; `kappa_calibration.{independent_analyst, agreement_computation}` (Phase 13). Schemas preserve `criteria`, `isu_name`, `isu_second_level_of_abstraction` as distinct fields throughout synchronic-family substeps; the `study: {ivs, dvs}` schema enforces non-overlap by default and validates against the observed score range.
- **Convergence-decision contract.** `diachronic.criteria_revision` represents **one revision pass**. Its schema requires a `convergence: {decision: "more_revision_needed"|"converged", reason: "<one sentence>"}` field. The orchestrator dispatches subsequent `criteria_revision` substeps until `decision == "converged"`, with a hard cap (default 5 passes) emitting a `revision_cap_reached` audit event if hit. This makes the "iterate until no further improvements can be made" instruction from manual_kev.md observable on disk: each pass is its own close with its own commit, and the convergence decision is a first-class artifact field, not a hidden LLM stop condition.
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
    "stage": "diachronic", "substep": "idu_naming_ordering", "scope": "p1s1",
    "prompt": {"system": "...", "user": "...", "tools_available": [...]},
    "response": {"raw_text": "...", "parsed_units_path": "analyses/p1s1-diachronic.idu_naming_ordering.json"},
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

**Goal:** `mpi-analyst` self-persists per substep across the diachronic and synchronic stages (`criteria_grouping`, `criteria_revision`, `idu_naming_ordering` per participant; `theme_grouping_within_idu`, `isu_naming`, `isu_second_level_grouping` per IDU).

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-analyst.md` — `tools:` changes from `Read` to `Read, Write, Bash`
- New "Persistence (mandatory before returning)" subsection enumerating the per-substep persistence sequence: write `<scope>-<stage>.<substep>.{json,md,prompt.json}`, then invoke `python scripts/mpi_step.py close --stage <S> --substep <S2> --scope <pNsN[-phN]> --artifact <paths> --prompt-artifact <path> --units-json <path> --reason ...`, then return `OK <scope> <stage>.<substep> <N>units <K>flagged` or `ERROR <scope> <stage>.<substep>: <reason>` only
- Anti-fabrication clause added (verbatim, see Phase 10)
- Per-substep markdown table contract (column order, header) pinned in each `skills/mpi-<stage>/SKILL.md` so agent has a single source for output shape

**Dependencies:** Phase 2, Phase 4, Phase 5.

**Done when:** Agent declares `Read, Write, Bash`; the Persistence subsection enumerates all 6 mpi-analyst substeps (3 diachronic per participant + 3 synchronic per IDU); fixture-driven test exercises one diachronic substep end-to-end producing all three artifacts plus a clean `close`. The IDU-split-after-synchronic return edge (re-close `diachronic.criteria_revision` after a `synchronic.theme_grouping_within_idu` finding) is exercised in a separate fixture. Verifies `doc-as-done.AC1.4`, `doc-as-done.AC1.5`, `doc-as-done.AC6.1`, `doc-as-done.AC6.2`, `doc-as-done.AC10.4`, `doc-as-done.AC12.1`.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Subagent contract — `mpi-cross-analyst`

**Goal:** `mpi-cross-analyst` self-persists per substep across the generic-diachronic, generic-synchronic, global-synchronic, and hypothesis stages.

**Components:**
- `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md` — `tools:` changes from `Read` to `Read, Write, Bash`
- "Persistence (mandatory before returning)" subsection enumerates the LLM-driven substeps: `generic_diachronic.{idu_similarity_grouping, pattern_identification, cross_iv_contrast}` per event; `generic_synchronic.{select_generic_idus_of_interest, isu_second_level_grouping}` (select per event; grouping per worksheet); `global_synchronic` per (generic-IDU × IV category); `hypothesis.{evidence_extraction, candidate_drafting}` per DV focus and `hypothesis.weak_evidence_review` global; `kappa_calibration.independent_analyst` per calibration run. The mechanical assembly substeps (`participant_row_assembly`, `worksheet_assembly`, `kappa_calibration.agreement_computation`) are orchestrator-only (no LLM, no prompt artifact) — see Phase 9.
- Pre-check: at stage start, read `.mpi/kappa_calibration.jsonl` if present and surface its `kappa`/`outcome` in the agent's reasoning. Do NOT block; emit `kappa_warning` if missing or low and proceed.
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
- `skills/mpi-diachronic/SKILL.md` — mpi-analyst closes 3 substeps per participant (`criteria_grouping`, `criteria_revision`, `idu_naming_ordering`); explicitly notes the manual's exclusion of sub-phase identification
- `skills/mpi-synchronic/SKILL.md` — mpi-analyst closes 3 substeps **per IDU** per participant (`theme_grouping_within_idu`, `isu_naming`, `isu_second_level_grouping`); IDU list comes from the participant's `diachronic.idu_naming_ordering` output; markdown table preserves the ISU and ISU 2nd Level of Abstraction columns distinctly. If a `theme_grouping_within_idu` close flags `temporal_order_within_idu: true`, the orchestrator schedules a return-edge `diachronic.criteria_revision` re-close for that participant before continuing.
- Each SKILL.md table-format spec is updated to one row per substep (replaces today's single-stage table)
- All existing yolo-commit prose blocks deleted in favour of the helper's canonical message

**Dependencies:** Phase 6.

**Done when:** Each per-participant SKILL.md contains a Closure subsection enumerating its substeps; no SKILL.md hand-specifies manifest mutation, log format, or git commit message format. Verifies `doc-as-done.AC6.3`, `doc-as-done.AC7.1`, `doc-as-done.AC10.6`.
<!-- END_PHASE_8 -->

<!-- START_PHASE_9 -->
### Phase 9: Skill closure sweep — cross-participant and read-only skills

**Goal:** Cross-participant SKILL.md files and read-only skills gain the same closure contract.

**Components:**
- `skills/mpi-generic-diachronic/SKILL.md` — closes 4 substeps per event: `participant_row_assembly` (orchestrator), `idu_similarity_grouping` (LLM), `pattern_identification` (LLM), `cross_iv_contrast` (LLM); the manual's colour-by-similarity inspection is realised as the LLM's `idu_similarity_grouping` rather than a deterministic heuristic
- `skills/mpi-generic-synchronic/SKILL.md` — mpi-cross-analyst closes 2 substeps per (event × IV category × generic-IDU-of-interest) (`worksheet_assembly`, `isu_second_level_grouping`); generic-IDU-of-interest list comes from `generic_diachronic.pattern_identification` outputs
- `skills/mpi-global-synchronic/SKILL.md` — single substep, scoped per (generic-IDU × IV category); ISU 2nd Level of Abstraction preserved as a distinct column
- `skills/mpi-hypothesis/SKILL.md` — closes 3 LLM substeps: `evidence_extraction` per DV focus (extracts pattern variations from upstream artifacts grouped by IV level with full traceability); `candidate_drafting` per DV focus (drafts causal hypotheses framed against IV-level differences, citing evidence artifact paths); `weak_evidence_review` global (flags hypotheses with thin support given participant count, mirroring the manual's "only provides weak evidence" guidance)
- `skills/mpi-kappa/SKILL.md` — calibration utility (see Phase 13). Single operation `mpi-kappa calibrate --participant pNsN --stage <S>` runs an alternate-agent analysis on one chosen pair, computes κ, writes `analyses/independent/<scope>-<stage>.{json,md,prompt.json}` and `.mpi/kappa_calibration.jsonl`. Cross-participant skills warn but do not block on low/missing κ unless `--strict-kappa` is set.
- `skills/mpi-status/SKILL.md` — read-only; closure section explicitly states "no artifact close" but emits a `stage_phase: read` audit event for trace continuity

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

<!-- START_PHASE_13 -->
### Phase 13: Kappa calibration as setup evidence

**Goal:** Implement manual_kev.md's κ > 0.6 check as a **one-shot setup sanity check** (the manual's "an example … continue training until κ > .6"), not a per-run blocker. yolo runs proceed regardless; the result is recorded as evidence in the audit trail and surfaced as a warning if low.

**Components:**
- `skills/mpi-kappa/SKILL.md` rewritten as a calibration utility. One operation: `mpi-kappa calibrate --participant pNsN --stage diachronic|synchronic [--alternate-model <m>] [--alternate-prompt <variant>]`. Picks one (participant, stage) pair, runs the analysis a second time with the alternate agent, computes Cohen's κ via `scripts/kappa.py`, writes:
  - `analyses/independent/pNsN-<stage>.{json,md,prompt.json}` — the alternate analysis (with its own prompt-capture artifact for replay)
  - `.mpi/kappa_calibration.jsonl` — append-only history of calibration runs (one JSON line per run): `{participant, stage, primary_model, alternate_model, kappa, ci_lower, ci_upper, n_units, threshold: 0.6, outcome: "passed"|"low", timestamp, prompt_variant_notes}`. "Continue training until κ > .6" implies repeatable attempts; consumers read the last line as the current state.
  - One audit event `event.action: kappa_calibration` referencing both prompt-capture artifacts
- Cross-participant skills emit a `kappa_warning` audit event at stage start if `.mpi/kappa_calibration.jsonl` is missing for the upstream stage or its most-recent line's `outcome == "low"`. They proceed regardless unless `--strict-kappa` was passed at `/mpi all` invocation, in which case they error.
- `mpi-cross-analyst` agent prompt updated: read the last line of `.mpi/kappa_calibration.jsonl` if present and include its summary in its reasoning; do NOT block on it.
- `scripts/kappa.py` extended only if its current API doesn't accept the new artifact paths.

**Dependencies:** Phase 6 (mpi-analyst can produce per-substep artifacts that the alternate run also produces).

**Done when:** `mpi-kappa calibrate` runs end-to-end on a fixture, produces both independent analysis artifacts and `kappa_calibration.jsonl`, and emits a calibration audit event. A yolo run with no calibration completes successfully but emits a `kappa_warning` audit event at each cross-participant stage start. A yolo run with `--strict-kappa` and missing or low κ exits non-zero before any cross-participant artifact is produced. Verifies `doc-as-done.AC13.1`, `doc-as-done.AC13.2`, `doc-as-done.AC13.3`, `doc-as-done.AC13.4`.
<!-- END_PHASE_13 -->

## Additional Considerations

**Implementation scoping: 13 phases require two implementation plans.** The writing-plans skill caps implementation plans at 8 phases. Recommended split:

- **Plan 1 (Phases 1–8): Foundation and per-participant pipeline.** Builds the helper CLI (Phases 1–3), pins per-substep schemas and prompt-capture contract (Phases 4–5), updates the mpi-analyst agent and per-participant skills (Phases 6, 8). After this plan, transcript_prep + diachronic + synchronic run end-to-end on the new contract; cross-participant skills still use the old contract.
- **Plan 2 (Phases 7, 9–13): Cross-participant pipeline, kappa calibration, tests, docs.** Updates the mpi-cross-analyst agent (Phase 7 has no per-participant dependency beyond Phases 2/4/5) and cross-participant skills (Phase 9), sweeps anti-fabrication guards (Phase 10), adds E2E tests (Phase 11), reconciles docs (Phase 12), implements kappa as a one-shot setup calibration utility (Phase 13).

The split keeps each plan focused and within the 8-phase budget. Plan 1 leaves the pipeline in a working but incomplete state — the cross-participant skills still pass JSON over the wire as today, and there is no κ gate — so users should not run `/mpi all` between the two plans; only `/mpi diachronic` and `/mpi synchronic` are upgraded after Plan 1.

**Methodology lineage and fidelity check.** A prior draft imported substep names from the µ-PATH pipeline (Wordweaver-EH/upath), which encodes Valenzuela-Moguillansky & Vásquez-Rosati 2019 — a different methodology that produces phases/sub-phases, DU/refined-DU, and SSS/GSS outputs. manual_kev.md is a deliberately simplified variant that omits sub-phase identification and uses IDU + ISU + ISU 2nd Level of Abstraction as its analytic columns. The current substep map is named after the operations manual_kev.md prescribes verbatim. Diff against the prior draft: dropped `diachronic.phases`, `diachronic.du`, `diachronic.refined_du`; renamed `synchronic.{groups,isus,structure}` → `synchronic.{theme_grouping_within_idu, isu_naming, isu_second_level_grouping}` and changed iteration from "per phase" to "per IDU"; replaced `generic_diachronic.{compare, gdus, structure}` with manual-native `participant_row_assembly`/`idu_similarity_grouping`/`pattern_identification`/`cross_iv_contrast`; replaced `generic_synchronic.{sss_grouping, gss_definition}` with `select_generic_idus_of_interest`/`worksheet_assembly`/`isu_second_level_grouping`; split `hypothesis` into `evidence_extraction`/`candidate_drafting`/`weak_evidence_review`; introduced `mpi-kappa calibrate` as a one-shot setup utility (warning-by-default, opt-in `--strict-kappa`) — explicitly **not** a per-run gate, per the manual's "an example … continue training until κ > .6" wording.

**Yolo mode auditability.** In `/mpi all --yolo` execution with no human in the loop, every state transition must be reconstructable from on-disk artifacts. Specific yolo-mode requirements:

- **Blocked-state audit events.** When a substep is skipped (because its upstream is `pending` or `failed`), the orchestrator emits a `stage_blocked` audit event with `mpi.blocked_reason: "upstream_pending|upstream_failed|kappa_low_strict|..."` and the upstream's `event_id`. Absence-of-artifact alone is not auditable; the blocked event is the trace.
- **Run identity.** Each `/mpi all` invocation generates or reuses `.mpi/run_id` (UUID4). The id propagates as `trace_id` on every event for the run. Resumed runs reuse the existing `run_id`; new runs after `git clean` create a new one.
- **Dirty-worktree behaviour.** Helper `close` refuses to run if `git status --porcelain` shows uncommitted files outside `analyses/` and `.mpi/` at start; logs `dirty_worktree_refused` and exits non-zero. This prevents commits that accidentally include unrelated work.
- **Commit-failure recovery.** If `git commit` fails after audit + manifest succeed (rare; e.g., pre-commit hook rejects), the helper emits a `commit_failed` audit event, rolls back the manifest write (the on-disk `.mpi/project.json` reverts to its pre-call state via the kept tmp), and exits non-zero. The artifact files remain on disk but unreferenced; the next `/mpi all` will detect them via the manifest `status: pending` and re-close them.
- **Partial prompt-artifact handling.** If a subagent writes the analysis JSON+md but crashes before writing the prompt artifact, the helper's pre-check rejects the close (`prompt_artifact_missing`). The partial files stay on disk for human inspection; the manifest stays `pending`. Re-running the substep produces a fresh complete triple.
- **Concurrent close races.** The helper acquires `.mpi/close.lock` via `fcntl.flock` (POSIX) / `msvcrt.locking` (Windows) for the duration of audit+manifest+commit; a second `close` invocation while one is in flight blocks up to 30s, then errors `concurrent_close_blocked`. The lock file holds the holder's PID, hostname, and ISO timestamp. On acquire-attempt the helper reads the existing lock and reclaims **only if the PID is verifiably not running** on the same host (POSIX: `os.kill(pid, 0)` raises ESRCH; Windows: `OpenProcess` returns null) — emits `stale_lock_reclaimed`. Long-running closes never trigger reclaim regardless of age. If the lock's hostname differs from the current host, the helper refuses to reclaim and errors `cross_host_lock_unresolvable` (a shared `.mpi/` directory across hosts is unsupported). A timestamp older than 60 minutes is recorded as a stderr warning by the *waiting* process (`WARNING: lock held by PID <p> on <host> for >60min`) — not written to `.mpi/audit.jsonl`, since the audit-write itself is serialized by the same lock. The holder, when it eventually closes, includes its full duration in its `stage_completed` audit event so the long run is still observable on disk after the fact. Manual recovery path `mpi_step.py unlock --reason ...` overrides safety checks; emits `manual_unlock` with the reason.
- **Artifact integrity pinning.** Each audit event for a substep close records `mpi.artifact_sha256` — a sorted map of `{path: sha256}` for every artifact closed. Future re-renders or replays can detect silent file tampering. Manifest's `output_paths` carry the same hashes alongside their paths.
- **Branch + HEAD verification.** Helper records `git.branch` and `git.head_sha` in every audit event. At resume, `mpi_step.py close` verifies the current HEAD matches the manifest's last recorded commit SHA; mismatch emits `head_mismatch` and refuses to close until the user resolves (e.g., post-rebase or after manual cherry-pick).
- **Reconfiguration reset.** If the user re-runs `mpi-init` (or invokes a future `mpi reconfigure`) while a manifest exists, the operation refuses by default. With `--force-reconfigure`, every substep status resets to `pending` and a `study_reconfigured` audit event is appended with both the old and new `study: {ivs, dvs}` payloads. The prior `analyses/` tree is moved aside to `analyses.archived-<timestamp>/` rather than deleted.

**Shell-quoting risk.** Subagents invoking `python scripts/mpi_step.py close --units-json '<huge json blob>'` would be fragile on Windows. Mitigation: helper accepts `--units-json -` to read from stdin, and accepts `--units-json path/to/file.json` to read from disk. Agent prompt instructs the latter (write `analyses/pNsN-<stage>.units.json` first, then pass the path).

**JSONL corruption from partial writes.** Each append is a single `open('a'); write(line); fsync(); close()` with the line constructed entirely in memory. `mpi_step.py render` flags malformed lines as `MALFORMED:<lineno>` rather than aborting the render — keeps human visibility intact even when the JSONL has a damaged tail.

**Helper as single point of failure.** It's stdlib-only (~300 LOC estimated), runs locally, has unit tests that exercise it without LLM calls, and is the same Python interpreter that already runs `kappa.py`. No new install step.

**`/mpi all` orchestration interaction.** The orchestrator (Claude in the main loop, executing the `mpi` command's routing logic) is itself an actor and must also call `mpi_step.py close` for orchestration-level events (cascade resets, stage dispatches). Phase 5 enumerates the orchestrator's close-points.

**Backwards compatibility.** Pre-release per the repo CLAUDE.md — edits land in `microphenomenograph/1.0.0/` directly with no shim. Any extant `runs/*/` directories from prior pipeline runs are not migrated; users start fresh.

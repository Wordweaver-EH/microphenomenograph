# Test Requirements: Documentation-as-Done Contract (Phases 1–6)

**Source design:** `docs/design-plans/2026-05-17-doc-as-done.md` (`fb65db5`)
**Implementation plan:** `docs/implementation-plans/2026-05-17-doc-as-done/phase_{01..06}.md`
**Slug:** `doc-as-done`
**Last updated:** 2026-05-18

Scope: 6 phases, 34 acceptance-criteria leaf items extracted from the "Acceptance Criteria Coverage" sections of each phase. AC28.3–.5 and AC29.4 are explicitly deferred to Plan 2 and are NOT in scope here.

---

## Automated Test Coverage Required

| AC ID | Case | Description | Implementing Phase | Verifying Phase | Test File | Test Class::Method |
|---|---|---|---|---|---|---|
| doc-as-done.AC1.1 | Success | Successful close emits full 5-event sequence (close_attempted → artifacts_validated → audit_appended → manifest_replaced → git_commit_succeeded) sharing one `close_id`; SHA recorded post-commit. | 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseHappyPath::test_close_writes_audit_events`, `TestCloseHappyPath::test_close_events_share_close_id` |
| doc-as-done.AC1.2 | Failure | git commit failure emits `git_commit_failed` + `manifest_rolled_back`; manifest reverts; substep stays `pending`. | 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseFailures::test_manifest_unchanged_on_failure` |
| doc-as-done.AC1.3 | Failure | Audit-append failure before manifest mutation leaves manifest untouched; exits non-zero. | 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseFailures::test_manifest_unchanged_on_failure` |
| doc-as-done.AC1.4 | Success | Manifest records `close_id`, `parent_head_sha`, `artifact_shas`, `expected_action`; NOT the commit's own SHA. | 2 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC1_6_AgentSelfPersistEndToEnd::test_agent_workflow_writes_artifacts_then_closes` (asserts `git_commit_sha not in substep_entry`) |
| doc-as-done.AC1.5 | Success | `done` iff manifest=done AND audit has matching `git_commit_succeeded` AND commit SHA resolves with matching tree contents. | 2 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC1_6_AgentSelfPersistEndToEnd::test_agent_workflow_writes_artifacts_then_closes` |
| doc-as-done.AC1.6 | Success | mpi-analyst writes `analyses/pNsN-<stage>.json/.md` itself before invoking helper. | 6 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC1_6_AgentSelfPersistEndToEnd::test_agent_workflow_writes_artifacts_then_closes` |
| doc-as-done.AC1.7 | Failure | Subagent that cannot write artifacts returns `ERROR <transcript> <stage>: <reason>`; never substitutes analysis content. | 6 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC1_6_AgentSelfPersistEndToEnd::test_agent_returning_error_instead_of_analysis_content` |
| doc-as-done.AC2.1 | Success | `mpi_step.py close` end-to-end succeeds in a clean repo with valid inputs. | 1, 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseHappyPath::test_close_criteria_grouping_succeeds` |
| doc-as-done.AC2.2 | Success | `--help` for top-level, `close`, and `init` print usage with all required/optional flags. | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCLIHelp::test_top_level_help`, `::test_close_help`, `::test_init_help` |
| doc-as-done.AC2.3 | Failure | Missing `--artifact`, missing `.mpi/project.json`, or empty artifact file exits non-zero with a named error and zero state mutation. | 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseFailures::test_missing_artifact_fails`, `::test_missing_manifest_fails` |
| doc-as-done.AC3.1 | Success | Manifest writes use `.tmp` → `os.replace` (atomic to concurrent readers). | 2 | 1, 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestAtomicWrite::test_write_is_atomic_no_tmp_leftover`, `::test_write_overwrites_existing` |
| doc-as-done.AC3.2 | Failure | Simulated `os.replace` failure leaves manifest at previous state; `.tmp` unlinked. | 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseFailures::test_manifest_unchanged_on_failure` |
| doc-as-done.AC3.3 | Success | `mpi_step.py render` is idempotent — byte-identical on re-run. | 3 | 3 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestRender::test_render_idempotent` |
| doc-as-done.AC4.1 | Success | Well-formed units payload (all required fields, no unknown keys, correct types) is accepted. | 1, 4 | 1, 4 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestValidateUnits::test_accepts_known_stage`, `TestSchemaAcceptsValid::test_criteria_grouping_valid`, `::test_criteria_revision_valid`, `::test_synchronic_theme_grouping_valid` |
| doc-as-done.AC4.2 | Failure | `title` instead of `idu_name`, or `utterance_lines` instead of `utterance_numbers`, rejected with named error. | 4 | 4 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestSchemaDriftNames::test_title_instead_of_idu_name_rejected`, `::test_utterance_lines_instead_of_utterance_numbers_rejected`, `::test_isu_2nd_level_instead_of_isu_second_level_rejected` |
| doc-as-done.AC4.3 | Failure | `confidence` outside 1–5, non-boolean `flag_for_review`, or null `hinge_to_next` on a non-last IDU rejected. | 4 | 4 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestSchemaRangeErrors::test_confidence_out_of_range`, `::test_flag_for_review_non_bool`, `::test_hinge_null_on_non_last_idu` |
| doc-as-done.AC5.1 | Success | `render` reads `.mpi/audit.jsonl` and produces `.mpi/reasoning.log` with one line per event in canonical format. | 3 | 3 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestRender::test_render_produces_reasoning_log`, `::test_render_includes_commit_sha` |
| doc-as-done.AC5.2 | Failure-tolerance | Malformed JSONL line emits `MALFORMED:<lineno>` placeholder; render does not abort. | 3 | 3 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestRender::test_render_malformed_line_placeholder` |
| doc-as-done.AC6.1 | Success | `agents/mpi-analyst.md` `tools:` line declares `Read, Write, Bash`. | 6 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC6_1_AgentTools::test_mpi_analyst_declares_write_bash` |
| doc-as-done.AC6.2 | Success | `agents/mpi-analyst.md` contains "Persistence (mandatory before returning)" naming exact files and `mpi_step.py close` invocation. | 6 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC6_2_PersistenceSection::test_persistence_section_exists`, `::test_persistence_section_names_close_invocation`, `::test_persistence_return_value_format` |
| doc-as-done.AC6.3 | Success | Every SKILL.md contains "Closure (mandatory)" naming responsible actor and closing artifacts. | 6 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC6_3_SkillClosureSections::test_diachronic_skill_has_closure`, `::test_synchronic_skill_has_closure` |
| doc-as-done.AC10.1 | Success | Manifest `stages.<stage>` has `substeps: {<substep>: {status, output_paths[]}}`; stage status derived (all-done/any-flagged/any-error). | 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseHappyPath::test_close_updates_manifest_substeps` |
| doc-as-done.AC10.2 | Success | Closing `diachronic.idu_naming_ordering` rejected when `diachronic.criteria_revision` is not `done` (substep DAG enforced). | 2 | 2 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseFailures::test_dag_prereq_enforced` |
| doc-as-done.AC10.3 | Success | Each (stage, substep) has its own schema in `_mpi_schemas.py`; helper invokes the right one. | 4 | 4 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestSchemaDriftNames::test_isu_second_level_not_required_at_theme_grouping`, `TestSchemaAcceptsValid::*` |
| doc-as-done.AC10.4 | Success | mpi-analyst Persistence section enumerates all 6 substeps (3 diachronic + 3 synchronic) with paths and manual-native names; no deprecated names. | 6 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC6_2_PersistenceSection::test_persistence_section_names_six_substeps`, `TestAC10_4_SubstepEnumeration::test_no_deprecated_substep_names` |
| doc-as-done.AC11.1 | Success | LLM-invoking substep close has matching `<scope>-<stage>.<substep>.prompt.json` artifact conforming to schema_version 2. | 5 | 5 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestPromptArtifactSchema::test_valid_prompt_artifact_accepted`, `TestClosePromptArtifactEnforcement::test_valid_prompt_artifact_accepted_in_close` |
| doc-as-done.AC11.2 | Failure | LLM substep close without `--prompt-artifact` rejected with named error. | 5 | 2, 5 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestCloseFailures::test_llm_substep_requires_prompt_artifact`, `TestClosePromptArtifactEnforcement::test_llm_substep_without_prompt_artifact_rejected` |
| doc-as-done.AC11.3 | Failure | Malformed `prompt.json` (missing keys, wrong `schema_version`, or `agent_file_sha256` mismatch) rejected at pre-check; manifest unchanged. | 5 | 5 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestPromptArtifactSchema::test_wrong_schema_version_rejected`, `::test_missing_actor_fields_rejected`, `::test_missing_cache_tokens_rejected`, `TestClosePromptArtifactEnforcement::test_malformed_prompt_artifact_rejected` |
| doc-as-done.AC12.1 | Success | Synchronic substeps iterate per IDU within participant; no deprecated substep names (`diachronic.phases`, `diachronic.du`, `diachronic.refined_du`, `generic_synchronic.sss_grouping`, `generic_synchronic.gss_definition`); names match `manual_kev.md`. | 6 | 6 | `tests/test_mpi_analyst_contract.py` | `TestAC12_1_ManualNativeSubstepNames::test_synchronic_skill_mentions_per_idu`, `::test_synchronic_skill_preserves_isu_second_level_column`, `::test_diachronic_skill_no_sub_phase_identification` |
| doc-as-done.AC28.1 | Success | Every generative substep schema requires non-empty `utterance_refs` array on each analytic unit. | 4 | 4, 6 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py`, `tests/test_mpi_analyst_contract.py` | `TestSchemaUtteranceRefs::test_empty_utterance_refs_rejected`, `TestAC28_1_UtteranceRefsRequirement::test_agent_documents_utterance_refs` |
| doc-as-done.AC28.2 | Failure | Analytic unit missing `utterance_refs` (or empty array) rejected with `missing_span_refs` naming the offending unit. | 4 | 4 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestSchemaUtteranceRefs::test_missing_utterance_refs_rejected`, `::test_empty_utterance_refs_rejected` |
| doc-as-done.AC33.1 | Failure | `init --run <dir>` inside non-empty git worktree errors `run_inside_active_repo` with prescribed message. | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestInitActiveRepoNesting::test_init_inside_nonempty_repo_fails_by_default` |
| doc-as-done.AC33.2 | Success | `--allow-active-repo-nested` proceeds; manifest records `study.run_repo_mode = "nested_in_active"`. | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestInitActiveRepoNesting::test_init_with_allow_flag_succeeds` |
| doc-as-done.AC33.3 | Success | Default mode writes `study.run_repo_mode = "dedicated"`; sets local `core.autocrlf false`, `core.eol lf` (never global). | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestInitDedicatedRepo::test_init_in_empty_dir_succeeds`, `::test_init_sets_autocrlf_false`, `::test_init_manifest_records_dedicated_mode` |
| doc-as-done.AC33.4 | Success | Sets local `core.hooksPath = .git/hooks-disabled` and creates that empty directory. | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestInitDedicatedRepo::test_init_sets_hooks_path` |
| doc-as-done.AC33.5 | Success | Sets local `commit.gpgsign false`. | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestInitDedicatedRepo::test_init_sets_gpgsign_false` |
| doc-as-done.AC33.6 | Failure | Without global or local `user.name`/`user.email`, init fails with `git_identity_unset`; never invents identity. | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestInitIdentityRequired::test_init_fails_without_identity` |
| doc-as-done.AC33.7 | Success | Helper never runs `git push` or `git remote add`. | 1 | 1 | `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | (implicit via absence of remote in `TestInitDedicatedRepo` flow; no `git push`/`git remote add` calls in `mpi_step.py` source — grep-style assertion recommended) |

---

## Supporting Tests (not directly mapped to a leaf AC)

| Test File | Test Class::Method | Supports |
|---|---|---|
| `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestAtomicWrite::test_write_creates_file`, `::test_write_creates_parent_dirs` | AC3.1 primitive |
| `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestAppendJsonl::test_append_creates_and_appends`, `::test_append_idempotent_under_re_read` | AC5.1 primitive |
| `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestLoadOrCreateRunId::test_creates_uuid_if_absent`, `::test_returns_existing_if_present` | run_id stability |
| `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestValidateUnits::test_rejects_unknown_stage`, `::test_rejects_non_dict` | AC4 stub baseline |
| `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestSchemaConvergenceField::test_criteria_revision_missing_convergence`, `::test_criteria_revision_bad_decision` | `diachronic.criteria_revision` convergence field (design constraint behind AC4) |
| `microphenomenograph/1.0.0/scripts/test_mpi_step.py` | `TestRender::test_render_filter_by_participant` | render filtering (AC5 functional surface) |
| `tests/test_mpi_analyst_contract.py` | `TestAntiFabricationClause::test_anti_fabrication_in_agent` | AC1.7 documentation backing |

---

## Human Verification Required

| Item | Why Manual | Notes |
|---|---|---|
| AC33.7 negative assertion (no `git push`/`git remote add`) | Negative absence is awkward to test from inside the helper. | Recommend a grep-style structural test: `grep -E "git (push|remote add)" microphenomenograph/1.0.0/scripts/mpi_step.py` returns no results. |
| End-to-end pipeline run on a real OSF transcript producing ~5 closes through `diachronic` substeps with real git history. | Smoke test catches integration regressions invisible to unit tests. | Manual `/mpi init --run <tmpdir>` then drive `mpi-analyst` through `diachronic.criteria_grouping` → `criteria_revision` → `idu_naming_ordering`. Verify `git log` shows 3 commits and `python scripts/mpi_step.py render` produces a well-formed `reasoning.log`. |
| AC11.3 cross-machine SHA path resolution | Behaviour when `agent_file_path` is absent on current machine (helper silently skips SHA check) is environment-dependent. | Manually move/rename the agent file, confirm close succeeds (skip) vs. confirm close fails when file present-but-modified. |
| AC33.6 with global identity present but local unset | Test uses monkeypatch to force false; real-world interaction with `git config --global` not exercised. | On a machine with global identity configured, confirm init succeeds without local config. On a machine without global, confirm failure. |
| Concurrent close attempt (lock contention) | `.mpi/close.lock` semantics are part of the design but not explicit in Phases 1–6 test plans. | Two parallel `mpi_step.py close` invocations — second should fail fast. |

---

## Out of Scope (deferred to Plan 2)

- doc-as-done.AC28.3 (`span_out_of_range`)
- doc-as-done.AC28.4 (`span_excerpt_mismatch`)
- doc-as-done.AC28.5 (cross-stage span chain)
- doc-as-done.AC29.4 (offset registry schema)
- doc-as-done.AC12.3 (`temporal_order_within_idu` orchestrator re-close)
- doc-as-done.AC12.4 (`concurrent_with_adjacent_idu` merge flag)
- `mpi-cross-analyst` portions of AC6.1 and AC6.2

These should NOT block Phase 1–6 sign-off.

---

## Run Commands

```bash
# Phase 1–5 unit tests (script-local)
pytest microphenomenograph/1.0.0/scripts/test_mpi_step.py -v

# Phase 6 contract + end-to-end tests
pytest tests/test_mpi_analyst_contract.py -v

# Full suite
pytest microphenomenograph/1.0.0/scripts/test_mpi_step.py tests/ -v
```

## AC Index (count check)

34 leaf ACs in scope, distributed:

- AC1: 7 (1.1–1.7)
- AC2: 3 (2.1–2.3)
- AC3: 3 (3.1–3.3)
- AC4: 3 (4.1–4.3)
- AC5: 2 (5.1, 5.2)
- AC6: 3 (6.1–6.3)
- AC10: 4 (10.1–10.4)
- AC11: 3 (11.1–11.3)
- AC12: 1 (12.1)
- AC28: 2 (28.1, 28.2)
- AC33: 7 (33.1–33.7)

Total: 38 leaf items listed in the coverage table above (counts include AC4.1 and AC11.2 which appear in two phases; AC28.1 spans Phases 4 and 6).

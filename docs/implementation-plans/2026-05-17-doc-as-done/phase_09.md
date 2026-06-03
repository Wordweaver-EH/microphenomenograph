# Documentation-as-Done Contract — Plan 2 Implementation Plan

**Goal:** Add "Closure (mandatory)" subsections to every remaining SKILL.md file that lacks one: all cross-participant skills (mpi-generic-diachronic, mpi-generic-synchronic, mpi-global-synchronic, mpi-hypothesis, mpi-status), plus the Phase 8 remainder (mpi-init, mpi-transcript-prep). Create `skills/mpi-irr/SKILL.md` (renamed from mpi-kappa). Remove hand-specified manifest mutation prose, log line format, and git commit message format from any file that has them.

**Architecture:** Append-only edits to existing SKILL.md files; one new skills directory. No code changes in this phase — pure documentation contract work.

**Tech Stack:** Markdown SKILL.md files; pytest for structural assertions.

**Scope:** Phase 9 of 13 from original design (Plan 2, phase 2 of 6). Also covers the Phase 8 remainder (mpi-init + mpi-transcript-prep Closure subsections) which was not landed in Plan 1.

**Codebase verified:** 2026-06-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC6.3: Every SKILL.md has a Closure subsection
- **doc-as-done.AC6.3 Success:** Every SKILL.md contains a "Closure (mandatory)" subsection naming the responsible actor and the artifacts that close the step.

### doc-as-done.AC6.4: Read-only skills explicitly declare no artifact close
- **doc-as-done.AC6.4 Success:** Read-only skills (`mpi-status` only — `mpi-irr` is NOT read-only; it produces alignment + agreement artifacts with bootstrap CIs) explicitly state "no artifact close" and emit a `stage_phase: read` audit event for trace continuity.

### doc-as-done.AC7.1: Old hand-written contracts removed
- **doc-as-done.AC7.1 Success:** No SKILL.md hand-specifies manifest mutation prose, log line format, or git commit message format — all three are owned by the helper.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Add Closure subsections to mpi-init and mpi-transcript-prep SKILL.md (Phase 8 remainder)

**Verifies:** doc-as-done.AC6.3, doc-as-done.AC7.1

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md`

**Implementation:**

**mpi-init/SKILL.md:** Append the following section at the end of the file. The manifest schema block in the existing file uses a legacy format (no `substeps`, no `study` block); do NOT rewrite the entire file — add only the Closure section. The schema reconciliation happens in Phase 12.

```markdown
## Closure (mandatory)

Each init substep closes its own four-part transaction via `mpi_step.py close`.
The orchestrator owns all three substeps (no LLM calls, no prompt artifact required
for `scan_transcripts` and `confirm_study_config`; `propose_study_config` is LLM-driven
when `study.config_provenance == "llm_proposed_user_confirmed"`).

| Substep | Actor | Artifacts | Notes |
|---------|-------|-----------|-------|
| `init.scan_transcripts` | orchestrator | `<manifest>.json` (initial write) | No prompt artifact. Records `study.transcripts[transcript_id].raw_sha256` for each transcript. |
| `init.propose_study_config` | orchestrator (LLM optional) | `init.propose_study_config.{json,md}` + `.prompt.json` when LLM path | Skipped entirely when `study.config_provenance` is `preregistered` or `user_specified`. |
| `init.confirm_study_config` | orchestrator | `init.confirm_study_config.json` (records final IV/DV) | Records `study.config_provenance` immutably; also records `study.calibration_transcript`. |

**Commit message format:** `mpi: orchestrator init.<substep> (<N>transcripts scanned)` or similar.

**Raw-immutability contract:** `hash_raw` is the first substep of `transcript_prep`, not of `init`. After `scan_transcripts` closes, the raw files under `transcripts/raw/` become the reference — any SHA mismatch at a subsequent close emits `raw_transcript_mutated` and exits non-zero.

**Study config provenance:** `study.config_provenance` is set at `init.confirm_study_config` and is immutable thereafter. Its value (`preregistered`, `user_specified`, `llm_proposed_user_confirmed`) is surfaced in every hypothesis output disclaimer.
```

**mpi-transcript-prep/SKILL.md:** Append the following at the end of the file. Do NOT rewrite the file; leave existing steps in place.

```markdown
## Closure (mandatory)

Each transcript-prep substep closes its own four-part transaction via `mpi_step.py close`.
The orchestrator owns all three substeps (no LLM calls, no prompt artifact for any).

| Substep | Actor | Artifacts | Notes |
|---------|-------|-----------|-------|
| `transcript_prep.hash_raw` | orchestrator | SHA256 entry in manifest | Marks raw file read-only. SHA recorded as `study.transcripts[transcript_id].raw_sha256`. |
| `transcript_prep.normalize` | orchestrator | `transcripts/normalized/<transcript_id>.txt`, `transcripts/diff/<transcript_id>.diff` | Diff from raw → normalized is committed alongside for reviewability. |
| `transcript_prep.register_offsets` | orchestrator | `transcripts/offsets/<transcript_id>.json` | Maps normalized line numbers to raw byte ranges. SHA recorded in manifest. |

**Commit message format:** `mpi: orchestrator transcript_prep.<substep> <transcript_id>`

**Raw-immutability contract:** The raw file at `transcripts/raw/<transcript_id>.txt` is
never overwritten. `hash_raw` makes it read-only (`chmod 0444` on POSIX; read-only attribute
on Windows). Any subsequent close that detects SHA mismatch on the raw file exits with
`raw_transcript_mutated`. The normalised file is a derived artifact; only the raw is the
ground truth for `utterance_refs`.

**Note (divergence from pre-Plan-1 behaviour):** The pre-existing SKILL.md above specifies
"Write cleaned transcript back to the same path (overwrite)." This is superseded by the
new contract: the normalised output goes to `transcripts/normalized/<transcript_id>.txt`;
the raw is never overwritten. Executors should follow the Closure section, not the old
"Output" section above it.
```

**Also: remove hand-specified commit messages.** Scan both files for any prose like `git add ... && git commit -m "..."` or `git commit -m "mpi: ..."` outside of a Closure section. If found, delete those lines — the helper owns the commit format.

**Commit:**
```bash
git add microphenomenograph/1.0.0/skills/mpi-init/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md
git commit -m "feat: add Closure subsections to mpi-init and mpi-transcript-prep SKILL.md (Phase 8 remainder)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add Closure subsections to mpi-generic-diachronic and mpi-generic-synchronic

**Verifies:** doc-as-done.AC6.3, doc-as-done.AC7.1

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md`

**Implementation:**

Read both files first to locate the end of the file. Append to each:

**mpi-generic-diachronic/SKILL.md** — append:
```markdown
## Closure (mandatory)

Each generic-diachronic substep closes its own four-part transaction via `mpi_step.py close`.
The orchestrator closes `participant_row_assembly`; `mpi-cross-analyst` closes the three LLM substeps.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `generic_diachronic.participant_row_assembly` | orchestrator | `event<E>-cat-<C>-generic_diachronic.participant_row_assembly.{json,md}` | `event<E>-cat-<C>` | Mechanical reshape; no LLM, no prompt artifact |
| `generic_diachronic.idu_similarity_grouping` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-generic_diachronic.idu_similarity_grouping.{json,md,prompt.json}` | `event<E>-cat-<C>` | LLM analytic judgment; colour/group label per IDU cell with rationale |
| `generic_diachronic.pattern_identification` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-generic_diachronic.pattern_identification.{json,md,prompt.json}` | `event<E>-cat-<C>` | Extracts common ordered patterns across IV-grouped rows |
| `generic_diachronic.cross_iv_contrast` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-generic_diachronic.cross_iv_contrast.{json,md,prompt.json}` | `event<E>-cat-<C>` | Explicit comparison of how patterns differ by IV level |

**Prerequisite gate:** `generic_diachronic.*` is blocked until all transcripts for the event have `diachronic.*` and `synchronic.*` all `done` with no pending `temporal_order_within_idu` or `concurrent_with_adjacent_idu` flags. The helper enforces this via `prereq_unsatisfied`.

**Commit message format:** `mpi: <actor> generic_diachronic.<substep> event<E>-cat-<C> (<N>units <K>flagged)`
```

**mpi-generic-synchronic/SKILL.md** — append:
```markdown
## Closure (mandatory)

Each generic-synchronic substep closes its own four-part transaction via `mpi_step.py close`.
The orchestrator closes `worksheet_assembly`; `mpi-cross-analyst` closes the two LLM substeps.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `generic_synchronic.select_generic_idus_of_interest` | mpi-cross-analyst (LLM) | `event<E>-generic_synchronic.select_generic_idus_of_interest.{json,md,prompt.json}` | `event<E>` | Reads pattern/cross-contrast outputs; selects generic-IDUs for downstream worksheets |
| `generic_synchronic.worksheet_assembly` | orchestrator | `event<E>-cat-<C>-gidu<G>-generic_synchronic.worksheet_assembly.{json,md}` | `event<E>-cat-<C>-gidu<G>` | Mechanical assembly per (event × IV category × selected generic-IDU); no LLM, no prompt artifact |
| `generic_synchronic.isu_second_level_grouping` | mpi-cross-analyst (LLM) | `event<E>-cat-<C>-gidu<G>-generic_synchronic.isu_second_level_grouping.{json,md,prompt.json}` | `event<E>-cat-<C>-gidu<G>` | ISU 2nd Level of Abstraction preserved as distinct column |

**Prerequisite gate:** `generic_synchronic.*` is blocked until the matching `generic_diachronic.*` outputs for the same (event, IV category) are `done`.

**Commit message format:** `mpi: <actor> generic_synchronic.<substep> <scope> (<N>units <K>flagged)`
```

**Also:** Remove any hand-specified `git commit -m "..."` lines in these files outside a Closure section.

**Commit:**
```bash
git add microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md
git commit -m "feat: add Closure subsections to mpi-generic-diachronic and mpi-generic-synchronic SKILL.md"
```
<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->

<!-- START_TASK_3 -->
### Task 3: Add Closure subsections to mpi-global-synchronic and mpi-hypothesis

**Verifies:** doc-as-done.AC6.3, doc-as-done.AC7.1

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`

**Implementation:**

**mpi-global-synchronic/SKILL.md** — append:
```markdown
## Closure (mandatory)

The single global-synchronic substep closes its own four-part transaction via `mpi_step.py close`.
The `mpi-cross-analyst` subagent owns persistence.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `global_synchronic` | mpi-cross-analyst (LLM) | `gidu<G>-cat-<C>-global_synchronic.{json,md,prompt.json}` | `gidu<G>-cat-<C>` | ISU 2nd Level of Abstraction preserved as a distinct column |

**Prerequisite gate:** `global_synchronic.*` is blocked until `generic_synchronic.*` is `done` for every relevant (event × IV category × generic-IDU) triple.

**Commit message format:** `mpi: mpi-cross-analyst global_synchronic gidu<G>-cat-<C> (<N>units <K>flagged)`
```

**mpi-hypothesis/SKILL.md** — append:
```markdown
## Closure (mandatory)

Each hypothesis substep closes its own four-part transaction via `mpi_step.py close`.
All three are LLM substeps; `mpi-cross-analyst` owns persistence for all.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `hypothesis.evidence_extraction` | mpi-cross-analyst (LLM) | `hypotheses/dv-<focus>.evidence.{json,md,prompt.json}` | `dv-<focus>` | One per DV focus; gathers pattern variations from all upstream sources |
| `hypothesis.candidate_drafting` | mpi-cross-analyst (LLM) | `hypotheses/dv-<focus>.candidates.{json,md,prompt.json}` | `dv-<focus>` | Drafts candidate mechanism hypotheses with claim-level evidence + `raw_span_refs`; mandatory `disclaimer` field |
| `hypothesis.weak_evidence_review` | mpi-cross-analyst (LLM) | `hypotheses/review_summary.{json,md,prompt.json}` | `global` | Flags thin-support hypotheses and unsupported causal language |

**Prerequisite gate:** `hypothesis.evidence_extraction` is blocked until `generic_diachronic.*`, `generic_synchronic.*`, AND `global_synchronic.*` are all `done`.

**Disclaimer mandate:** Every `hypothesis.candidate_drafting` artifact MUST carry this verbatim field:
```
"disclaimer": "These are generative conjectures inferred from qualitative pattern variation across IV levels in a small sample. They are not causal estimates from a hypothesis test and should not be reported as such."
```
The schema validator enforces this field's presence.

**Commit message format:** `mpi: mpi-cross-analyst hypothesis.<substep> <scope> (<N>units <K>flagged)`
```

**Commit:**
```bash
git add microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md
git commit -m "feat: add Closure subsections to mpi-global-synchronic and mpi-hypothesis SKILL.md"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Create `skills/mpi-irr/` (rename from mpi-kappa) and add Closure to mpi-status

**Verifies:** doc-as-done.AC6.3, doc-as-done.AC6.4, doc-as-done.AC7.1

**Files:**
- Create: `microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md` (new directory + file)
- Modify: `microphenomenograph/1.0.0/skills/mpi-status/SKILL.md`

**Implementation:**

**Create `microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md`:**

The mpi-kappa skill is being renamed to mpi-irr (Phase 13 will fill the body with the full IRR calibration logic). Create the new directory and a SKILL.md shell that:
1. Has the correct frontmatter (`name: mpi-irr`, `description: ...`)
2. Has a Closure section enumerating the three irr_calibration substeps
3. Marks the body as "Phase 13 fills this" so the executor knows the body is incomplete

```markdown
---
name: mpi-irr
description: Use when running /mpi-irr calibrate — runs alternate-agent re-analysis for a calibration transcript, aligns categories via LLM, computes Krippendorff α + Cohen κ + αU + ARI with bootstrap 95% CIs. Writes structured record to .mpi/irr_calibration.jsonl.
user-invocable: true
---
# mpi-irr

> **Implementation note (Phase 13):** The full operational body of this skill — the
> calibration workflow, alternate-agent dispatch, alignment substep, and agreement
> computation — is implemented in Phase 13. This file contains only the Closure contract
> and structural outline. Do not invoke this skill until Phase 13 is complete.

## Operation

`mpi-irr calibrate --transcript <pNsN> --stage diachronic|synchronic`

Runs an automatic inter-rater reliability (IRR) check for the given calibration transcript
and stage. Three steps:
1. `irr_calibration.independent_analyst` — re-runs the stage's substep DAG through a fresh
   `mpi-cross-analyst` (or `mpi-analyst` for per-transcript stages) in the `analyses/independent/`
   directory.
2. `irr_calibration.alignment` — a fresh `mpi-cross-analyst` subagent proposes a category
   mapping between primary and alternate with per-pair confidence + rationale.
3. `irr_calibration.agreement_computation` — orchestrator builds the union-of-categories
   coincidence matrix and computes four metrics (α, κ, αU, ARI) with 95% bootstrap CIs
   (N=5000). Appends one structured record to `.mpi/irr_calibration.jsonl`.

Phase 13 implements `scripts/irr.py` which backs the agreement computation.

## Closure (mandatory)

`mpi-irr` is NOT a read-only skill. It produces alignment and agreement artifacts.

| Substep | Actor | Artifacts | Scope | Notes |
|---------|-------|-----------|-------|-------|
| `irr_calibration.independent_analyst` | mpi-cross-analyst or mpi-analyst (LLM) | `analyses/independent/<scope>-<stage>.<substep>.{json,md,prompt.json}` for every substep of the shadowed stage | per-substep scope mirrors primary | Re-runs the full stage DAG through the alternate agent |
| `irr_calibration.alignment` | mpi-cross-analyst (LLM) | `analyses/irr_calibration.alignment.{json,md,prompt.json}` | `global` | In assisted mode: user accepts/edits the proposed mapping. In yolo: auto-accepted, emits `irr_alignment_auto_accepted` audit event |
| `irr_calibration.agreement_computation` | orchestrator | record appended to `.mpi/irr_calibration.jsonl` | `global` | Mechanical computation; no LLM, no prompt artifact. Writes four metrics with bootstrap CIs |

**Cross-participant warning gate:** Skills that follow IRR calibration in the pipeline
(`mpi-generic-diachronic`, etc.) emit an `irr_warning` audit event at stage start if the
most-recent IRR record's α CI lower bound is below 0.6 or no IRR record exists. They proceed
unless `--strict-irr` is passed, in which case they exit with a named ERROR.
```

**Modify `mpi-status/SKILL.md`** — append:
```markdown
## Closure (mandatory)

`mpi-status` is a **read-only skill**. It produces no artifact and performs no close.

However, it MUST emit a read-only audit event for trace continuity:
```bash
python scripts/mpi_step.py close \
  --actor orchestrator \
  --stage status \
  --substep status_read \
  --scope global \
  --status read \
  --reason "status read" \
  --run-dir .
```
The `--status read` flag causes `mpi_step.py` to emit a `stage_phase: read` audit event
without writing any artifact, mutating the manifest, or creating a git commit. This keeps
the audit trail complete even for read-only operations.
```

**Commit:**
```bash
git add microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md
git add microphenomenograph/1.0.0/skills/mpi-status/SKILL.md
git commit -m "feat: create mpi-irr SKILL.md shell and add read-only Closure to mpi-status"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Add `--status read` mode to `mpi_step.py` for read-only audit events

**Verifies:** doc-as-done.AC6.4

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

The current `close` verb's `--status` argument accepts `done` and `flagged` only. `mpi-status/SKILL.md` (Task 4 of this phase) instructs the orchestrator to emit a `stage_phase: read` audit event without writing artifacts, mutating the manifest, or creating a git commit.

Add `"read"` as a valid `--status` value. When `--status read` is passed to `mpi_step.py close`:

1. **Skip all pre-checks** that require artifacts to exist (no artifacts for a read-only event)
2. **Emit a single audit event** with `event.action: "stage_read"` and `mpi.stage_phase: "read"` to `.mpi/audit.jsonl`
3. **Do NOT** write any artifact, mutate the manifest, or create a git commit
4. Exit 0

The event schema:
```json
{
  "event_id": "<UUID4>",
  "@timestamp": "<RFC3339 UTC>",
  "trace_id": "<run_id>",
  "span_id": "<UUID4>",
  "actor": {"kind": "orchestrator", "name": "orchestrator"},
  "event": {"kind": "event", "action": "stage_read", "outcome": "success"},
  "mpi": {
    "stage": "status",
    "substep": "status_read",
    "scope": "global",
    "stage_phase": "read"
  },
  "reason": "status read"
}
```

**Also update the mpi-status/SKILL.md Closure block** (added in Task 4 of this phase) to use the correct invocation:
```bash
python scripts/mpi_step.py close \
  --actor orchestrator \
  --stage status \
  --substep status_read \
  --scope global \
  --status read \
  --reason "status read" \
  --run-dir .
```

This is now a valid invocation after the `--status read` mode is implemented.

**Commit:**
```bash
git add microphenomenograph/1.0.0/scripts/mpi_step.py
git commit -m "feat: add --status read mode to mpi_step.py for read-only audit events (AC6.4)"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: Structural tests — every SKILL.md has a Closure subsection



**Verifies:** doc-as-done.AC6.3, doc-as-done.AC6.4, doc-as-done.AC7.1

**Files:**
- Modify: `tests/test_plugin_structure.py` (extend existing test file)

**Implementation:**

Read `tests/test_plugin_structure.py` first to understand its current assertion structure and helper patterns. Extend it with new test cases:

**Testing:**

- doc-as-done.AC6.3: For each SKILL.md under `microphenomenograph/1.0.0/skills/`, assert the file contains the heading `## Closure (mandatory)`. The set of skills to check: `mpi-init`, `mpi-transcript-prep`, `mpi-diachronic`, `mpi-synchronic`, `mpi-generic-diachronic`, `mpi-generic-synchronic`, `mpi-global-synchronic`, `mpi-hypothesis`, `mpi-irr`, `mpi-status`. (Note: `mpi-kappa/` skill directory is deleted in Phase 12 Task 3; do not assert for it here.)
- doc-as-done.AC6.4 (mpi-status): Assert `mpi-status/SKILL.md` contains both `"no artifact close"` (or equivalent) AND `"stage_phase: read"`.
- doc-as-done.AC7.1: For each SKILL.md, assert it does NOT contain any of: `os.replace`, `project.json.tmp`, `reasoning.log` format prose outside a blockquote, or hand-crafted `git commit -m "mpi:` lines outside of a Closure section. (Simple string search is sufficient — the Closure sections contain commit format examples, but those are in code blocks, not bare prose.)

Follow the existing test patterns in `test_plugin_structure.py` exactly.

**Verification:**
```
Run: pytest tests/test_plugin_structure.py -v
Expected: All tests pass (new + existing)
```

**Commit:**
```bash
git add tests/test_plugin_structure.py
git commit -m "test: assert all SKILL.md files have Closure subsections (AC6.3, AC6.4, AC7.1)"
```
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

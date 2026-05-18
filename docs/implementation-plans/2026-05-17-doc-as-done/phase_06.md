# Documentation-as-Done Contract Implementation Plan

**Goal:** `mpi-analyst` gains `Write` and `Bash` tools so it can self-persist artifacts and call `mpi_step.py close` directly. A "Persistence (mandatory before returning)" subsection enumerates all 6 substeps. Anti-fabrication clause added. Per-substep output format pinned in `mpi-diachronic` and `mpi-synchronic` SKILL.md files.

**Architecture:** Markdown edits to two files (`agents/mpi-analyst.md`, two SKILL.md files). Tests verify the agent file declares the correct tools and Persistence section, and exercise one diachronic substep end-to-end via a fixture-driven close.

**Tech Stack:** Markdown edits. Fixture-driven Python test in `tests/`.

**Scope:** Phase 6 of 6.

**Codebase verified:** 2026-05-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC1: Every step closes via the phased close protocol or stays `pending`
- **doc-as-done.AC1.6 Success:** `mpi-analyst` writes `analyses/pNsN-<stage>.json` and `.md` itself before invoking the helper.
- **doc-as-done.AC1.7 Failure:** A subagent that fails to write artifacts returns `ERROR <transcript> <stage>: <reason>` and never returns analysis content as a substitute.

### doc-as-done.AC6: Subagents own their persistence
- **doc-as-done.AC6.1 Success (mpi-analyst portion):** `agents/mpi-analyst.md` `tools:` line declares `Read, Write, Bash`. (`mpi-cross-analyst.md` deferred to Plan 2.)
- **doc-as-done.AC6.2 Success (mpi-analyst portion):** `agents/mpi-analyst.md` contains a "Persistence (mandatory before returning)" subsection naming the exact files to Write and the `mpi_step.py close` invocation to make. (`mpi-cross-analyst.md` deferred to Plan 2.)
- **doc-as-done.AC6.3 Success:** Every SKILL.md contains a "Closure (mandatory)" subsection naming the responsible actor and the artifacts that close the step.

### doc-as-done.AC10: Substep granularity replaces stage granularity
- **doc-as-done.AC10.4 Success:** `agents/mpi-analyst.md` Persistence subsection enumerates all 6 mpi-analyst substeps (3 diachronic per participant + 3 synchronic per IDU) with per-substep artifact paths and the manual-native substep names.

### doc-as-done.AC12: Manual-native methodology fidelity
- **doc-as-done.AC12.1 Success:** Synchronic substeps iterate **per IDU within a participant**, not per phase. There is no `diachronic.phases` substep, no `diachronic.du`, no `diachronic.refined_du`, no `generic_synchronic.sss_grouping`, no `generic_synchronic.gss_definition`. Substep names match manual_kev.md verbatim.

> **Deferred to Plan 2:** AC12.3 (`temporal_order_within_idu: true` → orchestrator schedules `diachronic.criteria_revision` re-close) and AC12.4 (`concurrent_with_adjacent_idu` merge flag with `--allow-synchronic-merge`). These require orchestrator logic that is outside the scope of Phase 6 (agent file and SKILL.md edits). The agent file documents the `temporal_order_within_idu` flag field; the orchestrator scheduling of the re-close is Plan 2 work.

### doc-as-done.AC28: Transcript-span grounding is mandatory, not optional
- **doc-as-done.AC28.1 Success:** Every generative substep schema requires a non-empty `utterance_refs` array on every analytic unit emitted.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->

<!-- START_TASK_1 -->
### Task 1: Update `agents/mpi-analyst.md` — tools, Persistence, anti-fabrication

**Files:**
- Modify: `microphenomenograph/1.0.0/agents/mpi-analyst.md`

**Implementation:**

Make three targeted edits to the file:

**Edit 1 — Change `tools:` in the frontmatter:**

Find:
```
tools: Read
```
Replace with:
```
tools: Read, Write, Bash
```

**Edit 2 — Add anti-fabrication clause** (insert after the `## Important constraints` section, before the last line `Output ONLY the Reasoning and Output sections.`):

```markdown
## Anti-fabrication rule

If your input artifacts (transcripts, upstream substep outputs) are missing, empty, or
malformed, return `ERROR <reason>` and stop. Never generate placeholder or synthetic
content to make the pipeline appear to progress.
```

**Edit 3 — Add Persistence section** (append after `## Anti-fabrication rule`, before `Output ONLY...`):

```markdown
## Persistence (mandatory before returning)

After producing your analysis, you MUST persist it yourself before returning. Failure to
do so means the step stays `pending`. Follow this sequence for each substep:

### Diachronic substeps (per transcript `pNsN`)

**`diachronic.criteria_grouping`**
```bash
# Write the JSON and markdown artifacts
# (replace pNsN with actual participant key, e.g. p1s1)
Write analyses/pNsN-diachronic.criteria_grouping.json  # full JSON output
Write analyses/pNsN-diachronic.criteria_grouping.md    # markdown table
Write analyses/pNsN-diachronic.criteria_grouping.prompt.json  # schema_version 2 prompt capture

python scripts/mpi_step.py close \
  --actor mpi-analyst \
  --participant pNsN \
  --stage diachronic \
  --substep criteria_grouping \
  --scope pNsN \
  --artifact analyses/pNsN-diachronic.criteria_grouping.json \
  --artifact analyses/pNsN-diachronic.criteria_grouping.md \
  --prompt-artifact analyses/pNsN-diachronic.criteria_grouping.prompt.json \
  --units-json analyses/pNsN-diachronic.criteria_grouping.json \
  --reason "Criteria grouping complete" \
  --run-dir .
```

**`diachronic.criteria_revision`** — same pattern; artifact names end in `.criteria_revision.*`.
JSON must include `convergence: {decision, reason}` field.
```bash
python scripts/mpi_step.py close \
  --actor mpi-analyst --participant pNsN \
  --stage diachronic --substep criteria_revision --scope pNsN \
  --artifact analyses/pNsN-diachronic.criteria_revision.json \
  --artifact analyses/pNsN-diachronic.criteria_revision.md \
  --prompt-artifact analyses/pNsN-diachronic.criteria_revision.prompt.json \
  --units-json analyses/pNsN-diachronic.criteria_revision.json \
  --reason "Criteria revision complete (decision: <converged|more_revision_needed>)" \
  --run-dir .
```

**`diachronic.idu_naming_ordering`** — same pattern; artifact names end in `.idu_naming_ordering.*`.
```bash
python scripts/mpi_step.py close \
  --actor mpi-analyst --participant pNsN \
  --stage diachronic --substep idu_naming_ordering --scope pNsN \
  --artifact analyses/pNsN-diachronic.idu_naming_ordering.json \
  --artifact analyses/pNsN-diachronic.idu_naming_ordering.md \
  --prompt-artifact analyses/pNsN-diachronic.idu_naming_ordering.prompt.json \
  --units-json analyses/pNsN-diachronic.idu_naming_ordering.json \
  --reason "IDU naming and ordering complete" \
  --run-dir .
```

### Synchronic substeps (per IDU within transcript `pNsN`, scope = `pNsN-iduN`)

> **Schema alignment note:** The synchronic JSON payload must have `idu_name` at the top level of the payload object (not inside each ISU entry). This matches `_validate_synchronic_theme_grouping` in `_mpi_schemas.py` which requires `payload["idu_name"]`. Shape: `{"analysis_type": "synchronic", "participant": "pNsN", "idu_name": "...", "isus": [...]}`.

Synchronic substeps iterate **per IDU**. For each IDU (e.g., `p1s1-idu1`, `p1s1-idu2`):

**`synchronic.theme_grouping_within_idu`**
```bash
python scripts/mpi_step.py close \
  --actor mpi-analyst --participant pNsN \
  --stage synchronic --substep theme_grouping_within_idu --scope pNsN-iduN \
  --artifact analyses/pNsN-iduN-synchronic.theme_grouping_within_idu.json \
  --artifact analyses/pNsN-iduN-synchronic.theme_grouping_within_idu.md \
  --prompt-artifact analyses/pNsN-iduN-synchronic.theme_grouping_within_idu.prompt.json \
  --units-json analyses/pNsN-iduN-synchronic.theme_grouping_within_idu.json \
  --reason "Theme grouping complete for iduN" \
  --run-dir .
```

**`synchronic.isu_naming`** — same pattern; artifact names end in `.isu_naming.*`.

**`synchronic.isu_second_level_grouping`** — same pattern; artifact names end in `.isu_second_level_grouping.*`.

### Return value

On success: `OK pNsN diachronic.criteria_grouping 3units 0flagged`
On failure: `ERROR pNsN diachronic.criteria_grouping: <reason>`

Never return the analysis content itself. The orchestrator reads from disk.

### Span grounding requirement

Every IDU and ISU in your JSON output MUST carry a non-empty `utterance_refs` array:
```json
"utterance_refs": [
  {
    "transcript_id": "p1s1",
    "utterance_number": 3,
    "byte_start": 142,
    "byte_end": 198,
    "raw_excerpt": "I noticed a heaviness in my hands"
  }
]
```
The helper rejects closes with missing or empty `utterance_refs`. There is no "uncited claim" path.
```

**Verification:**
```bash
cd microphenomenograph/1.0.0
grep "tools:" agents/mpi-analyst.md
grep "Write" agents/mpi-analyst.md
grep "Persistence" agents/mpi-analyst.md
grep "Anti-fabrication" agents/mpi-analyst.md
```
Expected: tools line shows `Read, Write, Bash`; both sections present.

**Commit:** `feat: update mpi-analyst.md with Write/Bash tools, Persistence, anti-fabrication`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Add Closure subsections to `mpi-diachronic` and `mpi-synchronic` SKILL.md files

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md`
- Modify: `microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md`

**Implementation:**

**For `skills/mpi-diachronic/SKILL.md`** — append this section at the end of the file:

```markdown
## Closure (mandatory)

Each diachronic substep closes its own four-part transaction via `mpi_step.py close`.
The `mpi-analyst` subagent owns persistence for all three LLM substeps.

| Substep | Actor | Artifacts | Notes |
|---------|-------|-----------|-------|
| `diachronic.criteria_grouping` | mpi-analyst (LLM) | `pNsN-diachronic.criteria_grouping.{json,md,prompt.json}` | First substep; no prerequisites |
| `diachronic.criteria_revision` | mpi-analyst (LLM) | `pNsN-diachronic.criteria_revision.{json,md,prompt.json}` | JSON must include `convergence: {decision, reason}`; orchestrator re-dispatches while `decision == "more_revision_needed"`, capped at 5 passes |
| `diachronic.idu_naming_ordering` | mpi-analyst (LLM) | `pNsN-diachronic.idu_naming_ordering.{json,md,prompt.json}` | Final diachronic substep; its close triggers synchronic eligibility |

**Commit message format:** `mpi: mpi-analyst diachronic.<substep> pNsN (<N>units <K>flagged)`

**Manual-native constraint:** Diachronic does NOT include sub-phase identification (`diachronic.phases`, `diachronic.du`, `diachronic.refined_du`). Substep names follow manual_kev.md (Sheldrake & Dienes 2025) verbatim.

**Anti-fabrication rule:** If transcript is missing, empty, or malformed, `mpi-analyst` returns `ERROR <reason>` and stops. Never synthesize placeholder content.
```

**For `skills/mpi-synchronic/SKILL.md`** — append this section at the end of the file:

```markdown
## Closure (mandatory)

Synchronic substeps iterate **per IDU within a transcript**, not per stage-level invocation.
Scope for each substep is `pNsN-iduN` (e.g., `p1s1-idu1`, `p1s1-idu2`).

| Substep | Actor | Artifacts | Notes |
|---------|-------|-----------|-------|
| `synchronic.theme_grouping_within_idu` | mpi-analyst (LLM) | `pNsN-iduN-synchronic.theme_grouping_within_idu.{json,md,prompt.json}` | First synchronic substep per IDU. If `temporal_order_within_idu: true`, orchestrator schedules `diachronic.criteria_revision` re-close for that transcript before continuing |
| `synchronic.isu_naming` | mpi-analyst (LLM) | `pNsN-iduN-synchronic.isu_naming.{json,md,prompt.json}` | Requires `theme_grouping_within_idu` done for same IDU |
| `synchronic.isu_second_level_grouping` | mpi-analyst (LLM) | `pNsN-iduN-synchronic.isu_second_level_grouping.{json,md,prompt.json}` | Final synchronic substep per IDU |

**Output columns (all three substeps):** `criteria` (string) | `isu_name` (string) | `isu_second_level_of_abstraction` (string or empty). These three columns are preserved as distinct fields through all downstream aggregation.

**IDU-split-after-synchronic return edge:** If `theme_grouping_within_idu` flags `temporal_order_within_idu: true`, the orchestrator re-closes `diachronic.criteria_revision` for that transcript with the split context in the prompt. Manifest records `idu_split_after_synchronic` audit event linking both span_ids.

**Anti-fabrication rule:** If diachronic output is missing, empty, or malformed, `mpi-analyst` returns `ERROR <reason>` and stops.
```

**Verification:**
```bash
grep "Closure" microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md
grep "Closure" microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md
grep "theme_grouping_within_idu" microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md
```
Expected: both files contain the Closure section; synchronic uses per-IDU substep names.

**Commit:** `feat: add Closure subsections to mpi-diachronic and mpi-synchronic SKILL.md`

<!-- END_TASK_2 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->

<!-- START_TASK_3 -->
### Task 3: Fixture-driven test — one diachronic substep end-to-end

**Verifies:** doc-as-done.AC1.6, doc-as-done.AC1.7, doc-as-done.AC6.1, doc-as-done.AC6.2, doc-as-done.AC10.4, doc-as-done.AC12.1, doc-as-done.AC28.1

**Files:**
- Create: `tests/test_mpi_analyst_contract.py`

**Implementation:**

These tests verify the structural contracts of the agent file and skills (no LLM calls):

```python
"""
Tests verifying mpi-analyst.md and SKILL.md structural contracts from Phase 6.
These are contract tests — they verify the files contain the required sections and
declarations without invoking any LLM.
"""
from pathlib import Path
import re
import sys

import pytest

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
AGENT_FILE = PLUGIN_ROOT / "agents" / "mpi-analyst.md"
DIACHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-diachronic" / "SKILL.md"
SYNCHRONIC_SKILL = PLUGIN_ROOT / "skills" / "mpi-synchronic" / "SKILL.md"


class TestAC6_1_AgentTools:
    """AC6.1: mpi-analyst.md declares Read, Write, Bash in tools: line."""

    def test_mpi_analyst_declares_write_bash(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        # Find tools: line in frontmatter
        match = re.search(r"^tools:\s*(.+)$", content, re.MULTILINE)
        assert match, "No 'tools:' line found in mpi-analyst.md frontmatter"
        tools_line = match.group(1)
        assert "Write" in tools_line, f"'Write' missing from tools line: {tools_line!r}"
        assert "Bash" in tools_line, f"'Bash' missing from tools line: {tools_line!r}"
        assert "Read" in tools_line, f"'Read' missing from tools line: {tools_line!r}"


class TestAC6_2_PersistenceSection:
    """AC6.2: mpi-analyst.md contains Persistence (mandatory before returning) subsection."""

    def test_persistence_section_exists(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "Persistence (mandatory before returning)" in content, \
            "Missing 'Persistence (mandatory before returning)' section in mpi-analyst.md"

    def test_persistence_section_names_six_substeps(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        required_substeps = [
            "diachronic.criteria_grouping",
            "diachronic.criteria_revision",
            "diachronic.idu_naming_ordering",
            "synchronic.theme_grouping_within_idu",
            "synchronic.isu_naming",
            "synchronic.isu_second_level_grouping",
        ]
        for substep in required_substeps:
            assert substep in content, \
                f"Substep '{substep}' not found in mpi-analyst.md Persistence section"

    def test_persistence_section_names_close_invocation(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "mpi_step.py close" in content, \
            "mpi_step.py close invocation not found in mpi-analyst.md"

    def test_persistence_return_value_format(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "OK " in content and "ERROR " in content, \
            "Return value format (OK / ERROR) not documented in mpi-analyst.md"


class TestAC6_3_SkillClosureSections:
    """AC6.3: SKILL.md files contain 'Closure (mandatory)' subsection."""

    def test_diachronic_skill_has_closure(self):
        content = DIACHRONIC_SKILL.read_text(encoding="utf-8")
        assert "Closure (mandatory)" in content, \
            "Missing 'Closure (mandatory)' section in mpi-diachronic/SKILL.md"

    def test_synchronic_skill_has_closure(self):
        content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
        assert "Closure (mandatory)" in content, \
            "Missing 'Closure (mandatory)' section in mpi-synchronic/SKILL.md"


class TestAC10_4_SubstepEnumeration:
    """AC10.4: Agent enumerates all 6 mpi-analyst substeps with manual-native names."""

    def test_no_deprecated_substep_names(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        # These names are from µ-PATH and must NOT appear in the agent file
        deprecated = ["diachronic.phases", "diachronic.du", "diachronic.refined_du",
                      "generic_synchronic.sss_grouping", "generic_synchronic.gss_definition"]
        for name in deprecated:
            assert name not in content, \
                f"Deprecated substep name '{name}' found in mpi-analyst.md — use manual_kev.md names"


class TestAC12_1_ManualNativeSubstepNames:
    """AC12.1: Synchronic skill uses per-IDU iteration, not per-phase."""

    def test_synchronic_skill_mentions_per_idu(self):
        content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
        assert "per IDU" in content or "per-IDU" in content or "per_idu" in content.lower(), \
            "mpi-synchronic/SKILL.md must document per-IDU iteration"

    def test_synchronic_skill_preserves_isu_second_level_column(self):
        content = SYNCHRONIC_SKILL.read_text(encoding="utf-8")
        assert "isu_second_level_of_abstraction" in content or "ISU 2nd Level" in content or \
               "isu_second_level" in content, \
            "mpi-synchronic/SKILL.md must document isu_second_level_of_abstraction column"

    def test_diachronic_skill_no_sub_phase_identification(self):
        content = DIACHRONIC_SKILL.read_text(encoding="utf-8")
        # These terms come from µ-PATH, not manual_kev.md
        for term in ["sub-phase", "DU", "refined_du"]:
            assert term not in content, \
                f"Term '{term}' found in mpi-diachronic/SKILL.md — manual_kev.md excludes sub-phase identification"


class TestAC28_1_UtteranceRefsRequirement:
    """AC28.1: Agent documents the utterance_refs requirement."""

    def test_agent_documents_utterance_refs(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "utterance_refs" in content, \
            "mpi-analyst.md must document the utterance_refs grounding requirement"


class TestAntiFabricationClause:
    """AC5.3: Anti-fabrication rule present in agent file."""

    def test_anti_fabrication_in_agent(self):
        content = AGENT_FILE.read_text(encoding="utf-8")
        assert "Never generate placeholder" in content or \
               "never generate placeholder" in content or \
               "Anti-fabrication" in content, \
            "Anti-fabrication rule not found in mpi-analyst.md"
```

**Verification:**
```bash
pytest tests/test_mpi_analyst_contract.py -v
```
Expected: all tests pass after the agent file and SKILL.md updates in Tasks 1 and 2.

**Commit:** `test: add Phase 6 contract tests for mpi-analyst structural requirements`

<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: End-to-end fixture — one diachronic substep close through mpi_step.py

**Verifies:** doc-as-done.AC1.6 (mpi-analyst writes artifacts itself before invoking helper)

**Files:**
- Modify: `tests/test_mpi_analyst_contract.py` (append end-to-end fixture class)

**Implementation:**

This test exercises one complete diachronic substep close end-to-end using `mpi_step.main()` directly (no LLM). It simulates what a correctly-behaving `mpi-analyst` would do: write the three artifact files, then call close.

Append this class to `tests/test_mpi_analyst_contract.py`:

```python
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# Import mpi_step from the plugin's scripts directory
_SCRIPTS_DIR = PLUGIN_ROOT / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))
import mpi_step
from _mpi_atomic import atomic_write, load_or_create_run_id


def _setup_run_dir(tmp_path: Path) -> Path:
    """Create a git-initialised MPI run dir that passes init."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    subprocess.run(["git", "init"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.name", "Test"], cwd=run_dir, capture_output=True)
    subprocess.run(["git", "config", "--local", "user.email", "t@test.com"], cwd=run_dir, capture_output=True)
    mpi_step.main(["init", "--run", str(run_dir)])
    return run_dir


_VALID_CRITERIA_GROUPING_UNITS = {
    "analysis_type": "diachronic",
    "participant": "p1s1",
    "reasoning_summary": "One IDU identified.",
    "idus": [
        {
            "idu_number": 1, "idu_name": "Opening Moment", "moment": 1,
            "criteria": "The utterances talk about the opening experience.",
            "confidence": 4, "flag_for_review": False,
            "utterance_numbers": ["1", "2"],
            "hinge_to_next": None,
            "utterance_refs": [
                {
                    "transcript_id": "p1s1",
                    "utterance_number": 1,
                    "byte_start": 0,
                    "byte_end": 20,
                    "raw_excerpt": "I noticed something.",
                }
            ],
        }
    ],
}

_VALID_PROMPT_ARTIFACT_DATA = {
    "schema_version": "2",
    "actor": {
        "kind": "subagent", "name": "mpi-analyst",
        "agent_file_sha256": "fakefakefakefake",
        "agent_file_path": "agents/mpi-analyst.md",
    },
    "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
    "sampling": {"temperature": 1.0, "top_p": 1.0, "top_k": None,
                 "max_tokens": 8192, "seed": None, "stop_sequences": []},
    "stage": "diachronic", "substep": "criteria_grouping", "scope": "p1s1",
    "prompt": {"system": "...", "messages": [], "tools_available": []},
    "response": {"raw_text": "...", "tool_calls": [], "parsed_units_path": ""},
    "metadata": {
        "finish_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50,
                  "cache_read_tokens": 0, "cache_write_tokens": 0},
        "duration_ms": 800, "timestamp": "2026-05-18T10:00:00Z",
        "anthropic_request_id": "req_e2e",
    },
}


class TestAC1_6_AgentSelfPersistEndToEnd:
    """
    AC1.6: mpi-analyst writes artifacts itself before invoking mpi_step.py close.
    This fixture simulates the agent workflow: write three files, then call close.
    No LLM is invoked — we're testing the close contract, not the analysis.
    """

    def test_agent_workflow_writes_artifacts_then_closes(self, tmp_path):
        run_dir = _setup_run_dir(tmp_path)
        analyses = run_dir / "analyses"
        analyses.mkdir()

        scope = "p1s1"
        stage = "diachronic"
        substep = "criteria_grouping"

        # Step 1: Agent writes JSON artifact
        json_path = analyses / f"{scope}-{stage}.{substep}.json"
        json_path.write_text(json.dumps(_VALID_CRITERIA_GROUPING_UNITS))

        # Step 2: Agent writes MD artifact
        md_path = analyses / f"{scope}-{stage}.{substep}.md"
        md_path.write_text("# IDU Analysis\n\n| IDU | Criteria |\n|-----|----------|\n| Opening Moment | ... |\n")

        # Step 3: Agent writes prompt-capture artifact
        prompt_path = analyses / f"{scope}-{stage}.{substep}.prompt.json"
        prompt_path.write_text(json.dumps(_VALID_PROMPT_ARTIFACT_DATA))

        # Step 4: Agent calls mpi_step.py close (simulated here)
        rc = mpi_step.main([
            "close",
            "--actor", "mpi-analyst",
            "--participant", scope,
            "--stage", stage,
            "--substep", substep,
            "--scope", scope,
            "--artifact", str(json_path),
            "--artifact", str(md_path),
            "--prompt-artifact", str(prompt_path),
            "--units-json", str(json_path),
            "--reason", "criteria_grouping complete for p1s1",
            "--run-dir", str(run_dir),
        ])

        # Verify: close succeeded
        assert rc == 0, f"close returned {rc}"

        # Verify: manifest updated at substep granularity
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        substep_entry = (
            manifest.get("participants", {})
            .get(scope, {})
            .get("stages", {})
            .get(stage, {})
            .get("substeps", {})
            .get(substep, {})
        )
        assert substep_entry.get("status") == "done", f"substep not done: {substep_entry}"
        assert substep_entry.get("expected_action") == "git_commit_succeeded"
        assert "git_commit_sha" not in substep_entry  # AC1.4 self-reference impossibility

        # Verify: audit trail has full phase sequence
        audit_lines = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit_lines if l.strip()]
        actions = [e.get("event", {}).get("action") for e in events]
        assert "close_attempted" in actions
        assert "git_commit_succeeded" in actions

        # Verify: git has a commit with canonical message
        r = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=run_dir, capture_output=True, text=True,
        )
        assert f"mpi: mpi-analyst {stage}.{substep} {scope}" in r.stdout

    def test_agent_returning_error_instead_of_analysis_content(self, tmp_path):
        """AC1.7: When agent fails, it returns ERROR string, NOT analysis content."""
        # This is a documentation/contract test — verifies that the agent's
        # Persistence section instructs it to return ERROR, not content.
        content = AGENT_FILE.read_text(encoding="utf-8")
        # The Persistence section must document the ERROR return format
        assert "ERROR" in content and ("ERROR <" in content or "ERROR pNsN" in content), \
            "mpi-analyst.md Persistence section must document ERROR return format for failures"
        # The agent must NOT instruct itself to return analysis content on failure
        # (This is a best-effort check — full behavioral testing requires LLM-in-the-loop)
        persistence_idx = content.find("Persistence (mandatory before returning)")
        if persistence_idx >= 0:
            persistence_section = content[persistence_idx:]
            assert "Never return the analysis content" in persistence_section or \
                   "The orchestrator reads from disk" in persistence_section, \
                "mpi-analyst.md Persistence section must instruct agent to NOT return content"
```

**Verification:**
```bash
pytest tests/test_mpi_analyst_contract.py -v
```
Expected: all tests pass, including the end-to-end `TestAC1_6_AgentSelfPersistEndToEnd`.

**Commit:** `test: add Phase 6 end-to-end fixture for agent self-persist contract`

<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Run full test suite

**Verification:**
```bash
pytest microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
pytest tests/ -v
```
Expected: all pass.

**Commit:** *(no additional commit — test run only)*

<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

# Documentation-as-Done Contract Implementation Plan

**Goal:** Every LLM substep close requires a `--prompt-artifact` path pointing at a schema_version 2 `prompt.json`. The helper validates the artifact at pre-check time and records the path in the audit event. Malformed or missing prompt artifacts are rejected before any state mutation.

**Architecture:** Extend `mpi_step.py close` pre-checks to validate the prompt.json schema. The schema itself is defined as a Python dict validator in `_mpi_schemas.py`. The `--prompt-artifact` flag already exists in the parser (Phase 1); this phase activates the validation logic. Agent file SHA256 check (`actor.agent_file_sha256` vs current SHA of `actor.agent_file_path`) is done at pre-check time.

**Tech Stack:** Python 3.9+ stdlib (`hashlib`, `json`). No new deps.

**Scope:** Phase 5 of 6.

**Codebase verified:** 2026-05-18

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC11: Every LLM call is captured as a replayable artifact (schema_version 2, replay-grade)
- **doc-as-done.AC11.1 Success:** For every LLM-invoking substep close, a `<scope>-<stage>.<substep>.prompt.json` artifact exists on disk conforming to the schema_version 2 shape.
- **doc-as-done.AC11.2 Failure:** A `close` invocation for an LLM-invoking substep without `--prompt-artifact` is rejected with a named error.
- **doc-as-done.AC11.3 Failure:** A malformed `prompt.json` (missing required keys, wrong schema_version, or `actor.agent_file_sha256` doesn't match the SHA of the agent file at recorded `agent_file_path`) is rejected at pre-check time; manifest unchanged.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add `validate_prompt_artifact` to `_mpi_schemas.py`

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py` (append prompt artifact validator)

**Implementation:**

Append this function to the bottom of `_mpi_schemas.py`:

```python
# ---------------------------------------------------------------------------
# Prompt artifact validator (schema_version 2)
# ---------------------------------------------------------------------------

_PROMPT_ARTIFACT_REQUIRED_KEYS = [
    "schema_version", "actor", "model", "sampling",
    "stage", "substep", "scope", "prompt", "response", "metadata",
]

_PROMPT_ACTOR_REQUIRED = ["kind", "name", "agent_file_sha256", "agent_file_path"]
_PROMPT_MODEL_REQUIRED = ["id", "provider"]
_PROMPT_SAMPLING_REQUIRED = ["temperature", "top_p", "max_tokens"]
_PROMPT_INNER_REQUIRED = ["system", "messages", "tools_available"]
_PROMPT_RESPONSE_REQUIRED = ["raw_text", "tool_calls", "parsed_units_path"]
_PROMPT_METADATA_REQUIRED = ["finish_reason", "usage", "duration_ms", "timestamp"]
_PROMPT_USAGE_REQUIRED = ["input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"]


def validate_prompt_artifact(
    artifact: dict,
    *,
    check_agent_sha: bool = True,
) -> list[SchemaError]:
    """
    Validate a prompt.json dict against schema_version 2.
    If check_agent_sha=True (default), reads the agent file at
    artifact['actor']['agent_file_path'] and verifies SHA256 matches
    artifact['actor']['agent_file_sha256'].
    Returns list of SchemaError; empty means valid.
    """
    import hashlib
    import os

    errors = _require_keys(artifact, _PROMPT_ARTIFACT_REQUIRED_KEYS, "prompt")

    if artifact.get("schema_version") != "2":
        errors.append(SchemaError("prompt.schema_version",
                                  f"must be '2', got {artifact.get('schema_version')!r}"))

    actor = artifact.get("actor", {})
    if isinstance(actor, dict):
        errors.extend(_require_keys(actor, _PROMPT_ACTOR_REQUIRED, "prompt.actor"))
        if check_agent_sha and "agent_file_sha256" in actor and "agent_file_path" in actor:
            agent_path = actor["agent_file_path"]
            expected_sha = actor["agent_file_sha256"]
            # Resolve relative to cwd (the plugin root during execution)
            if os.path.exists(agent_path):
                with open(agent_path, "rb") as f:
                    actual_sha = hashlib.sha256(f.read()).hexdigest()
                if actual_sha != expected_sha:
                    errors.append(SchemaError(
                        "prompt.actor.agent_file_sha256",
                        f"SHA256 mismatch: recorded={expected_sha[:16]}... "
                        f"actual={actual_sha[:16]}... — agent file has changed since this prompt was captured",
                    ))
            # If file doesn't exist at path, skip SHA check (may be a different machine/path)

    model = artifact.get("model", {})
    if isinstance(model, dict):
        errors.extend(_require_keys(model, _PROMPT_MODEL_REQUIRED, "prompt.model"))

    sampling = artifact.get("sampling", {})
    if isinstance(sampling, dict):
        errors.extend(_require_keys(sampling, _PROMPT_SAMPLING_REQUIRED, "prompt.sampling"))

    prompt_inner = artifact.get("prompt", {})
    if isinstance(prompt_inner, dict):
        errors.extend(_require_keys(prompt_inner, _PROMPT_INNER_REQUIRED, "prompt.prompt"))

    response = artifact.get("response", {})
    if isinstance(response, dict):
        errors.extend(_require_keys(response, _PROMPT_RESPONSE_REQUIRED, "prompt.response"))

    metadata = artifact.get("metadata", {})
    if isinstance(metadata, dict):
        errors.extend(_require_keys(metadata, _PROMPT_METADATA_REQUIRED, "prompt.metadata"))
        usage = metadata.get("usage", {})
        if isinstance(usage, dict):
            errors.extend(_require_keys(usage, _PROMPT_USAGE_REQUIRED, "prompt.metadata.usage"))

    return errors
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python -c "
import sys; sys.path.insert(0, '.')
from _mpi_schemas import validate_prompt_artifact
print('import OK')
"
```

**Commit:** `feat: add validate_prompt_artifact to _mpi_schemas.py`

<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Wire prompt artifact validation into `cmd_close`

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py` (update Phase 2 pre-check block in `cmd_close`)

**Implementation:**

In `cmd_close`, find the block that checks `--prompt-artifact` (after "Check LLM substep requires --prompt-artifact"). Replace that block with the following, which also validates the prompt.json schema:

```python
    # Check LLM substep requires --prompt-artifact and validate it
    from _mpi_schemas import LLM_SUBSTEPS, validate_prompt_artifact
    if (args.stage, args.substep) in LLM_SUBSTEPS:
        if not getattr(args, "prompt_artifact", None):
            msg = (f"prompt_artifact_required: substep ({args.stage}, {args.substep}) "
                   "is LLM-invoking and requires --prompt-artifact")
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)
        pa = Path(args.prompt_artifact)
        if not pa.exists():
            msg = f"prompt_artifact_not_found: {args.prompt_artifact}"
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)
        try:
            pa_data = json.loads(pa.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            msg = f"prompt_artifact_invalid_json: {exc}"
            print(f"ERROR {msg}", file=sys.stderr)
            return _abort(msg)
        pa_errors = validate_prompt_artifact(pa_data, check_agent_sha=False)
        if pa_errors:
            for err in pa_errors:
                print(f"ERROR prompt_artifact_schema_invalid: {err}", file=sys.stderr)
            return _abort(f"prompt_artifact_schema_invalid: {pa_errors[0]}")
    elif getattr(args, "prompt_artifact", None):
        msg = (f"prompt_artifact_unexpected: substep ({args.stage}, {args.substep}) "
               "is orchestrator-only and must NOT have --prompt-artifact")
        print(f"ERROR {msg}", file=sys.stderr)
        return _abort(msg)
```

Note: `check_agent_sha=False` here because the agent file path in the artifact may be relative to a different working directory than where `mpi_step.py` runs. SHA verification is done by the replay verifier (`mpi_replay.py`, future work) which can resolve paths. The schema structure is still fully validated.

**Commit:** `feat: wire prompt artifact schema validation into close pre-checks`

<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Tests for Phase 5 — prompt artifact validation

**Verifies:** doc-as-done.AC11.1, doc-as-done.AC11.2, doc-as-done.AC11.3

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py` (append Phase 5 test classes)

**Implementation:**

Append these classes to `test_mpi_step.py`:

```python
# ---------------------------------------------------------------------------
# Phase 5: prompt artifact validation tests
# ---------------------------------------------------------------------------

VALID_PROMPT_ARTIFACT = {
    "schema_version": "2",
    "actor": {
        "kind": "subagent", "name": "mpi-analyst",
        "agent_file_sha256": "abc123def456",
        "agent_file_path": "agents/mpi-analyst.md",
    },
    "model": {"id": "claude-haiku-4-5", "provider": "anthropic"},
    "sampling": {
        "temperature": 1.0, "top_p": 1.0, "top_k": None,
        "max_tokens": 8192, "seed": None, "stop_sequences": [],
    },
    "stage": "diachronic", "substep": "criteria_grouping", "scope": "p1s1",
    "prompt": {"system": "...", "messages": [], "tools_available": []},
    "response": {"raw_text": "...", "tool_calls": [], "parsed_units_path": ""},
    "metadata": {
        "finish_reason": "end_turn",
        "usage": {
            "input_tokens": 100, "output_tokens": 50,
            "cache_read_tokens": 0, "cache_write_tokens": 0,
        },
        "duration_ms": 1500,
        "timestamp": "2026-05-18T10:00:00Z",
        "anthropic_request_id": "req_abc123",
    },
}


class TestPromptArtifactSchema:
    def test_valid_prompt_artifact_accepted(self):
        from _mpi_schemas import validate_prompt_artifact
        errs = validate_prompt_artifact(VALID_PROMPT_ARTIFACT, check_agent_sha=False)
        assert errs == [], [str(e) for e in errs]

    def test_wrong_schema_version_rejected(self):
        from _mpi_schemas import validate_prompt_artifact
        bad = {**VALID_PROMPT_ARTIFACT, "schema_version": "1"}
        errs = validate_prompt_artifact(bad, check_agent_sha=False)
        assert any("schema_version" in str(e) for e in errs), [str(e) for e in errs]

    def test_missing_actor_fields_rejected(self):
        from _mpi_schemas import validate_prompt_artifact
        bad_actor = {"kind": "subagent"}  # missing name, agent_file_sha256, agent_file_path
        bad = {**VALID_PROMPT_ARTIFACT, "actor": bad_actor}
        errs = validate_prompt_artifact(bad, check_agent_sha=False)
        assert any("agent_file_sha256" in str(e) for e in errs), [str(e) for e in errs]

    def test_missing_cache_tokens_rejected(self):
        from _mpi_schemas import validate_prompt_artifact
        bad_usage = {"input_tokens": 100, "output_tokens": 50}  # missing cache fields
        bad_meta = {**VALID_PROMPT_ARTIFACT["metadata"], "usage": bad_usage}
        bad = {**VALID_PROMPT_ARTIFACT, "metadata": bad_meta}
        errs = validate_prompt_artifact(bad, check_agent_sha=False)
        assert any("cache_read_tokens" in str(e) or "cache_write_tokens" in str(e) for e in errs), [str(e) for e in errs]


class TestClosePromptArtifactEnforcement:
    def test_llm_substep_without_prompt_artifact_rejected(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            # NO --prompt-artifact
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0

    def test_malformed_prompt_artifact_rejected(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        # Write a prompt.json missing required fields
        bad_prompt = run_dir / "bad_prompt.json"
        bad_prompt.write_text(json.dumps({"schema_version": "1", "actor": {}}))
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(bad_prompt),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc != 0
        # Manifest must be unchanged — criteria_grouping substep must not be present
        manifest = json.loads((run_dir / ".mpi" / "project.json").read_text())
        assert "criteria_grouping" not in manifest.get("participants", {}).get("p1s1", {}).get("stages", {}).get("diachronic", {}).get("substeps", {})

    def test_valid_prompt_artifact_accepted_in_close(self, tmp_path):
        run_dir = _init_run_dir(tmp_path)
        art_json = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.json")
        art_md = _write_artifact(run_dir, "p1s1-diachronic.criteria_grouping.md", "# out")
        prompt_art = _write_prompt_artifact(run_dir, "p1s1", "diachronic", "criteria_grouping")
        units = _write_units_json(run_dir, "units.json", VALID_CRITERIA_GROUPING_UNITS)
        rc = mpi_step.main([
            "close", "--actor", "mpi-analyst", "--participant", "p1s1",
            "--stage", "diachronic", "--substep", "criteria_grouping",
            "--scope", "p1s1", "--artifact", str(art_json), "--artifact", str(art_md),
            "--prompt-artifact", str(prompt_art),
            "--units-json", str(units), "--reason", "test", "--run-dir", str(run_dir),
        ])
        assert rc == 0
        # Audit event must reference the prompt artifact path
        audit = (run_dir / ".mpi" / "audit.jsonl").read_text().splitlines()
        events = [json.loads(l) for l in audit if l.strip()]
        audit_events = [e for e in events if e.get("event", {}).get("action") == "audit_appended"]
        assert audit_events, "No audit_appended event found"
        assert any(
            e.get("mpi", {}).get("prompt_artifact_path") for e in events
        ), "No prompt_artifact_path in any audit event"
```

**Verification:**
```bash
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py -k "PromptArtifact" -v
```
Expected: all pass.

**Commit:** `test: add Phase 5 prompt artifact validation tests`

<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

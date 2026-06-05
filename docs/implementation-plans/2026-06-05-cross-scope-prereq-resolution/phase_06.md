# Pipeline Correctness Implementation Plan — Phase 6

**Goal:** Add offset-file format enforcement to the `register_offsets` validator; update `mpi-transcript-prep` SKILL.md to specify flat-dict format and single-line-per-utterance invariant; add a note to `microphenomenograph/1.0.0/CLAUDE.md`.

**Architecture:** `_validate_utterance_refs` (line 732 of `mpi_step.py`) already expects the flat-dict format — `registry.get(str(utterance_number))` — so a correctly-formatted offset file works today. Phase 6 adds a guard in `_validate_transcript_prep_register_offsets` (added in Phase 5) that rejects the old array format (`{"transcript_id": ..., "utterances": [...]}`) at close time with a descriptive error. The check reads and parses the file at `offsets_path` during validation.

**Tech Stack:** Python 3, JSON, pytest.

**Scope:** Phase 6 of 8 (depends on Phase 5).

**Codebase verified:** 2026-06-05

**Investigator findings:**
- `_validate_utterance_refs` at line 732 uses `registry.get(str(utterance_number))` — confirms flat-dict is the expected format.
- Each entry must have `byte_start` and `byte_end` fields (accessed at lines 743–744).
- SKILL.md Closure section (line 76) describes `register_offsets` as "Maps normalized line numbers to raw byte ranges" — does not specify the JSON format.
- No `_validate_offset` function or format check exists anywhere in the codebase.
- SKILL.md does not mention the single-line-per-utterance invariant or byte range definition.

---

## Acceptance Criteria Coverage

### cross-scope-prereq-resolution.AC6: Offset files use flat-dict format aligned to utterance boundaries
- **cross-scope-prereq-resolution.AC6.1 Success:** `transcripts/offsets/<id>.json` is a flat dict keyed by string utterance number: `{"1": {"byte_start": N, "byte_end": N}, ...}`.
- **cross-scope-prereq-resolution.AC6.2 Success:** Each entry's `byte_start` is the byte offset of the first character of the speaker label on that utterance line; `byte_end` is the last character before the line ending. Each utterance occupies exactly one physical line — the `normalize` step enforces this invariant; `register_offsets` may assume it.
- **cross-scope-prereq-resolution.AC6.3 Success:** `utterance_refs` in diachronic/synchronic artifacts that cite utterance 3 use `byte_start`/`byte_end` values that correspond exactly to the full text of utterance 3 in the raw file.
- **cross-scope-prereq-resolution.AC6.4 Failure:** An offset file in the old array format (`{"transcript_id": ..., "utterances": [...]}`) causes `cmd_close` to reject with a descriptive error.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Add offset file format guard to `_validate_transcript_prep_register_offsets`

**Verifies:** cross-scope-prereq-resolution.AC6.1, AC6.4

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/_mpi_schemas.py`

**Implementation:**

Replace the current `_validate_transcript_prep_register_offsets` function (added in Phase 5) with the version that also validates the offset file content:

```python
def _validate_transcript_prep_register_offsets(payload: dict) -> list[SchemaError]:
    """
    register_offsets — records path of the utterance offset file and utterance count.

    In addition to required-fields validation, opens and inspects the offset file
    to reject the old array format {"transcript_id": ..., "utterances": [...]}.

    Expected flat-dict format:
        {"1": {"byte_start": N, "byte_end": N}, "2": {...}, ...}

    Keys: string utterance numbers ("1", "2", ...)
    Values: dicts with "byte_start" and "byte_end" integer fields
    """
    import json
    import os

    errors = _require_keys(payload, ["transcript_id", "offsets_path", "utterance_count"], "payload")
    if errors:
        return errors  # Can't check file if required path field is missing

    offsets_path = payload.get("offsets_path")
    # Path resolution: offsets_path is resolved relative to CWD. The schema validator
    # does not receive run_dir (unlike _validate_utterance_refs, which is passed run_dir
    # explicitly at lines 696/714 of mpi_step.py and uses run_dir/"transcripts"/"offsets").
    # Here we rely on the close-time invariant: CWD == run_dir, because all
    # `mpi_step.py close` invocations run from inside the run directory with --run-dir .
    # The file check is therefore equivalent to `(run_dir / offsets_path).exists()`.
    if offsets_path and os.path.exists(offsets_path):
        try:
            data = json.loads(open(offsets_path, encoding="utf-8").read())
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(SchemaError(
                "payload.offsets_path",
                f"offset file could not be read: {exc}"
            ))
            return errors

        # Detect old array format: top-level dict with "utterances" list key
        if isinstance(data, dict) and "utterances" in data:
            errors.append(SchemaError(
                "payload.offsets_path",
                "offset file is in the old array format "
                '({"transcript_id": ..., "utterances": [...]}) — '
                "use the flat-dict format instead: "
                '{"1": {"byte_start": N, "byte_end": N}, "2": {...}, ...}'
            ))
            return errors

        # Validate flat-dict structure
        if not isinstance(data, dict):
            errors.append(SchemaError(
                "payload.offsets_path",
                f"offset file must be a JSON object (dict), got {type(data).__name__}"
            ))
            return errors

        # Spot-check: every key should be a string-encoded integer; every value should
        # have byte_start and byte_end
        for key, entry in data.items():
            try:
                int(key)
            except (ValueError, TypeError):
                errors.append(SchemaError(
                    "payload.offsets_path",
                    f"offset file key {key!r} is not a string utterance number"
                ))
                break  # Report first bad key only
            if not isinstance(entry, dict):
                errors.append(SchemaError(
                    "payload.offsets_path",
                    f"offset file entry for utterance {key!r} must be a dict "
                    "with byte_start and byte_end"
                ))
                break
            for field in ("byte_start", "byte_end"):
                if field not in entry:
                    errors.append(SchemaError(
                        "payload.offsets_path",
                        f"offset file entry for utterance {key!r} is missing field '{field}'"
                    ))
                    break
            if errors:
                break

    return errors
```

**Testing:**

Add tests in `TestTranscriptPrepValidators` (or a new `TestOffsetFileFormat` class):
- Valid flat-dict offset file → `[]`
- Old array format file → `SchemaError` with `payload.offsets_path` field mentioning "old array format"
- Dict with non-integer string key → schema error
- Entry missing `byte_start` → schema error
- Non-dict top-level value → schema error
- `offsets_path` pointing to a non-existent file → no error (file not yet written is valid during testing; the schema only validates when the file exists)

**Verification:**
```
cd microphenomenograph/1.0.0/scripts
python -m pytest test_mpi_step.py -k "offset" -v
```
Expected: all offset format tests pass.

**Commit:** `feat: add offset file format guard to _validate_transcript_prep_register_offsets`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update `mpi-transcript-prep` SKILL.md — offset format and invariants

**Verifies:** cross-scope-prereq-resolution.AC6.2 (byte-range definition)

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md`

**Implementation:**

**2a. Update the `register_offsets` row in the Closure table** (currently line 76):

Find:
```
| `transcript_prep.register_offsets` | orchestrator | `transcripts/offsets/<transcript_id>.json` | Maps normalized line numbers to raw byte ranges. SHA recorded in manifest. |
```

Replace with:
```
| `transcript_prep.register_offsets` | orchestrator | `transcripts/offsets/<transcript_id>.json` | Produces a flat-dict offset file mapping string utterance numbers to byte ranges in the raw transcript: `{"1": {"byte_start": N, "byte_end": N}, "2": {...}}`. `byte_start` = byte offset of the first character of the speaker label on that utterance line; `byte_end` = byte offset of the last character before the line ending. Assumes the single-line-per-utterance invariant enforced by `normalize`. SHA recorded in manifest. |
```

**2b. Add offset format contract to the `normalize` row** (currently line 75). Append to its Notes cell:

```
Also enforces the single-line-per-utterance invariant: after normalization, each utterance must occupy exactly one physical line (identified by its speaker-label prefix). This is a precondition for `register_offsets` byte-range computation.
```

**2c. Add a "Offset file format" section** after the Closure table and before the Commit message format note:

```markdown
## Offset file format

`transcripts/offsets/<transcript_id>.json` uses the flat-dict format:

```json
{
  "1": {"byte_start": 0, "byte_end": 42},
  "2": {"byte_start": 44, "byte_end": 91},
  ...
}
```

Keys are string utterance numbers (`"1"`, `"2"`, ...). Values are dicts with:
- `byte_start`: byte index (0-based) of the first character of the speaker label on
  that utterance line in the **raw** transcript file
- `byte_end`: byte index of the last character before the newline (`\n` or `\r\n`)

**Precondition:** the `normalize` step must ensure that each utterance occupies exactly
one physical line (speaker-label prefix on the same line as the utterance text).
Multi-line turns are not supported by this offset model.

**Do not** use the old array format `{"transcript_id": ..., "utterances": [...]}` — the
`register_offsets` validator will reject it with a descriptive error.
```

**Verification:**
Read the updated file and confirm sections are present. No automated test.

**Commit:** `docs: update mpi-transcript-prep SKILL.md — offset format, byte-range definition, single-line invariant`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Update `microphenomenograph/1.0.0/CLAUDE.md` — transcript_prep and offset contract

**Verifies:** None (documentation)

**Files:**
- Modify: `microphenomenograph/1.0.0/CLAUDE.md`

**Implementation:**

Find the `transcript_prep` row in the Substep DAG table. It currently reads:

```
| `transcript_prep` | `hash_raw` → `normalize` → `register_offsets` | per transcript | orchestrator |
```

Add a footnote or inline note below the table (or extend the existing "Documentation-as-Done contract" section) with:

```markdown
**`transcript_prep` offset contract:** `transcripts/offsets/<id>.json` uses a flat-dict
format keyed by string utterance number — `{"1": {"byte_start": N, "byte_end": N}, ...}`.
The `normalize` step enforces the single-line-per-utterance invariant (each utterance on
one physical line). The `register_offsets` validator rejects the old array format
`{"utterances": [...]}`. Byte ranges are anchored to the **raw** transcript file
(`transcripts/raw/<id>.txt`), not the normalized version.
```

**Verification:**
Read the file and confirm the note appears. No automated test.

**Commit:** `docs: add transcript_prep offset format contract to microphenomenograph CLAUDE.md`
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

## Phase 6 completion

**Run full test suite:**
```
cd C:/microphenomenograph
python -m pytest tests/ microphenomenograph/1.0.0/scripts/test_mpi_step.py -v
```
Expected: all tests pass, including AC6 offset-format tests.

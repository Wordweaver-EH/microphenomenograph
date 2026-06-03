# Documentation-as-Done Contract — Plan 2 Implementation Plan

**Goal:** Implement `scripts/irr.py` — a pure-Python module providing Krippendorff α, Cohen's κ, αU, and ARI with bootstrap 95% CIs (N=5000) — replacing `scripts/kappa.py`. Wire automatic IRR calibration into the orchestrator: fires after calibration transcript's diachronic and synchronic complete. Fill the `skills/mpi-irr/SKILL.md` body (shell created in Phase 9). Rename `mpi-kappa` → `mpi-irr` everywhere.

**Architecture:** Pure Python stdlib, ~300–400 LOC total. Four metric calculators + one generic bootstrap function + one top-level `compute_irr` convenience. The coincidence matrix approach follows Krippendorff (2011) with the union-of-categories convention: categories used by only one rater appear with zero diagonal + nonzero marginals (canonical, not a hack). Block bootstrap for αU (block length ≈ √N); naive utterance bootstrap for α, κ, ARI. Existing `kappa.py` logic (load CSV, compute Cohen's κ on diachronic/synchronic tables) merges in without breaking the CSVbased path — that functionality is absorbed into `irr.py`.

**Tech Stack:** Python 3, stdlib only (`math`, `random`, `json`, `csv`, `pathlib`); pytest.

**Scope:** Phase 13 of 13 from original design (Plan 2, phase 6 of 6). Depends on Phase 6 (mpi-analyst per-substep artifacts), Phase 7 (mpi-cross-analyst persistence), Phase 8 (per-transcript SKILL closure), Phase 9 (mpi-irr SKILL shell).

**Codebase verified:** 2026-06-02

---

## Acceptance Criteria Coverage

This phase implements and tests:

### doc-as-done.AC13.1–AC13.10: IRR calibration end-to-end
- **doc-as-done.AC13.1 Success:** `mpi-irr calibrate --participant <pNsN> --stage diachronic|synchronic` runs alternate-agent re-analysis through every substep and writes alternate artifacts to `analyses/independent/`.
- **doc-as-done.AC13.2 Success:** Orchestrator automatically triggers calibration after calibration transcript's `diachronic.idu_naming_ordering` closes and after its last `synchronic.isu_second_level_grouping` closes.
- **doc-as-done.AC13.3 Success:** Alignment substep invokes a fresh mpi-cross-analyst; in assisted mode user accepts/edits; in yolo, auto-accepts with `irr_alignment_auto_accepted` event.
- **doc-as-done.AC13.4 Success:** Coincidence matrix built per Krippendorff (2011) on the union of post-alignment category labels.
- **doc-as-done.AC13.5 Success:** Four metrics with 95% bootstrap CI from N=5000 resamples. Naive utterance resampling for α, κ, ARI; block bootstrap for αU.
- **doc-as-done.AC13.6 Success:** JSONL record matches the schema in DoD #8.
- **doc-as-done.AC13.7 Success:** `outcome = "passed"` iff `alpha.ci_lo >= 0.6`.
- **doc-as-done.AC13.8 Success:** Cross-participant skills emit `irr_warning` if most-recent IRR is `low` or absent.
- **doc-as-done.AC13.9 Failure:** With `--strict-irr` and missing/low IRR, cross-participant stages exit with named ERROR.
- **doc-as-done.AC13.10 Success:** `irr.py` unit tests cover identical inputs → metrics ≈ 1.0; random inputs → metrics ≈ 0; bootstrap completes in <2s for 70-utterance fixture; consistent CIs with fixed seed; asymmetric marginals handled.

### doc-as-done.AC24.1–AC24.4: Calibration transcript configurability
- **doc-as-done.AC24.1–AC24.4 Success:** Calibration transcript strategies (`stratified`, specific id, `first`) work as specified. Stratified produces per-stratum records + aggregate summary.

### doc-as-done.AC25.1–AC25.3: Pre-alignment metrics and sensitivity
- **doc-as-done.AC25.1–AC25.3 Success:** Records include `alpha_pre_alignment`, `alpha_sensitivity_low_conf_excluded`, and `confidence_distribution`.

### doc-as-done.AC31.1–AC31.2: Stratified default and fallback
- **doc-as-done.AC31.1–AC31.2 Success:** Default calibration is `stratified`; `first` is opt-in; stratified with empty strata refused.

### doc-as-done.AC32.1–AC32.3: Block bootstrap for αU
- **doc-as-done.AC32.1–AC32.3 Success:** αU uses block bootstrap (block length ≈ √N); α/κ/ARI use naive utterance; `bootstrap.method` field discloses which scheme.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Create `scripts/irr.py` — metric calculators and bootstrap

**Verifies:** doc-as-done.AC13.4, doc-as-done.AC13.5, doc-as-done.AC13.10, doc-as-done.AC32.1, doc-as-done.AC32.2

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/irr.py`

**Implementation:**

Create `microphenomenograph/1.0.0/scripts/irr.py` with the following functions. All pure Python stdlib — no external deps.

**Public API:**

```python
def compute_coincidence(
    primary_assignments: dict[str, str],   # {utterance_id: category_label}
    alternate_assignments: dict[str, str], # {utterance_id: category_label}
    alignment: list[dict],                  # [{primary, alternate, confidence, ...}]
    unmatched_primary: list[str],
    unmatched_alternate: list[str],
) -> tuple[list[str], dict[tuple, float]]:
    """
    Apply alignment to relabel alternate side, build union-of-categories coincidence matrix.
    Returns (sorted_categories, matrix) where matrix is {(cat_a, cat_b): count}.
    Categories used by only one rater appear with zero diagonal and nonzero marginal.
    """
```

```python
def alpha_nominal(categories: list[str], matrix: dict[tuple, float]) -> float:
    """
    Krippendorff's nominal α on the coincidence matrix.
    Returns float in [-1, 1]. Returns 1.0 for perfect agreement, 0.0 for chance.
    Reference: Krippendorff (2011), Content Analysis, 3rd ed., eq. 1-6.
    """
```

```python
def cohens_kappa(categories: list[str], matrix: dict[tuple, float]) -> float:
    """
    Cohen's κ on the coincidence matrix.
    Returns float in [-1, 1].
    """
```

def alpha_unitizing(
    boundaries_a: list[tuple[int, int]],  # list of (start_utterance, end_utterance) for rater A
    boundaries_b: list[tuple[int, int]],  # same for rater B
    n_utterances: int,
) -> float:
    """
    Krippendorff's unitizing α (αU) for segmentation agreement.
    Operates on raw utterance-range boundaries, label-independent.
    Reference: Krippendorff (2016), Quality & Quantity.
    """
```

```python
def adjusted_rand_index(
    labels_a: list[str],  # per-utterance label list for rater A
    labels_b: list[str],  # per-utterance label list for rater B
) -> float:
    """
    Adjusted Rand Index — label-permutation-invariant partition agreement.
    Reference: Hubert & Arabie (1985).
    """
```

```python
def bootstrap_ci(
    metric_fn,            # callable(labels_a, labels_b) -> float
    utterances_a: list,   # per-utterance labels for rater A
    utterances_b: list,   # per-utterance labels for rater B
    n_bootstrap: int = 5000,
    alpha: float = 0.05,
    seed: int = 42,
    block_length: int | None = None,  # if set, use block bootstrap
) -> dict:
    """
    Naive utterance bootstrap (block_length=None) or block bootstrap (block_length=k).
    Resamples paired (a[i], b[i]) utterances with replacement.
    Returns {point, ci_lo, ci_hi, n_bootstrap, method}.
    method = "naive_utterance" | "block_utterance".
    """
```

```python
def compute_irr(
    primary: dict[str, str],    # {utterance_id: category}
    alternate: dict[str, str],  # {utterance_id: category}
    alignment: list[dict],
    unmatched_primary: list[str],
    unmatched_alternate: list[str],
    n_utterances: int,
    bootstrap_seed: int = 42,
    n_bootstrap: int = 5000,
) -> dict:
    """
    Top-level convenience: runs all four metrics with bootstrap CIs.
    Returns the full JSONL record dict matching the DoD #8 schema.
    """
```

**Implementation notes:**

- `alpha_nominal`: Use the standard Krippendorff formula — $1 - D_o / D_e$ where $D_o$ is the observed disagreement (off-diagonal elements of coincidence matrix weighted by metric difference squared for interval, or simply 0/1 for nominal) and $D_e$ is expected disagreement under independence assumption. For nominal metric: $D_o = 1 - \sum_k m_{kk} / n$ and $D_e$ uses marginal products.
- `cohens_kappa`: Standard formula — $(\text{observed accuracy} - \text{expected accuracy}) / (1 - \text{expected accuracy})$. Compute from the coincidence matrix's diagonal (observed) and marginal products (expected).
- `adjusted_rand_index`: Use the combinatorial formula from Hubert & Arabie (1985). No clustering library needed — compute $a$ (pairs in same cluster in both), $b$ (pairs in different clusters in both), $c$ (one same, one different), $d$ (other case), then the standard ARI formula.
- `alpha_unitizing`: Implement Krippendorff's 2016 boundary-based formula. The metric measures how much raters agree on where segment boundaries fall on the continuum of utterances.
- `bootstrap_ci`: For naive bootstrap: resample indices `range(n)` with replacement; use same indices for both raters. For block bootstrap (αU only): generate contiguous blocks of length `block_length`, concatenate to length n, use as index sequence. Block length for αU is `max(1, round(n**0.5))`. Use `random.Random(seed)` for deterministic resampling.
- `compute_irr`: Same `bootstrap_seed` (shared seed) for α/κ/ARI bootstrap (same bootstrap indices for cross-metric consistency). αU gets its own `random.Random(seed + 1)` to keep block-bootstrap independent.
- Pre-alignment α: compute `alpha_nominal` on the RAW (unaligned) assignments treating non-identical category names as disagreement. Report as `alpha_pre_alignment`.
- Sensitivity α: after dropping alignment mappings with confidence < 0.7, recompute coincidence and α. Report as `alpha_sensitivity_low_conf_excluded`.
- `confidence_distribution`: from the alignment mapping list's `confidence` values: `{min, p25, median, p75, max}`.

**Kappa.py legacy path:** The existing CSV-based Cohen's κ computation in `kappa.py` uses a different input format (CSV with columns Speaker, #, Utterance, Moment, IDU, Criteria). Absorb this into `irr.py` by adding:

```python
def load_diachronic_csv(csv_path) -> dict[str, str]:
    """Load diachronic CSV → {utterance_id: moment_str}. Absorbs kappa.py's load_diachronic."""

def load_synchronic_csv(csv_path) -> dict[str, str]:
    """Load synchronic CSV → {utterance_id: isu_name}. Absorbs kappa.py's load_synchronic."""
```

The existing `test_kappa.py` tests must still pass — they test the CSV loading and κ computation path. Wire them to the new functions in `irr.py`.

**Commit:**
```bash
git add microphenomenograph/1.0.0/scripts/irr.py
git commit -m "feat: implement scripts/irr.py — α, κ, αU, ARI with bootstrap CIs (AC13.4, AC13.5, AC32.1-32.3)"
```
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: `irr.py` unit tests

**Verifies:** doc-as-done.AC13.10, doc-as-done.AC32.3

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/test_irr.py`

**Implementation:**

**Testing:**

- AC13.10 (identical inputs): Build coincidence matrix from perfectly agreeing assignments (all utterances in same category for both raters). Assert all four metrics point ≈ 1.0 (within 0.001). Assert all CI lo > 0.9.
- AC13.10 (random inputs): Generate two random label assignments over 70 utterances (4 categories each, independent). Assert all four metrics point ≈ 0 (|value| < 0.3 for 5000 samples with seed=42).
- AC13.10 (bootstrap speed): Run `compute_irr` on 70-utterance fixture with `n_bootstrap=5000`. Assert elapsed time < 2.0 seconds (use `time.monotonic()`).
- AC13.10 (deterministic CIs): Run bootstrap twice with same seed on same data. Assert results are byte-identical.
- AC13.10 (asymmetric marginals): One rater uses 5 categories, other uses 3 (2 unmatched from the first rater). Build coincidence with union of 5 categories. Assert α is computable (not NaN) and reflects honest disagreement (< 1.0). Assert κ is also computable. Assert both metrics reflect the asymmetric marginals by being < 1.0.
- AC32.3 (block bootstrap vs naive for αU): Create a fixture where utterances are strongly correlated within segments (simulate two raters who mostly agree on boundaries). Assert that block bootstrap CI for αU is WIDER than naive bootstrap CI on the same data (demonstrating naive over-estimates CI tightness). Use 70 utterances, block_length = round(70**0.5) = 8.

Follow existing test patterns in `test_kappa.py` and `test_mpi_step.py` — look at them before writing.

**Verification:**
```
Run: pytest microphenomenograph/1.0.0/scripts/test_irr.py -v
Expected: All tests pass, bootstrap speed test < 2s
```

**Commit:**
```bash
git add microphenomenograph/1.0.0/scripts/test_irr.py
git commit -m "test: irr.py unit tests — metrics, bootstrap, determinism, asymmetric marginals (AC13.10, AC32.3)"
```
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Delete `kappa.py`, update `test_kappa.py` to use `irr.py`

**Verifies:** (test_kappa.py still passes after kappa.py is removed)

**Files:**
- Delete: `microphenomenograph/1.0.0/scripts/kappa.py`
- Modify: `microphenomenograph/1.0.0/scripts/test_kappa.py`

**Implementation:**

The design says: *"`scripts/kappa.py` (existing) is deleted; its logic merges into `irr.py`. Pre-release: no backwards-compatibility shim."*

1. Read `test_kappa.py` to understand what it imports and which functions it calls.
2. Update all imports in `test_kappa.py` from `import kappa` / `from kappa import ...` to `from irr import load_diachronic_csv, load_synchronic_csv, cohens_kappa` (or whichever functions are tested).
3. Update any function call sites in `test_kappa.py` to match the new function signatures in `irr.py`.
4. Delete `kappa.py`.
5. Run `pytest microphenomenograph/1.0.0/scripts/test_kappa.py -v` and confirm all tests pass.

**Note:** The `mpi-kappa/` skill directory was already deleted in Phase 12 Task 3. This task only deletes `kappa.py` (the script file).

**Commit:**
```bash
git rm microphenomenograph/1.0.0/scripts/kappa.py
git add microphenomenograph/1.0.0/scripts/test_kappa.py
git commit -m "refactor: delete kappa.py, update test_kappa.py to use irr.py (pre-release, no shim)"
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-6) -->

<!-- START_TASK_4 -->
### Task 4: Fill `skills/mpi-irr/SKILL.md` body (Phase 9 shell → full content)

**Verifies:** doc-as-done.AC6.3, doc-as-done.AC13.1, doc-as-done.AC13.2, doc-as-done.AC13.8, doc-as-done.AC13.9, doc-as-done.AC24.1, doc-as-done.AC24.2, doc-as-done.AC31.1, doc-as-done.AC31.2

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md`

**Implementation:**

Read the current file (Phase 9 shell). Replace the `> Implementation note (Phase 13)...` block with the full operational body:

Add after the frontmatter and `# mpi-irr` heading, before `## Operation`:

```markdown
## Overview

Automatic inter-rater reliability (IRR) check for model quality. Runs after the calibration
transcript's diachronic and synchronic stages complete. Warning-by-default; opt-in
`--strict-irr` blocks cross-participant stages.

Two IRR checks per run:
1. After `diachronic.idu_naming_ordering` closes for the calibration transcript
2. After `synchronic.isu_second_level_grouping` (last IDU) closes for the calibration transcript

When `study.calibration_transcript = "stratified"`, both checks fire once per calibration
transcript, plus one aggregate summary record per stage.

## Calibration transcript strategy

Set at `/mpi init --calibration <strategy>`. Valid strategies:

| Strategy | Meaning | Notes |
|---|---|---|
| `stratified` | One transcript per (suggestion × IV-level) stratum (default) | Methodologically defensible; requires ≥1 transcript per stratum |
| `<transcript_id>` | Specific transcript (e.g., `p1s1`) | Defensible if pre-chosen and documented |
| `first` | First transcript to complete (smoke-test mode) | Sets `study.calibration_mode = "smoke_test"` in manifest; user must confirm |

If `stratified` is requested but any stratum has zero transcripts, init refuses with
`stratified_unavailable` and prompts the user to pick an alternative.
```

Add the following operational sections:

```markdown
## Calibration workflow

`mpi-irr calibrate --transcript <pNsN> --stage diachronic|synchronic` performs three steps:

### Step 1: `irr_calibration.independent_analyst` (LLM)

Run the alternate-agent analysis through the same substep DAG as the primary, writing
per-substep alternate artifacts to `analyses/independent/<scope>-<stage>.<substep>.{json,md,prompt.json}`.

The alternate agent is a fresh subagent invocation — same agent file (`mpi-analyst` for
per-transcript stages), different session context. It should produce its analysis
independently, without seeing the primary analysis.

### Step 2: `irr_calibration.alignment` (LLM)

A fresh `mpi-cross-analyst` subagent proposes a category mapping between primary and
alternate IDU/ISU sets. Output:
```json
{
  "mapping": [
    {
      "primary": "Initial Sensation",
      "alternate": "First Awareness",
      "confidence": 0.82,
      "rationale": "both describe the opening tactile moment before any imagery"
    }
  ],
  "unmatched_primary": [],
  "unmatched_alternate": []
}
```

In **assisted mode**: surface the proposed mapping via AskUserQuestion for accept/edit.
In **yolo**: auto-accept; emit `irr_alignment_auto_accepted` audit event.

Unmatched categories from either rater are retained in the union (canonical Krippendorff —
they contribute zero-diagonal cells with nonzero marginals, not "structural zeros").

### Step 3: `irr_calibration.agreement_computation` (orchestrator)

Call `scripts/irr.py:compute_irr()` with the aligned assignments. Writes four metrics with
95% bootstrap CIs:

| Metric | Bootstrap | Notes |
|---|---|---|
| Nominal α | Naive utterance | Primary headline metric |
| Cohen's κ | Naive utterance | Secondary; matches manual literally |
| αU | Block (block_length ≈ √N) | Segmentation metric, label-independent |
| ARI | Naive utterance | Label-permutation-invariant sanity check |

Append one structured record to `.mpi/irr_calibration.jsonl`.

`outcome = "passed"` iff `alpha.ci_lo >= 0.6` (conservative against small-N noise).

## IRR warning gate (cross-participant skills)

At the start of each cross-participant stage (`mpi-generic-diachronic`, etc.):

1. Read `.mpi/irr_calibration.jsonl` (most recent record for the upstream stage)
2. If missing or `outcome == "low"`:
   - Emit `irr_warning` audit event with `mpi.blocked_reason: "irr_low|irr_missing"`
   - **Without `--strict-irr`**: proceed with a console warning
   - **With `--strict-irr`**: exit with `irr_check_failed` error before producing any artifact

## Literature thresholds (informational)

Thresholds below are calibrated for *human analysts after training*, not LLM raters.
Transfer to LLM-as-rater is by analogy — treat as convention, not evidence.

| Metric | Tentative | Acceptable | Source |
|---|---|---|---|
| α | ≥ 0.667 | ≥ 0.8 | Krippendorff 2018 |
| κ | ≥ 0.6 | ≥ 0.61 | Sheldrake & Dienes 2025; Landis & Koch 1977 |
| αU | ≥ 0.667 | ≥ 0.8 | Krippendorff 2016 |
| ARI | (no bright-line) | — | Hubert & Arabie 1985 |
```

Keep the existing Closure section (added in Phase 9) unchanged at the end of the file.

**Commit:**
```bash
git add microphenomenograph/1.0.0/skills/mpi-irr/SKILL.md
git commit -m "feat: fill mpi-irr SKILL.md with full calibration workflow (AC13.1-13.9, AC24.1-24.4, AC31.1-31.2)"
```
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Orchestrator hook — auto-trigger IRR after calibration transcript closes

**Verifies:** doc-as-done.AC13.2, doc-as-done.AC13.8, doc-as-done.AC13.9

**Files:**
- Modify: `microphenomenograph/1.0.0/scripts/mpi_step.py`

**Implementation:**

Read `mpi_step.py` fully. The `close` verb's post-commit logic needs to check whether the just-closed substep triggers IRR calibration.

Add after the `git_commit_succeeded` event write in the `close` verb:

```python
def _maybe_trigger_irr_calibration(
    run_dir: Path,
    stage: str,
    substep: str,
    scope: str,
    manifest: dict,
) -> None:
    """
    Check if the just-closed substep triggers IRR calibration.
    Fires for:
      - diachronic.idu_naming_ordering: scope is pNsN (transcript scope)
      - synchronic.isu_second_level_grouping (last IDU): scope is pNsN-iduN

    IMPORTANT: Derive the transcript_id from scope before checking calibration_ids,
    because synchronic scope is pNsN-iduN but calibration_ids contains pNsN.
    """
    calibration_ids = _get_calibration_transcript_ids(manifest)

    # Derive transcript_id from scope (handles both pNsN and pNsN-iduN forms)
    transcript_id = scope.split("-idu")[0]  # "p1s1-idu2" → "p1s1"; "p1s1" → "p1s1"

    if transcript_id not in calibration_ids:
        return

    if stage == "diachronic" and substep == "idu_naming_ordering":
        _schedule_irr_calibration(run_dir, manifest, transcript_id, "diachronic")
    elif stage == "synchronic" and substep == "isu_second_level_grouping":
        # Only trigger after LAST IDU for this transcript
        # _is_last_synchronic_idu checks manifest: all IDUs' isu_second_level_grouping done
        if _is_last_synchronic_idu(manifest, transcript_id):
            _schedule_irr_calibration(run_dir, manifest, transcript_id, "synchronic")
```

The `_schedule_irr_calibration` function appends a `irr_calibration_scheduled` audit event (does not run calibration synchronously — the orchestrator reads these events and dispatches accordingly).

For `_get_calibration_transcript_ids`: read `manifest["study"]["calibration_transcript"]` (or `calibration_transcript_ids` for stratified). If the field is `"first"`, return the first transcript that has any `done` status.

For `_is_last_synchronic_idu`: check the manifest's synchronic substep statuses for all IDUs of the transcript. If all IDUs' `isu_second_level_grouping` substeps are `done` after this close (or only this one remains), return True.

**Add `--strict-irr` pre-check to cross-participant substep close:**

In the `close` verb's pre-checks, for stages in `{"generic_diachronic", "generic_synchronic", "global_synchronic", "hypothesis"}`:

```python
def _check_irr_gate(run_dir: Path, stage: str, substep: str, scope: str, args, audit_path: Path) -> None:
    """
    At the start of each cross-participant close, check IRR calibration outcome.
    - If outcome is low/missing: ALWAYS emit irr_warning audit event.
    - Without --strict-irr: emit warning, then return (proceed).
    - With --strict-irr: emit warning, then exit with irr_check_failed.
    """
    irr_records = _load_irr_records(run_dir)  # reads .mpi/irr_calibration.jsonl
    last_record = irr_records[-1] if irr_records else None
    outcome = last_record.get("outcome") if last_record else None

    if outcome != "passed":
        # Always emit irr_warning, regardless of --strict-irr
        blocked_reason = "irr_low" if outcome == "low" else "irr_missing"
        irr_warning_event = {
            "event_id": str(uuid.uuid4()),
            "@timestamp": _utcnow(),
            "trace_id": _load_run_id(run_dir),
            "span_id": str(uuid.uuid4()),
            "actor": {"kind": "orchestrator", "name": "orchestrator"},
            "event": {"kind": "event", "action": "irr_warning", "outcome": "warning"},
            "mpi": {
                "stage": stage, "substep": substep, "scope": scope,
                "blocked_reason": blocked_reason,
            },
            "reason": f"IRR outcome is {outcome or 'missing'}; proceeding without --strict-irr" if not getattr(args, 'strict_irr', False) else f"IRR outcome is {outcome or 'missing'}; --strict-irr blocks"
        }
        append_jsonl(audit_path, irr_warning_event)

        if getattr(args, 'strict_irr', False):
            sys.stderr.write(f"ERROR: irr_check_failed — IRR outcome is {outcome or 'missing'} (--strict-irr set)\n")
            sys.exit(1)
        # else: proceed (non-strict mode)
```

Add `--strict-irr` flag to the `close` subcommand's argparse.

**Commit:**
```bash
git add microphenomenograph/1.0.0/scripts/mpi_step.py
git commit -m "feat: wire IRR calibration auto-trigger and --strict-irr gate into mpi_step.py (AC13.2, AC13.8, AC13.9)"
```
<!-- END_TASK_5 -->

<!-- START_TASK_6 -->
### Task 6: IRR integration tests + rename mpi-kappa → mpi-irr in test assertions

**Verifies:** doc-as-done.AC13.1, doc-as-done.AC13.6, doc-as-done.AC13.7, doc-as-done.AC24.4, doc-as-done.AC25.1, doc-as-done.AC25.2, doc-as-done.AC25.3, doc-as-done.AC31.1

**Files:**
- Create: `tests/test_irr_calibration.py`
- Modify: `microphenomenograph/1.0.0/scripts/test_mpi_step.py` (add `--strict-irr` tests)
- Modify: `tests/test_plugin_structure.py` (already partially done in Phase 12, but ensure mpi-kappa is removed from expected skills list and mpi-irr is present)

**Implementation:**

**`tests/test_irr_calibration.py`:**

Tests that exercise the IRR calibration flow using fixtures (no LLM):

- AC13.6 (JSONL schema): Build a minimal `irr_calibration.jsonl` record using `irr.compute_irr()` with known assignments. Assert the output dict contains all required fields: `stage`, `participant_id`, `transcript_id`, `primary_model`, `alternate_model`, `alignment`, `metrics.alpha`, `metrics.kappa`, `metrics.alpha_u`, `metrics.ari`, `n_utterances`, `n_bootstrap`, `bootstrap_seed`, `outcome`.
- AC13.7 (outcome rule): Assert `outcome == "passed"` when `alpha.ci_lo >= 0.6`. Assert `outcome == "low"` when `alpha.ci_lo < 0.6`.
- AC25.1 (pre-alignment α): Assert the record contains `metrics.alpha_pre_alignment` with a `point` value.
- AC25.2 (sensitivity α): Assert the record contains `metrics.alpha_sensitivity_low_conf_excluded` with a `point` value.
- AC25.3 (confidence distribution): Assert `alignment.confidence_distribution` contains `min`, `p25`, `median`, `p75`, `max`.
- AC24.4 (stratified aggregate): Build two JSONL records with `record_type: "stratum"`. Compute an aggregate by pooling their bootstrap distributions. Assert the aggregate record has `record_type: "aggregate"`, `n_strata: 2`, and recomputed `metrics.*` values.
- AC31.1 (stratified default): Assert the `irr.py` module's documentation / default calibration mode is `"stratified"` (check docstring or a module-level constant).

**`test_mpi_step.py` additions (`--strict-irr`):**

- With `--strict-irr` and a run dir that has no `.mpi/irr_calibration.jsonl`: close a `generic_diachronic.*` substep and assert exit non-zero with `irr_check_failed`.
- With `--strict-irr` and a `.mpi/irr_calibration.jsonl` containing `outcome: "passed"`: same close succeeds (exit 0).
- Without `--strict-irr` and `outcome: "low"`: close succeeds (exit 0) but audit.jsonl contains an `irr_warning` event.

**Verification:**
```
Run: pytest tests/test_irr_calibration.py microphenomenograph/1.0.0/scripts/test_irr.py microphenomenograph/1.0.0/scripts/test_kappa.py -v
Expected: All tests pass
Run: pytest --tb=short -q
Expected: Full suite passes
```

**Final: Update CLAUDE.md implementation status** (see Phase 12 Task 2 for deferred status flip):
```bash
# After all tests pass, update the implementation status in both CLAUDE.md files
git add microphenomenograph/1.0.0/CLAUDE.md CLAUDE.md
git commit -m "docs: mark Plan 2 all phases landed in CLAUDE.md"
```

**Commit (tests):**
```bash
git add tests/test_irr_calibration.py
git add microphenomenograph/1.0.0/scripts/test_mpi_step.py
git add tests/test_plugin_structure.py
git commit -m "test: IRR calibration integration tests and --strict-irr gate tests (AC13.1, AC13.6, AC13.7, AC24.4, AC25.1-25.3, AC31.1)"
```
<!-- END_TASK_6 -->

<!-- END_SUBCOMPONENT_B -->

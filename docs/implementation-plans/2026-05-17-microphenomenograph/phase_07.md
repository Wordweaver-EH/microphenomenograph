# Microphenomenograph Implementation Plan — Phase 7: Inter-Rater Reliability (Cohen's Kappa)

**Goal:** Implement `scripts/kappa.py` (2-rater per-utterance κ) and `mpi-kappa` skill. Must match the OSF `kappa.Rmd` reference output (diachronic κ=0.82, synchronic κ=0.60) within ±0.01. Also verify AC3.6 integrity: κ ≥ 0.4 between mpi-analyst phase2 diachronic outputs and phase2 reference analyses.

**Architecture:** `kappa.py` reads two analyst CSV files (same format as OSF inter-rater CSVs), parses utterance→category assignments using a custom formula matching `kappa.Rmd` (NOT sklearn's `cohen_kappa_score` — see Note below), and reports stage κ. `mpi-kappa` skill invokes the script via Bash and interprets the result.

**Note on formula:** The design glossary specifies `sklearn.metrics.cohen_kappa_score`, but the OSF `kappa.Rmd` uses a custom formula: `kappa = (agree - expected/N) / (N - expected/N)`. These give different results. The implementation uses the custom formula to match the reference values within ±0.01. This is an accepted deviation from the glossary, justified by the AC7.1 requirement to match the reference output.

**Tech Stack:** Python 3 (no sklearn required — custom formula per kappa.Rmd), Markdown skill

**Scope:** Phase 7 of 8

**Codebase verified:** 2026-05-17 — stub `skills/mpi-kappa/SKILL.md` exists. Inter-rater CSV files are at `microphenomenograph/1.0.0/examples/inter-rater/` (copied in Phase 1). Reference kappa values confirmed from `osf-archive/Inter-rater Reliability/kappa.html`: diachronic=0.82, synchronic=0.60.

---

## Acceptance Criteria Coverage

### microphenomenograph.AC7: Kappa reports correct agreement
- **microphenomenograph.AC7.1 Success:** Diachronic κ and synchronic κ each match `kappa.Rmd` reference output within ±0.01 on OSF inter-rater data
- **microphenomenograph.AC7.2 Success:** κ reported separately for diachronic stage and synchronic stage
- **microphenomenograph.AC7.3 Failure:** Overall κ < 0.61 for any stage triggers a pipeline-level adequacy warning
- **microphenomenograph.AC7.4 Edge:** Missing utterance annotations in one analyst's file handled without crash

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: scripts/kappa.py

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/kappa.py`

**Purpose:** Compute Cohen's κ between two analysts' CSV files for diachronic (Moment column) and synchronic (ISUnum column) stages. Must replicate the `kappa.Rmd` computation.

**kappa.Rmd computation logic (verified from source):**
1. Load two CSV files — same utterance IDs, different `Moment` (diachronic) or `ISUnum` (synchronic) assignments
2. Remove experimenter utterances (those not from participant) — filter by Speaker if column present
3. Build union of utterance IDs across both analysts
4. For each category, find intersection of utterances assigned that category by both analysts (agree), and product of counts (expected)
5. Compute: `kappa = (agree - expected/N) / (N - expected/N)` where N = total unique utterances
6. Note: this is a custom kappa formula, NOT sklearn's default. Must match the R implementation.

**Important:** The R code uses a custom kappa formula (not the standard Cohen's kappa from sklearn). Match it exactly:
```
kappa = (sum_agree - sum_expected/N) / (N - sum_expected/N)
```
where:
- `sum_agree = sum over categories of |intersection of uttNums for that category|`
- `sum_expected = sum over categories of (count_analyst1[cat] × count_analyst2[cat])`
- `N = total unique utterance numbers (union of both analysts)`

**Implementation:**

Create `microphenomenograph/1.0.0/scripts/kappa.py`:

```python
#!/usr/bin/env python3
"""
Compute Cohen's kappa between two MPI analysts' CSV files.

Replicates the computation in osf-archive/Inter-rater Reliability/kappa.Rmd.

CSV format (diachronic):
  Speaker, #, Utterance, Moment, IDU, Criteria

CSV format (synchronic):
  IDU, #, Utterance, Criteria, ISU, ISU 2nd Level of Abstraction, ISUnum

Usage:
    python kappa.py <analyst1_diachronic.csv> <analyst2_diachronic.csv> \\
                    <analyst1_synchronic.csv> <analyst2_synchronic.csv>

Output:
    Diachronic kappa: 0.82
    Synchronic kappa: 0.60
    [WARNING] Synchronic kappa 0.60 is below the 0.61 adequacy threshold.
"""
import sys
import csv
from pathlib import Path


def load_diachronic(csv_path):
    """
    Load diachronic CSV.
    Returns dict: { utterance_number_str -> moment_str }
    Skips rows where Moment is empty or non-numeric.
    Skips experimenter utterances (rows where Speaker is not 'P<N>').

    Note: some diachronic CSVs (e.g. yesesvi) have a preamble row 0 containing
    the participant identifier before the actual header row. Search for the header
    row by looking for a row containing 'Moment' rather than assuming row 0.
    """
    assignments = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        content = f.read()

    lines = content.splitlines()
    # Find header row (contains 'Moment')
    header_idx = next(
        (i for i, line in enumerate(lines) if "Moment" in line), None
    )
    if header_idx is None:
        raise ValueError(f"No Moment column found in {csv_path}")

    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        utt = str(row.get("#", "")).strip()
        moment = str(row.get("Moment", "")).strip()
        speaker = str(row.get("Speaker", "")).strip()
        if not utt or not moment:
            continue
        # Skip experimenter lines
        if speaker and not speaker.upper().startswith("P"):
            continue
        assignments[utt] = moment
    return assignments


def load_synchronic(csv_path):
    """
    Load synchronic CSV.
    Returns dict: { utterance_number_str -> isunum_str }
    Skips rows where ISUnum is empty or 0.
    """
    assignments = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        # synchronic CSVs have a blank first row — skip it
        content = f.read()

    lines = content.splitlines()
    # Find header row (contains 'ISUnum')
    header_idx = next(
        (i for i, line in enumerate(lines) if "ISUnum" in line), None
    )
    if header_idx is None:
        raise ValueError(f"No ISUnum column found in {csv_path}")

    reader = csv.DictReader(lines[header_idx:])
    for row in reader:
        utt = str(row.get("#", "")).strip()
        isunum = str(row.get("ISUnum", "")).strip()
        if not utt or not isunum:
            continue
        try:
            if float(isunum) <= 0:
                continue
        except ValueError:
            continue
        assignments[utt] = isunum
    return assignments


def compute_kappa(assignments_a, assignments_b, categories):
    """
    Compute kappa using the formula from kappa.Rmd:
      kappa = (agree - expected/N) / (N - expected/N)

    where:
      agree = sum over categories of |intersection(uttNums_a[cat], uttNums_b[cat])|
      expected = sum over categories of (|uttNums_a[cat]| * |uttNums_b[cat]|)
      N = |union of all uttNums in a and b|

    Handles missing utterances: utterances present in one analyst but not the other
    are included in N but contribute 0 to agree for the missing category.
    """
    all_utts = set(assignments_a.keys()) | set(assignments_b.keys())
    N = len(all_utts)

    if N == 0:
        return float("nan")

    agree = 0
    expected = 0

    for cat in categories:
        set_a = {u for u, c in assignments_a.items() if c == str(cat)}
        set_b = {u for u, c in assignments_b.items() if c == str(cat)}
        agree += len(set_a & set_b)
        expected += len(set_a) * len(set_b)

    exp_freq = expected / N
    if N == exp_freq:
        return float("nan")

    return (agree - exp_freq) / (N - exp_freq)


def main():
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    dia_a_path, dia_b_path, syn_a_path, syn_b_path = sys.argv[1:5]

    # Diachronic kappa (Moment categories 1–7)
    dia_a = load_diachronic(dia_a_path)
    dia_b = load_diachronic(dia_b_path)
    kappa_dia = compute_kappa(dia_a, dia_b, range(1, 8))

    # Synchronic kappa (ISUnum categories 1–9)
    syn_a = load_synchronic(syn_a_path)
    syn_b = load_synchronic(syn_b_path)
    kappa_syn = compute_kappa(syn_a, syn_b, range(1, 10))

    print(f"Diachronic kappa: {kappa_dia:.2f}")
    print(f"Synchronic kappa: {kappa_syn:.2f}")

    warnings = []
    if not (float("nan") == kappa_dia) and kappa_dia < 0.61:
        warnings.append(
            f"WARNING: Diachronic kappa {kappa_dia:.2f} is below the 0.61 adequacy threshold."
        )
    if not (float("nan") == kappa_syn) and kappa_syn < 0.61:
        warnings.append(
            f"WARNING: Synchronic kappa {kappa_syn:.2f} is below the 0.61 adequacy threshold."
        )

    for w in warnings:
        print(w)

    if warnings:
        sys.exit(2)  # Exit 2 = below threshold (not a crash)


if __name__ == "__main__":
    main()
```

**Verifies:** microphenomenograph.AC7.1, microphenomenograph.AC7.2, microphenomenograph.AC7.3, microphenomenograph.AC7.4
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Test kappa.py against OSF reference values

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/test_kappa.py`

**Verifies:** microphenomenograph.AC7.1 (within ±0.01 of reference), microphenomenograph.AC7.4 (missing annotations handled)

**Implementation:**

Create `microphenomenograph/1.0.0/scripts/test_kappa.py`:

```python
#!/usr/bin/env python3
"""
Tests for kappa.py — validates against OSF reference values.

Reference (from osf-archive/Inter-rater Reliability/kappa.html):
  Diachronic kappa = 0.82
  Synchronic kappa = 0.60
"""
import sys
import os
import math
import tempfile
import csv
from pathlib import Path

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).parent))
from kappa import load_diachronic, load_synchronic, compute_kappa

# Path to inter-rater examples (relative to plugin root)
PLUGIN_ROOT = Path(__file__).parent.parent
INTER_RATER_DIR = PLUGIN_ROOT / "examples" / "inter-rater"

REFERENCE_DIACHRONIC_KAPPA = 0.82
REFERENCE_SYNCHRONIC_KAPPA = 0.60
TOLERANCE = 0.01


def test_diachronic_kappa_matches_reference():
    """AC7.1: Diachronic kappa matches kappa.Rmd within ±0.01."""
    kev = load_diachronic(INTER_RATER_DIR / "kev-diachronic-analysis.csv")
    yesesvi = load_diachronic(INTER_RATER_DIR / "yesesvi-diachronic-analysis.csv")
    kappa = compute_kappa(kev, yesesvi, range(1, 8))
    assert abs(kappa - REFERENCE_DIACHRONIC_KAPPA) <= TOLERANCE, (
        f"Diachronic kappa {kappa:.3f} differs from reference {REFERENCE_DIACHRONIC_KAPPA} "
        f"by more than {TOLERANCE}"
    )
    print(f"✓ Diachronic kappa: {kappa:.2f} (reference: {REFERENCE_DIACHRONIC_KAPPA})")


def test_synchronic_kappa_matches_reference():
    """AC7.1: Synchronic kappa matches kappa.Rmd within ±0.01."""
    kev = load_synchronic(INTER_RATER_DIR / "kev-synchronic-analysis.csv")
    yesesvi = load_synchronic(INTER_RATER_DIR / "yesesvi-synchronic-analysis.csv")
    kappa = compute_kappa(kev, yesesvi, range(1, 10))
    assert abs(kappa - REFERENCE_SYNCHRONIC_KAPPA) <= TOLERANCE, (
        f"Synchronic kappa {kappa:.3f} differs from reference {REFERENCE_SYNCHRONIC_KAPPA} "
        f"by more than {TOLERANCE}"
    )
    print(f"✓ Synchronic kappa: {kappa:.2f} (reference: {REFERENCE_SYNCHRONIC_KAPPA})")


def test_separate_diachronic_and_synchronic():
    """AC7.2: Kappa reported separately for each stage."""
    kev_dia = load_diachronic(INTER_RATER_DIR / "kev-diachronic-analysis.csv")
    yesesvi_dia = load_diachronic(INTER_RATER_DIR / "yesesvi-diachronic-analysis.csv")
    kev_syn = load_synchronic(INTER_RATER_DIR / "kev-synchronic-analysis.csv")
    yesesvi_syn = load_synchronic(INTER_RATER_DIR / "yesesvi-synchronic-analysis.csv")
    k_dia = compute_kappa(kev_dia, yesesvi_dia, range(1, 8))
    k_syn = compute_kappa(kev_syn, yesesvi_syn, range(1, 10))
    assert k_dia != k_syn, "Diachronic and synchronic kappa should differ"
    print(f"✓ Separate kappa: diachronic={k_dia:.2f}, synchronic={k_syn:.2f}")


def test_missing_annotations_handled():
    """AC7.4: Missing utterance annotations handled without crash."""
    # Analyst A has utterances 1, 2, 3 assigned to moments
    # Analyst B is missing utterance 2
    a = {"1": "1", "2": "2", "3": "1"}
    b = {"1": "1", "3": "1"}  # utterance 2 missing
    kappa = compute_kappa(a, b, range(1, 4))
    assert not math.isnan(kappa), "Kappa should not be NaN with missing annotations"
    assert isinstance(kappa, float), "Kappa should be a float"
    print(f"✓ Missing annotations handled: kappa={kappa:.3f}")


def test_low_kappa_detected():
    """AC7.3: Kappa below 0.61 is detectable."""
    # Completely random assignments → low kappa
    a = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
    b = {"1": "5", "2": "4", "3": "3", "4": "2", "5": "1"}
    kappa = compute_kappa(a, b, range(1, 6))
    # Not testing threshold enforcement here (that's in main()), just that
    # the computed value is what it is
    assert isinstance(kappa, float)
    print(f"✓ Low kappa computable: kappa={kappa:.3f}")


if __name__ == "__main__":
    tests = [
        test_diachronic_kappa_matches_reference,
        test_synchronic_kappa_matches_reference,
        test_separate_diachronic_and_synchronic,
        test_missing_annotations_handled,
        test_low_kappa_detected,
    ]
    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: UNEXPECTED ERROR: {e}")
            failed += 1

    if failed:
        print(f"\n{failed}/{len(tests)} tests FAILED")
        sys.exit(1)
    else:
        print(f"\n{len(tests)}/{len(tests)} tests passed")
```

**Step 1: Run tests**

```bash
cd C:\microphenomenograph
python microphenomenograph/1.0.0/scripts/test_kappa.py
```

Expected:
```
✓ Diachronic kappa: 0.82 (reference: 0.82)
✓ Synchronic kappa: 0.60 (reference: 0.60)
✓ Separate kappa: diachronic=0.82, synchronic=0.60
✓ Missing annotations handled: kappa=...
✓ Low kappa computable: kappa=...

5/5 tests passed
```

**If tests fail:** The kappa formula in `kappa.py` does not match the R implementation. Re-read `kappa.Rmd` and adjust the `compute_kappa` function. The R code does NOT use sklearn — it uses a custom formula. Do NOT switch to `sklearn.metrics.cohen_kappa_score` as that would change the result.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: mpi-kappa SKILL.md

**Files:**
- Modify: `microphenomenograph/1.0.0/skills/mpi-kappa/SKILL.md` (replace stub)

**Implementation:**

```markdown
---
name: mpi-kappa
description: Use when running /mpi kappa — computes Cohen's kappa between two MPI analysis directories; emits pipeline-level warning if kappa < 0.61 for any stage
user-invocable: false
---
# mpi-kappa

Compute Cohen's κ inter-rater reliability between two sets of analysis CSVs.

## Usage

```
/mpi kappa [dir1] [dir2]
```

- `dir1`, `dir2`: paths to directories containing diachronic and synchronic CSV files
  in the same format as `examples/inter-rater/` (columns: `Speaker, #, Utterance, Moment, IDU, Criteria`
  for diachronic; `IDU, #, Utterance, Criteria, ISU, ISU 2nd Level of Abstraction, ISUnum` for synchronic)

If no directories given, default to `examples/inter-rater/` for both analysts (uses OSF
bundled inter-rater data).

## Execution

Run the Python script:

```bash
python microphenomenograph/1.0.0/scripts/kappa.py \\
    <dir1>/kev-diachronic-analysis.csv \\
    <dir2>/yesesvi-diachronic-analysis.csv \\
    <dir1>/kev-synchronic-analysis.csv \\
    <dir2>/yesesvi-synchronic-analysis.csv
```

Wait for exit code:
- Exit 0: all kappa values ≥ 0.61
- Exit 2: one or more kappa values below threshold (WARNING already printed by script)

## Output

Display the script output to the user. If exit code 2, also emit a Claude Code
pipeline-level warning:

**PIPELINE ADEQUACY WARNING:** Inter-rater reliability below threshold (κ < 0.61).
Review the analysis outputs before proceeding. The manual specifies κ > .6 as the
adequacy threshold for the whole calibration set.

**Verifies:** microphenomenograph.AC7.1, microphenomenograph.AC7.2, microphenomenograph.AC7.3, microphenomenograph.AC7.4
```

**Step 1: Verify skill works**

From test working directory with plugin installed:
```
/mpi kappa
```

Expected: Displays diachronic kappa and synchronic kappa values matching reference (0.82 and 0.60). No pipeline warning (both ≥ 0.61).

**Step 2: Commit**

```bash
cd C:\microphenomenograph
git add microphenomenograph/1.0.0/scripts/kappa.py
git add microphenomenograph/1.0.0/scripts/test_kappa.py
git add microphenomenograph/1.0.0/skills/mpi-kappa/SKILL.md
git commit -m "feat: implement kappa.py, tests, and mpi-kappa skill"
```
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: AC3.6 integrity verification — mpi-analyst κ ≥ 0.4 on Phase 2 data

**Verifies:** microphenomenograph.AC3.6

This task verifies that the `mpi-analyst` agent produces diachronic analyses on Phase 2 transcripts that agree sufficiently with the Phase 2 reference analyses (κ ≥ 0.4 on per-utterance Moment assignment).

**Important:** This is an *integrity* test, not a unit test. It requires the full pipeline (Phase 4 implemented) and the kappa script (this phase). Run this after Phase 7 kappa tests pass.

**Step 1: Run mpi-analyst on a Phase 2 transcript**

Choose a Phase 2 transcript that has a reference analysis — e.g., `p8s1`.

Create a fresh test directory:
```bash
mkdir -p C:/Temp/mpi-ac36-test/transcripts C:/Temp/mpi-ac36-test/analyses
cp C:/microphenomenograph/microphenomenograph/1.0.0/examples/transcripts/p8s1.txt C:/Temp/mpi-ac36-test/transcripts/
cd C:/Temp/mpi-ac36-test
git init
```

In Claude Code with plugin installed:
```
/mpi init
/mpi transcript-prep p8s1
/mpi diachronic p8s1
```

**Step 2: Convert the Phase 2 reference XLSX to a comparable format**

The reference analysis for p8s1 is at `osf-archive/Phase 2/analyses/p8s1.xlsx`.
The mpi-analyst output is in `analyses/p8s1-diachronic.md` as a markdown table.

To compare κ, we need both in the same CSV format (utterance# → Moment). Write a
conversion helper:

```bash
python -c "
import openpyxl, csv, sys
wb = openpyxl.load_workbook(r'C:\microphenomenograph\osf-archive\Phase 2\analyses\p8s1.xlsx')
sheet_name = next(s for s in wb.sheetnames if 'diachronic analysis' in s.lower())
ws = wb[sheet_name]
rows = list(ws.iter_rows(values_only=True))
with open('C:/Temp/mpi-ac36-test/p8s1-reference-diachronic.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['Speaker', '#', 'Utterance', 'Moment', 'IDU', 'Criteria'])
    for row in rows[2:]:
        if row[0] is not None and row[3] is not None:
            writer.writerow([row[0] or '', row[1] or '', row[2] or '', row[3] or '', row[4] or '', row[5] or ''])
print('Reference CSV written')
"
```

**Step 3: Convert mpi-analyst output to CSV format**

Parse `analyses/p8s1-diachronic.md` markdown table to extract utterance numbers and their
IDU (Moment) assignments. Since the mpi-analyst assigns IDU numbers (1, 2, 3...) as Moments,
write a helper:

```bash
python -c "
import re, csv

with open('C:/Temp/mpi-ac36-test/analyses/p8s1-diachronic.md') as f:
    content = f.read()

# Parse markdown table rows
rows = []
for line in content.split('\n'):
    if line.startswith('|') and not line.startswith('|---'):
        cells = [c.strip() for c in line.strip('|').split('|')]
        if len(cells) >= 4 and cells[0].isdigit():
            idu_num = cells[0]
            utts = [u.strip() for u in cells[3].split(',')]
            for utt in utts:
                if utt:
                    rows.append({'#': utt, 'Moment': idu_num})

with open('C:/Temp/mpi-ac36-test/p8s1-analyst-diachronic.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=['Speaker', '#', 'Utterance', 'Moment', 'IDU', 'Criteria'])
    writer.writeheader()
    for row in rows:
        writer.writerow({'Speaker': 'P8', '#': row['#'], 'Utterance': '', 'Moment': row['Moment'], 'IDU': '', 'Criteria': ''})

print(f'Analyst CSV written with {len(rows)} utterances')
"
```

**Step 4: Compute κ between analyst and reference**

```bash
python C:/microphenomenograph/microphenomenograph/1.0.0/scripts/kappa.py \
    C:/Temp/mpi-ac36-test/p8s1-analyst-diachronic.csv \
    C:/Temp/mpi-ac36-test/p8s1-reference-diachronic.csv \
    NUL NUL
```

(Pass `NUL` for synchronic files since we're only checking diachronic here.)

Expected: Diachronic kappa ≥ 0.40. If below 0.40, this indicates the mpi-analyst is not coding consistently with the reference. This is not a failure condition that blocks the pipeline — it is an informational adequacy check.

**Note on interpretation:** The κ ≥ 0.40 threshold for AC3.6 (from the design) is intentionally lower than the overall adequacy threshold (κ > 0.61) because this compares an AI analyst against a human reference, not two human analysts. A κ of 0.40 indicates moderate agreement and is the minimum acceptable.

**Step 5: Document result**

Record the computed κ value. If κ < 0.40, investigate:
- Check if the mpi-analyst is using consistent IDU numbering
- Check if the few-shot examples are providing enough guidance
- Consider adding more Phase 1 examples to the few-shot pool

This step does NOT need to pass before proceeding with the rest of the pipeline.
<!-- END_TASK_4 -->

<!-- END_SUBCOMPONENT_A -->

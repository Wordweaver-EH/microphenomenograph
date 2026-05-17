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
python microphenomenograph/1.0.0/scripts/kappa.py \
    <dir1>/*-diachronic-analysis.csv \
    <dir2>/*-diachronic-analysis.csv \
    <dir1>/*-synchronic-analysis.csv \
    <dir2>/*-synchronic-analysis.csv
```

**Important:** Each glob pattern should match exactly one CSV file per analyst. The execution expects exactly one `*-diachronic-analysis.csv` and one `*-synchronic-analysis.csv` per directory.

**Default (no arguments):** Uses OSF bundled inter-rater data with filenames `kev-diachronic-analysis.csv`,
`yesesvi-diachronic-analysis.csv`, etc. in `examples/inter-rater/`.

**User-provided directories:** Should contain `*-diachronic-analysis.csv` and `*-synchronic-analysis.csv`
files (analyst identifiers in place of `*`).

**Note:** The script automatically detects yesesvi files by filename and applies recoding transformations
only to those files. Kev files are loaded without recoding.

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

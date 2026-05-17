#!/usr/bin/env python3
"""
Compute Cohen's kappa between two MPI analysts' CSV files.

Replicates the computation in osf-archive/Inter-rater Reliability/kappa.Rmd.

CSV format (diachronic):
  Speaker, #, Utterance, Moment, IDU, Criteria

CSV format (synchronic):
  IDU, #, Utterance, Criteria, ISU, ISU 2nd Level of Abstraction, ISUnum

Usage:
    python kappa.py <analyst1_diachronic.csv> <analyst2_diachronic.csv> \
                    <analyst1_synchronic.csv> <analyst2_synchronic.csv>

Output:
    Diachronic kappa: 0.82
    Synchronic kappa: 0.60
    [WARNING] Synchronic kappa 0.60 is below the 0.61 adequacy threshold.
"""
import sys
import csv
import math
from pathlib import Path


def load_diachronic(csv_path):
    """
    Load diachronic CSV.
    Returns dict: { utterance_number_str -> moment_str }
    Filters out experimenter utterances by utterance number (BEFORE recoding).
    Applies recoding for yesesvi files ONLY (identified by 'yesesvi' in filename).
    Keeps utterances with empty Moment using '' as sentinel so they count toward N.

    Note: some diachronic CSVs (e.g. yesesvi) have a preamble row 0 containing
    the participant identifier before the actual header row. Search for the header
    row by looking for a row containing 'Moment' rather than assuming row 0.
    """
    # Experimenter utterance numbers to filter (from kappa.Rmd line 51)
    # MUST apply filter BEFORE recoding, so use the original utterance numbers
    experimenter_utts = {'10', '21', '23', '29', '12', '14', '16', '19', '39', '27', '31', '33', '35', '37', '25'}

    # Check if this is a yesesvi file to determine if recoding should apply
    is_yesesvi = 'yesesvi' in str(csv_path).lower()

    # Recoding for yesesvi utterance numbers (applied AFTER filtering, yesesvi only)
    utt_recode = {'22': '22.1', '22a': '22.2', '22b': '22.3', '15': '15.2', '15a': '15.1'} if is_yesesvi else {}

    # Recoding for yesesvi Moment values (yesesvi only)
    moment_recode = {'6': '7'} if is_yesesvi else {}

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

        # Skip rows with empty utterance number
        if not utt:
            continue

        # Filter experimenter utterances BEFORE recoding
        if utt in experimenter_utts:
            continue

        # Apply recoding AFTER filtering (for yesesvi only, others pass through unchanged)
        utt = utt_recode.get(utt, utt)
        moment = moment_recode.get(moment, moment) if moment else ''

        assignments[utt] = moment
    return assignments


def load_synchronic(csv_path):
    """
    Load synchronic CSV.
    Returns dict: { utterance_number_str -> isunum_str }
    Applies recoding for yesesvi files ONLY (identified by 'yesesvi' in filename).
    Keeps utterances with empty ISUnum using '' as sentinel so they count toward N.
    Skips rows where ISUnum is <= 0 (numeric check only if valid number).
    Filters out experimenter utterances by utterance number.
    """
    # Experimenter utterance numbers to filter (from kappa.Rmd line 53)
    experimenter_utts = {'10', '21', '23', '29', '12', '14', '16', '19', '39', '27', '31', '33', '35', '37', '25'}

    # Check if this is a yesesvi file to determine if recoding should apply
    is_yesesvi = 'yesesvi' in str(csv_path).lower()

    # Recoding for yesesvi utterance numbers (yesesvi only)
    utt_recode = {'22': '22.1', '22a': '22.2', '22b': '22.3', '15': '15.2', '15a': '15.1'} if is_yesesvi else {}

    assignments = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
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

        # Skip rows with empty utterance number
        if not utt:
            continue

        # Filter experimenter utterances
        if utt in experimenter_utts:
            continue

        # Check if ISUnum is a positive number; skip if not
        if isunum:
            try:
                if float(isunum) <= 0:
                    continue
            except ValueError:
                continue
            # Valid positive ISUnum
        else:
            # Empty ISUnum: use sentinel
            isunum = ''

        # Apply recoding (for yesesvi only, others pass through unchanged)
        utt = utt_recode.get(utt, utt)

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
    if not math.isnan(kappa_dia) and kappa_dia < 0.61:
        warnings.append(
            f"WARNING: Diachronic kappa {kappa_dia:.2f} is below the 0.61 adequacy threshold."
        )
    if not math.isnan(kappa_syn) and kappa_syn < 0.61:
        warnings.append(
            f"WARNING: Synchronic kappa {kappa_syn:.2f} is below the 0.61 adequacy threshold."
        )

    for w in warnings:
        print(w)

    if warnings:
        sys.exit(2)  # Exit 2 = below threshold (not a crash)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
IRR calibration module — Krippendorff α, Cohen's κ, αU (approximation), ARI with bootstrap CIs.

Implements inter-rater reliability (IRR) metrics for MPI analysis quality assessment.
Pure Python stdlib (no external dependencies).

Key functions:
  - load_diachronic_csv: Load diachronic CSV (absorbs kappa.py's logic)
  - load_synchronic_csv: Load synchronic CSV (absorbs kappa.py's logic)
  - compute_coincidence: Build union-of-categories coincidence matrix
  - alpha_nominal: Krippendorff's nominal α (primary metric)
  - cohens_kappa: Cohen's κ (secondary, literal match to manual)
  - alpha_unitizing: Boundary-agreement approximation for segmentation (label-independent)
  - adjusted_rand_index: ARI (label-permutation-invariant sanity check)
  - bootstrap_ci: Naive utterance or block bootstrap for CIs
  - compute_irr: Top-level convenience — all 4 metrics with bootstrap CIs

Default calibration mode: "stratified" (one transcript per IV-level stratum).
"""
import csv
import math
import random
from pathlib import Path


DEFAULT_CALIBRATION_MODE = "stratified"


# ---------------------------------------------------------------------------
# CSV loaders (absorbing kappa.py logic)
# ---------------------------------------------------------------------------

def load_diachronic_csv(csv_path):
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


def load_synchronic_csv(csv_path):
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


# ---------------------------------------------------------------------------
# Shared utterance sorting
# ---------------------------------------------------------------------------

def _utt_sort_key(utterance_id: str) -> tuple:
    """
    Parse utterance ID into numeric tuple for sorting.
    Handles both integer strings ("1", "10", "2") and dotted strings ("22.1", "22.2").

    Returns tuple of integers for lexicographic (numeric) sorting.

    Examples:
      "1" -> (1,)
      "10" -> (10,)
      "2" -> (2,)
      "22.1" -> (22, 1)
      "22.2" -> (22, 2)
    """
    utt_str = str(utterance_id)
    parts = utt_str.split('.')
    try:
        # All parts should be numeric
        return tuple(int(p) for p in parts)
    except ValueError:
        # Fallback: try to extract leading numeric part
        numeric_part = ""
        for char in utt_str:
            if char.isdigit():
                numeric_part += char
            else:
                break
        if numeric_part:
            return (int(numeric_part),)
        # Last resort: return 0 for non-numeric strings
        return (0,)


# ---------------------------------------------------------------------------
# Core metric functions
# ---------------------------------------------------------------------------

def compute_coincidence(
    primary_assignments: dict,
    alternate_assignments: dict,
    alignment: list,
    unmatched_primary: list,
    unmatched_alternate: list,
) -> tuple:
    """
    Apply alignment to relabel alternate side, build union-of-categories coincidence matrix.

    Returns (sorted_categories, matrix) where matrix is {(cat_a, cat_b): count}.
    Categories used by only one rater appear with zero diagonal and nonzero marginals
    (canonical Krippendorff union-of-categories convention).

    Args:
        primary_assignments: {utterance_id: category_label}
        alternate_assignments: {utterance_id: category_label}
        alignment: [{primary, alternate, confidence, ...}, ...]
        unmatched_primary: [category_label, ...]
        unmatched_alternate: [category_label, ...]
    """
    # Build alignment mapping: alternate category → primary category
    alignment_map = {}
    for entry in alignment:
        primary_cat = entry.get("primary")
        alternate_cat = entry.get("alternate")
        if primary_cat and alternate_cat:
            alignment_map[alternate_cat] = primary_cat

    # Collect all unique categories (union)
    all_categories = set(primary_assignments.values()) | set(alternate_assignments.values())
    for cat in unmatched_primary + unmatched_alternate:
        all_categories.add(cat)

    sorted_categories = sorted(all_categories)

    # Build coincidence matrix: count matches per (primary, aligned_alternate) pair
    matrix = {}
    for cat_a, cat_b in [(c1, c2) for c1 in sorted_categories for c2 in sorted_categories]:
        matrix[(cat_a, cat_b)] = 0.0

    # Collect utterance IDs (union of both raters)
    all_utterances = set(primary_assignments.keys()) | set(alternate_assignments.keys())

    for utt_id in all_utterances:
        cat_a = primary_assignments.get(utt_id, "")
        cat_b = alternate_assignments.get(utt_id, "")

        # Apply alignment: map cat_b using the alignment map
        if cat_b in alignment_map:
            cat_b_aligned = alignment_map[cat_b]
        else:
            cat_b_aligned = cat_b

        # Ensure categories are in sorted_categories
        if cat_a not in sorted_categories:
            cat_a = ""
        if cat_b_aligned not in sorted_categories:
            cat_b_aligned = ""

        # Increment coincidence count
        if (cat_a, cat_b_aligned) in matrix:
            matrix[(cat_a, cat_b_aligned)] += 1.0

    return sorted_categories, matrix


def compute_kappa(assignments_a, assignments_b, categories):
    """
    Legacy wrapper: compute Cohen's kappa from two assignment dicts.
    Used by test_kappa.py for backward compatibility with the old kappa.py API.

    Args:
        assignments_a: {utterance_id: category_str}
        assignments_b: {utterance_id: category_str}
        categories: iterable of category values (e.g., range(1, 8))

    Returns: float (Cohen's kappa)
    """
    _, matrix = compute_coincidence(assignments_a, assignments_b, [], [], [])
    sorted_categories = sorted(str(c) for c in categories)
    return cohens_kappa(sorted_categories, matrix)


def alpha_nominal(categories: list, matrix: dict) -> float:
    """
    Krippendorff's nominal α on the coincidence matrix.
    Returns float in [-1, 1]. Returns 1.0 for perfect agreement, 0.0 for chance.

    Formula: α = 1 - (D_o / D_e)
    where D_o is observed disagreement (off-diagonal), D_e is expected disagreement.

    Reference: Krippendorff (2011), Content Analysis, 3rd ed., eq. 1-6.
    """
    # Calculate total count
    total = sum(matrix.values())

    if total == 0:
        return 0.0

    # If only one category, return perfect agreement
    if len(categories) <= 1:
        return 1.0

    # Observed disagreement: off-diagonal elements (all non-matching pairs)
    d_o = sum(
        matrix.get((cat_a, cat_b), 0.0)
        for cat_a in categories
        for cat_b in categories
        if cat_a != cat_b
    ) / total

    # Expected disagreement under independence
    # For nominal metric: D_e = 1 - Σ(n_k / n)²
    # where n_k is the marginal count for category k
    marginals = {}
    for cat in categories:
        n_k = sum(matrix.get((cat, cat_b), 0.0) for cat_b in categories)
        marginals[cat] = n_k

    # Calculate D_e using marginal products
    d_e = 0.0
    for cat_a in categories:
        for cat_b in categories:
            if cat_a != cat_b:
                # Probability of pair being different by chance
                n_a = marginals.get(cat_a, 0.0)
                n_b = marginals.get(cat_b, 0.0)
                d_e += (n_a / total) * (n_b / total)

    if d_e == 0.0:
        # Perfect expected disagreement would be 0, meaning all same category
        return 1.0 if d_o == 0.0 else 0.0

    alpha = 1.0 - (d_o / d_e)
    return alpha


def cohens_kappa(categories: list, matrix: dict) -> float:
    """
    Cohen's κ on the coincidence matrix.
    Returns float in [-1, 1].

    Formula: κ = (p_o - p_e) / (1 - p_e)
    where p_o is observed proportion of agreement, p_e is expected by chance.
    """
    total = sum(matrix.values())

    if total == 0:
        return 0.0

    # If only one category, return perfect agreement
    if len(categories) <= 1:
        return 1.0

    # Observed agreement: diagonal elements
    p_o = sum(matrix.get((cat, cat), 0.0) for cat in categories) / total

    # Expected agreement by chance (marginal products)
    p_e = 0.0
    for cat in categories:
        n_a = sum(matrix.get((cat, cat_b), 0.0) for cat_b in categories)
        n_b = sum(matrix.get((cat_c, cat), 0.0) for cat_c in categories)
        p_e += (n_a / total) * (n_b / total)

    if p_e >= 1.0:
        return 1.0 if p_o == p_e else -1.0

    denominator = 1.0 - p_e
    if denominator == 0.0:
        return 1.0 if p_o == 1.0 else 0.0

    kappa = (p_o - p_e) / denominator
    return kappa


def alpha_unitizing(
    boundaries_a: list,
    boundaries_b: list,
    n_utterances: int,
) -> float:
    """
    Segmentation agreement metric (αU approximation).

    This is a boundary-agreement approximation, not the canonical length-weighted
    Krippendorff αU continuum formula. The metric is chance-corrected via bootstrap.

    Operates on raw utterance-range boundaries, label-independent.

    Args:
        boundaries_a: list of (start_utterance, end_utterance) tuples for rater A
        boundaries_b: list of (start_utterance, end_utterance) tuples for rater B
        n_utterances: total number of utterances

    Reference: Krippendorff (2016), Quality & Quantity.
    """
    if n_utterances == 0:
        return 1.0

    # If no boundaries from either rater, perfect agreement
    if not boundaries_a and not boundaries_b:
        return 1.0

    # Convert boundaries to sets of transition positions (where boundaries occur)
    # A boundary (start, end) contributes transitions at start and end positions
    transitions_a = set()
    for start, end in boundaries_a:
        if start > 0:
            transitions_a.add(start)
        if end < n_utterances:
            transitions_a.add(end)

    transitions_b = set()
    for start, end in boundaries_b:
        if start > 0:
            transitions_b.add(start)
        if end < n_utterances:
            transitions_b.add(end)

    # If both have no boundaries, return 1.0
    if not transitions_a and not transitions_b:
        return 1.0

    # Agreement: positions where both have a boundary or both don't
    all_positions = set(range(1, n_utterances))  # Positions where boundaries can occur

    if not all_positions:
        return 1.0

    # Intersection: positions where both agree on boundary existence
    agreed_positions = (transitions_a & transitions_b) | (all_positions - transitions_a - transitions_b)
    agreement_count = len(agreed_positions)

    # αU ≈ (2 * agreement) / (all_positions) for simple approximation
    # More formally: compare observed vs expected disagreement
    if len(all_positions) == 0:
        return 1.0

    au = 2.0 * agreement_count / len(all_positions) - 1.0
    return max(-1.0, min(1.0, au))  # Clamp to [-1, 1]


def adjusted_rand_index(labels_a: list, labels_b: list) -> float:
    """
    Adjusted Rand Index — label-permutation-invariant partition agreement.
    Compares two partitioning/clustering schemes, invariant to label renaming.

    Returns float in [-1, 1].

    Formula (Hubert & Arabie 1985):
      ARI = (sum_ij C(n_ij,2) − [sum_i C(a_i,2) · sum_j C(b_j,2)] / C(n,2))
            / (½[sum_i C(a_i,2) + sum_j C(b_j,2)] − [sum_i C(a_i,2)·sum_j C(b_j,2)] / C(n,2))

    where C(k,2) = k(k-1)/2, n_ij is the contingency cell count, a_i is row sum, b_j is column sum.

    Reference: Hubert & Arabie (1985), Comparing Partitions. J. Classification.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("labels_a and labels_b must have same length")

    n = len(labels_a)
    if n <= 1:
        return 1.0 if labels_a == labels_b else 0.0

    # Build contingency table: count occurrences of each (label_a, label_b) pair
    contingency = {}
    for a, b in zip(labels_a, labels_b):
        key = (a, b)
        contingency[key] = contingency.get(key, 0) + 1

    # Row sums (a_i) and column sums (b_j)
    row_sums = {}
    col_sums = {}
    for (a, b), count in contingency.items():
        row_sums[a] = row_sums.get(a, 0) + count
        col_sums[b] = col_sums.get(b, 0) + count

    # Compute the three terms of the ARI formula
    # Term 1: sum over contingency cells of C(n_ij, 2)
    sum_cij = sum(math.comb(count, 2) for count in contingency.values())

    # Term 2: sum of C(a_i, 2) for each row
    sum_ai = sum(math.comb(count, 2) for count in row_sums.values())

    # Term 3: sum of C(b_j, 2) for each column
    sum_bj = sum(math.comb(count, 2) for count in col_sums.values())

    # Total binomial coefficient
    cn2 = math.comb(n, 2)

    if cn2 == 0:
        return 1.0 if labels_a == labels_b else 0.0

    # Expected value under hypergeometric model
    expected = (sum_ai * sum_bj) / cn2

    # Numerator
    numerator = sum_cij - expected

    # Denominator
    denominator = 0.5 * (sum_ai + sum_bj) - expected

    if denominator == 0.0:
        return 1.0 if numerator == 0.0 else 0.0

    return numerator / denominator


def bootstrap_ci(
    metric_fn,
    utterances_a: list,
    utterances_b: list,
    n_bootstrap: int = 5000,
    ci_alpha: float = 0.05,
    seed: int = 42,
    block_length: int = None,
) -> dict:
    """
    Naive utterance bootstrap (block_length=None) or block bootstrap (block_length=k).
    Resamples paired (a[i], b[i]) utterances with replacement.

    Args:
        metric_fn: callable(labels_a, labels_b) -> float
        utterances_a, utterances_b: per-utterance labels (lists)
        n_bootstrap: number of resamples
        ci_alpha: significance level (default 0.05 for 95% CI)
        seed: random seed for reproducibility
        block_length: if set, use block bootstrap; if None, use naive resampling

    Returns: {point, ci_lo, ci_hi, n_bootstrap, method}
    method = "naive_utterance" | "block_utterance"
    """
    if len(utterances_a) != len(utterances_b):
        raise ValueError("utterances_a and utterances_b must have same length")

    n = len(utterances_a)
    if n == 0:
        return {
            "point": 0.0,
            "ci_lo": 0.0,
            "ci_hi": 0.0,
            "n_bootstrap": n_bootstrap,
            "method": "naive_utterance" if block_length is None else "block_utterance"
        }

    # Compute point estimate
    point = metric_fn(utterances_a, utterances_b)

    rng = random.Random(seed)

    bootstrap_values = []

    if block_length is None:
        # Naive bootstrap: resample indices with replacement
        method = "naive_utterance"
        for _ in range(n_bootstrap):
            indices = [rng.randint(0, n - 1) for _ in range(n)]
            sample_a = [utterances_a[i] for i in indices]
            sample_b = [utterances_b[i] for i in indices]
            value = metric_fn(sample_a, sample_b)
            bootstrap_values.append(value)
    else:
        # Block bootstrap: generate contiguous blocks
        method = "block_utterance"
        block_len = max(1, block_length)
        for _ in range(n_bootstrap):
            indices = []
            pos = 0
            while len(indices) < n:
                start = rng.randint(0, max(0, n - block_len))
                end = min(start + block_len, n)
                indices.extend(range(start, end))
            indices = indices[:n]  # Trim to exact size
            sample_a = [utterances_a[i] for i in indices]
            sample_b = [utterances_b[i] for i in indices]
            value = metric_fn(sample_a, sample_b)
            bootstrap_values.append(value)

    # Compute percentile-based CI
    bootstrap_values.sort()
    lo_idx = int(n_bootstrap * (ci_alpha / 2.0))
    hi_idx = int(n_bootstrap * (1.0 - ci_alpha / 2.0))
    lo_idx = max(0, min(lo_idx, n_bootstrap - 1))
    hi_idx = max(0, min(hi_idx, n_bootstrap - 1))

    ci_lo = bootstrap_values[lo_idx]
    ci_hi = bootstrap_values[hi_idx]

    return {
        "point": point,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "n_bootstrap": n_bootstrap,
        "method": method,
    }


def _derive_boundaries(assignments: dict, n_utterances: int) -> list:
    """
    Derive segment boundaries from category assignments.

    Given {utterance_id: category_label}, sorted by utterance_id (1-indexed),
    return list of (start_utt, end_utt) for each contiguous same-category run.
    Utterances not in assignments are treated as their own singleton segments.

    Args:
        assignments: {utterance_id: category_str}
        n_utterances: total number of utterances

    Returns: list of (start_utt, end_utt) tuples (1-indexed, inclusive ends)
    """
    boundaries = []
    if not assignments:
        return boundaries

    # Sort assignment keys using _utt_sort_key for numeric ordering
    sorted_utts = sorted(assignments.keys(), key=_utt_sort_key)
    if not sorted_utts:
        return boundaries

    current_cat = assignments[sorted_utts[0]]
    start_tuple = _utt_sort_key(sorted_utts[0])
    start_utt = start_tuple[0] if start_tuple else 0

    for i in range(1, len(sorted_utts)):
        uid = sorted_utts[i]
        cat = assignments[uid]
        utt_tuple = _utt_sort_key(uid)
        utt_num = utt_tuple[0] if utt_tuple else 0

        if cat != current_cat:
            # Category change: close the previous boundary
            end_tuple = _utt_sort_key(sorted_utts[i - 1])
            end_utt = end_tuple[0] if end_tuple else 0
            boundaries.append((start_utt, end_utt))
            start_utt = utt_num
            current_cat = cat

    # Close the last boundary
    end_tuple = _utt_sort_key(sorted_utts[-1])
    end_utt = end_tuple[0] if end_tuple else 0
    boundaries.append((start_utt, end_utt))

    return boundaries


def compute_irr(
    primary: dict,
    alternate: dict,
    alignment: list,
    unmatched_primary: list,
    unmatched_alternate: list,
    n_utterances: int,
    bootstrap_seed: int = 42,
    n_bootstrap: int = 5000,
    stage: str = "diachronic",
    transcript_id: str = "",
    participant_id: str = "",
    primary_model: str = "",
    alternate_model: str = "",
) -> dict:
    """
    Top-level convenience: runs all four metrics with bootstrap CIs.

    Computes:
      - Nominal α: Primary agreement metric
      - Cohen's κ: Secondary metric for literal match comparison
      - αU (approximation): Boundary-agreement metric for segmentation
      - ARI: Label-permutation-invariant sanity check

    Args:
        primary: {utterance_id: category}
        alternate: {utterance_id: category}
        alignment: [{primary, alternate, confidence, ...}, ...]
        unmatched_primary, unmatched_alternate: lists of unmatched categories
        n_utterances: total utterance count
        bootstrap_seed: seed for reproducibility
        n_bootstrap: number of bootstrap resamples
        stage: "diachronic" or "synchronic" (required for IRR gate mapping)
        transcript_id: identifier of the transcript (optional)
        participant_id: identifier of the participant (optional)
        primary_model: primary analysis model name (optional)
        alternate_model: alternate analysis model name (optional)

    Returns: dict with all metrics, CIs, confidence distribution, outcome
    """
    # Validate stage parameter
    if stage not in {"diachronic", "synchronic"}:
        raise ValueError(f"stage must be 'diachronic' or 'synchronic', got {stage!r}")

    # Compute pre-alignment α (before alignment is applied)
    categories_pre, matrix_pre = compute_coincidence(
        primary, alternate, [], unmatched_primary, unmatched_alternate
    )
    alpha_pre = alpha_nominal(categories_pre, matrix_pre)

    # Apply alignment and build coincidence matrix
    categories, matrix = compute_coincidence(
        primary, alternate, alignment, unmatched_primary, unmatched_alternate
    )

    # Build lists of labels for bootstrap
    # Use _utt_sort_key for numeric sorting (handles "1", "10", "2", "22.1", etc.)
    utterance_ids = sorted(set(primary.keys()) | set(alternate.keys()), key=_utt_sort_key)
    labels_primary = [primary.get(uid, "") for uid in utterance_ids]
    labels_alternate = [alternate.get(uid, "") for uid in utterance_ids]

    # Apply alignment to alternate labels
    alignment_map = {}
    for entry in alignment:
        alignment_map[entry.get("alternate")] = entry.get("primary")

    labels_alternate_aligned = []
    for label in labels_alternate:
        if label in alignment_map:
            labels_alternate_aligned.append(alignment_map[label])
        else:
            labels_alternate_aligned.append(label)

    # Define metric functions for bootstrap
    def metric_alpha_aligned(a, b):
        categories, matrix = compute_coincidence(
            {str(i): a[i] for i in range(len(a))},
            {str(i): b[i] for i in range(len(b))},
            [], [], []
        )
        return alpha_nominal(categories, matrix)

    def metric_kappa_aligned(a, b):
        categories, matrix = compute_coincidence(
            {str(i): a[i] for i in range(len(a))},
            {str(i): b[i] for i in range(len(b))},
            [], [], []
        )
        return cohens_kappa(categories, matrix)

    def metric_ari(a, b):
        return adjusted_rand_index(a, b)

    # Bootstrap CIs (naive for α, κ, ARI; block bootstrap for αU)
    # Compute bootstrap for α with shared seed
    alpha_ci = bootstrap_ci(
        metric_alpha_aligned,
        labels_primary,
        labels_alternate_aligned,
        n_bootstrap=n_bootstrap,
        seed=bootstrap_seed,
        block_length=None
    )

    # κ with same bootstrap seed for consistency
    kappa_ci = bootstrap_ci(
        metric_kappa_aligned,
        labels_primary,
        labels_alternate_aligned,
        n_bootstrap=n_bootstrap,
        seed=bootstrap_seed,
        block_length=None
    )

    # ARI with same seed
    ari_ci = bootstrap_ci(
        metric_ari,
        labels_primary,
        labels_alternate_aligned,
        n_bootstrap=n_bootstrap,
        seed=bootstrap_seed,
        block_length=None
    )

    # αU with block bootstrap: derive boundaries from assignments, compute point estimate,
    # then use block bootstrap to get CIs
    boundaries_primary = _derive_boundaries(primary, n_utterances)
    boundaries_alternate = _derive_boundaries(alternate, n_utterances)

    # Point estimate for αU
    au_point = alpha_unitizing(boundaries_primary, boundaries_alternate, n_utterances)

    # Define metric function for αU bootstrap that operates on label sequences
    # and internally derives boundaries
    def metric_alpha_u(labels_a, labels_b):
        # Reconstruct assignments from labels
        assignments_a = {str(i): labels_a[i] for i in range(len(labels_a))}
        assignments_b = {str(i): labels_b[i] for i in range(len(labels_b))}
        # Derive boundaries and compute αU
        bounds_a = _derive_boundaries(assignments_a, len(labels_a))
        bounds_b = _derive_boundaries(assignments_b, len(labels_b))
        return alpha_unitizing(bounds_a, bounds_b, len(labels_a))

    # Block bootstrap for αU (block_length = sqrt(n_utterances))
    block_length = max(1, round(n_utterances ** 0.5))
    au_ci = bootstrap_ci(
        metric_alpha_u,
        labels_primary,
        labels_alternate_aligned,
        n_bootstrap=n_bootstrap,
        seed=bootstrap_seed + 1,
        block_length=block_length
    )

    # Compute sensitivity α (exclude low-confidence alignments)
    high_conf_alignment = [
        entry for entry in alignment
        if entry.get("confidence", 0.0) >= 0.7
    ]

    categories_sens, matrix_sens = compute_coincidence(
        primary, alternate, high_conf_alignment, unmatched_primary, unmatched_alternate
    )
    alpha_sensitivity = alpha_nominal(categories_sens, matrix_sens)

    # Build confidence distribution from alignment
    confidences = [entry.get("confidence", 0.0) for entry in alignment]
    if confidences:
        confidences_sorted = sorted(confidences)
        n_conf = len(confidences_sorted)
        confidence_distribution = {
            "min": min(confidences),
            "p25": confidences_sorted[n_conf // 4] if n_conf > 0 else 0.0,
            "median": confidences_sorted[n_conf // 2] if n_conf > 0 else 0.0,
            "p75": confidences_sorted[3 * n_conf // 4] if n_conf > 0 else 0.0,
            "max": max(confidences),
        }
    else:
        confidence_distribution = {
            "min": 0.0,
            "p25": 0.0,
            "median": 0.0,
            "p75": 0.0,
            "max": 0.0,
        }

    # Determine outcome based on α CI lower bound
    outcome = "passed" if alpha_ci["ci_lo"] >= 0.6 else "low"

    # Build complete record
    record = {
        "stage": stage,
        "participant_id": participant_id,
        "transcript_id": transcript_id,
        "primary_model": primary_model,
        "alternate_model": alternate_model,
        "n_utterances": n_utterances,
        "n_bootstrap": n_bootstrap,
        "bootstrap_seed": bootstrap_seed,
        "alignment": {
            "n_mappings": len(alignment),
            "n_unmatched_primary": len(unmatched_primary),
            "n_unmatched_alternate": len(unmatched_alternate),
            "confidence_distribution": confidence_distribution,
        },
        "metrics": {
            "alpha": {
                "point": alpha_ci["point"],
                "ci_lo": alpha_ci["ci_lo"],
                "ci_hi": alpha_ci["ci_hi"],
            },
            "alpha_pre_alignment": {
                "point": alpha_pre,
            },
            "alpha_sensitivity_low_conf_excluded": {
                "point": alpha_sensitivity,
            },
            "kappa": {
                "point": kappa_ci["point"],
                "ci_lo": kappa_ci["ci_lo"],
                "ci_hi": kappa_ci["ci_hi"],
            },
            "alpha_u": {
                "point": au_ci["point"],
                "ci_lo": au_ci["ci_lo"],
                "ci_hi": au_ci["ci_hi"],
            },
            "ari": {
                "point": ari_ci["point"],
                "ci_lo": ari_ci["ci_lo"],
                "ci_hi": ari_ci["ci_hi"],
            },
        },
        "bootstrap": {
            "alpha_method": alpha_ci["method"],
            "kappa_method": kappa_ci["method"],
            "alpha_u_method": au_ci["method"],
            "ari_method": ari_ci["method"],
            "alpha_u_block_length": block_length,
        },
        "outcome": outcome,
        "notes": "",
    }

    return record


def aggregate_stratum_records(records: list) -> dict:
    """
    Aggregate multiple stratum IRR records into a single aggregate record.

    Args:
        records: list of IRR records (each from compute_irr)

    Returns:
        dict: aggregate record with:
            - record_type: "aggregate"
            - n_strata: int, number of strata
            - metrics: dict with pooled metrics (point = mean, ci_lo = min, ci_hi = max)
            - outcome: "passed" if all strata passed, else "low"
            - strata_outcomes: list of per-stratum outcomes
            - notes: aggregation summary

    Raises:
        ValueError: if records is empty
    """
    if not records:
        raise ValueError("Cannot aggregate empty list of stratum records")

    n_strata = len(records)

    # Collect outcomes
    strata_outcomes = [r.get("outcome", "unknown") for r in records]
    # Outcome is "passed" only if ALL strata are "passed"
    outcome = "passed" if all(o == "passed" for o in strata_outcomes) else "low"

    # Pool metrics: point = mean, ci_lo = min, ci_hi = max
    aggregated_metrics = {}
    metric_names = ["alpha", "kappa", "alpha_u", "ari", "alpha_pre_alignment", "alpha_sensitivity_low_conf_excluded"]

    for metric_name in metric_names:
        # Collect metric data from all strata
        metric_data = [
            r.get("metrics", {}).get(metric_name)
            for r in records
        ]
        # Filter out None values (some metrics may not be present)
        metric_data = [m for m in metric_data if m is not None]

        if not metric_data:
            continue

        # Extract point, ci_lo, ci_hi from each stratum
        points = [m.get("point") for m in metric_data if m.get("point") is not None]
        ci_los = [m.get("ci_lo") for m in metric_data if m.get("ci_lo") is not None]
        ci_his = [m.get("ci_hi") for m in metric_data if m.get("ci_hi") is not None]

        # Compute aggregate values
        if points:
            agg_point = sum(points) / len(points)
        else:
            agg_point = None

        agg_ci_lo = min(ci_los) if ci_los else None
        agg_ci_hi = max(ci_his) if ci_his else None

        # Build aggregated metric
        agg_metric = {}
        if agg_point is not None:
            agg_metric["point"] = agg_point
        if agg_ci_lo is not None:
            agg_metric["ci_lo"] = agg_ci_lo
        if agg_ci_hi is not None:
            agg_metric["ci_hi"] = agg_ci_hi

        if agg_metric:
            aggregated_metrics[metric_name] = agg_metric

    # Build aggregate record
    aggregate_record = {
        "record_type": "aggregate",
        "n_strata": n_strata,
        "metrics": aggregated_metrics,
        "outcome": outcome,
        "strata_outcomes": strata_outcomes,
        "notes": f"Aggregated {n_strata} stratum records; outcome='passed' iff all strata passed",
    }

    return aggregate_record

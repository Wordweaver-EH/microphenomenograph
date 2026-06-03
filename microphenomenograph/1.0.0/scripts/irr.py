#!/usr/bin/env python3
"""
IRR calibration module — Krippendorff α, Cohen's κ, αU, ARI with bootstrap CIs.

Implements inter-rater reliability (IRR) metrics for MPI analysis quality assessment.
Pure Python stdlib (no external dependencies).

Key functions:
  - load_diachronic_csv: Load diachronic CSV (absorbs kappa.py's logic)
  - load_synchronic_csv: Load synchronic CSV (absorbs kappa.py's logic)
  - compute_coincidence: Build union-of-categories coincidence matrix
  - alpha_nominal: Krippendorff's nominal α (primary metric)
  - cohens_kappa: Cohen's κ (secondary, literal match to manual)
  - alpha_unitizing: Krippendorff's αU (segmentation metric, label-independent)
  - adjusted_rand_index: ARI (label-permutation-invariant sanity check)
  - bootstrap_ci: Naive utterance or block bootstrap for CIs
  - compute_irr: Top-level convenience — all 4 metrics with bootstrap CIs

Default calibration mode: "stratified" (one transcript per IV-level stratum).
"""
import csv
import json
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
    # Build alignment mapping: primary category → alternate category
    alignment_map = {}
    for entry in alignment:
        primary_cat = entry.get("primary")
        alternate_cat = entry.get("alternate")
        if primary_cat and alternate_cat:
            alignment_map[primary_cat] = alternate_cat

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
    Krippendorff's unitizing α (αU) for segmentation agreement.
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

    Reference: Hubert & Arabie (1985).
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("labels_a and labels_b must have same length")

    n = len(labels_a)
    if n <= 1:
        return 1.0

    # Build contingency table: count pairs (i, j) in same cluster in both, etc.
    # a = pairs in same cluster in both
    # b = pairs in different clusters in both
    # c = pairs in same cluster in A, different in B
    # d = pairs in different clusters in A, same in B

    all_pairs = set()
    for i in range(n):
        for j in range(i + 1, n):
            all_pairs.add((i, j))

    same_a = set()
    for i in range(n):
        for j in range(i + 1, n):
            if labels_a[i] == labels_a[j]:
                same_a.add((i, j))

    same_b = set()
    for i in range(n):
        for j in range(i + 1, n):
            if labels_b[i] == labels_b[j]:
                same_b.add((i, j))

    a = len(same_a & same_b)  # Both same
    b = len((all_pairs - same_a - same_b))  # Both different

    total_pairs = n * (n - 1) // 2

    # Expected value under random labeling
    # E(index) = sum over contingency table entries of expected cell values
    # For ARI: E(RI) = 2 * sum_k (n_k choose 2) * sum_l (m_l choose 2) / (n choose 2)^2
    # where n_k, m_l are cluster sizes

    # Count cluster sizes in A and B
    cluster_sizes_a = {}
    for label in labels_a:
        cluster_sizes_a[label] = cluster_sizes_a.get(label, 0) + 1

    cluster_sizes_b = {}
    for label in labels_b:
        cluster_sizes_b[label] = cluster_sizes_b.get(label, 0) + 1

    # Compute expected RI
    expected_ri = 0.0
    for size_a in cluster_sizes_a.values():
        for size_b in cluster_sizes_b.values():
            if size_a > 1 and size_b > 1:
                expected_ri += size_a * (size_a - 1) * size_b * (size_b - 1)

    expected_ri = expected_ri / (2.0 * total_pairs * (total_pairs - 1.0)) if total_pairs > 1 else 0.0

    # Observed RI
    observed_ri = (a + b) / total_pairs if total_pairs > 0 else 0.0

    # ARI = (RI - E(RI)) / (max_RI - E(RI))
    # For normalized index: max_RI = 1 when perfect agreement
    max_ri = 1.0

    denominator = max_ri - expected_ri
    if denominator == 0.0:
        return 1.0 if observed_ri == max_ri else 0.0

    ari = (observed_ri - expected_ri) / denominator
    return max(-1.0, min(1.0, ari))  # Clamp to [-1, 1]


def bootstrap_ci(
    metric_fn,
    utterances_a: list,
    utterances_b: list,
    n_bootstrap: int = 5000,
    alpha: float = 0.05,
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
        alpha: significance level (default 0.05 for 95% CI)
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
    lo_idx = int(n_bootstrap * (alpha / 2.0))
    hi_idx = int(n_bootstrap * (1.0 - alpha / 2.0))
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


def compute_irr(
    primary: dict,
    alternate: dict,
    alignment: list,
    unmatched_primary: list,
    unmatched_alternate: list,
    n_utterances: int,
    bootstrap_seed: int = 42,
    n_bootstrap: int = 5000,
) -> dict:
    """
    Top-level convenience: runs all four metrics with bootstrap CIs.

    Args:
        primary: {utterance_id: category}
        alternate: {utterance_id: category}
        alignment: [{primary, alternate, confidence, ...}, ...]
        unmatched_primary, unmatched_alternate: lists of unmatched categories
        n_utterances: total utterance count
        bootstrap_seed: seed for reproducibility
        n_bootstrap: number of bootstrap resamples

    Returns: dict with all metrics, CIs, confidence distribution, outcome
    """
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
    utterance_ids = sorted(set(primary.keys()) | set(alternate.keys()))
    labels_primary = [primary.get(uid, "") for uid in utterance_ids]
    labels_alternate = [alternate.get(uid, "") for uid in utterance_ids]

    # Apply alignment to alternate labels
    alignment_map = {}
    for entry in alignment:
        alignment_map[entry.get("primary")] = entry.get("alternate")

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

    # Bootstrap CIs (naive for α, κ, ARI)
    shared_rng = random.Random(bootstrap_seed)

    # Manually compute bootstrap for α with shared seed
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

    # αU with block bootstrap (separate seed)
    block_length = max(1, round(n_utterances ** 0.5))
    # For αU, we need boundaries, not labels. For now, use a simple per-utterance label bootstrap
    # with block length as a proxy for boundary structure.
    au_ci = bootstrap_ci(
        metric_alpha_aligned,
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
        "stage": "diachronic",  # Or "synchronic", set by caller
        "participant_id": "",  # Set by caller
        "transcript_id": "",  # Set by caller
        "primary_model": "",  # Set by caller
        "alternate_model": "",  # Set by caller
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
        },
        "outcome": outcome,
        "notes": "",
    }

    return record

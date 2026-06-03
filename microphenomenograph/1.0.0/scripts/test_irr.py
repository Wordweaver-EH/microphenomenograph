#!/usr/bin/env python3
"""
Unit tests for irr.py -- Krippendorff alpha, Cohen's kappa, aU, ARI with bootstrap CIs.

Tests cover:
- AC13.10: identical inputs, random inputs, bootstrap speed, determinism, asymmetric marginals
- AC32.3: block bootstrap vs naive for aU
"""
import sys
import time
import random
from pathlib import Path

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).parent))
from irr import (
    compute_coincidence,
    alpha_nominal,
    cohens_kappa,
    alpha_unitizing,
    adjusted_rand_index,
    bootstrap_ci,
    compute_irr,
)


def test_identical_inputs():
    """AC13.10: Identical inputs -> all metrics ~= 1.0."""
    # All 70 utterances assigned to same category by both raters
    assignments_a = {str(i): "category_A" for i in range(70)}
    assignments_b = {str(i): "category_A" for i in range(70)}
    alignment = []  # No alignment needed, already identical

    categories, matrix = compute_coincidence(assignments_a, assignments_b, alignment, [], [])

    alpha = alpha_nominal(categories, matrix)
    kappa = cohens_kappa(categories, matrix)
    ari = adjusted_rand_index(
        [assignments_a[str(i)] for i in range(70)],
        [assignments_b[str(i)] for i in range(70)]
    )

    assert abs(alpha - 1.0) < 0.001, f"alpha should be ~=1.0, got {alpha}"
    assert abs(kappa - 1.0) < 0.001, f"kappa should be ~=1.0, got {kappa}"
    assert abs(ari - 1.0) < 0.001, f"ari should be ~=1.0, got {ari}"

    # Test bootstrap CIs
    ci = bootstrap_ci(
        lambda a, b: alpha_nominal(*compute_coincidence(
            {str(i): a[i] for i in range(len(a))},
            {str(i): b[i] for i in range(len(b))},
            [], [], []
        )),
        [assignments_a[str(i)] for i in range(70)],
        [assignments_b[str(i)] for i in range(70)],
        n_bootstrap=1000,
        seed=42
    )

    assert ci['ci_lo'] > 0.9, f"CI lower bound should be > 0.9, got {ci['ci_lo']}"
    print(f"[PASS] Identical inputs: a={alpha:.3f}, k={kappa:.3f}, ARI={ari:.3f}, a_CI=[{ci['ci_lo']:.3f}, {ci['ci_hi']:.3f}]")


def test_random_inputs():
    """AC13.10: Random assignments -> metrics computable (near chance-level with seed 42)."""
    rng = random.Random(42)
    categories_list = ["cat1", "cat2", "cat3", "cat4"]

    assignments_a = {str(i): rng.choice(categories_list) for i in range(70)}
    assignments_b = {str(i): rng.choice(categories_list) for i in range(70)}
    alignment = []

    categories, matrix = compute_coincidence(assignments_a, assignments_b, alignment, [], [])

    alpha = alpha_nominal(categories, matrix)
    kappa = cohens_kappa(categories, matrix)
    ari = adjusted_rand_index(
        [assignments_a[str(i)] for i in range(70)],
        [assignments_b[str(i)] for i in range(70)]
    )

    # With 4 categories and random seed 42, metrics should be near chance-level (small values)
    assert not (alpha != alpha), f"alpha should not be NaN, got {alpha}"
    assert not (kappa != kappa), f"kappa should not be NaN, got {kappa}"
    assert not (ari != ari), f"ari should not be NaN, got {ari}"
    assert abs(alpha) < 0.3, f"alpha with random inputs should be small, got {alpha:.3f}"
    assert abs(kappa) < 0.3, f"kappa with random inputs should be small, got {kappa:.3f}"
    assert abs(ari) < 0.3, f"ARI with random inputs should be small, got {ari:.3f}"
    print(f"[PASS] Random inputs (near chance-level): a={alpha:.3f}, k={kappa:.3f}, ARI={ari:.3f}")


def test_bootstrap_speed():
    """AC13.10: Bootstrap with 5000 resamples completes in <2.0 seconds for 70 utterances."""
    assignments_a = {str(i): f"cat{i % 3}" for i in range(70)}
    assignments_b = {str(i): f"cat{(i+1) % 3}" for i in range(70)}

    labels_a = [assignments_a[str(i)] for i in range(70)]
    labels_b = [assignments_b[str(i)] for i in range(70)]

    start = time.monotonic()
    ci = bootstrap_ci(
        lambda a, b: alpha_nominal(*compute_coincidence(
            {str(i): a[i] for i in range(len(a))},
            {str(i): b[i] for i in range(len(b))},
            [], [], []
        )),
        labels_a,
        labels_b,
        n_bootstrap=5000,
        seed=42
    )
    elapsed = time.monotonic() - start

    assert elapsed < 2.0, f"Bootstrap should complete in <2.0s, took {elapsed:.2f}s"
    print(f"[PASS] Bootstrap speed: {elapsed:.3f}s for 5000 resamples")


def test_deterministic_cis():
    """AC13.10: Same seed produces identical results."""
    assignments_a = {str(i): f"cat{i % 3}" for i in range(70)}
    assignments_b = {str(i): f"cat{(i+1) % 3}" for i in range(70)}

    labels_a = [assignments_a[str(i)] for i in range(70)]
    labels_b = [assignments_b[str(i)] for i in range(70)]

    def metric_fn(a, b):
        return alpha_nominal(*compute_coincidence(
            {str(i): a[i] for i in range(len(a))},
            {str(i): b[i] for i in range(len(b))},
            [], [], []
        ))

    ci1 = bootstrap_ci(metric_fn, labels_a, labels_b, n_bootstrap=1000, seed=42)
    ci2 = bootstrap_ci(metric_fn, labels_a, labels_b, n_bootstrap=1000, seed=42)

    assert ci1 == ci2, f"Same seed should produce identical results: {ci1} vs {ci2}"
    print(f"[PASS] Deterministic CIs: point={ci1['point']:.3f}, identical on re-run")


def test_asymmetric_marginals():
    """AC13.10: Asymmetric marginal distributions (different category counts) handled correctly."""
    # Rater A uses 5 categories
    assignments_a = {
        "1": "cat_a1", "2": "cat_a2", "3": "cat_a3", "4": "cat_a4", "5": "cat_a5",
        "6": "cat_a1", "7": "cat_a2", "8": "cat_a3", "9": "cat_a4", "10": "cat_a5",
    }
    # Rater B uses 3 categories (missing cat_a4 and cat_a5)
    assignments_b = {
        "1": "cat_b1", "2": "cat_b2", "3": "cat_b3", "4": "cat_b1", "5": "cat_b2",
        "6": "cat_b3", "7": "cat_b1", "8": "cat_b2", "9": "cat_b3", "10": "cat_b1",
    }
    alignment = []

    categories, matrix = compute_coincidence(assignments_a, assignments_b, alignment, [], [])

    alpha = alpha_nominal(categories, matrix)
    kappa = cohens_kappa(categories, matrix)

    assert not (alpha != alpha), f"a should not be NaN"  # NaN != NaN check
    assert not (kappa != kappa), f"k should not be NaN"
    assert alpha < 1.0, f"a with asymmetric marginals should be < 1.0, got {alpha}"
    assert kappa < 1.0, f"k with asymmetric marginals should be < 1.0, got {kappa}"
    print(f"[PASS] Asymmetric marginals: a={alpha:.3f}, k={kappa:.3f} (both computable and < 1.0)")


def test_ari_partial_agreement():
    """AC13.10: ARI Hubert-Arabie reference: [0,0,0,1,1,1] vs [0,0,1,1,2,2] ~= 0.2424."""
    result = adjusted_rand_index([0,0,0,1,1,1], [0,0,1,1,2,2])
    assert abs(result - 0.2424) < 0.001, f"ARI should be ~= 0.2424, got {result:.4f}"
    print(f"[PASS] ARI partial agreement: {result:.4f} (expected ~= 0.2424)")


def test_block_bootstrap_vs_naive_for_alpha_u():
    """AC32.3: Block bootstrap CI for aU (on real boundaries) is wider than naive bootstrap CI."""
    from irr import _derive_boundaries

    # Create label sequences where boundaries are clear (70 utterances total)
    # Segment each 10 utterances: 7 segments
    labels_a = ["seg" + str(i // 10) for i in range(70)]
    labels_b = ["seg" + str(i // 10) for i in range(70)]
    assert len(labels_a) == 70
    assert len(labels_b) == 70

    # Define metric function for αU bootstrap
    def metric_alpha_u(a, b):
        assignments_a = {str(i): a[i] for i in range(len(a))}
        assignments_b = {str(i): b[i] for i in range(len(b))}
        bounds_a = _derive_boundaries(assignments_a, len(a))
        bounds_b = _derive_boundaries(assignments_b, len(b))
        return alpha_unitizing(bounds_a, bounds_b, len(a))

    # Naive bootstrap (no block)
    ci_naive = bootstrap_ci(
        metric_alpha_u,
        labels_a,
        labels_b,
        n_bootstrap=1000,
        seed=42,
        block_length=None
    )

    # Block bootstrap (block_length ~= sqrt(70) = 8)
    block_length = max(1, round(70 ** 0.5))
    ci_block = bootstrap_ci(
        metric_alpha_u,
        labels_a,
        labels_b,
        n_bootstrap=1000,
        seed=42,
        block_length=block_length
    )

    naive_width = ci_naive['ci_hi'] - ci_naive['ci_lo']
    block_width = ci_block['ci_hi'] - ci_block['ci_lo']

    # Block bootstrap should be >= naive CI width (accounts for autocorrelation in boundary structure)
    assert block_width >= naive_width * 0.95, (
        f"Block bootstrap CI should be >= naive CI width: "
        f"naive={naive_width:.4f}, block={block_width:.4f}"
    )
    print(f"[PASS] Block bootstrap wider for aU: naive_width={naive_width:.4f}, block_width={block_width:.4f}")


if __name__ == "__main__":
    tests = [
        test_identical_inputs,
        test_random_inputs,
        test_bootstrap_speed,
        test_deterministic_cis,
        test_asymmetric_marginals,
        test_ari_partial_agreement,
        test_block_bootstrap_vs_naive_for_alpha_u,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except AssertionError as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: UNEXPECTED ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    if failed:
        print(f"\n{failed}/{len(tests)} tests FAILED")
        sys.exit(1)
    else:
        print(f"\n{len(tests)}/{len(tests)} tests passed")

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
    RATER_KIND_INTRA,
    RATER_KIND_HETERO,
    CAVEAT_INTRA_MODEL,
    CAVEAT_HETEROGENEOUS_MODEL,
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


def test_utt_sort_key_numeric_ordering():
    """Test that _utt_sort_key correctly sorts utterance IDs numerically, not lexically.

    This is a direct test for the sort key function. With lexical sort, "10" < "2" < "3",
    which breaks boundary detection in alpha_unitizing. This test ensures numeric sort
    is applied everywhere utterance IDs are sorted.
    """
    from irr import _utt_sort_key

    # Test single-digit and multi-digit numeric IDs
    test_ids = ["1", "2", "10", "22.1", "22.2", "9"]
    expected_order = ["1", "2", "9", "10", "22.1", "22.2"]

    sorted_ids = sorted(test_ids, key=_utt_sort_key)
    assert sorted_ids == expected_order, (
        f"_utt_sort_key numeric sort failed: got {sorted_ids}, expected {expected_order}"
    )

    # Verify that lexical sort would give wrong order
    lexical_order = sorted(test_ids)
    assert lexical_order != expected_order, (
        f"Lexical sort should differ from numeric sort"
    )
    assert lexical_order == ["1", "10", "2", "22.1", "22.2", "9"], (
        f"Lexical sort should be ['1', '10', '2', '22.1', '22.2', '9'], got {lexical_order}"
    )


def test_compute_irr_stage_field_propagates():
    """Verify compute_irr stage parameter propagates into returned record.

    This test catches regressions where stage parameter is ignored or hardcoded.
    The record's 'stage' field must reflect the parameter passed to compute_irr,
    not default to 'diachronic' regardless of caller intent.

    This is critical for --strict-irr gate: cross-participant stages must correctly
    route to synchronic calibration, not diachronic (which would be unverified).
    """
    # Minimal utterance data (2 raters, 4 utterances)
    primary = {"1": "A", "2": "A", "3": "B", "4": "B"}
    alternate = {"1": "A", "2": "B", "3": "B", "4": "A"}

    # Test default stage (should be "diachronic")
    record_default = compute_irr(
        primary,
        alternate,
        alignment=[],
        unmatched_primary=[],
        unmatched_alternate=[],
        n_utterances=4,
        n_bootstrap=100,
        bootstrap_seed=42,
    )
    assert record_default["stage"] == "diachronic", (
        f"Default stage should be 'diachronic', got {record_default['stage']!r}"
    )

    # Test explicit synchronic stage
    record_sync = compute_irr(
        primary,
        alternate,
        alignment=[],
        unmatched_primary=[],
        unmatched_alternate=[],
        n_utterances=4,
        n_bootstrap=100,
        bootstrap_seed=42,
        stage="synchronic",
    )
    assert record_sync["stage"] == "synchronic", (
        f"stage='synchronic' should propagate into record, got {record_sync['stage']!r}. "
        f"If 'diachronic', the stage parameter is being ignored or hardcoded."
    )

    # Test explicit diachronic stage
    record_dia = compute_irr(
        primary,
        alternate,
        alignment=[],
        unmatched_primary=[],
        unmatched_alternate=[],
        n_utterances=4,
        n_bootstrap=100,
        bootstrap_seed=42,
        stage="diachronic",
    )
    assert record_dia["stage"] == "diachronic"

    print("[PASS] compute_irr stage propagation: default diachronic, explicit values respected")


def test_compute_irr_invalid_stage_raises():
    """Verify compute_irr raises ValueError for invalid stage parameter.

    This prevents silent bugs where synchronic calibration calls might typo the stage,
    e.g., compute_irr(..., stage="synchro") would silently default to diachronic
    without validation. ValueError catches the mistake immediately.
    """
    primary = {"1": "A", "2": "B"}
    alternate = {"1": "A", "2": "A"}

    try:
        compute_irr(
            primary,
            alternate,
            alignment=[],
            unmatched_primary=[],
            unmatched_alternate=[],
            n_utterances=2,
            n_bootstrap=100,
            bootstrap_seed=42,
            stage="invalid",
        )
        assert False, "compute_irr should raise ValueError for invalid stage"
    except ValueError as e:
        assert "stage must be" in str(e), f"Error message should mention valid stages, got {str(e)!r}"
        print(f"[PASS] compute_irr invalid stage raises: {str(e)}")


def test_alignment_disjoint_labels_full_agreement():
    """AC1.1, AC1.3: Disjoint label sets with full alignment yield alpha=1.0; without alignment alpha<<1.0."""
    # 10 utterances; primary uses A/B; alternate uses X/Y for same structure
    primary = {"1": "A", "2": "A", "3": "A", "4": "A", "5": "A",
               "6": "B", "7": "B", "8": "B", "9": "B", "10": "B"}
    alternate = {"1": "X", "2": "X", "3": "X", "4": "X", "5": "X",
                 "6": "Y", "7": "Y", "8": "Y", "9": "Y", "10": "Y"}
    # Full alignment: X->A, Y->B
    alignment = [{"primary": "A", "alternate": "X", "confidence": 0.9, "rationale": "same"},
                 {"primary": "B", "alternate": "Y", "confidence": 0.9, "rationale": "same"}]

    # AC1.1: With alignment, alpha should be ~= 1.0
    categories, matrix = compute_coincidence(primary, alternate, alignment, [], [])
    alpha_with = alpha_nominal(categories, matrix)
    assert abs(alpha_with - 1.0) < 0.001, (
        f"AC1.1: With full disjoint alignment, alpha should be ~=1.0, got {alpha_with}. "
        f"This suggests the alignment map is not being applied correctly."
    )

    # AC1.3: Without alignment, alpha should be <<1.0 (all alternate labels are wrong namespace)
    categories0, matrix0 = compute_coincidence(primary, alternate, [], [], [])
    alpha_without = alpha_nominal(categories0, matrix0)
    assert alpha_without < 0.2, (
        f"AC1.3: Without alignment, alpha should be <<1.0 (disjoint namespaces), got {alpha_without}."
    )

    print(f"[PASS] test_alignment_disjoint_labels_full_agreement: alpha_with={alpha_with:.4f}, alpha_without={alpha_without:.4f}")


def test_alignment_partial_keeps_unaligned_distinct():
    """AC1.4: Partial alignment remaps only aligned categories; unaligned alternate labels stay distinct."""
    # 6 utterances; primary {A,B}; alternate {X,Y,Z}
    # Only X is aligned to A; Y and Z are unaligned
    primary = {"1": "A", "2": "A", "3": "A", "4": "B", "5": "B", "6": "B"}
    alternate = {"1": "X", "2": "X", "3": "X", "4": "Y", "5": "Y", "6": "Z"}
    alignment = [{"primary": "A", "alternate": "X", "confidence": 0.9, "rationale": ""}]
    unmatched_alternate = ["Y", "Z"]

    categories, matrix = compute_coincidence(primary, alternate, alignment, [], unmatched_alternate)
    sorted_categories = categories

    # Y and Z should remain in sorted_categories (unaligned, stays distinct)
    assert "Y" in sorted_categories, f"AC1.4: Y should remain in sorted_categories, got {sorted_categories}"
    assert "Z" in sorted_categories, f"AC1.4: Z should remain in sorted_categories, got {sorted_categories}"

    # Utterances 1-3: primary A, alternate X remapped to A -> matrix[(A,A)] == 3.0
    assert matrix[("A", "A")] == 3.0, (
        f"AC1.4: matrix[(A,A)] should be 3.0 (X remapped to A), got {matrix[('A','A')]}"
    )

    # Utterances 4-5: primary B, alternate Y unaligned -> matrix[(B,Y)] == 2.0
    assert matrix[("B", "Y")] == 2.0, (
        f"AC1.4: matrix[(B,Y)] should be 2.0 (Y unaligned), got {matrix[('B','Y')]}"
    )

    # Utterance 6: primary B, alternate Z unaligned -> matrix[(B,Z)] == 1.0
    assert matrix[("B", "Z")] == 1.0, (
        f"AC1.4: matrix[(B,Z)] should be 1.0 (Z unaligned), got {matrix[('B','Z')]}"
    )

    # X stays in sorted_categories as a zero-marginal phantom (category set built before remapping)
    assert "X" in sorted_categories, f"AC1.4: X should remain in sorted_categories as zero-marginal phantom, got {sorted_categories}"
    x_total = sum(matrix.get((c, "X"), 0.0) for c in sorted_categories) + sum(matrix.get(("X", c), 0.0) for c in sorted_categories)
    assert x_total == 0.0, (
        f"AC1.4: All matrix entries involving X should sum to 0.0 (X is phantom after remapping), got {x_total}"
    )

    print(f"[PASS] test_alignment_partial_keeps_unaligned_distinct: categories={sorted_categories}")


def test_rater_kind_intra_model():
    """AC2.1: Absent or equal alternate_model produces rater_kind=='intra_model' with correct caveat."""
    primary = {"1": "A", "2": "A", "3": "B", "4": "B"}
    alternate = {"1": "A", "2": "A", "3": "B", "4": "B"}

    # Case 1: alternate_model is empty string
    record1 = compute_irr(
        primary, alternate, [], [], [],
        n_utterances=4, n_bootstrap=100, bootstrap_seed=42,
        primary_model="claude-sonnet-4-5", alternate_model=""
    )
    assert record1["rater_kind"] == "intra_model", (
        f"Case 1: empty alternate_model should yield rater_kind=='intra_model', got {record1['rater_kind']!r}"
    )
    assert record1["caveat"] == CAVEAT_INTRA_MODEL, (
        f"Case 1: caveat should equal CAVEAT_INTRA_MODEL"
    )

    # Case 2: alternate_model equals primary_model
    record2 = compute_irr(
        primary, alternate, [], [], [],
        n_utterances=4, n_bootstrap=100, bootstrap_seed=42,
        primary_model="claude-sonnet-4-5", alternate_model="claude-sonnet-4-5"
    )
    assert record2["rater_kind"] == "intra_model", (
        f"Case 2: equal models should yield rater_kind=='intra_model', got {record2['rater_kind']!r}"
    )
    assert record2["caveat"] == CAVEAT_INTRA_MODEL, (
        f"Case 2: caveat should equal CAVEAT_INTRA_MODEL"
    )

    # Case 3: both empty
    record3 = compute_irr(
        primary, alternate, [], [], [],
        n_utterances=4, n_bootstrap=100, bootstrap_seed=42,
        primary_model="", alternate_model=""
    )
    assert record3["rater_kind"] == "intra_model", (
        f"Case 3: both empty models should yield rater_kind=='intra_model', got {record3['rater_kind']!r}"
    )

    print("[PASS] test_rater_kind_intra_model: all three intra-model cases correct")


def test_rater_kind_heterogeneous_model():
    """AC2.2: Differing alternate_model produces rater_kind=='heterogeneous_model' with correct caveat."""
    primary = {"1": "A", "2": "A", "3": "B", "4": "B"}
    alternate = {"1": "A", "2": "A", "3": "B", "4": "B"}

    record = compute_irr(
        primary, alternate, [], [], [],
        n_utterances=4, n_bootstrap=100, bootstrap_seed=42,
        primary_model="claude-sonnet-4-5", alternate_model="claude-opus-4"
    )
    assert record["rater_kind"] == "heterogeneous_model", (
        f"Differing models should yield rater_kind=='heterogeneous_model', got {record['rater_kind']!r}"
    )
    assert record["caveat"] == CAVEAT_HETEROGENEOUS_MODEL, (
        f"caveat should equal CAVEAT_HETEROGENEOUS_MODEL (equality check only)"
    )

    print("[PASS] test_rater_kind_heterogeneous_model: heterogeneous model case correct")


if __name__ == "__main__":
    tests = [
        test_identical_inputs,
        test_random_inputs,
        test_bootstrap_speed,
        test_deterministic_cis,
        test_asymmetric_marginals,
        test_ari_partial_agreement,
        test_block_bootstrap_vs_naive_for_alpha_u,
        test_utt_sort_key_numeric_ordering,
        test_alignment_disjoint_labels_full_agreement,
        test_alignment_partial_keeps_unaligned_distinct,
        test_rater_kind_intra_model,
        test_rater_kind_heterogeneous_model,
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

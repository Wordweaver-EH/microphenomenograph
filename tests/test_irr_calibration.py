#!/usr/bin/env python3
"""
Integration tests for IRR calibration module.

Tests cover:
- AC13.6: JSONL record schema completeness
- AC13.7: outcome rule (passed vs low)
- AC25.1: alpha_pre_alignment present
- AC25.2: alpha_sensitivity_low_conf_excluded present
- AC25.3: confidence_distribution with percentiles
- AC24.4: stratified aggregate summary
- AC31.1: DEFAULT_CALIBRATION_MODE == "stratified"
"""
import sys
import json
from pathlib import Path

# Add scripts/ to path
scripts_dir = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0" / "scripts"
sys.path.insert(0, str(scripts_dir))

from irr import compute_irr, DEFAULT_CALIBRATION_MODE


def test_irr_jsonl_schema():
    """AC13.6: Compute IRR record contains all required fields."""
    primary = {
        "1": "Initial Sensation",
        "2": "Initial Sensation",
        "3": "Body Awareness",
        "4": "Body Awareness",
        "5": "Emotion",
    }
    alternate = {
        "1": "First Awareness",
        "2": "First Awareness",
        "3": "Physical Presence",
        "4": "Physical Presence",
        "5": "Feeling",
    }
    alignment = [
        {"primary": "Initial Sensation", "alternate": "First Awareness", "confidence": 0.9, "rationale": "opening moment"},
        {"primary": "Body Awareness", "alternate": "Physical Presence", "confidence": 0.85, "rationale": "body focus"},
        {"primary": "Emotion", "alternate": "Feeling", "confidence": 0.8, "rationale": "emotional content"},
    ]
    unmatched_primary = []
    unmatched_alternate = []

    record = compute_irr(
        primary, alternate, alignment, unmatched_primary, unmatched_alternate,
        n_utterances=5, bootstrap_seed=42, n_bootstrap=100
    )

    # Check required fields
    required_fields = [
        "stage", "participant_id", "transcript_id", "primary_model", "alternate_model",
        "n_utterances", "n_bootstrap", "bootstrap_seed",
        "alignment", "metrics", "bootstrap", "outcome", "notes",
        "rater_kind", "caveat",
    ]
    for field in required_fields:
        assert field in record, f"Missing required field: {field}"

    # Check metrics fields
    metrics = record.get("metrics", {})
    required_metrics = ["alpha", "kappa", "alpha_u", "ari"]
    for metric in required_metrics:
        assert metric in metrics, f"Missing metric: {metric}"
        m = metrics[metric]
        assert "point" in m or "ci_lo" in m, f"Metric {metric} missing point/CI"

    print("[PASS] IRR record schema complete")


def test_outcome_rule():
    """AC13.7: outcome='passed' iff alpha.ci_lo >= 0.6; outcome='low' otherwise."""
    # Build assignments that give high agreement
    primary_high = {str(i): "cat_a" for i in range(20)}
    alternate_high = {str(i): "cat_a" for i in range(20)}
    alignment_high = []

    record_high = compute_irr(
        primary_high, alternate_high, alignment_high, [], [],
        n_utterances=20, bootstrap_seed=42, n_bootstrap=100
    )
    assert record_high["outcome"] == "passed", f"High agreement should give outcome='passed', got {record_high['outcome']}"
    assert record_high["metrics"]["alpha"]["ci_lo"] >= 0.6, "High agreement should have alpha.ci_lo >= 0.6"

    # Build assignments with low agreement
    primary_low = {
        "1": "cat1", "2": "cat2", "3": "cat3", "4": "cat4", "5": "cat5",
    }
    alternate_low = {
        "1": "catx", "2": "caty", "3": "catz", "4": "catw", "5": "catv",
    }
    alignment_low = []

    record_low = compute_irr(
        primary_low, alternate_low, alignment_low, [], [],
        n_utterances=5, bootstrap_seed=42, n_bootstrap=100
    )
    assert record_low["outcome"] == "low", f"Low agreement should give outcome='low', got {record_low['outcome']}"
    assert record_low["metrics"]["alpha"]["ci_lo"] < 0.6, "Low agreement should have alpha.ci_lo < 0.6"

    print("[PASS] Outcome rule correctly applied")


def test_alpha_pre_alignment():
    """AC25.1: Record includes alpha_pre_alignment with point value."""
    primary = {
        "1": "Initial",
        "2": "Initial",
        "3": "Body",
    }
    alternate = {
        "1": "First",
        "2": "First",
        "3": "Physical",
    }
    alignment = [
        {"primary": "Initial", "alternate": "First", "confidence": 0.9, "rationale": ""},
        {"primary": "Body", "alternate": "Physical", "confidence": 0.85, "rationale": ""},
    ]

    record = compute_irr(
        primary, alternate, alignment, [], [],
        n_utterances=3, bootstrap_seed=42, n_bootstrap=100
    )

    assert "alpha_pre_alignment" in record["metrics"], "Missing alpha_pre_alignment"
    assert "point" in record["metrics"]["alpha_pre_alignment"], "alpha_pre_alignment missing point value"
    print("[PASS] alpha_pre_alignment present")


def test_alpha_sensitivity():
    """AC25.2: Record includes alpha_sensitivity_low_conf_excluded with point value."""
    primary = {str(i): f"cat{i % 2}" for i in range(10)}
    alternate = {str(i): f"cat{i % 2}" for i in range(10)}
    alignment = [
        {"primary": "cat0", "alternate": "cat0", "confidence": 0.95, "rationale": ""},
        {"primary": "cat1", "alternate": "cat1", "confidence": 0.3, "rationale": ""},  # Low confidence
    ]

    record = compute_irr(
        primary, alternate, alignment, [], [],
        n_utterances=10, bootstrap_seed=42, n_bootstrap=100
    )

    assert "alpha_sensitivity_low_conf_excluded" in record["metrics"], "Missing alpha_sensitivity_low_conf_excluded"
    assert "point" in record["metrics"]["alpha_sensitivity_low_conf_excluded"], "alpha_sensitivity missing point value"
    print("[PASS] alpha_sensitivity_low_conf_excluded present")


def test_confidence_distribution():
    """AC25.3: confidence_distribution has min, p25, median, p75, max."""
    primary = {str(i): "cat_a" for i in range(10)}
    alternate = {str(i): "cat_b" for i in range(10)}
    alignment = [
        {"primary": "cat_a", "alternate": "cat_b", "confidence": 0.5, "rationale": ""},
        {"primary": "cat_c", "alternate": "cat_d", "confidence": 0.7, "rationale": ""},
        {"primary": "cat_e", "alternate": "cat_f", "confidence": 0.9, "rationale": ""},
    ]

    record = compute_irr(
        primary, alternate, alignment, [], [],
        n_utterances=10, bootstrap_seed=42, n_bootstrap=100
    )

    conf_dist = record.get("alignment", {}).get("confidence_distribution", {})
    required_percentiles = ["min", "p25", "median", "p75", "max"]
    for perc in required_percentiles:
        assert perc in conf_dist, f"confidence_distribution missing {perc}"

    # Verify monotonicity
    assert conf_dist["min"] <= conf_dist["p25"] <= conf_dist["median"] <= conf_dist["p75"] <= conf_dist["max"], \
        "Confidence percentiles should be monotonically increasing"

    print("[PASS] confidence_distribution has all percentiles")


def test_bootstrap_disclosure_fields():
    """AC32.1/32.2: Record includes bootstrap method fields and alpha_u_block_length."""
    primary = {str(i): "cat_a" for i in range(20)}
    alternate = {str(i): "cat_a" for i in range(20)}
    alignment = []
    unmatched_primary = []
    unmatched_alternate = []

    record = compute_irr(
        primary, alternate, alignment, unmatched_primary, unmatched_alternate,
        n_utterances=20, bootstrap_seed=42, n_bootstrap=100
    )

    # Verify bootstrap dict exists and has all method fields
    assert "bootstrap" in record, "Missing 'bootstrap' key in record"
    bootstrap = record["bootstrap"]

    # Check method fields
    assert bootstrap["alpha_method"] == "naive_utterance", "alpha_method should be 'naive_utterance'"
    assert bootstrap["kappa_method"] == "naive_utterance", "kappa_method should be 'naive_utterance'"
    assert bootstrap["alpha_u_method"] == "block_utterance", "alpha_u_method should be 'block_utterance'"
    assert bootstrap["ari_method"] == "naive_utterance", "ari_method should be 'naive_utterance'"

    # Check alpha_u_block_length is present and is a valid int >= 1
    assert "alpha_u_block_length" in bootstrap, "Missing 'alpha_u_block_length' in bootstrap dict"
    block_length = bootstrap["alpha_u_block_length"]
    assert isinstance(block_length, int), f"alpha_u_block_length should be int, got {type(block_length)}"
    assert block_length >= 1, f"alpha_u_block_length should be >= 1, got {block_length}"

    # For n_utterances=20, block_length should be round(sqrt(20)) = round(4.47) = 4
    expected_block_length = max(1, round(20 ** 0.5))
    assert block_length == expected_block_length, f"Expected block_length={expected_block_length}, got {block_length}"

    print("[PASS] bootstrap disclosure fields present and correct")


def test_stratified_aggregate():
    """AC24.4: Stratified aggregate record computed from multiple stratum records."""
    from irr import aggregate_stratum_records

    # Build two stratum records (high agreement, so both should pass)
    record1 = compute_irr(
        {str(i): "cat_a" for i in range(5)},
        {str(i): "cat_a" for i in range(5)},
        [], [], [],
        n_utterances=5, bootstrap_seed=42, n_bootstrap=50
    )

    record2 = compute_irr(
        {str(i): "cat_a" for i in range(7)},
        {str(i): "cat_a" for i in range(7)},
        [], [], [],
        n_utterances=7, bootstrap_seed=43, n_bootstrap=50
    )

    # Aggregate the two records
    aggregate = aggregate_stratum_records([record1, record2])

    # Check aggregate structure
    assert aggregate["record_type"] == "aggregate", f"record_type should be 'aggregate', got {aggregate.get('record_type')}"
    assert aggregate["n_strata"] == 2, f"n_strata should be 2, got {aggregate.get('n_strata')}"

    # Check metrics pooling
    assert "metrics" in aggregate, "Aggregate should have 'metrics' key"
    metrics = aggregate["metrics"]
    assert "alpha" in metrics, "Aggregate metrics should have 'alpha'"

    # Point estimate should be mean of strata
    alpha_point1 = record1["metrics"]["alpha"]["point"]
    alpha_point2 = record2["metrics"]["alpha"]["point"]
    expected_alpha_point = (alpha_point1 + alpha_point2) / 2.0
    assert abs(aggregate["metrics"]["alpha"]["point"] - expected_alpha_point) < 1e-6, \
        f"Aggregate alpha point should be mean of strata: {expected_alpha_point}, got {aggregate['metrics']['alpha']['point']}"

    # CI bounds should be min/max of strata
    alpha_ci_lo1 = record1["metrics"]["alpha"]["ci_lo"]
    alpha_ci_lo2 = record2["metrics"]["alpha"]["ci_lo"]
    expected_ci_lo = min(alpha_ci_lo1, alpha_ci_lo2)
    assert aggregate["metrics"]["alpha"]["ci_lo"] == expected_ci_lo, \
        f"Aggregate ci_lo should be min of strata: {expected_ci_lo}, got {aggregate['metrics']['alpha']['ci_lo']}"

    # Since both records should have outcome='passed', aggregate should also be 'passed'
    assert aggregate["outcome"] == "passed", f"Both strata passed, so aggregate should be 'passed', got {aggregate['outcome']}"
    assert aggregate["strata_outcomes"] == ["passed", "passed"], f"strata_outcomes should list each stratum outcome"

    print("[PASS] Stratified aggregate computed correctly")


def test_stratified_aggregate_with_low_outcome():
    """AC24.4: Aggregate outcome is 'low' if any stratum is 'low'."""
    from irr import aggregate_stratum_records

    # Build one high-agreement (passed) and one low-agreement (low outcome) record
    record_high = compute_irr(
        {str(i): "cat_a" for i in range(20)},
        {str(i): "cat_a" for i in range(20)},
        [], [], [],
        n_utterances=20, bootstrap_seed=42, n_bootstrap=100
    )

    record_low = compute_irr(
        {"1": "cat1", "2": "cat2", "3": "cat3", "4": "cat4", "5": "cat5"},
        {"1": "catx", "2": "caty", "3": "catz", "4": "catw", "5": "catv"},
        [], [], [],
        n_utterances=5, bootstrap_seed=42, n_bootstrap=100
    )

    # Aggregate: one passed, one low
    aggregate = aggregate_stratum_records([record_high, record_low])

    # Outcome should be 'low' since at least one stratum is low
    assert aggregate["outcome"] == "low", f"Aggregate with one low stratum should be 'low', got {aggregate['outcome']}"
    assert "passed" in aggregate["strata_outcomes"], "One stratum should have passed"
    assert "low" in aggregate["strata_outcomes"], "One stratum should have low"

    print("[PASS] Aggregate outcome is 'low' when any stratum is 'low'")


def test_stratified_aggregate_empty_raises():
    """AC24.4: aggregate_stratum_records raises ValueError for empty list."""
    from irr import aggregate_stratum_records

    try:
        aggregate_stratum_records([])
        assert False, "Should have raised ValueError for empty list"
    except ValueError as e:
        assert "empty" in str(e).lower(), f"Error message should mention 'empty', got: {e}"
        print("[PASS] aggregate_stratum_records raises ValueError for empty list")


def test_default_calibration_mode():
    """AC31.1: DEFAULT_CALIBRATION_MODE == 'stratified'."""
    assert DEFAULT_CALIBRATION_MODE == "stratified", \
        f"DEFAULT_CALIBRATION_MODE should be 'stratified', got {DEFAULT_CALIBRATION_MODE}"
    print("[PASS] DEFAULT_CALIBRATION_MODE is 'stratified'")


def test_compute_irr_alpha_u_ordering():
    """Test αU computation with ≥10 utterances and multi-digit sorting.

    Verifies that numeric sort order (not lexical) is applied to utterance keys.
    With lexical sort, "10" sorts before "2"/"3"/.../etc, which scrambles boundary
    detection in block bootstrap. This test uses real disagreement (not perfect
    agreement) at a boundary crossing between single-digit and multi-digit keys,
    so the sort order directly affects the boundary positions and thus αU value.
    """
    # Test case 1: Disagreement at boundary crossing (single→multi-digit)
    # Analysts split between utterances 9 and 10:
    # - Analyst A (primary): "1"-"6" → "A", "7"-"12" → "B"  (split between 6→7)
    # - Analyst B (alternate): "1"-"9" → "A", "10"-"12" → "B"  (split between 9→10)
    #
    # If lexical sort: "10" < "2" < "3" < ... < "9", boundaries scrambled, αU affected
    # If numeric sort: "1" < "2" < ... < "9" < "10", boundaries preserve disagreement
    primary = {
        "1": "A", "2": "A", "3": "A", "4": "A", "5": "A", "6": "A",
        "7": "B", "8": "B", "9": "B", "10": "B", "11": "B", "12": "B",
    }
    alternate = {
        "1": "A", "2": "A", "3": "A", "4": "A", "5": "A",
        "6": "A", "7": "A", "8": "A", "9": "A",
        "10": "B", "11": "B", "12": "B",
    }
    alignment = []

    record = compute_irr(
        primary, alternate, alignment, [], [],
        n_utterances=12, bootstrap_seed=42, n_bootstrap=100
    )

    # With numeric sort, αU should be in valid range and reflect disagreement
    # (not perfect agreement, so αU < 1.0; but disagreement is localized, so αU > 0)
    alpha_u = record["metrics"]["alpha_u"]["point"]
    assert not (alpha_u != alpha_u), f"αU should not be NaN, got {alpha_u}"
    assert -1.0 <= alpha_u <= 1.0, f"αU should be in [-1, 1], got {alpha_u}"
    # With disagreement at one boundary, expect moderate αU (not perfect, not terrible)
    assert alpha_u > 0.0, f"αU with localized disagreement should be > 0.0, got {alpha_u}"
    assert alpha_u < 1.0, f"αU with disagreement should be < 1.0 (not perfect), got {alpha_u}"
    # Pin the expected value: correct numeric sort → ~0.2727.
    # A lexical-sort regression moves αU well outside the ±0.05 band.
    assert abs(alpha_u - 0.2727) < 0.05, (
        f"αU with numeric sort should be ~0.2727 (got {alpha_u:.4f}). "
        f"Large deviations suggest incorrect (lexical) sort order in _utt_sort_key or _derive_boundaries."
    )

    # Test case 2: Dotted utterance IDs with disagreement at multi-digit boundary
    # Keys: "1"-"9", "10.1", "10.2", "11"-"12"
    # - Analyst A: "1"-"7" → "A", rest → "B"  (split between 7 and 8)
    # - Analyst B: "1"-"9" → "A", rest → "B"  (split between 9 and 10.1)
    # This creates disagreement at the boundary transition to multi-digit keys.
    # Numeric sort: "1"<"2"<..."9"<"10.1"<"10.2"<"11"<"12"
    # Lexical sort would wrongly place "10.1"/"10.2" earlier
    primary_dotted = {
        "1": "A", "2": "A", "3": "A", "4": "A", "5": "A", "6": "A", "7": "A",
        "8": "B", "9": "B",
        "10.1": "B", "10.2": "B",
        "11": "B", "12": "B",
    }
    alternate_dotted = {
        "1": "A", "2": "A", "3": "A", "4": "A", "5": "A", "6": "A", "7": "A",
        "8": "A", "9": "A",
        "10.1": "B", "10.2": "B",
        "11": "B", "12": "B",
    }
    alignment_dotted = []

    record_dotted = compute_irr(
        primary_dotted, alternate_dotted, alignment_dotted, [], [],
        n_utterances=12, bootstrap_seed=42, n_bootstrap=100
    )

    # With numeric sort on dotted IDs, should produce specific value
    alpha_u_dotted = record_dotted["metrics"]["alpha_u"]["point"]
    assert not (alpha_u_dotted != alpha_u_dotted), f"αU with dotted IDs should not be NaN, got {alpha_u_dotted}"
    assert -1.0 <= alpha_u_dotted <= 1.0, f"αU should be in [-1, 1], got {alpha_u_dotted}"
    # Pin the expected value for dotted case: numeric sort should give ~0.3333
    # (disagreement at 8/9 boundary vs 10.1 boundary affects αU)
    assert abs(alpha_u_dotted - 0.3333) < 0.05, (
        f"αU with dotted numeric sort should be ~0.3333 (got {alpha_u_dotted:.4f}). "
        f"Large deviations suggest incorrect sort order."
    )


def test_compute_irr_with_disjoint_alignment():
    """AC1.2: End-to-end through compute_irr with disjoint full-alignment fixture yields alpha~=1.0 and outcome=='passed'."""
    primary = {"1": "A", "2": "A", "3": "A", "4": "A", "5": "A",
               "6": "B", "7": "B", "8": "B", "9": "B", "10": "B"}
    alternate = {"1": "X", "2": "X", "3": "X", "4": "X", "5": "X",
                 "6": "Y", "7": "Y", "8": "Y", "9": "Y", "10": "Y"}
    alignment = [{"primary": "A", "alternate": "X", "confidence": 0.9, "rationale": "same"},
                 {"primary": "B", "alternate": "Y", "confidence": 0.9, "rationale": "same"}]

    record = compute_irr(primary, alternate, alignment, [], [], n_utterances=10, bootstrap_seed=42, n_bootstrap=500)

    # AC1.2 headline: alpha.point ~= 1.0
    alpha_point = record["metrics"]["alpha"]["point"]
    assert abs(alpha_point - 1.0) < 0.001, (
        f"AC1.2: With disjoint full alignment, metrics.alpha.point should be ~=1.0, got {alpha_point}. "
        f"Alignment map inversion bug likely not fixed."
    )

    # AC1.2 outcome: passed
    assert record["outcome"] == "passed", (
        f"AC1.2: outcome should be 'passed' for perfect agreement, got {record['outcome']!r}"
    )

    # Control: same call without alignment -> alpha_point < 0.5 (discriminates aligned from unaligned)
    record_no_align = compute_irr(primary, alternate, [], [], [], n_utterances=10, bootstrap_seed=42, n_bootstrap=500)
    alpha_no_align = record_no_align["metrics"]["alpha"]["point"]
    assert alpha_no_align < 0.5, (
        f"AC1.2 control: Without alignment, alpha.point should be < 0.5 (disjoint namespaces), got {alpha_no_align}"
    )

    print(f"[PASS] test_compute_irr_with_disjoint_alignment: alpha_aligned={alpha_point:.4f}, alpha_unaligned={alpha_no_align:.4f}")


def test_agreement_computation_schema_rejects_missing_rater_kind():
    """AC2.3: Schema validator rejects agreement_computation record missing rater_kind or caveat."""
    from _mpi_schemas import validate_units

    # Valid payload missing rater_kind
    payload_no_rk = {
        "stage": "diachronic",
        "participant_id": "p1s1",
        "metrics": {"alpha": {"point": 0.8}},
        "outcome": "passed",
        "caveat": "some caveat",
        # rater_kind deliberately omitted
    }
    errors = validate_units("irr_calibration", "agreement_computation", payload_no_rk)
    assert any("rater_kind" in str(e) for e in errors), (
        f"Expected schema error for missing rater_kind, got: {errors}"
    )

    # Valid payload missing caveat
    payload_no_caveat = {
        "stage": "diachronic",
        "participant_id": "p1s1",
        "metrics": {"alpha": {"point": 0.8}},
        "outcome": "passed",
        "rater_kind": "intra_model",
        # caveat deliberately omitted
    }
    errors2 = validate_units("irr_calibration", "agreement_computation", payload_no_caveat)
    assert any("caveat" in str(e) for e in errors2), (
        f"Expected schema error for missing caveat, got: {errors2}"
    )

    # Full valid payload (both fields present) passes
    payload_valid = {
        "stage": "diachronic",
        "participant_id": "p1s1",
        "metrics": {"alpha": {"point": 0.8}},
        "outcome": "passed",
        "rater_kind": "intra_model",
        "caveat": "some caveat text",
    }
    errors3 = validate_units("irr_calibration", "agreement_computation", payload_valid)
    assert errors3 == [], f"Valid payload should have no errors, got: {errors3}"

    print("[PASS] agreement_computation schema rejects missing rater_kind/caveat")


if __name__ == "__main__":
    tests = [
        test_irr_jsonl_schema,
        test_outcome_rule,
        test_alpha_pre_alignment,
        test_alpha_sensitivity,
        test_confidence_distribution,
        test_stratified_aggregate,
        test_default_calibration_mode,
        test_compute_irr_alpha_u_ordering,
        test_compute_irr_with_disjoint_alignment,
        test_agreement_computation_schema_rejects_missing_rater_kind,
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

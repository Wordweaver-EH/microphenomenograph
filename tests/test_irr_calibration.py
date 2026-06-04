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
        "alignment", "metrics", "bootstrap", "outcome", "notes"
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


def test_stratified_aggregate():
    """AC24.4: Two stratum records can be aggregated to produce aggregate summary."""
    # This is a simplified test that verifies the structure
    # In practice, aggregation happens in the orchestrator layer

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

    # Both records should have all required fields
    for rec in [record1, record2]:
        assert "metrics" in rec
        assert "alpha" in rec["metrics"]

    print("[PASS] Stratum records have proper structure for aggregation")


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

    # Test case 2: Dotted utterance IDs with disagreement
    # Keys: "1"-"9", "10.1", "10.2", "11"-"12"
    # - Analyst A: "1"-"5" → "A", rest → "B"
    # - Analyst B: "1"-"7" → "A", rest → "B"
    # Disagreement at boundary between "7" and "8" (or "7" and "10.1" if sort is wrong)
    primary_dotted = {
        "1": "A", "2": "A", "3": "A", "4": "A", "5": "A",
        "6": "B", "7": "B", "8": "B", "9": "B",
        "10.1": "B", "10.2": "B",
        "11": "B", "12": "B",
    }
    alternate_dotted = {
        "1": "A", "2": "A", "3": "A", "4": "A", "5": "A",
        "6": "A", "7": "A",
        "8": "B", "9": "B",
        "10.1": "B", "10.2": "B",
        "11": "B", "12": "B",
    }
    alignment_dotted = []

    record_dotted = compute_irr(
        primary_dotted, alternate_dotted, alignment_dotted, [], [],
        n_utterances=12, bootstrap_seed=42, n_bootstrap=100
    )

    # With numeric sort on dotted IDs, should produce valid metrics
    alpha_u_dotted = record_dotted["metrics"]["alpha_u"]["point"]
    assert not (alpha_u_dotted != alpha_u_dotted), f"αU with dotted IDs should not be NaN, got {alpha_u_dotted}"
    assert -1.0 <= alpha_u_dotted <= 1.0, f"αU should be in [-1, 1], got {alpha_u_dotted}"
    # Disagreement at one boundary should give moderate αU
    assert alpha_u_dotted > -1.0 and alpha_u_dotted < 1.0, \
        f"αU with disagreement and dotted IDs should be valid, got {alpha_u_dotted}"


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

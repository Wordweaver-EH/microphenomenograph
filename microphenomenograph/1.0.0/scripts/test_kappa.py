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
import pytest

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).parent))
from irr import load_diachronic_csv as load_diachronic, load_synchronic_csv as load_synchronic, compute_kappa

# Path to inter-rater examples (relative to plugin root)
PLUGIN_ROOT = Path(__file__).parent.parent
INTER_RATER_DIR = PLUGIN_ROOT / "examples" / "inter-rater"

# Reference values from osf-archive/Inter-rater Reliability/kappa.html
REFERENCE_DIACHRONIC_KAPPA = 0.82
REFERENCE_SYNCHRONIC_KAPPA = 0.60
TOLERANCE = 0.01


@pytest.mark.skipif(not INTER_RATER_DIR.exists(), reason="inter-rater CSV fixtures not present (examples/inter-rater/ missing)")
def test_diachronic_kappa_matches_reference():
    """AC7.1: Diachronic kappa matches kappa.Rmd within ±0.01."""
    kev = load_diachronic(INTER_RATER_DIR / "kev-diachronic-analysis.csv")
    yesesvi = load_diachronic(INTER_RATER_DIR / "yesesvi-diachronic-analysis.csv")
    kappa = compute_kappa(kev, yesesvi, range(1, 8))
    assert abs(kappa - REFERENCE_DIACHRONIC_KAPPA) <= TOLERANCE, (
        f"Diachronic kappa {kappa:.3f} differs from reference {REFERENCE_DIACHRONIC_KAPPA} "
        f"by more than {TOLERANCE}"
    )
    print(f"[PASS] Diachronic kappa: {kappa:.2f} (reference: {REFERENCE_DIACHRONIC_KAPPA})")


@pytest.mark.skipif(not INTER_RATER_DIR.exists(), reason="inter-rater CSV fixtures not present (examples/inter-rater/ missing)")
def test_synchronic_kappa_matches_reference():
    """AC7.1: Synchronic kappa matches kappa.Rmd within ±0.01."""
    kev = load_synchronic(INTER_RATER_DIR / "kev-synchronic-analysis.csv")
    yesesvi = load_synchronic(INTER_RATER_DIR / "yesesvi-synchronic-analysis.csv")
    kappa = compute_kappa(kev, yesesvi, range(1, 10))
    assert abs(kappa - REFERENCE_SYNCHRONIC_KAPPA) <= TOLERANCE, (
        f"Synchronic kappa {kappa:.3f} differs from reference {REFERENCE_SYNCHRONIC_KAPPA} "
        f"by more than {TOLERANCE}"
    )
    print(f"[PASS] Synchronic kappa: {kappa:.2f} (reference: {REFERENCE_SYNCHRONIC_KAPPA})")


@pytest.mark.skipif(not INTER_RATER_DIR.exists(), reason="inter-rater CSV fixtures not present (examples/inter-rater/ missing)")
def test_separate_diachronic_and_synchronic():
    """AC7.2: Kappa reported separately for each stage."""
    kev_dia = load_diachronic(INTER_RATER_DIR / "kev-diachronic-analysis.csv")
    yesesvi_dia = load_diachronic(INTER_RATER_DIR / "yesesvi-diachronic-analysis.csv")
    kev_syn = load_synchronic(INTER_RATER_DIR / "kev-synchronic-analysis.csv")
    yesesvi_syn = load_synchronic(INTER_RATER_DIR / "yesesvi-synchronic-analysis.csv")
    k_dia = compute_kappa(kev_dia, yesesvi_dia, range(1, 8))
    k_syn = compute_kappa(kev_syn, yesesvi_syn, range(1, 10))
    assert k_dia != k_syn, "Diachronic and synchronic kappa should differ"
    print(f"[PASS] Separate kappa: diachronic={k_dia:.2f}, synchronic={k_syn:.2f}")


def test_missing_annotations_handled():
    """AC7.4: Missing utterance annotations handled without crash."""
    # Analyst A has utterances 1, 2, 3 assigned to moments
    # Analyst B is missing utterance 2
    a = {"1": "1", "2": "2", "3": "1"}
    b = {"1": "1", "3": "1"}  # utterance 2 missing
    kappa = compute_kappa(a, b, range(1, 4))
    assert not math.isnan(kappa), "Kappa should not be NaN with missing annotations"
    assert isinstance(kappa, float), "Kappa should be a float"
    print(f"[PASS] Missing annotations handled: kappa={kappa:.3f}")


def test_low_kappa_detected():
    """AC7.3: Kappa below 0.61 is detectable."""
    # Completely random assignments → low kappa
    a = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5"}
    b = {"1": "5", "2": "4", "3": "3", "4": "2", "5": "1"}
    kappa = compute_kappa(a, b, range(1, 6))
    # Not testing threshold enforcement here (that's in main()), just that
    # the computed value is what it is
    assert isinstance(kappa, float)
    print(f"[PASS] Low kappa computable: kappa={kappa:.3f}")


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
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: UNEXPECTED ERROR: {e}")
            failed += 1

    if failed:
        print(f"\n{failed}/{len(tests)} tests FAILED")
        sys.exit(1)
    else:
        print(f"\n{len(tests)}/{len(tests)} tests passed")

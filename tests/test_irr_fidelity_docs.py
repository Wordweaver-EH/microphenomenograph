#!/usr/bin/env python3
"""
Documentation assertion tests for IRR fidelity phase 2.

Tests cover:
- AC3.1: mpi-irr SKILL.md uses 'intra-model consistency' terminology
- AC3.1: mpi-irr SKILL.md contains alternate-analyst no-analyses-dir isolation rule
- AC3.1: mpi-cross-analyst.md contains alternate-analyst isolation instruction
"""
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent / "microphenomenograph" / "1.0.0"
SKILL_MD = PLUGIN_ROOT / "skills" / "mpi-irr" / "SKILL.md"
CROSS_ANALYST = PLUGIN_ROOT / "agents" / "mpi-cross-analyst.md"


def test_skill_md_contains_intra_model_label():
    """AC3.1: mpi-irr SKILL.md uses 'intra-model consistency' terminology."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert "intra-model consistency" in content, (
        "SKILL.md must label same-model metrics 'intra-model consistency'"
    )
    assert "self-consistency" not in content, (
        "SKILL.md must not use 'self-consistency' (collides with Wang et al. CoT decoding)"
    )


def test_skill_md_contains_isolation_rule():
    """AC3.1: mpi-irr SKILL.md contains alternate-analyst no-analyses-dir rule."""
    content = SKILL_MD.read_text(encoding="utf-8")
    assert "must not read" in content.lower() or "MUST NOT read" in content, (
        "SKILL.md must contain no-reading-analyses/ isolation rule"
    )
    assert "isolation_statement" in content, (
        "SKILL.md must require isolation_statement in prompt artifact"
    )


def test_cross_analyst_contains_isolation_rule():
    """AC3.1: mpi-cross-analyst.md contains alternate-analyst isolation instruction."""
    content = CROSS_ANALYST.read_text(encoding="utf-8")
    assert "isolation" in content.lower(), (
        "mpi-cross-analyst.md must contain isolation instruction for independent_analyst substep"
    )
    assert "isolation_statement" in content, (
        "mpi-cross-analyst.md must require isolation_statement field in prompt artifact"
    )


if __name__ == "__main__":
    import sys

    tests = [
        test_skill_md_contains_intra_model_label,
        test_skill_md_contains_isolation_rule,
        test_cross_analyst_contains_isolation_rule,
    ]

    failed = 0
    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
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

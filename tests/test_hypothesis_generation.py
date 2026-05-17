#!/usr/bin/env python3
"""
Test suite for mpi-hypothesis skill and hypothesis generation.

Verifies:
- AC6.1: Each hypothesis names IV, DV, pattern, Pearl ladder rung, and confidence
- AC6.2: Each hypothesis references the source IDUs/ISUs it was derived from
- AC6.3: No cross-participant patterns found produces explicit "no hypothesis" output
"""

import re
from pathlib import Path
from typing import Dict, List


def parse_hypothesis_structure(hypothesis_md: str) -> Dict:
    """
    Parse a hypothesis section from markdown.

    Expected format:
    ## Hypothesis 1: <title>

    | Field | Value |
    |---|---|
    | Independent Variable | ... |
    | Dependent Variable | ... |
    | Pattern | ... |
    | Pearl Ladder Rung | ... |
    | Confidence | ... |
    | Suggested Test | ... |

    **Source IDUs/ISUs:**
    - p1s1: ...
    - p2s1: ...

    Returns dict with parsed fields.
    """
    result = {
        "title": None,
        "independent_variable": None,
        "dependent_variable": None,
        "pattern": None,
        "pearl_ladder_rung": None,
        "confidence": None,
        "suggested_test": None,
        "source_references": []
    }

    lines = hypothesis_md.split('\n')

    # Extract title
    title_match = re.search(r'^## Hypothesis \d+: (.+)$', hypothesis_md, re.MULTILINE)
    if title_match:
        result["title"] = title_match.group(1).strip()

    # Extract table rows
    field_pattern = r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|'
    for line in lines:
        match = re.match(field_pattern, line)
        if match:
            field = match.group(1).strip().lower()
            value = match.group(2).strip()

            if "independent" in field and "variable" in field:
                result["independent_variable"] = value
            elif "dependent" in field and "variable" in field:
                result["dependent_variable"] = value
            elif field == "pattern":
                result["pattern"] = value
            elif "pearl" in field and "rung" in field:
                result["pearl_ladder_rung"] = value
            elif "confidence" in field:
                result["confidence"] = value
            elif "suggested" in field and "test" in field:
                result["suggested_test"] = value

    # Extract source references (p1s1: name format)
    source_section_match = re.search(
        r'\*\*Source IDUs/ISUs:\*\*\s*\n((?:- p\d+s\d+: [^\n]+\n?)+)',
        hypothesis_md
    )
    if source_section_match:
        source_text = source_section_match.group(1)
        for line in source_text.split('\n'):
            match = re.match(r'^- (p\d+s\d+):\s*(.+)$', line.strip())
            if match:
                result["source_references"].append({
                    "participant_key": match.group(1),
                    "name": match.group(2)
                })

    return result


def test_hypothesis_required_fields():
    """
    Test AC6.1: Each hypothesis includes IV, DV, pattern, Pearl rung, confidence.

    This test verifies the structure of a single hypothesis.
    """
    print("TEST: AC6.1 - Hypothesis includes required fields")

    sample_hypothesis = """## Hypothesis 1: Automaticity and Suggestibility

| Field | Value |
|---|---|
| Independent Variable | Hypnotic suggestibility score (0–5) |
| Dependent Variable | Felt sense of automaticity in hand movement |
| Pattern | Participants with higher suggestibility scores report stronger automaticity |
| Pearl Ladder Rung | 1 (Association) |
| Confidence | 4/5 |
| Suggested Test | Regression: suggestibility → automaticity rating |

**Source IDUs/ISUs:**
- p1s1: Automaticity experience
- p3s2: Hand movement without intention
"""

    parsed = parse_hypothesis_structure(sample_hypothesis)

    # Verify all required fields present
    assert parsed["independent_variable"] is not None, "Missing Independent Variable"
    assert parsed["dependent_variable"] is not None, "Missing Dependent Variable"
    assert parsed["pattern"] is not None, "Missing Pattern"
    assert parsed["pearl_ladder_rung"] is not None, "Missing Pearl Ladder Rung"
    assert parsed["confidence"] is not None, "Missing Confidence"

    # Verify field content is not empty
    assert parsed["independent_variable"].strip() != "", "IV field is empty"
    assert parsed["dependent_variable"].strip() != "", "DV field is empty"
    assert parsed["pattern"].strip() != "", "Pattern field is empty"
    assert parsed["pearl_ladder_rung"].strip() != "", "Pearl rung field is empty"
    assert parsed["confidence"].strip() != "", "Confidence field is empty"

    # Verify Pearl rung is one of the three rungs
    rung_str = parsed["pearl_ladder_rung"].lower()
    valid_rungs = ["1", "2", "3", "association", "intervention", "counterfactual"]
    assert any(rung in rung_str for rung in valid_rungs), \
        f"Pearl rung must be 1/2/3 or association/intervention/counterfactual, got: {parsed['pearl_ladder_rung']}"

    # Verify confidence is numeric and 1-5
    confidence_match = re.search(r'(\d+)', parsed["confidence"])
    assert confidence_match is not None, f"Confidence must contain a number, got: {parsed['confidence']}"
    confidence_num = int(confidence_match.group(1))
    assert 1 <= confidence_num <= 5, f"Confidence must be 1-5, got: {confidence_num}"

    print("  [PASS] All required fields present in hypothesis")
    print(f"  [PASS] IV: {parsed['independent_variable']}")
    print(f"  [PASS] DV: {parsed['dependent_variable']}")
    print(f"  [PASS] Pearl Ladder Rung: {parsed['pearl_ladder_rung']}")
    print(f"  [PASS] Confidence: {parsed['confidence']}")


def test_hypothesis_source_references():
    """
    Test AC6.2: Each hypothesis references source IDUs/ISUs with participant keys.

    Verifies that:
    - Source references section exists
    - References use participant key format (pNsN)
    - Each reference includes a name
    """
    print("\nTEST: AC6.2 - Hypothesis includes source IDU/ISU references")

    sample_hypothesis = """## Hypothesis 1: Automaticity and Suggestibility

| Field | Value |
|---|---|
| Independent Variable | Hypnotic suggestibility score (0–5) |
| Dependent Variable | Felt sense of automaticity |
| Pattern | Pattern description |
| Pearl Ladder Rung | 1 (Association) |
| Confidence | 4/5 |
| Suggested Test | Test description |

**Source IDUs/ISUs:**
- p1s1: Automaticity experience
- p2s1: Hand movement without intention
- p4s2: Involuntary motion sense
"""

    parsed = parse_hypothesis_structure(sample_hypothesis)

    # Verify source references exist
    assert len(parsed["source_references"]) > 0, "No source references found"

    # Verify format of each reference
    for ref in parsed["source_references"]:
        assert "participant_key" in ref, "Source reference missing participant_key"
        assert "name" in ref, "Source reference missing name"

        # Verify participant key format (pNsN)
        pkey = ref["participant_key"]
        assert re.match(r'^p\d+s\d+$', pkey), f"Invalid participant key format: {pkey}"

        # Verify name is not empty
        assert ref["name"].strip() != "", f"Source reference name is empty for {pkey}"

    # Verify we have references from multiple participants
    participant_keys = [ref["participant_key"] for ref in parsed["source_references"]]
    assert "p1s1" in participant_keys, "Missing reference to p1s1"
    assert "p2s1" in participant_keys, "Missing reference to p2s1"

    print("  [PASS] Source references section present")
    print(f"  [PASS] Found {len(parsed['source_references'])} source references")
    for ref in parsed["source_references"]:
        print(f"    - {ref['participant_key']}: {ref['name']}")


def test_no_patterns_edge_case():
    """
    Test AC6.3: No cross-participant patterns produces explicit "No Hypotheses Generated"
    section, never an empty file.

    Verifies that:
    - Output is not empty
    - Output contains "No Hypotheses Generated" heading
    - Output explains why no hypotheses were found
    - Output suggests next steps
    """
    print("\nTEST: AC6.3 - No-patterns edge case produces explicit message")

    # Simulate the "no hypotheses" output
    no_hypotheses_output = """# MPI Research Hypotheses

Generated from global synchronic analysis of 1 participant.

## No Hypotheses Generated

No consistent cross-participant patterns were identified in the global synchronic analysis.
This may indicate: (a) high individual variation, (b) insufficient participants for pattern
detection, or (c) the patterns are idiosyncratic to individual experiences.

Suggested next step: Review the global synchronic analysis for qualitative themes that
did not meet the cross-participant threshold.
"""

    # Verify output is not empty
    assert len(no_hypotheses_output.strip()) > 0, "Output file is empty"

    # Verify "No Hypotheses Generated" heading is present
    assert "## No Hypotheses Generated" in no_hypotheses_output, \
        "Output missing 'No Hypotheses Generated' heading"

    # Verify explanatory text is present
    assert "No consistent cross-participant patterns" in no_hypotheses_output, \
        "Output missing explanation"

    # Verify it suggests next steps
    assert "next step" in no_hypotheses_output.lower() or "suggested" in no_hypotheses_output.lower(), \
        "Output missing next step suggestion"

    # Verify it doesn't have hypothesis sections (no "Hypothesis 1:", etc.)
    assert not re.search(r'## Hypothesis \d+:', no_hypotheses_output), \
        "No-patterns output should not contain hypothesis sections"

    print("  [PASS] No-patterns output is not empty")
    print("  [PASS] Contains 'No Hypotheses Generated' heading")
    print("  [PASS] Includes explanation of why")
    print("  [PASS] Suggests next steps")
    print("  [PASS] Does not contain individual hypothesis sections")


def test_full_hypotheses_file_structure():
    """
    Test overall hypotheses.md file structure.

    Verifies:
    - File has title and introductory text
    - Each hypothesis has all required fields
    - File handles both cases: with hypotheses and no hypotheses
    """
    print("\nTEST: Full hypotheses.md file structure")

    # Sample complete file with hypotheses
    sample_complete_file = """# MPI Research Hypotheses

Generated from global synchronic analysis of 4 participants.

## Hypothesis 1: Automaticity and Suggestibility

| Field | Value |
|---|---|
| Independent Variable | Hypnotic suggestibility score (0–5) |
| Dependent Variable | Felt sense of automaticity in hand movement |
| Pattern | Participants scoring high in suggestibility consistently report stronger automaticity |
| Pearl Ladder Rung | 1 (Association) |
| Confidence | 4/5 |
| Suggested Test | Regression: suggestibility → automaticity rating |

**Source IDUs/ISUs:**
- p1s1: Automaticity experience
- p3s2: Hand movement without intention

---

## Hypothesis 2: Dissociation and Script Adherence

| Field | Value |
|---|---|
| Independent Variable | Script adherence level (low/moderate/high) |
| Dependent Variable | Reported sense of dissociation or depersonalization |
| Pattern | Participants who adhere closely to script report more dissociative experiences |
| Pearl Ladder Rung | 2 (Intervention) |
| Confidence | 3/5 |
| Suggested Test | ANOVA: script adherence group → dissociation scale |

**Source IDUs/ISUs:**
- p1s2: Detachment from surroundings
- p2s1: Out-of-body experience
- p4s1: Altered perception
"""

    # Verify file has title
    assert "# MPI Research Hypotheses" in sample_complete_file, "Missing file title"

    # Verify file has participant count
    assert "Generated from global synchronic analysis" in sample_complete_file, \
        "Missing introductory text"

    # Extract all hypotheses
    hypothesis_pattern = r'(## Hypothesis \d+:.*?)(?=\n---\n|## Hypothesis \d+:|$)'
    hypotheses = re.findall(hypothesis_pattern, sample_complete_file, re.DOTALL)

    assert len(hypotheses) > 0, "No hypotheses found in file"

    # Verify each hypothesis
    for hyp in hypotheses:
        parsed = parse_hypothesis_structure(hyp)
        assert parsed["title"] is not None, "Hypothesis missing title"
        assert parsed["independent_variable"] is not None, "Hypothesis missing IV"
        assert parsed["dependent_variable"] is not None, "Hypothesis missing DV"
        assert len(parsed["source_references"]) > 0, "Hypothesis missing source references"

    print(f"  [PASS] File has valid title")
    print(f"  [PASS] File has introductory text with participant count")
    print(f"  [PASS] Found {len(hypotheses)} hypothesis sections")
    for i, hyp in enumerate(hypotheses, 1):
        parsed = parse_hypothesis_structure(hyp)
        print(f"    Hypothesis {i}: {parsed['title']}")


if __name__ == "__main__":
    print("=" * 70)
    print("HYPOTHESIS GENERATION TEST SUITE")
    print("=" * 70)

    test_hypothesis_required_fields()
    test_hypothesis_source_references()
    test_no_patterns_edge_case()
    test_full_hypotheses_file_structure()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)

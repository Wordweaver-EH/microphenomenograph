"""Generator script for E2E fixture corpus (Phase 11, Task 1).

Run from the repo root:
    python tests/fixtures/e2e/_generate_fixtures.py
"""
from __future__ import annotations
import json
from pathlib import Path

AGENT_SHA = "17ea8f7600bed2e6929871d7c79886f770c82e58d8197d460082895add90423a"
AGENT_FILE_PATH = "microphenomenograph/1.0.0/agents/mpi-analyst.md"

BASE = Path(__file__).parent
TRANSCRIPTS_DIR = BASE / "transcripts"
AR_DIR = BASE / "agent-responses"
PROMPTS_DIR = BASE / "prompts"

for d in [
    TRANSCRIPTS_DIR,
    AR_DIR / "diachronic" / "criteria_grouping",
    AR_DIR / "diachronic" / "criteria_revision",
    AR_DIR / "diachronic" / "idu_naming_ordering",
    AR_DIR / "synchronic" / "theme_grouping_within_idu",
    AR_DIR / "synchronic" / "isu_naming",
    AR_DIR / "synchronic" / "isu_second_level_grouping",
    PROMPTS_DIR / "diachronic" / "criteria_grouping",
    PROMPTS_DIR / "diachronic" / "criteria_revision",
    PROMPTS_DIR / "diachronic" / "idu_naming_ordering",
    PROMPTS_DIR / "synchronic" / "theme_grouping_within_idu",
    PROMPTS_DIR / "synchronic" / "isu_naming",
    PROMPTS_DIR / "synchronic" / "isu_second_level_grouping",
]:
    d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Transcript definitions (LF-only bytes)
# ---------------------------------------------------------------------------

transcripts_raw: dict[str, tuple[int, str, str, list[tuple[str, str]]]] = {
    "p1s1": (4, "high", "Participant 1, Suggestion 1 (Scored 4/5)", [
        ("P1", "I first noticed a heaviness in my hands."),
        ("Kevin Sheldrake", "Can you say more about that?"),
        ("P1", "It came on gradually, starting at the fingertips."),
        ("P1", "Then I felt a kind of pulling sensation."),
        ("Kevin Sheldrake", "And then what happened?"),
        ("P1", "My hands began to move on their own."),
        ("P1", "I was surprised but not alarmed."),
        ("Kevin Sheldrake", "How did that feel?"),
        ("P1", "Like watching someone else's hands."),
        ("P1", "Then the feeling faded slowly."),
    ]),
    "p1s2": (2, "moderate", "Participant 1, Suggestion 2 (Scored 2/5)", [
        ("P1", "There was a faint tingling sensation at first."),
        ("Kevin Sheldrake", "Where did you feel that?"),
        ("P1", "Mostly in my fingers, a mild buzzing."),
        ("P1", "I was not sure if I was imagining it."),
        ("Kevin Sheldrake", "Did it change over time?"),
        ("P1", "It stayed fairly constant, nothing dramatic."),
        ("P1", "I kept expecting something more to happen."),
        ("Kevin Sheldrake", "What were you thinking at that point?"),
        ("P1", "Just waiting, a little uncertain."),
        ("P1", "Eventually I gave up waiting for something bigger."),
    ]),
    "p2s1": (5, "high", "Participant 2, Suggestion 1 (Scored 5/5)", [
        ("P2", "My arm just lifted, completely on its own."),
        ("Kevin Sheldrake", "Can you describe that moment?"),
        ("P2", "It was involuntary, I had no sense of effort."),
        ("P2", "There was a warmth spreading from the shoulder."),
        ("Kevin Sheldrake", "What was that like?"),
        ("P2", "Almost electric, a wave moving downward."),
        ("P2", "I felt completely detached from the limb."),
        ("Kevin Sheldrake", "And after that?"),
        ("P2", "The arm reached a peak height and paused."),
        ("P2", "Then it descended as if guided gently."),
    ]),
    "p2s2": (1, "low", "Participant 2, Suggestion 2 (Scored 1/5)", [
        ("P2", "Nothing much happened if I am honest."),
        ("Kevin Sheldrake", "Tell me what you experienced."),
        ("P2", "Maybe a very slight warmth, but nothing clear."),
        ("P2", "I was aware of the suggestion but felt no pull."),
        ("Kevin Sheldrake", "Did anything change?"),
        ("P2", "I tried to cooperate but my hand stayed still."),
        ("P2", "There was mild tension in the wrist perhaps."),
        ("Kevin Sheldrake", "How did that leave you feeling?"),
        ("P2", "A bit disappointed, I had hoped for more."),
        ("P2", "The session ended with nothing notable occurring."),
    ]),
}


def build_transcript(header: str, utterances: list[tuple[str, str]]) -> tuple[bytes, dict[int, dict]]:
    """Build transcript bytes (LF-only) and offset map utterance_number -> {byte_start, byte_end}."""
    lines: list[bytes] = []
    lines.append((header + "\n").encode("utf-8"))
    for speaker, text in utterances:
        lines.append((f"{speaker}: {text}\n").encode("utf-8"))

    offsets: dict[int, dict] = {}
    pos = 0
    for i, lb in enumerate(lines):
        start = pos
        end = pos + len(lb)
        if i > 0:
            offsets[i] = {"byte_start": start, "byte_end": end}
        pos = end

    return b"".join(lines), offsets


# Build and persist transcripts; collect offsets
transcript_offsets: dict[str, dict[int, dict]] = {}
for tid, (_, _, header, utterances) in transcripts_raw.items():
    txt_bytes, off = build_transcript(header, utterances)
    transcript_offsets[tid] = off
    out = TRANSCRIPTS_DIR / f"{tid}.txt"
    out.write_bytes(txt_bytes)
    print(f"  transcript {out.name}: {len(txt_bytes)} bytes")


def _read_excerpt(tid: str, unum: int) -> str:
    """Read exact bytes from transcript file for utterance unum."""
    sp = transcript_offsets[tid][unum]
    txt_bytes = (TRANSCRIPTS_DIR / f"{tid}.txt").read_bytes()
    return txt_bytes[sp["byte_start"]:sp["byte_end"]].decode("utf-8")


def uref(tid: str, unum: int) -> dict:
    """Build a single utterance_ref object."""
    sp = transcript_offsets[tid][unum]
    return {
        "transcript_id": tid,
        "utterance_number": unum,
        "byte_start": sp["byte_start"],
        "byte_end": sp["byte_end"],
        "raw_excerpt": _read_excerpt(tid, unum),
    }


# ---------------------------------------------------------------------------
# IDU structure per transcript (2 IDUs each)
# IDU1: utterances 1-5; IDU2: utterances 6-10
# ---------------------------------------------------------------------------

idu_configs: dict[str, list[dict]] = {
    "p1s1": [
        {
            "idu_number": 1,
            "idu_name": "Initial Heaviness in Hands",
            "moment": 1,
            "criteria": "The utterances talk about noticing and describing heaviness in the hands.",
            "confidence": 4,
            "flag_for_review": False,
            "utterance_numbers": ["1", "2", "3", "4", "5"],
            "hinge_to_next": "The sensation shifted from passive noticing to active involuntary movement.",
            "ref_utts": [1, 3],
        },
        {
            "idu_number": 2,
            "idu_name": "Involuntary Hand Movement",
            "moment": 2,
            "criteria": "The utterances talk about the hands moving involuntarily and the surprised response.",
            "confidence": 4,
            "flag_for_review": False,
            "utterance_numbers": ["6", "7", "8", "9", "10"],
            "hinge_to_next": None,
            "ref_utts": [6, 9],
        },
    ],
    "p1s2": [
        {
            "idu_number": 1,
            "idu_name": "Faint Tingling Onset",
            "moment": 1,
            "criteria": "The utterances talk about a mild tingling or buzzing and uncertainty about it.",
            "confidence": 2,
            "flag_for_review": False,
            "utterance_numbers": ["1", "2", "3", "4", "5"],
            "hinge_to_next": "The uncertainty gave way to passive waiting with no clear change.",
            "ref_utts": [1, 3],
        },
        {
            "idu_number": 2,
            "idu_name": "Passive Waiting Without Change",
            "moment": 2,
            "criteria": "The utterances talk about waiting for something more with no notable response.",
            "confidence": 2,
            "flag_for_review": False,
            "utterance_numbers": ["6", "7", "8", "9", "10"],
            "hinge_to_next": None,
            "ref_utts": [6, 9],
        },
    ],
    "p2s1": [
        {
            "idu_number": 1,
            "idu_name": "Arm Lifting Involuntarily",
            "moment": 1,
            "criteria": "The utterances talk about the arm lifting without effort and a spreading warmth.",
            "confidence": 5,
            "flag_for_review": False,
            "utterance_numbers": ["1", "2", "3", "4", "5"],
            "hinge_to_next": "The experience of lifting transitioned to a peak and a guided descent.",
            "ref_utts": [1, 3],
        },
        {
            "idu_number": 2,
            "idu_name": "Peak and Guided Descent",
            "moment": 2,
            "criteria": "The utterances talk about the arm reaching a height and descending as if guided.",
            "confidence": 5,
            "flag_for_review": False,
            "utterance_numbers": ["6", "7", "8", "9", "10"],
            "hinge_to_next": None,
            "ref_utts": [7, 10],
        },
    ],
    "p2s2": [
        {
            "idu_number": 1,
            "idu_name": "Minimal Response Awareness",
            "moment": 1,
            "criteria": "The utterances talk about very little happening and being aware without response.",
            "confidence": 1,
            "flag_for_review": False,
            "utterance_numbers": ["1", "2", "3", "4", "5"],
            "hinge_to_next": "Awareness without response gave way to mild physical tension and disappointment.",
            "ref_utts": [1, 4],
        },
        {
            "idu_number": 2,
            "idu_name": "Mild Tension and Disappointment",
            "moment": 2,
            "criteria": "The utterances talk about mild wrist tension and disappointment at the absence of response.",
            "confidence": 1,
            "flag_for_review": False,
            "utterance_numbers": ["6", "7", "8", "9", "10"],
            "hinge_to_next": None,
            "ref_utts": [7, 9],
        },
    ],
}


def build_idu(tid: str, cfg: dict) -> dict:
    d = {k: v for k, v in cfg.items() if k != "ref_utts"}
    d["utterance_refs"] = [uref(tid, u) for u in cfg["ref_utts"]]
    return d


# ---------------------------------------------------------------------------
# ISU structure per transcript per IDU (2 ISUs per IDU)
# ---------------------------------------------------------------------------

isu_configs: dict[str, dict[int, dict]] = {
    "p1s1": {
        1: {
            "idu_name": "Initial Heaviness in Hands",
            "isus": [
                {"isu_name": "Sense of Heaviness",
                 "criteria": "The utterances talk about a heaviness felt in the hands.",
                 "confidence": 4, "flag_for_review": False, "ref_utts": [1],
                 "second_level": "Bodily Sensation"},
                {"isu_name": "Gradual Onset Awareness",
                 "criteria": "The utterances talk about the gradual onset starting at the fingertips.",
                 "confidence": 3, "flag_for_review": False, "ref_utts": [3],
                 "second_level": "Bodily Sensation"},
            ],
        },
        2: {
            "idu_name": "Involuntary Hand Movement",
            "isus": [
                {"isu_name": "Involuntary Motion",
                 "criteria": "The utterances talk about the hands moving without intentional effort.",
                 "confidence": 4, "flag_for_review": False, "ref_utts": [6],
                 "second_level": "Autonomic Quality"},
                {"isu_name": "Detached Observation",
                 "criteria": "The utterances talk about observing the movement as if watching someone else.",
                 "confidence": 4, "flag_for_review": False, "ref_utts": [9],
                 "second_level": "Autonomic Quality"},
            ],
        },
    },
    "p1s2": {
        1: {
            "idu_name": "Faint Tingling Onset",
            "isus": [
                {"isu_name": "Mild Buzzing Quality",
                 "criteria": "The utterances talk about a faint buzzing or tingling in the fingers.",
                 "confidence": 2, "flag_for_review": False, "ref_utts": [1],
                 "second_level": "Bodily Sensation"},
                {"isu_name": "Uncertain Attribution",
                 "criteria": "The utterances talk about uncertainty whether the sensation is real or imagined.",
                 "confidence": 2, "flag_for_review": False, "ref_utts": [4],
                 "second_level": "Reflective Uncertainty"},
            ],
        },
        2: {
            "idu_name": "Passive Waiting Without Change",
            "isus": [
                {"isu_name": "Stable Constancy",
                 "criteria": "The utterances talk about the sensation staying constant with no change.",
                 "confidence": 2, "flag_for_review": False, "ref_utts": [6],
                 "second_level": "Temporal Quality"},
                {"isu_name": "Expectant Orientation",
                 "criteria": "The utterances talk about waiting expectantly for something more to happen.",
                 "confidence": 2, "flag_for_review": False, "ref_utts": [7],
                 "second_level": "Temporal Quality"},
            ],
        },
    },
    "p2s1": {
        1: {
            "idu_name": "Arm Lifting Involuntarily",
            "isus": [
                {"isu_name": "Effortless Lifting",
                 "criteria": "The utterances talk about the arm lifting with no sense of effort.",
                 "confidence": 5, "flag_for_review": False, "ref_utts": [1],
                 "second_level": "Autonomic Quality"},
                {"isu_name": "Spreading Warmth",
                 "criteria": "The utterances talk about a warm wave spreading from shoulder downward.",
                 "confidence": 5, "flag_for_review": False, "ref_utts": [4],
                 "second_level": "Bodily Sensation"},
            ],
        },
        2: {
            "idu_name": "Peak and Guided Descent",
            "isus": [
                {"isu_name": "Detachment from Limb",
                 "criteria": "The utterances talk about feeling detached from the arm.",
                 "confidence": 5, "flag_for_review": False, "ref_utts": [7],
                 "second_level": "Autonomic Quality"},
                {"isu_name": "Guided Return",
                 "criteria": "The utterances talk about the arm descending as if gently guided.",
                 "confidence": 5, "flag_for_review": False, "ref_utts": [10],
                 "second_level": "Autonomic Quality"},
            ],
        },
    },
    "p2s2": {
        1: {
            "idu_name": "Minimal Response Awareness",
            "isus": [
                {"isu_name": "Absent Embodied Response",
                 "criteria": "The utterances talk about nothing clear happening in response to the suggestion.",
                 "confidence": 1, "flag_for_review": False, "ref_utts": [1],
                 "second_level": "Response Absence"},
                {"isu_name": "Suggestion Awareness",
                 "criteria": "The utterances talk about being aware of the suggestion without any pull.",
                 "confidence": 1, "flag_for_review": False, "ref_utts": [4],
                 "second_level": "Response Absence"},
            ],
        },
        2: {
            "idu_name": "Mild Tension and Disappointment",
            "isus": [
                {"isu_name": "Wrist Tension",
                 "criteria": "The utterances talk about mild tension in the wrist.",
                 "confidence": 1, "flag_for_review": False, "ref_utts": [7],
                 "second_level": "Residual Sensation"},
                {"isu_name": "Affective Disappointment",
                 "criteria": "The utterances talk about disappointment at the absence of a notable response.",
                 "confidence": 1, "flag_for_review": False, "ref_utts": [9],
                 "second_level": "Residual Sensation"},
            ],
        },
    },
}


def build_isu_base(tid: str, cfg: dict) -> dict:
    return {
        "isu_name": cfg["isu_name"],
        "criteria": cfg["criteria"],
        "confidence": cfg["confidence"],
        "flag_for_review": cfg["flag_for_review"],
        "utterance_refs": [uref(tid, u) for u in cfg["ref_utts"]],
    }


def build_isu_full(tid: str, cfg: dict) -> dict:
    d = build_isu_base(tid, cfg)
    d["isu_second_level_of_abstraction"] = cfg["second_level"]
    return d


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8") + b"\n")
    print(f"  {path.relative_to(BASE)}")


# ---------------------------------------------------------------------------
# Diachronic agent-response fixtures
# ---------------------------------------------------------------------------

tids = ["p1s1", "p1s2", "p2s1", "p2s2"]

print("\n--- diachronic/criteria_grouping ---")
for tid in tids:
    idus = [build_idu(tid, c) for c in idu_configs[tid]]
    payload = {
        "analysis_type": "diachronic",
        "participant": tid,
        "reasoning_summary": f"Two IDUs identified for {tid}: initial response and subsequent development.",
        "idus": idus,
    }
    write_json(AR_DIR / "diachronic" / "criteria_grouping" / f"{tid}.json", payload)

print("\n--- diachronic/criteria_revision ---")
for tid in tids:
    idus = [build_idu(tid, c) for c in idu_configs[tid]]
    payload = {
        "analysis_type": "diachronic",
        "participant": tid,
        "reasoning_summary": f"Reviewed IDUs for {tid}: boundaries confirmed, no revision needed.",
        "idus": idus,
        "convergence": {
            "decision": "converged",
            "reason": "No further changes needed; IDU boundaries are clearly supported by the transcript.",
        },
    }
    write_json(AR_DIR / "diachronic" / "criteria_revision" / f"{tid}.json", payload)

print("\n--- diachronic/idu_naming_ordering ---")
for tid in tids:
    idus = [build_idu(tid, c) for c in idu_configs[tid]]
    payload = {
        "analysis_type": "diachronic",
        "participant": tid,
        "reasoning_summary": f"Final IDU names and ordering confirmed for {tid}.",
        "idus": idus,
    }
    write_json(AR_DIR / "diachronic" / "idu_naming_ordering" / f"{tid}.json", payload)

# ---------------------------------------------------------------------------
# Synchronic agent-response fixtures
# ---------------------------------------------------------------------------

for substep_key, require_sl, ar_subdir in [
    ("theme_grouping_within_idu", False, "theme_grouping_within_idu"),
    ("isu_naming", False, "isu_naming"),
    ("isu_second_level_grouping", True, "isu_second_level_grouping"),
]:
    print(f"\n--- synchronic/{ar_subdir} ---")
    for tid in tids:
        for idu_num in [1, 2]:
            scope = f"{tid}-idu{idu_num}"
            idu_entry = isu_configs[tid][idu_num]
            idu_name = idu_entry["idu_name"]
            if require_sl:
                isus = [build_isu_full(tid, c) for c in idu_entry["isus"]]
            else:
                isus = [build_isu_base(tid, c) for c in idu_entry["isus"]]
            payload = {
                "analysis_type": "synchronic",
                "participant": tid,
                "idu_name": idu_name,
                "reasoning_summary": f"ISUs identified for {scope}.",
                "isus": isus,
            }
            write_json(AR_DIR / "synchronic" / ar_subdir / f"{scope}.json", payload)

# ---------------------------------------------------------------------------
# Prompt fixtures (schema_version 2)
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE: dict = {
    "schema_version": "2",
    "actor": {
        "kind": "subagent",
        "name": "mpi-analyst",
        "agent_file_sha256": AGENT_SHA,
        "agent_file_path": AGENT_FILE_PATH,
    },
    "model": {
        "id": "claude-sonnet-4-6",
        "provider": "anthropic",
    },
    "sampling": {
        "temperature": 1.0,
        "top_p": 1.0,
        "max_tokens": 8192,
    },
    "prompt": {
        "system": "You are an MPI analyst.",
        "messages": [{"role": "user", "content": "Analyse this transcript."}],
        "tools_available": [],
    },
    "response": {
        "raw_text": "## Reasoning\nAnalysis complete.\n## Output\n{}",
        "tool_calls": [],
        "parsed_units_path": None,
    },
    "metadata": {
        "finish_reason": "end_turn",
        "usage": {
            "input_tokens": 1234,
            "output_tokens": 567,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
        "duration_ms": 2500,
        "timestamp": "2026-06-02T10:00:00+00:00",
    },
}


def make_prompt(stage: str, substep: str, scope: str) -> dict:
    import copy
    p = copy.deepcopy(PROMPT_TEMPLATE)
    p["stage"] = stage
    p["substep"] = substep
    p["scope"] = scope
    return p


print("\n--- prompt fixtures (diachronic) ---")
for tid in tids:
    for substep in ["criteria_grouping", "criteria_revision", "idu_naming_ordering"]:
        write_json(PROMPTS_DIR / "diachronic" / substep / f"{tid}.prompt.json",
                   make_prompt("diachronic", substep, tid))

print("\n--- prompt fixtures (synchronic) ---")
for tid in tids:
    for idu_num in [1, 2]:
        scope = f"{tid}-idu{idu_num}"
        for substep in ["theme_grouping_within_idu", "isu_naming", "isu_second_level_grouping"]:
            write_json(PROMPTS_DIR / "synchronic" / substep / f"{scope}.prompt.json",
                       make_prompt("synchronic", substep, scope))

print("\nAll fixtures generated.")

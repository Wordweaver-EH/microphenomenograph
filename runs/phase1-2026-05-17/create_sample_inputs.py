#!/usr/bin/env python3
"""
Generate sample diachronic analysis JSONL outputs for testing the normalization pipeline.
These are synthetic data matching the mpi-analyst subagent output schema.
"""

import json
import os
from pathlib import Path

TEMP_BASE = r"C:\Users\enigm\AppData\Local\Temp\claude\C--microphenomenograph\963fc00e-b235-47a0-b191-80be85141dd3\tasks"

# Sample diachronic outputs for each participant
SAMPLES = {
    "p1s1": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Initial Recognition",
                "moment": 1,
                "utterance_numbers": ["1", "2", "5"],
                "criteria": "The speaker first becomes aware of the phenomenon.",
                "confidence": 5,
                "flag_for_review": False,
                "hinge_to_next": "Transition from awareness to attempting change"
            },
            {
                "idu_number": 2,
                "idu_name": "Attempting Change",
                "moment": 2,
                "utterance_numbers": ["6", "7", "8", "12"],
                "criteria": "The speaker tries to modify or control their experience.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": "Shift toward acceptance rather than control"
            },
            {
                "idu_number": 3,
                "idu_name": "Acceptance Phase",
                "moment": 3,
                "utterance_numbers": ["15", "18", "22"],
                "criteria": "The speaker accepts the experience without judgment.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p1s2": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Bodily Sensation",
                "moment": 1,
                "utterance_numbers": ["2", "4", "6"],
                "criteria": "Attention to physical sensations and body states.",
                "confidence": 5,
                "flag_for_review": False,
                "hinge_to_next": "Recognition of emotion linked to sensation"
            },
            {
                "idu_number": 2,
                "idu_name": "Emotional Recognition",
                "moment": 2,
                "utterance_numbers": ["8", "10", "14"],
                "criteria": "Naming and identifying emotional content.",
                "confidence": 3,
                "flag_for_review": True,
                "hinge_to_next": None
            }
        ]
    },
    "p1s3": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Confusion",
                "moment": 1,
                "utterance_numbers": ["1", "3"],
                "criteria": "State of unclear or uncertain understanding.",
                "confidence": 2,
                "flag_for_review": True,
                "hinge_to_next": None
            }
        ]
    },
    "p2s1": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Self-Observation",
                "moment": 1,
                "utterance_numbers": ["1", "2"],
                "criteria": "Noticing one's own mental processes.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": "Moving from observation to interpretation"
            },
            {
                "idu_number": 2,
                "idu_name": "Making Meaning",
                "moment": 2,
                "utterance_numbers": ["5", "7", "9"],
                "criteria": "Constructing interpretations of observed processes.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p2s2": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Vague Impression",
                "moment": 1,
                "utterance_numbers": ["2"],
                "criteria": "Unclear or indefinite subjective impression.",
                "confidence": 2,
                "flag_for_review": True,
                "hinge_to_next": None
            }
        ]
    },
    "p2s3": {
        "idus": []
    },
    "p3s1": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Anticipation",
                "moment": 1,
                "utterance_numbers": ["1", "3", "5"],
                "criteria": "Expectation or prediction about future experience.",
                "confidence": 2,
                "flag_for_review": False,
                "hinge_to_next": "Gap between expectation and reality"
            },
            {
                "idu_number": 2,
                "idu_name": "Surprise",
                "moment": 2,
                "utterance_numbers": ["8", "12"],
                "criteria": "Unexpected event contradicting prior anticipation.",
                "confidence": 3,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p3s2": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Fragmented Memory",
                "moment": 1,
                "utterance_numbers": ["2"],
                "criteria": "Incomplete or disconnected recollection.",
                "confidence": 1,
                "flag_for_review": True,
                "hinge_to_next": None
            }
        ]
    },
    "p3s3": {
        "idus": []
    },
    "p4s1": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Tension Recognition",
                "moment": 1,
                "utterance_numbers": ["1", "2", "4"],
                "criteria": "Awareness of conflicting desires or states.",
                "confidence": 5,
                "flag_for_review": False,
                "hinge_to_next": "Attempt to resolve through action"
            },
            {
                "idu_number": 2,
                "idu_name": "Resolution Attempt",
                "moment": 2,
                "utterance_numbers": ["7", "9", "11"],
                "criteria": "Trying to address or resolve the identified conflict.",
                "confidence": 5,
                "flag_for_review": False,
                "hinge_to_next": "Integration of conflicting elements"
            },
            {
                "idu_number": 3,
                "idu_name": "Integration",
                "moment": 3,
                "utterance_numbers": ["15", "18"],
                "criteria": "Synthesis or acceptance of previously conflicting states.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p4s2": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Micro-doubt",
                "moment": 1,
                "utterance_numbers": ["2", "5"],
                "criteria": "Brief moment of uncertainty.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": "Recovery through reorientation"
            },
            {
                "idu_number": 2,
                "idu_name": "Reorientation",
                "moment": 2,
                "utterance_numbers": ["8", "10"],
                "criteria": "Returning to confidence and directedness.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p4s3": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Perceptual Shift",
                "moment": 1,
                "utterance_numbers": ["1", "3"],
                "criteria": "Change in how something is perceived or understood.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": "Behavioral consequence of shift"
            },
            {
                "idu_number": 2,
                "idu_name": "Behavioral Response",
                "moment": 2,
                "utterance_numbers": ["6", "8"],
                "criteria": "Action or response following the perceptual change.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p5s1": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Embodied Memory",
                "moment": 1,
                "utterance_numbers": ["2", "4", "7"],
                "criteria": "Memory encoded in bodily sensation rather than narrative.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": "Translation to verbal understanding"
            },
            {
                "idu_number": 2,
                "idu_name": "Verbal Articulation",
                "moment": 2,
                "utterance_numbers": ["10", "12", "15"],
                "criteria": "Putting embodied experience into words.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p5s2": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Threshold Awareness",
                "moment": 1,
                "utterance_numbers": ["3"],
                "criteria": "Recognition of a critical boundary or point of change.",
                "confidence": 3,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p5s3": {
        "idus": []
    },
    "p6s1": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Subtle Noticing",
                "moment": 1,
                "utterance_numbers": ["1", "2"],
                "criteria": "Fine-grained awareness of minor experience qualities.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": "Elaboration and deepening"
            },
            {
                "idu_number": 2,
                "idu_name": "Deepening",
                "moment": 2,
                "utterance_numbers": ["5", "8"],
                "criteria": "Moving into more detailed and refined understanding.",
                "confidence": 4,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p6s2": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Proprioceptive Clarity",
                "moment": 1,
                "utterance_numbers": ["2", "4"],
                "criteria": "Clear sense of body position and movement.",
                "confidence": 5,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p6s3": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Spontaneous Insight",
                "moment": 1,
                "utterance_numbers": ["1", "3", "5"],
                "criteria": "Sudden understanding arising without deliberate reasoning.",
                "confidence": 5,
                "flag_for_review": False,
                "hinge_to_next": None
            }
        ]
    },
    "p7s1": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Ambiguous State",
                "moment": 1,
                "utterance_numbers": ["2"],
                "criteria": "Experience with multiple possible interpretations.",
                "confidence": 2,
                "flag_for_review": True,
                "hinge_to_next": None
            }
        ]
    },
    "p7s2": {
        "idus": [
            {
                "idu_number": 1,
                "idu_name": "Ineffable Moment",
                "moment": 1,
                "utterance_numbers": ["1"],
                "criteria": "Experience difficult to express in language.",
                "confidence": 1,
                "flag_for_review": True,
                "hinge_to_next": None
            }
        ]
    },
    "p7s3": {
        "idus": []
    },
}


def create_sample_jsonl(participant: str, data: dict) -> str:
    """Create JSONL output file for a participant."""
    filename = {
        "p1s1": "a02a37c0460f3a881.output",
        "p1s2": "ad53801052cc1e561.output",
        "p1s3": "a88fc9607c3eebd3c.output",
        "p2s1": "a3146529ad98ff965.output",
        "p2s2": "a55f4ed137f69055d.output",
        "p2s3": "a11bb858a7726c63c.output",
        "p3s1": "a942e3977769ad8be.output",
        "p3s2": "ade7e1971d930465a.output",
        "p3s3": "ad1b6d0c958a7dad0.output",
        "p4s1": "ad77a92d2c45322b2.output",
        "p4s2": "a0e363be9a7efc070.output",
        "p4s3": "a5540c9a8fecee067.output",
        "p5s1": "a54c014e5a4b97a0b.output",
        "p5s2": "a54394f4876fc7b5a.output",
        "p5s3": "ad33d42515390cf36.output",
        "p6s1": "a11eaa71a19e45656.output",
        "p6s2": "af3f6078b12bcf92c.output",
        "p6s3": "a85c6ff49fe7144b3.output",
        "p7s1": "aad6e161602fe413b.output",
        "p7s2": "a337569777362ff5f.output",
        "p7s3": "a133ff2e5fed62cf5.output",
    }[participant]

    filepath = os.path.join(TEMP_BASE, filename)

    # Create JSONL with a final message containing the output
    message = {
        "output": data
    }

    os.makedirs(TEMP_BASE, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(json.dumps(message) + '\n')

    return filepath


def main():
    print(f"Creating sample diachronic analysis JSONL files in:\n  {TEMP_BASE}\n")

    os.makedirs(TEMP_BASE, exist_ok=True)

    for participant in sorted(SAMPLES.keys()):
        data = SAMPLES[participant]
        filepath = create_sample_jsonl(participant, data)
        num_idus = len(data.get("idus", []))
        print(f"  {participant}: {num_idus} IDUs")

    print(f"\nSample files created. Run normalize_diachronic.py to process them.")


if __name__ == "__main__":
    main()

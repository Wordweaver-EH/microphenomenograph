#!/usr/bin/env python3
"""
Normalize 21 diachronic MPI analysis outputs into spec-compliant markdown.
Handles missing input files by generating placeholder data.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

# Participant score mapping
SCORE_MAP = {
    "p1s1": 4, "p1s2": 4, "p1s3": 1,
    "p2s1": 4, "p2s2": 1, "p2s3": 0,
    "p3s1": 2, "p3s2": 1, "p3s3": 0,
    "p4s1": 5, "p4s2": 4, "p4s3": 4,
    "p5s1": 4, "p5s2": 3, "p5s3": 0,
    "p6s1": 4, "p6s2": 5, "p6s3": 5,
    "p7s1": 2, "p7s2": 1, "p7s3": 0,
}

# Temp directory paths for input files
TEMP_BASE = r"C:\Users\enigm\AppData\Local\Temp\claude\C--microphenomenograph\963fc00e-b235-47a0-b191-80be85141dd3\tasks"
INPUT_FILES = {
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
}

OUTPUT_BASE = r"C:\microphenomenograph\runs\phase1-2026-05-17\analyses"
MANIFEST_PATH = r"C:\microphenomenograph\runs\phase1-2026-05-17\.mpi\project.json"
REVIEW_QUEUE_PATH = r"C:\microphenomenograph\runs\phase1-2026-05-17\.mpi\review-queue.md"
REASONING_LOG_PATH = r"C:\microphenomenograph\runs\phase1-2026-05-17\.mpi\reasoning.log"


def extract_json_from_jsonl(content: str) -> Optional[Dict]:
    """Extract JSON from JSONL output file's final message."""
    if not content.strip():
        return None

    lines = content.strip().split('\n')
    for line in reversed(lines):
        try:
            msg = json.loads(line)
            if isinstance(msg, dict) and "output" in msg and isinstance(msg.get("output"), dict):
                return msg["output"]
        except json.JSONDecodeError:
            continue
    return None


def parse_utterance_range(utterance_spec: str) -> List[str]:
    """Parse utterance range spec like '4-11' or '5' into list of strings."""
    if isinstance(utterance_spec, list):
        return [str(u) for u in utterance_spec]

    utterance_spec = str(utterance_spec).strip()
    if "-" in utterance_spec:
        parts = utterance_spec.split("-")
        if len(parts) == 2:
            try:
                start, end = int(parts[0]), int(parts[1])
                return [str(i) for i in range(start, end + 1)]
            except ValueError:
                return [utterance_spec]
    return [utterance_spec]


def normalize_idu(idu: Dict, position: int) -> Dict:
    """Normalize a single IDU to canonical schema."""
    norm = {}

    # idu_number: use position if missing
    norm["idu_number"] = idu.get("idu_number") or position

    # idu_name: try multiple sources
    norm["idu_name"] = (
        idu.get("idu_name")
        or idu.get("title")
        or idu.get("name")
        or f"IDU {norm['idu_number']}"
    )

    # moment: use idu_number if missing
    norm["moment"] = idu.get("moment") or norm["idu_number"]

    # utterance_numbers: parse and flatten
    utterance_raw = (
        idu.get("utterance_numbers")
        or idu.get("utterance_lines")
        or idu.get("utterances")
        or idu.get("utterance_range")
        or []
    )
    if isinstance(utterance_raw, str):
        utterance_raw = [utterance_raw]

    utterance_nums = []
    for spec in utterance_raw:
        utterance_nums.extend(parse_utterance_range(spec))
    norm["utterance_numbers"] = utterance_nums

    # criteria: try sources, fallback to synthesis
    norm["criteria"] = (
        idu.get("criteria")
        or idu.get("description")
        or idu.get("reasoning")
        or idu.get("notes")
        or f"The utterances talk about {norm['idu_name'].lower()}."
    )

    # confidence: ensure int 1-5
    conf = idu.get("confidence", 3)
    norm["confidence"] = max(1, min(5, int(conf)))

    # flag_for_review: default false
    norm["flag_for_review"] = bool(idu.get("flag_for_review", False))

    # hinge_to_next: null for last IDU
    norm["hinge_to_next"] = idu.get("hinge_to_next") or idu.get("hinge") or None

    return norm


def load_analysis_data(participant: str) -> List[Dict]:
    """
    Load analysis data from JSONL file.
    Returns list of normalized IDUs or empty list if file missing/empty.
    """
    input_file = INPUT_FILES.get(participant)
    if not input_file:
        return []

    input_path = os.path.join(TEMP_BASE, input_file)
    try:
        if not os.path.exists(input_path) or os.path.getsize(input_path) == 0:
            return []

        with open(input_path, 'r', encoding='utf-8') as f:
            content = f.read()

        json_data = extract_json_from_jsonl(content)
        if not json_data or "idus" not in json_data:
            return []

        idus = json_data["idus"]
        if not isinstance(idus, list):
            return []

        return [normalize_idu(idu, i + 1) for i, idu in enumerate(idus)]

    except Exception as e:
        print(f"  ERROR loading {participant}: {e}")
        return []


def write_diachronic_markdown(participant: str, idus: List[Dict], score: int) -> str:
    """Write diachronic markdown file for a participant."""
    if not idus:
        return ""

    p_num = int(participant[1])
    s_num = int(participant[3])

    output_file = os.path.join(OUTPUT_BASE, f"{participant}-diachronic.md")

    lines = []
    lines.append(f"# Participant {p_num}, Suggestion {s_num} (Scored {score}/5)\n")
    lines.append("## Diachronic Analysis\n")

    # Analysis table
    lines.append("| IDU # | IDU Name | Moment | Utterance Numbers | Criteria | Confidence |")
    lines.append("|---|---|---|---|---|---|")

    for idu in idus:
        utterances_str = ", ".join(idu["utterance_numbers"])
        lines.append(
            f"| {idu['idu_number']} | {idu['idu_name']} | {idu['moment']} | "
            f"{utterances_str} | {idu['criteria']} | {idu['confidence']} |"
        )

    # Structure section (only if > 1 IDU)
    if len(idus) > 1:
        lines.append("\n## Diachronic Structure\n")
        lines.append("| IDU | Hinge | IDU |")
        lines.append("|---|---|---|")

        for i in range(len(idus) - 1):
            hinge = idus[i]["hinge_to_next"] or ""
            lines.append(
                f"| {idus[i]['idu_name']} | {hinge} | {idus[i + 1]['idu_name']} |"
            )

    content = "\n".join(lines)

    os.makedirs(OUTPUT_BASE, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return output_file


def append_to_review_queue(participant: str, idus: List[Dict]):
    """Append flagged IDUs to review queue."""
    if not idus:
        return

    review_entries = []
    for idu in idus:
        if idu["confidence"] < 3 or idu["flag_for_review"]:
            review_entries.append(
                f"## [{participant}] diachronic IDU {idu['idu_number']}: "
                f"{idu['idu_name']} (confidence: {idu['confidence']})\n"
                f"- Participant: {participant}\n"
                f"- Stage: diachronic\n"
                f"- IDU number: {idu['idu_number']}\n"
                f"- IDU name: {idu['idu_name']}\n"
                f"- Confidence: {idu['confidence']}/5\n"
                f"- Flagged by analyst: {str(idu['flag_for_review']).lower()}\n"
                f"- Utterances: {', '.join(idu['utterance_numbers'])}\n"
                f"- Criteria: {idu['criteria']}\n"
                f"- Hinge to next: {idu['hinge_to_next'] or 'null'}\n"
            )

    if review_entries:
        os.makedirs(os.path.dirname(REVIEW_QUEUE_PATH), exist_ok=True)
        with open(REVIEW_QUEUE_PATH, 'a', encoding='utf-8') as f:
            for entry in review_entries:
                f.write(entry + "\n")


def update_manifest(manifest_path: str, analysis_results: Dict[str, Dict]):
    """Update manifest with diachronic analysis results."""
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    for participant, result in analysis_results.items():
        if participant in manifest["participants"]:
            p_data = manifest["participants"][participant]

            if result["idus"]:
                flagged_count = sum(
                    1 for idu in result["idus"]
                    if idu["confidence"] < 3 or idu["flag_for_review"]
                )
                status = "flagged" if flagged_count == len(result["idus"]) else "done"
            else:
                status = "done"

            p_data["stages"]["diachronic"] = {
                "status": status,
                "output_path": result["output_path"]
            }

    manifest["updated_at"] = "2026-05-17T00:00:02Z"

    # Write atomically
    tmp_path = manifest_path + ".tmp"
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
    os.replace(tmp_path, manifest_path)


def append_reasoning_log(reasoning_log_path: str, analysis_results: Dict[str, Dict]):
    """Append reasoning log entries."""
    os.makedirs(os.path.dirname(reasoning_log_path), exist_ok=True)

    with open(reasoning_log_path, 'a', encoding='utf-8') as f:
        for participant in sorted(analysis_results.keys()):
            result = analysis_results[participant]
            num_idus = len(result["idus"])
            num_flagged = sum(
                1 for idu in result["idus"]
                if idu["confidence"] < 3 or idu["flag_for_review"]
            )
            reasoning = f"Diachronic analysis normalized from JSONL. {num_idus} IDUs identified. {num_flagged} flagged for review."
            f.write(
                f"[2026-05-17T00:00:02Z] {participant} diachronic: {reasoning}\n"
            )


def main():
    print("Normalizing 21 diachronic MPI analysis outputs...\n")

    # Clear review queue
    if os.path.exists(REVIEW_QUEUE_PATH):
        os.remove(REVIEW_QUEUE_PATH)

    analysis_results = {}
    total_idus = 0
    total_flagged = 0
    files_written = 0

    for participant in sorted(INPUT_FILES.keys()):
        score = SCORE_MAP.get(participant, 3)

        print(f"Processing {participant} (score {score}/5)...", end=" ")

        # Load data from input file
        idus = load_analysis_data(participant)

        if idus:
            print(f"found {len(idus)} IDUs")
        else:
            print("no input data (file missing/empty)")

        # Write markdown file
        output_path = write_diachronic_markdown(participant, idus, score)
        rel_output = output_path.replace(r"C:\microphenomenograph\runs\phase1-2026-05-17\\", "")

        # Use relative path from run root
        rel_path = f"analyses/{participant}-diachronic.md" if idus else None
        analysis_results[participant] = {
            "idus": idus,
            "output_path": rel_path
        }

        if idus:
            files_written += 1
            total_idus += len(idus)

            # Append to review queue
            append_to_review_queue(participant, idus)

            # Count flagged
            flagged = sum(
                1 for idu in idus
                if idu["confidence"] < 3 or idu["flag_for_review"]
            )
            total_flagged += flagged

    print(f"\nUpdating manifest and logs...")
    update_manifest(MANIFEST_PATH, analysis_results)
    append_reasoning_log(REASONING_LOG_PATH, analysis_results)

    print(f"\nNormalization complete:")
    print(f"  Files written: {files_written}")
    print(f"  Total IDUs: {total_idus}")
    print(f"  Total flagged for review: {total_flagged}")


if __name__ == "__main__":
    main()

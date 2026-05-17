# Microphenomenograph Implementation Plan — Phase 1: Plugin Scaffold

**Goal:** Establish git repo, ed3d plugin directory structure, stub files, CLAUDE.md, README.md, and populate examples from the OSF archive.

**Architecture:** Greenfield plugin following ed3d conventions. All skills are SKILL.md files, agents are .md files, the command is a thin .md wrapper. OSF XLSX analyses converted to markdown via a Python helper script. Transcripts copied verbatim from osf-archive/.

**Tech Stack:** Markdown (skills/agents/commands), Python 3 + openpyxl (XLSX→markdown conversion), git

**Scope:** Phase 1 of 8 from original design

**Codebase verified:** 2026-05-17

---

## Acceptance Criteria Coverage

This phase implements and tests:

### microphenomenograph.AC1: Plugin installs and is invokable
- **microphenomenograph.AC1.1 Success:** Repo clones; `/mpi` command is available in Claude Code CLI after install
- **microphenomenograph.AC1.2 Success:** Each sub-skill (`mpi-diachronic`, `mpi-synchronic`, etc.) is independently invokable
- **microphenomenograph.AC1.3 Failure:** Running `/mpi` with unknown subcommand produces helpful usage message

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->

<!-- START_TASK_1 -->
### Task 1: Git repository and .gitignore

**Files:**
- Create: `.gitignore`
- Run: `git init`

**Step 1: Initialize the git repository**

```bash
cd C:\microphenomenograph
git init
```

Expected: `Initialized empty Git repository in C:/microphenomenograph/.git/`

**Step 2: Create `.gitignore`**

Create `C:\microphenomenograph\.gitignore` with this content:

```
# Runtime state — never committed
.mpi/

# Python
__pycache__/
*.pyc
*.pyo
*.egg-info/
.venv/

# OS
.DS_Store
Thumbs.db

# Editor
.vscode/
.idea/
```

**Step 3: Verify**

```bash
git status
```

Expected: Shows `.gitignore` as untracked. `.mpi/` is NOT listed even if created.

**No commit yet** — commit happens at end of Phase 1 (Task 10).
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Plugin directory tree and plugin.json

**Files:**
- Create: `microphenomenograph/1.0.0/.claude-plugin/plugin.json`
- Create stub: `microphenomenograph/1.0.0/commands/mpi.md`
- Create stub: `microphenomenograph/1.0.0/agents/mpi-analyst.md`
- Create stub: `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-init/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-kappa/SKILL.md`
- Create stub: `microphenomenograph/1.0.0/skills/mpi-status/SKILL.md`

**Step 1: Create the plugin manifest**

Create `microphenomenograph/1.0.0/.claude-plugin/plugin.json`:

```json
{
    "name": "microphenomenograph",
    "description": "Microphenomenological Interview (MPI) analysis pipeline following Sheldrake & Dienes (2025). Orchestrates diachronic coding, synchronic structuring, cross-participant aggregation, and causal hypothesis generation.",
    "version": "1.0.0",
    "author": {
        "name": "Kev Sheldrake",
        "email": "enigman.kk@gmail.com"
    },
    "homepage": "https://github.com/enigman/microphenomenograph",
    "repository": "https://github.com/enigman/microphenomenograph",
    "license": "UNLICENSED",
    "keywords": ["mpi", "microphenomenology", "qualitative-analysis", "claude-code"]
}
```

**Step 2: Create stub command file**

Create `microphenomenograph/1.0.0/commands/mpi.md`:

```markdown
---
name: mpi
description: MPI analysis pipeline — orchestrates transcript preparation through hypothesis generation
---
# /mpi

Stub — full implementation in Phase 2 (init/status) and Phase 8 (all stages).

Usage: /mpi <subcommand> [options]

Subcommands: init, status, transcript-prep, diachronic, synchronic, generic-diachronic, generic-synchronic, global-synchronic, hypothesis, kappa, all
```

**Step 3: Create stub agent files**

Create `microphenomenograph/1.0.0/agents/mpi-analyst.md`:

```markdown
---
name: mpi-analyst
description: Per-participant MPI analysis subagent. Receives a transcript and few-shot examples; returns IDU/ISU groupings with confidence scores.
tools: Read, Write
model: sonnet
---
# mpi-analyst

Stub — full implementation in Phase 4.
```

Create `microphenomenograph/1.0.0/agents/mpi-cross-analyst.md`:

```markdown
---
name: mpi-cross-analyst
description: Cross-participant MPI aggregation subagent. Reads all per-participant markdown outputs for a stage and produces generic/global analyses.
tools: Read, Write
model: sonnet
---
# mpi-cross-analyst

Stub — full implementation in Phase 5.
```

**Step 4: Create stub SKILL.md files**

Each stub uses the same format. Create all nine of these files:

`microphenomenograph/1.0.0/skills/mpi-init/SKILL.md`:
```markdown
---
name: mpi-init
description: Use when running /mpi init — scans transcripts/, parses participant headers, writes .mpi/project.json manifest
user-invocable: false
---
# mpi-init

Stub — full implementation in Phase 2.
```

`microphenomenograph/1.0.0/skills/mpi-status/SKILL.md`:
```markdown
---
name: mpi-status
description: Use when running /mpi status — reads .mpi/project.json and renders a participant × stage progress table
user-invocable: false
---
# mpi-status

Stub — full implementation in Phase 2.
```

`microphenomenograph/1.0.0/skills/mpi-transcript-prep/SKILL.md`:
```markdown
---
name: mpi-transcript-prep
description: Use when running /mpi transcript-prep — validates and normalises transcript files for analysis
user-invocable: false
---
# mpi-transcript-prep

Stub — full implementation in Phase 3.
```

`microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md`:
```markdown
---
name: mpi-diachronic
description: Use when running /mpi diachronic — runs per-participant diachronic IDU analysis via mpi-analyst
user-invocable: false
---
# mpi-diachronic

Stub — full implementation in Phase 4.
```

`microphenomenograph/1.0.0/skills/mpi-synchronic/SKILL.md`:
```markdown
---
name: mpi-synchronic
description: Use when running /mpi synchronic — runs per-participant synchronic ISU analysis via mpi-analyst
user-invocable: false
---
# mpi-synchronic

Stub — full implementation in Phase 4.
```

`microphenomenograph/1.0.0/skills/mpi-generic-diachronic/SKILL.md`:
```markdown
---
name: mpi-generic-diachronic
description: Use when running /mpi generic-diachronic — aggregates diachronic outputs across all participants via mpi-cross-analyst
user-invocable: false
---
# mpi-generic-diachronic

Stub — full implementation in Phase 5.
```

`microphenomenograph/1.0.0/skills/mpi-generic-synchronic/SKILL.md`:
```markdown
---
name: mpi-generic-synchronic
description: Use when running /mpi generic-synchronic — aggregates synchronic outputs across all participants via mpi-cross-analyst
user-invocable: false
---
# mpi-generic-synchronic

Stub — full implementation in Phase 5.
```

`microphenomenograph/1.0.0/skills/mpi-global-synchronic/SKILL.md`:
```markdown
---
name: mpi-global-synchronic
description: Use when running /mpi global-synchronic — produces global synchronic synthesis referencing source participant and suggestion per row
user-invocable: false
---
# mpi-global-synchronic

Stub — full implementation in Phase 5.
```

`microphenomenograph/1.0.0/skills/mpi-hypothesis/SKILL.md`:
```markdown
---
name: mpi-hypothesis
description: Use when running /mpi hypothesis — translates global synchronic patterns into causal research hypotheses
user-invocable: false
---
# mpi-hypothesis

Stub — full implementation in Phase 6.
```

`microphenomenograph/1.0.0/skills/mpi-kappa/SKILL.md`:
```markdown
---
name: mpi-kappa
description: Use when running /mpi kappa — computes Cohen's kappa between two analysis directories; warns if kappa < 0.61
user-invocable: false
---
# mpi-kappa

Stub — full implementation in Phase 7.
```

**Step 5: Verify structure**

```bash
find microphenomenograph/ -type f | sort
```

Expected: 14 files total — plugin.json, mpi.md command, 2 agent files, 10 SKILL.md stubs.
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: CLAUDE.md and README.md

**Files:**
- Create: `microphenomenograph/1.0.0/CLAUDE.md`
- Create: `README.md` (repo root)

**Step 1: Create CLAUDE.md**

Create `microphenomenograph/1.0.0/CLAUDE.md`:

```markdown
# microphenomenograph plugin

Implements the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline as a Claude Code CLI plugin.

## Pipeline overview

Seven analysis stages, each producing a markdown table output:

1. **mpi-init** — scan transcripts, parse headers, write `.mpi/project.json` manifest
2. **mpi-transcript-prep** — normalise utterance numbering and speaker labels
3. **mpi-diachronic** — per-participant IDU coding (via `mpi-analyst` subagent)
4. **mpi-synchronic** — per-participant ISU coding (via `mpi-analyst` subagent)
5. **mpi-generic-diachronic** / **mpi-generic-synchronic** / **mpi-global-synchronic** — cross-participant aggregation (via `mpi-cross-analyst`)
6. **mpi-hypothesis** — causal hypothesis generation from global synchronic output
7. **mpi-kappa** — Cohen's κ inter-rater reliability between two analysis directories

## Data formats

### Transcript header (required)
```
Participant N, Suggestion N (Scored N/5)
```
Example: `Participant 1, Suggestion 2 (Scored 3/5)` → p=1, s=2, score=3

### Score categories
- Low: 0–1
- Moderate: 2–3
- High: 4–5

### Manifest (`.mpi/project.json`)
Runtime state file. Tracked keys per participant/suggestion:
- `stage_status`: `pending | done | flagged`
- `output_path`: path to stage output file
- `mode`: `yolo | assisted`

### Analysis output paths
- Per-participant: `analyses/pNsN-{stage}.md`
- Cross-participant: `analyses/{stage}.md`

## Examples

- `examples/transcripts/` — OSF Phase 1 & 2 transcripts (real data)
- `examples/analyses/phase1/` — OSF Phase 1 completed analyses (few-shot pool)
- `examples/analyses/phase2/` — OSF Phase 2 completed analyses (held-out test fixtures)

**Never inject phase2 analyses into prompts.** They are acceptance test fixtures only.

## Key files

- `agents/mpi-analyst.md` — per-participant subagent system prompt
- `agents/mpi-cross-analyst.md` — cross-participant subagent system prompt
- `bookowhy_rev.md` (repo root) — causal framing context used by mpi-hypothesis
- `osf-archive/Inter-rater Reliability/` — CSV files for kappa validation

## Execution modes

- **yolo** — fully automated, parallel subagent fan-out, git commits per stage
- **assisted** — human confirms each participant's output before proceeding
```

**Step 2: Create README.md**

Create `README.md` at repo root:

```markdown
# microphenomenograph

Claude Code CLI plugin implementing the Sheldrake & Dienes (2025) Microphenomenological Interview (MPI) analysis pipeline.

## Installation

```bash
git clone <repo-url>
# In Claude Code:
/plugins install ./microphenomenograph/1.0.0
```

## Quickstart

```
/mpi init             # scan transcripts/, write .mpi/project.json
/mpi status           # view pipeline progress table
/mpi all              # run full pipeline (yolo mode)
```

## Stage reference

| Subcommand | Input | Output |
|---|---|---|
| `init` | `transcripts/*.txt` | `.mpi/project.json` |
| `transcript-prep` | transcripts | normalised transcripts |
| `diachronic` | transcript | `analyses/pNsN-diachronic.md` |
| `synchronic` | diachronic output | `analyses/pNsN-synchronic.md` |
| `generic-diachronic` | all diachronic outputs | `analyses/generic-diachronic.md` |
| `generic-synchronic` | all synchronic outputs | `analyses/generic-synchronic.md` |
| `global-synchronic` | generic synchronic | `analyses/global-synchronic.md` |
| `hypothesis` | global synchronic | `analyses/hypotheses.md` |
| `kappa` | two analysis dirs | κ report |
| `all` | everything | complete pipeline |

## Data

Real OSF data from Sheldrake & Dienes (2025) is bundled in `examples/`. Phase 1 (p1–p7) serves as few-shot examples; Phase 2 (p8–p13) is the held-out test set.

## Scope note: simplified approach

This plugin implements the **simplified analysis approach** from Sheldrake & Dienes (2025) as described in `manual_kev.md`. Specifically:

- IDU (diachronic), diachronic structure (hinges between adjacent IDUs), ISU (synchronic), and cross-participant aggregation are all implemented.
- **Diachronic phases (grouping IDUs into higher-level phases) are NOT implemented.** The simplified approach from `manual_kev.md` stops at the IDU + hinge level.

## Requirements

- Claude Code CLI
- Python 3.8+ (for kappa computation: `pip install scikit-learn`)
```
<!-- END_TASK_3 -->

<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->

<!-- START_TASK_4 -->
### Task 4: XLSX-to-markdown conversion script

**Files:**
- Create: `microphenomenograph/1.0.0/scripts/convert_osf_analyses.py`

**Purpose:** Convert OSF XLSX analysis files into markdown tables suitable as few-shot examples. Must handle the encoding quirks (special quote characters) in IDU names.

**XLSX structure (verified):**
- Sheet `Diachronic Analysis - Participa`: columns `Speaker, #, Utterance, Moment, IDU, Criteria`
  - Row 1: header (`Participant N, Suggestion N (Scored N/5)`)
  - Row 2: column names
  - Rows 3+: data; IDU name only in first row of group, others None
- Sheet `Synchronic Analysis`: columns `IDU, #, Utterance, Criteria, ISU, ISU 2nd Level of Abstraction`
  - Row 1: `Table 1` (skip)
  - Row 2: column names
  - Rows 3+: data; blank rows between IDU groups

**Implementation:**

Create `microphenomenograph/1.0.0/scripts/convert_osf_analyses.py`:

```python
#!/usr/bin/env python3
"""
Convert OSF XLSX analysis files to markdown format for use as few-shot examples.

Usage:
    python convert_osf_analyses.py <input_dir> <output_dir>

Example:
    python convert_osf_analyses.py osf-archive/Phase\ 1/analyses/ \
        microphenomenograph/1.0.0/examples/analyses/phase1/

The OSF XLSX files contain three sheets: 'Diachronic Analysis', 'Diachronic Structure',
and 'Synchronic Analysis'. All three are parsed. The 'Diachronic Structure' sheet contains
IDUs in experiential order with a 'Hinge' row annotating the transition criterion between
each adjacent IDU pair — this is included in the output markdown as a ## Diachronic Structure
table, enabling benchmarking against OSF reference data.
"""
import sys
import re
from pathlib import Path
import openpyxl


def clean(text):
    """Normalise smart quotes and strip whitespace."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("�", "?")
        .strip()
    )


def parse_diachronic(ws):
    """
    Parse 'Diachronic Analysis - Participa' sheet.

    Returns list of dicts:
      { idu_name, idu_number, utterance_numbers, criteria }
    where idu_number is assigned sequentially.
    """
    rows = list(ws.iter_rows(values_only=True))
    # Row 0: header text; Row 1: column names; Rows 2+: data
    idus = []
    current_idu = None
    idu_counter = 0

    for row in rows[2:]:
        speaker, num, utterance, moment, idu_name, criteria = row[:6]
        idu_name = clean(idu_name)
        if idu_name:
            if current_idu:
                idus.append(current_idu)
            idu_counter += 1
            current_idu = {
                "idu_number": idu_counter,
                "idu_name": idu_name,
                "moment": moment,
                "utterance_numbers": [str(num)] if num is not None else [],
                "criteria": clean(criteria),
            }
        elif current_idu and num is not None:
            current_idu["utterance_numbers"].append(str(num))

    if current_idu:
        idus.append(current_idu)

    return idus


def parse_synchronic(ws):
    """
    Parse 'Synchronic Analysis' sheet.

    Returns list of dicts:
      { idu_name, utterance_numbers, criteria, isus: [{isu_name, isu_2nd_level}] }
    """
    rows = list(ws.iter_rows(values_only=True))
    # Row 0: "Table 1"; Row 1: column names; Rows 2+: data
    groups = []
    current_group = None

    for row in rows[2:]:
        idu_name, num, utterance, criteria, isu, isu_2nd = row[:6]
        idu_name = clean(idu_name)
        isu = clean(isu)
        isu_2nd = clean(isu_2nd)
        criteria_clean = clean(criteria)

        if idu_name:
            if current_group:
                groups.append(current_group)
            current_group = {
                "idu_name": idu_name,
                "utterance_numbers": [str(num)] if num is not None else [],
                "isus": [],
            }
            if isu:
                current_group["isus"].append({
                    "isu_name": isu,
                    "isu_2nd_level": isu_2nd,
                    "criteria": criteria_clean,
                })
        elif current_group:
            if num is not None:
                current_group["utterance_numbers"].append(str(num))
            if isu:
                current_group["isus"].append({
                    "isu_name": isu,
                    "isu_2nd_level": isu_2nd,
                    "criteria": criteria_clean,
                })

    if current_group:
        groups.append(current_group)

    return groups


def parse_diachronic_structure(ws):
    """
    Parse 'Diachronic Structure' sheet.

    Sheet layout (wide format):
      Row 1 (index 0): "Table 1"
      Row 2 (index 1): IDU names in alternating columns (cols 1, 3, 5, ...)
      Row 3 (index 2): Hinges in alternating columns (cols 2, 4, 6, ...)

    Returns list of dicts: { idu_name, hinge_to_next }
    where hinge_to_next is None for the last IDU.
    """
    rows = list(ws.iter_rows(values_only=True))
    if len(rows) < 3:
        return []
    idu_row = rows[1]   # IDU names
    hinge_row = rows[2]  # Hinge criteria

    # IDU names are at columns 1, 3, 5, ... (0-indexed); hinges at 2, 4, 6, ...
    idus = []
    col = 1
    while col < len(idu_row):
        name = clean(idu_row[col]) if col < len(idu_row) else ""
        if not name:
            break
        hinge = clean(hinge_row[col + 1]) if col + 1 < len(hinge_row) else ""
        idus.append({
            "idu_name": name,
            "hinge_to_next": hinge if hinge else None,
        })
        col += 2

    # Last IDU has no hinge
    if idus:
        idus[-1]["hinge_to_next"] = None

    return idus


def to_diachronic_md(header, idus, structure=None):
    lines = [f"# {header}", "", "## Diachronic Analysis", ""]
    lines.append("| IDU # | IDU Name | Utterance Numbers | Criteria |")
    lines.append("|---|---|---|---|")
    for idu in idus:
        utts = ", ".join(idu["utterance_numbers"])
        lines.append(
            f"| {idu['idu_number']} | {idu['idu_name']} "
            f"| {utts} | {idu['criteria']} |"
        )
    if structure and len(structure) >= 2:
        lines += ["", "## Diachronic Structure", ""]
        lines.append("| IDU | Hinge | IDU |")
        lines.append("|---|---|---|")
        for i in range(len(structure) - 1):
            left = structure[i]["idu_name"]
            hinge = structure[i]["hinge_to_next"] or ""
            right = structure[i + 1]["idu_name"]
            lines.append(f"| {left} | {hinge} | {right} |")
    return "\n".join(lines) + "\n"


def to_synchronic_md(header, groups):
    lines = [f"# {header}", "", "## Synchronic Analysis", ""]
    lines.append("| IDU Name | ISU Name | ISU 2nd Level | Utterance Numbers | Criteria |")
    lines.append("|---|---|---|---|---|")
    for group in groups:
        utts = ", ".join(group["utterance_numbers"])
        if group["isus"]:
            for i, isu in enumerate(group["isus"]):
                idu_cell = group["idu_name"] if i == 0 else ""
                utts_cell = utts if i == 0 else ""
                lines.append(
                    f"| {idu_cell} | {isu['isu_name']} "
                    f"| {isu['isu_2nd_level']} | {utts_cell} | {isu['criteria']} |"
                )
        else:
            lines.append(f"| {group['idu_name']} | | | {utts} | |")
    return "\n".join(lines) + "\n"


def convert_file(xlsx_path, out_dir):
    stem = xlsx_path.stem  # e.g. "p1s1"
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)

    # Diachronic sheet
    dia_sheet_name = next(
        (s for s in wb.sheetnames if "diachronic analysis" in s.lower()), None
    )
    structure = []
    struct_sheet_name = next(
        (s for s in wb.sheetnames if "diachronic structure" in s.lower()), None
    )
    if struct_sheet_name:
        structure = parse_diachronic_structure(wb[struct_sheet_name])
    if dia_sheet_name:
        ws = wb[dia_sheet_name]
        header = clean(list(ws.iter_rows(values_only=True))[0][0])
        idus = parse_diachronic(ws)
        md = to_diachronic_md(header, idus, structure)
        (out_dir / f"{stem}-diachronic.md").write_text(md, encoding="utf-8")

    # Synchronic sheet
    syn_sheet_name = next(
        (s for s in wb.sheetnames if "synchronic analysis" in s.lower()), None
    )
    if syn_sheet_name:
        ws = wb[syn_sheet_name]
        header_row = list(ws.iter_rows(values_only=True))[0][0]
        # Use diachronic header for consistency (same participant)
        header = clean(header_row) if header_row and header_row != "Table 1" else ""
        if not header and dia_sheet_name:
            ws_dia = wb[dia_sheet_name]
            header = clean(list(ws_dia.iter_rows(values_only=True))[0][0])
        groups = parse_synchronic(wb[syn_sheet_name])
        md = to_synchronic_md(header, groups)
        (out_dir / f"{stem}-synchronic.md").write_text(md, encoding="utf-8")


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    xlsx_files = sorted(in_dir.glob("*.xlsx"))
    if not xlsx_files:
        print(f"No XLSX files found in {in_dir}", file=sys.stderr)
        sys.exit(1)

    for xlsx_path in xlsx_files:
        print(f"Converting {xlsx_path.name}...")
        convert_file(xlsx_path, out_dir)

    print(f"Done. {len(xlsx_files)} files converted to {out_dir}")


if __name__ == "__main__":
    main()
```

**Step 2: Verify script parses p1s1.xlsx without error**

```bash
cd C:\microphenomenograph
python microphenomenograph/1.0.0/scripts/convert_osf_analyses.py \
    "osf-archive/Phase 1/analyses/" C:/Temp/mpi-test-convert/
ls C:/Temp/mpi-test-convert/
```

Expected: Files like `p1s1-diachronic.md`, `p1s1-synchronic.md` etc. (21 pairs for Phase 1).

**Step 3: Inspect one output file**

```bash
head -20 C:/Temp/mpi-test-convert/p1s1-diachronic.md
```

Expected: Markdown table with IDU #, IDU Name, Utterance Numbers, Criteria columns. No `?` characters for IDU names that had smart quotes in source.
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Populate examples/ from OSF archive

**Files:**
- Create: `microphenomenograph/1.0.0/examples/transcripts/` (populated from osf-archive)
- Create: `microphenomenograph/1.0.0/examples/analyses/phase1/` (converted from XLSX)
- Create: `microphenomenograph/1.0.0/examples/analyses/phase2/` (converted from XLSX)

**Step 1: Create directories**

```bash
mkdir -p microphenomenograph/1.0.0/examples/transcripts
mkdir -p microphenomenograph/1.0.0/examples/analyses/phase1
mkdir -p microphenomenograph/1.0.0/examples/analyses/phase2
```

**Step 2: Copy transcripts**

On Windows (PowerShell):
```powershell
Copy-Item "osf-archive\Phase 1\transcripts\*.txt" "microphenomenograph\1.0.0\examples\transcripts\"
Copy-Item "osf-archive\Phase 2\transcripts\*.txt" "microphenomenograph\1.0.0\examples\transcripts\"
```

On Linux/Mac:
```bash
cp osf-archive/Phase\ 1/transcripts/*.txt microphenomenograph/1.0.0/examples/transcripts/
cp osf-archive/Phase\ 2/transcripts/*.txt microphenomenograph/1.0.0/examples/transcripts/
```

Expected: 39 `.txt` files (21 Phase 1 + 18 Phase 2) in `examples/transcripts/`.

**Step 3: Convert Phase 1 analyses to markdown**

```bash
python microphenomenograph/1.0.0/scripts/convert_osf_analyses.py \
    "osf-archive/Phase 1/analyses/" \
    microphenomenograph/1.0.0/examples/analyses/phase1/
```

Expected: 42 markdown files (21 pairs: pNsN-diachronic.md + pNsN-synchronic.md for p1s1–p7s3).

**Step 4: Convert Phase 2 analyses to markdown**

```bash
python microphenomenograph/1.0.0/scripts/convert_osf_analyses.py \
    "osf-archive/Phase 2/analyses/" \
    microphenomenograph/1.0.0/examples/analyses/phase2/
```

Expected: 36 markdown files (18 pairs: pNsN-diachronic.md + pNsN-synchronic.md for p8s1–p13s3).

**Step 5: Spot-check output quality**

```bash
cat microphenomenograph/1.0.0/examples/analyses/phase1/p1s1-diachronic.md
```

Expected output (first few rows):
```
# Participant 1, Suggestion 1 (Scored 4/5)

## Diachronic Analysis

| IDU # | IDU Name | Utterance Numbers | Criteria |
|---|---|---|---|
| 1 | Initial thoughts | 2, 3, 10, 16, 24 | The utterances talk about initial thoughts |
...
```

No `?` placeholder characters. IDU names are readable strings.
<!-- END_TASK_5 -->

<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->

<!-- START_TASK_6 -->
### Task 6: Copy inter-rater reliability data

**Files:**
- Create: `microphenomenograph/1.0.0/examples/inter-rater/` (copy from osf-archive)

The kappa validation in Phase 7 needs the inter-rater CSV files accessible inside the plugin.

**Step 1: Copy CSV files**

```bash
mkdir -p microphenomenograph/1.0.0/examples/inter-rater
cp "osf-archive/Inter-rater Reliability/"*.csv microphenomenograph/1.0.0/examples/inter-rater/
```

On Windows PowerShell:
```powershell
New-Item -ItemType Directory -Force "microphenomenograph\1.0.0\examples\inter-rater"
Copy-Item "osf-archive\Inter-rater Reliability\*.csv" "microphenomenograph\1.0.0\examples\inter-rater\"
```

Expected: 6 CSV files copied:
- `kev-diachronic-analysis.csv`
- `kev-diachronic-structure.csv`
- `kev-synchronic-analysis.csv`
- `yesesvi-diachronic-analysis.csv`
- `yesesvi-diachronic-structure.csv`
- `yesesvi-synchronic-analysis.csv`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Verify plugin.json registers correctly and commit

**Step 1: Verify directory structure**

```bash
find microphenomenograph/ -type f | sort
```

Expected layout:
```
microphenomenograph/1.0.0/.claude-plugin/plugin.json
microphenomenograph/1.0.0/CLAUDE.md
microphenomenograph/1.0.0/agents/mpi-analyst.md
microphenomenograph/1.0.0/agents/mpi-cross-analyst.md
microphenomenograph/1.0.0/commands/mpi.md
microphenomenograph/1.0.0/examples/analyses/phase1/p1s1-diachronic.md
  ... (42 phase1 analysis files)
microphenomenograph/1.0.0/examples/analyses/phase2/p8s1-diachronic.md
  ... (36 phase2 analysis files)
microphenomenograph/1.0.0/examples/inter-rater/kev-diachronic-analysis.csv
  ... (6 CSV files)
microphenomenograph/1.0.0/examples/transcripts/p1s1.txt
  ... (39 transcript files)
microphenomenograph/1.0.0/scripts/convert_osf_analyses.py
microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md
  ... (10 SKILL.md stubs)
```

**Step 2: Verify bookowhy_rev.md exists at repo root**

```bash
python -c "
import pathlib
p = pathlib.Path('bookowhy_rev.md')
assert p.exists(), 'ERROR: bookowhy_rev.md not found at repo root. Phase 6 hypothesis generation depends on it.'
print(f'bookowhy_rev.md found ({p.stat().st_size} bytes)')
"
```

This file is already present in the repo (confirmed in codebase investigation). If missing, check the OSF archive — it should be restored before proceeding.

**Step 4: Validate plugin.json is valid JSON**

```bash
python -c "import json; json.load(open('microphenomenograph/1.0.0/.claude-plugin/plugin.json'))"
```

Expected: Exits 0 (no error).

**Step 5: Verify transcript header format is intact**

```bash
head -1 microphenomenograph/1.0.0/examples/transcripts/p1s1.txt
```

Expected: `Participant 1, Suggestion 1 (Scored 4/5)`

**Step 6: Commit**

```bash
git add microphenomenograph/ README.md .gitignore
git commit -m "feat: scaffold microphenomenograph plugin with ed3d structure and OSF examples"
```

Expected: Commit succeeds. `.mpi/` not tracked.

**Verifies:** microphenomenograph.AC1.1 (plugin directory installable), microphenomenograph.AC1.2 (stubs for all sub-skills present)
<!-- END_TASK_7 -->

<!-- END_SUBCOMPONENT_C -->

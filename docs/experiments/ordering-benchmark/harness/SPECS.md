# Harness Script Specs (phase 0 deliverables)

_Each section: contract, I/O, acceptance test. The phase-0 builder agent implements these in `docs/experiments/ordering-benchmark/harness/`, runs the acceptance tests, and the workflow proceeds only when ALL are green. Python 3.13, stdlib + already-installed packages only (openai 2.31.0 present; google-genai per SDK verification step). All scripts deterministic; all randomness via explicit `--seed`._

## 1. `gold_recovery.py`

Recover OSF gold from git history into `gold/` (gitignored).

- `python gold_recovery.py --dest gold/` → extracts from `git show d99e9f5:<path>`:
  - `osf-archive/Inter-rater Reliability/` (kev/yesesvi diachronic+synchronic CSVs, kappa.Rmd, kappa.html)
  - `osf-archive/Phase 1/analyses/*.xlsx` (21 per-transcript files; skip aggregation files)
  - Raw Phase-1 transcripts are already in the working tree — verify presence, do not copy.
- **MUST NOT** extract anything matching `p8*..p13*` or `Phase 2` (test-set guard lives here too).
- Output: `gold/manifest.json` — per-file path, sha256, source git path.
- **Accept**: manifest lists ≥ 21 XLSX + 4 IRR CSVs; zero Phase-2 paths; re-run is idempotent (same hashes).

## 2. `parse_gold.py`

XLSX/CSV → normalized JSON gold.

- Input: one XLSX (3 sheets: `Diachronic Analysis - Participa` [sic], `Diachronic Structure`, `Synchronic Analysis`) or one IRR CSV pair.
- Output per transcript: `gold/parsed/<stem>.gold.json`:
  ```json
  { "transcript": "p3s1", "rater": "kev",
    "idus": [ { "name": str, "moment": int, "gold_utts": ["15.1", "16", ...], "criteria": str } ],
    "experienced_order": ["IDU name", ...],   // from Diachronic Structure sheet sequence
    "experimenter_utts": ["10", "21", ...] }
  ```
- XLSX row conventions per `scripts/convert_osf_analyses.py` (row 0 header text, row 1 column names, IDU name non-empty on first utterance of each IDU; Structure sheet: IDU names in odd cols, hinges in even).
- **Accept**: p3s1 kev parse yields 7 IDUs with moments 1–7 and the exact utterance sets recorded in Stage A grounding (e.g., IDU 'Imagining a force' = {9,11,19,20,21,22.1}); yesesvi parse yields 6 IDUs with the 6→7 moment recode applied.

## 3. `crosswalk.py` (F3 — the load-bearing script)

Map plugin physical-line utterance numbers ↔ gold sub-utterance numbers.

- `python crosswalk.py --transcript <raw.txt> --gold gold/parsed/<stem>.gold.json --out gold/crosswalk/<stem>.json`
- Method: number the raw transcript's physical lines exactly as `transcript_prep` does; match gold utterance text fragments to lines (exact-substring first, then normalized [whitespace/case/punct] matching); handle **1-to-many** (one physical line → several gold sub-utterances, e.g. line→15.1+15.2 at different moments) by splitting on the gold fragments' text spans within the line.
- Output: `{ "line_to_gold": {"17": ["15.1","15.2"]}, "gold_to_line": {...}, "coverage": 0.97, "unmatched_gold": [...], "unmatched_lines": [...] }`
- Coverage = fraction of gold utterances (excluding experimenter rows) matched to a line span. **Per-transcript rule: coverage < 0.80 ⇒ transcript excluded from all verdict-bearing metrics (recorded in report).**
- **Accept**: p3s1 coverage ≥ 0.95 for both raters AND `reproduce_kappa.py` (below) passes through this crosswalk.

## 4. `reproduce_kappa.py` (harness self-validation gate)

Recompute the published human–human numbers from raw inputs through the full harness path.

- Uses `parse_gold.py` output for kev+yesesvi, the crosswalk, the kappa.Rmd hand-rolled formula: per-category `agree = |kev_set ∩ yes_set|`, `expfreq = (|kev_set|·|yes_set|)/N`, `κ = (Σagree − Σexpfreq)/(N − Σexpfreq)` over the aligned category map (kev↔yesesvi IDU name pairs as in kappa.Rmd), experimenter utterances filtered.
- **Accept (hard barrier for the whole workflow)**: diachronic κ = 0.82 ± 0.01 and synchronic κ = 0.60 ± 0.01, matching kappa.html. Also computes and records the ordering band: kev-vs-yesesvi moment τ (expected 1.0) into `prereg.json`.

## 5. `metrics.py`

Score one model artifact against gold.

- Input: model artifact JSON (the diachronic close payload shape: IDUs with `idu_name`, `moment`, `utterance_numbers`), gold parse, crosswalk.
- Alignment: model IDUs ↔ gold IDUs by maximum-Jaccard on crosswalked utterance sets (Hungarian assignment; ties broken by name token overlap). Alignment map recorded in output for audit.
- Output JSON per cell: `assignment_kappa` (hand-rolled formula, same as §4), `assignment_alpha` (call existing `irr.py` `compute_coincidence`/alpha), `kendall_tau` (moment order over aligned IDUs; stdlib implementation — scipy availability not assumed), `inversion_rate` (adjacent aligned pairs out of order), `idu_count_delta`, `name_overlap`, `schema_valid`, `coverage_used`.
- **`--validate-only <artifact>`**: schema-validate a model artifact (shape per the diachronic `idu_naming_ordering` payload) without gold/scoring; exit 0/1. Used by cell idempotency checks and verifier fallbacks.
- **Accept**: scoring kev-as-model vs kev-gold gives κ=1.0, τ=1.0, inversions=0; scoring yesesvi-as-model vs kev-gold reproduces §4's κ within 0.01.

## 6. `run_cell.py` (external arms only — Gemini now, OpenRouter hook later)

- `python run_cell.py --config cell.json --transcript <raw.txt> --out artifacts/<cell_key>.json`
- `cell.json`: `{model_id, provider: "google"|"openrouter", scaffold: "S1", seed, rep, thinking, max_tokens}`.
- Implements the S1 ported scaffold as 3 sequential calls (criteria_grouping → criteria_revision → idu_naming_ordering), JSON-schema response format where supported, client-side validation + 2 retries with error feedback.
- Encodes landmines: Gemini 3.x `temperature=1.0`, `thinkingLevel` string (NOT `thinkingBudget`); generous `max_tokens`; logs token usage + cost to `artifacts/<cell_key>.cost.json`.
- Refuses any transcript matching `p8*..p13*` (guard, again).
- **`--judge` mode**: `python run_cell.py --judge --config judge.json --out <out>` — single blind adjudication call: config carries `{model_id, disagreement: {context_excerpt, label_A, label_B}}`; returns `{decision: "A"|"B", rationale}`. Order-balancing and label anonymization are the CALLER's job (the workflow's scorer emits pre-balanced disagreements).
- **Accept**: dry-run mode (`--mock`) produces a schema-valid artifact without network (both analysis and judge modes); a real single call against the verified SDK succeeds when `GEMINI_API_KEY` is set.

## 7. `precompute_shuffles.py` (S6 hook — not used by ceiling defaults)

- Seeded permutations of IDU-group presentation order per (transcript, rep): `gold/shuffles/<stem>.<rep>.json`. Deterministic from `--seed`.
- **Accept**: same seed ⇒ identical output.

## 8. `report.py`

- Aggregates `artifacts/*.metrics.json` → `results/report.md` + `results/summary.json`: per-arm tables (calibration verdicts; dev distributions clustered by participant), cost-quality table, verbatim caveats (n=1 band; degenerate ordering band; Phase-1 contamination flags on A1), and the pre-registered criteria echoed from `prereg.json`.
- **Accept**: runs on synthetic fixture metrics and renders all sections.

# Ordering Benchmark — Design of Record (ceiling-first)

_2026-06-06. Derived from the Stage-A meta-workflow (grounding + 3 architecture lenses + adversarial critiques + opus adjudication; full record at `docs/reviews/_orderbench_stageA.json`) with principal's amendments. Status: draft awaiting first run._

## Question

Can any current LLM method match or beat the OSF human analyst at **diachronic analysis** — grouping utterances into IDUs and ordering them by **experienced-moment order** (not interview/narrative order)? The human gold is treated as a **fallible rater**, not truth.

## Key measured facts (Stage A grounding — these shaped the design)

1. **Gold location**: all OSF analyses (21 Phase-1 XLSX, 18 Phase-2 XLSX, IRR CSVs, kappa.Rmd) were removed from the working tree in commit `1bf235f`; fully recoverable via `git show d99e9f5:<path>`. Working tree retains only the 21 Phase-1 raw transcripts (`osf-archive/Phase 1/transcripts/`).
2. **Human–human data exists for exactly one transcript**: p3s1 (scored 2/5), raters kev + yesesvi. Published Cohen's κ (hand-rolled per-category formula, see kappa.Rmd): **diachronic 0.82, synchronic 0.60**.
3. **The human–human ORDERING band is degenerate**: kev-vs-yesesvi moment-order Kendall τ = 1.0 (utterance-level n=16 shared; IDU-level n=6; robust to the moment-6→7 recode). The raters disagree on utterance→IDU **boundaries** (κ=0.82), never on **sequence**. ⇒ No τ-band match criterion is possible; assignment agreement is the operative MATCH dimension; τ is descriptive.
4. **Numbering spaces are disjoint**: kev's gold uses sub-utterance numbers (15.1/15.2; 22.1/22.2/22.3) that map 1-to-many onto transcript physical lines; the plugin's `transcript_prep` numbers physical lines. Without a crosswalk, every alignment metric is noise.
5. Experimenter-utterance filter `{10,21,23,29,12,14,16,19,39,27,31,33,35,37,25}` (in `irr.py`) is **p3s1-specific**, not general.

## Arms (ceiling set — defaults; later stages parameterized via args)

| Arm | Runtime | Scaffold |
|---|---|---|
| A1 current skill implementation | workflow `agent()` running the real `/mpi` diachronic pipeline in a temp run dir (Opus-driven, incumbent) | native (S1 + remediation rules) |
| A2 Claude Opus (API tier) | workflow `agent()` with ported S1 prompts | S1 ported |
| A3 Claude Sonnet | workflow `agent()` | S1 ported |
| A4 Gemini 3 Pro | `run_cell.py` via Google AI Studio key | S1 ported |
| A5 Gemini 3.5 Flash | `run_cell.py` | S1 ported |

k = **3 reps** per cell. `cell_key = sha256(model_id + scaffold_id + transcript_stem + rep_index + seed)` (F1). Claude arms run through `agent()` — never `run_cell.py` (F2; no ANTHROPIC_API_KEY exists on this machine; cost from agent token-usage fields). Gemini arms: **phase 0 web-verifies the current `google-genai` SDK + model ids + thinkingLevel shape before any cell runs** (Google SDK churn); temperature 1.0 on 3.x; generous max_tokens.

**Scaffold parity (what each contrast isolates):** phase 0 produces `harness/ported_s1.md` — the S1 substep instructions extracted verbatim from the skill/agent prompts, minus plugin mechanics (closes, manifest, persistence). A2–A5 all receive exactly this text. Therefore **A1 vs A2 isolates the pipeline machinery** (multi-substep dispatch, close protocol, enforcement gates) at fixed model+instructions, and **A2 vs A4 isolates the model** at fixed scaffold. Without this parity the A1–A2 contrast would conflate model with scaffold richness.

**Deferred stages** (hooks, not defaults): cheap-model × scaffold matrix (S2 timeline-first / S4 pair-verify / S6 shuffled-input; Flash-Lite, DeepSeek, Qwen via OpenRouter key when provisioned); optional second human rater; Phase-2 confirmatory run.

## Data split (hard rule)

- **Calibration**: p3s1 — the only transcript where MATCH is a real test.
- **Dev**: 5 stratified Phase-1 transcripts (≥1 per IV category; chosen by seed in args) vs kev's single-rater gold — **descriptive only**, contamination-caveated (Phase-1 analyses were plugin-development fixtures; flags A1 results especially).
- **Test**: **Phase 2 (p8–p13) is RESERVED.** The workflow contains an explicit guard: any attempt to read or run a p8–p13 transcript aborts. The confirmatory run is a separate, future, one-shot decision.

## Leakage guards

Gold content (XLSX/CSV-derived) never enters any analysis prompt or `run_cell.py` input. Gold lives in `gold/` inside the experiment dir; analysis cells receive only raw transcripts. Scoring happens in deterministic Python after artifacts exist. The zero-shot convention holds for all arms.

## Metrics (computed by `harness/metrics.py`, choices fixed by the Phase-0 band measurement)

Primary (verdict-bearing, p3s1 only):
- **Utterance→IDU assignment agreement** vs kev: Cohen's κ via the kappa.Rmd hand-rolled formula (reproduced exactly) + Krippendorff α via existing `irr.py`. Human band: κ = 0.82 (yesesvi).

Descriptive (all transcripts):
- Kendall τ between model moment-order and kev's, after IDU alignment (flagged "human band degenerate at τ=1.0; no discriminating threshold")
- Adjacent-pair inversion rate (the narrative-order failure detector)
- IDU count Δ vs gold; IDU-name similarity (LLM-free token overlap; LLM-assisted alignment only for the alignment map, never scoring)
- Schema-validity rate; cost per transcript (tokens × current prices; agent-usage fields for Claude arms)

## Verdicts (pre-registered — written to `prereg.json` by phase 0 before any cell runs)

**ORDERING-MATCH is the primary verdict.** The τ=1.0 human–human result is not a missing band — it is the **human ceiling**: both raters ordered the moments identically, so the one-sided test is "is the model statistically distinguishable from that ceiling?" A model at τ=0.6 demonstrably fails ordering; this is the research question, and it must not be buried under assignment agreement (κ and τ are separable — an arm can draw correct boundaries and still number them in narrative order).

- **ORDERING-MATCH (primary, p3s1)**: over aligned IDUs (alignment per `metrics.py`), the arm matches human ordering competence iff **τ-vs-kev = 1.0 (zero adjacent inversions) on the majority of its k reps**. Near-miss band τ ≥ 0.90 (≤ 1 adjacent swap at n≈7 IDUs) reported as ORDERING-NEAR. Small-n note: τ is discrete here; exact rep-level values + inversion counts are always reported alongside the verdict.
- **ASSIGNMENT-MATCH (secondary, p3s1, one-sided)**: assignment κ vs kev ≥ 0.82 within bootstrap sampling error (95% CI lower bound vs the band; the band is n=1 rater — caveat carried verbatim). One-sided because gold is a rater.
- **BEAT (p3s1 disagreements — NOT gated on either MATCH)**: every arm's boundary *and ordering* disagreements with kev go to a **single cross-family blind judge** (Gemini judges Claude arms; Claude judges Gemini arms; order-balanced, arm-anonymous). Evidence-of-beat iff the judge sides with the model on a majority of its disagreements. Not gating on MATCH is deliberate: an arm with great ordering but mediocre boundaries must still get its ordering adjudicated — and judge-sides-with-model cases are exactly the "human got it wrong" detector. If no cross-family judge is available (no Gemini key), BEAT is skipped with a logged note — never crashed into.
- **Dev set**: distance-to-gold distributions per arm (τ, inversion rate, κ, count Δ), clustered by participant; no verdicts; BH-FDR if any inferential cross-arm comparison is reported.

## Workflow architecture (implemented in `ordering-benchmark.workflow.js`)

- **Phase 0 — Harness (hard barrier)**: one builder agent writes the Python scripts per `harness/SPECS.md`; gate = all acceptance tests green, **including reproducing the published κ=0.82/0.60 from the recovered IRR CSVs through the crosswalk** (F3: if the harness can't reproduce the published number from raw inputs, nothing downstream is trustworthy). Also: SDK web-verification; `prereg.json`; seeded shuffle precompute (S6 hook); Phase-2 guard self-test.
- **Phase 1 — Calibration cells**: arms × p3s1 × 3 reps via `pipeline()` (artifact → immediate validity check). Idempotent by `cell_key`; verifier-fallback for any cell agent that works-but-doesn't-report.
- **Phase 2 — Dev cells**: arms × 5 transcripts × 3 reps, same shape.
- **Phase 3 — Scoring + verdicts**: deterministic Python (no LLM except the alignment-map proposal step, which reuses `irr.py`'s aligner); judge cells only for BEAT-eligible disagreements.
- **Phase 4 — Report**: one agent renders `results/report.md` from the JSONL; includes cost-quality table, the n=1-band caveat, and contamination flags.

Small structured returns throughout (paths + status); details on disk; resume-safe via cell_key idempotency.

## Cost estimate (ceiling defaults)

~5 arms × 6 transcripts × 3 reps = 90 analysis cells (+ judge cells, bounded by disagreement count on one transcript). Claude-arm cells dominate: rough order 2–4M tokens total. Gemini cells billed to AI Studio key. Phase 0 ≈ 1 builder agent + tests.

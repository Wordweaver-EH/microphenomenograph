export const meta = {
  name: "ordering-benchmark",
  description: "Ceiling-first diachronic-ordering benchmark: arms x transcripts x reps vs fallible human gold (design: docs/experiments/ordering-benchmark/design.md)",
  phases: [
    { title: "Harness", detail: "build + acceptance-test all Python tooling; HARD BARRIER incl. reproducing published kappa=0.82", model: "sonnet" },
    { title: "Calibration", detail: "arms x p3s1 x reps (MATCH-verdict transcript)", model: "sonnet" },
    { title: "Dev", detail: "arms x 5 stratified Phase-1 transcripts x reps (descriptive)", model: "sonnet" },
    { title: "Score", detail: "deterministic metrics + verdicts + cross-family judge on disagreements", model: "sonnet" },
    { title: "Report", detail: "render results/report.md", model: "sonnet" },
  ],
}

const ROOT = "C:/microphenomenograph"
const EXP = ROOT + "/docs/experiments/ordering-benchmark"
const input = (typeof args === "string") ? JSON.parse(args) : (args || {})

// ---- parameters (defaults = ceiling run) ----
const ARMS = input.arms || [
  { id: "A1-skill", runtime: "skill", model: "opus", family: "claude" },
  { id: "A2-opus", runtime: "agent", model: "opus", family: "claude" },
  { id: "A3-sonnet", runtime: "agent", model: "sonnet", family: "claude" },
  { id: "A4-gemini3pro", runtime: "external", model: "VERIFIED_IN_PHASE0", family: "google" },
  { id: "A5-gemini35flash", runtime: "external", model: "VERIFIED_IN_PHASE0", family: "google" },
]
const CAL = input.calibration || ["p3s1"]
const DEV = input.dev_transcripts || ["p3s3", "p7s2", "p5s2", "p1s1", "p6s3"] // scores 0,1,3,4,5 — one per IV level
const REPS = input.reps || 3
const SEED = input.seed || 1337
const STAMP = input.timestamp || "unstamped" // pass ISO date via args

// ---- Phase-2 test-set guard (design.md: RESERVED) ----
function assertNotTestSet(stem) {
  if (/^p(8|9|1[0-3])s/i.test(stem)) throw new Error("PHASE-2 TEST SET IS RESERVED — refused: " + stem)
}
CAL.concat(DEV).forEach(assertNotTestSet)

const HYGIENE = `
RULES: Repo ${ROOT}. Experiment dir ${EXP}. Never read anything under gold/ except via the scoring scripts (LEAKAGE GUARD: analysis prompts must never contain gold content). Never touch transcripts p8*-p13* (reserved test set). Keep your structured return SMALL (paths + status + numbers only); durable detail goes to files. Your VERY LAST action must be the StructuredOutput call.`

const CELL_SCHEMA = {
  type: "object", required: ["cell_key", "artifact", "ok"],
  properties: { cell_key: { type: "string" }, artifact: { type: "string" }, ok: { type: "boolean" }, cost_note: { type: "string" }, blockers: { type: "string" } }
}

// =============== Phase 0: Harness (hard barrier) ===============
phase("Harness")
log("Building + validating harness")
const harness = await agent(`You are the harness builder. Implement EVERY script specified in ${EXP}/harness/SPECS.md into ${EXP}/harness/, then run all acceptance tests in order (gold_recovery -> parse_gold -> crosswalk -> reproduce_kappa -> metrics -> run_cell --mock -> precompute_shuffles -> report fixture).
ALSO: (a) web-verify the CURRENT google-genai SDK package + Gemini 3 Pro / 3.5 Flash model ids + thinkingLevel API shape (Google churns SDKs); record findings in ${EXP}/harness/sdk_verification.md and use the verified model ids in run_cell.py; pip install the verified SDK if missing. (b) Write ${EXP}/prereg.json: the pre-registered verdict criteria EXACTLY as in design.md's Verdicts section (PRIMARY = ORDERING-MATCH: tau-vs-kev 1.0 / zero adjacent inversions on majority of reps, near-miss band tau >= 0.90; SECONDARY = ASSIGNMENT-MATCH: kappa >= 0.82 one-sided within bootstrap CI; BEAT: cross-family blind judge majority on each arm's boundary AND ordering disagreements, NOT gated on either MATCH) PLUS the measured kev-vs-yesesvi numbers your reproduce_kappa run produced. (c) Confirm GEMINI_API_KEY (or GOOGLE_API_KEY) is set in the environment — if absent, report it in blockers but still finish the build (Claude arms can run without it). (d) Write ${EXP}/harness/ported_s1.md: the S1 substep instructions extracted VERBATIM from ${ROOT}/microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md and agents/mpi-analyst.md diachronic rules, minus plugin mechanics (no closes/manifest/persistence) — the shared scaffold for arms A2-A5 (scaffold parity: A1-vs-A2 isolates pipeline machinery, A2-vs-A4 isolates model).
Commit everything: "feat(ordering-benchmark): harness". ${HYGIENE}`,
  { label: "harness-build", phase: "Harness", model: "sonnet", schema: {
    type: "object", required: ["all_green", "kappa_diachronic", "kappa_synchronic", "tau_band", "gemini_models", "blockers"],
    properties: {
      all_green: { type: "boolean" },
      kappa_diachronic: { type: "number" }, kappa_synchronic: { type: "number" }, tau_band: { type: "number" },
      gemini_models: { type: "array", items: { type: "string" }, description: "verified model ids [3 Pro, 3.5 Flash]" },
      blockers: { type: "string" }
    }
  } })

if (!harness || !harness.all_green) {
  log("HARNESS NOT GREEN — stopping before any cell spends tokens")
  return { status: "harness_failed", harness }
}
log(`Harness green: kappa_d=${harness.kappa_diachronic} kappa_s=${harness.kappa_synchronic} tau_band=${harness.tau_band}`)
const gemModels = harness.gemini_models || []
const geminiReady = gemModels.length >= 2 && !(harness.blockers || "").toLowerCase().includes("key")

// =============== cell construction ===============
function cells(transcripts, phaseName) {
  const out = []
  for (const arm of ARMS) {
    if (arm.runtime === "external" && !geminiReady) { log(`SKIP ${arm.id} (${phaseName}): gemini not ready — ${harness.blockers}`); continue }
    const model_id = arm.runtime === "external" ? (arm.id === "A4-gemini3pro" ? gemModels[0] : gemModels[1]) : arm.model
    for (const stem of transcripts) {
      assertNotTestSet(stem)
      for (let rep = 1; rep <= REPS; rep++) {
        out.push({ arm, model_id, stem, rep, phaseName, key: `${arm.id}|S1|${stem}|r${rep}|s${SEED}` })
      }
    }
  }
  return out
}

function cellPrompt(c) {
  const art = `${EXP}/artifacts/${c.key.replace(/[|]/g, "_")}.json`
  const idem = `IDEMPOTENCY: if ${art} already exists and is schema-valid (run: python ${EXP}/harness/metrics.py --validate-only ${art}), verify and return ok=true without re-running.`
  const tx = `${ROOT}/osf-archive/Phase 1/transcripts/${c.stem}.txt`
  if (c.arm.runtime === "skill") return `You are experiment cell ${c.key}. ${idem}
Run the CURRENT skill implementation's diachronic stage for real: create a temp run dir (e.g. ${EXP}/tmp-runs/${c.stem}-r${c.rep}/), use ${ROOT}/microphenomenograph/1.0.0/scripts/mpi_step.py init + transcript_prep substeps on a COPY of ${tx}, then perform the full mpi-diachronic SKILL flow (read ${ROOT}/microphenomenograph/1.0.0/skills/mpi-diachronic/SKILL.md and agents/mpi-analyst.md and follow them faithfully, including closes). Copy the final idu_naming_ordering artifact JSON to ${art}. Record rough token cost in cost_note.${HYGIENE}`
  if (c.arm.runtime === "agent") return `You are experiment cell ${c.key} — the ${c.model_id} API-tier arm with the ported S1 scaffold. ${idem}
Read EXACTLY TWO files: the scaffold ${EXP}/harness/ported_s1.md and the raw transcript ${tx} — nothing else (scaffold parity: this arm tests the bare model + the same instructions the other arms get, not the plugin machinery). Follow the scaffold's 3-substep diachronic analysis (criteria_grouping -> criteria_revision until converged -> idu_naming_ordering; EXPERIENCED-moment order, not interview order). Write the final artifact to ${art} matching the diachronic idu_naming_ordering JSON shape (idus: [{idu_number, idu_name, moment, criteria, utterance_numbers, confidence, flag_for_review, hinge_to_next, utterance_refs}]; number utterances by physical line as transcript_prep would).${HYGIENE}`
  return `You are experiment cell ${c.key} (external arm). ${idem}
Write ${EXP}/artifacts/${c.key.replace(/[|]/g, "_")}.cell.json with {"model_id":"${c.model_id}","provider":"google","scaffold":"S1","seed":${SEED},"rep":${c.rep},"thinking":"low","max_tokens":16384} then run: python ${EXP}/harness/run_cell.py --config that file --transcript "${tx}" --out ${art}. On schema failure run_cell retries internally; report ok per exit code and copy its cost log path into cost_note.${HYGIENE}`
}

async function runCells(list, phaseName) {
  return pipeline(list, async (c) => {
    let r
    try {
      r = await agent(cellPrompt(c), { label: c.key, phase: phaseName, model: c.arm.runtime === "agent" ? c.arm.model : "sonnet", schema: CELL_SCHEMA })
    } catch (e) {
      log(`${c.key}: no structured return — verifier fallback`)
      r = await agent(`A prior agent ran experiment cell ${c.key}; verify its durable output: does ${EXP}/artifacts/${c.key.replace(/[|]/g, "_")}.json exist and pass python ${EXP}/harness/metrics.py --validate-only? Report ok accordingly; do not re-run analysis.${HYGIENE}`,
        { label: "verify:" + c.key, phase: phaseName, model: "sonnet", schema: CELL_SCHEMA })
    }
    return { key: c.key, ok: r ? r.ok : false, blockers: r ? (r.blockers || "") : "no return" }
  })
}

phase("Calibration")
const calResults = await runCells(cells(CAL, "Calibration"), "Calibration")
log(`Calibration: ${calResults.filter(x => x && x.ok).length}/${calResults.length} cells ok`)

phase("Dev")
const devResults = await runCells(cells(DEV, "Dev"), "Dev")
log(`Dev: ${devResults.filter(x => x && x.ok).length}/${devResults.length} cells ok`)

// =============== Phase 3: Score + verdicts + judge ===============
phase("Score")
const scoring = await agent(`You are the scorer. For every artifact in ${EXP}/artifacts/*.json (skip *.cell.json/*.cost.json): run python ${EXP}/harness/metrics.py --artifact <a> --gold ${EXP}/gold/parsed/<stem>.gold.json --crosswalk ${EXP}/gold/crosswalk/<stem>.json --out <a>.metrics.json. Then compute verdicts per ${EXP}/prereg.json into ${EXP}/results/verdicts.json (PRIMARY ordering-match: tau=1.0/zero-inversions on majority of reps, near band tau>=0.90; SECONDARY assignment-match: kappa>=0.82 one-sided with bootstrap CI; per arm on p3s1; descriptive aggregates for dev, clustered by participant). Also emit ${EXP}/results/disagreements.json: for EVERY arm (NOT gated on match), kev-vs-model boundary AND ordering disagreements on p3s1 (utterance ids + the two anonymized, order-balanced readings labeled label_A/label_B with a hidden key) for judging. Commit: "feat(ordering-benchmark): scores + verdicts". Return ONLY: number scored, ordering-match arms, assignment-match arms, arms with disagreements.${HYGIENE}`,
  { label: "score", phase: "Score", model: "sonnet", schema: {
    type: "object", required: ["scored", "ordering_match_arms", "assignment_match_arms", "arms_with_disagreements"],
    properties: { scored: { type: "number" }, ordering_match_arms: { type: "array", items: { type: "string" } }, assignment_match_arms: { type: "array", items: { type: "string" } }, arms_with_disagreements: { type: "array", items: { type: "string" } } }
  } })

let judged = []
const judgeable = (scoring ? scoring.arms_with_disagreements : []).filter(armId => {
  const arm = ARMS.find(a => a.id === armId) || { family: "claude" }
  if (arm.family === "claude" && !geminiReady) { log(`BEAT skipped for ${armId}: no cross-family judge (no Gemini key) — logged, not crashed`); return false }
  return true
})
if (judgeable.length) {
  judged = await parallel(judgeable.map(armId => () => {
    const arm = ARMS.find(a => a.id === armId) || { family: "claude" }
    const crossFamily = arm.family === "claude"
    const judgePrompt = `You are the BLIND JUDGE for arm ${armId}'s p3s1 disagreements (you do not know which reading is the human's — they are order-balanced in ${EXP}/results/disagreements.json under "${armId}"). For each disagreement, read the raw transcript ${ROOT}/osf-archive/Phase 1/transcripts/p3s1.txt and decide which reading (label_A or label_B) better fits the temporal evidence (linkage phrases, causal prerequisites, tense). ${crossFamily ? `You MUST judge via the cross-family model: for each disagreement write a judge config and run python ${EXP}/harness/run_cell.py --judge --config <cfg> --out <out> using the verified Gemini model ${gemModels[0] || ""}; aggregate its decisions.` : "Judge directly (you are the cross-family judge for a Google arm)."} Write ${EXP}/results/judge_${armId}.json with per-disagreement decisions + a one-line rationale each. Return counts only.${HYGIENE}`
    return agent(judgePrompt, { label: "judge:" + armId, phase: "Score", model: "sonnet", schema: {
      type: "object", required: ["arm", "n_disagreements", "model_favored"],
      properties: { arm: { type: "string" }, n_disagreements: { type: "number" }, model_favored: { type: "number" } }
    } })
  }))
}

phase("Report")
const report = await agent(`Run python ${EXP}/harness/report.py --exp ${EXP} to render ${EXP}/results/report.md (verdicts incl. judge outcomes ${JSON.stringify(judged.filter(Boolean))}, cost-quality table, verbatim caveats: n=1 human band, degenerate ordering band tau=1.0, Phase-1 contamination flag on A1-skill). Commit: "feat(ordering-benchmark): report ${STAMP}". Return the report path + a 5-line headline summary.${HYGIENE}`,
  { label: "report", phase: "Report", model: "sonnet", schema: {
    type: "object", required: ["report_path", "headline"],
    properties: { report_path: { type: "string" }, headline: { type: "string" } }
  } })

return {
  status: "complete",
  harness: { kappa_d: harness.kappa_diachronic, tau_band: harness.tau_band, blockers: harness.blockers },
  cells: { calibration: calResults.filter(Boolean), dev_ok: devResults.filter(x => x && x.ok).length, dev_total: devResults.length },
  ordering_match: scoring ? scoring.ordering_match_arms : [],
  assignment_match: scoring ? scoring.assignment_match_arms : [],
  judged: judged.filter(Boolean),
  report: report ? report.report_path : "",
  headline: report ? report.headline : "",
}
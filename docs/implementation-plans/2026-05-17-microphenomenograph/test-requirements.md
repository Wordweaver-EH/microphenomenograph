# Test Requirements: Microphenomenograph

This document maps every acceptance criterion in the Microphenomenograph design plan
(`docs/design-plans/2026-05-17-microphenomenograph.md`) to a verification approach.

The plugin is a Claude Code CLI plugin. Skills (`SKILL.md`) and agents (`.md`) are
markdown documents interpreted by Claude Code at runtime — they are not executable
code and cannot be unit-tested in the traditional sense. The only traditional code
artifacts are:

- `scripts/kappa.py` (and its unit tests in `scripts/test_kappa.py`)
- `scripts/convert_osf_analyses.py`

**Note on test file locations:** Actual test files are located in the `tests/` directory at the repository root, not `scripts/tests/e2e/`. Test files follow the pattern `tests/test_*.py`.

**Automated tests added:** Several criteria that can be verified without Claude Code CLI execution have been implemented as pure Python unit tests in `tests/test_plugin_structure.py`:
- AC1.1: plugin.json validation
- AC1.2: SKILL.md discovery and frontmatter
- AC1.3: unknown subcommand message
- AC3.6 (structural): phase2 exclusion
- AC7.3: kappa warning threshold

Remaining criteria (AC3.1, AC3.3, AC3.4, AC3.5, AC8.1, AC8.2, AC8.4, AC7.2 skill-level) require Claude Code CLI execution with an LLM and are documented in the human test plan below.

Accordingly, verification falls into three buckets:

- **unit** — Python `pytest` tests of the helper scripts.
- **e2e** — invoking the plugin through Claude Code against the bundled OSF fixtures
  and asserting on the on-disk artifacts (manifest JSON, markdown tables, git log,
  review queue). These can be driven by a thin pytest harness that shells out to
  `claude` in non-interactive mode, but the work being verified is LLM behaviour.
- **human** — criteria whose pass/fail depends on subjective qualitative judgement
  (e.g. "groupings are traceable", "hypothesis is causal") or on interactive TTY
  behaviour (assisted-mode confirmation prompts, Ctrl+C interrupts, terminal
  rendering). A reviewer follows a written checklist against the e2e run output.

Reference kappa values on the bundled OSF Phase 2 fixtures (computed against
`Inter-rater Reliability/kappa.Rmd`): **diachronic κ = 0.82**, **synchronic κ =
0.60**. The `scripts/kappa.py` output must match these within ±0.01.

---

## AC1: Plugin installs and is invokable

### microphenomenograph.AC1.1
- **Test type:** unit
- **Description:** Plugin is installable with valid plugin.json.
- **Test file:** `tests/test_plugin_structure.py::TestAC1_1_PluginInstallable`
- **Verification approach:** Assert `plugin.json` exists at
  `microphenomenograph/1.0.0/.claude-plugin/plugin.json`, is valid JSON, and
  contains required fields (name, version).

### microphenomenograph.AC1.2
- **Test type:** unit
- **Description:** 10 skills are discoverable with valid SKILL.md files.
- **Test file:** `tests/test_plugin_structure.py::TestAC1_2_SkillsDiscoverable`
- **Verification approach:** Assert all 10 skill directories exist with SKILL.md
  files containing YAML frontmatter and a name field. Skills:
  `mpi-init`, `mpi-transcript-prep`, `mpi-diachronic`, `mpi-synchronic`,
  `mpi-generic-diachronic`, `mpi-generic-synchronic`, `mpi-global-synchronic`,
  `mpi-hypothesis`, `mpi-kappa`, `mpi-status`.

### microphenomenograph.AC1.3
- **Test type:** unit
- **Description:** Unknown subcommand produces usage message.
- **Test file:** `tests/test_plugin_structure.py::TestAC1_3_UnknownSubcommand`
- **Verification approach:** Assert `commands/mpi.md` contains "Unknown subcommand"
  message and lists main subcommands (`init`, `status`, `transcript-prep`,
  `diachronic`, `synchronic`).

---

## AC2: /mpi init parses transcripts and writes manifest

### microphenomenograph.AC2.1
- **Test type:** unit
- **Description:** Header parser maps `"Participant 1, Suggestion 2 (Scored 3/5)"`
  to `{participant: 1, suggestion: 2, score: 3}`.
- **Test file:** `scripts/test_kappa.py` (or a new
  `scripts/test_header_parser.py` if the parser is extracted into Python; if the
  parser lives only in the skill, downgrade to e2e against
  `scripts/tests/e2e/test_init.py`).
- **Verification approach:** Parametrised assertion on the parser function for at
  least five header variants including the canonical form, leading/trailing
  whitespace, and a `Scored 0/5` edge value.

### microphenomenograph.AC2.2
- **Test type:** e2e
- **Description:** Running `/mpi init` over the bundled OSF transcripts produces
  `.mpi/project.json` whose schema is valid and where every stage is `pending`.
- **Test file:** `scripts/tests/e2e/test_init.py`
- **Verification approach:** Copy `examples/transcripts/` into a temp dir, run
  `/mpi init`, load the resulting JSON, assert: (a) one entry per
  participant/suggestion pair found in transcript headers; (b) every stage value
  in `{pending}`; (c) `mode` field present; (d) JSON validates against the schema
  declared in `phase_02.md`.

### microphenomenograph.AC2.3
- **Test type:** e2e
- **Description:** A transcript whose header cannot be parsed produces a named
  error referencing the file, rather than silently recording a wrong score.
- **Test file:** `scripts/tests/e2e/test_init.py`
- **Verification approach:** Drop a fixture transcript with header
  `"Participant one, Suggestion two"` into the temp dir, run `/mpi init`, assert
  the run reports an error mentioning the offending filename and the string
  "header" (or similar), and that no manifest entry with a fabricated score is
  written for that file.

### microphenomenograph.AC2.4
- **Test type:** e2e
- **Description:** Re-running `init` on a directory that already has a manifest
  with some stages marked `done` preserves those `done` markers and only appends
  new participants.
- **Test file:** `scripts/tests/e2e/test_init.py`
- **Verification approach:** Hand-craft a `.mpi/project.json` with one stage set
  to `done`, add a new transcript file, re-run `init`, assert the `done` value
  survives and the new participant appears as `pending`.

---

## AC3: Diachronic analysis produces correct output

### microphenomenograph.AC3.1
- **Test type:** e2e
- **Description:** Each transcript produces an `analyses/pNsN-diachronic.md` file
  containing an IDU markdown table.
- **Test file:** `scripts/tests/e2e/test_diachronic.py`
- **Verification approach:** Run `/mpi diachronic` over a single OSF Phase 2
  transcript, glob for the expected output path, parse the markdown, assert
  presence of an `idu_number` column and at least one data row.

### microphenomenograph.AC3.2
- **Test type:** human
- **Description:** Each IDU row's utterance number references point at utterances
  whose content plausibly supports the IDU label.
- **Test file:** N/A
- **Verification approach:** Reviewer opens a generated `pNsN-diachronic.md` next
  to the source transcript and confirms, for a sample of three IDUs per
  participant, that the cited utterance numbers exist and the content matches the
  IDU name/criteria. Justification: traceability of semantic alignment is a
  qualitative judgement that LLM evals cannot reliably stand in for.

### microphenomenograph.AC3.3
- **Test type:** e2e
- **Description:** Every IDU row has a confidence column populated with an
  integer in `[1, 5]`.
- **Test file:** `scripts/tests/e2e/test_diachronic.py`
- **Verification approach:** Parse all generated `pNsN-diachronic.md` tables,
  assert the confidence column is present, non-null, and every value coerces to
  `int` in `{1,2,3,4,5}`.

### microphenomenograph.AC3.4
- **Test type:** e2e
- **Description:** IDUs with `confidence < 3` or `flag_for_review=true` appear in
  `.mpi/review-queue.md` and not (only) in the accepted output.
- **Test file:** `scripts/tests/e2e/test_diachronic.py`
- **Verification approach:** After a run, parse both files; assert every accepted
  IDU has `confidence >= 3` and `flag_for_review=false`, and that every entry in
  `.mpi/review-queue.md` violates at least one of those conditions. If the run
  produces no flagged items, inject a fixture transcript engineered to be
  ambiguous and re-assert.

### microphenomenograph.AC3.5
- **Test type:** e2e
- **Description:** A transcript yielding a single IDU produces a one-row table
  rather than an error or empty output.
- **Test file:** `scripts/tests/e2e/test_diachronic.py`
- **Verification approach:** Use a minimal fixture transcript (one utterance pair),
  run the skill, assert exactly one data row is written and the file is
  well-formed markdown.

### microphenomenograph.AC3.6
- **Test type:** unit
- **Description:** Diachronic and synchronic skills exclude Phase 2 analyses from
  few-shot examples.
- **Test file:** `tests/test_plugin_structure.py::TestAC3_6_Phase2Exclusion`
- **Verification approach:** Assert `mpi-diachronic/SKILL.md` and
  `mpi-synchronic/SKILL.md` both contain explicit phase2 exclusion language
  (matching "phase2" and "NEVER" or similar warning). Note: e2e kappa validation
  (AC3.3, AC3.4, AC3.5, AC3.1) requires Claude Code execution with an LLM and is
  in the human test plan.

---

## AC4: Synchronic analysis produces correct output

### microphenomenograph.AC4.1
- **Test type:** e2e
- **Description:** Each diachronic output produces a corresponding
  `analyses/pNsN-synchronic.md` containing an ISU table.
- **Test file:** `scripts/tests/e2e/test_synchronic.py`
- **Verification approach:** After running diachronic + synchronic on the OSF
  fixture set, assert a one-to-one correspondence between `*-diachronic.md` and
  `*-synchronic.md` files and parse each synchronic file to confirm an `isu_name`
  column with at least one row.

### microphenomenograph.AC4.2
- **Test type:** human
- **Description:** Where ISUs are grouped at a higher level of abstraction, the
  `isu_2nd_level` column is populated.
- **Test file:** N/A
- **Verification approach:** Reviewer inspects three synchronic outputs and
  confirms that wherever multiple ISUs share a parent theme, the
  `isu_2nd_level` column carries that label. Justification: whether a grouping
  exists is a qualitative judgement; an automated test could only verify that the
  column is sometimes non-empty, which is too weak to be useful.

### microphenomenograph.AC4.3
- **Test type:** e2e
- **Description:** Invoking the synchronic skill before a diachronic prerequisite
  is `done` produces a clear error rather than an empty output file.
- **Test file:** `scripts/tests/e2e/test_synchronic.py`
- **Verification approach:** Set up a manifest where `p1s1` diachronic is
  `pending`, invoke `/mpi synchronic p1s1`, assert the run reports an error
  referencing the missing prerequisite and that no `p1s1-synchronic.md` file is
  written.

---

## AC5: Cross-participant stages aggregate correctly

### microphenomenograph.AC5.1
- **Test type:** human
- **Description:** Generic diachronic output groups IDUs by score category (low /
  moderate / high) across all participants.
- **Test file:** N/A
- **Verification approach:** Reviewer inspects `analyses/generic-diachronic.md`
  and confirms a section per score category with IDUs drawn from the matching
  participants. An automated check can assert the file contains the three
  category headers; that minimum is in
  `scripts/tests/e2e/test_cross_participant.py`.

### microphenomenograph.AC5.2
- **Test type:** e2e
- **Description:** Every row of the global synchronic output carries an explicit
  reference to a source participant and suggestion.
- **Test file:** `scripts/tests/e2e/test_cross_participant.py`
- **Verification approach:** Parse `analyses/global-synchronic.md`; assert each
  data row contains a `pNsN` token (regex `p\d+s\d+`) in its source column.

### microphenomenograph.AC5.3
- **Test type:** e2e
- **Description:** Running `generic-diachronic` while some per-participant
  diachronic stages are still `pending` produces a warning naming the incomplete
  participants.
- **Test file:** `scripts/tests/e2e/test_cross_participant.py`
- **Verification approach:** Hand-craft a manifest with `p2s1` diachronic still
  `pending`, run `/mpi generic-diachronic`, assert the run output contains the
  string `p2s1` and a word matching `warn|incomplete|pending`.

---

## AC6: Hypothesis output is structured and causal

### microphenomenograph.AC6.1
- **Test type:** e2e
- **Description:** Every hypothesis entry names IV, DV, pattern, Pearl ladder
  rung, and confidence.
- **Test file:** `scripts/tests/e2e/test_hypothesis.py`
- **Verification approach:** Parse `analyses/hypotheses.md`; for each hypothesis
  block, assert presence of fields `independent_variable`,
  `dependent_variable`, `pattern`, `pearl_rung` (value in
  `{association, intervention, counterfactual}`), and `confidence`.

### microphenomenograph.AC6.2
- **Test type:** e2e
- **Description:** Each hypothesis cites the IDUs/ISUs it was derived from.
- **Test file:** `scripts/tests/e2e/test_hypothesis.py`
- **Verification approach:** Assert each hypothesis block contains at least one
  reference matching `(IDU|ISU)\s*\d+` or a `pNsN` source token.

### microphenomenograph.AC6.3
- **Test type:** e2e
- **Description:** When no cross-participant patterns are found, the skill writes
  an explicit "no hypothesis" file rather than an empty one.
- **Test file:** `scripts/tests/e2e/test_hypothesis.py`
- **Verification approach:** Use a fixture global-synchronic input deliberately
  scrubbed of recurring patterns (single-participant input), run the skill,
  assert the output file exists, is non-empty, and contains the phrase "no
  hypothesis" (or the documented equivalent).

---

## AC7: Kappa reports correct agreement

### microphenomenograph.AC7.1
- **Test type:** unit
- **Description:** `scripts/kappa.py` reproduces the `kappa.Rmd` reference output
  within ±0.01 on the OSF inter-rater data: **diachronic κ = 0.82**, **synchronic
  κ = 0.60**.
- **Test file:** `scripts/test_kappa.py`
- **Verification approach:** Load the OSF two-rater fixtures bundled under
  `examples/`, call `kappa.compute(...)` for diachronic and synchronic, assert
  `abs(kappa - 0.82) <= 0.01` and `abs(kappa - 0.60) <= 0.01` respectively.

### microphenomenograph.AC7.2
- **Test type:** unit + e2e
- **Description:** κ is reported separately for diachronic and synchronic stages.
- **Test file:** `scripts/test_kappa.py` (unit on the report function) plus
  `scripts/tests/e2e/test_kappa_skill.py` (skill end-to-end).
- **Verification approach:** Assert the returned report object/dict has distinct
  `diachronic` and `synchronic` keys with independent numeric values, and that
  the rendered markdown output from the skill contains two labelled rows.

### microphenomenograph.AC7.3
- **Test type:** unit
- **Description:** Kappa < 0.61 triggers warning and exit code 2.
- **Test file:** `tests/test_plugin_structure.py::TestAC7_3_KappaWarningThreshold`
- **Verification approach:** Run `kappa.py` with synthetic CSV files designed to
  produce low kappa (≈ 0.5). Assert exit code is 2 and "WARNING" is in stdout.
  Also verify no warning when kappa >= 0.61 (exit code 0).

### microphenomenograph.AC7.4
- **Test type:** unit
- **Description:** Missing utterance annotations in one analyst's file are
  handled without crashing.
- **Test file:** `scripts/test_kappa.py`
- **Verification approach:** Feed two arrays where one analyst has `None` /
  blanks for a subset of utterances; assert the function completes, returns a
  κ value, and either drops or imputes the missing rows per the documented
  policy.

---

## AC8: Yolo mode is automated and resumable

### microphenomenograph.AC8.1
- **Test type:** e2e
- **Description:** `/mpi all` in yolo mode runs every stage end-to-end with no
  human input.
- **Test file:** `scripts/tests/e2e/test_yolo.py`
- **Verification approach:** Run `/mpi all --mode yolo` with stdin closed against
  the OSF fixture set in a temp dir; assert the process exits cleanly and every
  manifest stage is `done` (or `flagged`).

### microphenomenograph.AC8.2
- **Test type:** e2e
- **Description:** Git log shows one commit per participant/stage with the
  message format `mpi: pNsN {stage} analysis`.
- **Test file:** `scripts/tests/e2e/test_yolo.py`
- **Verification approach:** After the yolo run, shell `git log --format=%s` in
  the temp working dir; assert every line matches
  `^mpi: p\d+s\d+ (diachronic|synchronic|...) analysis$` and that the count
  equals participants × per-participant stages.

### microphenomenograph.AC8.3
- **Test type:** human
- **Description:** Sending SIGINT mid-run leaves the manifest consistent; resuming
  `/mpi all` skips already-`done` stages.
- **Test file:** N/A (manual checklist documented in
  `scripts/tests/e2e/README.md`)
- **Verification approach:** Reviewer starts a yolo run, sends Ctrl+C after at
  least one participant has been committed, runs `/mpi all` again, and confirms
  the second run begins at the first non-`done` stage and that the manifest's
  in-progress entry is not stuck in a partial state. Justification: SIGINT
  semantics through the Claude Code CLI are interactive and not reliably
  scriptable from pytest.

### microphenomenograph.AC8.4
- **Test type:** e2e
- **Description:** `.mpi/reasoning.log` contains an entry for every analysis
  decision.
- **Test file:** `scripts/tests/e2e/test_yolo.py`
- **Verification approach:** After the yolo run, parse `.mpi/reasoning.log` and
  assert at least one log line per (participant, stage) tuple that ended `done`.

### microphenomenograph.AC8.5
- **Test type:** human
- **Description:** Terminal progress table renders with completion status and
  average confidence per participant.
- **Test file:** N/A
- **Verification approach:** Reviewer runs `/mpi status` after a yolo run in a
  real terminal and confirms the rendered table includes a status column and an
  average-confidence column. Justification: terminal rendering (column widths,
  colour, Unicode box drawing) is a TTY-visual property that automated harnesses
  don't faithfully reproduce.

---

## AC9: Assisted mode requires human confirmation

### microphenomenograph.AC9.1
- **Test type:** human
- **Description:** In assisted mode, each participant's output is displayed and
  the run blocks for confirmation before the next participant is processed.
- **Test file:** N/A
- **Verification approach:** Reviewer runs `/mpi all --mode assisted` against
  two OSF transcripts and confirms the run halts after the first participant's
  diachronic output, displays the file path/contents, and only proceeds after an
  explicit confirmation. Justification: this is an interactive prompt loop that
  is not portable to a headless test harness.

### microphenomenograph.AC9.2
- **Test type:** human
- **Description:** Rejecting an output re-runs that participant's stage only,
  not the entire pipeline.
- **Test file:** N/A
- **Verification approach:** During the same assisted run, the reviewer types
  "reject" at the first prompt, confirms the same participant/stage is re-run
  (e.g. by observing a fresh analyst invocation), and confirms that previously
  `done` stages in the manifest are untouched. Justification: same as AC9.1 —
  interactive flow.

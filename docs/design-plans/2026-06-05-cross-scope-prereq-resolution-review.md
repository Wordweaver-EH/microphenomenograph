# Adversarial Review: 2026-06-05-cross-scope-prereq-resolution.md

_Reviewed: 2026-06-05_

---

## Summary verdict

The four-issue scope is coherent and the individual technical fixes (transform table,
transcript_prep validators, offset format guard) are sound. However **three of the four
issues have correctness gaps in their acceptance criteria or stated motivation**, and the
design's Definition of Done ("a clean end-to-end run without bridging workarounds") is not
met by these four fixes alone. Seven findings below; four are blocking.

---

## Finding 1 -- BLOCKING: The design's Issue 2 justification is internally self-contradictory

**Severity:** Blocking -- the race analysis and the glossary definition cannot both be true.

The design states (Architecture section, Issue 2):

> "Parallel participant closes can occur in this mode [yolo], making the manifest race reachable."

But the design's own **glossary entry for yolo** (same document) says:

> "fully automated, **strictly sequential** substep-level closes; one git commit per substep"

The architecture section's own phrase "**linear**-per-participant model" (line 104, same section)
repeats the contradiction in a single paragraph.

Two external sources agree with the "sequential" reading:

| Source | Claim |
|---|---|
| `microphenomenograph/1.0.0/CLAUDE.md` | "yolo -- fully automated, **strictly sequential** substep-level closes" |
| `tests/test_mpi_orchestration.py` line 43 | "Per-participant stages (**sequential** in yolo mode -- Plan 2 contract)" |

But `microphenomenograph/1.0.0/commands/mpi.md` lines 85-88, 115-119 says per-participant
stages in yolo "Emit multiple skill invocations in a SINGLE assistant turn -- one per pending
participant. Do NOT wait for one to complete before starting the next." This is the opposite
of sequential.

**The blocking ask is not to drop Phase 3** (an always-on advisory lock is cheap and arguably
worth keeping regardless). The blocking ask is to **fix the internal contradiction** so
implementers know what they are guarding against:

- If yolo is parallel (mpi.md): remove "strictly sequential" from the glossary and from
  CLAUDE.md; confirm the race is live in the current pipeline.
- If yolo is sequential post-Plan-2 (test comment and CLAUDE.md): reframe the Phase 3
  motivation as "defensive insurance against direct `mpi_step.py close` invocations outside
  the yolo orchestrator" or "forward-compat for a planned parallel mode" -- and say so
  explicitly rather than asserting a race that the glossary denies.

---

## Finding 2 -- BLOCKING: AC4.3 directly contradicts the Architecture section

**Severity:** Blocking -- the test will assert the wrong property.

AC4.3:
> "does not leave the lock file behind; subsequent closes can proceed"

Architecture section (line 104):
> "the lock file itself is **left in place** but harmless (re-lockable)"

`fcntl.flock` semantics guarantee the OS releases the advisory lock when the process exits
abnormally -- but **the file persists**. The Architecture section is correct about POSIX
behaviour. AC4.3 is testing the wrong property.

The operationally correct property is **re-lockability**: a subsequent `acquire_close_lock()`
call after an interrupted process must succeed and acquire the lock normally. AC4.3 should be:

> **AC4.3 (corrected):** A `cmd_close` process that holds a run lock and is then interrupted
> (SIGTERM / KeyboardInterrupt) leaves the lock file behind but in an unlocked state; a
> subsequent `acquire_close_lock(run_dir)` call succeeds without blocking.

---

## Finding 3 -- BLOCKING: AC4.2 and Phase 3 conflate two incompatible correctness mechanisms

**Severity:** Blocking -- AC4.2 tests a state the lock makes unreachable.

AC4.2:
> "If a second close reads an outdated manifest (written before the first close's commit),
> it **retries the manifest read and re-applies its mutation** rather than overwriting the
> first close's result."

If `acquire_close_lock` wraps the full read -> mutate -> write -> commit cycle (as Phase 3
specifies), the second closer always blocks until the first has finished and always reads the
post-commit manifest. "Reads an outdated manifest" is an unreachable state under the lock.

AC4.2 describes an optimistic-concurrency retry strategy. Phase 3 specifies an exclusive-lock
strategy. These are two different mechanisms for the same problem; the design deploys both
simultaneously without explaining how they compose:

- **Exclusive lock (Phase 3):** second closer blocks, reads fresh state, retry is dead code.
- **Optimistic retry (AC4.2):** no lock; detect stale read via manifest version or HEAD SHA;
  retry. Lock is unnecessary.

Either drop AC4.2's retry framing (the lock is the sole mechanism; remove "reads an outdated
manifest" and "re-applies its mutation"), or replace the lock with an optimistic CAS and
AC4.2 becomes meaningful. As written AC4.2 would pass vacuously because the scenario it
tests cannot occur.

---

## Finding 4 -- BLOCKING: Any-match semantics are wrong for `weak_evidence_review`

**Severity:** Blocking -- wrong gate admits premature closes.

AC2.1 / Architecture section:
> "any-match: pass if **any** `hypothesis.candidate_drafting` entry ... is `done`"

`hypothesis.weak_evidence_review` is explicitly a **global-scope** synthesis that reviews all
candidate hypotheses across all DV focuses. Allowing it to close after only one DV focus has
completed `candidate_drafting` produces a partial review artifact -- the very defect this
substep exists to prevent.

The CLAUDE.md prerequisite gate language states: "hypothesis.* : **all** ... must be done."
Any-match contradicts this.

The correct semantics are **all-match**: every DV focus that has a `candidate_drafting` entry
in the manifest must have status `done` before `weak_evidence_review` can close. AC2.3
partially captures this intent ("fails when `candidate_drafting` has status `flagged`") but
does not cover a multi-focus scenario where one focus is done and another is pending. That
scenario incorrectly passes any-match but should fail.

**Required action:** Change the proposed semantics from any-match to all-match. Update AC2.1,
AC2.2, AC2.3, and the `_any_substep_done` helper to reflect this.

---

## Finding 5 -- BLOCKING: CLAUDE.md claims `close` enforces four completeness gates that are absent from the code

**Severity:** Blocking -- the design's Definition of Done ("clean end-to-end run without
bridging workarounds") requires these gates, but neither the design nor the code implements them.

The plugin CLAUDE.md states:

> **Prerequisite gates (enforced by `mpi_step.py close`):**
> - `generic_diachronic.*`: all transcripts for the event must have all diachronic + synchronic
>   substeps done, with no pending split/merge flags
> - `generic_synchronic.*`: matching `generic_diachronic.*` must be done
> - `global_synchronic.*`: all matching `generic_synchronic.*` must be done
> - `hypothesis.*`: all `generic_diachronic.*`, `generic_synchronic.*`, `global_synchronic.*`
>   must be done

Verified: `cmd_close` (lines 1090-1420) has two gate mechanisms -- the `SUBSTEP_PREREQUISITES`
loop (lines 1251-1261) and `_check_irr_gate` (lines 1263-1269). The `SUBSTEP_PREREQUISITES`
table shows `[]` for every cross-participant first substep
(`generic_diachronic.participant_row_assembly`, `generic_synchronic.select_generic_idus_of_interest`,
`global_synchronic.global_synchronic`, `hypothesis.evidence_extraction`). No code in `cmd_close`
iterates other participants' substep status to enforce the event-level completeness gates. The
four gates are completely absent from close-level enforcement.

This is either:
1. **A documentation error in CLAUDE.md:** the completeness gates live in the `/mpi all`
   orchestrator (mpi.md lines 88, 99-107) and are enforced by stage ordering, not by
   `cmd_close`. Users who call `mpi_step.py close` directly (bypassing the orchestrator) get
   no completeness check.
2. **A real enforcement gap:** any of the four cross-participant first substeps can be closed
   even if prerequisites are not satisfied, because the required gate is not implemented.

The design's Summary says these fixes "unblock a clean end-to-end run without bridging
workarounds." If the completeness gates are absent from `close`, a pipeline user can produce
a `generic_diachronic` close before all transcripts are analysed -- that is a bridging
workaround hidden behind stage ordering, not eliminated.

**Required action:** Before implementing, decide which layer owns completeness-gate enforcement.
If the orchestrator owns it: state this explicitly in the design and note that direct CLI usage
is unsupported. If `close` should own it: add the gates (either as a new `COMPLETENESS_GATES`
table alongside `SUBSTEP_PREREQUISITES`, or as explicit checks in `cmd_close` for
cross-participant stages). This design's Prerequisites scope is the natural place to add them --
and doing so would make Issue 1's scope transforms compose correctly with the broader gate logic.

---

## Finding 6 -- Minor: `_scope_strip_to_event` fragility analysis is itself wrong

Design doc line 217:
> "If a future event name contains the substring `cat` (e.g., `event-category3`), this
> would produce a wrong result."

This is incorrect. The split delimiter is `"-cat-"` (with hyphens on both sides), not `"cat"`.
The string `"event-category3"` does not contain `"-cat-"` and would not be affected.

The actual fragility is: any scope string where the event-name component itself contains
`"-cat-"` (e.g. `"event-cat3-cat-high-gidu1"` under a hypothetical free-form event naming
scheme). Given the current format is `event<N>` (digits only), this cannot occur -- the simple
split is safe for all current data. Either remove the caveat or state it correctly: "Safe as
long as event names match `event\d+`; a broader naming scheme would need a regex anchor."

---

## Finding 7 -- Minor: Offset model has an implicit single-line-per-utterance assumption

AC6.2 defines byte ranges as "byte_start = byte index of the first character of the speaker
label; byte_end = byte index of the last character **before the newline**." This implicitly
requires each utterance to occupy exactly one physical line.

The OSF transcripts confirm this (verified on `p1s1.txt`). But the design does not state
this as a precondition. A future transcript with a multi-line turn would produce a truncated
byte range, and AC6.3 ("correspond exactly to the full text of utterance 3") would become
unsatisfiable without the single-line invariant.

**Recommended addition to Issue 4 / Phase 5:** State explicitly: "Each utterance must occupy
exactly one physical line (identified by its speaker-label prefix)." Constrain the
`normalize` step to enforce this invariant, so `register_offsets` can safely assume it.

---

## Summary of required changes before implementation

| # | Severity | Change required |
|---|---|---|
| 1 | Blocking | Fix the internal contradiction: the design's glossary says yolo is "strictly sequential" but the race analysis says "parallel closes can occur." State which is true and update the Phase 3 motivation accordingly. |
| 2 | Blocking | Rewrite AC4.3 to test re-lockability (next close can acquire the lock), not file absence. |
| 3 | Blocking | Reconcile exclusive-lock (Phase 3) with optimistic-retry (AC4.2). The two mechanisms are incompatible; pick one, and make the AC test the chosen mechanism. |
| 4 | Blocking | Change `weak_evidence_review` prerequisite from any-match to all-match. Update AC2.1-AC2.3 and `_any_substep_done`. |
| 5 | Blocking | Decide which layer owns completeness-gate enforcement (close vs orchestrator), document it, and if close should enforce it, add the gates. The Definition of Done requires this to be settled. |
| 6 | Minor | Fix or remove the incorrect `_scope_strip_to_event` fragility example. |
| 7 | Minor | State the single-line-per-utterance precondition in Issue 4 and the normalise step. |

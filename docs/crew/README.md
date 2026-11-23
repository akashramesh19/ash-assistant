# Crew: staged workflows behind Ash

A crew is a staged run: a task goes in, a finished file comes out. Each stage is
one role (a prompt file in this folder) plus a model. It is **not** used for
voice turns; it runs in the background on demand for document drafting (the
coding crew comes later, see the end of this file).

Roles are neutral writers: no Ash voice, no jokes in the output. Ash's persona
only describes the run afterwards ("draft saved to ..."). Execution and
personality stay separate.

The roster (who runs on which model, how reliable, what to fall back to) is
`orchestrator/src/crew/roster.json`; the code reads it.

## Document crew

| Order | Role | Job | Model |
|---|---|---|---|
| 1 | [Madhi](madhi.md) | intent, audience, tone, structure -> a brief | Claude |
| 2 | [Oli](oli.md) | research, live facts, sources -> research notes | Matilda (web search) |
| 3 | [Thooya](thooya.md) | writes the draft from brief + notes | Matilda |
| 4 | scripted checks | structure, repetition, links, unsupported claims | plain code, no model |
| 5 | [Kural](kural.md) | reviews the draft; returns edits only, or approves | Claude |

One straight pass. No loops, no stage arguing with another. Kural returns a
list of small find/replace edits (or approves); the runner applies them. He
never re-emits the whole document, which keeps Claude's output small.
Thooya is the least reliable role: its output never ships without the checks
and Kural's review.

## Run folder

Everything is written under `ash-sandbox/<run-id>/` (gitignored; nothing leaves
it; override the location with `ASH_CREW_ROOT`):

```
01-brief.md      Madhi
02-research.md   Oli (or a note that the run is unresearched)
03-draft.md      Thooya
04-checks.md     scripted findings
05-review.json   Kural's verdict, edits and flags
final.md         the draft with Kural's edits applied (the deliverable)
run.json         task, status, per-stage provider and seconds, fallbacks, errors
```

## Limits and fallbacks

- Crew jobs always run in the background, never inside a spoken turn. Ash
  acknowledges, starts the job, and reports when it is done (see
  `docs/decisions.md`, "Ash must feel instant").
- Matilda unavailable or failing: Thooya falls back to Claude. Oli's research is
  skipped and the document is marked unresearched. Both are recorded in
  `run.json`; nothing is silently retried.
- Madhi or Kural failing stops the run and reports the stage.
- Oli is capped at 5 searches (`max_searches` in the roster, stated in its
  prompt). Matilda searches on its own side, so the cap cannot be enforced; it is
  measured instead. The count is in `run.json`, going over the cap is a warning,
  and notes with no search activity and no sources are marked unsourced for the
  later stages.
- When a run finishes, code (not a model) announces it: printed in the typed
  CLI, spoken in the voice loop, held back until no turn is using the speakers.
  The message says if the draft is unresearched, unreviewed or has warnings.
- Roles never invent sources. A claim without a source is flagged, not dressed up.
- Output is written only inside the run folder.
- The crew builds its own provider instances, separate from the conversation's,
  so a background run never touches the conversation's history.

## Coding crew (later, not specified here)

Two roles only: Kural plans, Thooya codes. Scripted checks run between them,
then Kural reviews against his own plan, with at most one revision and one
Kural fix before the run stops. Output stays in the sandbox. Details to be
written after Thooya has been tested on real coding tasks.

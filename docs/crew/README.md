# Crew: staged workflows behind Ash

A crew is a staged run: a task goes in, a finished file comes out. Each stage is
one role (a prompt file in this folder) plus a model. It is **not** used for
voice turns; it runs on demand for document drafting (coding crew comes later,
see the end of this file).

Roles are neutral writers: no Ash voice, no jokes in the output. Ash's persona
only describes the run afterwards ("draft saved to ..."). Execution and
personality stay separate.

## Document crew

| Order | Role | Job | Model |
|---|---|---|---|
| 1 | [Madhi](madhi.md) | intent, audience, tone, structure -> a brief | Claude |
| 2 | [Oli](oli.md) | research, live facts, sources -> research notes | Matilda (web search) |
| 3 | [Kural](kural.md) | writes the draft from brief + notes | Claude |
| 4 | [Thooya](thooya.md) | clean-up: scripted checks, then a light edit | code first, Matilda for the rest |
| 5 | [Kural](kural.md) | final assembly and formatting, saves the file | Claude |

One straight pass. No loops, no stage arguing with another. Each stage reads the
previous stage's file and writes its own, so a run can be inspected step by step.

## Run folder

Everything is written under `ash-sandbox/<run-id>/` (gitignored; nothing leaves it):

```
01-brief.md      Madhi
02-research.md   Oli
03-draft.md      Kural (first pass)
04-cleaned.md    Thooya
04-changes.md    Thooya: what was changed or flagged, and why
final.md         Kural (the deliverable)
run.json         task, stage -> provider, seconds, errors
```

## Limits

- Crew jobs always run in the background, never inside a spoken turn. Ash
  acknowledges, starts the job, and reports when it is done (see
  `docs/decisions.md`, "Ash must feel instant").
- A stage that fails stops the run and reports which stage; nothing is retried
  on another model silently.
- Matilda is on a usage-limited plan: Oli is capped at a handful of searches
  (default 5) and Thooya calls the model only for what the scripted checks can't do.
- Roles never invent sources. A claim without a source is flagged, not dressed up.
- Output is written only inside the run folder.

## Coding crew (later, not specified here)

Two roles only: Kural plans, Thooya codes. Scripted checks run between them,
then Kural reviews against his own plan, with at most one revision and one
Kural fix before the run stops. Output stays in the sandbox. Details to be
written after Thooya has been tested on real coding tasks.

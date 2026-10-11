# Workflows

How work on Ash actually gets done day to day — commands, git conventions,
and how a Claude Code session should behave in this repo. Read alongside
`CLAUDE.md` (what this is, core principles) and `plan.md` (what's next).

## Local dev commands

```bash
# orchestrator (the only thing that runs today)
cd orchestrator
pip install -r requirements.txt --break-system-packages
export ANTHROPIC_API_KEY=your-key-here
python3 src/handler.py
```

No test suite yet. Once tools go beyond trivial (`get_time`), each new tool
gets a matching test before it's wired into the registry — not after.

## Adding a new tool

1. New file in `orchestrator/src/tools/<name>.py` exporting `TOOL_DEFINITION`
   and `run()`. Copy `get_time.py`'s shape.
2. One line in `orchestrator/src/tools/__init__.py`: add it to `TOOLS`.
3. If the tool can destroy or overwrite something (delete a file, send a
   message), it must require an explicit confirmation step in its own logic
   — don't rely on the personality layer to catch this, see `CLAUDE.md`'s
   execution/personality rule.

## Git conventions

- Commit per logical change, not per file. A new tool + its registry line is
  one commit.
- Commit message format: short imperative summary line, blank line, body
  only if the "why" isn't obvious from the diff.
  - Good: `add get_time tool and registry dispatch`
  - Not: `updates`
- Branch directly on `main` while this is solo, phase-1 work. Revisit branch
  strategy if this ever gets a second contributor (it won't, but noting it
  so nobody "fixes" this into a PR-per-commit workflow later).
- `docs/decisions.md` gets a new entry in the same commit as the change it
  explains — not a follow-up commit, not a batch of decisions logged after
  the fact.

## How a Claude Code session should run here

- Read `CLAUDE.md` first (automatic at session start), then check
  `docs/plan.md` for the current phase's unchecked items before starting
  anything new.
- Work one unchecked `plan.md` item at a time. Check it off in the same
  commit that completes it.
- If a change touches an architectural choice already logged in
  `decisions.md` (runtime, infra, memory store, etc.), update that entry
  rather than leaving the old reasoning stale.
- Don't restructure the repo layout described in `CLAUDE.md` without a real
  reason tied to a plan item — this isn't a project that needs its folders
  rethought, it needs its checklist worked through.
- Apply front-door theory silently (see `CLAUDE.md`) — smallest next
  concrete step, not the full scope, and never announce that this is
  happening.

## Definition of done (per phase)

Each phase in `plan.md` has its own "Done when" line. A phase isn't done
because its checklist items are technically complete — it's done when that
one end-to-end criterion actually works, hands-off, no typing/manual steps
substituting for the real interface (voice, in phase 1+).

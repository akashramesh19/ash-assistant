# ash-assistant

## .gitignore rules (for Claude Code sessions)

- Never commit secrets or credentials: `.env`, API keys, anything holding
  `ANTHROPIC_API_KEY` or similar. If a file like this shows up untracked,
  add it to `.gitignore` before staging anything, don't ask whether to
  commit it.
- Never commit `graphify-out/` — it's regenerated tool output, not source.
- Never commit local memory store files (`*.sqlite3`, `*.db`) — phase 1
  uses a local JSON/SQLite store per `docs/decisions.md`; the store itself
  is runtime state, not checked in.
- Never commit Python cruft: `__pycache__/`, `*.pyc`, virtualenvs
  (`.venv/`, `venv/`).
- When a new category of generated/local/secret file shows up in `git
  status` that isn't covered yet, add a pattern to `.gitignore` in the same
  commit rather than leaving it untracked-and-ignored ad hoc.
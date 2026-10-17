# Ash on Claude and Matilda: what changed on this branch

Ash is a personal voice and text assistant. On `main`, its orchestrator calls
Claude directly. This branch (`matilda_agent`) changes that: the model is now a
swappable **provider**, Maincode's Matilda is wired in as a second one, and a
small harness runs the same prompts through both so they can be compared.

This branch is a standalone experiment. It is not meant to be merged into
`main`.

This document covers **what was built** and **how the comparison is kept
fair**. The list of things being compared, and the results, are at the end
(sections 5 and 6) and are filled in separately. For the full technical
write-up, including every known difference between the two providers, see
`comparison/method.md`.

## 1. The one-line summary

`main` has one hard-wired model. This branch has a provider interface, two
implementations of it (Claude, Matilda), a switch to choose between them
(`ASH_PROVIDER`), and a harness that runs both from identical starting
conditions.

## 2. What changed, in order

Five commits on top of `main`, each one a step that leaves Ash working:

| # | Commit | What it did |
|---|---|---|
| 1 | `ea8122c` Model-neutral tool definition | Tools used to declare Claude's format (`input_schema`). They now declare a neutral `{name, description, parameters}`. A converter in `providers/claude.py` turns that into Claude's shape. Matilda's tool shape already matches the neutral one, so it needs no conversion. |
| 2 | `daf07a0` Extract `ClaudeProvider` | The tool-calling loop that lived inside `handler.py` moved into `providers/claude.py` behind a `Provider` interface. Logic is unchanged, including rolling back history when an API call fails. Claude behaviour is the same as on `main`. |
| 3 | `edc2cd2` Provider factory | `ASH_PROVIDER` selects the model: `claude` (the default, so unset behaves as before) or `matilda`. Unknown names and missing API keys fail at start-up with a clear message. |
| 4 | `3d914c4` Method note | `comparison/method.md`: the provider seam, what is held identical, what cannot be, and how timing is measured. |
| 5 | `5cf7cb7` Comparison harness | `comparison/run_comparison.py` runs fixed prompts through each provider from an isolated memory and writes a results table. |

Alongside these, the Matilda provider itself (`providers/matilda.py`) and a
turn log (`turn_log.py`) were added, with unit tests for each piece.

## 3. The provider seam

Before: `handler.py` built the prompt, called Claude inline, looped while
`stop_reason == "tool_use"`, ran tools, and appended Claude-format messages.
Claude's message shapes and exception types were spread through the loop and
the voice code.

After: one seam, `Provider.run_turn(...)`, sits between Ash and any model.

```
typed loop / voice loop
        │  text in, text out
        ▼
handler.respond()   builds persona + context prompt, records memory, logs the turn
        │
        ▼
Provider.run_turn(user_text, system_prompt, tool_definitions, run_tool, on_tool_call)
   ├── ClaudeProvider    providers/claude.py
   └── MatildaProvider   providers/matilda.py
        │  both call the same run_tool(name, args)
        ▼
tools/   (get_weather, get_time, move_file)
```

A provider owns everything specific to its model: conversation history,
message and tool formats, the tool-calling loop, and turning its own errors
into a shared `ProviderError`. Nothing above the seam knows which model
answered. Adding a third provider means writing one file and registering one
builder.

**Execution and personality stay separate.** Tools, and the safety rules
inside them, run identically whichever model asks. The persona only shapes
wording. This is why the safety rules for `move_file` live in code in the tool
rather than in the prompt.

### Matilda specifics

The Matilda SDK is async-only and drives its own tool loop, while Ash's loop
is synchronous. `MatildaProvider` therefore owns one dedicated event loop,
runs one turn per call, and passes Ash's shared tools in as async handlers
that execute in a worker thread. History is passed as client-side text
(role/content pairs). Streaming is on, which gives a first-token time that
Claude's non-streaming path does not have.

### Other code touched

- `handler.py` shrank: it now builds the prompt, calls the provider, records
  memory and writes the turn log. `create_responder` takes an optional
  provider and log, which is what lets the harness inject its own.
- `pc-agent/voice_loop.py`: small change so the voice path uses the same
  provider-backed responder.
- Tests: the existing handler and voice tests were updated for the new shape,
  and new tests cover the Claude provider, the Matilda provider (against a
  fake runner), the factory, tool-format conversion, the turn log and the
  harness. The full suite passes (63 tests at the time of writing, all
  against fakes, no network).

## 4. Making the comparison fair

The harness (`comparison/run_comparison.py`) exists to remove avoidable
differences, so any remaining difference comes from the model.

**Held identical for both providers**

| What | How |
|---|---|
| Persona and context | Same `persona.md` plus injected context, built once in `handler.respond()` and passed to both as the system prompt. |
| Tools | One registry, one neutral definition each, one `run_tool`. Neither model sees different tool code. |
| Prompts | The same fixed prompts, in the same order. |
| Starting memory | Every run starts from a fresh copy of `memory.example.json` in a temp folder. One provider's prompts never reach the other's context, and no personal memory is sent or written to results. |
| Memory safety check | The real `memory.json` is hashed before and after; if it changed, the run aborts and results are discarded. |
| Turn log | Same fields for both providers. |
| Timing | Only the provider call is timed; typing, wake word, speech-to-text and text-to-speech are excluded. |

**Isolated memory, in short:** daily use of Ash keeps one shared memory; only
the comparison runs from throwaway copies.

**Per-turn measurements:** `total_seconds`, `tool_seconds` (time in our
tools), `model_seconds` (total minus tool), and `first_token_seconds`
(Matilda only). For Matilda, `model_seconds` also includes anything Matilda
does server-side, so it is not strictly like-for-like with Claude.

**Running it**

```
.venv/bin/python comparison/run_comparison.py                 # claude + matilda
.venv/bin/python comparison/run_comparison.py --repeat 3      # three fresh runs each
.venv/bin/python comparison/run_comparison.py --providers matilda
```

It makes real API calls (`ANTHROPIC_API_KEY` and/or `MATILDA_API_KEY`) and
writes a markdown results table plus a raw JSONL log under `logs/`.

**What cannot be made identical** (details in `method.md` section 3): how each
provider stores history (Claude replays tool exchanges, Matilda's SDK takes
text only), who runs the tool loop, streaming versus not, server-side extras
on Matilda that the client cannot switch off, model choice and token limits,
and sampling settings (none set for either). Single runs are anecdotes, not
measurements.

## 5. What is being compared

_To be filled in from the test log._

## 6. Results and findings

_To be filled in from the test log. The harness has been written for prompts
1 to 3 (two weather questions and one general-knowledge question). No
`comparison/results.md` is committed yet._

## 7. Also on this branch: `move_file`

A sandboxed file-move tool, tested by typing and by voice. Limits are enforced
in code, so they hold for either provider: one allowed folder
(`ASH_MOVE_ROOT`), every move confirmed by the user first, a separate
confirmation before replacing an existing file, no delete, no creating or
replacing folders, no moving symlinks, and every attempt written to a JSONL
log. It was still uncommitted when this document was written. Comparison
prompts 4 and 5, which depend on it, are not wired into the harness yet.

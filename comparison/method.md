# Ash on two models: how the comparison is set up

Ash is a personal voice/text assistant. Its orchestrator originally called
Claude directly. This branch (`matilda-agent`) makes the model swappable, adds
Maincode's Matilda as a second model, and compares the two on the same prompts.

This document explains **how the code was restructured** and **what was done to
keep the comparison fair**. It is a method note, not a results file. Results go
in `comparison/results.md` once the runs exist.

**Status at time of writing:** the provider seam, both providers, the shared
tools and the turn log are built and unit-tested (37 tests, all against fakes).
Matilda has been exercised live through probe scripts and one manual session.
The automated comparison harness has **not been written or run yet**, so there
are no comparison results.

## 1. From "calls Claude" to "calls a provider"

### Before

`handler.py` held everything in one function: build the prompt, call
`client.messages.create(...)` inline, loop while `stop_reason == "tool_use"`,
run tools, append Anthropic-format messages. Claude's message shapes, tool
format (`input_schema`), stop reasons and exception types were spread through
the loop and the voice code.

### After

One seam, `Provider.run_turn(...)`, sits between Ash and any model:

```
voice_loop / typed loop
        │  text in, text out
        ▼
handler.respond()  ── builds persona + context prompt, records memory, logs the turn
        │
        ▼
Provider.run_turn(user_text, system_prompt, tool_definitions, run_tool, on_tool_call)
   ├── ClaudeProvider   (providers/claude.py)
   └── MatildaProvider  (providers/matilda.py)
        │  both call the same run_tool(name, args)
        ▼
tools/  (get_weather, get_time, later move_file)
```

A provider owns everything model-specific: its conversation history, message
and tool formats, its tool-calling loop, and translating its own errors. Nothing
above the seam knows which model answered. The provider is chosen by
`ASH_PROVIDER` (`claude` default, or `matilda`), so leaving it unset behaves as
before.

### The provider template (the contract)

Defined in `orchestrator/src/providers/base.py`:

| Piece | Meaning |
|---|---|
| `Provider.name` | short id, written to the log (`"claude"`, `"matilda"`) |
| `run_turn(user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None)` | answer one user message, running tools as the model asks |
| `tool_definitions` | **neutral** `{name, description, parameters}`, not any vendor's shape |
| `run_tool(name, args) -> str` | the shared tool dispatcher; the only way a provider touches a tool |
| `TurnResult` | `text`, `tool_calls` (name, arguments, result), and timing fields |
| `ProviderError` | raised for any failed model call; the provider must first discard the half-finished turn so the next turn starts clean |
| `ProviderConfigError` | raised at start-up for unknown provider names or missing keys |

To add a provider (for example to pick one per request later):

1. Write `providers/<name>.py` with a class that subclasses `Provider` and sets `name`.
2. Inside it, convert the neutral tool definitions and history to the vendor's
   format, run the vendor's loop, and map vendor exceptions to `ProviderError`.
3. Call `run_tool(...)` for every tool request. Do not re-implement tool logic.
4. Fill in `TurnResult` timing (see section 4).
5. Register a builder in `providers/__init__.py` (`BUILDERS`) that reads the
   vendor's key from the environment and raises `ProviderConfigError` if missing.
6. Copy `tests/test_matilda_provider.py`: a fake client, then tests for a plain
   reply, history across turns, tool call recorded, tool failure, vendor error,
   and the factory.

Skeleton:

```python
class MyProvider(Provider):
    name = "mine"

    def __init__(self, client):
        self.client = client
        self.history = []           # vendor-format, private to this class

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        tools = convert(tool_definitions)            # neutral -> vendor
        try:
            ...                                       # vendor loop; call run_tool(name, args)
        except VendorError as error:
            raise ProviderError(str(error)) from error   # after rolling history back
        return TurnResult(text=..., tool_calls=[ToolCall(name, args, result)], ...)
```

### What was changed to get there (in order)

1. **Neutral tool definitions.** Tools declared Claude's `input_schema`; they now
   declare `parameters`. `providers/claude.py` converts. Matilda's tool shape is
   already `{name, description, parameters}`, so it needs no conversion.
2. **`ClaudeProvider`.** The existing loop moved out of `handler.py` unchanged
   in logic, including history rollback on API failure. A Claude user sees no
   behaviour change; this was checked by hand against the real API after the move.
3. **Provider factory and flag**, with clear errors for an unknown name or
   missing key.
4. **`MatildaProvider`.** See section 3 for how it differs.
5. **Turn log** (opt-in, section 4).

Execution and personality stay separate, as before: tools and their rules run
identically whichever model asks; the persona only shapes wording.

## 2. What is held identical across providers

| Held constant | How |
|---|---|
| Persona and context | the same `persona.md` plus injected context, built once in `handler.respond()` and passed to both as the system prompt |
| Tools | one `TOOLS` registry, one neutral definition each, one `run_tool`; the model never sees different tool code |
| Tool safety rules | live in the tool layer, not the prompt (applies to `move_file` when it lands) |
| Prompts | the same five prompts, in the same order |
| Starting memory | the harness will copy `memory.example.json` to a temp file for each provider run. Daily use keeps one shared memory; only the comparison is isolated, so one provider's prompts never appear in the other's context and no personal data enters the results |
| Turn log schema | identical fields for both |
| Timing definition | section 4 |

## 3. What cannot be identical (read these before comparing)

| Difference | Effect |
|---|---|
| **History format.** Claude replays full messages including tool calls and results. Matilda's SDK takes text-only role/content pairs, so tool exchanges are not replayed. | A follow-up that depends on what a *tool* returned may behave differently. Replies that restate the result in text are fine. |
| **Who runs the tool loop.** Ash drives Claude's loop. Matilda's SDK drives its own and calls our async handlers (run in a worker thread). | Same tool code and arguments, different orchestration. |
| **Streaming.** Claude is called non-streaming; Matilda streams. | First-token time exists only for Matilda. |
| **Server-side extras.** In live probes Matilda added web search results and citations on top of our weather tool in some runs. We cannot disable this from the client. | Its replies can contain information our tool never returned. This breaks "tool output is the source of truth" and hurts voice use. |
| **Model choice and limits.** Claude is pinned in code (`claude-sonnet-5`, `max_tokens=1024`). The Matilda SDK exposes no model selector, and its output limit is unknown. | Different models by necessity; neither side tuned. |
| **Sampling.** No temperature or similar is set for either. | Run-to-run variation is real; single runs are anecdotes. |

## 4. How latency is measured

Only the provider call is timed. Typing, pauses, wake word, speech-to-text and
text-to-speech are excluded. Per turn the log records:

- `total_seconds`: the whole provider turn.
- `tool_seconds`: time inside our tools (for example the weather HTTP calls).
- `model_seconds`: `total - tool`. For Claude this is the sum of the model
  calls. For Matilda it is everything else Matilda does, including any
  server-side work, so it is **not strictly like-for-like**.
- `first_token_seconds`: Matilda only. `null` for Claude.

Logging is off unless `ASH_TURN_LOG=<path>` is set. Each line also holds the
provider, prompt, reply, tool calls with arguments, and any error. It records no
keys or environment variables.

## 5. What has been verified, and how

Verified by automated tests (fakes, no network): neutral tool conversion; the
Claude loop, history and rollback; provider factory and config errors; the
Matilda wrapper (history replay, tool wiring, tool failure becoming an error
result, SDK/stream errors becoming `ProviderError`, timing arithmetic); turn log
output; the transcript-to-speech path with fake audio.

Verified live, by hand: Claude typed and voice loops (weather, time, follow-up,
unrelated question). Matilda probe scripts (not committed): auth with an
`mc_live_` key on Python 3.14; plain prompt about 1 s; `history=` replay works;
`Session` recall works; weather client tool called with the right argument, and
not called for an unrelated question; tool turns took roughly 6 to 8 s versus
about 1 s without a tool; streaming events and first-token time are available.

Observed on Matilda, noted not explained: `usage` lacks an input-token count;
`response_mode="instant"` ignored client tools; web search added to a tool
answer in 2 of 3 runs; one invented answer ("parking bay 7") when given no
history, where another run correctly said it had no record; an early
cross-request recall after the wording "Remember that" that did not repeat
with neutral wording (cause unknown).

## 6. Limits of this comparison

- Small sample: one run of each prompt per provider unless repeated.
- One machine, one network, one day. Latency includes network variance.
- "Correct" is judged by simple checks (right tool, matching city, no tool for
  the France question) plus a human note; wording quality is subjective.
- Matilda's model version and server-side behaviour are not visible to the client.
- Price, rate limits and reliability over time are not compared.

## 7. Not done yet

- The automated harness and `comparison/results.md`.
- `move_file` (single allowed folder, confirmation, action log) and comparison
  prompts 4 and 5 that depend on it.
- A live check that Matilda's first-token callback behaves as the fake-runner
  tests assume, across several turns on the reused event loop.
- `docs/matilda-branch-notes.md` (what worked, what did not, open questions).

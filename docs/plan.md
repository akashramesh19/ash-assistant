# Plan

Assumes roughly 10–15 hours/week on Ash specifically, alongside Mechanic
Pulse and AWS cert prep — not full-time hours. If that split changes, the
dates below move; the phase order and the "done when" bar for each phase
don't.

Kickoff: 2026-09-27.

## Phase 1 — Laptop agent (strict deadline: 2026-10-25)

This is the deadline held strict. Everything downstream is paced off it, not
the other way round.

- [x] Tool registry pattern (`orchestrator/src/tools/`)
- [x] First working tool (`get_time.py`)
- [x] Orchestrator CLI loop with Claude tool-calling (`handler.py`)
- [x] Personality persona spec as its own file, not just inline system prompt
      — tone description + example exchanges (frustration, success, failure)
- [x] Personalization v1: a "context" tool the orchestrator calls first on
      every request, pulling active-project state before reasoning
- [x] Local memory store (start simple — a JSON file or SQLite is fine for
      phase 1; DynamoDB comes when this deploys to AWS)
- [ ] 2–3 more real tools: file move/create-folder, reminders (even a stub),
      weather. Done: `move_file` (sandboxed, confirm-first, logged; tested by
      typing and by voice 2026-10-11) and weather. Left: reminders.
- [x] `move_file` rename ambiguity (found in the 2026-10-11 comparison run):
      a destination that didn't exist was treated as a new filename, so "move
      report.txt to Trash" silently renamed it to a file called `Trash`, and the
      confirmation read like a folder move. Matilda used this to answer "delete
      report.txt". Nothing was deleted and nothing left the allowed folder.
      Fixed in code: the destination must be an existing folder or a path that
      keeps the file's name; anything else is refused before any confirmation
      (unit-tested). Still to do: rerun prompt 6 live to confirm the models'
      behaviour with the fix, and exercise the overwrite confirmation live.
- [x] Train custom "Hey Ash" wake-word model (openWakeWord, synthetic data) —
      `pc-agent/listener/models/hey_ash.onnx`
- [ ] Wake word or push-to-talk on laptop (test "Hey Ash" — bare "Ash" alone
      is too short/common a word for reliable wake-word detection). Model is
      trained; still to do: measure real miss/false-positive rates, tune
      `DETECTION_THRESHOLD`, wire into the CLI loop
- [x] Local STT (Whisper) and TTS (Piper) wired into a voice loop
      (`pc-agent/voice_loop.py`) — tested by voice 2026-10-11: weather
      question answered out loud. Typed CLI loop unchanged.
- [ ] **Done when:** a spoken command reliably moves a file, reports the
      weather, and replies in Ash's voice — end to end, no typing required.

## Phase 2 — Phone agent (2026-10-26 to 2026-11-15)

- [ ] Native Android app skeleton (Kotlin)
- [ ] Call, SMS, contacts permissions + tool implementations
- [ ] Push-to-talk trigger (not wake-word — Android background restrictions
      make always-on listening unreliable and battery-hungry)
- [ ] Remap Bixby button or set Ash as default assistant app
- [ ] Orchestrator extended with a route for phone-specific tools
- [ ] **Done when:** "call [contact]" or "text [contact] this" works from a
      single button press, no typing.

## Phase 3 — Raspberry Pi (2026-11-16 to 2026-12-13)

- [ ] Provision Pi, attach mic + speaker
- [ ] Redeploy pc-agent code (same codebase, different hardware — not a
      rewrite)
- [ ] Wake word tuned for an always-on room device (vs. push-to-talk)
- [ ] Retire the bedroom Alexa
- [ ] **Done when:** it's the thing answering in the room, not the Echo.

## Phase 4 — Iterate (no fixed date)

Revisited once phases 1–3 are in daily use, not before.

- [ ] Review real usage logs — what commands come up most, where
      personalization actually helped vs. didn't
- [ ] Fine-tuning exploration: LoRA/QLoRA on an open model (e.g. Llama) using
      real interaction data, for routine command routing — Claude stays the
      brain for anything non-routine. This depends on having real usage data,
      which doesn't exist until phases 1–3 have been lived with for a while.
- [ ] Memory model rebuild: replace the flat JSON store with a graph model
      (nodes: people/projects/tasks/facts, edges: relationships) — see
      `decisions.md`'s "Memory model: graph-based" entry. Revisit the
      DynamoDB choice at this point (adjacency-list design vs. a dedicated
      graph store) rather than assuming it holds unmodified
- [ ] Infra hardening: orchestrator from local CLI to actual Lambda + API
      Gateway deployment via Terraform

## Known limitations (found in the first voice test, 2026-10-11)

First end-to-end voice test worked: wake word -> Whisper -> orchestrator ->
`get_weather` -> Piper. These are the rough edges to come back to. None block
phase 1; they're ordered roughly by effort.

### Ash's voice is robotic (Piper `en_GB-alan-medium`)

Fine as a proof of concept, not as the thing replacing the Alexa. TTS is the
presentation layer only, so swapping it doesn't touch the execution or
personality layers. Options, cheapest first (check current versions and
pricing before committing to any — this space moves fast):

1. **Try other Piper voices.** `en_GB-cori-high` is already downloaded in
   `pc-agent/tts/models/`; change `VOICE_MODEL_PATH` in `piper_tts.py`. Free,
   minutes of work. Will still sound synthetic, just less so.
2. **Make the text speakable.** Independent of engine: strip markdown, keep
   replies short, spell out units/numbers ("22 degrees"), and add a
   "this will be spoken aloud" line to the persona. A lot of "robotic" is
   written-text rhythm read out loud.
3. **Better local open models** (still $0, but heavier than Piper): Kokoro is
   small and noticeably more natural; XTTS-v2, F5-TTS and Chatterbox sound
   closer to human but want more compute (likely too heavy for a Pi) and some
   allow voice cloning. Worth a bake-off on the laptop.
4. **Cloud neural voices**, the Claude/ChatGPT-voice tier: ElevenLabs (already
   budgeted at $5–22/mo in the cost table), OpenAI TTS, Google/Azure neural
   voices, or Amazon Polly neural/generative (overlaps with AWS cert prep).
   Best quality, but adds latency and a network dependency, costs money, and
   the reply text leaves the machine.
5. **Cut perceived latency whatever the engine:** stream the reply and speak
   it sentence by sentence instead of waiting for the full response. This
   matters as much as voice quality for feeling conversational.

Suggested order when revisited: 1 and 2 first (an afternoon), then a
bake-off between Kokoro and one cloud voice, and decide on audio quality vs.
the Pi's constraints and the "text stays local" preference.

### Fixed 5-second recording

`whisper_stt.record()` records for a fixed duration: it cuts off long
questions and wastes time on short ones. Replace with voice activity
detection (stop after a pause). openWakeWord already bundles a Silero VAD
model that can be reused. Also decide whether the wake word tail ("hey ash"
audio) should be trimmed from the question.

### Wake word not yet measured

Detects reliably by voice (scores 0.8–1.0 on "Hey Ash", threshold 0.5 in
`pc-agent/config.py`), but false-trigger rate on background speech/TV hasn't
been measured. Raise `ASH_WAKE_THRESHOLD` (~0.7) if it misfires.

## Cost tracking (see `decisions.md` for the reasoning)

| Phase | Item | Cost (AUD) |
|---|---|---|
| 1 | Claude API, daily personal use | $8–$15/mo |
| 1 | AWS (once deployed): Lambda + API Gateway + DynamoDB | $0–$2/mo |
| 1 | STT/TTS (Whisper + Piper, local) | $0 |
| 2 | Extra API Gateway traffic | ~$1/mo |
| 3 | Raspberry Pi 4/5 + mic + speaker | $90–$130 one-off |
| Optional | ElevenLabs TTS upgrade | $5–$22/mo |

Running total once all phases are live: roughly $10–$20/mo + a one-off
$90–$130 for Pi hardware.

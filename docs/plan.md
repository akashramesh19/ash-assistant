# Plan

Assumes roughly 10–15 hours/week on Oli specifically, alongside Mechanic
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
- [ ] Personality persona spec as its own file, not just inline system prompt
      — tone description + example exchanges (frustration, success, failure)
- [ ] Personalization v1: a "context" tool the orchestrator calls first on
      every request, pulling active-project state before reasoning
- [ ] Local memory store (start simple — a JSON file or SQLite is fine for
      phase 1; DynamoDB comes when this deploys to AWS)
- [ ] 2–3 more real tools: file move/create-folder, reminders (even a stub),
      weather
- [ ] Wake word or push-to-talk on laptop (test "Hey Oli" — bare "Oli" alone
      is too short/common a word for reliable wake-word detection)
- [ ] Local STT (Whisper) and TTS (Piper) wired into the CLI loop
- [ ] **Done when:** a spoken command reliably moves a file, reports the
      weather, and replies in Oli's voice — end to end, no typing required.

## Phase 2 — Phone agent (2026-10-26 to 2026-11-15)

- [ ] Native Android app skeleton (Kotlin)
- [ ] Call, SMS, contacts permissions + tool implementations
- [ ] Push-to-talk trigger (not wake-word — Android background restrictions
      make always-on listening unreliable and battery-hungry)
- [ ] Remap Bixby button or set Oli as default assistant app
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
- [ ] Infra hardening: move from local memory store to DynamoDB, orchestrator
      from local CLI to actual Lambda + API Gateway deployment via Terraform

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

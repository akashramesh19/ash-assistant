# Oli

## What this is

Oli is a personal voice assistant, built and used by one person (Akash), not a
product for sale. It is not a generic Alexa clone: the differentiator is
**personalization** (persistent memory of active projects, context, and
phrasing habits) and a **personality layer** (dry, deadpan, precise — never
robotic, never falsely enthusiastic) sitting on top of real LLM reasoning
rather than fixed intent matching.

The name "Oli" has no special meaning attached — it was picked at the end of
a long naming detour and locked in on the spot. Nothing more to read into it.

This project doubles as portfolio work for Akash's software engineering job
search in Australia (junior/graduate full-stack + technical roles). The AWS
pieces reinforce AWS Developer Associate (DVA-C02) cert prep. Keep that
context in mind: code quality, clear commit history, and defensible
architecture choices matter here beyond just "does it work."

## Core design principle: execution vs. personality are separate layers

Never let these blur:
- **Execution layer** — parses the command, resolves tool calls, checks
  confirmation logic. Stays literal and correct no matter how the command was
  phrased. A destructive action (delete, overwrite) always requires an
  explicit confirmation step, regardless of tone.
- **Personality layer** — once the action is decided/executed, the response
  wording goes through Oli's voice (system prompt in `orchestrator/src/handler.py`).
  Wit lives here only. It never changes what actually got executed.

## Architecture (current target)

```
Laptop agent ──┐
Phone agent  ──┼──> Orchestrator (AWS Lambda + API Gateway) ──> Claude API (reasoning)
Pi agent     ──┘                        │
                                         └──> DynamoDB (memory + project/task state)
```

One orchestrator, multiple thin device clients. Each device only exposes the
tools relevant to it (laptop: files/git; phone: calls/texts/contacts; Pi:
voice, replaces the bedroom Alexa). The orchestrator is the only thing that
talks to Claude and to DynamoDB — devices never call either directly.

## Repo layout

```
oli/
├── orchestrator/        # the brain — deployed to AWS
│   ├── src/
│   │   ├── tools/        # one file per tool + registry in __init__.py
│   │   └── handler.py    # Claude tool-calling loop; Lambda entry point later
│   └── infra/             # Terraform — Lambda, API Gateway, DynamoDB, IAM
├── pc-agent/             # runs locally on the laptop, later redeployed to the Pi
│   ├── listener/           # wake word / push-to-talk
│   ├── stt/ tts/
│   └── tools/              # move_file.py, create_folder.py, git_ops.py
├── phone-agent/          # native Android (Kotlin)
│   └── tools/              # call.kt, sms.kt, contacts.kt
├── docs/
│   ├── plan.md            # phased roadmap, current status
│   └── decisions.md       # architecture decision log
└── CLAUDE.md             # this file
```

## Tech stack (and why — don't swap without updating decisions.md)

| Component | Choice | Why |
|---|---|---|
| Orchestrator runtime | Python | Most mature ecosystem for LLM tool-calling glue |
| LLM | Claude API (`claude-sonnet-5`) | Already the daily driver; consistent tool-calling |
| STT | Whisper, local | Free, laptop has spare CPU |
| TTS | Piper (local) for v1, ElevenLabs optional later | Zero cost to start |
| Wake trigger | Push-to-talk on phone; wake word on laptop/Pi | Android background restrictions make always-on listening unreliable |
| Phone app | Kotlin, native Android | Call/SMS/contacts permissions are more predictable native than via Flutter |
| IaC | Terraform | Reusable, versioned, overlaps with AWS cert material |
| Memory/state | DynamoDB | Serverless, scales to zero, free-tier friendly |
| Infra | Lambda + API Gateway | Pay-per-invocation; sits idle at $0 when nobody's talking to Oli |

## Phases

See `docs/plan.md` for the full roadmap with dates. Summary:

1. **Laptop agent** — orchestrator + 2–3 tools, push-to-talk, STT/TTS, personality
   and basic memory built in from the start (not bolted on later). This phase
   is the strict deadline; everything after it is paced off it, not the
   reverse.
2. **Phone agent** — native Android, call/text/contacts, Bixby button
   remapped or set as default assistant.
3. **Raspberry Pi** — same pc-agent code redeployed onto a Pi with mic +
   speaker, retiring the bedroom Alexa.
4. **Iterate** — no fixed date. Revisited once phases 1–3 are in daily use.
   Includes the fine-tuning idea (LoRA/QLoRA on an open model using real
   usage logs) — deliberately not scheduled, since it depends on data that
   doesn't exist yet.

## How to work with Akash on this

- **Hand him the smallest next concrete action, not the full scope.** He
  fixates on scope and it stalls him from starting. Don't lecture him on this
  or call it a technique — just do it: one file, one function, one command
  to run next.
- **Direct, unfiltered feedback over reassurance.** If an approach is weak,
  say so plainly and say why.
- **Keep the execution/personality separation intact in every change** — see
  above. This is the one architectural rule not to compromise on for
  convenience.
- Don't add scope beyond what's asked. This project already had one long
  naming detour — resist re-opening settled decisions (the name is Oli, full
  stop) unless he raises it again himself.

## Current status

Phase 1 in progress. Working so far:
- `orchestrator/src/tools/` — tool registry pattern (`__init__.py` + one file
  per tool), `get_time.py` as the first proof-of-concept tool.
- `orchestrator/src/handler.py` — local CLI loop: takes text input, runs the
  Claude tool-calling loop, replies in Oli's voice. Not yet deployed to
  Lambda. Not yet wired to real STT/TTS or DynamoDB memory.

Not started: personalization/memory design (see `docs/decisions.md` for the
intended design), personality persona spec as its own versioned file (system
prompt in `handler.py` is a first draft, not final), pc-agent listener/stt/tts,
phone-agent, infra/Terraform, Pi deployment.

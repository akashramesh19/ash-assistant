# Decisions

Architecture decision log. Add a new entry when a real choice gets made;
don't relitigate a closed one without a new reason.

## Orchestrator runtime: Python

Chosen over Java/Spring Boot (Akash's stronger language) because the
tool-calling glue code changes weekly during early development, and Python's
LLM tooling/examples are the most mature. Not a "learn a new stack" move —
narrow, deliberate trade-off for this one component.

## LLM: Claude API

Already the daily driver for this whole build. Consistent tool-calling
behavior matters more than shopping model providers at this stage.

## Infra: Lambda + API Gateway, not EC2

Pay-per-invocation. An always-on EC2 box would cost more and sit idle almost
all day for a single-user assistant. Scales to zero between uses.

## Memory/state: DynamoDB (phase 1+ target), local file/SQLite for now

On-demand pricing matches bursty, low-volume personal use better than RDS's
flat instance cost. Deferred to a local store in phase 1 dev to avoid
standing up AWS infra before there's anything worth persisting.

## IaC: Terraform

Reusable and versioned; deliberately overlaps with AWS Developer Associate
cert material instead of one-off console clicking.

## Phone app: native Kotlin, not Flutter

Call/SMS/contacts permissions and background behavior are more predictable
native than cross-platform. This is the one place native beats "write once."

## Wake trigger: push-to-talk on phone, wake word on laptop/Pi

Always-on listening fights Android's Doze/background restrictions and drains
battery. No such constraint on laptop or Pi, so wake word is fine there.

## Wake word: use the full name, not a shortened trigger

One-syllable or overly common trigger words (tested: "Vaan", "Ash") produce
too many false positives/misses for wake-word engines (Porcupine,
openWakeWord) — not enough distinct audio pattern, or the word occurs too
often in normal speech. Use "Hey Oli" as the tested wake phrase, same pattern
Siri/Alexa/Google use for their own short names.

## Personalization design

Not a bolt-on. Before every request reaches Claude, the orchestrator runs a
context lookup (active project, standing facts, recent commands) and folds
it into the prompt. Every completed action writes its outcome back. This is
the actual thing that makes Oli different from Alexa — Alexa has no
equivalent lookup step, reasoning alone doesn't create personalization.

## Personality layer: separate from execution, always

Execution (tool calls, confirmation logic) stays literal and correct
regardless of phrasing or tone. Personality (dry, deadpan, wry) only shapes
how the *result* gets said back, generated in a separate pass after the
action is already decided. Never let wit affect what actually executes —
this is the one rule not to compromise for convenience.

## Naming: Oli

Long detour through Tamil, Sanskrit, Greek, Finnish, and English sky-themed
names (Raki, Raju, Mugil, Vaanoli, Vaani, Caelum, Zenith, others) — most
collided with existing apps/products/films. Landed on Oli, acknowledged
collision with an existing GitHub personal-assistant project of the same
name, and locked it anyway since this isn't going to be sold or trademarked.
Not reopening this again without a real reason.

## Fine-tuning: deliberately not scheduled

The idea (LoRA/QLoRA on an open model, using real usage logs, for routine
command routing while Claude stays the brain for anything non-routine) is
sound but depends on data that doesn't exist until phases 1–3 have real
daily usage behind them. Training a foundation model from scratch was
explicitly ruled out early — not achievable at individual scale, full stop.

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

One-syllable or overly common trigger words used bare, with no "Hey" prefix
(tested: "Vaan", "Ash") produce too many false positives/misses for
wake-word engines (Porcupine, openWakeWord) — not enough distinct audio
pattern, or the word occurs too often in normal speech. Fix: always use the
"Hey <name>" pattern, same as Siri/Alexa/Google do for their own short
names — never the bare name alone.

This was originally read as ruling out "Ash" as a name entirely, but that
overstated the finding: the bare-word test rejected *unprefixed* "Ash," not
"Hey Ash." Per the "Naming: Ash" entry below, the name changed anyway, and
the wake phrase is now **"Hey Ash"** — same mitigation pattern that made
"Hey Oli" work, plus the household context (Tamil is the primary spoken
language at home) meaningfully reduces how often the English word "ash"
shows up in ambient speech, which was the other half of the original
false-positive concern. Still, this is a claim to verify empirically the
same way "Vaan"/"Ash" were originally tested, not assumed to be true — check
the real false-positive rate once trained, per `pc-agent/listener/TRAINING.md`.

## Personalization design

Not a bolt-on. Before every request reaches Claude, the orchestrator runs a
context lookup (active project, standing facts, recent commands) and folds
it into the prompt. Every completed action writes its outcome back. This is
the actual thing that makes Ash different from Alexa — Alexa has no
equivalent lookup step, reasoning alone doesn't create personalization.

## Personality layer: separate from execution, always

Execution (tool calls, confirmation logic) stays literal and correct
regardless of phrasing or tone. Personality (dry, deadpan, wry) only shapes
how the *result* gets said back, generated in a separate pass after the
action is already decided. Never let wit affect what actually executes —
this is the one rule not to compromise for convenience.

## Naming: Ash (previously Oli)

Long detour through Tamil, Sanskrit, Greek, Finnish, and English sky-themed
names (Raki, Raju, Mugil, Vaanoli, Vaani, Caelum, Zenith, others) — most
collided with existing apps/products/films. Landed on Oli, acknowledged
collision with an existing GitHub personal-assistant project of the same
name, and locked it in anyway.

Reopened later and renamed to **Ash**, short for Akash — a real reason, not
a whim: this is a personal project built for one person, and the name comes
directly from that person rather than being arbitrary. The rename also
touches the "Wake word" decision above, since "Ash" was a name tested and
rejected during the original wake-word round — see that entry for why the
rename doesn't actually contradict that earlier test. Repo and folder
renamed to match (`oli-assistant` → `ash-assistant`). Not reopening the name
again without a real reason, same as before.

## Memory model: graph-based, deferred to Phase 4

Phase 1's flat JSON store (`active_project` / `standing_facts` /
`recent_commands`) is deliberately simple and stays that way through phase 1
— it unblocks the tools/wake-word/STT/TTS work still needed before the
2026-10-25 deadline, and a flat store is genuinely fine at this data volume.

But the long-term intent is for Ash's memory to be a graph, not a flat
store: nodes for people, projects, tasks, and standing facts, edges for how
they relate. Personalization is the actual differentiator for this project
(see "Personalization design" above), and personalization gets more honest
the more it can represent relationships ("this fact is about this project,
raised by this person") instead of independent lists. A flat key-value store
stops being able to express that as memory grows; a graph is built for
exactly that query shape.

Deliberately not building this now — logging it here so it isn't
relitigated as a surprise later, and so Phase 4's "infra hardening" line
means something specific: replace the flat store with a graph model once
real usage data exists to design the schema against, not before. This also
changes the AWS-side target: DynamoDB alone doesn't do graph traversal
natively (would need an adjacency-list table design, or a dedicated graph
store like Neptune) — revisit the "Memory/state: DynamoDB" decision above
at that point rather than assuming it still holds unmodified.

## Fine-tuning: deliberately not scheduled

The idea (LoRA/QLoRA on an open model, using real usage logs, for routine
command routing while Claude stays the brain for anything non-routine) is
sound but depends on data that doesn't exist until phases 1–3 have real
daily usage behind them. Training a foundation model from scratch was
explicitly ruled out early — not achievable at individual scale, full stop.

## move_file: safety rules live in code, not the prompt

`move_file` is the first tool that changes things on disk, so its limits are
enforced in `orchestrator/src/tools/move_file.py` and hold whichever model is
calling it (Claude or Matilda), however the request was phrased:

- Only paths inside one allowed folder (`ASH_MOVE_ROOT`). Paths are resolved
  first, so `..` and symlinks that lead outside are rejected.
- Every move is confirmed by the user before anything changes. The model has
  no parameter that can skip or pre-answer the confirmation.
- Replacing an existing file needs a second, separate confirmation.
- No delete, no creating folders, no replacing folders, no moving symlinks.
- Every attempt, allowed or not, is appended to a JSONL log
  (`ASH_MOVE_LOG`, default `logs/move_file.jsonl`).

Why code and not the system prompt: a prompt rule is a request the model can
get wrong or be talked out of; a check in the tool can't be. This is the
execution/personality split applied to safety — Ash's voice only describes
what the tool actually did.

Known limits, accepted for a single-user local tool: the checks run just
before the move, so a path swapped in that instant could slip through; and
the confirmation is currently typed at the terminal (`console_confirm`), even
in the voice loop. Spoken confirmation can plug in through `set_confirmer`
and hasn't been built yet. Tested by typing and by voice against
`~/AshSandbox` on 2026-10-11.

# Notch app: design (iteration 1)

A native macOS app that lives at the MacBook's notch and shows Ash's state. It
draws and relays input only; the Python voice agent still does the listening,
thinking and speaking, so the Pi redeploy stays pure Python.

## Decisions

| Question | Decision |
|---|---|
| Always listening | Wake word only ("Hey Ash", local). Nothing is transcribed or sent until it fires. The orange mic dot is macOS's and stays on. |
| What it shows | Idle / listening / thinking / speaking, a reply preview that expands below the notch, Yes/No buttons for `move_file` confirmations (voice still works), crew-run progress and the "draft ready" notice. No typed input in iteration 1. |
| Which screen | The built-in notch, plus a small floating pill at the top centre of the main display (the external ultrawide has no notch). Follows display changes. |
| Who starts Python | The Swift app launches and supervises `voice_loop.py` as a child process and restarts it if it dies. |
| Toolchain | SwiftUI + AppKit as a SwiftPM package (`notch-app/`), built with `swift build`. Xcode is not installed and not needed. |

## Shape

```
┌─ notch-app (Swift) ──────────┐   Unix socket    ┌─ pc-agent (Python) ─────────┐
│ NSPanel at the notch / pill  │ ◄── events ────  │ voice_loop + ui_bridge.py   │
│ states, reply, Yes/No, crew  │ ──── answers ──► │ wake word, Whisper, Piper   │
│ supervises the agent process │                  │ orchestrator (unchanged)    │
└──────────────────────────────┘                  └─────────────────────────────┘
```

## Protocol

Newline-delimited JSON over a Unix domain socket at `~/.ash/ash.sock`, mode
0600 (owner only: another local process must not be able to answer a
confirmation). The Python side listens; the app connects and reconnects.

Python to app:

| type | fields | meaning |
|---|---|---|
| `state` | `state`: idle / listening / thinking / speaking | what Ash is doing |
| `heard` | `text` | what Whisper heard |
| `reply` | `text` | Ash's reply (also spoken) |
| `confirm` | `id`, `question` | a destructive action is waiting for yes/no |
| `confirm_closed` | `id`, `answer`: yes / no / timeout | how it was settled (voice or click) |
| `crew` | `run_id`, `status`, `stage`, `message` | crew progress and the finished/failed notice |
| `error` | `message` | something broke |

App to Python:

| type | fields | meaning |
|---|---|---|
| `answer` | `id`, `answer`: yes / no | a click on Yes or No |

Confirmation rules (execution layer, enforced in Python, not in the UI):
- An answer counts only if its `id` matches the confirmation currently
  pending. Stale, repeated or unknown ids are ignored.
- The first clear answer wins. A click while the question is spoken, before
  any transcript, counts. After a listen, if the click and the transcript are
  both clear and they disagree, the answer is no. An empty or unclear
  transcript leaves the click in force. A later click on the same id is dropped.
- No answer in time is a no. A dead or disconnected UI never counts as yes.
- The confirmation text is shown exactly as the tool wrote it, with no
  persona jokes (see `persona.md`).

The pill, separate from those rules:
- A crew event during a confirmation is stored. The question, the id, and the
  buttons stay until the answer. The stored line is shown after that turn's
  reply has lingered.
- A `running` line stays until the next crew event. `idle` leaves it up, and
  when a reply's linger ends the current running line comes back. `done`,
  `done-unreviewed`, and `failed` linger like a reply and are shown once.

## Window

- A borderless, non-activating `NSPanel` above the menu bar, on all Spaces and
  over full-screen apps; it never takes focus. Accessory app (no Dock icon).
- Notch geometry from `NSScreen.safeAreaInsets` and the auxiliary top areas
  (notch width = screen width minus both). The pill is black and rounded, grows
  down from the notch, and expands for a reply or a confirmation.
- Idle is nearly invisible. The panel ignores mouse events unless a
  confirmation is open. While one is open the panel shrinks to the pill, top
  edge fixed, so a click beside it reaches the menu bar.
- A menu bar item offers Restart agent, Show log and Quit.

## Build order

1. Pill window with fixed states and a debug way to switch between them; check
   placement on the notch and on the external display.
2. `ui_bridge.py` and the Swift client: real states from `voice_loop.py`.
3. Reply preview, Yes/No buttons, and the first-answer-wins race with the
   spoken confirmer.
4. Crew progress and the "draft ready" notice through the same socket.
5. Supervisor: launch, restart on crash, menu bar item.

Then one end-to-end test of everything (routing, spoken confirmer, crew, notch)
and a list of what is wrong, for iteration 2.

## Known risks

- **Microphone permission.** The mic permission belongs to the app that
  started the process. Run the notch app from Terminal for now (Terminal
  already has the permission, as the voice loop does). A packaged `.app` would
  need an Info.plist with a microphone usage string; leave that for later.
- **No screenshot check from the tool side.** Window placement has to be
  judged by eye on the real displays.
- **Spoken notifications play while the wake-word mic is open** (see
  `RESEARCH-NOTES.md`); watch for false triggers in the end-to-end test.

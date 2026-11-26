"""Voice loop: "Hey Ash" -> record a question -> Whisper -> orchestrator -> Piper.

Run from the repo root: .venv/bin/python pc-agent/voice_loop.py
Needs ANTHROPIC_API_KEY in the environment. The typed loop
(orchestrator/src/handler.py) is unaffected by this.

move_file confirmations are spoken and answered by voice (pc-agent/spoken_confirm.py).

Every turn prints what Whisper heard, any tool called (with its result), and
the reply, so failures show which stage broke.
"""

import sys
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "orchestrator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "pc-agent"))

from crew.notify import set_notifier  # noqa: E402
from handler import create_responder  # noqa: E402
from providers.base import ProviderConfigError, ProviderError  # noqa: E402
from listener.wake_word import listen  # noqa: E402
from ui_bridge import UIBridge  # noqa: E402
from spoken_confirm import LISTEN_SECONDS as CONFIRM_SECONDS, make_spoken_confirmer  # noqa: E402
from tools import move_file  # noqa: E402
import stt.whisper_stt as whisper_stt  # noqa: E402
from tts.piper_tts import speak  # noqa: E402

RECORD_SECONDS = 5.0  # how long to wait for speech to start; recording ends on a pause


def listen_for_question() -> str:
    """Question turn. The wait for speech to start is short; the take can run to 20s."""
    return whisper_stt.listen_and_transcribe(RECORD_SECONDS)


def listen_for_confirmation() -> str:
    """Yes/no. Both the wait and the hard cap are CONFIRM_SECONDS; a pause can end it sooner."""
    return whisper_stt.listen_and_transcribe(CONFIRM_SECONDS, max_seconds=CONFIRM_SECONDS)


def handle_turn(
    respond,
    transcribe=listen_for_question,
    say=speak,
    log=print,
    emit=lambda event: None,
) -> None:
    """One wake-word-to-reply turn. The audio functions are parameters so the
    transcript -> handler path can be tested without a mic or speakers. emit
    sends state events to the notch app (a no-op when there is none)."""
    state = lambda name: emit({"type": "state", "state": name})  # noqa: E731
    log("[wake] Hey Ash detected. Speak now...")
    state("listening")
    try:
        t0 = time.perf_counter()
        whisper_stt.last_capture = None
        transcript = transcribe()
        t_heard = time.perf_counter()
        info = whisper_stt.last_capture
        detail = f" {whisper_stt.format_capture(info)}" if info else ""
        log(f"[whisper] heard: {transcript!r}{detail} (listen + transcribe {t_heard - t0:.1f}s)")
        if not transcript:
            log("[skip] empty transcript, nothing to send")
            return
        emit({"type": "heard", "text": transcript})

        def log_tool(name, tool_input, result):
            log(f"[tool] {name}({tool_input}) -> {result}")

        state("thinking")
        try:
            reply = respond(transcript, on_tool_call=log_tool)
        except ProviderError as error:
            log(f"[error] model call failed: {error}")
            emit({"type": "error", "message": str(error)})
            return
        t_reply = time.perf_counter()
        log(f"[reply] {reply!r} (model {t_reply - t_heard:.1f}s)")
        if reply:
            emit({"type": "reply", "text": reply})
            say(reply)
            log(f"[timing] speak {time.perf_counter() - t_reply:.1f}s; model interval {t_reply - t_heard:.1f}s")
    finally:
        state("idle")


def make_announcer(say, audio_lock, log=print):
    """Notifier for finished crew runs: speaks the message, but only when no
    turn is using the speakers or mic, so it never talks over a conversation.
    It waits for the current turn to finish."""

    def announce(message: str, detail: str = "") -> None:
        log(f"[crew] {message}" + (f" {detail}" if detail else ""))
        with audio_lock:
            say(message)

    return announce


def main() -> None:
    try:
        respond = create_responder()
    except ProviderConfigError as error:
        print(f"error: {error}")
        return
    # move_file asks "go ahead?" out loud and listens for the answer, instead of
    # waiting for a typed y/N. Anything but a clear yes is a no.
    move_file.set_confirmer(
        make_spoken_confirmer(say=speak, listen=listen_for_confirmation)
    )
    audio_lock = threading.Lock()  # one thing at a time on the speakers and mic

    bridge = UIBridge()
    try:
        bridge.start()
    except RuntimeError as error:
        print(f"error: {error}")
        return
    bridge.emit({"type": "state", "state": "idle"})

    def locked_turn():
        with audio_lock:
            handle_turn(respond, emit=bridge.emit)

    set_notifier(make_announcer(speak, audio_lock))
    try:
        listen(on_wake_word=locked_turn)
    except KeyboardInterrupt:
        print()
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()

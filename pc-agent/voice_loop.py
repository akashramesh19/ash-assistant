"""Voice loop: "Hey Ash" -> record a question -> Whisper -> orchestrator -> Piper.

Run from the repo root: .venv/bin/python pc-agent/voice_loop.py
Needs ANTHROPIC_API_KEY in the environment. The typed loop
(orchestrator/src/handler.py) is unaffected by this.

Every turn prints what Whisper heard, any tool called (with its result), and
the reply, so failures show which stage broke.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "orchestrator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "pc-agent"))

from handler import MissingApiKeyError, create_responder  # noqa: E402
from providers.base import ProviderError  # noqa: E402
from listener.wake_word import listen  # noqa: E402
from stt.whisper_stt import listen_and_transcribe  # noqa: E402
from tts.piper_tts import speak  # noqa: E402

RECORD_SECONDS = 5.0


def handle_turn(
    respond,
    transcribe=lambda: listen_and_transcribe(RECORD_SECONDS),
    say=speak,
    log=print,
) -> None:
    """One wake-word-to-reply turn. The audio functions are parameters so the
    transcript -> handler path can be tested without a mic or speakers."""
    log("[wake] Hey Ash detected. Speak now...")
    transcript = transcribe()
    log(f"[whisper] heard: {transcript!r}")
    if not transcript:
        log("[skip] empty transcript, nothing to send")
        return

    def log_tool(name, tool_input, result):
        log(f"[tool] {name}({tool_input}) -> {result}")

    try:
        reply = respond(transcript, on_tool_call=log_tool)
    except ProviderError as error:
        log(f"[error] model call failed: {error}")
        return
    log(f"[reply] {reply!r}")
    if reply:
        say(reply)


def main() -> None:
    try:
        respond = create_responder()
    except MissingApiKeyError as error:
        print(f"error: {error}")
        return
    try:
        listen(on_wake_word=lambda: handle_turn(respond))
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()

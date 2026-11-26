"""Spoken yes/no confirmation for tools that need the user's go-ahead (move_file).

Fails closed: only an unmistakable yes counts as yes. Silence, noise, a Whisper
hallucination ("Thank you."), a long or mixed answer, a mic error, a dropped
UI: all are no. A click counts only when its id is the question still open.
The click callback stores that answer and nothing else — it must not take the
audio lock or call say/listen, because it runs on the bridge thread while the
turn holds the mic. The audio functions are parameters so this is testable
without a mic or speakers.
"""

import re
import threading
import uuid
from typing import Callable

YES_WORDS = {"yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed", "okay", "ok"}
YES_PHRASES = ("go ahead", "do it", "go for it")
NO_WORDS = {"no", "nope", "nah", "cancel", "stop", "wait", "negative", "dont", "don't"}
NO_PHRASES = ("do not", "hold on", "not yet")
MAX_ANSWER_WORDS = 6  # longer than this is a sentence, not an answer

LISTEN_SECONDS = 4.0
MAX_ATTEMPTS = 2


def parse_answer(transcript: str) -> bool | None:
    """True for a clear yes, False for a clear no, None if unclear. No beats yes."""
    text = re.sub(r"[^a-z' ]", " ", (transcript or "").lower().replace("’", "'"))
    words = text.split()
    if not words or len(words) > MAX_ANSWER_WORDS:
        return None
    spaced = " " + " ".join(words) + " "
    if set(words) & NO_WORDS or any(f" {p} " in spaced for p in NO_PHRASES):
        return False
    if set(words) & YES_WORDS or any(f" {p} " in spaced for p in YES_PHRASES):
        return True
    return None


def speakable(question: str) -> str:
    """Make a tool's question read naturally aloud: no quote marks, and file
    paths spoken as 'Archive slash report dot txt'."""
    text = question.replace("'", "").replace("’", "")
    text = re.sub(r"(?<=\w)\.(?=\w)", " dot ", text)
    return text.replace("/", " slash ")


def make_spoken_confirmer(
    say: Callable[[str], None],
    listen: Callable[[], str],
    log: Callable[[str], None] = print,
    max_attempts: int = MAX_ATTEMPTS,
    emit: Callable[[dict], None] = lambda event: None,
) -> Callable[[str], bool]:
    """Returns confirm(question) -> bool, for move_file.set_confirmer().

    confirm.on_answer(id, "yes"|"no") is the only way in for a click. Each
    call to confirm uses a new id, so a yes for the move cannot answer the
    overwrite prompt that follows it.
    """
    pending = {"id": None, "click": None}
    lock = threading.Lock()

    def on_answer(confirm_id: str, answer: str) -> None:
        # Store only. The caller is the bridge thread and must not touch audio.
        if confirm_id == "debug" or answer not in ("yes", "no"):
            return
        with lock:
            if pending["id"] is None or confirm_id != pending["id"] or pending["click"] is not None:
                return
            pending["click"] = answer == "yes"

    def take_click() -> bool | None:
        with lock:
            click = pending["click"]
            pending["click"] = None
            return click

    def confirm(question: str) -> bool:
        confirm_id = uuid.uuid4().hex
        settled = "no"
        try:
            with lock:
                pending["id"] = confirm_id
                pending["click"] = None
            # The screen gets the tool's question, quotes and path included.
            # speakable() is only what is said aloud.
            emit({"type": "confirm", "id": confirm_id, "question": question})
            say(speakable(question))
            click = take_click()
            if click is not None:
                log(f"[confirm] click {'yes' if click else 'no'}")
                settled = "yes" if click else "no"
                return click
            for attempt in range(1, max_attempts + 1):
                heard = listen()
                # Both are in hand now, so this is not "whichever came first".
                # A clear disagreement is a no. Empty or unclear speech leaves
                # the click in force. A click taken before this listen already
                # returned above, because there was no transcript yet.
                click = take_click()
                answer = parse_answer(heard)
                if click is not None and answer is not None and click != answer:
                    log(f"[confirm] click {'yes' if click else 'no'} disagrees with {heard!r}, treating as no")
                    settled = "no"
                    return False
                if click is not None:
                    log(f"[confirm] click {'yes' if click else 'no'}")
                    settled = "yes" if click else "no"
                    return click
                log(f"[confirm] heard {heard!r} -> {'yes' if answer else 'no' if answer is False else 'unclear'}")
                if answer is not None:
                    settled = "yes" if answer else "no"
                    return answer
                if attempt < max_attempts:
                    say("Sorry, was that a yes or a no?")
                    click = take_click()
                    if click is not None:
                        log(f"[confirm] click {'yes' if click else 'no'}")
                        settled = "yes" if click else "no"
                        return click
            say("I didn't catch a clear yes, so I'll leave it.")
            settled = "timeout"
            return False
        except Exception as error:  # a mic or speaker fault must never count as yes
            log(f"[confirm] error, treating as no: {type(error).__name__}: {error}")
            settled = "no"
            return False
        finally:
            with lock:
                pending["id"] = None
                pending["click"] = None
            emit({"type": "confirm_closed", "id": confirm_id, "answer": settled})

    confirm.on_answer = on_answer
    return confirm

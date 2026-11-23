"""Spoken yes/no confirmation for tools that need the user's go-ahead (move_file).

Fails closed: only an unmistakable yes counts as yes. Silence, noise, a Whisper
hallucination ("Thank you."), a long or mixed answer, a mic error: all are no.
The audio functions are parameters so this is testable without a mic or speakers.
"""

import re
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
) -> Callable[[str], bool]:
    """Returns confirm(question) -> bool, for move_file.set_confirmer()."""

    def confirm(question: str) -> bool:
        try:
            say(speakable(question))
            for attempt in range(1, max_attempts + 1):
                heard = listen()
                answer = parse_answer(heard)
                log(f"[confirm] heard {heard!r} -> {'yes' if answer else 'no' if answer is False else 'unclear'}")
                if answer is not None:
                    return answer
                if attempt < max_attempts:
                    say("Sorry, was that a yes or a no?")
            say("I didn't catch a clear yes, so I'll leave it.")
            return False
        except Exception as error:  # a mic or speaker fault must never count as yes
            log(f"[confirm] error, treating as no: {type(error).__name__}: {error}")
            return False

    return confirm

"""Tell the user when a background crew run finishes.

The message is chosen by code from the run's outcome, not by a model, so it is
instant, costs no tokens, and cannot claim more than what happened. Whoever
owns the interface (the typed CLI, the voice loop) registers a notifier; with
none registered, nothing happens and the result is still readable with
crew_status.
"""

from typing import Callable

_notifier: Callable[[str, str], None] | None = None


def set_notifier(notifier: Callable[[str, str], None] | None) -> None:
    """notifier(message, detail): message is for speaking, detail for the screen."""
    global _notifier
    _notifier = notifier


def completion_message(meta: dict, final_path: str = "") -> tuple[str, str]:
    """(message, detail) for a finished run, from its run.json."""
    status = meta.get("status")
    if status == "failed":
        return f"The draft failed at the {meta.get('failed_stage', 'start')} stage, Sir.", meta.get("error", "")
    message = "Your draft is ready, Sir."
    if status == "done-unreviewed":
        message += " The review failed, so it's unreviewed."
    if meta.get("unresearched"):
        message += " It's unresearched."
    elif meta.get("warnings"):
        message += " There are warnings."
    return message, final_path


def notify(meta: dict, final_path: str = "") -> None:
    if _notifier is None:
        return
    try:
        _notifier(*completion_message(meta, final_path))
    except Exception as error:  # a broken speaker must not break the run
        print(f"[crew] notification failed: {type(error).__name__}: {error}")

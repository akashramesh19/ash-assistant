"""Tell the user when a background crew run finishes.

The message is chosen by code from the run's outcome, not by a model, so it is
instant, costs no tokens, and cannot claim more than what happened. Whoever
owns the interface (the typed CLI, the voice loop) registers a notifier; with
none registered, nothing happens and the result is still readable with
crew_status.

A separate progress callback receives pill events: one per stage, then one
when the run finishes. Those events are not spoken. With none registered,
they are dropped.
"""

from typing import Callable

_notifier: Callable[[str, str], None] | None = None
_progress: Callable[[dict], None] | None = None


def set_notifier(notifier: Callable[[str, str], None] | None) -> None:
    """notifier(message, detail): message is for speaking, detail for the screen."""
    global _notifier
    _notifier = notifier


def set_progress(callback: Callable[[dict], None] | None) -> None:
    """callback(event): a crew pill event. Not spoken."""
    global _progress
    _progress = callback


def stage_line(role: str) -> str:
    """A fixed line for the pill while a stage is running. Not a model sentence."""
    name = (role or "").strip()
    if not name:
        return "The crew is working."
    return f"{name[:1].upper()}{name[1:]} is working."


def report(run_id: str, status: str, stage: str, message: str) -> None:
    """Hand one crew event to the pill. A missing or broken callback is ignored."""
    if _progress is None:
        return
    try:
        _progress({
            "type": "crew",
            "run_id": run_id,
            "status": status,
            "stage": stage,
            "message": message,
        })
    except Exception as error:  # a broken pill must not break the run or skip the spoken notice
        print(f"[crew] progress failed: {type(error).__name__}: {error}")


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
    """Show the outcome on the pill, then speak it. The pill does not wait
    for the mic. Speech still goes through the registered notifier."""
    message, detail = completion_message(meta, final_path)
    report(
        str(meta.get("id") or ""),
        str(meta.get("status") or ""),
        str(meta.get("failed_stage") or meta.get("current_stage") or ""),
        message,
    )
    if _notifier is None:
        return
    try:
        _notifier(message, detail)
    except Exception as error:  # a broken speaker must not break the run
        print(f"[crew] notification failed: {type(error).__name__}: {error}")

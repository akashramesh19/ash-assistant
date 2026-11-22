"""Move a file or folder inside one allowed folder, with the user's say-so.

The safety rules live here, in code, not in the prompt, so they hold whichever
model calls the tool:
- Only paths inside ASH_MOVE_ROOT. Every path is resolved (so `..` and
  symlinks are followed) and rejected if it lands outside.
- The user confirms every move before anything changes. The model has no
  parameter that can skip or pre-answer this.
- Replacing an existing file needs a second, separate confirmation.
- No delete, no creating folders, no replacing folders, no moving symlinks.
- No renaming: the destination must be an existing folder, or a path that keeps
  the source's file name (e.g. Archive/report.txt). A destination that doesn't
  exist and would give the file a new name is refused, not guessed at.
- Every attempt, allowed or not, is appended to a JSONL action log.

Known limit: the checks happen just before the move, so a path swapped in that
instant could slip through. Fine for a single-user local tool; not for a
shared machine.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

TOOL_DEFINITION = {
    "name": "move_file",
    "description": (
        "Move a file or folder to another place inside Ash's allowed folder. "
        "Names are relative to that folder, e.g. source 'report.txt', "
        "destination 'Archive' (an existing folder) or 'Archive/report.txt'. "
        "The destination must be an existing folder or keep the file's name; "
        "it cannot rename, delete anything or create folders. "
        "The user is asked to confirm before anything moves; if they decline, "
        "nothing moves."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "File or folder to move, relative to the allowed folder."},
            "destination": {
                "type": "string",
                "description": "Existing folder to move it into, or a full path that keeps the file's name.",
            },
        },
        "required": ["source", "destination"],
    },
}

DEFAULT_LOG = Path(__file__).resolve().parents[3] / "logs" / "move_file.jsonl"


def console_confirm(question: str) -> bool:
    """Ask on the terminal. Anything but an explicit yes (including no input) is no."""
    try:
        answer = input(f"{question} [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


_confirmer = console_confirm


def set_confirmer(confirmer) -> None:
    """Swap how the user is asked (e.g. spoken confirmation for the voice loop)."""
    global _confirmer
    _confirmer = confirmer


class _Rejected(Exception):
    pass


def _log(record: dict) -> None:
    path = Path(os.environ.get("ASH_MOVE_LOG") or DEFAULT_LOG)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamped = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **record}
    with path.open("a") as file:
        file.write(json.dumps(stamped, ensure_ascii=False) + "\n")


def _inside(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def _within(raw: str, root: Path) -> tuple[Path, Path]:
    """(path as written, fully resolved path); the resolved one must be inside root."""
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if not _inside(resolved, root):
        raise _Rejected(f"'{raw}' is outside the allowed folder")
    return candidate, resolved


def _plan(source: str, destination: str, root: Path):
    source_path, source_resolved = _within(source, root)
    if source_path.is_symlink():
        raise _Rejected(f"'{source}' is a symlink; symlinks are not moved")
    if source_resolved == root:
        raise _Rejected("the allowed folder itself can't be moved")
    if not source_resolved.exists():
        raise _Rejected(f"'{source}' doesn't exist")

    _, dest_resolved = _within(destination, root)
    if dest_resolved.is_dir():
        target = dest_resolved / source_resolved.name
    else:
        target = dest_resolved
        if not target.parent.is_dir():
            raise _Rejected(f"the folder '{target.parent.relative_to(root)}' doesn't exist (move_file never creates folders)")
        if target.name != source_resolved.name:
            raise _Rejected(
                f"'{destination}' isn't an existing folder, and move_file doesn't rename files. "
                f"Name an existing folder, or a path that keeps the name '{source_resolved.name}'"
            )
    if not _inside(target.resolve(), root):
        raise _Rejected(f"'{destination}' is outside the allowed folder")
    if target == source_resolved:
        raise _Rejected("it's already there")
    if source_resolved in target.parents:
        raise _Rejected("can't move a folder into itself")
    if target.is_dir():
        raise _Rejected(f"'{target.relative_to(root)}' is an existing folder and won't be replaced")
    return source_resolved, target


def run(source: str = "", destination: str = "", **kwargs) -> str:
    requested = {"source": source, "destination": destination}
    root_setting = os.environ.get("ASH_MOVE_ROOT")
    if not root_setting:
        return "error: move_file isn't configured (ASH_MOVE_ROOT is not set)"
    root = Path(root_setting).expanduser().resolve()
    if not root.is_dir():
        _log({"outcome": "error", "requested": requested, "detail": "allowed folder missing"})
        return "error: the allowed folder doesn't exist"

    try:
        src, target = _plan(source, destination, root)
    except _Rejected as reason:
        _log({"outcome": "rejected", "requested": requested, "detail": str(reason)})
        return f"error: {reason}"

    shown = {"from": str(src.relative_to(root)), "to": str(target.relative_to(root))}

    if not _confirmer(f"Ash wants to move '{shown['from']}' to '{shown['to']}'. Go ahead?"):
        _log({"outcome": "denied", "requested": requested, **shown})
        return "Not moved: the user declined."

    overwriting = target.exists()
    if overwriting and not _confirmer(
        f"'{shown['to']}' already exists. Replace it with '{shown['from']}'? The existing file will be overwritten."
    ):
        _log({"outcome": "denied", "requested": requested, "detail": "overwrite declined", **shown})
        return "Not moved: the user declined to overwrite the existing file."

    try:
        os.replace(src, target) if overwriting else src.rename(target)
    except OSError as error:
        _log({"outcome": "error", "requested": requested, "detail": str(error), **shown})
        return f"error: couldn't move it ({error.strerror or error})"

    _log({"outcome": "overwritten" if overwriting else "moved", "requested": requested, **shown})
    return f"Moved '{shown['from']}' to '{shown['to']}'."

"""Start a document crew run in the background and return immediately.

Ash stays responsive: this tool only creates the run folder and starts a worker
thread. Progress and the finished document are read with crew_status. One run
at a time, since Matilda is on a usage-limited plan. The crew builds its own
provider instances, separate from the conversation's.
"""

import json
import threading

from crew.notify import notify, report, stage_line
from crew.runner import prepare_run, run_document_crew, _write_json
from providers import available_providers

MAX_TASK_CHARS = 4000

TOOL_DEFINITION = {
    "name": "run_crew",
    "description": (
        "Start a background crew run that drafts a document (spec, README, memo, post, report) "
        "from a task description. Returns at once with a run id; the work takes a minute or more. "
        "The result is saved as markdown in a sandbox folder. Use crew_status to check progress. "
        "Not for conversation or quick answers."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "What document to write, for whom, and any key points."},
        },
        "required": ["task"],
    },
}

_lock = threading.Lock()
_active = None  # (run id, thread) of the run in progress


def _worker(task: str, run_dir) -> None:
    def on_progress(role: str) -> None:
        report(run_dir.name, "running", role, stage_line(role))

    try:
        providers, skipped = available_providers()
        meta = run_document_crew(task, providers, run_dir, on_progress=on_progress)
    except Exception as error:  # the thread must never die silently
        meta = {**json.loads((run_dir / "run.json").read_text()), "status": "failed", "error": f"{type(error).__name__}: {error}"}
        _write_json(run_dir / "run.json", meta)
    notify(meta, str(run_dir / "final.md"))


def run(task: str = "", **kwargs) -> str:
    global _active
    task = (task or "").strip()
    if not task:
        return "error: no task given"
    if len(task) > MAX_TASK_CHARS:
        return f"error: task is too long ({len(task)} characters, limit {MAX_TASK_CHARS})"
    with _lock:
        if _active and _active[1].is_alive():
            return f"A crew run is already in progress (id {_active[0]}). Wait for it to finish."
        run_dir = prepare_run(task)
        thread = threading.Thread(target=_worker, args=(task, run_dir), daemon=True, name=f"crew-{run_dir.name}")
        _active = (run_dir.name, thread)
        thread.start()
    return f"Started crew run {run_dir.name}. It is running in the background."

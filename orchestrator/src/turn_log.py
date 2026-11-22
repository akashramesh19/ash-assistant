"""Optional per-turn JSONL log, enabled by setting ASH_TURN_LOG to a file path.

One line per turn: provider, prompt, reply, tool calls with arguments, latency
and any error. Only the model call is timed (see providers/base.py); typing and
pauses are not. It records no environment variables or keys.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


class TurnLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def write(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def turn_log_from_env() -> TurnLog | None:
    path = os.environ.get("ASH_TURN_LOG")
    return TurnLog(Path(path)) if path else None


def build_record(provider, prompt, result=None, error=None, elapsed_seconds=None) -> dict:
    def rounded(value):
        return None if value is None else round(value, 3)

    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provider": provider,
        "prompt": prompt,
        "reply": result.text if result else None,
        "tool_calls": [
            {"name": call.name, "arguments": call.arguments, "result": call.result[:500]}
            for call in (result.tool_calls if result else [])
        ],
        "latency": {
            "first_token_seconds": rounded(result.first_token_seconds) if result else None,
            "model_seconds": rounded(result.model_seconds) if result else None,
            "tool_seconds": rounded(result.tool_seconds) if result else None,
            "total_seconds": rounded(result.total_seconds if result else elapsed_seconds),
        },
        "error": error,
    }

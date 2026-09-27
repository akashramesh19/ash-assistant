import json
import shutil
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMORY_PATH = DATA_DIR / "memory.json"
MEMORY_TEMPLATE_PATH = DATA_DIR / "memory.example.json"


def _load_memory() -> dict:
    if not MEMORY_PATH.exists():
        shutil.copy(MEMORY_TEMPLATE_PATH, MEMORY_PATH)
    return json.loads(MEMORY_PATH.read_text())


def get_context() -> str:
    memory = _load_memory()

    lines = [f"Active project: {memory['active_project']}"]

    if memory["standing_facts"]:
        lines.append("Standing facts:")
        lines.extend(f"- {fact}" for fact in memory["standing_facts"])

    if memory["recent_commands"]:
        lines.append("Recent commands:")
        lines.extend(f"- {command}" for command in memory["recent_commands"])

    return "\n".join(lines)


def record_command(command: str) -> None:
    memory = _load_memory()
    memory["recent_commands"].append(command)
    memory["recent_commands"] = memory["recent_commands"][-10:]
    MEMORY_PATH.write_text(json.dumps(memory, indent=2) + "\n")

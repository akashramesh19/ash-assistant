"""Voice-loop settings. Each can be overridden with an environment variable
so tuning doesn't need a code edit."""

import os
from pathlib import Path

PC_AGENT_DIR = Path(__file__).resolve().parent

WAKE_MODEL_PATH = Path(
    os.environ.get("ASH_WAKE_MODEL", PC_AGENT_DIR / "listener" / "models" / "hey_ash.onnx")
)

# Score (0-1) the wake word model must exceed to count as "Hey Ash".
# Higher = fewer false triggers, more missed ones.
WAKE_THRESHOLD = float(os.environ.get("ASH_WAKE_THRESHOLD", "0.5"))

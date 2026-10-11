"""Mic check for the "Hey Ash" model: prints the live score so you can pick a
threshold. Say "Hey Ash" a few times, then say unrelated things and see what
scores they get.

Run: .venv/bin/python pc-agent/listener/score_check.py
Threshold comes from pc-agent/config.py (override with ASH_WAKE_THRESHOLD).
"""

import sys
from pathlib import Path

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import WAKE_MODEL_PATH, WAKE_THRESHOLD  # noqa: E402

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80ms at 16kHz, openWakeWord's expected frame size
SHOW_FLOOR = 0.05  # don't print near-zero scores


def main() -> None:
    model = Model(wakeword_models=[str(WAKE_MODEL_PATH)], inference_framework="onnx")
    peak = 0.0
    print(f"Model: {WAKE_MODEL_PATH.name}  threshold: {WAKE_THRESHOLD}")
    print("Say 'Hey Ash'. Ctrl+C to stop.\n")

    with sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK_SAMPLES
    ) as stream:
        try:
            while True:
                chunk, _ = stream.read(CHUNK_SAMPLES)
                scores = model.predict(np.squeeze(chunk))
                score = max(scores.values())
                peak = max(peak, score)
                if score >= SHOW_FLOOR:
                    bar = "#" * int(score * 40)
                    mark = "  <-- WAKE" if score > WAKE_THRESHOLD else ""
                    print(f"{score:5.2f} {bar}{mark}")
        except KeyboardInterrupt:
            print(f"\nPeak score this session: {peak:.2f}")


if __name__ == "__main__":
    main()

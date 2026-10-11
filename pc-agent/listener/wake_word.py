"""Wake word listener for "Hey Ash", built on openWakeWord.

Needs a trained model file at MODEL_PATH before this will do anything useful
— see pc-agent/listener/TRAINING.md for how to generate it. This file only
does detection; it does not train the model.
"""

import sys
from pathlib import Path
from typing import Callable

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import WAKE_MODEL_PATH as MODEL_PATH, WAKE_THRESHOLD as DETECTION_THRESHOLD  # noqa: E402

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 1280  # 80ms at 16kHz, openWakeWord's expected frame size


def listen(on_wake_word: Callable[[], None]) -> None:
    """Blocks, listening on the default mic until interrupted. Calls
    on_wake_word() each time "Hey Ash" is detected."""

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"no trained wake word model at {MODEL_PATH} — "
            "see pc-agent/listener/TRAINING.md to generate one first"
        )

    model = Model(wakeword_models=[str(MODEL_PATH)], inference_framework="onnx")

    # The mic stream is closed while on_wake_word runs, so the handler can
    # use the mic itself (recording the question) and the model doesn't
    # hear Ash's own reply.
    while True:
        with sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=CHUNK_SAMPLES
        ) as stream:
            print("Listening for 'Hey Ash'... (Ctrl+C to stop)")
            while True:
                audio_chunk, _ = stream.read(CHUNK_SAMPLES)
                predictions = model.predict(np.squeeze(audio_chunk))
                if any(score > DETECTION_THRESHOLD for score in predictions.values()):
                    break

        model.reset()
        on_wake_word()
        model.reset()


if __name__ == "__main__":
    listen(on_wake_word=lambda: print("Wake word detected."))

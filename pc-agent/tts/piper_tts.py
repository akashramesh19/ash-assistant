"""Local text-to-speech using Piper. Free, runs on CPU — see
docs/decisions.md's TTS choice.

Needs a downloaded voice model at VOICE_MODEL_PATH before this works — see
pc-agent/tts/SETUP.md.
"""

from pathlib import Path

import numpy as np
import sounddevice as sd
from piper.voice import PiperVoice

VOICE_MODEL_PATH = Path(__file__).resolve().parent / "models" / "en_GB-alan-medium.onnx"

_voice = None


def _get_voice() -> PiperVoice:
    global _voice
    if _voice is None:
        if not VOICE_MODEL_PATH.exists():
            raise FileNotFoundError(
                f"no Piper voice model at {VOICE_MODEL_PATH} — "
                "see pc-agent/tts/SETUP.md to download one first"
            )
        _voice = PiperVoice.load(str(VOICE_MODEL_PATH))
    return _voice


def speak(text: str) -> None:
    voice = _get_voice()
    chunks = list(voice.synthesize(text))

    if not chunks:
        return

    audio = np.concatenate([chunk.audio_int16_array for chunk in chunks])
    sd.play(audio, chunks[0].sample_rate)
    sd.wait()


if __name__ == "__main__":
    speak("Hey Sir. Testing, one two three.")

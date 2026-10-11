"""Local speech-to-text using Whisper. Free, runs on CPU — see
docs/decisions.md's STT choice."""

import tempfile
from pathlib import Path

import numpy as np
import sounddevice as sd
import whisper
from scipy.io.wavfile import write as write_wav

SAMPLE_RATE = 16000
MODEL_SIZE = "base"

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = whisper.load_model(MODEL_SIZE)
    return _model


def record(duration_seconds: float = 5.0) -> Path:
    """Records from the default mic for a fixed duration and returns the
    path to a temp WAV file. Phase 1 uses a fixed duration; silence
    detection is a later improvement, not a blocker for the first loop."""

    audio = sd.rec(
        int(duration_seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()

    wav_path = Path(tempfile.mktemp(suffix=".wav"))
    write_wav(wav_path, SAMPLE_RATE, audio)
    return wav_path


def transcribe(wav_path: Path) -> str:
    result = _get_model().transcribe(str(wav_path), fp16=False)
    return result["text"].strip()


def listen_and_transcribe(duration_seconds: float = 5.0) -> str:
    wav_path = record(duration_seconds)
    try:
        return transcribe(wav_path)
    finally:
        wav_path.unlink(missing_ok=True)


if __name__ == "__main__":
    print("Recording for 5 seconds — speak now.")
    print("Transcript:", listen_and_transcribe())

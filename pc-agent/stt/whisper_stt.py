"""Local speech-to-text using Whisper. Free, runs on CPU — see
docs/decisions.md's STT choice."""

import os
import tempfile
import unicodedata
from pathlib import Path

import numpy as np
import sounddevice as sd
import whisper
from scipy.io.wavfile import write as write_wav

from stt.endpoint import CHUNK_SECONDS, Endpointer, trim_quiet_ends

SAMPLE_RATE = 16000
MODEL_SIZE = "base"  # default; ASH_WHISPER_MODEL overrides (for example small)
# Whisper skips a suspect span only when this is set and word timestamps are on.
HALLUCINATION_SILENCE_THRESHOLD = 2.0

_model = None
last_capture = None  # listen_and_transcribe: audio length, why it stopped, model size


def model_size() -> str:
    return os.environ.get("ASH_WHISPER_MODEL", MODEL_SIZE)


def end_silence_seconds() -> float:
    """Pause that ends a turn. Read at record(), not from the Endpointer class default."""
    return float(os.environ.get("ASH_END_SILENCE", "2.0"))


def _get_model():
    global _model
    if _model is None:
        _model = whisper.load_model(model_size())
    return _model


def format_capture(info: dict) -> str:
    return f"audio={info['audio_s']:.1f}s stop={info['stop']} model={info['model']}"


def mostly_non_latin(text: str) -> bool:
    """True when non-Latin letters outnumber Latin ones. Digits and punctuation are ignored."""
    letters = [ch for ch in text if unicodedata.category(ch).startswith("L")]
    if not letters:
        return False
    non_latin = sum(1 for ch in letters if not unicodedata.name(ch, "").startswith("LATIN"))
    return non_latin > len(letters) - non_latin


def transcript_to_send(text: str, info: dict, log=print) -> str:
    """Empty means do not send this transcript to the model."""
    if mostly_non_latin(text):
        info["dropped"] = text
        log(f"[whisper] not sent (non-Latin): {text!r} {format_capture(info)}")
        return ""
    info["dropped"] = None
    return text


def record(max_seconds: float = 20.0, no_speech_seconds: float = 5.0) -> tuple[Path, dict]:
    """Records from the default mic until the speaker stops (a pause after
    speech), nobody speaks for no_speech_seconds, or max_seconds is reached.
    Quiet ends are trimmed, leaving a short pad. Returns the temp WAV path
    and a description of the take (recorded length, stop reason, model)."""

    endpointer = Endpointer(
        end_silence=end_silence_seconds(),
        no_speech=no_speech_seconds,
        max_seconds=max_seconds,
    )
    block = int(SAMPLE_RATE * CHUNK_SECONDS)
    pieces = []
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=block) as stream:
        while True:
            data, _ = stream.read(block)
            pieces.append(data.copy())
            loudness = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
            if endpointer.feed(loudness):
                break

    samples = np.concatenate(pieces)
    info = {
        "audio_s": len(samples) / SAMPLE_RATE,
        "stop": endpointer.reason,
        "model": model_size(),
        "dropped": None,
    }
    samples = trim_quiet_ends(samples, endpointer.speech_start, endpointer.speech_end, SAMPLE_RATE)
    wav_path = Path(tempfile.mktemp(suffix=".wav"))
    write_wav(wav_path, SAMPLE_RATE, samples)
    return wav_path, info


def transcribe_kwargs() -> dict:
    return {
        "fp16": False,
        "language": "en",
        "condition_on_previous_text": False,
        "word_timestamps": True,  # silence skip runs only with word timestamps
        "hallucination_silence_threshold": HALLUCINATION_SILENCE_THRESHOLD,
    }


def transcribe(wav_path: Path) -> str:
    result = _get_model().transcribe(str(wav_path), **transcribe_kwargs())
    return result["text"].strip()


def listen_and_transcribe(no_speech_seconds: float = 5.0, max_seconds: float = 20.0) -> str:
    """Listen until the speaker finishes, then transcribe.

    no_speech_seconds waits for speech to start. max_seconds is the hard cap
    on the recording; a pause can still stop it earlier.
    """
    global last_capture
    wav_path, info = record(max_seconds=max_seconds, no_speech_seconds=no_speech_seconds)
    try:
        text = transcribe(wav_path)
    finally:
        wav_path.unlink(missing_ok=True)
    last_capture = info
    return transcript_to_send(text, info)


if __name__ == "__main__":
    print("Speak now; I stop when you pause.")
    text = listen_and_transcribe()
    extra = f" {format_capture(last_capture)}" if last_capture else ""
    print(f"Transcript: {text!r}{extra}")

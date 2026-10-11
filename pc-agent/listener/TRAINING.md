# Training the "Hey Ash" wake word model

`wake_word.py` only runs detection — it expects a trained model file at
`pc-agent/listener/models/hey_ash.onnx` that doesn't exist yet. This is a
one-time step, not something to redo per session.

## Why this can't just be pip-installed

openWakeWord ships pretrained models for phrases like "alexa" or "hey
jarvis", but "Hey Ash" isn't one of them — per `docs/decisions.md`, the
tested phrase has to be the full name, not a shortened trigger. That means
training a small custom keyword model.

## How

openWakeWord (github.com/dscripka/openWakeWord) publishes an automatic
training pipeline: it synthesizes many spoken variations of your target
phrase using TTS voices, mixes in background noise for robustness, and
trains a lightweight classifier — no manual voice recording needed.

1. Find the automatic model training notebook in the openWakeWord repo
   (it's a Colab notebook maintained alongside the library — check the
   repo's README/notebooks folder for the current link, since paths can
   change between versions).
2. Run it with the target phrase set to `hey ash`. A free Colab GPU handles
   this in roughly 1–2 hours, unattended.
3. Download the resulting model file (`.tflite` or `.onnx`).
4. Save it as `pc-agent/listener/models/hey_ash.onnx` in this repo.
5. Run `python3 pc-agent/listener/wake_word.py` to test detection standalone
   before wiring it into the orchestrator loop.

## Tuning

If it's missing real "Hey Ash" or firing on unrelated speech, adjust
`DETECTION_THRESHOLD` in `wake_word.py` (higher = fewer false positives,
more missed detections) rather than retraining first — retrain only if
threshold tuning alone doesn't fix it.

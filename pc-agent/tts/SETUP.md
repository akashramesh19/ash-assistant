# Setting up a Piper voice

`piper_tts.py` needs a voice model at `pc-agent/tts/models/`. Piper voices
ship as a pair of files — a `.onnx` model and a matching `.onnx.json` config
— published in Piper's own voice samples/releases. Check Piper's GitHub
repo (`rhasspy/piper`) for its current voice list and download links, since
exact URLs and the set of available voices change over time.

## Which voice

Currently using **`en_GB-alan-medium`** — medium quality is the right
tradeoff for a spoken assistant (good enough quality, fast enough on CPU
that replies don't feel laggy). `piper_tts.py`'s `VOICE_MODEL_PATH` points
at this by name; if you switch voices later, update that constant to match.

## Steps

1. Download the voice's `.onnx` and `.onnx.json` files from Piper's voice
   releases.
2. Place both in `pc-agent/tts/models/` (same directory, same base
   filename — Piper expects the `.json` alongside the `.onnx`).
3. Run `python3 pc-agent/tts/piper_tts.py` to test — it should speak a test
   line out loud through your speakers.

## Note on Ash's voice specifically

This just gets a generic voice speaking. Whether this voice actually suits
Ash's dry/deadpan persona (`docs/persona.md`) is a separate, later judgment
call — swap voices freely once you can hear one, this isn't a locked
decision like the wake phrase was.

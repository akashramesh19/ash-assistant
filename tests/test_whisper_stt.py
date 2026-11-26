"""Whisper call options and the non-Latin drop. No microphone, no model load."""

from stt.whisper_stt import (
    MODEL_SIZE,
    end_silence_seconds,
    model_size,
    transcript_to_send,
    transcribe_kwargs,
)


def test_model_stays_base_unless_the_env_switches_it(monkeypatch):
    monkeypatch.delenv("ASH_WHISPER_MODEL", raising=False)
    assert model_size() == MODEL_SIZE == "base"
    monkeypatch.setenv("ASH_WHISPER_MODEL", "small")
    assert model_size() == "small"


def test_end_silence_defaults_to_2_seconds_at_the_call_site(monkeypatch):
    monkeypatch.delenv("ASH_END_SILENCE", raising=False)
    assert end_silence_seconds() == 2.0
    monkeypatch.setenv("ASH_END_SILENCE", "2.5")
    assert end_silence_seconds() == 2.5


def test_transcribe_is_pinned_to_english():
    opts = transcribe_kwargs()
    assert opts["fp16"] is False
    assert opts["language"] == "en"
    assert opts["condition_on_previous_text"] is False
    assert opts["hallucination_silence_threshold"] == 2.0
    assert opts["word_timestamps"] is True


def test_a_mostly_non_latin_transcript_is_not_sent():
    info = {"audio_s": 3.25, "stop": "pause", "model": "base", "dropped": None}
    logs = []
    assert transcript_to_send("谢谢观看", info, log=logs.append) == ""
    assert info["dropped"] == "谢谢观看"
    assert len(logs) == 1
    assert "not sent" in logs[0]
    assert "谢谢观看" in logs[0]
    assert "audio=3.2s" in logs[0] and "stop=pause" in logs[0] and "model=base" in logs[0]
    # A few Latin letters do not save a transcript that is still mostly Chinese.
    assert transcript_to_send("hi 你好世界", info, log=logs.append) == ""


def test_english_and_a_minority_of_non_latin_are_kept():
    info = {"audio_s": 1.0, "stop": "pause", "model": "base", "dropped": "stale"}
    logs = []
    assert transcript_to_send("what's the weather", info, log=logs.append) == "what's the weather"
    assert transcript_to_send("hello 你", info, log=logs.append) == "hello 你"
    assert transcript_to_send("", info, log=logs.append) == ""
    assert info["dropped"] is None
    assert logs == []

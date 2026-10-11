"""The transcript -> orchestrator -> speech path, with fake audio in and out."""

from types import SimpleNamespace

import anthropic

from voice_loop import handle_turn


def run_turn(respond, transcript="what's the weather in Melbourne"):
    logs, spoken = [], []
    handle_turn(
        respond,
        transcribe=lambda: transcript,
        say=spoken.append,
        log=logs.append,
    )
    return logs, spoken


def test_transcript_goes_to_respond_and_reply_is_spoken():
    seen = []

    def respond(text, on_tool_call=None):
        seen.append(text)
        on_tool_call("get_weather", {"location": "Melbourne"}, "Melbourne: 14.0°C, overcast")
        return "Fourteen and overcast."

    logs, spoken = run_turn(respond)

    assert seen == ["what's the weather in Melbourne"]
    assert spoken == ["Fourteen and overcast."]
    assert any("[whisper] heard: \"what's the weather in Melbourne\"" in line for line in logs)
    assert any("[tool] get_weather({'location': 'Melbourne'})" in line for line in logs)
    assert any("[reply]" in line for line in logs)


def test_empty_transcript_is_skipped():
    called = []
    logs, spoken = run_turn(lambda text, on_tool_call=None: called.append(text), transcript="")
    assert called == []
    assert spoken == []
    assert any("[skip]" in line for line in logs)


def test_api_error_is_logged_not_raised_and_nothing_is_spoken():
    def respond(text, on_tool_call=None):
        raise anthropic.APIConnectionError(request=SimpleNamespace())

    logs, spoken = run_turn(respond)
    assert spoken == []
    assert any("[error]" in line for line in logs)

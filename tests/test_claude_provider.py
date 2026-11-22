from types import SimpleNamespace

import anthropic
import pytest

from fakes import FakeClient, response, text_block, tool_block
from providers.base import Provider, ProviderError, ToolCall
from providers.claude import ClaudeProvider

WEATHER = {
    "name": "get_weather",
    "description": "weather",
    "parameters": {"type": "object", "properties": {}},
}


def make(script):
    client = FakeClient(script)
    return ClaudeProvider(client, model="test-model"), client


def test_is_a_provider():
    provider, _ = make([])
    assert isinstance(provider, Provider)
    assert provider.name == "claude"


def test_plain_reply():
    provider, _ = make([response([text_block("Paris.")])])
    result = provider.run_turn("capital of France?", "sys", [WEATHER], lambda n, a: "")
    assert (result.text, result.tool_calls) == ("Paris.", [])


def test_tool_loop_runs_tool_and_records_the_call():
    provider, client = make(
        [
            response([tool_block("get_weather", {"location": "Melbourne"})], "tool_use"),
            response([text_block("Fourteen degrees.")]),
        ]
    )
    seen = []
    result = provider.run_turn(
        "weather?",
        "sys",
        [WEATHER],
        lambda name, args: f"{args['location']}: 14°C",
        on_tool_call=lambda *a: seen.append(a),
    )
    assert result.text == "Fourteen degrees."
    assert result.tool_calls == [ToolCall("get_weather", {"location": "Melbourne"}, "Melbourne: 14°C")]
    assert seen == [("get_weather", {"location": "Melbourne"}, "Melbourne: 14°C")]
    assert client.calls == [1, 3]
    assert "input_schema" in client.tools_seen[0][0]  # converted for Claude


def test_history_carries_over_between_turns():
    provider, client = make([response([text_block("a")]), response([text_block("b")])])
    provider.run_turn("one", "sys", [WEATHER], lambda n, a: "")
    provider.run_turn("two", "sys", [WEATHER], lambda n, a: "")
    assert client.calls == [1, 3]  # user, assistant, user


def test_api_error_becomes_provider_error_and_rolls_back_history():
    error = anthropic.APIConnectionError(request=SimpleNamespace())
    provider, client = make([error, response([text_block("Back.")])])
    with pytest.raises(ProviderError):
        provider.run_turn("first", "sys", [WEATHER], lambda n, a: "")
    assert provider.run_turn("second", "sys", [WEATHER], lambda n, a: "").text == "Back."
    assert client.calls == [1, 1]

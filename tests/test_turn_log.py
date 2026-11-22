import json
import time
from types import SimpleNamespace

import anthropic
import pytest

import context
import handler
from fakes import FakeClient, response, text_block, tool_block
from providers.base import ProviderError
from providers.claude import ClaudeProvider
from turn_log import TurnLog, turn_log_from_env

WEATHER = {
    "name": "get_weather",
    "description": "weather",
    "parameters": {"type": "object", "properties": {}},
}


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    monkeypatch.setattr(context, "MEMORY_PATH", tmp_path / "memory.json")


def read(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_write_appends_json_lines_and_creates_directories(tmp_path):
    log = TurnLog(tmp_path / "nested" / "turns.jsonl")
    log.write({"a": 1})
    log.write({"a": 2})
    assert read(tmp_path / "nested" / "turns.jsonl") == [{"a": 1}, {"a": 2}]


def test_disabled_when_env_unset(monkeypatch):
    monkeypatch.delenv("ASH_TURN_LOG", raising=False)
    assert turn_log_from_env() is None


def test_enabled_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ASH_TURN_LOG", str(tmp_path / "t.jsonl"))
    assert turn_log_from_env() is not None


def make_responder(script, tmp_path):
    provider = ClaudeProvider(FakeClient(script), "test-model")
    return handler.create_responder(provider, TurnLog(tmp_path / "turns.jsonl"))


def test_turn_is_logged_with_provider_prompt_tools_and_latency(tmp_path, monkeypatch):
    monkeypatch.setitem(
        handler.TOOLS,
        "get_weather",
        SimpleNamespace(run=lambda **kw: "Melbourne: 24°C", TOOL_DEFINITION=WEATHER),
    )
    respond = make_responder(
        [
            response([tool_block("get_weather", {"location": "Melbourne"})], "tool_use"),
            response([text_block("Twenty-four.")]),
        ],
        tmp_path,
    )
    respond("weather in Melbourne?")

    (record,) = read(tmp_path / "turns.jsonl")
    assert record["provider"] == "claude"
    assert record["prompt"] == "weather in Melbourne?"
    assert record["reply"] == "Twenty-four."
    assert record["tool_calls"] == [
        {"name": "get_weather", "arguments": {"location": "Melbourne"}, "result": "Melbourne: 24°C"}
    ]
    assert record["error"] is None
    latency = record["latency"]
    assert latency["total_seconds"] >= latency["model_seconds"] >= 0
    assert latency["first_token_seconds"] is None  # Claude path is not streamed


def api_down():
    error = anthropic.APIConnectionError(request=SimpleNamespace())
    error.message = "down"
    return error


def test_failed_turn_is_logged_with_error_then_raised(tmp_path):
    respond = make_responder([api_down()], tmp_path)
    with pytest.raises(ProviderError):
        respond("hello")
    (record,) = read(tmp_path / "turns.jsonl")
    assert record["reply"] is None and "down" in record["error"]


def test_model_time_excludes_tool_time(tmp_path, monkeypatch):
    def slow_tool(**kw):
        time.sleep(0.15)
        return "ok"

    monkeypatch.setitem(
        handler.TOOLS, "get_weather", SimpleNamespace(run=slow_tool, TOOL_DEFINITION=WEATHER)
    )
    client = FakeClient(
        [response([tool_block("get_weather", {})], "tool_use"), response([text_block("done")])]
    )
    provider = ClaudeProvider(client, "m")
    result = provider.run_turn("w", "sys", [WEATHER], handler.run_tool)
    assert result.tool_seconds >= 0.15
    assert result.model_seconds < 0.1  # the fake client is instant
    assert result.total_seconds >= result.tool_seconds

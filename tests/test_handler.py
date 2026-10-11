"""Orchestrator loop against a fake Claude client (no network, no real key)."""

from types import SimpleNamespace

import anthropic
import pytest

import context
import handler


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, tool_input, tool_id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=tool_id)


def response(blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(len(kwargs["messages"]))
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    # record_command writes memory.json; keep tests off the real file.
    monkeypatch.setattr(context, "MEMORY_PATH", tmp_path / "memory.json")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")


def make_responder(monkeypatch, script):
    client = FakeClient(script)
    monkeypatch.setattr(handler.anthropic, "Anthropic", lambda: client)
    return handler.create_responder(), client


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(handler.MissingApiKeyError):
        handler.create_responder()


def test_plain_reply(monkeypatch):
    respond, _ = make_responder(monkeypatch, [response([text_block("Paris.")])])
    assert respond("capital of France?") == "Paris."


def test_tool_call_runs_tool_and_reports_it(monkeypatch):
    monkeypatch.setitem(
        handler.TOOLS, "get_weather", SimpleNamespace(run=lambda **kw: f"{kw['location']}: 14°C", TOOL_DEFINITION={})
    )
    respond, client = make_responder(
        monkeypatch,
        [
            response([tool_block("get_weather", {"location": "Melbourne"})], "tool_use"),
            response([text_block("Fourteen degrees.")]),
        ],
    )
    seen = []
    reply = respond("weather in Melbourne", on_tool_call=lambda *a: seen.append(a))

    assert reply == "Fourteen degrees."
    assert seen == [("get_weather", {"location": "Melbourne"}, "Melbourne: 14°C")]
    assert client.calls == [1, 3]  # second call includes assistant tool_use + tool_result


def test_api_error_rolls_back_history(monkeypatch):
    error = anthropic.APIConnectionError(request=SimpleNamespace())
    respond, client = make_responder(
        monkeypatch, [error, response([text_block("Back.")])]
    )
    with pytest.raises(anthropic.APIError):
        respond("first try")
    assert respond("second try") == "Back."
    assert client.calls == [1, 1]  # failed turn left nothing behind

"""MatildaProvider against a fake Runner (no network, no real key)."""

import asyncio
import time
from types import SimpleNamespace

import pytest
from matilda_agent_sdk import MatildaError

from providers import create_provider
from providers.base import Provider, ProviderConfigError, ProviderError, ToolCall
from providers.matilda import MatildaProvider

WEATHER = {
    "name": "get_weather",
    "description": "weather",
    "parameters": {"type": "object", "properties": {"location": {"type": "string"}}},
}


class FakeRunner:
    """Stands in for matilda_agent_sdk.Runner. `steps` is one entry per run():
    a reply string, an Exception to raise, or a dict {tool, args, reply} that
    calls a tool handler the way the SDK would, then replies."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.runs = []
        self.tool_results = []

    async def run(self, agent, prompt, **kwargs):
        self.runs.append({"agent": agent, "prompt": prompt, **kwargs})
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, dict) and "errors" in step:
            return SimpleNamespace(final_output="", errors=step["errors"], truncated_reason=None, usage=None)
        reply = step
        if isinstance(step, dict):
            handler = kwargs["tool_handlers"][step["tool"]]
            self.tool_results.append(await handler(step["args"], None))
            reply = step["reply"]
        await asyncio.sleep(0.02)
        kwargs["callbacks"]["on_token"](reply)  # the SDK streams tokens to this
        return SimpleNamespace(final_output=reply, errors=[], truncated_reason=None, usage=None)


def make(steps):
    runner = FakeRunner(steps)
    return MatildaProvider(runner), runner


def turn(provider, text="hi", run_tool=lambda n, a: "ok", on_tool_call=None, tools=(WEATHER,)):
    return provider.run_turn(text, "SYSTEM", list(tools), run_tool, on_tool_call)


def test_is_a_provider():
    provider, _ = make([])
    assert isinstance(provider, Provider) and provider.name == "matilda"


def test_plain_reply_sends_system_prompt_as_instructions():
    provider, runner = make(["Paris."])
    result = turn(provider, "capital of France?")
    assert result.text == "Paris." and result.tool_calls == []
    sent = runner.runs[0]
    assert sent["agent"]["instructions"] == "SYSTEM"
    assert sent["prompt"] == "capital of France?"
    assert sent["history"] == []
    assert sent["throw_on_stream_error"] is False


def test_second_turn_replays_text_history():
    provider, runner = make(["one", "two"])
    turn(provider, "first")
    turn(provider, "second")
    assert runner.runs[1]["history"] == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "one"},
    ]


def test_tools_are_advertised_in_neutral_shape():
    provider, runner = make(["x"])
    turn(provider)
    assert runner.runs[0]["client_tools"] == [WEATHER]
    assert set(runner.runs[0]["tool_handlers"]) == {"get_weather"}


def test_tool_call_runs_shared_tool_and_is_recorded():
    seen = []
    provider, runner = make([{"tool": "get_weather", "args": {"location": "Melbourne"}, "reply": "24 degrees."}])
    result = turn(
        provider,
        run_tool=lambda name, args: f"{args['location']}: 24°C",
        on_tool_call=lambda *a: seen.append(a),
    )
    assert result.text == "24 degrees."
    assert result.tool_calls == [ToolCall("get_weather", {"location": "Melbourne"}, "Melbourne: 24°C")]
    assert seen == [("get_weather", {"location": "Melbourne"}, "Melbourne: 24°C")]
    assert runner.tool_results[0].content == "Melbourne: 24°C" and not runner.tool_results[0].is_error


def test_tool_exception_becomes_error_result_not_a_crash():
    def boom(name, args):
        raise RuntimeError("network down")

    provider, runner = make([{"tool": "get_weather", "args": {}, "reply": "Couldn't check."}])
    result = turn(provider, run_tool=boom)
    assert result.text == "Couldn't check."
    assert runner.tool_results[0].is_error
    assert "network down" in runner.tool_results[0].content


def test_stream_errors_on_result_become_provider_error_and_leave_history_alone():
    errors = [SimpleNamespace(code="rate_limited", message="slow down")]
    provider, runner = make([{"errors": errors}, "Back."])
    with pytest.raises(ProviderError, match="rate_limited"):
        turn(provider, "first")
    turn(provider, "second")
    assert runner.runs[1]["history"] == []  # failed turn not replayed


def test_sdk_exception_becomes_provider_error():
    provider, _ = make([MatildaError("boom")])
    with pytest.raises(ProviderError, match="boom"):
        turn(provider)


def test_factory_builds_matilda_and_needs_its_key(monkeypatch):
    monkeypatch.setenv("ASH_PROVIDER", "matilda")
    monkeypatch.delenv("MATILDA_API_KEY", raising=False)
    with pytest.raises(ProviderConfigError, match="MATILDA_API_KEY"):
        create_provider()
    monkeypatch.setenv("MATILDA_API_KEY", "mc_live_not_real")
    assert create_provider().name == "matilda"


def test_timing_splits_tool_time_from_model_time_and_reports_first_token():
    def slow_tool(name, args):
        time.sleep(0.15)
        return "ok"

    provider, _ = make([{"tool": "get_weather", "args": {}, "reply": "done"}])
    result = turn(provider, run_tool=slow_tool)
    assert result.tool_seconds >= 0.15
    assert result.total_seconds >= result.tool_seconds
    assert result.model_seconds == pytest.approx(result.total_seconds - result.tool_seconds)
    assert result.first_token_seconds is not None
    assert result.first_token_seconds <= result.total_seconds

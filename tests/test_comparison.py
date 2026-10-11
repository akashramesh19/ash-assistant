"""The comparison harness, driven by scripted fake providers (no network)."""

import hashlib
import json

import pytest

import context
import run_comparison as rc
from providers.base import Provider, ProviderError, ToolCall, TurnResult


class ScriptedProvider(Provider):
    """Replies per prompt from a dict: prompt -> (text, [ToolCall]) or Exception."""

    def __init__(self, name, script):
        self.name = name
        self.script = script
        self.seen_context = []

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        self.seen_context.append(system_prompt)
        item = self.script[user_text]
        if isinstance(item, Exception):
            raise item
        text, calls = item
        return TurnResult(text=text, tool_calls=calls, total_seconds=1.0, model_seconds=0.7, tool_seconds=0.3)


MEL = ToolCall("get_weather", {"location": "Melbourne, AU"}, "Melbourne: 24°C, clear sky")
SYD = ToolCall("get_weather", {"location": "Sydney"}, "Sydney: 20°C, rain")
GOOD = {
    "What's the weather in Melbourne?": ("24 and clear.", [MEL]),
    "And in Sydney?": ("20 and wet.", [SYD]),
    "What is the capital of France?": ("Paris.", []),
}


def test_weather_check_needs_the_tool_and_the_right_city():
    ok, _ = rc.CHECKS[1]("24 and clear.", [MEL])
    assert ok
    assert not rc.CHECKS[1]("Probably mild.", [])[0]  # answered without the tool
    assert not rc.CHECKS[1]("x", [SYD])[0]  # wrong city
    assert rc.CHECKS[2]("x", [SYD])[0]


def test_capital_check_wants_paris_and_no_tool():
    assert rc.CHECKS[3]("Paris.", [])[0]
    assert not rc.CHECKS[3]("Paris.", [MEL])[0]
    assert not rc.CHECKS[3]("Lyon.", [])[0]


def test_each_provider_run_starts_from_a_fresh_copy_of_the_example_memory(tmp_path):
    seen = {}

    def build(name):
        provider = ScriptedProvider(name, GOOD)
        seen[name] = provider
        return provider

    rc.run_all(["claude", "matilda"], [1, 2, 3], repeat=1, build_provider=build, work_dir=tmp_path)
    # Claude's three prompts must not appear in Matilda's first-turn context.
    first_matilda_context = seen["matilda"].seen_context[0]
    assert "weather in Melbourne" not in first_matilda_context
    assert "Akash prefers dry" in first_matilda_context  # the example fixture


def test_real_memory_is_untouched_and_path_restored(tmp_path, monkeypatch):
    real = tmp_path / "real_memory.json"
    real.write_text('{"active_project": "x", "standing_facts": [], "recent_commands": ["private"]}')
    monkeypatch.setattr(context, "MEMORY_PATH", real)
    before = hashlib.sha256(real.read_bytes()).hexdigest()

    rc.run_all(["claude"], [1, 2, 3], repeat=1, build_provider=lambda n: ScriptedProvider(n, GOOD), work_dir=tmp_path / "w")

    assert hashlib.sha256(real.read_bytes()).hexdigest() == before
    assert context.MEMORY_PATH == real


def test_rows_capture_checks_latency_and_errors(tmp_path):
    script = dict(GOOD)
    script["And in Sydney?"] = ProviderError("RateLimit: slow down")
    rows = rc.run_all(["claude"], [1, 2, 3], repeat=1, build_provider=lambda n: ScriptedProvider(n, script), work_dir=tmp_path)
    assert [row["passed"] for row in rows] == [True, False, True]
    assert rows[1]["error"] and "RateLimit" in rows[1]["error"]
    assert rows[0]["total_seconds"] == 1.0 and rows[0]["tool_calls"][0]["name"] == "get_weather"


def test_markdown_has_summary_detail_and_flags_citations(tmp_path):
    script = dict(GOOD)
    script["What's the weather in Melbourne?"] = ("24 and clear.\n\nSources\n[1] https://x.example", [MEL])
    rows = rc.run_all(["claude"], [1, 2, 3], repeat=1, build_provider=lambda n: ScriptedProvider(n, script), work_dir=tmp_path)
    md = rc.render_markdown(rows, repeat=1, providers=["claude"], claude_model="m", python="3.x")
    assert "## Summary" in md and "## Detail" in md and "## Replies" in md
    assert "citations" in md.lower()  # the extra-information flag
    summary_rows = [line for line in md.splitlines() if line.startswith("| claude | ")]
    assert len([line for line in summary_rows if "1/1" in line]) == 3  # one per prompt


def test_prompts_4_and_5_are_refused_until_move_file_exists():
    with pytest.raises(SystemExit):
        rc.parse_prompts("1-5")


def test_refuses_to_overwrite_existing_results(tmp_path):
    out = tmp_path / "results.md"
    out.write_text("keep me")
    with pytest.raises(SystemExit):
        rc.write_results(out, "new")
    assert out.read_text() == "keep me"

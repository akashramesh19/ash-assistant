import pytest

import providers
from providers.base import Provider, ProviderConfigError, ProviderError, ToolCall, TurnResult
from providers.claude import ClaudeProvider
from providers.router import RoutingProvider, choose_order


class FakeProvider(Provider):
    """Replays a script: a string is a reply, an Exception is raised, a tuple
    (tool_name, reply) runs that tool through run_tool first."""

    def __init__(self, name, script):
        self.name = name
        self.script = list(script)
        self.history_seen = []
        self.replaced_with = []

    def replace_history(self, turns):
        self.replaced_with.append(list(turns))

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        item = self.script.pop(0)
        if isinstance(item, tuple):
            tool, item = item
            result = run_tool(tool, {})
            if on_tool_call:
                on_tool_call(tool, {}, result)
        if isinstance(item, Exception):
            raise item
        return TurnResult(text=item)


def run(router, text, tools=None):
    return router.run_turn(text, "sys", [], tools or (lambda name, args: "ok"), None)


def pair(claude_script=(), matilda_script=(), default="claude"):
    claude, matilda = FakeProvider("claude", claude_script), FakeProvider("matilda", matilda_script)
    return RoutingProvider({"claude": claude, "matilda": matilda}, default), claude, matilda


AVAILABLE = ["claude", "matilda"]


@pytest.mark.parametrize("text", ["What's the weather in Melbourne?", "Move report.txt into the Archive folder", "delete report.txt", "what time is it", "what's the latest version of my file"])
def test_tool_requests_go_to_claude_even_after_matilda_or_with_live_words(text):
    order, reason = choose_order(text, AVAILABLE, last="matilda")
    assert order == ["claude", "matilda"] and reason == "tool request"


@pytest.mark.parametrize("text", ["What's the latest news on the Matilda model?", "Who won the grand final?", "What is the price of bitcoin right now", "What happened in Canberra this week?"])
def test_live_information_goes_to_matilda(text):
    order, reason = choose_order(text, AVAILABLE, last=None)
    assert order == ["matilda", "claude"] and reason == "live information"


def test_everything_else_goes_to_the_default_which_is_claude():
    assert choose_order("What is the capital of France?", AVAILABLE, last=None) == (["claude", "matilda"], "default model")
    assert choose_order("What is the capital of France?", AVAILABLE, last=None, default="matilda")[0][0] == "matilda"


def test_live_information_falls_back_to_default_when_matilda_is_unavailable():
    assert choose_order("latest news please", ["claude"], last=None)[0] == ["claude"]


@pytest.mark.parametrize("text", ["And in Sydney?", "yes", "ok do it", "No, the other one please"])
def test_follow_ups_stay_with_the_last_model(text):
    assert choose_order(text, AVAILABLE, last="claude")[0][0] == "claude"
    assert choose_order(text, AVAILABLE, last="matilda")[0][0] == "matilda"


def test_no_prefix_is_a_word_not_a_substring():
    order, reason = choose_order("Nothing beats Melbourne coffee, tell me why that is so", AVAILABLE, last="matilda")
    assert order[0] == "claude" and reason == "default model"


def test_follow_up_with_no_history_is_routed_normally():
    assert choose_order("yes", AVAILABLE, last=None)[0][0] == "claude"


def test_routes_and_records_the_answering_model():
    router, claude, matilda = pair(["22 and clear"], ["Paris, Sir."])
    assert run(router, "What's the weather in Sydney?").text == "22 and clear"
    assert router.name == "claude"
    assert run(router, "What's the latest news on Canberra?").text == "Paris, Sir."
    assert router.name == "matilda" and router.last_route["reason"] == "live information"


def test_switching_hands_the_new_model_the_text_transcript():
    router, claude, matilda = pair(["22 and clear"], ["Paris, Sir."])
    run(router, "What's the weather in Sydney?")
    run(router, "What's the latest news on Canberra?")
    assert matilda.replaced_with == [[("What's the weather in Sydney?", "22 and clear")]]
    assert claude.replaced_with == []  # never needed it: it had answered first


def test_same_model_twice_does_not_resend_history():
    router, claude, matilda = pair(["a", "b"])
    run(router, "weather in Sydney")
    run(router, "And in Perth?")
    assert claude.replaced_with == [] and router.name == "claude"


def test_falls_back_when_the_first_model_fails_before_any_tool_ran():
    router, claude, matilda = pair([ProviderError("rate limited")], ["Fine, Sir."])
    assert run(router, "weather in Sydney").text == "Fine, Sir."
    assert router.name == "matilda"
    assert router.last_route["fallback_from"] == "claude"
    assert "rate limited" in router.last_route["errors"][0]


def test_no_fallback_after_a_tool_has_run():
    calls = []
    router, claude, matilda = pair([("move_file", ProviderError("connection dropped"))], ["Done."])
    with pytest.raises(ProviderError, match="not retrying on another model"):
        run(router, "move report.txt into Archive", tools=lambda name, args: calls.append(name) or "Moved")
    assert calls == ["move_file"] and matilda.script == ["Done."]  # matilda never asked


def test_all_models_failing_raises_one_error_with_both_reasons():
    router, *_ = pair([ProviderError("claude down")], [ProviderError("matilda down")])
    with pytest.raises(ProviderError) as error:
        run(router, "weather in Sydney")
    assert "claude down" in str(error.value) and "matilda down" in str(error.value)


def test_a_failed_turn_is_not_added_to_the_transcript():
    router, claude, matilda = pair([ProviderError("x")], [ProviderError("y")])
    with pytest.raises(ProviderError):
        run(router, "weather in Sydney")
    assert router.transcript == []


def test_history_is_resent_after_a_total_failure():
    router, claude, matilda = pair(["a", ProviderError("x")], ["b", "c"])
    run(router, "weather in Sydney")                 # claude answers
    run(router, "weather in Perth")                  # claude fails -> matilda answers
    assert matilda.replaced_with == [[("weather in Sydney", "a")]]
    assert router.name == "matilda"


def test_on_tool_call_still_reaches_the_caller():
    seen = []
    router, claude, matilda = pair([("get_weather", "22 and clear")])
    router.run_turn("weather", "sys", [], lambda n, a: "r", lambda n, a, r: seen.append(n))
    assert seen == ["get_weather"]


def test_replace_history_on_claude_provider_builds_valid_alternating_text():
    provider = ClaudeProvider(client=None, model="m")
    provider.replace_history([("a", "b"), ("c", "d")])
    assert [m["role"] for m in provider.messages] == ["user", "assistant", "user", "assistant"]
    assert provider.messages[2]["content"] == "c"


# --- factory -------------------------------------------------------------

def test_auto_with_both_available_routes(monkeypatch):
    monkeypatch.setenv("ASH_PROVIDER", "auto")
    monkeypatch.setitem(providers.BUILDERS, "claude", lambda: FakeProvider("claude", []))
    monkeypatch.setitem(providers.BUILDERS, "matilda", lambda: FakeProvider("matilda", []))
    assert isinstance(providers.create_provider(), RoutingProvider)


def test_auto_with_one_provider_missing_just_uses_the_other(monkeypatch):
    def no_key():
        raise ProviderConfigError("MATILDA_API_KEY isn't set")

    monkeypatch.setitem(providers.BUILDERS, "claude", lambda: FakeProvider("claude", []))
    monkeypatch.setitem(providers.BUILDERS, "matilda", no_key)
    assert providers.create_provider("auto").name == "claude"


def test_auto_with_nothing_available_fails_clearly(monkeypatch):
    def no_key():
        raise ProviderConfigError("key missing")

    monkeypatch.setitem(providers.BUILDERS, "claude", no_key)
    monkeypatch.setitem(providers.BUILDERS, "matilda", no_key)
    with pytest.raises(ProviderConfigError, match="no provider could be set up"):
        providers.create_provider("auto")


def test_bad_route_chat_value_fails_clearly(monkeypatch):
    monkeypatch.setenv("ASH_ROUTE_DEFAULT", "nope")
    monkeypatch.setitem(providers.BUILDERS, "claude", lambda: FakeProvider("claude", []))
    monkeypatch.setitem(providers.BUILDERS, "matilda", lambda: FakeProvider("matilda", []))
    with pytest.raises(ProviderConfigError, match="ASH_ROUTE_DEFAULT"):
        providers.create_provider("auto")

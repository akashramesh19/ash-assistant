"""Fake Anthropic client pieces shared by the tests."""

from types import SimpleNamespace


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_block(name, tool_input, tool_id="t1"):
    return SimpleNamespace(type="tool_use", name=name, input=tool_input, id=tool_id)


def response(blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


class FakeClient:
    """Replays a script of responses (or exceptions) and records, for each
    call, how many messages were sent and which tools were offered."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.tools_seen = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(len(kwargs["messages"]))
        self.tools_seen.append(kwargs["tools"])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

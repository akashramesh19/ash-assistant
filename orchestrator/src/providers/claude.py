"""Claude-specific formats and loop. Tools are model-neutral everywhere else;
conversion to Anthropic's shapes happens here."""

import anthropic

from providers.base import Provider, ProviderError, ToolCall, TurnResult


def to_claude_tools(tool_definitions: list[dict]) -> list[dict]:
    """Neutral {name, description, parameters} -> Anthropic {..., input_schema}."""
    return [
        {
            "name": definition["name"],
            "description": definition["description"],
            "input_schema": definition["parameters"],
        }
        for definition in tool_definitions
    ]


class ClaudeProvider(Provider):
    name = "claude"

    def __init__(self, client, model: str, max_tokens: int = 1024):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.messages = []  # Anthropic-format history, private to this provider

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        history_length = len(self.messages)
        try:
            return self._run_turn(user_text, system_prompt, tool_definitions, run_tool, on_tool_call)
        except anthropic.APIError as error:
            # Drop the half-finished turn so the next one starts from a valid
            # history (no dangling user message or unanswered tool call).
            del self.messages[history_length:]
            raise ProviderError(f"{type(error).__name__}: {getattr(error, 'message', error)}") from error

    def _run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call):
        tools = to_claude_tools(tool_definitions)
        tool_calls = []
        self.messages.append({"role": "user", "content": user_text})

        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                tools=tools,
                messages=self.messages,
            )
            self.messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = run_tool(block.name, block.input)
                tool_calls.append(ToolCall(block.name, block.input, result))
                if on_tool_call:
                    on_tool_call(block.name, block.input, result)
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": result}
                )
            self.messages.append({"role": "user", "content": tool_results})

        text = "\n".join(block.text for block in response.content if block.type == "text")
        return TurnResult(text=text, tool_calls=tool_calls)

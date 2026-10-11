import os
from pathlib import Path

import anthropic

from context import get_context, record_command
from providers.claude import to_claude_tools
from tools import TOOLS

MODEL = "claude-sonnet-5"
PERSONA_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "persona.md"


def load_system_prompt() -> str:
    return PERSONA_PATH.read_text()


def build_tool_definitions():
    return [module.TOOL_DEFINITION for module in TOOLS.values()]


def run_tool(name: str, tool_input: dict) -> str:
    if name not in TOOLS:
        return f"error: unknown tool '{name}'"
    return TOOLS[name].run(**tool_input)


class MissingApiKeyError(RuntimeError):
    pass


def create_responder():
    """Returns respond(text, on_tool_call=None) -> reply text. Each responder
    keeps its own conversation history, so typed and voice callers share the
    same Claude tool loop.

    on_tool_call(name, tool_input, result) is called after each tool runs,
    for callers that want to log it."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingApiKeyError(
            "ANTHROPIC_API_KEY isn't set in this terminal. "
            "Run: export ANTHROPIC_API_KEY=... (then start Ash again)"
        )
    client = anthropic.Anthropic()
    tool_definitions = to_claude_tools(build_tool_definitions())
    persona = load_system_prompt()
    messages = []

    def respond(user_input: str, on_tool_call=None) -> str:
        history_length = len(messages)
        try:
            return _run_turn(user_input, on_tool_call)
        except anthropic.APIError:
            # Drop the half-finished turn so the next one starts from a valid
            # history (no dangling user message or unanswered tool call).
            del messages[history_length:]
            raise

    def _run_turn(user_input: str, on_tool_call) -> str:
        messages.append({"role": "user", "content": user_input})
        system_prompt = f"{persona}\n\n## Context\n{get_context()}"

        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=tool_definitions,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = run_tool(block.name, block.input)
                if on_tool_call:
                    on_tool_call(block.name, block.input, result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        record_command(user_input)
        return "\n".join(block.text for block in response.content if block.type == "text")

    return respond


def main():
    try:
        respond = create_responder()
    except MissingApiKeyError as error:
        print(f"error: {error}")
        return

    print("Ash is listening. Type a command (Ctrl+C to quit).")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

        try:
            reply = respond(user_input)
        except anthropic.APIError as error:
            print(f"error: {type(error).__name__}: {getattr(error, 'message', error)}")
            continue
        if reply:
            print(reply)


if __name__ == "__main__":
    main()

from pathlib import Path

import anthropic

from context import get_context, record_command
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


def main():
    client = anthropic.Anthropic()
    tool_definitions = build_tool_definitions()
    persona = load_system_prompt()
    messages = []

    print("Oli is listening. Type a command (Ctrl+C to quit).")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not user_input:
            continue

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
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
            messages.append({"role": "user", "content": tool_results})

        for block in response.content:
            if block.type == "text":
                print(block.text)

        record_command(user_input)


if __name__ == "__main__":
    main()

import time
from pathlib import Path

from context import get_context, record_command
from providers import create_provider
from providers.base import ProviderConfigError, ProviderError
from tools import TOOLS
from turn_log import build_record, turn_log_from_env

PERSONA_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "persona.md"


def load_system_prompt() -> str:
    return PERSONA_PATH.read_text()


def build_tool_definitions():
    return [module.TOOL_DEFINITION for module in TOOLS.values()]


def run_tool(name: str, tool_input: dict) -> str:
    if name not in TOOLS:
        return f"error: unknown tool '{name}'"
    return TOOLS[name].run(**tool_input)


def create_responder(provider=None, turn_log=None):
    """Returns respond(text, on_tool_call=None) -> reply text. Each responder
    keeps its own conversation (inside its provider), so typed and voice
    callers share the same tool loop.

    on_tool_call(name, tool_input, result) is called after each tool runs,
    for callers that want to log it."""
    provider = provider or create_provider()
    turn_log = turn_log or turn_log_from_env()
    tool_definitions = build_tool_definitions()
    persona = load_system_prompt()

    def respond(user_input: str, on_tool_call=None) -> str:
        system_prompt = f"{persona}\n\n## Context\n{get_context()}"
        started = time.perf_counter()
        try:
            result = provider.run_turn(
                user_input, system_prompt, tool_definitions, run_tool, on_tool_call
            )
        except ProviderError as error:
            if turn_log:
                turn_log.write(
                    build_record(
                        provider.name, user_input, error=str(error),
                        elapsed_seconds=time.perf_counter() - started,
                    )
                )
            raise
        record_command(user_input)
        if turn_log:
            turn_log.write(build_record(provider.name, user_input, result))
        return result.text

    return respond


def main():
    try:
        respond = create_responder()
    except ProviderConfigError as error:
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
        except ProviderError as error:
            print(f"error: {error}")
            continue
        if reply:
            print(reply)


if __name__ == "__main__":
    main()

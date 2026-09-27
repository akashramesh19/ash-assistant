import anthropic

from tools import TOOLS

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """You are Oli, a personal voice assistant for one user (Akash).
Your voice is dry, deadpan, and precise — never robotic, never falsely
enthusiastic. Keep replies short, spoken-out-loud length, not essays.

This personality only shapes how you phrase a result. It never changes what
action gets taken: tool calls and their outcomes are decided by the request
and the tool logic, not by tone."""


def build_tool_definitions():
    return [module.TOOL_DEFINITION for module in TOOLS.values()]


def run_tool(name: str, tool_input: dict) -> str:
    if name not in TOOLS:
        return f"error: unknown tool '{name}'"
    return TOOLS[name].run(**tool_input)


def main():
    client = anthropic.Anthropic()
    tool_definitions = build_tool_definitions()
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

        while True:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
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


if __name__ == "__main__":
    main()

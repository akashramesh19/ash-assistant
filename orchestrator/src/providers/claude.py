"""Claude-specific formats. Tools and history are model-neutral everywhere
else; conversion to Anthropic's shapes happens here."""


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

"""Tools declare one neutral definition; each provider converts it."""

from providers.claude import to_claude_tools
from tools import TOOLS


def test_every_tool_uses_the_neutral_format():
    for name, module in TOOLS.items():
        definition = module.TOOL_DEFINITION
        assert definition["name"] == name
        assert definition["description"]
        assert definition["parameters"]["type"] == "object"
        assert "input_schema" not in definition  # Claude's spelling lives in providers/claude.py


def test_claude_conversion_renames_parameters_to_input_schema():
    neutral = [
        {
            "name": "x",
            "description": "d",
            "parameters": {"type": "object", "properties": {"a": {"type": "string"}}},
        }
    ]
    assert to_claude_tools(neutral) == [
        {
            "name": "x",
            "description": "d",
            "input_schema": {"type": "object", "properties": {"a": {"type": "string"}}},
        }
    ]


def test_conversion_does_not_mutate_the_neutral_definitions():
    neutral = [{"name": "x", "description": "d", "parameters": {"type": "object"}}]
    to_claude_tools(neutral)
    assert "parameters" in neutral[0] and "input_schema" not in neutral[0]

"""The seam between Ash's loop and whichever model answers.

A provider owns everything model-specific: its conversation history, message
and tool formats, and its tool-calling loop. The rest of Ash only passes in
neutral tool definitions and a run_tool function, and gets a TurnResult back.
Tool behaviour (including confirmation and safety) lives in tools/, so it is
identical whichever provider calls it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable


class ProviderError(Exception):
    """The model call failed (network, auth, rate limit, ...). The provider has
    already discarded the half-finished turn, so the next turn starts clean."""


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: str


@dataclass
class TurnResult:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


RunTool = Callable[[str, dict], str]
OnToolCall = Callable[[str, dict, str], None]


class Provider(ABC):
    name: str

    @abstractmethod
    def run_turn(
        self,
        user_text: str,
        system_prompt: str,
        tool_definitions: list[dict],
        run_tool: RunTool,
        on_tool_call: OnToolCall | None = None,
    ) -> TurnResult:
        """Answer one user message, running tools as the model asks.
        tool_definitions are neutral {name, description, parameters}."""

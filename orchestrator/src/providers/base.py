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


class ProviderConfigError(RuntimeError):
    """The chosen provider can't be set up (unknown name, missing key, ...)."""


@dataclass
class ToolCall:
    name: str
    arguments: dict
    result: str


@dataclass
class TurnResult:
    """total_seconds is the whole provider turn; tool_seconds is time spent in
    our tools; model_seconds is the rest (the model call, plus anything the
    provider does server-side). first_token_seconds is None where the provider
    isn't streamed. Typing and pauses are never included."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    total_seconds: float = 0.0
    model_seconds: float = 0.0
    tool_seconds: float = 0.0
    first_token_seconds: float | None = None
    # Tools the provider ran on its own side (e.g. Matilda's web search), by
    # name. Not our tools; recorded so callers can see what actually happened.
    server_tool_calls: list[str] = field(default_factory=list)


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

    def replace_history(self, turns: list[tuple[str, str]]) -> None:
        """Replace this provider's history with plain (user, reply) text turns.
        Used by the router when the answering model changes. Providers that
        keep history override this; tool exchanges are not carried across."""

"""Automatic provider switching: route each turn to a model, fall back on failure.

RoutingProvider is itself a Provider, so nothing above the seam changes.

Routing is deterministic code, not an LLM call (execution layer stays literal).
Claude is the default; Matilda is used by choice for one thing and as a fallback:
  - tool requests (weather, files, time) always go to Claude. In the 2026-10-11
    comparison Matilda added web citations and details our weather tool never
    returned (3 of 6 and 7 of 10 replies), which breaks "tool output is the
    source of truth" and reads badly aloud.
  - live-information questions ("latest", "news", "price of", "who won") go to
    Matilda. It searches the web server-side; Claude has no web access in Ash.
  - short follow-ups ("and in Sydney?", "yes") stay with whichever model answered
    last, since they only make sense in that model's context.
  - everything else goes to the default model (Claude; ASH_ROUTE_DEFAULT can change it).

Fallback: if the chosen model raises ProviderError, the next one is tried, but
only if no tool ran during the failed attempt. A tool that already ran (a file
move, say) must never be repeated on a second model.

Each provider keeps its own history. When the answering model changes, it is
given the shared plain-text transcript first (tool exchanges are not carried
across), so a follow-up still makes sense after a switch.
"""

import re

from providers.base import Provider, ProviderError

TOOL_WORDS = re.compile(
    r"\b(weather|temperature|forecast|raining|rain|time|move|moving|file|files|folder|"
    r"archive|rename|delete|remove|trash|overwrite|replace)\b",
    re.IGNORECASE,
)
LIVE_INFO = re.compile(
    r"\b(latest|news|headlines|current|currently|right now|price of|stock|score|who won|"
    r"what happened|recent|recently|this week|this year|today's)\b",
    re.IGNORECASE,
)
FOLLOW_UP_START = re.compile(
    r"^(and|also|what about|how about|yes|yeah|yep|no|nope|ok|okay|confirm|do it)\b", re.IGNORECASE
)
MAX_FOLLOW_UP_WORDS = 4


def choose_order(user_text: str, available: list[str], last: str | None, default: str = "claude") -> tuple[list[str], str]:
    """Providers to try, best first, and the reason for the choice."""
    text = user_text.strip().lower()
    is_tool = bool(TOOL_WORDS.search(text))
    is_follow_up = len(text.split()) <= MAX_FOLLOW_UP_WORDS or bool(FOLLOW_UP_START.match(text))
    if is_tool and "claude" in available:
        first, reason = "claude", "tool request"
    elif last in available and is_follow_up:
        first, reason = last, "follow-up stays with the last model"
    elif LIVE_INFO.search(text) and "matilda" in available:
        first, reason = "matilda", "live information"
    elif default in available:
        first, reason = default, "default model"
    else:
        first, reason = available[0], "only option"
    return [first] + [name for name in available if name != first], reason


class RoutingProvider(Provider):
    def __init__(self, providers: dict[str, Provider], default: str = "claude"):
        if not providers:
            raise ValueError("RoutingProvider needs at least one provider")
        self.providers = providers
        self.default = default
        self.transcript: list[tuple[str, str]] = []  # (user, reply) text only
        self._last: str | None = None  # provider that answered the previous turn
        self.last_route: dict | None = None  # what happened on the latest turn
        self._answered: str | None = None

    @property
    def name(self) -> str:
        """The provider that answered the latest turn, for the turn log."""
        return self._answered or "auto"

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        order, reason = choose_order(user_text, list(self.providers), self._last, self.default)
        route = {"order": order, "reason": reason, "fallback_from": None, "errors": []}
        self.last_route = route
        error = None

        for name in order:
            provider = self.providers[name]
            self._answered = name
            if name != self._last and self.transcript:
                provider.replace_history(self.transcript)

            ran_tools = []

            def watch(tool_name, tool_input, result):
                ran_tools.append(tool_name)
                if on_tool_call:
                    on_tool_call(tool_name, tool_input, result)

            try:
                result = provider.run_turn(user_text, system_prompt, tool_definitions, run_tool, watch)
            except ProviderError as exc:
                route["errors"].append(f"{name}: {exc}")
                error = exc
                if ran_tools:
                    # A tool already changed something; retrying elsewhere could repeat it.
                    self._last = None  # its history may no longer match ours
                    raise ProviderError(
                        f"{name} failed after running {', '.join(ran_tools)}; not retrying on another model. {exc}"
                    ) from exc
                route["fallback_from"] = name
                continue

            self.transcript.append((user_text, result.text))
            self._last = name
            return result

        self._last = None
        raise ProviderError("; ".join(route["errors"])) from error

"""Provider selection. ASH_PROVIDER picks the model backend; Claude is the
default, so leaving it unset behaves exactly as before."""

import os

import anthropic

from providers.base import Provider, ProviderConfigError
from providers.claude import DEFAULT_MODEL, ClaudeProvider


def _build_claude() -> Provider:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ProviderConfigError(
            "ANTHROPIC_API_KEY isn't set in this terminal. "
            "Run: export ANTHROPIC_API_KEY=... (then start Ash again)"
        )
    return ClaudeProvider(anthropic.Anthropic(), DEFAULT_MODEL)


def _build_matilda() -> Provider:
    # Imported here so Claude-only setups don't need the Matilda SDK installed.
    from matilda_agent_sdk import MatildaClient, Runner

    from providers.matilda import MatildaProvider

    key = os.environ.get("MATILDA_API_KEY")
    if not key:
        raise ProviderConfigError(
            "MATILDA_API_KEY isn't set in this terminal. "
            "Run: export MATILDA_API_KEY=... (then start Ash again)"
        )
    base_url = os.environ.get("ASH_MATILDA_BASE_URL", "https://matilda.maincode.com/api")
    return MatildaProvider(Runner(MatildaClient(base_url=base_url, token=key)))


BUILDERS = {"claude": _build_claude, "matilda": _build_matilda}


def create_provider(name: str | None = None) -> Provider:
    name = (name or os.environ.get("ASH_PROVIDER") or "claude").strip().lower()
    if name not in BUILDERS:
        raise ProviderConfigError(
            f"unknown ASH_PROVIDER '{name}'. Options: {', '.join(sorted(BUILDERS))}"
        )
    return BUILDERS[name]()

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


BUILDERS = {"claude": _build_claude}


def create_provider(name: str | None = None) -> Provider:
    name = (name or os.environ.get("ASH_PROVIDER") or "claude").strip().lower()
    if name not in BUILDERS:
        raise ProviderConfigError(
            f"unknown ASH_PROVIDER '{name}'. Options: {', '.join(sorted(BUILDERS))}"
        )
    return BUILDERS[name]()

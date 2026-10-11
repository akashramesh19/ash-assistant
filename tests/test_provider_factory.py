import pytest

from providers import create_provider
from providers.base import ProviderConfigError
from providers.claude import ClaudeProvider


@pytest.fixture(autouse=True)
def claude_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.delenv("ASH_PROVIDER", raising=False)


def test_defaults_to_claude():
    assert isinstance(create_provider(), ClaudeProvider)


def test_flag_selects_provider_ignoring_case_and_spaces(monkeypatch):
    monkeypatch.setenv("ASH_PROVIDER", " Claude ")
    assert create_provider().name == "claude"


def test_unknown_provider_fails_clearly_and_lists_options(monkeypatch):
    monkeypatch.setenv("ASH_PROVIDER", "nope")
    with pytest.raises(ProviderConfigError) as error:
        create_provider()
    assert "nope" in str(error.value) and "claude" in str(error.value)


def test_claude_without_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        create_provider()

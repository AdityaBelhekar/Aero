"""Vast provider catalog: big-name APIs + OpenRouter-reaches-all (AERO-BRAIN-305)."""

from __future__ import annotations

from aero.cognition.providers import (
    PROVIDERS,
    openrouter_popular,
    provider,
)
from aero.cognition.registry import build_from_profile, registry


def test_big_name_providers_present():
    reg = registry()
    for pid in ("anthropic", "kimi", "cohere", "perplexity", "cerebras",
                "qwen", "nvidia"):
        assert pid in reg, f"{pid} missing from registry"
        assert pid in PROVIDERS
        assert provider(pid).auth == "key"      # direct APIs are key-based


def test_the_names_the_user_asked_for_are_covered():
    reg = registry()
    # claude, chatgpt, grok, gemini, kimi, deepseek — all connectable
    assert reg["anthropic"].model.startswith("claude")     # Claude
    assert "gpt" in reg["openai"].model                    # ChatGPT/OpenAI
    assert reg["xai"].model.startswith("grok")             # Grok
    assert reg["gemini"].model.startswith("gemini")        # Gemini
    assert reg["kimi"].base_url.startswith("https://api.moonshot")  # Kimi
    assert reg["deepseek"].model.startswith("deepseek")    # DeepSeek


def test_anthropic_builds_at_its_endpoint():
    llm = build_from_profile(registry()["anthropic"], api_key="k")
    assert "api.anthropic.com" in llm.base_url


def test_anthropic_vision_capable():
    assert registry()["anthropic"].supports_vision is True


def test_big_names_have_signup_urls():
    for pid in ("anthropic", "kimi", "cohere", "perplexity", "cerebras", "qwen", "nvidia"):
        assert provider(pid).signup_url.startswith("https://")


# -- openrouter reaches all of them (via one login) ------------------------
def test_openrouter_popular_covers_the_big_names():
    pop = openrouter_popular()
    assert pop["claude"].startswith("anthropic/")
    assert pop["chatgpt"].startswith("openai/")
    assert pop["grok"].startswith("x-ai/")
    assert pop["gemini"].startswith("google/")
    assert "deepseek" in pop and "kimi" in pop


def test_openrouter_is_still_the_login_aggregator():
    assert provider("openrouter").auth == "oauth"
    assert provider("openrouter").aggregator


def test_none_of_the_big_names_are_fake_logins():
    # Claude/OpenAI/Grok are key-only; they must NOT masquerade as login providers
    for pid in ("anthropic", "openai", "xai", "kimi", "deepseek"):
        assert provider(pid).auth == "key"

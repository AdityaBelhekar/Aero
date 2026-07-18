"""Expanded provider catalog (local + cloud) + metadata. Hermetic."""

from __future__ import annotations

from aero.cognition.providers import (
    PROVIDERS,
    cloud_ids,
    local_ids,
    oauth_ids,
    provider,
)
from aero.cognition.registry import build_from_profile, registry


# -- registry has the new providers ----------------------------------------
def test_new_local_providers_in_registry():
    reg = registry()
    for pid in ("lmstudio", "llamacpp", "jan", "vllm", "localai"):
        assert pid in reg
        assert reg[pid].is_local and reg[pid].is_private   # local => private
        assert reg[pid].key_env is None                    # keyless


def test_new_cloud_providers_in_registry():
    reg = registry()
    for pid in ("mistral", "deepseek", "together", "xai", "fireworks"):
        assert pid in reg
        assert not reg[pid].is_local and reg[pid].key_env


def test_local_providers_build_openai_at_localhost():
    reg = registry()
    llm = build_from_profile(reg["lmstudio"])
    assert "localhost:1234" in llm.base_url


def test_cloud_provider_builds_with_full_url():
    reg = registry()
    llm = build_from_profile(reg["mistral"], api_key="k")
    assert llm.base_url == "https://api.mistral.ai/v1"


# -- catalog metadata ------------------------------------------------------
def test_local_vs_cloud_split():
    assert "lmstudio" in local_ids() and "ollama" not in local_ids()
    assert "local" in local_ids()
    assert "openai" in cloud_ids() and "openai" not in local_ids()


def test_auth_kinds():
    assert provider("local").auth == "none"
    assert provider("openai").auth == "key"
    assert provider("openrouter").auth == "oauth"


def test_openrouter_is_oauth_aggregator():
    p = provider("openrouter")
    assert p.auth == "oauth" and p.aggregator
    assert p.oauth["flow"] == "pkce" and "auth_url" in p.oauth


def test_oauth_ids_only_legit_token_issuers():
    # providers with a real token-issuing login flow; NO subscription proxying
    assert set(oauth_ids()) == {"openrouter", "huggingface", "github"}
    # the ToS-violating ones must never be login providers
    assert "openai" not in oauth_ids() and "anthropic" not in oauth_ids()


def test_key_providers_have_signup_urls():
    for pid in cloud_ids():
        p = provider(pid)
        if p.auth == "key":
            assert p.signup_url.startswith("https://")


def test_every_provider_has_a_registry_profile():
    reg = registry()
    for pid in PROVIDERS:
        # 'local' provider maps to the built-in 'local' profile
        assert pid in reg, f"{pid} has no registry profile"

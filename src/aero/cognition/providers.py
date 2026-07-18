"""Provider catalog — the "connect any AI" metadata over the brain registry.

Each brain profile (registry.py) is *how to talk* to a model; a ``Provider`` here
is *how you connect to it*: is it local or cloud, does it need nothing / an API key
/ an OAuth login, is it an aggregator (one connection, many models), and where do
you sign up. This drives the Control-App "add a brain" flow and `aero brain
--providers/--discover/--login`.

Three auth kinds, all legitimate:
  * ``none``  — local servers (Ollama, LM Studio, llama.cpp, …). No account at all.
  * ``key``   — paste/store an API key (OpenAI, Groq, Mistral, …).
  * ``oauth`` — log in via the provider's real token-issuing flow. **OpenRouter**
    is the standout: its OAuth-PKCE flow hands your app a genuine API key, so
    "log in once → hundreds of models" works without touching any subscription.

Explicitly NOT modelled: piping a consumer ChatGPT/Claude *subscription* through a
reverse-proxied web session. That violates those providers' ToS; there is no
Provider entry for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provider:
    id: str                    # matches a registry BrainProfile id
    kind: str                  # "local" | "cloud"
    auth: str                  # "none" | "key" | "oauth"
    aggregator: bool = False   # one connection unlocks many models
    signup_url: str = ""       # where to get a key / make an account
    oauth: dict = field(default_factory=dict)  # oauth/device config when auth=="oauth"

    @property
    def is_local(self) -> bool:
        return self.kind == "local"

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "auth": self.auth,
                "aggregator": self.aggregator, "signup_url": self.signup_url,
                "oauth": bool(self.oauth)}


_PROVIDERS: tuple[Provider, ...] = (
    # -- local: no account, nothing leaves the device --
    Provider("local", "local", "none"),          # Ollama gemma4 default
    Provider("lmstudio", "local", "none"),
    Provider("llamacpp", "local", "none"),
    Provider("jan", "local", "none"),
    Provider("vllm", "local", "none"),
    Provider("localai", "local", "none"),
    # local-hosted aggregator (you auth providers inside the proxy, not in Aero)
    Provider("litellm", "local", "none", aggregator=True,
             signup_url="https://docs.litellm.ai/docs/proxy/quick_start"),
    # -- cloud via API key --
    Provider("groq", "cloud", "key", signup_url="https://console.groq.com/keys"),
    Provider("openai", "cloud", "key", signup_url="https://platform.openai.com/api-keys"),
    Provider("gemini", "cloud", "key",
             signup_url="https://aistudio.google.com/apikey"),
    Provider("mistral", "cloud", "key", signup_url="https://console.mistral.ai/api-keys"),
    Provider("deepseek", "cloud", "key", signup_url="https://platform.deepseek.com/api_keys"),
    Provider("together", "cloud", "key", signup_url="https://api.together.xyz/settings/api-keys"),
    Provider("xai", "cloud", "key", signup_url="https://console.x.ai"),
    Provider("fireworks", "cloud", "key",
             signup_url="https://fireworks.ai/account/api-keys"),
    # -- cloud via OAuth login (issues a real API key) --
    Provider("openrouter", "cloud", "oauth", aggregator=True,
             signup_url="https://openrouter.ai/keys",
             oauth={
                 # OpenRouter's PKCE flow: open auth_url, user approves, the
                 # callback code exchanges at token_url for a real API key.
                 "flow": "pkce",
                 "auth_url": "https://openrouter.ai/auth",
                 "token_url": "https://openrouter.ai/api/v1/auth/keys",
                 "note": "log in once, use hundreds of models",
             }),
)

PROVIDERS: dict[str, Provider] = {p.id: p for p in _PROVIDERS}


def provider(pid: str) -> Provider | None:
    return PROVIDERS.get(pid)


def local_ids() -> list[str]:
    return [p.id for p in _PROVIDERS if p.is_local]


def cloud_ids() -> list[str]:
    return [p.id for p in _PROVIDERS if not p.is_local]


def oauth_ids() -> list[str]:
    return [p.id for p in _PROVIDERS if p.auth == "oauth"]

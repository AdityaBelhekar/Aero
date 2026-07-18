# Open Brain — any model can power Aero (M8 / AERO-BRAIN-3xx)

Aero's personality lives in the **vault + persona prompt, never the weights**
(AERO-ID-002). So the "brain" is just a swappable engine: pick a **profile** and
Aero thinks with that model — same Aero, different mind. Switching is a CLI flag
today (a Control-App click later), never a code change.

```
aero brain                     # show the active brain + the whole registry
aero brain --set groq          # switch Aero's brain to a profile
```

## The registry

A **profile** is `{id, adapter, model, base_url, key_env, cost_tier, supports_vision}`.
Two adapters cover every brain:

| adapter | powers | private? |
|---|---|---|
| `ollama` | local models (gemma4:e4b default) | ✅ on-device |
| `openai` | anything speaking the OpenAI `/chat/completions` API — Groq, OpenAI, OpenRouter, Gemini, **or a local LiteLLM proxy** | ❌ prompt leaves device |

Built-in profiles: `local`, `groq`, `openai`, `openrouter`, `gemini`, `litellm`.
Add your own or override a built-in from `settings.json` under `brains`, e.g.:

```json
"brains": { "openai": { "model": "gpt-4o" },
            "mistral": { "adapter": "openai", "model": "mistral-large-latest",
                         "base_url": "https://api.mistral.ai/v1",
                         "key_env": "MISTRAL_API_KEY" } }
```

or from the CLI: `aero brain --set openai --model gpt-4o`.

## Keys (never in settings.json)

API keys resolve **OS keyring → the profile's `key_env` → legacy env fallback**.
The keyring is the recommended store:

```
pip install -e ".[keyring]"            # once (Linux: uses GNOME Keyring / KWallet)
aero brain --set-key groq  <your-key>  # stored in the OS keyring, not on disk
aero brain --del-key groq              # remove it
```

No keyring backend? Aero degrades to environment variables — set the profile's
`key_env` (e.g. `export GROQ_API_KEY=...`) and it just works.

## LiteLLM — ~100 providers behind one seam (AERO-BRAIN-302)

The **recommended power path.** [LiteLLM](https://docs.litellm.ai/) runs a local
proxy that speaks the OpenAI API and fans out to ~100 providers. Aero already
speaks OpenAI, so one profile (`litellm`, pointing at `localhost:4000`) unlocks
all of them with zero adapter code — and the proxy holds the real keys, so Aero
stays keyless.

```bash
pip install "litellm[proxy]"
export OPENAI_API_KEY=sk-...            # (whatever providers you want it to reach)
litellm --model gpt-4o-mini --port 4000 # or a config.yaml with many models
```

Then:

```
aero brain --set litellm                # talk through the proxy
aero brain --set litellm --model claude-3-5-sonnet-latest   # any model it exposes
```

The proxy also gives you one place for cost tracking, rate limits, and fallbacks
across providers.

## Two-speed router — cheap for reflex, strong for talk (AERO-BRAIN-303)

Consolidation tags your memories constantly in the background (`complete_json`).
Sending that structured-output job to a paid frontier model burns money for
nothing. The router splits the roles:

```
aero brain --primary groq --reflex local   # talk to Groq; tag/consolidate on local gemma4
aero brain --private-only                   # refuse a cloud primary; keep talk on-device
aero brain --shared                         # allow a cloud primary again
```

- **chat** → the *primary* brain (strong).
- **tagging / reflex** (`complete_json`) → the *reflex* brain (cheapest reliable).
- **degrade, never die** — if the primary is offline/out-of-credits mid-turn,
  chat transparently falls back to the reflex brain.
- **privacy** — `--private-only` refuses a non-private primary, so personal talk
  never leaves the device even if a cloud profile is configured.

Set the same profile for both roles (or neither) for plain single-brain mode —
that's the default, identical to pre-M8 behaviour.

## Per-session override

Any command that thinks takes `--brain <profile>` to pin the *primary* for one
run (reflex/tagging stays local):

```
aero chat  --brain groq
aero voice --brain litellm
```

## Connect any AI — local, key, or login (AERO-BRAIN-305)

Aero connects to models three legitimate ways. See the whole catalog:

```
aero brain --providers      # every provider: kind (local/cloud) + how to connect
```

### 1. Local — no account, nothing leaves the device

Ollama (default) plus any OpenAI-compatible local server: **LM Studio, llama.cpp,
Jan, vLLM, LocalAI**. Aero can find the ones you're running:

```
aero brain --discover       # probes each local port, lists what's up + its models
aero brain --set lmstudio   # use it (already a built-in profile)
```

A local server is **private** (localhost, no key) — unlike the LiteLLM proxy,
which is local-hosted but forwards to the cloud.

### 2. Cloud by API key

Groq, OpenAI, Gemini, Mistral, DeepSeek, Together, xAI, Fireworks:

```
aero brain --set-key mistral <key>    # stored in the OS keyring
aero brain --set mistral
```

### 3. Login (OAuth) — "log in once → any model"

For providers with a real token-issuing flow. **OpenRouter** is the one to know:
its OAuth-PKCE login hands Aero a genuine API key that reaches hundreds of models:

```
aero brain --login openrouter    # opens the browser, captures the code, stores the key
aero brain --set openrouter
```

> **Not supported (on purpose):** using a consumer **ChatGPT / Claude Pro
> subscription** as an API brain. Those subscriptions are the chat *product*, not
> API access; the only way to fake it is a reverse-proxied web session, which
> violates those providers' Terms of Service and risks a ban. Aero has no such
> path. If you want cheap cloud, a **free Groq key** or **OpenRouter login** is the
> legitimate answer.

## Offline / plane test (Rule 9)

Turn off every cloud profile and Aero still runs entirely on `local` — thinks,
tags, remembers. Every cloud capability has a local fallback; the brain is no
exception.

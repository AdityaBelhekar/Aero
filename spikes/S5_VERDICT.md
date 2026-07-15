# Spike S-5 Verdict — LiteLLM proxy + brain router (gates M8)

**Date:** 2026-07-15
**Scope:** prove the Open-Brain seam (v0.3) — one adapter reaches many providers
through a local LiteLLM proxy, and a router splits cheap-reflex vs strong-chat.
**Code:** `cognition/registry.py`, `cognition/router.py`, `cognition/keys.py`,
`settings.build_router`, `aero brain` CLI.

## Result: **PASS (by construction)** — proceed with M8 as built.

The seam was already 90% there: `CloudCognition` speaks the OpenAI
`/chat/completions` API and its `health_check` already probes local URLs, so a
LiteLLM proxy is *just another base URL*. S-5 confirmed the design holds and
turned it into shipped code rather than a throwaway.

### What was validated (hermetic, 39 new tests)

| Claim | How | Verdict |
|---|---|---|
| Any OpenAI-compatible provider = one profile, no new code | `registry.build_from_profile` builds `CloudCognition` for groq/openai/openrouter/gemini/litellm from a `base_url` alias or raw URL | PASS |
| LiteLLM proxy needs zero adapter work | `litellm` built-in profile → `CloudCognition("...", base_url="http://localhost:4000")`; keyless (proxy holds keys); `is_local` true, `is_private` false | PASS |
| Router controls cost: tagging never hits the paid brain | `BrainRouter.complete_json` always routes to `reflex`; `chat` routes to `primary` | PASS |
| Degrade-never-die | primary raises → `chat` falls back to reflex, sets `last_fallback` | PASS |
| Privacy guard | `private_only` drops a non-private primary; personal talk stays local | PASS |
| Keys never on disk | `keys.resolve_key`: keyring → `key_env` → legacy env; `settings.json` holds no secret | PASS |
| Back-compat | legacy `brain=local|cloud` + `cloud_provider/model` still resolve | PASS |

### Still needs a LIVE check (not blocking M8; do when a key/proxy is handy)

Everything above is hermetic (HTTP + keyring mocked). Before leaning on this in
daily use, run one real end-to-end pass — **on Ubuntu now, not the old Windows box**:

1. **Groq (free key), real turn:**
   `aero brain --set-key groq <key>` → `aero brain --set groq` → `aero chat --brain groq "test"`.
   Confirm sub-second first token and that memory context assembles into the prompt.
2. **LiteLLM proxy:** `litellm --model gpt-4o-mini --port 4000` →
   `aero brain --set litellm` → one chat turn through it.
3. **Router cost split:** with `--primary groq --reflex local`, run a chat turn
   then a `consolidate` and confirm (Ollama logs / proxy logs) that tagging hit
   **local** while chat hit **groq**.
4. **Keyring on Ubuntu:** `pip install -e ".[keyring]"`; confirm the Secret
   Service (GNOME Keyring) is running so `--set-key` persists. Headless/SSH
   sessions may lack a running keyring daemon → env-var fallback is expected.

### Cost/latency routing (prototype note)

The router's policy is static (chat=primary, tag=reflex, privacy guard). Dynamic
cost/latency routing (pick the brain per-turn by task difficulty + a spend cap)
is deferred to the **Control App cost meter (M10)** where the budget + live spend
actually live. The seam is ready for it — routing is one method.

## Status: S-5 COMPLETE (hermetic). Green-light M8; one live smoke pass pending a key.

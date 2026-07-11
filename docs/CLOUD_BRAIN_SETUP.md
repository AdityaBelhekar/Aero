# Aero's Cloud Brain (the real-time "online boost")

Aero's brain is swappable. **Local `gemma4:e4b` is the private default** — but on a
CPU box it's ~5–11 s per reply. The **cloud brain** routes generation to an
OpenAI-compatible API for **sub-second, real-time** responses.

**Memory is untouched.** The vault, consolidation, retrieval, and core identity
all still run locally, exactly as before. The cloud only *generates the words*
from the same memory-in-the-loop context gemma4 gets. Aero without memory is
generic ChatGPT; Aero *with* your memory fed in is still Aero — just faster.

> **Privacy:** with the cloud brain, each turn's prompt — including the assembled
> memory **context** — is sent to the provider to generate the reply. It's never
> *stored* there (memory lives in your local encrypted vault), but the text does
> transit the network. That's why local is the default and cloud is opt-in.

There are two ways to connect. **Option A** uses your ChatGPT subscription (no
API key). **Option B** uses a free/official API key. Aero doesn't care which —
both expose an OpenAI-compatible endpoint the cloud brain points at.

---

## Option A — ChatGPT Plus/Pro via login (no API key)

Uses your existing **ChatGPT Plus ($20/mo) or Pro** subscription through OpenAI's
official OAuth (the same flow Codex CLI / Cline / OpenClaw use). No per-token
billing, no API key. A local **LiteLLM** proxy does the login and bridges it to
an OpenAI-compatible endpoint that Aero talks to.

**1. Install LiteLLM** (its own venv keeps Aero's env clean):
```powershell
python -m venv .venv-litellm
.\.venv-litellm\Scripts\python.exe -m pip install "litellm[proxy]"
```

**2. Create `litellm-chatgpt.yaml`:**
```yaml
model_list:
  - model_name: chatgpt/gpt-5.4
    model_info: { mode: responses }
    litellm_params: { model: chatgpt/gpt-5.4 }
```
(Models available: `gpt-5.4`, `gpt-5.4-pro`, `gpt-5.3-codex`, and `-instant`
variants — an `-instant` model is snappiest for real-time voice.)

**3. Start the proxy and log in** (one-time OAuth device-code flow — it prints a
URL + code; open it, sign into ChatGPT, approve):
```powershell
.\.venv-litellm\Scripts\litellm.exe --config litellm-chatgpt.yaml
# runs on http://localhost:4000 ; tokens are cached for reuse
```

**4. Point Aero at the local proxy** (no key needed for a local proxy — Aero
detects `localhost` and skips auth):
```powershell
python -m aero.cli brain --set cloud --provider http://localhost:4000/v1 --model chatgpt/gpt-5.4
python -m aero.cli chat --brain cloud
```
> Note: the ChatGPT backend ignores `max_tokens`, so the two-speed brain's reply
> caps won't shorten cloud replies (LiteLLM strips the field — no error). Keep
> replies tight via the persona/prompt if needed.

---

## Option B — free/official API key

**Google Gemini** (free, no credit card — recommended free path):
1. Get a key at https://aistudio.google.com
2. ```powershell
   setx AERO_BRAIN_API_KEY "your_gemini_key"      # open a NEW terminal after
   python -m aero.cli brain --set cloud --provider gemini --model gemini-2.0-flash
   ```

Other OpenAI-compatible providers work the same way — set the key env var and
pick the provider: **Groq** (`groq`, free ~1k/day, fastest), **OpenAI**
(`openai`, paid), **OpenRouter** (`openrouter`). The key env var can be
`AERO_BRAIN_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` /
`GEMINI_API_KEY`.

---

## Everyday use

```powershell
python -m aero.cli brain                 # show current brain + key/proxy status
python -m aero.cli brain --set cloud     # use the cloud brain
python -m aero.cli brain --set local     # back to private gemma4
python -m aero.cli chat  --brain cloud   # per-session override, no persist
python -m aero.cli voice --brain cloud
```

If the cloud brain is unreachable (proxy down / no key / offline), Aero
automatically falls back to local gemma4 and tells you — nothing breaks.

## 3. Providers & models

| Provider    | `--provider` | Example `--model`          | Notes                    |
|-------------|--------------|----------------------------|--------------------------|
| Groq        | `groq`       | `llama-3.3-70b-versatile`  | **free**, fastest        |
| OpenAI      | `openai`     | `gpt-4o-mini`              | paid, cheap, GPT quality |
| OpenRouter  | `openrouter` | many                       | one key, many models     |
| Gemini      | `gemini`     | `gemini-2.0-flash`         | free tier                |

You can also pass a full base URL to `--provider` for any other OpenAI-compatible
endpoint (including a self-hosted one).

## Notes
- The two-speed brain (reflex vs deep memory, see `effort.py`) still applies —
  with the cloud brain, both speeds are fast; the tiering then mainly saves
  tokens/cost and keeps deep memory for turns that need it.
- Your selection persists in `AERO_HOME/settings.json`. The **API key is never
  written there** — it's read from the environment each run.

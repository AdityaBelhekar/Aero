"""Discover which local model servers are actually running (AERO-BRAIN-305).

"Local through Ollama and other providers" is only friendly if Aero can *find*
what you've already got running. This probes each local provider's endpoint (a
cheap GET) and reports which are up and what models they expose — so the Control
App can say "LM Studio is running with 3 models — use it?" instead of making you
know ports.

The prober is injected, so this is testable without any server; the default uses
a short-timeout urllib GET (stdlib only).
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable

from aero.cognition.providers import local_ids
from aero.cognition.registry import registry

# probe(url) -> parsed JSON dict if the server answered, else None.
Prober = Callable[[str], "dict | None"]


def _probe_url(profile) -> str:
    """The endpoint to hit to tell if a local provider is up + list its models."""
    if profile.adapter == "ollama":
        return "http://localhost:11434/api/tags"
    return profile.base_url.rstrip("/") + "/models"


def _default_probe(url: str, timeout: float = 0.7) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _models_from(payload: dict) -> list[str]:
    # Ollama: {"models": [{"name": ...}]}; OpenAI: {"data": [{"id": ...}]}
    if "models" in payload:
        return [m.get("name", "") for m in payload["models"] if isinstance(m, dict)]
    if "data" in payload:
        return [m.get("id", "") for m in payload["data"] if isinstance(m, dict)]
    return []


def discover_local(*, probe: Prober | None = None) -> list[dict]:
    """Probe every local provider. Returns one entry per provider with whether
    it's running and any models it advertises."""
    probe = probe or _default_probe
    reg = registry()
    out = []
    for pid in local_ids():
        prof = reg.get(pid)
        if prof is None:
            continue
        url = _probe_url(prof)
        payload = probe(url)
        out.append({
            "id": pid,
            "running": payload is not None,
            "url": url,
            "models": _models_from(payload) if payload else [],
        })
    return out


def running_local(*, probe: Prober | None = None) -> list[dict]:
    """Just the local providers that are actually up right now."""
    return [d for d in discover_local(probe=probe) if d["running"]]

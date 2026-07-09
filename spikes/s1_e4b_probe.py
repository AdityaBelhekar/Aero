"""Spike S-1 — Gemma 4 E4B viability probe.

This is the go/no-go for the whole local-model stack (implementation plan §2).
It answers three questions on the *actual target hardware*:

  1. THROUGHPUT  — tokens/sec sustained. Plan kill criterion: < 8 tok/s.
  2. CODE-SWITCH — can it hold a natural English/Hindi/Marathi mixed chat in
     Aero's register (casual friend, not customer service)?
  3. JSON TAGGING — can it reliably emit the structured tags consolidation needs
     (AERO-WRT-001)? This is the one most likely to quietly fail.

Run (after `ollama pull gemma4:e4b`):
    python spikes/s1_e4b_probe.py

It prints a verdict block you can paste into the spike's written conclusion. It
is a throwaway diagnostic, but it drives the real OllamaCognition backend, so a
green run also proves the production path works.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aero.cognition.ollama_backend import OllamaCognition  # noqa: E402
from aero.cognition.service import ChatMessage  # noqa: E402

KILL_TOKENS_PER_SEC = 8.0

AERO_SYSTEM = (
    "You are Aero, a casual local AI companion for one friend named Aditya. "
    "You speak like a close friend, not a customer-service bot. You naturally "
    "mix English, Hindi and Marathi the way he does. Keep replies short."
)


def probe_throughput(llm: OllamaCognition) -> float:
    print("\n[1/3] THROUGHPUT")
    res = llm.chat(
        [
            ChatMessage("system", AERO_SYSTEM),
            ChatMessage("user", "explain in 3 short lines why you run locally on my laptop"),
        ],
        temperature=0.6,
        max_tokens=200,
    )
    s = res.stats
    print(textwrap.indent(res.text.strip(), "    "))
    print(f"    prompt_tokens={s.prompt_tokens} completion_tokens={s.completion_tokens}")
    print(f"    total={s.total_seconds:.2f}s load={s.load_seconds:.2f}s")
    print(f"    -> {s.tokens_per_second:.1f} tok/s")
    return s.tokens_per_second


def probe_codeswitch(llm: OllamaCognition) -> None:
    print("\n[2/3] CODE-SWITCH + REGISTER")
    turns = [
        "bhai ye assignment ka deadline kal aahe and I haven't started, kay karu",
        "arey but mala Valorant khelaycha aahe na",
    ]
    history: list[ChatMessage] = [ChatMessage("system", AERO_SYSTEM)]
    for t in turns:
        history.append(ChatMessage("user", t))
        res = llm.chat(history, temperature=0.8, max_tokens=160)
        reply = res.text.strip()
        history.append(ChatMessage("assistant", reply))
        print(f"    USER: {t}")
        print(textwrap.indent(f"AERO: {reply}", "    "))
        print()


def probe_json_tagging(llm: OllamaCognition) -> tuple[int, int]:
    print("[3/3] JSON TAGGING (consolidation path, AERO-WRT-001)")
    schema_hint = (
        "Extract memory tags from the event. Respond with ONLY a JSON object of "
        "the form: {\"summary\": str, \"topics\": [str], \"emotion\": str, "
        "\"is_failure\": bool, \"roast_value\": number 0..1, "
        "\"sensitivity\": number 0..1, \"associations\": [str]}."
    )
    events = [
        "Aditya bottom-fragged in Valorant and blamed his mouse again.",
        "Aditya abandoned a new AI project at 2am after starting it enthusiastically.",
        "Aditya said he prefers medium roast coffee now, the dark one is too bitter.",
        "Aditya got frustrated: the same build error kept happening for an hour.",
    ]
    required = {"summary", "topics", "emotion", "is_failure", "roast_value",
                "sensitivity", "associations"}
    ok = 0
    for ev in events:
        parsed, res = llm.complete_json(
            [
                ChatMessage("system", schema_hint),
                ChatMessage("user", ev),
            ],
            temperature=0.2,
            max_tokens=300,
        )
        valid = isinstance(parsed, dict) and required.issubset(parsed.keys())
        mark = "OK " if valid else "BAD"
        print(f"    [{mark}] {ev[:52]}...")
        if valid:
            ok += 1
            print(textwrap.indent(json.dumps(parsed, ensure_ascii=False), "        "))
        else:
            print(textwrap.indent((res.text or "<empty>")[:200], "        "))
    return ok, len(events)


def main() -> int:
    llm = OllamaCognition()
    print(f"Model: {llm.model_name}   Host: {llm.host}")
    if not llm.health_check():
        print("\nFAIL: Ollama not reachable or model not pulled.")
        print("  Start Ollama and run:  ollama pull gemma4:e4b")
        return 1

    tps = probe_throughput(llm)
    probe_codeswitch(llm)
    ok, total = probe_json_tagging(llm)

    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    tps_pass = tps >= KILL_TOKENS_PER_SEC
    json_pass = ok == total
    print(f"  throughput : {tps:.1f} tok/s   "
          f"{'PASS' if tps_pass else f'FAIL (<{KILL_TOKENS_PER_SEC})'}")
    print(f"  json tagging: {ok}/{total} valid   {'PASS' if json_pass else 'FAIL'}")
    print("  code-switch : review the [2/3] replies by eye (register + language mix)")
    overall = tps_pass and json_pass
    print(f"\n  S-1 automated gates: {'PASS' if overall else 'FAIL'} "
          "(code-switch is a human judgement)")
    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())

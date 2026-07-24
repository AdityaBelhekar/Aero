# Proactivity — Aero notices, and mostly stays silent (M4 / PRD §7)

The feature that makes Aero not-a-chatbot: it can initiate. "Initiate" here means
the decision to engage **at all**, whose overwhelming default is silence
(AERO-PRO-002). Silence is a first-class output.

```
aero proactive status                       # gate state + relationship + threads + recent decisions
aero proactive threads                      # list thought threads
aero proactive thread-add "maybe we approached this backwards" --trigger impulse.py --trigger generator
aero proactive thread-resolve <id>          # close a thread (explicitly done/superseded)
aero proactive feedback dont_interrupt --app code.exe   # teach the gate
aero proactive simulate --app impulse.py --title "generator.py" --activity idle --hour 14
```

Nothing here needs hardware. `simulate` runs one full gate tick against a
described moment — the whole loop is hermetic and deterministic.

## Two tiers, by cost (AERO-PRO-003)

Continuous LLM inference is unaffordable, so proactivity is split:

- **Tier 1 — impulse generation** (`proactive/generator.py`): cheap, continuous,
  **no model**. Every daemon tick, plain heuristics watch world-state *deltas* and
  emit **impulses** — candidate reasons to engage, each carrying a `source`, a
  `strength` (0..1), and a `decay_seconds`. Producers: app-switch novelty,
  return-from-away, repeated-failure, thought-thread reactivation.
- **Tier 2 — impulse gate** (`proactive/gate.py`): the LLM social evaluation runs
  **only** after an impulse clears a context-dependent threshold. Its default
  output is still silence — a confident "speak" with a real one-line utterance is
  the exception, not the rule.

## Default silence is structural (like the consent gate)

The rules that keep Aero quiet are **code**, not prompt guidance a clever context
could talk around. `ImpulseGate.evaluate` says *silent* — never speaks — on any
of these, cheapest first, and only the last one ever spends a token:

1. **kill switch on** → silent (no initiative at all).
2. **quiet hours** → silent (persona `quiet_hours`; default 1am–8am).
3. **impulse stale** → silent — the moment passed; late proactive speech is
   discarded, never delivered.
4. **strength below threshold** → silent, **without a model call** (the ~90% path).
5. **LLM social eval** → still defaults to silence; a broken/absent brain degrades
   to silence too. It never *forces* speech.

**Never timer-based (AERO-PRO-001):** no producer keys on elapsed idle time. A
world that simply sits still — however long — produces zero impulses. Only deltas
and content triggers do. "Return from away" is a *state transition*, which is
allowed; "it's been 10 minutes, say something" is impossible by construction.

## The context threshold (AERO-PRO-004)

`proactive/threshold.py` — higher = quieter Aero:

- active/typing → **raise** (never interrupt focus); present-but-idle → **lower**
  (a good moment); away → **raise hard** (no audience).
- `chattiness` dial lowers it; low `familiarity` raises it (cold-start
  conservatism, AERO-COLD-003).
- an explicit "talk to me" pulls it right down (but never to zero).
- quiet hours push it past the ceiling — Aero cannot speak.

## Every decision is remembered (AERO-PRO-006)

Silences included. `proactive/selfmem.py` logs each gate decision to
`self_memory` with its reasoning, so a suppressed impulse can inform a later
moment ("I noticed this earlier but you were busy").

## The gate learns (AERO-PRO-005 / AERO-FBK-003)

Feedback routes to the right store:

- **interruption tolerance → gate threshold** (persisted in settings):
  `dont_interrupt` (explicit, durable, can be `--app`-scoped), `talk_more`,
  `good_call`, and the passive `ignored`/`interrupted` (slow movement).
- **joke/quality reactions → relationship dimensions** (in the vault):
  slow-moving `trust`, `familiarity`, etc., each capped per nudge (AERO-REL-003)
  so one bad evening can't crater trust and one good joke can't unlock roast mode.

## Thought threads (AERO-THT-001/002)

`proactive/threads.py` — a persistent *unresolved* idea with reactivation
triggers (file paths, topics, projects, people). Lifecycle: active → dormant
(aged out) → resolved. Active cap of 20 keeps the working set from flooding. When
the world matches a trigger, the thread reactivates into a THOUGHT_THREAD impulse
— a strong reason to speak, because Aero has been sitting on it.

## Where it runs

The daemon calls `ProactiveLoop.tick()` each tick (`daemon._maybe_proact`),
wrapped so a bad proactive tick can never take the companion down. A gate "speak"
surfaces as a **quiet text message** on the `proactive` raw-event channel (M4
surface: text first; voice proactivity comes only after text proves calibrated).
Turn the whole thing off with `settings.proactive["enabled"] = false`.

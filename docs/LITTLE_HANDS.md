# Little Hands — Aero doing things, safely (M12 / AERO-ACT-5xx)

Pillar 5 of v0.3. Aero *can* do things on your machine — open an app, a URL,
control media, organise a folder you allowed — but framed as **a friend doing you
a favour**, always opt-in, never an autonomous agent. This was the plan's *safety
milestone*: nothing here runs without passing the consent gate, and that's proven
by the S-10 red-team (`spikes/S10_VERDICT.md`).

```
aero hands tools                       # what Aero can do + the scope each needs
aero control perms.grant '{"scope":"browser","on":true}'   # allow a scope
aero hands run open_url '{"url":"https://x"}'              # run it (gated + logged)
aero hands run empty_trash --confirm   # hard-gate action needs explicit confirm
aero hands log                         # everything Aero did or was stopped from doing
```

## The layers

```
Tool          one atomic action; declares scope + reversible + hard_gate + run
ToolRegistry  the typed catalog
ConsentGate   the decision (code, not prompt): allow / confirm / refuse
ActuatorJournal every attempt recorded (allow/confirm/refuse, executed?, outcome)
HandsExecutor  the ONLY path a tool runs — registry -> gate -> journal -> invoke
```

Skills (user-authored recipes) and MCP tools both run *through the same executor*,
so they can't sidestep the gate.

## The consent gate (AERO-ACT-502/503/507)

Decision order, most restrictive first:

1. **kill switch on** → REFUSE everything (`aero control perms.killswitch '{"on":true}'`).
2. **scope not granted** → REFUSE + explain (default-deny).
3. **hard-gate or irreversible** → CONFIRM: delete/send/buy/post never go silent,
   even with the scope granted (AERO-AUTH-002). Confirmed → ALLOW.
4. **reversible + granted** → ALLOW.

Grants + kill switch live in your settings (M10) and are read **live**, so
revoking a scope or hitting the kill switch takes effect on the very next call.

## Scopes

`apps`, `files`, `media`, `browser`, `shell` (high-risk, off by default), `games`,
`screen`, `camera`, `mcp`. All default-deny. Grant/revoke in the Control App
Permissions panel or via `aero control perms.grant`.

## Skills (AERO-ACT-505)

A skill is **data, not code** — a JSON recipe of ordered tool calls:

```json
{ "name": "wind_down", "description": "pause music, open the journal",
  "steps": [ {"tool": "media_control", "params": {"action": "pause"}},
             {"tool": "open_app", "params": {"name": "journal"}} ] }
```

Each step runs through the executor (gated + journalled). A skill stops at the
first step the gate blocks — it can never smuggle a denied action past you.

## MCP bridge (AERO-ACT-506)

Existing MCP-server tools become Aero tools in the `mcp` scope, behind the same
gate — "any tool" the way LiteLLM is "any model". Bridged tools are **conservative
by default** (treated as irreversible → confirm path), since a third-party tool's
effect is unknown. The transport (a real MCP client session) is injected, so the
bridge is testable now and wiring a live client later is just supplying that
connection.

## Accountability (AERO-ACT-504)

Every attempt — run, refused, or awaiting confirmation — is in the `actuator_log`
table with tool, scope, params, verdict, reason, and outcome. `aero hands log` (or
the `hands.log` control op) shows it. This is separate from the vault's memory
`audit_log`: one is the log of the *hands*, the other of *memory writes*.

## Status & the honest caveat

The framework — gate, journal, executor, skills, MCP bridge — is complete and
S-10-verified. The **starter tools currently echo their intent** rather than
driving the real OS (except `list_files`, a safe read-only listing). Wiring each
tool to a real platform action (xdg-open, media keys, file moves in an allowed
folder) changes only the tool's `run` body — never the safety machinery — and
each new `run` gets a per-tool review that its `reversible`/`hard_gate` flags are
honest, then a re-run of S-10.

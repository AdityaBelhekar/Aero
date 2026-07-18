# Play — Aero games with you (M14 / AERO-PLAY-7xx)

Pillar 7 of v0.3. The friend who actually joins in. Two modes, decided per game
and enforced in code:

- **play** — your own Minecraft LAN world: Aero joins as a bot, sees the world,
  and acts (mine/build/follow/say) — a game-scoped actuator under the consent
  model.
- **spectate** — competitive games (Valorant, CS): Aero **never touches the
  game**. He watches through Eyes (M13) and reacts/roasts. Vision only, zero input.

```
aero play games                          # every game + its play/spectate policy
aero play status minecraft               # policy + grant + bridge reachability
aero control perms.grant '{"scope":"games","on":true}'   # allow acting in games
aero play act say '{"text":"chal bhai"}' # gated action to the Minecraft bridge
```

## Anti-cheat is structural (AERO-PLAY-705)

The play/spectate `mode` is the anti-cheat boundary and it lives in code, not
policy text:

- A **spectate-only game refuses every action** at the `GameSession` layer,
  regardless of the `games` grant or the kill switch — Aero literally cannot send
  input to Valorant.
- **Unknown games default to spectate** (fail safe): Aero won't auto-act on a game
  without an explicit play policy.
- A **play game** still needs the `games` scope granted (kill switch forces off).

The `Spectator` class has no `act` method at all — for a game Aero watches, the
only capability that exists is looking.

## Minecraft bridge (AERO-PLAY-702)

Aero joins via a headless **Mineflayer** bot (Node) that logs into your LAN world
and exposes a local JSON-lines socket; the Python `MinecraftConnector` talks to it.

1. **Open your world to LAN** (in-game: Esc → Open to LAN), note the port.
2. **Run the bridge** (a small Node script using [mineflayer](https://github.com/PrismarineJS/mineflayer)
   that listens on `127.0.0.1:25599` and maps `{op, params}` lines to bot calls —
   `join`, `observe`, `say`, `mine`, `place`, `follow`, `goto`, `stop`, `collect`).
   The op/response contract is the JSON-lines shape `MinecraftConnector` sends;
   `observe` should return `{position, health, inventory, entities, chat}`.
3. **Check it:** `aero play status minecraft` → *bridge: reachable*.
4. **Play:** grant `games`, then `aero play act ...` or drive the fusion loop.

> The bot side is a small Node process you run alongside Aero; the Python side
> ships here. Keeping them split means the same connector interface works for any
> future game bridge.

## The magic moment — voice + game + avatar fusion (AERO-PLAY-703)

`PlayFusion` ties it together: it observes the game, asks the brain (M8) how to
react, speaks it (voice M11), posts to in-game chat, and drives the avatar (M9) to
talk + emote in sync — all from one `react(user_said=...)` call. You say something
in the world; Aero answers, acts, and his face reacts. Every in-game action + chat
post still passes through `GameSession`, so play policy + the `games` grant apply;
talking and emoting are always free.

## Spectator (AERO-PLAY-704)

For a spectate game: `Spectator.watch()` captures the screen (needs the `screen`
grant, M13) and a vision brain comments in one line — hype, a roast, a dry
"...okay that was clean". No input reaches the game, ever.

## Status

The framework — connector interface, anti-cheat policy, Minecraft connector,
spectator, and fusion — is complete and tested (incl. an anti-cheat red-team). The
only external piece is the **Node Mineflayer bridge**, which you run against your
own world; until it's up, `aero play status` shows *bridge not running* and
actions report it cleanly rather than failing.

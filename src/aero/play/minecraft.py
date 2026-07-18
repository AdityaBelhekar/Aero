"""Minecraft LAN bridge connector (AERO-PLAY-702).

Aero joins your **LAN Minecraft world** through a headless bot. The bot itself is
a small Node process (Mineflayer) that logs into the world and exposes a local
JSON-lines socket; this connector is the Python side that talks to it — observe
state, send actions (mine/build/follow/say). See docs/PLAY_SETUP.md for standing
up the bridge.

The transport is injected (``BotTransport``), so this is testable without a
server and the real socket is one small class. All actions still flow through
``GameSession`` (M14.1), so the play/spectate policy + the ``games`` grant apply —
this connector never decides consent on its own.
"""

from __future__ import annotations

import json
import socket
from abc import ABC, abstractmethod

from aero.play.connector import GameAction, GameConnector, GameState

DEFAULT_BRIDGE_PORT = 25599   # the Mineflayer bridge's local socket


class BotTransport(ABC):
    @abstractmethod
    def request(self, op: str, params: dict | None = None) -> dict:
        ...

    @abstractmethod
    def available(self) -> bool:
        ...


class SocketBotTransport(BotTransport):
    """JSON-lines over a loopback TCP socket to the Mineflayer bridge. One request
    per connection (bot actions are low-frequency relative to a socket setup)."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_BRIDGE_PORT,
                 *, timeout: float = 10.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def available(self) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=1.0):
                return True
        except OSError:
            return False

    def request(self, op: str, params: dict | None = None) -> dict:
        line = json.dumps({"op": op, "params": params or {}}) + "\n"
        try:
            with socket.create_connection((self.host, self.port),
                                          timeout=self.timeout) as s:
                s.sendall(line.encode("utf-8"))
                buf = b""
                while b"\n" not in buf:
                    chunk = s.recv(65536)
                    if not chunk:
                        break
                    buf += chunk
        except OSError as e:
            # bridge not running / unreachable -> a clean result, never a raise
            return {"ok": False, "error": f"minecraft bridge unreachable: {e}",
                    "connected": False}
        raw = buf.split(b"\n", 1)[0]
        return json.loads(raw.decode("utf-8")) if raw else {}


class MinecraftConnector(GameConnector):
    game = "minecraft"

    #: actions the bridge understands (kept explicit so a typo'd action is caught
    #: here rather than silently sent to the bot)
    ACTIONS = ("say", "mine", "place", "follow", "goto", "stop", "look", "collect")

    def __init__(self, transport: BotTransport | None = None, *,
                 host: str = "127.0.0.1", port: int = DEFAULT_BRIDGE_PORT):
        self.transport = transport or SocketBotTransport(host, port)

    def available(self) -> bool:
        return self.transport.available()

    def _state_from(self, d: dict) -> GameState:
        pos = d.get("position")
        position = (pos["x"], pos["y"], pos["z"]) if isinstance(pos, dict) else (
            tuple(pos) if isinstance(pos, (list, tuple)) and len(pos) == 3 else None)
        return GameState(
            game=self.game,
            connected=bool(d.get("connected", True)),
            position=position,
            health=d.get("health"),
            inventory=list(d.get("inventory") or []),
            entities=list(d.get("entities") or []),
            chat=list(d.get("chat") or []),
            raw=d,
        )

    def join(self, *, username: str = "Aero", host: str | None = None,
             port: int | None = None) -> GameState:
        params = {"username": username}
        if host:
            params["host"] = host
        if port:
            params["port"] = port
        return self._state_from(self.transport.request("join", params))

    def observe(self) -> GameState:
        return self._state_from(self.transport.request("observe"))

    def act(self, action: GameAction) -> dict:
        if action.kind not in self.ACTIONS:
            return {"ok": False, "error": f"unknown minecraft action: {action.kind}"}
        return self.transport.request(action.kind, action.args)

    def leave(self) -> None:
        try:
            self.transport.request("leave")
        except Exception:
            pass

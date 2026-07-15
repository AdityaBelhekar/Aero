"""Local IPC for the control plane (AERO-APP-201).

The daemon runs headless; the Control App and the avatar overlay attach to it as
thin clients. This is that attachment point: a tiny JSON-lines request/response
protocol over a **local-only** socket.

  * Linux/macOS: a Unix-domain socket at ``AERO_HOME/control.sock`` (filesystem
    permissions gate access; nothing binds a network port).
  * Windows: a loopback TCP socket on 127.0.0.1; the chosen port is written to
    ``AERO_HOME/control.port`` for the client to find.

Wire format: one JSON object per line each way —
    -> {"op": "brain.set", "params": {"profile": "groq"}}
    <- {"ok": true, "result": {...}}

Requests dispatch straight into ``ControlService`` (which already sandboxes errors
into ``{ok:false}``), so a malformed or hostile request can never take the daemon
down. No third-party deps — stdlib ``socket``/``socketserver`` only.
"""

from __future__ import annotations

import json
import socket
import socketserver
import sys
import threading
from pathlib import Path

from aero.config import Config
from aero.control.service import ControlService

_IS_WINDOWS = sys.platform == "win32"


def socket_path(cfg: Config) -> Path:
    return cfg.home / "control.sock"


def port_path(cfg: Config) -> Path:
    return cfg.home / "control.port"


# -- server ----------------------------------------------------------------
class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        for raw in self.rfile:
            line = raw.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                resp = self.server.service.dispatch(  # type: ignore[attr-defined]
                    req.get("op", ""), req.get("params") or {}
                )
            except Exception as e:  # malformed line -> error, keep serving
                resp = {"ok": False, "error": f"bad request: {type(e).__name__}: {e}"}
            self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))
            self.wfile.flush()


# Single-threaded on purpose: control ops are infrequent human clicks, and the
# service's (lazily-opened) sqlite connection is thread-bound. Handling every
# request in the one serve_forever thread keeps that connection valid without
# per-request connections or locking. A slow op briefly queues others — fine at
# UI cadence.
if not _IS_WINDOWS:
    class _UnixServer(socketserver.UnixStreamServer):
        allow_reuse_address = True


class _TCPServer(socketserver.TCPServer):
    allow_reuse_address = True


class ControlServer:
    """Serves a ControlService over the local socket. Start it in the daemon so
    UIs can attach; stop it on shutdown."""

    def __init__(self, service: ControlService, *, cfg: Config | None = None):
        self.service = service
        self.cfg = cfg or service.cfg
        self._server: socketserver.BaseServer | None = None
        self._thread: threading.Thread | None = None

    def _make_server(self) -> socketserver.BaseServer:
        self.cfg.ensure_dirs()
        if _IS_WINDOWS:
            srv: socketserver.BaseServer = _TCPServer(("127.0.0.1", 0), _Handler)
            port = srv.server_address[1]  # type: ignore[index]
            port_path(self.cfg).write_text(str(port), encoding="utf-8")
        else:
            sp = socket_path(self.cfg)
            if sp.exists():
                sp.unlink()  # clear a stale socket from a previous run
            srv = _UnixServer(str(sp), _Handler)
        srv.service = self.service  # type: ignore[attr-defined]
        return srv

    def start_background(self) -> None:
        """Start serving in a daemon thread and return immediately."""
        self._server = self._make_server()
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="aero-control-ipc", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if not _IS_WINDOWS:
            sp = socket_path(self.cfg)
            if sp.exists():
                sp.unlink()
        else:
            pp = port_path(self.cfg)
            if pp.exists():
                pp.unlink()


# -- client ----------------------------------------------------------------
class ControlNotRunning(Exception):
    """Raised when no control server is reachable (daemon not up)."""


class ControlClient:
    def __init__(self, cfg: Config | None = None, *, timeout: float = 5.0):
        self.cfg = cfg or Config.load()
        self.timeout = timeout

    def _connect(self) -> socket.socket:
        if _IS_WINDOWS:
            pp = port_path(self.cfg)
            if not pp.exists():
                raise ControlNotRunning("no control.port — is the daemon running?")
            port = int(pp.read_text(encoding="utf-8").strip())
            s = socket.create_connection(("127.0.0.1", port), timeout=self.timeout)
        else:
            sp = socket_path(self.cfg)
            if not sp.exists():
                raise ControlNotRunning("no control.sock — is the daemon running?")
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            try:
                s.connect(str(sp))
            except OSError as e:
                raise ControlNotRunning(f"cannot reach control socket: {e}") from e
        return s

    def call(self, op: str, params: dict | None = None) -> dict:
        """Send one op to the running daemon and return its response dict."""
        s = self._connect()
        try:
            req = json.dumps({"op": op, "params": params or {}}) + "\n"
            s.sendall(req.encode("utf-8"))
            buf = b""
            while b"\n" not in buf:
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf += chunk
            line = buf.split(b"\n", 1)[0]
            return json.loads(line.decode("utf-8")) if line else {
                "ok": False, "error": "empty response"}
        finally:
            s.close()

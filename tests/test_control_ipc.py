"""Control IPC server/client round-trip (AERO-APP-201). Real local socket.

Skipped on Windows (Unix-socket path); the loopback-TCP path is exercised there
in practice. The service opens its own vault connection lazily inside the server
thread, so memory ops work across the socket without cross-thread sqlite issues.
"""

from __future__ import annotations

import sys
import warnings

import pytest

from aero.config import Config
from aero.control.ipc import ControlClient, ControlNotRunning, ControlServer
from aero.control.service import ControlService
from aero.memory.models import Memory
from aero.memory.store import MemoryStore
from aero.vault.connection import open_vault

pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="unix-socket round-trip; TCP path used on Windows")


@pytest.fixture()
def server(tmp_path):
    cfg = Config(home=tmp_path)
    # Pre-create a vault with one memory so memory ops have something to read.
    cfg.ensure_dirs()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v = open_vault(cfg.vault_path)
    MemoryStore(v, actor="seed").add_memory(Memory(summary="likes coffee", kind="semantic"))
    v.close()

    srv = ControlServer(ControlService(cfg), cfg=cfg)
    srv.start_background()
    try:
        yield cfg
    finally:
        srv.stop()


def test_roundtrip_status(server):
    resp = ControlClient(server).call("status")
    assert resp["ok"]
    assert resp["result"]["brain"]["active"] == "local"


def test_roundtrip_brain_set_then_get(server):
    assert ControlClient(server).call("brain.set", {"profile": "groq"})["ok"]
    assert ControlClient(server).call("brain.get")["result"]["active"] == "groq"


def test_roundtrip_memory_list_over_socket(server):
    resp = ControlClient(server).call("memory.list", {"query": "coffee"})
    assert resp["ok"]
    assert resp["result"]["count"] == 1


def test_roundtrip_error_shape(server):
    resp = ControlClient(server).call("brain.set", {})  # missing profile
    assert resp["ok"] is False and "profile" in resp["error"]


def test_bad_op_over_socket(server):
    resp = ControlClient(server).call("no.such.op")
    assert resp["ok"] is False and "unknown op" in resp["error"]


def test_socket_removed_after_stop(tmp_path):
    from aero.control.ipc import socket_path
    cfg = Config(home=tmp_path)
    srv = ControlServer(ControlService(cfg), cfg=cfg)
    srv.start_background()
    assert socket_path(cfg).exists()
    srv.stop()
    assert not socket_path(cfg).exists()


def test_client_errors_when_no_server(tmp_path):
    with pytest.raises(ControlNotRunning):
        ControlClient(Config(home=tmp_path)).call("status")

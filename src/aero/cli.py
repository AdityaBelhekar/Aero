"""The ``aero`` command — Milestone 1 surface.

Subcommands:
    init      create/upgrade the vault
    status    show vault info (version, encryption, row counts)
    backup    write a snapshot into the backups dir
    restore   restore the newest (or a named) snapshot
    smoke     prove state survives a simulated restart + backup/restore

Run as ``python -m aero.cli <cmd>`` or, once installed, ``aero <cmd>``.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from aero.config import Config
from aero.vault import backup as backup_mod
from aero.vault.connection import now_iso, open_vault
from aero.vault.repository import Repository


def _open(cfg: Config, *, create: bool = True):
    return open_vault(cfg.vault_path, create=create)


def cmd_init(cfg: Config, _args) -> int:
    cfg.ensure_dirs()
    with _open(cfg) as v:
        enc = "encrypted" if v.encrypted else "PLAINTEXT (install .[crypto])"
        print(f"Vault ready at {v.path}")
        print(f"  vault_id:       {v.vault_id}")
        print(f"  schema_version: {v.schema_version}")
        print(f"  storage:        {enc}")
    return 0


def cmd_status(cfg: Config, _args) -> int:
    if not cfg.vault_path.exists():
        print("No vault yet. Run: aero init")
        return 1
    with _open(cfg, create=False) as v:
        repo = Repository(v)
        tables = [
            "memories", "edges", "raw_events", "self_memory",
            "thought_threads", "boundaries", "permissions", "audit_log",
        ]
        print(f"Vault:          {v.path}")
        print(f"  vault_id:       {v.vault_id}")
        print(f"  schema_version: {v.schema_version}")
        print(f"  encrypted:      {v.get_meta('encrypted')}")
        print(f"  created_at:     {v.get_meta('created_at')}")
        print("  row counts:")
        for t in tables:
            print(f"    {t:<16} {repo.count(t)}")
    return 0


def cmd_backup(cfg: Config, _args) -> int:
    cfg.ensure_dirs()
    with _open(cfg, create=False) as v:
        info = backup_mod.snapshot(v, cfg.backups_dir)
    print(f"Backup written: {info.path} ({info.size_bytes} bytes)")
    return 0


def cmd_restore(cfg: Config, args) -> int:
    snap = Path(args.snapshot) if args.snapshot else backup_mod.latest_backup(cfg.backups_dir)
    if snap is None:
        print("No backups found.")
        return 1
    backup_mod.restore(snap, cfg.vault_path)
    ok = backup_mod.verify_roundtrip(cfg.vault_path)
    print(f"Restored from {snap} — {'OK' if ok else 'FAILED verification'}")
    return 0 if ok else 2


def cmd_smoke(cfg: Config, _args) -> int:
    """Milestone-1 acceptance: state survives a simulated restart, and a
    backup->wipe->restore round-trip recovers it."""
    cfg.ensure_dirs()
    print("== Aero Milestone-1 smoke test ==")

    # 1) Write a memory + a boundary through the audited repository.
    mem_id = uuid.uuid4().hex
    with _open(cfg) as v:
        repo = Repository(v, actor="user")
        repo.insert("memories", {
            "id": mem_id,
            "kind": "episodic",
            "summary": "First smoke-test memory: Aero's vault came online.",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "source_type": "explicit_statement",
        })
        repo.insert("boundaries", {
            "id": uuid.uuid4().hex,
            "topic_or_memory": "smoke-test-topic",
            "rule": "no_humour",
            "created_at": now_iso(),
        })
        vid = v.vault_id
        audits = repo.audit_count()
    print(f"  wrote memory {mem_id[:8]} + 1 boundary; audit rows so far: {audits}")
    assert audits >= 2, "audit journal did not record the writes"

    # 2) Simulate a restart: reopen and confirm the memory + identity persist.
    with _open(cfg, create=False) as v:
        assert v.vault_id == vid, "vault_id changed across restart"
        row = v.conn.execute("SELECT summary FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row is not None, "memory did not survive restart"
    print("  restart survived: memory + vault_id intact")

    # 3) Backup, wipe the vault, restore, re-verify the memory.
    with _open(cfg, create=False) as v:
        info = backup_mod.snapshot(v, cfg.backups_dir)
    print(f"  snapshot: {info.path.name}")

    for p in [cfg.vault_path,
              Path(str(cfg.vault_path) + "-wal"),
              Path(str(cfg.vault_path) + "-shm")]:
        if p.exists():
            p.unlink()
    assert not cfg.vault_path.exists(), "wipe failed"
    print("  vault wiped")

    backup_mod.restore(info.path, cfg.vault_path)
    with _open(cfg, create=False) as v:
        assert v.vault_id == vid, "vault_id mismatch after restore"
        row = v.conn.execute("SELECT summary FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row is not None, "memory missing after restore"
    print("  restore verified: memory + vault_id recovered")

    print("== PASS ==")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aero", description="Aero local companion (Milestone 1)")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create/upgrade the vault")
    sub.add_parser("status", help="show vault info")
    sub.add_parser("backup", help="snapshot the vault")
    r = sub.add_parser("restore", help="restore newest (or named) snapshot")
    r.add_argument("snapshot", nargs="?", help="path to a .aero-backup file")
    sub.add_parser("smoke", help="run the Milestone-1 acceptance smoke test")
    return p


_HANDLERS = {
    "init": cmd_init,
    "status": cmd_status,
    "backup": cmd_backup,
    "restore": cmd_restore,
    "smoke": cmd_smoke,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load()
    return _HANDLERS[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())

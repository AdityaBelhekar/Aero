"""Milestone-1 vault tests: schema, audit journal, restart survival, backup."""

from __future__ import annotations

import uuid
import warnings
from pathlib import Path

from aero.vault import backup as backup_mod
from aero.vault.connection import now_iso, open_vault
from aero.vault.repository import Repository


def _new_memory(repo: Repository) -> str:
    mem_id = uuid.uuid4().hex
    repo.insert("memories", {
        "id": mem_id,
        "kind": "episodic",
        "summary": "test memory",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    })
    return mem_id


def test_schema_and_identity(vault):
    assert vault.schema_version == 1
    assert vault.vault_id is not None
    assert vault.get_meta("created_at") is not None


def test_insert_is_audited(vault):
    repo = Repository(vault, actor="user")
    _new_memory(repo)
    assert repo.count("memories") == 1
    assert repo.audit_count() == 1
    row = vault.conn.execute(
        "SELECT op, actor, table_name FROM audit_log LIMIT 1"
    ).fetchone()
    assert row["op"] == "insert"
    assert row["actor"] == "user"
    assert row["table_name"] == "memories"


def test_update_and_delete_are_audited(vault):
    repo = Repository(vault)
    mem_id = _new_memory(repo)
    repo.update("memories", mem_id, {"confidence": 0.5, "updated_at": now_iso()})
    repo.delete("memories", mem_id)
    ops = [r["op"] for r in vault.conn.execute("SELECT op FROM audit_log ORDER BY id").fetchall()]
    assert ops == ["insert", "update", "delete"]
    # delete journal keeps the before-image
    del_row = vault.conn.execute(
        "SELECT before_json, after_json FROM audit_log WHERE op = 'delete'"
    ).fetchone()
    assert del_row["before_json"] is not None
    assert del_row["after_json"] is None


def test_roast_defaults_conservative(vault):
    """AERO-WRT-003: humour must be earned. Social defaults fail safe."""
    repo = Repository(vault)
    mem_id = _new_memory(repo)
    repo.insert("memory_social", {"memory_id": mem_id})
    row = vault.conn.execute(
        "SELECT roast_allowed, private_only, sensitivity FROM memory_social WHERE memory_id = ?",
        (mem_id,),
    ).fetchone()
    assert row["roast_allowed"] == 0
    assert row["private_only"] == 1
    assert row["sensitivity"] == 0.5


def test_restart_survival(vault_path: Path):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v1 = open_vault(vault_path)
    repo = Repository(v1)
    mem_id = _new_memory(repo)
    vid = v1.vault_id
    v1.close()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v2 = open_vault(vault_path, create=False)
    try:
        assert v2.vault_id == vid
        row = v2.conn.execute("SELECT id FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row is not None
    finally:
        v2.close()


def test_backup_wipe_restore_roundtrip(vault_path: Path, tmp_path: Path):
    backups = tmp_path / "backups"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v = open_vault(vault_path)
    repo = Repository(v)
    mem_id = _new_memory(repo)
    vid = v.vault_id
    info = backup_mod.snapshot(v, backups)
    v.close()

    # wipe
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(vault_path) + suffix)
        if p.exists():
            p.unlink()
    assert not vault_path.exists()

    backup_mod.restore(info.path, vault_path)
    assert backup_mod.verify_roundtrip(vault_path)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v2 = open_vault(vault_path, create=False)
    try:
        assert v2.vault_id == vid
        assert v2.conn.execute("SELECT id FROM memories WHERE id = ?", (mem_id,)).fetchone()
    finally:
        v2.close()


def test_restore_rejects_bad_snapshot(tmp_path: Path, vault_path: Path):
    bogus = tmp_path / "bogus.aero-backup"
    bogus.write_bytes(b"not a database")
    try:
        backup_mod.restore(bogus, vault_path)
        assert False, "restore should have rejected a non-vault snapshot"
    except Exception:
        pass

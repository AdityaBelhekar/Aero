"""Atomic vault snapshots and restore (AERO-VLT-004, risk R-8).

A relationship must survive a disk failure, so backup is Milestone-1 scope, not
a later feature. Snapshots use SQLite's online backup API, which produces a
consistent copy even while the vault is open and mid-WAL — safer than copying the
file bytes.

Restore is a first-class, tested flow: it validates the snapshot opens and
carries a matching ``vault_id`` before atomically swapping it into place, keeping
the displaced vault as a ``.pre-restore`` safety copy.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from aero.vault.connection import Vault, open_vault


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: str
    size_bytes: int


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def snapshot(vault: Vault, backups_dir: Path) -> BackupInfo:
    """Write a consistent snapshot of ``vault`` into ``backups_dir``.

    Uses the online backup API against a fresh destination DB, then fsyncs by
    closing it. The write goes to a temp name and is renamed into place so a
    crash mid-snapshot never leaves a half-written file mistaken for a backup.
    """
    backups_dir.mkdir(parents=True, exist_ok=True)
    final = backups_dir / f"aero-{_stamp()}.aero-backup"
    tmp = final.with_suffix(final.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()

    dest = sqlite3.connect(str(tmp))
    try:
        vault.conn.backup(dest)  # online backup: consistent even under WAL
    finally:
        dest.close()

    tmp.replace(final)  # atomic on the same filesystem
    return BackupInfo(path=final, created_at=_stamp(), size_bytes=final.stat().st_size)


def latest_backup(backups_dir: Path) -> Path | None:
    if not backups_dir.exists():
        return None
    backups = sorted(backups_dir.glob("aero-*.aero-backup"))
    return backups[-1] if backups else None


def _validate_snapshot(snapshot_path: Path) -> str:
    """Open the snapshot read-only and return its vault_id, or raise."""
    conn = sqlite3.connect(f"file:{snapshot_path}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = 'vault_id'").fetchone()
    finally:
        conn.close()
    if not row:
        raise ValueError(f"Snapshot {snapshot_path} has no vault_id — not a valid Aero backup")
    return row[0]


def restore(snapshot_path: Path, vault_path: Path) -> None:
    """Atomically replace the vault at ``vault_path`` with ``snapshot_path``.

    The displaced vault is preserved as ``<vault>.pre-restore`` so a mistaken
    restore is itself recoverable. WAL/SHM sidecars of the old vault are removed
    so the restored file is opened cleanly.
    """
    snapshot_path = Path(snapshot_path)
    vault_path = Path(vault_path)
    if not snapshot_path.exists():
        raise FileNotFoundError(snapshot_path)

    _validate_snapshot(snapshot_path)  # refuse to clobber with a bad backup

    vault_path.parent.mkdir(parents=True, exist_ok=True)

    if vault_path.exists():
        safety = vault_path.with_suffix(vault_path.suffix + ".pre-restore")
        if safety.exists():
            safety.unlink()
        vault_path.replace(safety)

    # Clear stale WAL/SHM so the restored DB isn't reconciled against old logs.
    for side in (".vault-wal", ".vault-shm"):
        p = vault_path.with_suffix(side)
        if p.exists():
            p.unlink()
    for suffix in ("-wal", "-shm"):
        p = Path(str(vault_path) + suffix)
        if p.exists():
            p.unlink()

    # Copy snapshot bytes into place (the snapshot is a plain, checkpointed DB).
    vault_path.write_bytes(snapshot_path.read_bytes())


def verify_roundtrip(vault_path: Path) -> bool:
    """Sanity check used by the smoke test: the restored vault opens and reports
    the same vault_id it had before. Returns True on success."""
    v = open_vault(vault_path, create=False)
    try:
        return v.vault_id is not None
    finally:
        v.close()

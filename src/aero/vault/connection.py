"""Vault connection factory, encryption abstraction, and migration bootstrap.

Encryption at rest is required (AERO-VLT-001). We want that *without* making the
Milestone-1 foundation un-runnable on a fresh machine, so encryption is
pluggable:

- If ``sqlcipher3`` (from the ``sqlcipher3-binary`` wheel) is importable, the
  vault is opened as an encrypted SQLCipher database. The key is read from a
  keyfile under the Aero home, created on first run.
- Otherwise the vault opens as a plaintext stdlib ``sqlite3`` database and the
  vault records ``encrypted=0`` in ``meta`` plus emits a warning, so the
  degraded state is never silent.

Key management here is a keyfile with restricted permissions. Binding the key to
the OS user via Windows DPAPI / Credential Manager is a follow-up (tracked in the
plan) — the abstraction below is where it will slot in.
"""

from __future__ import annotations

import secrets
import sqlite3
import stat
import uuid
import warnings
from datetime import datetime, timezone
from pathlib import Path

from aero.vault import schema

try:  # pragma: no cover - depends on optional install
    import sqlcipher3 as _sqlcipher  # type: ignore

    _HAVE_SQLCIPHER = True
except Exception:  # pragma: no cover
    _sqlcipher = None
    _HAVE_SQLCIPHER = False


def now_iso() -> str:
    """Timezone-aware ISO-8601 timestamp. All vault times use this."""
    return datetime.now(timezone.utc).astimezone().isoformat()


def _load_or_create_key(keyfile: Path) -> str:
    """Return the hex key for this vault, creating it on first run."""
    if keyfile.exists():
        return keyfile.read_text(encoding="utf-8").strip()
    key = secrets.token_hex(32)  # 256-bit
    keyfile.write_text(key, encoding="utf-8")
    try:
        keyfile.chmod(stat.S_IRUSR | stat.S_IWUSR)  # best-effort 0600
    except OSError:
        pass
    return key


class Vault:
    """A live handle to the Aero memory vault.

    Thin wrapper over a DB-API connection. The repository layer (repository.py)
    performs mutations through this so the audit journal is always written.
    """

    def __init__(self, conn: sqlite3.Connection, path: Path, *, encrypted: bool):
        self.conn = conn
        self.path = path
        self.encrypted = encrypted
        conn.row_factory = sqlite3.Row

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Vault":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- meta helpers ------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        try:
            row = self.conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        except sqlite3.OperationalError:
            # meta table not created yet (fresh vault, pre-migration).
            return None
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()

    @property
    def schema_version(self) -> int:
        v = self.get_meta("schema_version")
        return int(v) if v is not None else 0

    @property
    def vault_id(self) -> str | None:
        return self.get_meta("vault_id")


def _connect_raw(path: Path, key: str | None) -> tuple[sqlite3.Connection, bool]:
    """Open the underlying DB, applying the key if SQLCipher is present."""
    if _HAVE_SQLCIPHER and key is not None:
        conn = _sqlcipher.connect(str(path))
        # PRAGMA key must run before any other access.
        conn.execute(f"PRAGMA key = \"x'{key}'\"")
        return conn, True
    conn = sqlite3.connect(str(path))
    return conn, False


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = WAL")     # durability + concurrent reads
    conn.execute("PRAGMA foreign_keys = ON")      # cascades in schema depend on this
    conn.execute("PRAGMA synchronous = NORMAL")   # WAL-safe, faster than FULL


def _migrate(vault: Vault) -> None:
    """Bring the vault up to the current schema version.

    v1 is the baseline: create everything if absent, stamp version + identity.
    Future versions add ``if stored < N`` blocks here.
    """
    stored = vault.schema_version
    if stored > schema.SCHEMA_VERSION:
        raise RuntimeError(
            f"Vault schema v{stored} is newer than this code (v{schema.SCHEMA_VERSION}). "
            "Upgrade Aero before opening this vault."
        )

    vault.conn.executescript(schema.SCHEMA_SQL)

    if vault.get_meta("vault_id") is None:
        vault.set_meta("vault_id", uuid.uuid4().hex)
        vault.set_meta("created_at", now_iso())
    vault.set_meta("schema_version", str(schema.SCHEMA_VERSION))
    vault.conn.commit()


def open_vault(path: Path, *, keyfile: Path | None = None, create: bool = True) -> Vault:
    """Open (and, if needed, initialise) the vault at ``path``.

    ``keyfile`` defaults to ``<path>.key`` beside the vault. When SQLCipher is
    unavailable the key is created but unused, and the vault is marked plaintext.
    """
    path = Path(path)
    if not create and not path.exists():
        raise FileNotFoundError(f"No vault at {path}")
    path.parent.mkdir(parents=True, exist_ok=True)

    keyfile = keyfile or path.with_suffix(path.suffix + ".key")
    key = _load_or_create_key(keyfile)

    conn, encrypted = _connect_raw(path, key)
    _apply_pragmas(conn)
    vault = Vault(conn, path, encrypted=encrypted)
    _migrate(vault)

    stored_enc = vault.get_meta("encrypted")
    if stored_enc is None:
        vault.set_meta("encrypted", "1" if encrypted else "0")
    if not encrypted:
        warnings.warn(
            "Vault is UNENCRYPTED (sqlcipher3 not installed). Personal memory is "
            "stored in plaintext. Install with: pip install -e \".[crypto]\"",
            stacklevel=2,
        )
    return vault

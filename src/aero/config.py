"""Runtime paths and settings for Aero.

Everything Aero persists lives under a single data root so it can be backed up,
inspected, or wiped as one unit (privacy is a foundational requirement — PRD
Section 25). The root defaults to ``./data`` next to the repo but can be moved
with the ``AERO_HOME`` environment variable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 1


def _default_home() -> Path:
    env = os.environ.get("AERO_HOME")
    if env:
        return Path(env).expanduser().resolve()
    # Repo-root/data. config.py is src/aero/config.py -> parents[2] is repo root.
    return (Path(__file__).resolve().parents[2] / "data").resolve()


@dataclass(frozen=True)
class Config:
    """Resolved filesystem layout for one Aero instance."""

    home: Path

    @classmethod
    def load(cls) -> "Config":
        return cls(home=_default_home())

    @property
    def vault_path(self) -> Path:
        return self.home / "aero.vault"

    @property
    def backups_dir(self) -> Path:
        return self.home / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.home / "logs"

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

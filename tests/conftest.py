"""Shared fixtures. Tests never touch the real ./data vault — each gets a
throwaway vault under a tmp dir."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from aero.vault.connection import open_vault


@pytest.fixture()
def vault_path(tmp_path: Path) -> Path:
    return tmp_path / "aero.vault"


@pytest.fixture()
def vault(vault_path: Path):
    # The plaintext warning is expected in CI where sqlcipher isn't installed.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        v = open_vault(vault_path)
    try:
        yield v
    finally:
        v.close()

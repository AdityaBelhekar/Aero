"""The Aero memory vault.

A single encrypted SQLite file holding every persistent memory system. From the
user's perspective it is one vault (PRD AERO-MEM-003); internally the schema
carves it into the specialised systems described in the PRD Part II.
"""

from aero.vault.connection import Vault, open_vault

__all__ = ["Vault", "open_vault"]

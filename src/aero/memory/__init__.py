"""Aero's memory architecture (PRD Part II).

This package turns the vault's raw tables into the typed memory systems Aero
reasons over: episodic and semantic memories, the associative graph, and the
hybrid retrieval that surfaces them. Everything writes through the audited
Repository so provenance and the audit journal hold.
"""

from aero.memory.models import Edge, Memory, MemoryKind, SocialMeta
from aero.memory.store import MemoryStore

__all__ = ["Edge", "Memory", "MemoryKind", "SocialMeta", "MemoryStore"]

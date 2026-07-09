"""Typed views over vault rows.

These dataclasses are what the rest of Aero passes around; the store maps them
to/from the ``memories`` / ``memory_social`` / ``edges`` tables. Field defaults
encode the PRD's conservative-by-default stance (AERO-WRT-003): humour is off
until earned, sensitivity starts elevated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

MemoryKind = Literal["core", "semantic", "episodic"]
SourceType = Literal["explicit_statement", "repeated_observation", "inference"]


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class SocialMeta:
    """Governs how a memory may be used socially (AERO-WRT-002)."""

    roast_value: float = 0.0
    roast_allowed: bool = False        # earned, never assumed (AERO-WRT-003)
    sensitivity: float = 0.5           # elevated default, not 0
    private_only: bool = True
    emotional_weight: float = 0.0
    callback_fatigue: float = 0.0
    successful_callbacks: int = 0
    negative_reactions: int = 0
    last_used_at: str | None = None


@dataclass
class Memory:
    summary: str
    kind: MemoryKind = "episodic"
    id: str = field(default_factory=new_id)
    body: str | None = None
    confidence: float = 1.0
    evidence_count: int = 1
    source_type: SourceType = "inference"
    importance: float = 0.5
    decay_score: float = 1.0
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None
    social: SocialMeta | None = None


@dataclass
class Edge:
    src_id: str
    dst_id: str
    relation: str          # 'topic'|'person'|'emotion'|'failure'|'roast_material'|...
    weight: float = 1.0
    created_at: str | None = None


@dataclass
class Retrieved:
    """A memory surfaced by retrieval, with why it came up (provenance)."""

    memory: Memory
    score: float
    anchor_similarity: float
    activation: float
    reasons: list[str] = field(default_factory=list)

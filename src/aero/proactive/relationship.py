"""Relationship model — slow-moving scalars that gate behaviour (Section 17).

AERO-REL-001 dimensions: familiarity, trust, humour tolerance, roast tolerance,
conversation energy, recent interaction quality, user desire for interaction,
social distance, and Aero's confidence in its own interpretations. All are 0..1.

AERO-REL-002: the model *gates* behaviour — a new Aero doesn't use deeply personal
memories as aggressive jokes; a mature Aero has earned conversational freedom.
Explicit boundaries always override relationship inference (enforced elsewhere).

AERO-REL-003 (the important one here): dimensions move **slowly by design** —
bounded per-nudge so "one bad evening must not crater trust; one good joke must
not unlock roast mode." That bound is *code* (``MAX_STEP``), not a hope.

AERO-COLD-003: a new Aero behaves conservatively. The seeded defaults below are
deliberately low on familiarity/trust/humour so day-one Aero never acts like a
one-year-old Aero. Behaviour unlocks only as these accumulate.

Storage is the ``relationship_state`` table (one row per dimension), written
through the audited ``Repository``.
"""

from __future__ import annotations

from aero.memory.store import MemoryStore
from aero.vault.connection import now_iso

#: Max change to any dimension in a single nudge (AERO-REL-003, bounded delta).
MAX_STEP = 0.05

#: Conservative day-one seed (AERO-COLD-003). A fresh Aero is unsure and formal.
DEFAULTS: dict[str, float] = {
    "familiarity": 0.05,
    "trust": 0.30,
    "humour_tolerance": 0.15,
    "roast_tolerance": 0.05,
    "conversation_energy": 0.50,
    "interaction_quality": 0.50,
    "desire_for_interaction": 0.40,
    "social_distance": 0.70,          # starts distant; closeness is earned
    "self_confidence": 0.30,          # low confidence in its own reads early on
}

DIMENSIONS: tuple[str, ...] = tuple(DEFAULTS.keys())


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


class RelationshipModel:
    """Read/adjust the relationship dimensions, with a hard per-nudge cap."""

    def __init__(self, store: MemoryStore, *, max_step: float = MAX_STEP):
        self.store = store
        self.max_step = max_step

    def get(self, dimension: str) -> float:
        """Current value of a dimension, falling back to its conservative default."""
        row = self.store.vault.conn.execute(
            "SELECT value FROM relationship_state WHERE dimension = ?", (dimension,)
        ).fetchone()
        if row is not None:
            return float(row["value"])
        return DEFAULTS.get(dimension, 0.5)

    def all(self) -> dict[str, float]:
        return {dim: self.get(dim) for dim in DIMENSIONS}

    def _set(self, dimension: str, value: float) -> None:
        value = _clamp01(value)
        exists = self.store.vault.conn.execute(
            "SELECT 1 FROM relationship_state WHERE dimension = ?", (dimension,)
        ).fetchone()
        if exists:
            self.store.repo.update("relationship_state", dimension,
                                   {"value": value, "updated_at": now_iso()},
                                   pk_col="dimension")
        else:
            self.store.repo.insert("relationship_state",
                                   {"dimension": dimension, "value": value,
                                    "updated_at": now_iso()},
                                   pk_col="dimension")

    def nudge(self, dimension: str, delta: float) -> float:
        """Move a dimension by ``delta``, clamped to ±``max_step`` (AERO-REL-003)
        and to [0,1]. Returns the new value. Even explicit feedback goes through
        this cap — trust is not a light switch."""
        step = max(-self.max_step, min(self.max_step, delta))
        new = _clamp01(self.get(dimension) + step)
        self._set(dimension, new)
        return new

    def seed_defaults(self) -> None:
        """Write the conservative cold-start values for any missing dimension so a
        fresh vault reads sensible numbers even before any interaction."""
        for dim, val in DEFAULTS.items():
            exists = self.store.vault.conn.execute(
                "SELECT 1 FROM relationship_state WHERE dimension = ?", (dim,)
            ).fetchone()
            if not exists:
                self._set(dim, val)

    def summary(self) -> str:
        """One-line relationship summary for the working set / gate prompt."""
        v = self.all()
        return (f"familiarity {v['familiarity']:.2f}, trust {v['trust']:.2f}, "
                f"humour {v['humour_tolerance']:.2f}, roast {v['roast_tolerance']:.2f}, "
                f"social distance {v['social_distance']:.2f}")

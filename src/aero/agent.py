"""AeroAgent — one conversational turn, memory-in-the-loop.

Ties Milestone 2 together. Per user turn:
  1. log the user message to raw_events (consolidation will mine it later),
  2. retrieve relevant memories (hybrid pipeline) for this moment,
  3. assemble the working set (persona + identity + world + memories + history),
  4. generate Aero's reply (gemma4:e4b, thinking off),
  5. log Aero's reply to raw_events and keep it in the live conversation.

Consolidation is intentionally NOT run inline — it's an idle-time job. The chat
loop just accumulates raw events; ``aero consolidate`` (or the future daemon)
turns them into durable memory.
"""

from __future__ import annotations

import uuid

from aero.cognition.embeddings import EmbeddingService
from aero.cognition.service import CognitionService
from aero.memory.retrieval import RetrievalContext, RetrievalPipeline
from aero.memory.store import MemoryStore
from aero.vault.connection import now_iso
from aero.working_set import Turn, WorldState, assemble


class AeroAgent:
    def __init__(
        self,
        store: MemoryStore,
        llm: CognitionService,
        embedder: EmbeddingService,
        *,
        world: WorldState | None = None,
        world_provider=None,
    ):
        self.store = store
        self.llm = llm
        self.embedder = embedder
        self.pipeline = RetrievalPipeline(store, embedder)
        self.world = world
        # Optional perception.WorldStateProvider; when set, world state is
        # refreshed from live Tier-0 signals each turn.
        self.world_provider = world_provider
        self.conversation: list[Turn] = []

    def _refresh_world(self) -> None:
        if self.world_provider is None:
            return
        from datetime import datetime

        sample, switched = self.world_provider.poll()
        self.world = WorldState.from_tier0(
            sample, time_str=datetime.now().strftime("%a %H:%M")
        )
        if switched and sample.ok:
            # An app switch is a world-state delta worth remembering.
            self._log_event(
                "world", f"active app changed to {sample.process_name} "
                         f"({sample.window_title})"
            )

    def _log_event(self, speaker: str, text: str) -> None:
        self.store.vault.conn.execute(
            "INSERT INTO raw_events(id, ts, channel, payload) VALUES(?,?,?,?)",
            (uuid.uuid4().hex, now_iso(), "chat", f"{speaker}: {text}"),
        )
        self.store.vault.conn.commit()

    def respond(self, user_text: str) -> str:
        self._refresh_world()
        self._log_event("Aditya", user_text)
        self.conversation.append(Turn("user", user_text))

        # Retrieve against the user's message plus a little recent context.
        recent = " ".join(t.content for t in self.conversation[-3:])
        recalled = self.pipeline.retrieve(RetrievalContext(recent, private_ok=True))

        messages = assemble(self.store, recalled, self.conversation, world=self.world)
        result = self.llm.chat(messages, temperature=0.8, max_tokens=300)
        reply = result.text.strip()

        self.conversation.append(Turn("assistant", reply))
        self._log_event("Aero", reply)
        return reply

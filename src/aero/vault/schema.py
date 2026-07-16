"""Vault schema v1.

This is the storage substrate for the memory architecture in PRD Part II. The
tables mirror the schema sketch in the implementation plan (Milestone 1). Higher
milestones add indexes and the vector/graph query layers on top; v1 establishes
the durable shape so migrations later are additive.

Design rules baked in here:
- Every mutable row carries timestamps so decay/staleness sweeps (AERO-EVO-002,
  AERO-DEC-001) have something to work with.
- Inferred values carry confidence; nothing uncertain is stored as a bare fact
  (AERO-CORE-003, AERO-WS-002).
- ``boundaries`` are decay-exempt by construction — nothing here ever deletes
  them (AERO-SAFE-003).
"""

from __future__ import annotations

# Bumped whenever DDL below changes. connection.py refuses to open a vault whose
# stored version is newer than the code understands.
SCHEMA_VERSION = 1

SCHEMA_SQL = """
-- ---------------------------------------------------------------------------
-- meta: schema version + vault identity
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- memories: the shared substrate for semantic + episodic + core-identity items.
-- `kind` discriminates; specialised columns live in sibling tables.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memories (
    id             TEXT PRIMARY KEY,          -- uuid4 hex
    kind           TEXT NOT NULL              -- 'core' | 'semantic' | 'episodic'
                       CHECK (kind IN ('core', 'semantic', 'episodic')),
    summary        TEXT NOT NULL,             -- short retrievable gist
    body           TEXT,                      -- optional fuller text
    created_at     TEXT NOT NULL,             -- ISO-8601 with offset
    updated_at     TEXT NOT NULL,
    confidence     REAL NOT NULL DEFAULT 1.0  -- 0..1
                       CHECK (confidence >= 0.0 AND confidence <= 1.0),
    evidence_count INTEGER NOT NULL DEFAULT 1,
    source_type    TEXT NOT NULL DEFAULT 'inference'
                       CHECK (source_type IN
                           ('explicit_statement', 'repeated_observation', 'inference')),
    importance     REAL NOT NULL DEFAULT 0.5,
    decay_score    REAL NOT NULL DEFAULT 1.0, -- retrieval priority; sweeps lower it
    status         TEXT NOT NULL DEFAULT 'active'
                       CHECK (status IN ('active', 'dormant', 'archived', 'tombstoned'))
);
CREATE INDEX IF NOT EXISTS idx_memories_kind_status ON memories (kind, status);
CREATE INDEX IF NOT EXISTS idx_memories_updated ON memories (updated_at);

-- Social metadata (AERO-WRT-002). roast_allowed defaults 0 — humour must be
-- earned, never assumed (AERO-WRT-003).
CREATE TABLE IF NOT EXISTS memory_social (
    memory_id            TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    roast_value          REAL NOT NULL DEFAULT 0.0,
    roast_allowed        INTEGER NOT NULL DEFAULT 0,   -- boolean
    sensitivity          REAL NOT NULL DEFAULT 0.5,    -- defaults elevated, not 0
    private_only         INTEGER NOT NULL DEFAULT 1,   -- conservative default
    emotional_weight     REAL NOT NULL DEFAULT 0.0,
    callback_fatigue     REAL NOT NULL DEFAULT 0.0,
    successful_callbacks INTEGER NOT NULL DEFAULT 0,
    negative_reactions   INTEGER NOT NULL DEFAULT 0,
    last_used_at         TEXT
);

-- Associative graph edges (AERO-MEM-003 graph, AERO-RET-001 spread step).
CREATE TABLE IF NOT EXISTS edges (
    src_id     TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    dst_id     TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    relation   TEXT NOT NULL,     -- 'topic'|'person'|'emotion'|'failure'|...
    weight     REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    PRIMARY KEY (src_id, dst_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges (dst_id);
CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges (relation);

-- Embeddings live in their own table so a real ANN index (sqlite-vec) can
-- replace this in M2 without touching the rest of the schema. v1 stores the raw
-- vector as a blob so the column exists and round-trips.
CREATE TABLE IF NOT EXISTS embeddings (
    memory_id TEXT PRIMARY KEY REFERENCES memories(id) ON DELETE CASCADE,
    dim       INTEGER NOT NULL,
    vector    BLOB NOT NULL
);

-- Raw source events, retained on a rolling window before/after consolidation
-- (AERO-CON-010). expires_at drives the sweep; high-importance rows get NULL.
CREATE TABLE IF NOT EXISTS raw_events (
    id               TEXT PRIMARY KEY,
    ts               TEXT NOT NULL,
    channel          TEXT NOT NULL,   -- 'chat'|'window'|'audio'|...
    payload          TEXT NOT NULL,
    consolidated_into TEXT REFERENCES memories(id) ON DELETE SET NULL,
    expires_at       TEXT              -- NULL = retain indefinitely
);
CREATE INDEX IF NOT EXISTS idx_raw_events_ts ON raw_events (ts);
CREATE INDEX IF NOT EXISTS idx_raw_events_expires ON raw_events (expires_at);

-- Belief revision history so provenance can explain both current belief and its
-- past (AERO-EVO-003, AERO-PRV-001).
CREATE TABLE IF NOT EXISTS beliefs_history (
    belief_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    revision_no INTEGER NOT NULL,
    prior_state TEXT,               -- JSON snapshot of the belief before change
    reason      TEXT NOT NULL,
    ts          TEXT NOT NULL,
    PRIMARY KEY (belief_id, revision_no)
);

-- Explicit user boundaries. Decay-exempt and override-proof (AERO-SAFE-003).
CREATE TABLE IF NOT EXISTS boundaries (
    id              TEXT PRIMARY KEY,
    topic_or_memory TEXT NOT NULL,   -- topic label or a memory id
    rule            TEXT NOT NULL,   -- e.g. 'no_humour', 'never_mention'
    created_at      TEXT NOT NULL
);

-- Aero's memory of its own actions/decisions incl. silences (AERO-SELF-001,
-- AERO-PRO-006).
CREATE TABLE IF NOT EXISTS self_memory (
    id      TEXT PRIMARY KEY,
    ts      TEXT NOT NULL,
    action  TEXT NOT NULL,     -- 'spoke'|'stayed_silent'|'acted'|'delegated'|...
    context TEXT,
    outcome TEXT,
    lesson  TEXT
);
CREATE INDEX IF NOT EXISTS idx_self_memory_ts ON self_memory (ts);

-- Unresolved thought threads (AERO-THT-001/002).
CREATE TABLE IF NOT EXISTS thought_threads (
    id           TEXT PRIMARY KEY,
    statement    TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active'
                     CHECK (status IN ('active', 'dormant', 'resolved')),
    triggers_json TEXT,           -- JSON list of file paths/topics/people
    created_at   TEXT NOT NULL,
    last_active  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_threads_status ON thought_threads (status);

-- Slow-moving relationship dimensions (AERO-REL-001, bounded delta AERO-REL-003).
CREATE TABLE IF NOT EXISTS relationship_state (
    dimension  TEXT PRIMARY KEY,   -- 'familiarity'|'trust'|'humour_tolerance'|...
    value      REAL NOT NULL,
    updated_at TEXT NOT NULL
);

-- Granted authority with scope + expiry (AERO-AUTH-004).
CREATE TABLE IF NOT EXISTS permissions (
    id               TEXT PRIMARY KEY,
    scope            TEXT NOT NULL,
    grant_text       TEXT NOT NULL,
    expiry_condition TEXT,
    active           INTEGER NOT NULL DEFAULT 1,
    created_at       TEXT NOT NULL
);

-- Append-only audit journal of every mutation (AERO-VLT-002).
CREATE TABLE IF NOT EXISTS audit_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         TEXT NOT NULL,
    table_name TEXT NOT NULL,
    op         TEXT NOT NULL,     -- 'insert'|'update'|'delete'
    row_id     TEXT,
    before_json TEXT,
    after_json  TEXT,
    actor      TEXT NOT NULL DEFAULT 'system'  -- 'user'|'consolidation'|'system'
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log (ts);
CREATE INDEX IF NOT EXISTS idx_audit_table ON audit_log (table_name);

-- Append-only journal of every action Aero took a run at — allowed, refused,
-- confirmed, or dry-run (AERO-ACT-504). Distinct from audit_log (which tracks
-- vault mutations); this tracks the *hands*. The user can see everything Aero
-- did or was stopped from doing, and why.
CREATE TABLE IF NOT EXISTS actuator_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    tool      TEXT NOT NULL,
    scope     TEXT NOT NULL,
    params_json TEXT,
    verdict   TEXT NOT NULL,     -- 'allow'|'confirm'|'refuse'
    reason    TEXT,
    executed  INTEGER NOT NULL DEFAULT 0,  -- did the side-effect actually run?
    dry_run   INTEGER NOT NULL DEFAULT 0,
    outcome   TEXT,              -- 'ok'|'error'|null (not run)
    error     TEXT
);
CREATE INDEX IF NOT EXISTS idx_actuator_ts ON actuator_log (ts);
CREATE INDEX IF NOT EXISTS idx_actuator_tool ON actuator_log (tool);
"""

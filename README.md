# Aero

A persistent, local-first AI companion designed to build one long-term relationship with one human.

> The longer Aero lives with you, the less you need to explain yourself.

See [`Aero-PRD-v0.2.md`](Aero-PRD-v0.2.md) for the product requirements and
[`Aero-Implementation-Plan.md`](Aero-Implementation-Plan.md) for the build sequence.

## Status

**Milestone 2 — Memory Core** working (PRD Phase 0). Memory-in-the-loop chat with
cross-session continuity: a preference told in one session survives consolidation
and a process restart, and shapes Aero's reply in a fresh session, with provenance.

Done:

- **Milestone 1 — Vault:** SQLite (WAL) schema v1, pluggable encryption, migrations,
  audit journal on every mutation (`AERO-VLT-002`), atomic backup + tested restore
  (`AERO-VLT-004`).
- **Spike S-1:** Gemma 4 E4B viable via Ollama (`spikes/S1_VERDICT.md`). Note: it's a
  reasoning model — run with thinking off.
- **Spike S-2:** embeddinggemma 90% top-1 on romanised Hindi/Marathi
  (`spikes/S2_VERDICT.md`).
- **Milestone 2 — Memory core:** typed memory store, LLM consolidation (write path),
  associative graph, hybrid retrieval (vector anchor → graph spread → rerank) with
  Wild Recall + social-fit filtering, working-set assembler, and `aero chat`.

Requires [Ollama](https://ollama.com) with `gemma4:e4b` and `embeddinggemma` pulled.

## Quick start

```sh
python -m aero.cli init            # create the vault under ./data
python -m aero.cli chat            # memory-in-the-loop chat with Aero
python -m aero.cli consolidate     # turn the chat into durable memory
python -m aero.cli status          # vault info + memory counts
python -m aero.cli backup          # snapshot the vault
python -m aero.cli smoke           # prove state survives a simulated restart
```

The vault runs on the stdlib; encryption at rest activates if `sqlcipher3-binary`
is installed (`pip install -e ".[crypto]"`), else it warns and uses plaintext.
Chat/consolidate need Ollama running.

## Layout

```
src/aero/
  config.py        # paths, settings
  vault/
    schema.py      # schema v1 DDL (AERO-VLT-001 tables)
    connection.py  # encrypted-connection factory + migrations
    repository.py  # mutation layer that writes the audit journal
    backup.py      # atomic snapshot + restore (AERO-VLT-004)
  cli.py           # the `aero` command
tests/             # pytest suite (round-trip, audit, restart survival)
prompts/           # versioned prompt/schema library (W-4) — filled in M2
```

# Aero

A persistent, local-first AI companion designed to build one long-term relationship with one human.

> The longer Aero lives with you, the less you need to explain yourself.

See [`Aero-PRD-v0.2.md`](Aero-PRD-v0.2.md) for the product requirements and
[`Aero-Implementation-Plan.md`](Aero-Implementation-Plan.md) for the build sequence.

## Status

**Milestone 1 — Skeleton & Vault** (PRD Phase 0). The encrypted, versioned,
backed-up memory vault is the foundation everything else is a client of.

Implemented so far:

- Vault: SQLite (WAL) with schema v1, pluggable encrypted-connection factory,
  migration bootstrap.
- Audit journal on every mutation (`AERO-VLT-002`).
- Atomic snapshot backup + tested restore round-trip (`AERO-VLT-004`, risk R-8).
- `aero` CLI: `init`, `status`, `backup`, `restore`, `smoke`.

## Quick start

```sh
# from the repo root
python -m aero.cli init            # create the vault under ./data
python -m aero.cli status          # show vault info
python -m aero.cli smoke           # prove state survives a simulated restart
python -m aero.cli backup          # snapshot the vault
```

No third-party packages are required for Milestone 1 — it runs on the Python
3.11 standard library. Encryption at rest activates automatically if
`sqlcipher3-binary` is installed (`pip install -e ".[crypto]"`); otherwise the
vault is created as an explicitly-marked plaintext file and warns you.

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

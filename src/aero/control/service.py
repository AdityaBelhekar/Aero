"""ControlService — the daemon's management API (AERO-APP-203..207).

One ``dispatch(op, params)`` entry point maps a stable operation name to a handler
returning JSON-able data. Grouped by the Control-App panel each op serves:

    status                                    overall health + counts
    brain.list|get|set|router|set_key|del_key the brain manager (M8 registry/router)
    voice.list|get|set                        the voice manager
    persona.get|set                           the personality dials
    perms.get|grant|killswitch                capability grants + kill switch
    memory.list|get|edit|delete               the memory browser

Handlers raise ``ControlError`` for bad input (surfaced as ``{ok:false,error}``);
any other exception is caught by ``dispatch`` so a UI call can never crash the
daemon. Nothing here does I/O beyond settings + the vault; network health probes
are opt-in (``status`` with ``probe=true``) so the API stays fast and testable.
"""

from __future__ import annotations

from typing import Any, Callable

from aero import settings as st
from aero.config import Config

# Persona dials that are 0..1 floats; validated on persona.set.
_NUMERIC_DIALS = ("chattiness", "roast_level", "formality", "energy")
_LANGUAGE_MIX = ("auto", "english", "hinglish", "marathi-mix")

# Memory fields the browser may edit (AERO-VLT-003). Others (id, timestamps, kind)
# are structural and not user-editable here.
_EDITABLE_MEMORY_FIELDS = ("summary", "body", "importance", "confidence", "status")


class ControlError(Exception):
    """Bad request from a UI — reported as {ok:false, error} without a traceback."""


class ControlService:
    def __init__(self, cfg: Config | None = None, *, store=None):
        self.cfg = cfg or Config.load()
        # An injected MemoryStore (daemon reuse / tests); else opened lazily.
        self._store = store
        self._ops: dict[str, Callable[[dict], Any]] = {
            "status": self._status,
            "brain.list": self._brain_list,
            "brain.get": self._brain_get,
            "brain.set": self._brain_set,
            "brain.router": self._brain_router,
            "brain.set_key": self._brain_set_key,
            "brain.del_key": self._brain_del_key,
            "brain.providers": self._brain_providers,
            "brain.discover": self._brain_discover,
            "brain.login_start": self._brain_login_start,
            "brain.login_complete": self._brain_login_complete,
            "voice.list": self._voice_list,
            "voice.catalog": self._voice_catalog,
            "voice.get": self._voice_get,
            "voice.set": self._voice_set,
            "persona.get": self._persona_get,
            "persona.set": self._persona_set,
            "perms.get": self._perms_get,
            "perms.grant": self._perms_grant,
            "perms.killswitch": self._perms_killswitch,
            "memory.list": self._memory_list,
            "memory.get": self._memory_get,
            "memory.edit": self._memory_edit,
            "memory.delete": self._memory_delete,
            "hands.tools": self._hands_tools,
            "hands.run": self._hands_run,
            "hands.log": self._hands_log,
            "eyes.status": self._eyes_status,
            "eyes.look": self._eyes_look,
            "eyes.describe": self._eyes_describe,
            "play.games": self._play_games,
            "play.status": self._play_status,
            "play.act": self._play_act,
            "body.status": self._body_status,
            "body.service": self._body_service,
            "body.pi_preset": self._body_pi_preset,
        }
        self._hands = None
        self._eyes = None

    # -- dispatch ----------------------------------------------------------
    def ops(self) -> list[str]:
        return sorted(self._ops)

    def dispatch(self, op: str, params: dict | None = None) -> dict:
        handler = self._ops.get(op)
        if handler is None:
            return {"ok": False, "error": f"unknown op: {op}"}
        try:
            return {"ok": True, "result": handler(params or {})}
        except ControlError as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:  # never let a UI call crash the daemon
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}

    # -- helpers -----------------------------------------------------------
    def _settings(self) -> st.VoiceSettings:
        return st.load(self.cfg)

    def store(self):
        """Lazily open the memory store (only when a memory op needs it)."""
        if self._store is None:
            import warnings

            from aero.memory.store import MemoryStore
            from aero.vault.connection import open_vault
            self.cfg.ensure_dirs()
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # plaintext-vault warning
                vault = open_vault(self.cfg.vault_path)
            self._store = MemoryStore(vault, actor="control")
        return self._store

    # -- status ------------------------------------------------------------
    def _status(self, p: dict) -> dict:
        from aero.cognition import keys as _keys

        s = self._settings()
        active = st.resolve_brain_profile(s)
        out = {
            "brain": {"active": active.id, "model": active.model,
                      "private": active.is_private},
            "voice": {"engine": s.engine},
            "killswitch": s.killswitch,
            "keyring": _keys.keyring_available(),
            "vault": str(self.cfg.vault_path),
            "vault_exists": self.cfg.vault_path.exists(),
        }
        if self.cfg.vault_path.exists():
            out["memory_counts"] = self._counts()
        if p.get("probe"):  # opt-in network health checks
            out["health"] = self._probe_health(s)
        return out

    def _counts(self) -> dict:
        conn = self.store().vault.conn
        row = conn.execute(
            "SELECT "
            "  SUM(kind='core') AS core, "
            "  SUM(kind='semantic') AS semantic, "
            "  SUM(kind='episodic') AS episodic, "
            "  SUM(status='active') AS active "
            "FROM memories WHERE summary NOT LIKE 'concept:%'"
        ).fetchone()
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM raw_events WHERE consolidated_into IS NULL"
        ).fetchone()["n"]
        return {"core": row["core"] or 0, "semantic": row["semantic"] or 0,
                "episodic": row["episodic"] or 0, "active": row["active"] or 0,
                "pending_events": pending}

    def _probe_health(self, s: st.VoiceSettings) -> dict:
        health = {}
        try:
            health["brain"] = st.build_brain(self.cfg).health_check()
        except Exception:
            health["brain"] = False
        try:
            from aero.cognition.embeddings import OllamaEmbedder
            health["embeddings"] = OllamaEmbedder().health_check()
        except Exception:
            health["embeddings"] = False
        return health

    # -- brain manager (delegates to the M8 registry/router) ---------------
    def _brain_list(self, p: dict) -> dict:
        from aero.cognition import keys as _keys
        from aero.cognition.registry import registry

        s = self._settings()
        active = st.resolve_brain_profile(s).id
        profiles = []
        for pid, prof in registry(s.brains).items():
            has_key = _keys.resolve_key(prof) is not None
            profiles.append({
                "id": pid, "model": prof.model, "adapter": prof.adapter,
                "cost_tier": prof.cost_tier, "private": prof.is_private,
                "supports_vision": prof.supports_vision, "label": prof.label,
                "key_set": has_key or (prof.is_local and prof.key_env is None),
                "active": pid == active,
            })
        return {"profiles": profiles, "active": active}

    def _brain_get(self, p: dict) -> dict:
        s = self._settings()
        return {
            "active": st.resolve_brain_profile(s).id,
            "reflex": s.reflex_profile or None,
            "primary": s.primary_profile or None,
            "private_only": s.brain_private_only,
        }

    def _brain_set(self, p: dict) -> dict:
        profile = _require(p, "profile")
        s = self._settings()
        s.brain_profile = profile
        s.brain = profile
        st.save(s, self.cfg)
        return {"active": st.resolve_brain_profile(s).id}

    def _brain_router(self, p: dict) -> dict:
        s = self._settings()
        if "reflex" in p:
            s.reflex_profile = p["reflex"] or ""
        if "primary" in p:
            s.primary_profile = p["primary"] or ""
        if "private_only" in p:
            s.brain_private_only = bool(p["private_only"])
        st.save(s, self.cfg)
        return {"reflex": s.reflex_profile or None, "primary": s.primary_profile or None,
                "private_only": s.brain_private_only}

    def _brain_set_key(self, p: dict) -> dict:
        from aero.cognition import keys as _keys
        ok = _keys.set_key(_require(p, "profile"), _require(p, "key"))
        if not ok:
            raise ControlError("no keyring backend available (install '.[keyring]' "
                               "or use an env var)")
        return {"stored": True}

    def _brain_del_key(self, p: dict) -> dict:
        from aero.cognition import keys as _keys
        return {"deleted": _keys.delete_key(_require(p, "profile"))}

    def _brain_providers(self, p: dict) -> dict:
        """The connect-any-AI catalog: each provider with kind/auth + whether a
        key is already set (AERO-BRAIN-305)."""
        from aero.cognition import keys as _keys
        from aero.cognition.providers import PROVIDERS
        from aero.cognition.registry import registry
        reg = registry(self._settings().brains)
        out = []
        for pid, prov in PROVIDERS.items():
            prof = reg.get(pid)
            key_set = prov.auth == "none" or (
                prof is not None and _keys.resolve_key(prof) is not None)
            out.append({**prov.to_dict(),
                        "model": prof.model if prof else "",
                        "key_set": key_set})
        return {"providers": out}

    def _brain_discover(self, p: dict) -> dict:
        from aero.cognition.discovery import discover_local
        return {"local": discover_local()}

    def _brain_login_start(self, p: dict) -> dict:
        from aero.cognition.account import AccountLogin
        return AccountLogin(_require(p, "provider")).start(
            callback_url=p.get("callback_url", "http://localhost:8385/callback")
        ).to_dict()

    def _brain_login_complete(self, p: dict) -> dict:
        from aero.cognition.account import AccountLogin
        return AccountLogin(_require(p, "provider")).complete(
            _require(p, "code"), _require(p, "verifier"))

    # -- voice manager -----------------------------------------------------
    def _voice_list(self, p: dict) -> dict:
        s = self._settings()
        return {
            "engines": ["sapi", "svara", "parler", "kokoro"],
            "active_engine": s.engine,
            "voices": {"svara": s.svara_voice, "kokoro": s.kokoro_voice},
            "stt_model": s.stt_model,
        }

    def _voice_catalog(self, p: dict) -> dict:
        """The voice marketplace listing (AERO-VOX-401/402): every STT/TTS engine
        with its capabilities + key/active state, for the Voice panel."""
        from aero.cognition import keys as _keys
        from aero.voice.catalog import registry as _vreg

        s = self._settings()
        reg = _vreg(s.voice_engines)
        active = {"tts": s.engine, "stt": s.stt_model}
        out = {"tts": [], "stt": []}
        for prof in reg.values():
            has_key = (prof.local and prof.key_env is None) \
                or _keys.resolve_voice_key(prof) is not None
            out[prof.role].append({
                "id": prof.id, "backend": prof.backend, "cost_tier": prof.cost_tier,
                "local": prof.local, "private": prof.private,
                "streaming": prof.streaming, "emotion": prof.emotion,
                "languages": list(prof.languages), "implemented": prof.implemented,
                "key_set": has_key, "label": prof.label,
                "active": prof.id == active.get(prof.role),
            })
        return out

    def _voice_get(self, p: dict) -> dict:
        s = self._settings()
        return {"engine": s.engine, "svara_voice": s.svara_voice,
                "kokoro_voice": s.kokoro_voice, "stt_model": s.stt_model}

    def _voice_set(self, p: dict) -> dict:
        s = self._settings()
        for key in ("engine", "svara_voice", "kokoro_voice", "stt_model"):
            if key in p:
                setattr(s, key, p[key])
        st.save(s, self.cfg)
        return self._voice_get({})

    # -- personality dials -------------------------------------------------
    def _persona_get(self, p: dict) -> dict:
        return {"dials": st.merged_persona(self._settings()),
                "defaults": dict(st.DEFAULT_PERSONA_DIALS)}

    def _persona_set(self, p: dict) -> dict:
        dials = p.get("dials")
        if not isinstance(dials, dict):
            raise ControlError("persona.set needs a 'dials' object")
        s = self._settings()
        merged = st.merged_persona(s)
        for key, val in dials.items():
            if key not in st.DEFAULT_PERSONA_DIALS:
                raise ControlError(f"unknown persona dial: {key}")
            merged[key] = _validate_dial(key, val)
        s.persona = merged
        st.save(s, self.cfg)
        return {"dials": s.persona}

    # -- permissions + kill switch -----------------------------------------
    def _perms_get(self, p: dict) -> dict:
        s = self._settings()
        return {
            "killswitch": s.killswitch,
            "scopes": {scope: st.permission_granted(s, scope)
                       for scope in st.PERMISSION_SCOPES},
            "all_scopes": list(st.PERMISSION_SCOPES),
        }

    def _perms_grant(self, p: dict) -> dict:
        scope = _require(p, "scope")
        if scope not in st.PERMISSION_SCOPES:
            raise ControlError(f"unknown permission scope: {scope}")
        on = bool(p.get("on", True))
        s = self._settings()
        perms = dict(s.permissions or {})
        perms[scope] = on
        s.permissions = perms
        st.save(s, self.cfg)
        return {"scope": scope, "granted": st.permission_granted(s, scope)}

    def _perms_killswitch(self, p: dict) -> dict:
        s = self._settings()
        s.killswitch = bool(p.get("on", True))
        st.save(s, self.cfg)
        return {"killswitch": s.killswitch}

    # -- memory browser (AERO-VLT-003) -------------------------------------
    def _memory_list(self, p: dict) -> dict:
        limit = min(int(p.get("limit", 50)), 500)
        query = p.get("query")
        kind = p.get("kind")
        sql = ("SELECT id, kind, summary, confidence, importance, status, created_at "
               "FROM memories WHERE summary NOT LIKE 'concept:%'")
        args: list[Any] = []
        if query:
            sql += " AND (summary LIKE ? OR body LIKE ?)"
            args += [f"%{query}%", f"%{query}%"]
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        rows = self.store().vault.conn.execute(sql, args).fetchall()
        return {"memories": [dict(r) for r in rows], "count": len(rows)}

    def _memory_get(self, p: dict) -> dict:
        mid = _require(p, "id")
        store = self.store()
        mem = store.get(mid)
        if mem is None:
            raise ControlError(f"no memory {mid}")
        social = store.get_social(mid)
        neighbors = [{"dst": e.dst_id, "relation": e.relation, "weight": e.weight}
                     for e in store.neighbors(mid)]
        return {"memory": _memory_dict(mem),
                "social": social.__dict__ if social else None,
                "neighbors": neighbors}

    def _memory_edit(self, p: dict) -> dict:
        from aero.vault.connection import now_iso
        mid = _require(p, "id")
        fields = p.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ControlError("memory.edit needs a non-empty 'fields' object")
        store = self.store()
        if store.get(mid) is None:
            raise ControlError(f"no memory {mid}")
        changes = {}
        for key, val in fields.items():
            if key not in _EDITABLE_MEMORY_FIELDS:
                raise ControlError(f"field not editable: {key}")
            changes[key] = val
        changes["updated_at"] = now_iso()
        store.repo.update("memories", mid, changes)
        return {"memory": _memory_dict(store.get(mid))}

    # -- little hands (AERO-ACT-5xx) ---------------------------------------
    def _hands_executor(self):
        """Registry + consent gate + actuator journal, sharing the vault. Every
        UI-triggered action goes through this, so the gate + journal apply."""
        if self._hands is None:
            from aero.hands.consent import ConsentGate
            from aero.hands.executor import HandsExecutor
            from aero.hands.journal import ActuatorJournal
            from aero.hands.registry import default_registry
            journal = ActuatorJournal(self.store().vault)
            self._hands = HandsExecutor(default_registry(), ConsentGate(self.cfg),
                                        journal)
        return self._hands

    def _hands_tools(self, p: dict) -> dict:
        return {"tools": self._hands_executor().registry.describe()}

    def _hands_run(self, p: dict) -> dict:
        tool = _require(p, "tool")
        outcome = self._hands_executor().run(
            tool, p.get("params") or {},
            confirmed=bool(p.get("confirmed", False)),
            dry_run=bool(p.get("dry_run", False)),
        )
        return outcome.to_dict()

    def _hands_log(self, p: dict) -> dict:
        journal = self._hands_executor().journal
        return {"entries": journal.recent(int(p.get("limit", 50)),
                                          tool=p.get("tool"))}

    # -- eyes / vision (AERO-VIS-6xx) --------------------------------------
    def _eyes_obj(self):
        if self._eyes is None:
            from aero.perception.vision import build_eyes
            self._eyes = build_eyes(self.cfg)
        return self._eyes

    def _eyes_status(self, p: dict) -> dict:
        s = self._settings()
        eyes = self._eyes_obj()
        return {
            "sources": {name: {"scope": src.scope,
                               "granted": st.permission_granted(s, src.scope),
                               "available": src.available()}
                        for name, src in eyes.sources.items()},
            "killswitch": s.killswitch,
        }

    def _eyes_look(self, p: dict) -> dict:
        return self._eyes_obj().look(p.get("source", "screen")).to_dict()

    def _eyes_describe(self, p: dict) -> dict:
        from aero.perception.vision_router import VisionRouter
        look = self._eyes_obj().look(p.get("source", "screen"))
        if not look.ok:
            return {"look": look.to_dict(), "vision": None}
        answer = VisionRouter(self.cfg).see(
            look.frame, prompt=p.get("prompt", "What's on the screen?"))
        return {"look": look.to_dict(), "vision": answer.to_dict()}

    # -- play / games (AERO-PLAY-7xx) --------------------------------------
    def _play_games(self, p: dict) -> dict:
        from aero.play import known_games
        return {"games": [{"game": g.game, "mode": g.mode.value, "note": g.note,
                           "can_automate": g.can_automate} for g in known_games()]}

    def _play_status(self, p: dict) -> dict:
        from aero.play import game_policy
        game = p.get("game", "minecraft")
        s = self._settings()
        pol = game_policy(game)
        out = {"game": pol.game, "mode": pol.mode.value, "note": pol.note,
               "can_automate": pol.can_automate,
               "games_granted": st.permission_granted(s, "games"),
               "killswitch": s.killswitch}
        if pol.game == "minecraft":
            from aero.play.minecraft import MinecraftConnector
            out["bridge_available"] = MinecraftConnector().available()
        return out

    def _play_act(self, p: dict) -> dict:
        from aero.play import GameAction, GameSession
        from aero.play.minecraft import MinecraftConnector
        game = p.get("game", "minecraft")
        if game != "minecraft":
            # only minecraft has a connector today; others are spectate-only anyway
            from aero.play import game_policy
            return {"verdict": "refused_spectate",
                    "reason": f"{game}: {game_policy(game).note}", "result": None}
        sess = GameSession(MinecraftConnector(), cfg=self.cfg)
        result = sess.act(GameAction(_require(p, "kind"), p.get("args") or {}))
        return result.to_dict()

    # -- body / robot (AERO-BODY-8xx) --------------------------------------
    def _body_status(self, p: dict) -> dict:
        from aero.body.robot import robot_status
        return robot_status(self.cfg)

    def _body_service(self, p: dict) -> dict:
        from aero.body.robot import systemd_unit
        return {"unit": systemd_unit(aero_home=p.get("aero_home") or str(self.cfg.home))}

    def _body_pi_preset(self, p: dict) -> dict:
        from aero.body.robot import apply_pi_brain_preset
        s = self._settings()
        apply_pi_brain_preset(s)
        st.save(s, self.cfg)
        return {"reflex": s.reflex_profile, "primary": s.primary_profile,
                "note": "Pi two-speed router: local reflex + LAN/cloud chat "
                        "(point the litellm profile at your brain host)"}

    def _memory_delete(self, p: dict) -> dict:
        # Soft delete (tombstone) so provenance survives and it's reversible; a
        # hard delete would strip evidence out from under dependent beliefs
        # (AERO-VLT-003). Consolidation skips non-active memories.
        mid = _require(p, "id")
        store = self.store()
        if store.get(mid) is None:
            raise ControlError(f"no memory {mid}")
        store.set_status(mid, "tombstoned")
        return {"id": mid, "status": "tombstoned"}


# -- module helpers --------------------------------------------------------
def _require(p: dict, key: str) -> Any:
    if key not in p or p[key] in (None, ""):
        raise ControlError(f"missing required param: {key}")
    return p[key]


def _validate_dial(key: str, val: Any) -> Any:
    if key in _NUMERIC_DIALS:
        try:
            f = float(val)
        except (TypeError, ValueError):
            raise ControlError(f"{key} must be a number 0..1") from None
        if not 0.0 <= f <= 1.0:
            raise ControlError(f"{key} must be within 0..1")
        return f
    if key == "language_mix":
        if val not in _LANGUAGE_MIX:
            raise ControlError(f"language_mix must be one of {_LANGUAGE_MIX}")
        return val
    if key == "quiet_hours":
        if (not isinstance(val, (list, tuple)) or len(val) != 2
                or not all(isinstance(h, int) and 0 <= h <= 23 for h in val)):
            raise ControlError("quiet_hours must be [start_hour, end_hour] in 0..23")
        return list(val)
    return val


def _memory_dict(mem) -> dict:
    return {
        "id": mem.id, "kind": mem.kind, "summary": mem.summary, "body": mem.body,
        "confidence": mem.confidence, "evidence_count": mem.evidence_count,
        "source_type": mem.source_type, "importance": mem.importance,
        "decay_score": mem.decay_score, "status": mem.status,
        "created_at": mem.created_at, "updated_at": mem.updated_at,
    }

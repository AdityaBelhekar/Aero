"""The ``aero`` command — Milestone 1 surface.

Subcommands:
    init      create/upgrade the vault
    status    show vault info (version, encryption, row counts)
    backup    write a snapshot into the backups dir
    restore   restore the newest (or a named) snapshot
    smoke     prove state survives a simulated restart + backup/restore

Run as ``python -m aero.cli <cmd>`` or, once installed, ``aero <cmd>``.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from aero.config import Config
from aero.vault import backup as backup_mod
from aero.vault.connection import now_iso, open_vault
from aero.vault.repository import Repository


def _open(cfg: Config, *, create: bool = True):
    return open_vault(cfg.vault_path, create=create)


def cmd_init(cfg: Config, _args) -> int:
    cfg.ensure_dirs()
    with _open(cfg) as v:
        enc = "encrypted" if v.encrypted else "PLAINTEXT (install .[crypto])"
        print(f"Vault ready at {v.path}")
        print(f"  vault_id:       {v.vault_id}")
        print(f"  schema_version: {v.schema_version}")
        print(f"  storage:        {enc}")
    return 0


def cmd_status(cfg: Config, _args) -> int:
    if not cfg.vault_path.exists():
        print("No vault yet. Run: aero init")
        return 1
    with _open(cfg, create=False) as v:
        repo = Repository(v)
        tables = [
            "memories", "edges", "raw_events", "self_memory",
            "thought_threads", "boundaries", "permissions", "audit_log",
        ]
        print(f"Vault:          {v.path}")
        print(f"  vault_id:       {v.vault_id}")
        print(f"  schema_version: {v.schema_version}")
        print(f"  encrypted:      {v.get_meta('encrypted')}")
        print(f"  created_at:     {v.get_meta('created_at')}")
        print("  row counts:")
        for t in tables:
            print(f"    {t:<16} {repo.count(t)}")
    return 0


def cmd_backup(cfg: Config, _args) -> int:
    cfg.ensure_dirs()
    with _open(cfg, create=False) as v:
        info = backup_mod.snapshot(v, cfg.backups_dir)
    print(f"Backup written: {info.path} ({info.size_bytes} bytes)")
    return 0


def cmd_restore(cfg: Config, args) -> int:
    snap = Path(args.snapshot) if args.snapshot else backup_mod.latest_backup(cfg.backups_dir)
    if snap is None:
        print("No backups found.")
        return 1
    backup_mod.restore(snap, cfg.vault_path)
    ok = backup_mod.verify_roundtrip(cfg.vault_path)
    print(f"Restored from {snap} — {'OK' if ok else 'FAILED verification'}")
    return 0 if ok else 2


def cmd_smoke(cfg: Config, _args) -> int:
    """Milestone-1 acceptance: state survives a simulated restart, and a
    backup->wipe->restore round-trip recovers it."""
    cfg.ensure_dirs()
    print("== Aero Milestone-1 smoke test ==")

    # 1) Write a memory + a boundary through the audited repository.
    mem_id = uuid.uuid4().hex
    with _open(cfg) as v:
        repo = Repository(v, actor="user")
        repo.insert("memories", {
            "id": mem_id,
            "kind": "episodic",
            "summary": "First smoke-test memory: Aero's vault came online.",
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "source_type": "explicit_statement",
        })
        repo.insert("boundaries", {
            "id": uuid.uuid4().hex,
            "topic_or_memory": "smoke-test-topic",
            "rule": "no_humour",
            "created_at": now_iso(),
        })
        vid = v.vault_id
        audits = repo.audit_count()
    print(f"  wrote memory {mem_id[:8]} + 1 boundary; audit rows so far: {audits}")
    assert audits >= 2, "audit journal did not record the writes"

    # 2) Simulate a restart: reopen and confirm the memory + identity persist.
    with _open(cfg, create=False) as v:
        assert v.vault_id == vid, "vault_id changed across restart"
        row = v.conn.execute("SELECT summary FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row is not None, "memory did not survive restart"
    print("  restart survived: memory + vault_id intact")

    # 3) Backup, wipe the vault, restore, re-verify the memory.
    with _open(cfg, create=False) as v:
        info = backup_mod.snapshot(v, cfg.backups_dir)
    print(f"  snapshot: {info.path.name}")

    for p in [cfg.vault_path,
              Path(str(cfg.vault_path) + "-wal"),
              Path(str(cfg.vault_path) + "-shm")]:
        if p.exists():
            p.unlink()
    assert not cfg.vault_path.exists(), "wipe failed"
    print("  vault wiped")

    backup_mod.restore(info.path, cfg.vault_path)
    with _open(cfg, create=False) as v:
        assert v.vault_id == vid, "vault_id mismatch after restore"
        row = v.conn.execute("SELECT summary FROM memories WHERE id = ?", (mem_id,)).fetchone()
        assert row is not None, "memory missing after restore"
    print("  restore verified: memory + vault_id recovered")

    print("== PASS ==")
    return 0


def cmd_consolidate(cfg: Config, _args) -> int:
    """Run the idle-time consolidation pass over unprocessed raw events."""
    from aero.cognition.embeddings import OllamaEmbedder
    from aero.cognition.ollama_backend import OllamaCognition
    from aero.memory.consolidation import Consolidator
    from aero.memory.store import MemoryStore

    llm, emb = OllamaCognition(), OllamaEmbedder()
    if not llm.health_check() or not emb.health_check():
        print("Ollama models not available (need gemma4:e4b + embeddinggemma).")
        return 1
    with _open(cfg, create=False) as v:
        store = MemoryStore(v, actor="consolidation")
        res = Consolidator(store, llm, emb).run()
    print(f"consolidated: processed={res.processed} new={res.memories_created} "
          f"edges={res.edges_created} skipped={res.skipped}")
    print(f"beliefs: reinforced={res.beliefs_reinforced} revised={res.beliefs_revised} "
          f"decayed={res.beliefs_decayed} dormant={res.beliefs_dormant}")
    return 0


def _build_brain(cfg: Config, *, force: str | None = None):
    """Build Aero's brain (a two-speed router when configured, AERO-BRAIN-303),
    falling back to local gemma4 if a chosen single cloud brain is unreachable.
    Returns (llm, note-or-None)."""
    from aero import settings as st
    from aero.cognition.ollama_backend import OllamaCognition

    llm = st.build_router(cfg, force=force)
    # A bare single cloud brain that's unreachable -> fall back to local. (The
    # router handles its own primary->reflex fallback, so this only fires for a
    # non-routed single cloud profile.)
    if llm.__class__.__name__ == "CloudCognition" and not llm.health_check():
        note = ("Cloud brain unreachable (no API key or offline) — using local "
                "gemma4. Store a key: `aero brain --set-key <profile> <key>` "
                "and see docs/OPEN_BRAIN_SETUP.md.")
        return OllamaCognition(), note
    return llm, None


def cmd_chat(cfg: Config, args) -> int:
    """Interactive memory-in-the-loop chat with Aero (Milestone 2)."""
    from aero.agent import AeroAgent
    from aero.cognition.embeddings import OllamaEmbedder
    from aero.memory.store import MemoryStore
    from aero.perception import WorldStateProvider

    llm, note = _build_brain(cfg, force=getattr(args, "brain", None))
    if note:
        print(note)
    emb = OllamaEmbedder()
    if not llm.health_check():
        print("Brain not available. For local: start Ollama / pull gemma4:e4b.")
        return 1
    if not emb.health_check():
        print("embeddinggemma not available. Run: ollama pull embeddinggemma")
        return 1

    cfg.ensure_dirs()
    with _open(cfg) as v:
        store = MemoryStore(v, actor="user")
        # Live Tier-0 perception: Aero sees the active window/process each turn.
        agent = AeroAgent(store, llm, emb, world_provider=WorldStateProvider())
        n_mem = store.vault.conn.execute(
            "SELECT COUNT(*) AS n FROM memories WHERE summary NOT LIKE 'concept:%'"
        ).fetchone()["n"]
        print(f"Aero ({llm.model_name}) — {n_mem} memories in the vault.")
        print("Type your message. Ctrl-C or 'exit' to leave. "
              "Run `aero consolidate` afterwards to turn this chat into memory.\n")
        try:
            while True:
                try:
                    user = input("you> ").strip()
                except EOFError:
                    break
                if user.lower() in {"exit", "quit"}:
                    break
                if not user:
                    continue
                reply = agent.respond(user)
                print(f"aero> {reply}\n")
        except KeyboardInterrupt:
            print()
    print("(chat logged. run `aero consolidate` to consolidate it into memory.)")
    return 0


def cmd_voices(cfg: Config, args) -> int:
    """List Svara voice profiles and choose Aero's voice / TTS engine."""
    from aero import settings as st
    from aero.voice.svara_tts import (AERO_VOICE_CANDIDATES, SvaraTTS,
                                       describe_voice, voices)

    cur = st.load(cfg)
    if args.engine:
        cur.engine = args.engine
        st.save(cur, cfg)
        print(f"TTS engine set to: {cur.engine}")
        return 0
    if args.set:
        from aero.voice.kokoro_tts import KOKORO_VOICES
        if args.set in KOKORO_VOICES:      # a Kokoro voice -> switch to kokoro
            cur.kokoro_voice = args.set
            cur.engine = "kokoro"
            st.save(cur, cfg)
            print(f"Aero voice set to: {args.set} (Kokoro); engine=kokoro")
            return 0
        if args.set not in voices():
            print(f"Unknown voice '{args.set}'. Run `aero voices` to list them.")
            return 1
        cur.svara_voice = args.set
        cur.engine = "svara"
        st.save(cur, cfg)
        print(f"Aero voice set to: {args.set} ({describe_voice(args.set)}); engine=svara")
        return 0

    print(f"Current: engine={cur.engine}  svara_voice={cur.svara_voice} "
          f"({describe_voice(cur.svara_voice)})")
    reachable = SvaraTTS(cur.svara_voice, base_url=cur.svara_base_url).health_check()
    print(f"Svara server @ {cur.svara_base_url}: "
          f"{'reachable' if reachable else 'NOT reachable (see docs/SVARA_SETUP.md)'}\n")
    from aero.voice.kokoro_tts import KOKORO_VOICES
    print("\nKokoro voices (fast natural English, CPU — see docs/KOKORO_SETUP.md):")
    print("  " + ", ".join(KOKORO_VOICES))
    print("  select e.g.:  aero voices --set am_michael   (switches engine=kokoro)")

    print("\nSuggested for Aero (young Indian male):", ", ".join(AERO_VOICE_CANDIDATES))
    print("\nAll 38 Svara voices:")
    vs = voices()
    for i in range(0, len(vs), 2):
        a = vs[i]
        b = vs[i + 1] if i + 1 < len(vs) else ""
        print(f"  {a:<14}{describe_voice(a):<22}   {b:<14}{describe_voice(b) if b else ''}")
    print("\nSelect with:  aero voices --set hi_male")
    return 0


def cmd_brain(cfg: Config, args) -> int:
    """Show or switch Aero's brain — the registry of swappable profiles, plus the
    two-speed router and the keyring key vault (AERO-BRAIN-301/303/304)."""
    from aero import settings as st
    from aero.cognition import keys as _keys
    from aero.cognition.registry import registry

    cur = st.load(cfg)
    changed = False

    # -- key vault ---------------------------------------------------------
    if getattr(args, "set_key", None):
        pid, key = args.set_key
        if _keys.set_key(pid, key):
            print(f"Stored API key for '{pid}' in the OS keyring.")
        else:
            print("No keyring backend available. Install it (pip install -e "
                  "'.[keyring]') or use an env var. See docs/OPEN_BRAIN_SETUP.md.")
        return 0
    if getattr(args, "del_key", None):
        ok = _keys.delete_key(args.del_key)
        print(f"Removed stored key for '{args.del_key}'." if ok
              else f"No stored key for '{args.del_key}' (or no keyring backend).")
        return 0

    # -- mutations ---------------------------------------------------------
    if args.set:
        cur.brain_profile = args.set
        cur.brain = args.set  # keep legacy field in sync for older readers
        changed = True
    if args.provider:
        cur.brain = "cloud"
        cur.cloud_provider = args.provider
        changed = True
    if args.model:
        # Override the model of the active profile via a custom-profile entry.
        target = cur.brain_profile or (cur.cloud_provider if cur.brain == "cloud" else "cloud")
        cur.brains = {**cur.brains, target: {**cur.brains.get(target, {}), "model": args.model}}
        cur.cloud_model = args.model
        changed = True
    if args.reflex:
        cur.reflex_profile = args.reflex
        changed = True
    if args.primary:
        cur.primary_profile = args.primary
        changed = True
    if getattr(args, "private_only", None) is not None:
        cur.brain_private_only = args.private_only
        changed = True

    if changed:
        st.save(cur, cfg)
        print("Updated brain settings.\n")

    # -- status ------------------------------------------------------------
    reg = registry(cur.brains)
    active = st.resolve_brain_profile(cur)
    print(f"Active brain: {active.id}  ({active.model})")
    if cur.reflex_profile or cur.primary_profile:
        rp = st.resolve_brain_profile(cur, cur.reflex_profile or None)
        pp = st.resolve_brain_profile(cur, cur.primary_profile or None)
        print(f"  two-speed router: chat={pp.id}  tag/reflex={rp.id}"
              + ("  [private-only]" if cur.brain_private_only else ""))

    print("\nAvailable profiles:")
    for pid, prof in reg.items():
        key = _keys.resolve_key(prof)
        tag = "private" if prof.is_private else prof.cost_tier
        keystate = "no key needed" if (prof.is_local and prof.key_env is None) \
            else ("key set" if key else "NO KEY")
        mark = "*" if pid == active.id else " "
        print(f"  {mark} {pid:<11} {tag:<10} {keystate:<13} {prof.label}")

    print(f"\nKeyring backend: {'available' if _keys.keyring_available() else 'NOT installed (env-var fallback)'}")
    print("\nSwitch brain:     aero brain --set groq")
    print("Two-speed:        aero brain --primary groq --reflex local")
    print("Store a key:      aero brain --set-key groq <key>")
    print("Details:          docs/OPEN_BRAIN_SETUP.md")
    return 0


def cmd_control(cfg: Config, args) -> int:
    """Call the control plane (AERO-APP-201). Dispatches locally by default; with
    --remote it goes through a running daemon's IPC socket. Handy for scripting
    and for testing the same API the Control App uses."""
    import json as _json

    from aero.control.service import ControlService

    if args.op in (None, "ops"):
        print("\n".join(ControlService(cfg).ops()))
        return 0

    params = {}
    if args.params:
        try:
            params = _json.loads(args.params)
        except _json.JSONDecodeError as e:
            print(f"bad --params JSON: {e}")
            return 2

    if args.remote:
        from aero.control.ipc import ControlClient, ControlNotRunning
        try:
            resp = ControlClient(cfg).call(args.op, params)
        except ControlNotRunning as e:
            print(f"daemon not reachable: {e}")
            return 1
    else:
        resp = ControlService(cfg).dispatch(args.op, params)

    print(_json.dumps(resp, indent=2, ensure_ascii=False))
    return 0 if resp.get("ok") else 1


def cmd_mics(cfg: Config, _args) -> int:
    """List microphone input devices (for `aero voice --mic`)."""
    from aero.voice.mic import list_mics
    mics = list_mics()
    if not mics:
        print("No audio input devices found (or not on Windows).")
        return 1
    print("Microphones:")
    for m in mics:
        print(f"  {m}")
    return 0


def cmd_voice(cfg: Config, args) -> int:
    """Full voice loop: mic -> Whisper -> gemma4+memory -> speech-intent -> TTS."""
    from aero.agent import AeroAgent
    from aero.cognition.embeddings import OllamaEmbedder
    from aero.memory.store import MemoryStore
    from aero.perception import WorldStateProvider
    from aero import settings as st
    from aero.voice.loop import VoiceLoop
    from aero.voice.mic import Recorder
    from aero.voice.tts import SapiTTS

    llm, note = _build_brain(cfg, force=getattr(args, "brain", None))
    if note:
        print(note)
    emb = OllamaEmbedder()
    if not llm.health_check() or not emb.health_check():
        print("Need a reachable brain + embeddinggemma (Ollama for local).")
        return 1
    stt = st.build_stt(cfg, model=args.model)
    if not stt.health_check():
        if args.model == "indic":
            print("NeMo not installed. See docs/AI4BHARAT_SETUP.md "
                  "(pip install -e \".[indic_stt]\").")
        elif str(args.model).startswith("moonshine"):
            print("moonshine-onnx not installed. See docs/MOONSHINE_SETUP.md "
                  "(pip install -e \".[moonshine]\").")
        else:
            print("faster-whisper not installed. pip install -e \".[stt]\"")
        return 1

    # Selected TTS engine, with graceful fallback to SAPI if Svara isn't up.
    tts = st.build_tts(cfg)
    if not tts.health_check():
        if tts.__class__.__name__ != "SapiTTS":
            print(f"Selected voice engine unavailable ({tts.__class__.__name__}); "
                  "using SAPI. See docs/SVARA_SETUP.md to enable the real voice.")
        tts = SapiTTS()

    cfg.ensure_dirs()
    print(f"Loading STT ({args.model})... first run may download the model.")
    with _open(cfg) as v:
        store = MemoryStore(v, actor="user")
        agent = AeroAgent(store, llm, emb, world_provider=WorldStateProvider())
        if getattr(args, "realtime", False):
            from aero.voice.mic_stream import MicStream
            from aero.voice.realtime import RealtimeLoop
            RealtimeLoop(agent, stt, tts, mic=MicStream(device=args.mic)).run()
        else:
            loop = VoiceLoop(agent, stt, tts, recorder=Recorder(args.mic))
            if args.text:
                loop.run_text(speak=not args.no_speak)
            else:
                loop.run_voice()
    print("(voice session logged. run `aero consolidate` to form memory.)")
    return 0


def cmd_speak(cfg: Config, args) -> int:
    """Speak text through the selected TTS backend with a tone preset."""
    from aero import settings as st
    from aero.voice.speech_intent import SpeechIntent, render_ssml

    tts = st.build_tts(cfg)
    intent = SpeechIntent.from_tone(args.text, args.tone)
    if args.ssml:
        print(render_ssml(intent))
    if not tts.health_check():
        print(f"TTS backend ({tts.__class__.__name__}) unavailable. Intent/SSML shown above.")
        return 1
    if args.out:
        res = tts.synthesize(intent, args.out)
        print(f"wrote {args.out}" if res.ok else f"failed: {res.error}")
    else:
        res = tts.speak(intent)
        print(f"spoke ({res.seconds_compute:.2f}s)" if res.ok else f"failed: {res.error}")
    return 0 if res.ok else 2


def cmd_daemon(cfg: Config, args) -> int:
    """Run Aero's always-on background process (keep-warm + idle consolidation)."""
    from aero.daemon import AeroDaemon, DaemonConfig

    dcfg = DaemonConfig()
    if args.idle is not None:
        dcfg.idle_consolidate_seconds = args.idle
    daemon = AeroDaemon(cfg, dcfg)
    if args.once:
        # One tick for smoke-testing, then exit.
        if not daemon.llm.health_check() or not daemon.emb.health_check():
            print("Ollama models not available.")
            return 1
        daemon._warm_models()
        daemon._running = True
        daemon.tick()
        daemon.shutdown()
        print("daemon: single tick complete")
        return 0
    return daemon.start()


def cmd_watch(cfg: Config, args) -> int:
    """Print live Tier-0 world state — verify perception without the model."""
    import time
    from datetime import datetime

    from aero.perception import WorldStateProvider
    from aero.working_set import WorldState

    provider = WorldStateProvider()
    count = args.count if args.count else 0
    print("Watching Tier-0 world state (Ctrl-C to stop)...")
    try:
        i = 0
        while count == 0 or i < count:
            sample, switched = provider.poll()
            if not sample.ok:
                print("  (Tier-0 sensing unavailable on this platform)")
                return 0
            ws = WorldState.from_tier0(sample, time_str=datetime.now().strftime("%H:%M:%S"))
            flag = "  <-- app switch" if switched else ""
            print(f"  {ws.render()}{flag}")
            i += 1
            if count == 0 or i < count:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aero", description="Aero local companion")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create/upgrade the vault")
    sub.add_parser("status", help="show vault info")
    sub.add_parser("backup", help="snapshot the vault")
    r = sub.add_parser("restore", help="restore newest (or named) snapshot")
    r.add_argument("snapshot", nargs="?", help="path to a .aero-backup file")
    sub.add_parser("smoke", help="run the Milestone-1 acceptance smoke test")
    ch = sub.add_parser("chat", help="interactive memory-in-the-loop chat (Milestone 2)")
    ch.add_argument("--brain", metavar="PROFILE",
                    help="override brain for this session: a profile id "
                         "(local/groq/openai/...) or a base URL (default: persisted)")
    sub.add_parser("consolidate", help="turn logged raw events into durable memory")
    w = sub.add_parser("watch", help="print live Tier-0 world state (perception check)")
    w.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    w.add_argument("--count", type=int, default=0, help="number of samples (0 = forever)")
    d = sub.add_parser("daemon", help="run the always-on background process")
    d.add_argument("--once", action="store_true", help="run a single tick and exit")
    d.add_argument("--idle", type=float, default=None,
                   help="idle seconds before consolidating (default 120)")
    sp = sub.add_parser("speak", help="speak text via TTS (speech-intent -> SSML -> audio)")
    sp.add_argument("text", help="text to speak")
    sp.add_argument("--tone", default="neutral",
                    help="amused|teasing|serious|concerned|low|excited|neutral")
    sp.add_argument("--out", help="write WAV to this path instead of playing")
    sp.add_argument("--ssml", action="store_true", help="print the rendered SSML")
    sub.add_parser("mics", help="list microphone devices")
    vo = sub.add_parser("voices", help="list/select Aero's Svara voice + TTS engine")
    vo.add_argument("--set", help="choose a Svara voice profile, e.g. hi_male")
    vo.add_argument("--engine", choices=["sapi", "svara", "parler", "kokoro"],
                    help="set the TTS engine")
    vc = sub.add_parser("voice", help="full voice loop (mic -> STT -> Aero -> TTS)")
    vc.add_argument("--model", default="small",
                    help="STT: Whisper size ('small'...), 'moonshine[/tiny|/base]' "
                         "(fast English), or 'indic' (IndicConformer)")
    vc.add_argument("--mic", default=None, help="mic device name (see `aero mics`)")
    vc.add_argument("--text", action="store_true", help="type instead of speak (no mic)")
    vc.add_argument("--no-speak", action="store_true", help="don't voice replies (text mode)")
    vc.add_argument("--realtime", action="store_true",
                    help="hands-free real-time loop (VAD turn-taking + barge-in; no button)")
    vc.add_argument("--brain", metavar="PROFILE",
                    help="override brain for this session: a profile id "
                         "(local/groq/openai/...) or a base URL (default: persisted)")
    br = sub.add_parser("brain", help="show/switch Aero's brain (registry of swappable profiles)")
    br.add_argument("--set", metavar="PROFILE",
                    help="select the active brain profile (local/groq/openai/litellm/... "
                         "or legacy local|cloud)")
    br.add_argument("--provider", help="[legacy cloud] provider alias or base URL")
    br.add_argument("--model", help="override the model id for the selected profile")
    # Two-speed router (AERO-BRAIN-303)
    br.add_argument("--reflex", metavar="PROFILE",
                    help="set the cheap/private brain for tagging + reflex")
    br.add_argument("--primary", metavar="PROFILE",
                    help="set the strong brain for conversation")
    br.add_argument("--private-only", dest="private_only", action="store_true",
                    help="refuse a cloud primary; keep personal talk on-device")
    br.add_argument("--shared", dest="private_only", action="store_false",
                    help="allow a cloud primary (opposite of --private-only)")
    br.set_defaults(private_only=None)
    # Key vault (AERO-BRAIN-304)
    br.add_argument("--set-key", nargs=2, metavar=("PROFILE", "KEY"),
                    help="store an API key for a profile in the OS keyring")
    br.add_argument("--del-key", metavar="PROFILE", help="remove a stored API key")
    ctl = sub.add_parser("control", help="call the control plane (Control-App API)")
    ctl.add_argument("op", nargs="?", help="operation, e.g. status / brain.list "
                     "/ memory.list (omit or 'ops' to list all)")
    ctl.add_argument("params", nargs="?", help="JSON params, e.g. '{\"profile\":\"groq\"}'")
    ctl.add_argument("--remote", action="store_true",
                     help="call a running daemon over IPC instead of local dispatch")
    return p


_HANDLERS = {
    "init": cmd_init,
    "status": cmd_status,
    "backup": cmd_backup,
    "restore": cmd_restore,
    "smoke": cmd_smoke,
    "chat": cmd_chat,
    "consolidate": cmd_consolidate,
    "watch": cmd_watch,
    "daemon": cmd_daemon,
    "speak": cmd_speak,
    "mics": cmd_mics,
    "voice": cmd_voice,
    "voices": cmd_voices,
    "brain": cmd_brain,
    "control": cmd_control,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config.load()
    return _HANDLERS[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())

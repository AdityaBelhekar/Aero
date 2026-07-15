"""AeroDaemon — the always-on background process.

This is what makes Aero something you leave running rather than launch. Each tick
it:

  * polls Tier-0 world state and logs app-switch deltas as raw events,
  * keeps gemma4:e4b + embeddinggemma resident so a chat never eats a ~40s cold
    load (AERO-BGT-001: selective activation, but the core models stay warm),
  * when you've been idle a while, runs consolidation to turn accumulated raw
    events into durable memory (AERO-CON-001) — interruptibly: it consolidates in
    small batches and yields the moment you're active again (AERO-CON-003).

It is intentionally headless for Phase 0. The system-tray UI and daemon<->UI IPC
come later; the loop and lifecycle here are what the 14-day dogfood needs.
"""

from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from pathlib import Path

from aero.cognition.embeddings import OllamaEmbedder
from aero.cognition.ollama_backend import OllamaCognition
from aero.config import Config
from aero.memory.consolidation import Consolidator
from aero.memory.store import MemoryStore
from aero.perception import WorldStateProvider
from aero.vault.connection import now_iso, open_vault


@dataclass
class DaemonConfig:
    tick_seconds: float = 5.0
    keep_warm_seconds: float = 240.0     # re-touch models before Ollama's 5m unload
    idle_consolidate_seconds: float = 120.0  # idle this long -> consolidate
    consolidate_batch: int = 3           # small batches keep it interruptible
    keep_alive: str = "30m"
    control_ipc: bool = True             # serve the control plane for UIs to attach


class AeroDaemon:
    def __init__(self, cfg: Config, dcfg: DaemonConfig | None = None, *,
                 llm=None, emb=None, provider=None):
        self.cfg = cfg
        self.dcfg = dcfg or DaemonConfig()
        self.log = self._make_logger(cfg.logs_dir)

        # Dependencies are injectable so the daemon can be tested without Ollama.
        self.llm = llm or OllamaCognition()
        self.emb = emb or OllamaEmbedder()
        self.provider = provider or WorldStateProvider()

        cfg.ensure_dirs()
        self.vault = open_vault(cfg.vault_path)
        self.store = MemoryStore(self.vault, actor="consolidation")
        self.consolidator = Consolidator(self.store, self.llm, self.emb)

        self._running = False
        self._last_warm = 0.0
        self._control = None  # ControlServer, started in start()

    # -- lifecycle ---------------------------------------------------------
    def _make_logger(self, logs_dir: Path) -> logging.Logger:
        logs_dir.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("aero.daemon")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            fh = logging.FileHandler(logs_dir / "daemon.log", encoding="utf-8")
            sh = logging.StreamHandler()
            fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
            fh.setFormatter(fmt)
            sh.setFormatter(fmt)
            logger.addHandler(fh)
            logger.addHandler(sh)
        return logger

    def _install_signals(self) -> None:
        def _stop(signum, _frame):
            self.log.info("signal %s received, stopping", signum)
            self._running = False
        for sig in (signal.SIGINT, getattr(signal, "SIGTERM", signal.SIGINT)):
            try:
                signal.signal(sig, _stop)
            except (ValueError, OSError):
                pass  # not in main thread / unsupported

    def start(self) -> int:
        if not self.llm.health_check():
            self.log.error("gemma4:e4b not available via Ollama — cannot start")
            return 1
        if not self.emb.health_check():
            self.log.error("embeddinggemma not available via Ollama — cannot start")
            return 1
        self._install_signals()
        self._running = True
        self._warm_models()
        self._start_control()
        self.log.info("Aero daemon started (vault=%s)", self.vault.path)
        try:
            while self._running:
                try:
                    self.tick()
                except Exception:  # a bad tick must not kill the companion
                    self.log.exception("tick error")
                self._sleep(self.dcfg.tick_seconds)
        finally:
            self.shutdown()
        return 0

    def _sleep(self, seconds: float) -> None:
        # Sleep in small slices so a stop signal is honoured promptly.
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(0.25, max(0.0, end - time.monotonic())))

    def _start_control(self) -> None:
        """Serve the control plane so the Control App / overlay can attach
        (AERO-APP-201). Its own vault connection is opened lazily in the server
        thread — never shares the daemon's thread-bound connection."""
        if not self.dcfg.control_ipc:
            return
        try:
            from aero.control.ipc import ControlServer, socket_path
            from aero.control.service import ControlService
            self._control = ControlServer(ControlService(self.cfg), cfg=self.cfg)
            self._control.start_background()
            self.log.info("control IPC listening (%s)", socket_path(self.cfg))
        except Exception:
            self.log.exception("control IPC failed to start (continuing headless)")
            self._control = None

    def shutdown(self) -> None:
        self.log.info("Aero daemon stopped")
        if self._control is not None:
            try:
                self._control.stop()
            except Exception:
                pass
        try:
            self.vault.close()
        except Exception:
            pass

    # -- per-tick work -----------------------------------------------------
    def tick(self) -> None:
        sample, switched = self.provider.poll()
        if switched and sample.ok:
            self._log_world(f"active app changed to {sample.process_name} "
                            f"({sample.window_title})")
            self.log.info("world: -> %s", sample.process_name)

        now = time.monotonic()
        if now - self._last_warm >= self.dcfg.keep_warm_seconds:
            self._warm_models()

        self._maybe_consolidate(sample)

    def _warm_models(self) -> None:
        self.llm.ensure_loaded(self.dcfg.keep_alive)
        self.emb.ensure_loaded(self.dcfg.keep_alive)
        self._last_warm = time.monotonic()
        self.log.debug("models kept warm")

    def _log_world(self, text: str) -> None:
        import uuid
        self.vault.conn.execute(
            "INSERT INTO raw_events(id, ts, channel, payload) VALUES(?,?,?,?)",
            (uuid.uuid4().hex, now_iso(), "world", text),
        )
        self.vault.conn.commit()

    def _pending_events(self) -> int:
        return self.vault.conn.execute(
            "SELECT COUNT(*) AS n FROM raw_events WHERE consolidated_into IS NULL"
        ).fetchone()["n"]

    def _maybe_consolidate(self, sample) -> None:
        """Consolidate while the user is idle, in interruptible batches."""
        if not sample.ok or sample.idle_seconds < self.dcfg.idle_consolidate_seconds:
            return
        if self._pending_events() == 0:
            return
        self.log.info("idle %.0fs — consolidating pending events", sample.idle_seconds)
        total_new = total_reinforced = total_revised = 0
        while self._running:
            # Re-check activity between batches; yield the moment the user is back.
            cur, _ = self.provider.poll()
            if not cur.ok or cur.idle_seconds < self.dcfg.idle_consolidate_seconds:
                self.log.info("user active again — pausing consolidation")
                break
            if self._pending_events() == 0:
                break
            res = self.consolidator.run(limit=self.dcfg.consolidate_batch, sweep=False)
            total_new += res.memories_created
            total_reinforced += res.beliefs_reinforced
            total_revised += res.beliefs_revised
            if res.processed == 0:
                break
        # One staleness sweep after a consolidation session (cheap, no LLM).
        decayed, dormant = self.consolidator.sweep_staleness()
        self.log.info(
            "consolidation session: new=%d reinforced=%d revised=%d decayed=%d dormant=%d",
            total_new, total_reinforced, total_revised, decayed, dormant,
        )


def run_daemon(cfg: Config | None = None, dcfg: DaemonConfig | None = None) -> int:
    return AeroDaemon(cfg or Config.load(), dcfg).start()

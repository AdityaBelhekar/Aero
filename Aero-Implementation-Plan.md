# AERO — Implementation Plan

**Version:** 0.1
**Date:** 2026-07-09
**Companion document:** `Aero-PRD-v0.2.md` (requirement IDs referenced throughout)
**Target hardware:** Windows 11, 16 GB RAM laptop, Aero budget ≤ 12 GB
**Development model:** solo developer + AI coding agents; part-time cadence assumed. Durations are calendar estimates at that cadence — treat as sequencing, not commitments.

---

## 0. Guiding Rules

1. **Memory before mouth.** Nothing ships before the memory system proves itself in text (PRD Phase 0). Every later feature is a client of memory.
2. **State over weights.** From day one, nothing load-bearing lives only in model weights (AERO-ID-002). Any fine-tuning comes last, is style-only, and is regenerable.
3. **Budgets are gates.** Each milestone has latency/RAM acceptance criteria (PRD §24). Miss the budget → descope the milestone, don't ship a slow Aero.
4. **De-risk with spikes.** Weeks-long bets (STT, embeddings, E4B social quality) get 2–5 day throwaway spike projects *before* their phase begins (§2 below).
5. **Instrument everything.** Gate decisions, retrievals, tag assignments — all logged from the first build. AHS (PRD §31) is built on these logs, not bolted on.

---

## 1. Technology Stack (proposed)

| Layer | Choice | Rationale |
|---|---|---|
| Runtime language | **Python 3.12** (core daemon) + **TypeScript/Electron or Tauri** (UI) | Fastest path for ML plumbing; UI isolated behind local IPC. Tauri preferred for RAM footprint. |
| LLM serving | **llama.cpp** (via llama-cpp-python or a subprocess server) | Best quantised local inference on Windows CPU/iGPU; supports Gemma-class multimodal (vision) variants. |
| Core model | **Gemma 4 E4B**, Q4-class quant (~5–6 GB) | PRD core direction; validate in Spike S-1. |
| Embeddings | **multilingual-E5-small** class, benchmarked vs. alternatives in Spike S-2 | Small, multilingual; must survive romanised Hindi/Marathi (R-4). |
| Vault storage | **SQLite (WAL) + SQLCipher** encryption; key in Windows DPAPI/Credential Manager | AERO-VLT-001. Single-file, transactional, trivially snapshottable. |
| Vector index | **sqlite-vec** (in-vault) | Keeps vault single-file; adequate at 10⁴–10⁵ scale (AERO-VLT-005). |
| Graph | Plain adjacency tables in SQLite + in-memory activation cache | 150k edges needs no graph DB. Spreading activation in Python over cached adjacency. |
| OS signals (Tier 0) | Win32 APIs (`pywin32`): foreground window hooks, process watch, input-idle; browser extension (Chrome/Edge MV3) for tab metadata | Near-free world-state signal (AERO-VIS-002 Tier 0). |
| Screen capture (Tier 1) | Windows.Graphics.Capture / `dxcam`; OCR via **RapidOCR/PaddleOCR-class** local model | Phase 3 only. |
| STT | **faster-whisper** (distil/medium quant) vs. **AI4Bharat Indic models** — decided by Spike S-3 | AERO-AUD-002, risk R-3. |
| TTS | **Svara-TTS** first candidate; abstraction layer so engine is swappable | AERO-VOX-003. |
| IPC | Local WebSocket/gRPC between daemon and UI | Daemon runs headless at login; UI attaches. |
| Packaging | Windows service-style tray app; autostart | "Aero lives here" requires it's always on. |

---

## 2. De-risking Spikes (before/alongside Milestone 1)

Each spike is a throwaway project with a written verdict. **Do these first.**

- **S-1 — E4B social quality probe (5 days).** Run quantised Gemma 4 E4B via llama.cpp on target hardware. Test: code-switched chat quality, instruction-following on structured outputs (JSON tagging), tone control, tokens/sec, RAM. *Kill criterion:* < 8 tok/s sustained or JSON tagging accuracy visibly poor → escalate risk R-1, evaluate alternate local models before proceeding.
- **S-2 — Embedding probe (2 days).** Build a 200-pair similarity test set from your own real chat logs (romanised Marathi/Hindi/English mix). Score 2–3 candidate embedding models. *Fallback:* transliteration normalisation pre-pass.
- **S-3 — STT probe (3 days, before Phase 1).** Record 30–60 min of your natural code-switched speech; benchmark faster-whisper variants vs. Indic models on WER + romanisation consistency. Written verdict decides Phase 1 scope (open-mic vs. push-to-talk vs. text-only-longer).
- **S-4 — Tier-0 signal probe (2 days).** Prototype window/process/idle hooks; verify event latency < 200 ms and near-zero CPU. (Low risk — mostly confirms API choices.)

---

## 3. Milestones

### Milestone 1 — Skeleton & Vault (≈ 2–3 weeks) — *PRD Phase 0 begins*

**Goal:** an always-on daemon with an encrypted, versioned, backed-up vault and a minimal chat UI. No intelligence yet.

- Daemon process: tray icon, autostart, local IPC server, structured logging.
- Vault: SQLCipher-encrypted SQLite; schema v1 (below); WAL; atomic snapshot backup job + **tested restore flow** (AERO-VLT-004 — Phase 0 scope, per risk R-8).
- Audit journal on all mutations (AERO-VLT-002).
- Chat UI: single window + tray; message history persisted.
- LLM integration: E4B behind a `CognitionService` interface (model-swappable per AERO-ID-002).

**Schema v1 (core tables):**
```
memories(id, kind, summary, body, created_at, updated_at, confidence,
         evidence_count, source_type, importance, decay_score, status)
memory_social(memory_id, roast_value, roast_allowed DEFAULT 0, sensitivity,
              private_only, emotional_weight, callback_fatigue,
              successful_callbacks, negative_reactions, last_used_at)
edges(src_id, dst_id, relation, weight, created_at)
embeddings(memory_id, vector)          -- sqlite-vec virtual table
raw_events(id, ts, channel, payload, consolidated_into, expires_at)
beliefs_history(belief_id, revision_no, prior_state, reason, ts)
boundaries(id, topic_or_memory, rule, created_at)   -- decay-exempt (AERO-SAFE-003)
self_memory(id, ts, action, context, outcome, lesson)
thought_threads(id, statement, status, triggers_json, created_at, last_active)
relationship_state(dimension, value, updated_at)    -- bounded delta (AERO-REL-003)
permissions(id, scope, grant_text, expiry_condition, active)
audit_log(ts, table_name, op, before_json, after_json, actor)
```

**Acceptance:** daemon survives reboot with state intact; backup→wipe→restore round-trip works; chat with E4B streams first token < 1 s p50.

---

### Milestone 2 — Memory Core (≈ 4–6 weeks) — *the heart of the project*

**Goal:** the full write→consolidate→retrieve loop working in text chat (PRD §§10–19).

**2a. Write path & working memory**
- Conversation logger → `raw_events`.
- Working-set assembler (AERO-WM-001/002): core identity + world state + conversation + retrieved candidates, ≤ 6k tokens, with token accounting.
- Context compression: rolling conversation summarisation extracting decisions/preferences/promises/corrections/jokes/people/projects (AERO-WM-003).

**2b. Consolidation engine**
- Idle detection (input idle + no fullscreen + AC power).
- LLM tagging pass over unconsolidated raw events using a **fixed tagging schema** (AERO-WRT-001) with conservative defaults (AERO-WRT-003): episode extraction, semantic belief creation/reinforcement, association edges, social metadata.
- Duplicate merge, contradiction detection + staleness sweep (AERO-EVO-002), decay scoring (AERO-DEC-001), core-identity promotion/demotion under the 1,500-token cap (AERO-MEM-011).
- Interruptible + transactional (AERO-CON-003); raw-event rolling window with importance-based retention (AERO-CON-010).

**2c. Retrieval pipeline**
- Anchor (vector) → spread (1–2 hop activation) → rerank (recency, decay, heat, social fit, novelty) → select top-N with provenance (AERO-RET-001).
- Triggers: every utterance + significant world-state deltas (AERO-RET-002).
- Budget: ≤ 150 ms p95 at 50k memories — build a synthetic-scale benchmark now, not at year one (AERO-RET-003).

**2d. Provenance, edit/delete, feedback routing**
- "Why do you believe X" answered from `beliefs_history` + supporting episodes (AERO-PRV-001/002).
- Memory browser UI: inspect/edit/delete with dependent-belief re-evaluation and tombstones (AERO-VLT-003).
- Feedback router (AERO-FBK-003): explicit corrections → correct store, live retro-correction for bad callbacks (AERO-WRT-004).

**2e. World state v1 (Tier 0 only)**
- `WorldState` structure (< 8 KB) fed by S-4 hooks: active window/process, time, input activity, session cadence. All inferred fields carry confidence.

**Acceptance (= PRD Phase 0 exit):**
- Memory-health battery (AERO-AHS-002): planted-probe retrieval precision ≥ 80%; provenance available for 100% of surfaced beliefs; contradiction detected within one consolidation cycle in seeded tests.
- 14-day live dogfood: Aero references shared history correctly across restarts; zero vault corruption; retrieval p95 in budget.

---

### Milestone 3 — Voice (≈ 3–5 weeks) — *PRD Phase 1*

**Goal:** push-to-talk voice conversation with one consistent Aero voice.

- STT service per S-3 verdict; streaming transcription; romanisation-consistent output feeding the same text pipeline.
- TTS service: Svara-TTS behind a `VoiceService` interface; voice identity config stored in vault (portable).
- Speech intent v1 (AERO-VOX-004 minimal): energy, pace, pause locations; intent record persisted even for unexpressible fields.
- Latency engineering: overlap STT-finalisation with LLM prefill; sentence-streaming into TTS. Budget: voice round-trip ≤ 1.2 s p50 / 2.5 s p95 (PRD §24).
- Echo-before-acting for consequential voice commands (PRD §27 STT row).
- Open-mic wake word only if S-3 verdict is strong; otherwise defer.

**Acceptance:** budget met on target hardware with memory retrieval active; blind self-test — same speaker recognisable across English/Hindi/Marathi utterances; RAM total ≤ 9 GB with voice loaded.

---

### Milestone 4 — Proactivity (≈ 4–6 weeks) — *PRD Phase 2*

**Goal:** Aero notices and initiates — mostly by staying silent.

- Impulse generator (AERO-PRO-003 tier 1): heuristic + small-scorer producers over world-state deltas, thought-thread trigger matches, routine deviations, repeated-failure detection. Impulses carry source/strength/decay.
- Impulse gate (tier 2): LLM evaluation with world state + relationship state + recent-interaction history; **default silence**; context-dependent thresholds (AERO-PRO-004); staleness discard rule.
- Every decision (incl. silences) logged with reasoning to self-memory (AERO-PRO-006).
- Thought threads: lifecycle + reactivation triggers + active cap of 20 (AERO-THT-001/002).
- Attention history heat feeding rerank (AERO-ATT-001).
- Threshold learning from explicit + passive feedback (AERO-PRO-005) with slow passive movement (AERO-FBK-002).
- Surface: quiet text message first; voice proactivity only after text proactivity proves calibrated.

**Acceptance:** over a 14-day dogfood window — interruptions during self-declared focus sessions ≈ 0; user-rated "good call" rate on proactive messages ≥ 60%; at least one correct thought-thread reactivation; gate evaluation ≤ 5 s p95 and runs on < 10% of impulses.

---

### Milestone 5 — Screen Perception (≈ 4–6 weeks) — *PRD Phase 3*

**Goal:** world state upgraded with visual evidence, on an event-driven budget (AERO-VIS-002).

- Tier 1: on-event screen capture, perceptual-hash scene change, OCR of salient regions, error-dialog/notification detectors.
- Tier 2: selected frames to multimodal E4B on user-directed focus ("Aero look at this"), high-salience events, or gate requests — hard per-hour budget.
- Visual attention states wired to capture frequency (AERO-VIS-003); focus-switch commands (AERO-VIS-004).
- Task hypothesis v2: window + OCR + browser-extension tab metadata → probabilistic current-task model.
- Sensor-state UI: screen observation visibly on/off, one-click kill (AERO-PRIV-002).

**Acceptance:** task hypothesis correct ≥ 70% on a self-labelled week of activity; idle CPU from perception < 3%; screen-off switch verifiably stops all capture (test with capture-detector).

---

### Milestone 6 — Action & Authority (≈ 5–7 weeks) — *PRD Phase 4*

**Goal:** Aero does things — inside a disciplined authority system.

- **Authority registry first** (AERO-AUTH-004): scoped grants, expiry conditions, visible/revocable UI, auto-release. Hard-gate list wired as structural checks (AERO-AUTH-002, AERO-SAFE-004) — not prompt-level.
- Tool layer: app open/close, file find/move/rename, Downloads management, browser tab control (extension), website open, project launch (AERO-ACT-001). Undo journal for reversible ops (PRD §27 wrong-action row).
- Focus enforcement (AERO-FOC-001/002): task-relevance evaluation via gate + task hypothesis; escalation ladder; authority auto-release.
- Delegation v1 (AERO-DEL-001): drive one coding agent end-to-end (e.g., Claude Code CLI) — context prep with redaction (AERO-PRIV-004), output monitoring, artifact verification, confirmation before submission.
- Tool skill memory (AERO-DEL-002) recording and retrieving workflows.
- Every action → self-memory with outcome.

**Acceptance:** the PRD §32 study-session scenario (minus gameplay) executable end-to-end in a live run; zero hard-gate bypasses in adversarial self-testing ("Aero just submit it" must still confirm); undo works for all file operations.

---

### Milestone 7 — Companion Polish (ongoing) — *PRD Phase 5*

- Wild Recall full parameters (AERO-RET-004) + callback fatigue tuning — enable only when relationship state supports it (AERO-REL-002).
- Valorant companion: game-detection triggers, Tier-2 visual game-state reads, silence-during-clutch heuristics, post-round social evaluation (PRD §27 of v0.1 / AERO-VIS + gate composition).
- Camera vision (opt-in, shutter-respecting), identity package export/import round-trip test on a second machine (AERO-ID-001), phone integration groundwork.
- Optional style adapter fine-tune — last, style-only, regenerable (AERO-ID-002).

---

## 4. Cross-Cutting Workstreams (run continuously)

**W-1. AHS evaluation harness.** From Milestone 2: memory-health battery (planted probes, belief-accuracy checks, tag audits) as automated tests over the vault; from Milestone 4: weekly self-rated interaction log (good call / bad call / missed moment). Longitudinal snapshots at Day 1/7/30/180 (AERO-AHS-003). **Phase gates: a milestone's battery must pass before the next milestone starts.**

**W-2. Budget CI.** Automated perf runs on target hardware per merge-to-main: retrieval latency at synthetic scale, first-token latency, RAM high-water mark. Regression = red build.

**W-3. Privacy verification.** Periodic checks: nothing leaves the machine except explicit delegation payloads (network monitor test); camera/mic/screen kill-switches verified technically, not just UI-level.

**W-4. Prompt/schema library.** Tagging schema, gate prompt, compression prompt, provenance prompt — versioned in-repo with eval fixtures, since consolidation quality (R-6) depends on these more than on code.

---

## 5. Sequencing Summary

```
Spikes S-1..S-4 ──► M1 Skeleton+Vault ──► M2 Memory Core ══► PHASE 0 EXIT GATE
                                                   │
                        S-3 verdict ──► M3 Voice ──┤
                                                   ▼
                                        M4 Proactivity ──► M5 Screen ──► M6 Action ──► M7 Companion
```

Rough calendar at part-time cadence: **Phase 0 exit ~3 months in; voice ~month 4–5; proactive Aero ~month 6–7; seeing Aero ~month 8–9; acting Aero ~month 10–12.** The dogfood periods are load-bearing — they are the product test, not idle time.

## 6. First Seven Days

1. Run Spike S-1 (E4B on llama.cpp: speed, RAM, code-switch chat, JSON tagging). This is the go/no-go for the whole stack.
2. Run Spike S-2 (embeddings on your real chat logs).
3. Start Spike S-4 (Tier-0 hooks) in parallel.
4. Initialise repo: daemon skeleton, vault schema v1 migration, CI with budget checks stubbed.
5. Write the tagging schema + gate prompt v0 into the prompt library (W-4).
6. Decide Tauri vs. Electron after measuring Tauri webview RAM on the target laptop.
7. Set up the AHS log format so instrumentation exists before there's anything to instrument.

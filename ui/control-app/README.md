# Aero Control App (Tauri) — scaffold

The window where you configure Aero: brain, voice, personality, permissions +
kill switch, and the memory browser (v0.3 Pillar 2, AERO-APP-201..207).

**This is a scaffold.** The whole management API is done and tested in Python
(`aero.control`); this app is a thin Tauri shell over it. It was authored on a
headless Ubuntu box and **has not been compiled here** — building it needs the
Rust toolchain + system WebKit (see `docs/CONTROL_APP_SETUP.md`) and a display.

## Architecture

```
  Tauri window (this app)              Python daemon
  ┌───────────────────────┐           ┌──────────────────────────┐
  │ src/  (HTML/CSS/JS UI) │  invoke   │ aero.control.ControlService│
  │   control(op, params)  │──────────▶│   .dispatch(op, params)   │
  │ src-tauri/ (Rust)      │  socket   │ served by ControlServer    │
  │   forwards to socket   │◀──────────│ over $AERO_HOME/control.sock│
  └───────────────────────┘   JSON     └──────────────────────────┘
```

No logic lives in this app — it renders whatever `ControlService` returns. The
same API is reachable from the CLI (`aero control <op>`), which is the easy way
to exercise it without building the GUI.

## Run (once the toolchain + daemon are ready)

```bash
# 1. start the daemon so the control socket exists
AERO_HOME=~/.aero aero daemon        # (needs Ollama; see main README)

# 2. run the app pointed at the same home
cd ui/control-app
npm install
AERO_HOME=~/.aero npm run dev
```

See `docs/CONTROL_APP_SETUP.md` for the full dependency list and the OAuth /
account-login piece (AERO-APP-202), which is the next slice on this app.

## Layout

```
ui/control-app/
  package.json            # Tauri CLI
  src/                    # frontend (no bundler; plain HTML/CSS/JS)
    index.html  app.js  styles.css
  src-tauri/
    Cargo.toml  build.rs  tauri.conf.json
    src/main.rs  src/lib.rs   # the `control` bridge command -> daemon socket
```

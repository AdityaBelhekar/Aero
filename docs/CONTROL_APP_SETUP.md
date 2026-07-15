# Control App — setup (M10 / AERO-APP-201/202)

The Control App is the window where you own and tune Aero: **brain manager, voice
manager, personality dials, permissions + kill switch, memory browser**. It's a
Tauri shell over the Python control plane — a thin client, no logic of its own.

> **Status:** the backend (`aero.control`: service, IPC, CLI) is complete and
> tested. The Tauri frontend in `ui/control-app/` is a **scaffold** — authored on
> a headless box and not yet compiled. It needs the toolchain below plus a
> display. Until then, drive the exact same API from the CLI:
> `aero control status`, `aero control brain.list`, `aero control memory.list`, …

## What's already usable (no GUI needed)

```bash
aero control ops                       # list every operation
aero control status                    # brain/voice/counts/killswitch
aero control brain.set '{"profile":"groq"}'
aero control persona.set '{"dials":{"roast_level":0.6}}'
aero control perms.grant '{"scope":"apps","on":true}'
aero control memory.list '{"query":"coffee"}'
aero control --remote status           # via a running daemon's IPC socket
```

The daemon serves this over `$AERO_HOME/control.sock` (Linux) automatically
(`DaemonConfig.control_ipc`), which is what the GUI attaches to.

## Building the GUI

### 1. System dependencies (needs sudo — Ubuntu 26.04)

Tauri needs WebKitGTK + build tools:

```bash
sudo apt update
sudo apt install -y libwebkit2gtk-4.1-dev build-essential curl wget file \
  libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev
```

### 2. Rust toolchain (no sudo)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

### 3. Node + Tauri CLI

```bash
cd ui/control-app
npm install
```

### 4. Run

```bash
# terminal A: the daemon (creates the control socket) — needs Ollama running
AERO_HOME=~/.aero aero daemon

# terminal B: the app, pointed at the same data root
cd ui/control-app
AERO_HOME=~/.aero npm run dev        # or: npm run build  for a bundle
```

**`AERO_HOME` must match** what the daemon uses — that's how the app finds the
control socket. Generate app icons before `npm run build` with
`npx tauri icon path/to/logo.png`.

### Wayland note (Ubuntu 26.04)

Ubuntu 26.04 defaults to Wayland. WebKitGTK generally works, but if the window
misbehaves, try `WEBKIT_DISABLE_COMPOSITING_MODE=1` or run under XWayland. (This
same session-type question gates the avatar overlay — see
`spikes/S11_S12_NOTES.md`.)

## Account login / OAuth (AERO-APP-202) — next slice

The plan calls for logging into AI accounts via a real OAuth webview inside the
Control App (far more robust + ToS-friendly than a headless session — it turns
the scary Spike S-6 into a normal UX task). That panel isn't built yet. The seam
is ready: an account-login brain becomes another registry profile (M8), and the
webview flow lands here. Until then, **API-key + LiteLLM cover the same need** —
store keys with `aero brain --set-key <profile> <key>` (OS keyring) or via the
Brain panel.

## Security notes

- The control socket is **local-only** (Unix-domain socket / loopback TCP); no
  network port is exposed.
- API keys never travel over the socket except when you explicitly set one
  (`brain.set_key`); they're stored in the OS keyring, never in `settings.json`.
- The **kill switch** (`perms.killswitch`) forces every capability grant off at
  once — it's in the header of every panel.

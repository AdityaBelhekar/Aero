//! Aero Control App — Tauri backend (AERO-APP-201).
//!
//! This is a *thin bridge*: the whole management API lives in Python
//! (`aero.control.ControlService`), served over a local socket by the daemon.
//! The one Tauri command here forwards `{op, params}` from the web UI to that
//! socket and returns the JSON response. No logic lives on this side — swapping
//! the UI or the daemon never touches the other.
//!
//! Socket location mirrors Python's `Config`: `$AERO_HOME/control.sock`
//! (Unix) or `$AERO_HOME/control.port` (Windows loopback TCP). Launch the app
//! with `AERO_HOME` pointing at the same data root the daemon uses.

use std::io::{BufRead, BufReader, Write};
use std::path::PathBuf;

fn aero_home() -> Result<PathBuf, String> {
    // Match aero.config._default_home: honour AERO_HOME; otherwise the caller
    // must set it (the app can't know the repo's ./data root on its own).
    match std::env::var("AERO_HOME") {
        Ok(h) if !h.is_empty() => Ok(PathBuf::from(h)),
        _ => Err("AERO_HOME is not set — launch the Control App with AERO_HOME \
                  pointing at the same data root as the daemon."
            .to_string()),
    }
}

/// Send one request line to the daemon and read one JSON response line.
fn send_line(request: &str) -> Result<serde_json::Value, String> {
    let home = aero_home()?;

    #[cfg(unix)]
    {
        use std::os::unix::net::UnixStream;
        let path = home.join("control.sock");
        let stream = UnixStream::connect(&path)
            .map_err(|e| format!("daemon not reachable at {path:?}: {e}"))?;
        return roundtrip(stream, request);
    }

    #[cfg(windows)]
    {
        use std::net::TcpStream;
        let port = std::fs::read_to_string(home.join("control.port"))
            .map_err(|e| format!("daemon not running (no control.port): {e}"))?;
        let port: u16 = port.trim().parse().map_err(|e| format!("bad port: {e}"))?;
        let stream = TcpStream::connect(("127.0.0.1", port))
            .map_err(|e| format!("daemon not reachable on 127.0.0.1:{port}: {e}"))?;
        return roundtrip(stream, request);
    }

    #[allow(unreachable_code)]
    Err("unsupported platform".to_string())
}

fn roundtrip<S: Write + std::io::Read>(
    mut stream: S,
    request: &str,
) -> Result<serde_json::Value, String> {
    stream
        .write_all(request.as_bytes())
        .map_err(|e| e.to_string())?;
    let mut reader = BufReader::new(stream);
    let mut resp = String::new();
    reader.read_line(&mut resp).map_err(|e| e.to_string())?;
    serde_json::from_str(resp.trim()).map_err(|e| format!("bad response: {e}"))
}

/// The single command the UI calls: `invoke('control', {op, params})`.
#[tauri::command]
fn control(op: String, params: serde_json::Value) -> Result<serde_json::Value, String> {
    let req = serde_json::json!({ "op": op, "params": params });
    let line = format!("{}\n", req);
    send_line(&line)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![control])
        .run(tauri::generate_context!())
        .expect("error while running Aero Control");
}

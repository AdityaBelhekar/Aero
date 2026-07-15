// Aero Control — frontend. All logic lives in the Python control plane; this just
// calls control(op, params) via the Tauri bridge and renders the result.

const invoke = (cmd, args) => window.__TAURI__.core.invoke(cmd, args);

/** Call the daemon's control plane. Returns the `result` or throws on error. */
async function control(op, params = {}) {
  let resp;
  try {
    resp = await invoke("control", { op, params });
  } catch (e) {
    throw new Error(String(e)); // bridge/socket failure (daemon down, AERO_HOME unset)
  }
  if (!resp.ok) throw new Error(resp.error || "unknown error");
  return resp.result;
}

function toast(msg, ok = true) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = ok ? "show" : "show err";
  setTimeout(() => (t.className = ""), 2600);
}

// -- tabs ------------------------------------------------------------------
document.querySelectorAll("#tabs button").forEach((btn) => {
  btn.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.panel).classList.add("active");
  };
});

// -- status / kill switch --------------------------------------------------
async function refreshStatus() {
  const pill = document.getElementById("status-pill");
  try {
    const s = await control("status");
    pill.textContent = `brain: ${s.brain.active}${s.brain.private ? " (private)" : ""}`;
    pill.className = "pill ok";
    const kb = document.getElementById("killswitch");
    kb.classList.toggle("armed", s.killswitch);
    kb.textContent = s.killswitch ? "◉ Kill switch ON" : "◉ Kill switch";
  } catch (e) {
    pill.textContent = "daemon offline";
    pill.className = "pill err";
  }
}

document.getElementById("killswitch").onclick = async () => {
  try {
    const cur = await control("perms.get");
    const r = await control("perms.killswitch", { on: !cur.killswitch });
    toast(r.killswitch ? "Kill switch ARMED — actions off" : "Kill switch released");
    refreshStatus();
    loadPerms();
  } catch (e) {
    toast(e.message, false);
  }
};

// -- brain -----------------------------------------------------------------
async function loadBrain() {
  const { profiles, active } = await control("brain.list");
  const list = document.getElementById("brain-list");
  list.innerHTML = "";
  const opts = profiles.map((p) => `<option value="${p.id}">${p.id}</option>`).join("");
  for (const p of profiles) {
    const card = document.createElement("div");
    card.className = "card" + (p.active ? " active" : "");
    card.innerHTML = `
      <div class="card-h"><b>${p.id}</b>
        <span class="tag ${p.private ? "priv" : ""}">${p.private ? "private" : p.cost_tier}</span></div>
      <div class="model">${p.model}</div>
      <div class="lbl">${p.label || ""}</div>
      <div class="row">
        <span class="key ${p.key_set ? "ok" : "no"}">${p.key_set ? "key set" : "no key"}</span>
        <button ${p.active ? "disabled" : ""} data-id="${p.id}">${p.active ? "active" : "use"}</button>
      </div>`;
    card.querySelector("button").onclick = async () => {
      try { await control("brain.set", { profile: p.id }); toast(`Brain → ${p.id}`); loadBrain(); refreshStatus(); }
      catch (e) { toast(e.message, false); }
    };
    list.appendChild(card);
  }
  const router = await control("brain.get");
  const prim = document.getElementById("router-primary");
  const refl = document.getElementById("router-reflex");
  prim.innerHTML = `<option value="">(active: ${active})</option>` + opts;
  refl.innerHTML = `<option value="">(same as active)</option>` + opts;
  prim.value = router.primary || "";
  refl.value = router.reflex || "";
  document.getElementById("router-private").checked = !!router.private_only;
}

document.getElementById("router-save").onclick = async () => {
  try {
    await control("brain.router", {
      primary: document.getElementById("router-primary").value,
      reflex: document.getElementById("router-reflex").value,
      private_only: document.getElementById("router-private").checked,
    });
    toast("Router saved");
  } catch (e) { toast(e.message, false); }
};

// -- voice -----------------------------------------------------------------
async function loadVoice() {
  const v = await control("voice.list");
  const sel = document.getElementById("voice-engine");
  sel.innerHTML = v.engines.map((e) => `<option ${e === v.active_engine ? "selected" : ""}>${e}</option>`).join("");
  document.getElementById("voice-stt").value = v.stt_model;
}
document.getElementById("voice-save").onclick = async () => {
  try {
    await control("voice.set", {
      engine: document.getElementById("voice-engine").value,
      stt_model: document.getElementById("voice-stt").value,
    });
    toast("Voice saved");
  } catch (e) { toast(e.message, false); }
};

// -- persona ---------------------------------------------------------------
async function loadPersona() {
  const { dials } = await control("persona.get");
  const box = document.getElementById("persona-dials");
  box.innerHTML = "";
  for (const [key, val] of Object.entries(dials)) {
    const row = document.createElement("label");
    row.className = "dial";
    if (typeof val === "number") {
      row.innerHTML = `<span>${key}</span>
        <input type="range" min="0" max="1" step="0.05" value="${val}" data-key="${key}" />
        <output>${val}</output>`;
      const r = row.querySelector("input");
      r.oninput = () => (row.querySelector("output").textContent = r.value);
    } else {
      row.innerHTML = `<span>${key}</span><input value="${Array.isArray(val) ? val.join(",") : val}" data-key="${key}" data-str="1" />`;
    }
    box.appendChild(row);
  }
}
document.getElementById("persona-save").onclick = async () => {
  const dials = {};
  document.querySelectorAll("#persona-dials [data-key]").forEach((el) => {
    const k = el.dataset.key;
    if (el.dataset.str) {
      dials[k] = k === "quiet_hours" ? el.value.split(",").map((n) => parseInt(n, 10)) : el.value;
    } else dials[k] = parseFloat(el.value);
  });
  try { await control("persona.set", { dials }); toast("Personality saved"); }
  catch (e) { toast(e.message, false); }
};

// -- permissions -----------------------------------------------------------
async function loadPerms() {
  const p = await control("perms.get");
  const box = document.getElementById("perms-list");
  box.innerHTML = "";
  for (const scope of p.all_scopes) {
    const row = document.createElement("label");
    row.className = "perm";
    row.innerHTML = `<input type="checkbox" ${p.scopes[scope] ? "checked" : ""} ${p.killswitch ? "disabled" : ""}/>
      <span>${scope}</span>`;
    row.querySelector("input").onchange = async (e) => {
      try { await control("perms.grant", { scope, on: e.target.checked }); toast(`${scope}: ${e.target.checked ? "granted" : "revoked"}`); }
      catch (err) { toast(err.message, false); }
    };
    box.appendChild(row);
  }
}

// -- memory ----------------------------------------------------------------
async function loadMemory(query = "") {
  const { memories } = await control("memory.list", query ? { query } : {});
  const box = document.getElementById("mem-list");
  box.innerHTML = memories.length ? "" : "<p class='dim'>no memories yet</p>";
  for (const m of memories) {
    const row = document.createElement("div");
    row.className = "mem-row";
    row.innerHTML = `<span class="k ${m.kind}">${m.kind}</span>
      <span class="s">${m.summary}</span>
      <span class="c">${(m.confidence ?? 0).toFixed(2)}</span>
      <button title="forget">✕</button>`;
    row.querySelector("button").onclick = async () => {
      try { await control("memory.delete", { id: m.id }); toast("forgotten (tombstoned)"); loadMemory(query); }
      catch (e) { toast(e.message, false); }
    };
    box.appendChild(row);
  }
}
document.getElementById("mem-search").onclick = () => loadMemory(document.getElementById("mem-query").value.trim());

// -- boot ------------------------------------------------------------------
async function boot() {
  await refreshStatus();
  for (const [name, fn] of [["brain", loadBrain], ["voice", loadVoice],
                            ["persona", loadPersona], ["perms", loadPerms], ["memory", () => loadMemory()]]) {
    try { await fn(); } catch (e) { console.warn(name, e); }
  }
}
boot();

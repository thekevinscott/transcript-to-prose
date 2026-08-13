// Transcript -> prose. Vanilla JS, no build step.
//
// The whole UI is generated from /api/config, which mirrors CONTROLS and
// PANELS in app/config.py. To add a slider or an output panel, edit that file;
// nothing here needs to change.

const $ = (sel) => document.querySelector(sel);
const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem("ttp:" + key); return v === null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem("ttp:" + key, JSON.stringify(value)); } catch {}
  },
};

const els = {
  transcript: $("#transcript"),
  output: $("#col-output"),
  controls: $("#controls"),
  status: $("#status"),
  run: $("#run"),
  clear: $("#clear"),
  wordcount: $("#wordcount"),
};

let CONFIG = null;
let values = {};       // control id -> index
let enabled = {};      // panel id -> bool
const panelEls = {};   // panel id -> { root, body, dot }

let debounceTimer = null;
let inFlight = null;   // AbortController
let lastRunKey = null;

// ---------------------------------------------------------------- rendering

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// Deliberately tiny: the prose panel uses white-space: pre-wrap, so we only
// need inline emphasis and headings, not a real markdown parser.
function renderProse(text) {
  return escapeHtml(text)
    .replace(/^(#{1,4})\s+(.+)$/gm, (_, h, t) => `<h${Math.min(4, h.length + 2)}>${t}</h${Math.min(4, h.length + 2)}>`)
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/`([^`\n]+)`/g, "<code>$1</code>");
}

function buildPanels() {
  els.output.innerHTML = "";
  for (const panel of CONFIG.panels) {
    const root = document.createElement("div");
    root.className = "panel";
    root.dataset.kind = panel.kind;
    root.dataset.state = "idle";
    root.hidden = !enabled[panel.id];

    const head = document.createElement("div");
    head.className = "panel-head";
    head.innerHTML = `<span class="dot"></span><h3></h3>`;
    head.querySelector("h3").textContent = panel.label;

    const copy = document.createElement("button");
    copy.className = "ghost";
    copy.textContent = "Copy";
    copy.style.marginLeft = "auto";
    copy.addEventListener("click", () => {
      navigator.clipboard.writeText(root.dataset.raw || "").then(() => {
        copy.textContent = "Copied";
        setTimeout(() => (copy.textContent = "Copy"), 1200);
      });
    });
    head.appendChild(copy);

    const body = document.createElement("div");
    body.className = "panel-body";
    body.innerHTML = `<span class="placeholder">waiting for transcript</span>`;

    root.append(head, body);
    els.output.appendChild(root);
    panelEls[panel.id] = { root, body, def: panel };
  }
}

function setPanelState(id, state) {
  const p = panelEls[id];
  if (p) p.root.dataset.state = state;
}

function clearPanel(id, message) {
  const p = panelEls[id];
  if (!p) return;
  p.root.dataset.raw = "";
  p.body.innerHTML = `<span class="placeholder"></span>`;
  p.body.firstChild.textContent = message;
}

function appendDelta(id, text) {
  const p = panelEls[id];
  if (!p) return;
  if (p.root.dataset.raw === undefined || p.body.querySelector(".placeholder")) {
    p.body.textContent = "";
    p.root.dataset.raw = "";
  }
  p.root.dataset.raw += text;
  p.body.textContent = p.root.dataset.raw;
  p.body.scrollTop = p.body.scrollHeight;
}

function finishPanel(id, event) {
  const p = panelEls[id];
  if (!p) return;
  p.root.classList.remove("stale");
  if (p.def.kind === "list") {
    const items = event.items || [];
    p.root.dataset.raw = items.map((i) => "- " + i).join("\n");
    if (!items.length) {
      p.body.innerHTML = `<span class="placeholder">nothing found</span>`;
    } else {
      const ul = document.createElement("ul");
      for (const item of items) {
        const li = document.createElement("li");
        li.textContent = item;
        ul.appendChild(li);
      }
      p.body.innerHTML = "";
      p.body.appendChild(ul);
    }
  } else {
    const text = event.text || p.root.dataset.raw || "";
    p.root.dataset.raw = text;
    p.body.innerHTML = text.trim() ? renderProse(text) : `<span class="placeholder">nothing returned</span>`;
  }
  setPanelState(id, "done");
}

function failPanel(id, message) {
  const p = panelEls[id];
  if (!p) return;
  p.root.classList.remove("stale");
  p.body.innerHTML = `<div class="failure"></div>`;
  p.body.firstChild.textContent = message;
  setPanelState(id, "error");
}

// ---------------------------------------------------------------- controls

function buildControls() {
  els.controls.innerHTML = "";

  for (const control of CONFIG.controls) {
    const wrap = document.createElement("div");
    wrap.className = "control";

    const label = document.createElement("div");
    label.className = "control-label";
    const name = document.createElement("span");
    name.textContent = control.label;
    const current = document.createElement("b");
    label.append(name, current);
    wrap.appendChild(label);

    const setLabel = (i) => (current.textContent = control.scale[i] || "");

    if (control.kind === "select") {
      const select = document.createElement("select");
      control.scale.forEach((opt, i) => {
        const o = document.createElement("option");
        o.value = String(i);
        o.textContent = opt;
        select.appendChild(o);
      });
      select.value = String(values[control.id]);
      current.textContent = "";
      select.addEventListener("change", () => {
        values[control.id] = Number(select.value);
        store.set("controls", values);
        schedule(0);
      });
      wrap.appendChild(select);
    } else {
      const range = document.createElement("input");
      range.type = "range";
      range.min = "0";
      range.max = String(control.scale.length - 1);
      range.step = "1";
      range.value = String(values[control.id]);
      setLabel(values[control.id]);
      range.addEventListener("input", () => setLabel(Number(range.value)));
      range.addEventListener("change", () => {
        values[control.id] = Number(range.value);
        store.set("controls", values);
        schedule(0);
      });
      wrap.appendChild(range);
    }
    els.controls.appendChild(wrap);
  }

  // Panel on/off switches, generated from the same config.
  const group = document.createElement("div");
  group.className = "control-group";
  group.innerHTML = `<div class="control-label"><span>Outputs</span></div>`;
  const toggles = document.createElement("div");
  toggles.className = "toggles";
  for (const panel of CONFIG.panels) {
    const label = document.createElement("label");
    label.className = "toggle";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = !!enabled[panel.id];
    box.addEventListener("change", () => {
      enabled[panel.id] = box.checked;
      store.set("enabled", enabled);
      panelEls[panel.id].root.hidden = !box.checked;
      if (box.checked) schedule(0);
    });
    label.append(box, document.createTextNode(panel.label));
    toggles.appendChild(label);
  }
  group.appendChild(toggles);
  els.controls.appendChild(group);
}

// ---------------------------------------------------------------- running

function activePanels() {
  return CONFIG.panels.filter((p) => enabled[p.id]).map((p) => p.id);
}

function runKey(transcript) {
  return JSON.stringify([transcript, values, activePanels()]);
}

function setStatus(text, cls) {
  els.status.textContent = text;
  els.status.className = "status" + (cls ? " " + cls : "");
}

function schedule(delay) {
  clearTimeout(debounceTimer);
  const wait = delay === undefined ? CONFIG.debounce_ms : delay;
  debounceTimer = setTimeout(run, wait);
}

async function run(force) {
  const transcript = els.transcript.value.trim();
  const panels = activePanels();

  if (transcript.length < CONFIG.min_chars || !panels.length) {
    if (inFlight) inFlight.abort();
    setStatus(transcript.length ? `${CONFIG.min_chars - transcript.length} more chars` : "idle");
    return;
  }

  const key = runKey(transcript);
  if (!force && key === lastRunKey) return;
  lastRunKey = key;

  if (inFlight) inFlight.abort();
  const controller = new AbortController();
  inFlight = controller;

  for (const id of panels) {
    panelEls[id].root.classList.add("stale");
    setPanelState(id, "working");
  }
  setStatus("working", "working");
  const started = performance.now();

  let response;
  try {
    response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ transcript, controls: values, panels }),
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name !== "AbortError") setStatus("network error", "error");
    return;
  }

  if (!response.ok) {
    setStatus("http " + response.status, "error");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let firstPaint = true;

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.trim()) continue;
        let event;
        try { event = JSON.parse(line); } catch { continue; }
        handleEvent(event, () => {
          if (firstPaint) { firstPaint = false; }
        });
      }
    }
  } catch (err) {
    if (err.name === "AbortError") return;
    setStatus("stream error", "error");
    return;
  }

  if (inFlight === controller) inFlight = null;
  setStatus(`${((performance.now() - started) / 1000).toFixed(1)}s`);
}

function handleEvent(event, onPaint) {
  switch (event.type) {
    case "start":
      setPanelState(event.panel, "working");
      break;
    case "delta":
      panelEls[event.panel]?.root.classList.remove("stale");
      appendDelta(event.panel, event.text);
      onPaint();
      break;
    case "done":
      finishPanel(event.panel, event);
      onPaint();
      break;
    case "error":
      if (event.panel) failPanel(event.panel, event.message);
      else setStatus(event.message, "error");
      break;
  }
}

// ---------------------------------------------------------------- wiring

function updateWordCount() {
  const words = els.transcript.value.trim().split(/\s+/).filter(Boolean).length;
  els.wordcount.textContent = words === 1 ? "1 word" : `${words} words`;
}

async function init() {
  CONFIG = await (await fetch("/api/config")).json();

  const savedControls = store.get("controls", {});
  for (const c of CONFIG.controls) {
    values[c.id] = savedControls[c.id] !== undefined ? savedControls[c.id] : c.default;
  }
  const savedEnabled = store.get("enabled", {});
  for (const p of CONFIG.panels) {
    enabled[p.id] = savedEnabled[p.id] !== undefined ? savedEnabled[p.id] : p.default_on;
  }

  buildPanels();
  buildControls();

  els.transcript.value = store.get("transcript", "");
  updateWordCount();

  els.transcript.addEventListener("input", () => {
    store.set("transcript", els.transcript.value);
    updateWordCount();
    schedule();
  });

  els.run.addEventListener("click", () => run(true));
  els.clear.addEventListener("click", () => {
    els.transcript.value = "";
    store.set("transcript", "");
    updateWordCount();
    lastRunKey = null;
    if (inFlight) inFlight.abort();
    for (const p of CONFIG.panels) clearPanel(p.id, "waiting for transcript");
    setStatus("idle");
    els.transcript.focus();
  });

  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      run(true);
    }
  });

  els.transcript.focus();
  if (els.transcript.value.trim().length >= CONFIG.min_chars) setStatus("idle");
}

init();

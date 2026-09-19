// The floating input: the whole omni-all UI. Talks to the agent sidecar
// over HTTP and tells the shell when the run holds the mouse.
const { invoke } = window.__TAURI__.core;
const win = window.__TAURI__.window.getCurrentWindow();
const { LogicalSize, LogicalPosition } = window.__TAURI__.dpi;

const AGENT = "http://127.0.0.1:8766";
const LLM = "http://127.0.0.1:8081";
const WIDTH = 560;
const $ = (id) => document.getElementById(id);
const card = $("card");
const command = $("command");
const control = $("control");
const stopBtn = $("stop");
const ACTIVE = ["running", "paused", "confirm"];

let state = "loading"; // loading | idle | running | paused | confirm | done | failed | stopped
let lastClicks = 0;
let driving = false;
let polling = null;

applyIcons();

// The window follows the card's height, keeping its bottom edge in place.
new ResizeObserver(async () => {
  const h = Math.ceil(card.getBoundingClientRect().height);
  const scale = await win.scaleFactor();
  const pos = (await win.outerPosition()).toLogical(scale);
  const old = (await win.innerSize()).toLogical(scale).height;
  if (Math.abs(old - h) < 1) return;
  await win.setPosition(new LogicalPosition(pos.x, pos.y + old - h));
  await win.setSize(new LogicalSize(WIDTH, h));
}).observe(card);

$("grip").addEventListener("mousedown", (e) => {
  if (e.button === 0) win.startDragging();
});
$("quit").addEventListener("click", () => win.close());

async function api(path, body) {
  const res = await fetch(AGENT + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.status);
  return data;
}

// Startup (and after changing the model): wait for llama-server and the
// agent (with OmniParser loaded).
async function waitReady() {
  setState("loading");
  for (;;) {
    let llm = false;
    let vision = "";
    try {
      llm = (await fetch(LLM + "/health")).ok;
    } catch {}
    try {
      vision = (await api("/health")).vision;
    } catch {}
    if (llm && vision === "ready") break;
    const missing = [!llm && "Qwen", vision !== "ready" && "OmniParser"].filter(Boolean).join(" e ");
    command.placeholder = vision.startsWith("erro") ? vision : `Carregando ${missing}...`;
    await new Promise((r) => setTimeout(r, 1000));
  }
  setState("idle");
  command.placeholder = "O que devo fazer no computador?";
  command.focus();
}

// One control button: send (idle) / pause (running) / resume (paused).
control.addEventListener("click", async () => {
  if (state === "running") return api("/pause", { reason: "button" }).then(render);
  if (state === "paused" || state === "confirm") return api("/resume", {}).then(render);
  const task = command.value.trim();
  if (!task) return;
  $("result").hidden = true;
  try {
    render(await api("/run", { task }));
    command.value = "";
    await invoke("release_focus");
    startPolling();
  } catch (e) {
    showResult("failed", String(e.message || e));
  }
});
command.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !ACTIVE.includes(state)) control.click();
});
stopBtn.addEventListener("click", () => api("/stop", {}).then(render));

$("result-close").addEventListener("click", () => ($("result").hidden = true));
$("copy").addEventListener("click", () => navigator.clipboard.writeText($("result-text").innerText));

function startPolling() {
  clearInterval(polling);
  polling = setInterval(async () => {
    try {
      render(await api("/status"));
    } catch {}
  }, 200);
}

function setState(s) {
  state = s;
  const active = ACTIVE.includes(s);
  control.disabled = s === "loading";
  control.className = "icon-btn" + (s === "running" ? " running" : active ? " paused" : "");
  const iconName = s === "running" ? "pause" : active ? "play" : "send";
  control.title = s === "running" ? "Pausar" : s === "confirm" ? "Aprovar e continuar" : active ? "Retomar" : "Enviar";
  setIcon(control, iconName);
  stopBtn.hidden = !active;
  command.disabled = s === "loading" || active;
  const drive = s === "running";
  if (drive !== driving) {
    driving = drive;
    invoke("set_driving", { on: drive });
  }
}

function render(st) {
  setState(st.state);
  if ((st.clicks || 0) > lastClicks) invoke("badge_click");
  lastClicks = st.clicks || 0;

  const status = $("status");
  const active = ACTIVE.includes(st.state);
  status.hidden = !active;
  if (active) {
    const paused = st.state !== "running";
    status.classList.toggle("paused", paused);
    const icon = $("status-icon");
    icon.className = paused ? "" : "spin";
    setIcon(icon, st.state === "confirm" ? "shield-alert" : paused ? "mouse-pointer" : "loader");
    $("status-title").textContent =
      st.state === "confirm"
        ? "Confirme antes de continuar"
        : st.state === "paused"
          ? st.pause_reason === "mouse" ? "Pausado: você assumiu o mouse" : "Pausado"
          : st.task;
    $("status-detail").textContent = st.state === "confirm" ? st.pause_reason : st.message;
    $("status-steps").textContent = st.steps ? `passo ${st.steps}` : "";
  } else {
    clearInterval(polling);
    lastClicks = 0;
    if (st.state !== "idle") showResult(st.state, st.state === "done" ? st.answer : st.message);
  }
}

function showResult(kind, text) {
  const badge = $("result-badge");
  badge.className = "badge " + kind;
  badge.textContent = { done: "Concluído", failed: "Falhou", stopped: "Parado" }[kind];
  $("result-text").innerHTML = renderMarkdown(text);
  $("result").hidden = false;
  $("status").hidden = true;
}

// ---------- voice (Whisper large-v3-turbo, local; shared with Omni Use) ----------
const mic = $("mic");
let recording = false;

mic.addEventListener("click", async () => {
  if (mic.disabled) return;
  try {
    if (!recording) {
      const status = await invoke("voice_status");
      if (!status.model_ready) {
        showResult("failed", "Modelo de voz não encontrado. Rode scripts\\download_whisper_model.bat.");
        return;
      }
      await invoke("voice_start");
      recording = true;
      mic.classList.add("recording");
      setIcon(mic, "square");
      mic.title = "Parar e transcrever";
      return;
    }
    recording = false;
    mic.classList.remove("recording");
    mic.disabled = true;
    mic.innerHTML = `<span class="spin">${icon("loader", 18)}</span>`;
    const text = await invoke("voice_stop");
    if (text) {
      command.value = (command.value ? command.value + " " : "") + text;
      command.focus();
    }
  } catch (err) {
    recording = false;
    mic.classList.remove("recording");
    showResult("failed", `Voz: ${err}`);
  }
  mic.disabled = false;
  setIcon(mic, "mic");
  mic.title = "Falar (Whisper local)";
});

// ---------- debug window (OmniParser's view of each step) ----------
$("debug").addEventListener("click", async () => {
  $("debug").classList.toggle("active", await invoke("toggle_debug"));
});

// ---------- settings: model + context ----------
const CTX_OPTIONS = [4096, 8192, 16384, 32768, 65536, 131072];

$("gear").addEventListener("click", async () => {
  const panel = $("settings");
  if (!panel.hidden) return (panel.hidden = true);
  const s = await invoke("get_llm_settings");
  const ctxs = CTX_OPTIONS.includes(s.ctx) ? CTX_OPTIONS : [...CTX_OPTIONS, s.ctx].sort((a, b) => a - b);
  $("settings-body").innerHTML = `
    <label class="field">Modelo (pasta models/)
      <select id="set-model">${s.models.map((m) => `<option value="${escapeHtml(m)}" ${m === s.model ? "selected" : ""}>${escapeHtml(m.replace(/\.gguf$/, ""))}</option>`).join("")}</select>
    </label>
    <label class="field">Contexto (tokens)
      <select id="set-ctx">${ctxs.map((c) => `<option value="${c}" ${c === s.ctx ? "selected" : ""}>${c.toLocaleString("pt-BR")}</option>`).join("")}</select>
    </label>
    <div class="muted" style="margin-bottom:8px">Visão (o modelo vê a screenshot): ${s.vision ? "ativa" : "desligada — falta o mmproj do modelo (scripts\\download_qwen9b_vision.bat)"}. Mais contexto usa mais memória de vídeo. Aplicar recarrega o modelo.</div>
    <button id="set-apply" class="text-btn" ${ACTIVE.includes(state) ? "disabled" : ""}>Aplicar e recarregar</button>`;
  panel.hidden = false;
  $("set-apply").addEventListener("click", async () => {
    panel.hidden = true;
    try {
      await invoke("apply_llm_settings", { model: $("set-model").value, ctx: Number($("set-ctx").value) });
    } catch (err) {
      showResult("failed", String(err));
    }
    waitReady();
  });
});
$("settings-close").addEventListener("click", () => ($("settings").hidden = true));

// The mouse guard paused the run: re-render now instead of on the next poll.
window.__TAURI__.event.listen("takeover", () => api("/status").then(render).catch(() => {}));

waitReady();

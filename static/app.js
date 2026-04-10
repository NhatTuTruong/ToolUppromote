const state = {
  logCursor: 0,
  pollTimer: null,
};

const settingKeys = [
  "APIFY_TOKEN",
  "UPPROMOTE_API_URL",
  "UPPROMOTE_BEARER_TOKEN",
  "UPPROMOTE_MAX_PAGES",
  "UPPROMOTE_PAGE_DELAY_MS",
  "UPPROMOTE_PER_PAGE",
  "APIFY_MAX_DOMAINS_PER_RUN",
];

function $(id) {
  return document.getElementById(id);
}

function switchTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === tabId);
  });
}

async function loadSettings() {
  const res = await fetch("/api/settings");
  const data = await res.json();
  settingKeys.forEach((k) => {
    if ($(k)) $(k).value = data[k] || "";
  });
}

async function saveSettings() {
  const payload = {};
  settingKeys.forEach((k) => {
    payload[k] = ($(k)?.value || "").trim();
  });
  const res = await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    alert("Failed to save settings");
    return;
  }
  alert("Settings saved");
}

function appendLogs(lines) {
  const box = $("logBox");
  lines.forEach((line) => {
    box.textContent += line + "\n";
  });
  box.scrollTop = box.scrollHeight;
}

async function pollStatus() {
  const [stRes, lgRes] = await Promise.all([
    fetch("/api/status"),
    fetch(`/api/logs?since=${state.logCursor}`),
  ]);
  const st = await stRes.json();
  const lg = await lgRes.json();

  $("statusChip").textContent = st.status || "Idle";
  $("progressInner").style.width = `${Math.max(0, Math.min(100, st.progress || 0))}%`;
  $("progressText").textContent = `${Math.round(st.progress || 0)}%`;
  $("pauseBtn").disabled = !st.running;
  $("stopBtn").disabled = !st.running;
  $("runBtn").disabled = st.running;
  $("pauseBtn").textContent = st.paused ? "Resume" : "Pause";

  if (lg.logs && lg.logs.length) appendLogs(lg.logs);
  state.logCursor = lg.total || state.logCursor;

  if (!st.running && state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
    await loadResults();
  }
}

async function runFilter() {
  const settings = {};
  settingKeys.forEach((k) => {
    settings[k] = ($(k)?.value || "").trim();
  });
  const filters = {
    start_page: $("startPage").value.trim(),
    end_page: $("endPage").value.trim(),
    min_commission: $("minCommission").value.trim(),
    min_cookie: $("minCookie").value.trim(),
    currency: $("currency").value.trim(),
    application_review: $("applicationReview").value.trim(),
    min_payout_rate: $("minPayoutRate").value.trim(),
    min_approval_rate: $("minApprovalRate").value.trim(),
  };
  const minTraffic = Number($("minTraffic").value || "9000");

  $("logBox").textContent = "";
  state.logCursor = 0;
  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings, filters, min_traffic: minTraffic }),
  });
  if (!res.ok) {
    const er = await res.json().catch(() => ({}));
    alert(er.error || "Failed to start");
    return;
  }
  if (!state.pollTimer) {
    state.pollTimer = setInterval(pollStatus, 500);
  }
  await pollStatus();
  switchTab("runTab");
}

async function togglePause() {
  await fetch("/api/pause", { method: "POST" });
  await pollStatus();
}

async function stopRun() {
  await fetch("/api/stop", { method: "POST" });
  await pollStatus();
}

async function loadResults() {
  const res = await fetch("/api/results");
  const data = await res.json();
  const list = $("resultFileList");
  list.innerHTML = "";
  (data.files || []).forEach((f) => {
    const row = document.createElement("div");
    row.className = "file-row";
    const dt = new Date((f.modified || 0) * 1000);
    row.innerHTML = `
      <a class="btn sm primary" href="/api/download/${encodeURIComponent(f.name)}">Download</a>
      <div>${f.name}</div>
      <div class="file-meta">${(f.size || 0).toLocaleString()} bytes</div>
      <div class="file-meta">${isNaN(dt.getTime()) ? "" : dt.toLocaleString()}</div>
    `;
    list.appendChild(row);
  });
}

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
  $("saveSettingsBtn").addEventListener("click", saveSettings);
  $("runBtn").addEventListener("click", runFilter);
  $("pauseBtn").addEventListener("click", togglePause);
  $("stopBtn").addEventListener("click", stopRun);
  $("refreshResultsBtn").addEventListener("click", loadResults);
}

async function init() {
  bindEvents();
  await loadSettings();
  await loadResults();
  await pollStatus();
}

init();

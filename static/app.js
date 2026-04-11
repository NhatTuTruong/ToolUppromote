const state = {
  logCursor: 0,
  pollTimer: null,
};

const settingKeys = [
  "APIFY_TOKEN",
  "APIFY_MAX_DOMAINS_PER_RUN",
  "UPPROMOTE_API_URL",
  "UPPROMOTE_BEARER_TOKEN",
  "UPPROMOTE_MAX_PAGES",
  "UPPROMOTE_PAGE_DELAY_MS",
  "UPPROMOTE_PER_PAGE",
  "GOAFFPRO_API_URL",
  "GOAFFPRO_BEARER_TOKEN",
  "GOAFFPRO_LIMIT",
  "GOAFFPRO_MAX_PAGES",
  "GOAFFPRO_PAGE_DELAY_MS",
];

/** Đồng bộ khi đổi tab — không gồm minTraffic (để hai tab không ghi đè ngưỡng traffic). */
const FILTER_SYNC_PAIRS = [
  ["startPage", "startPageGp"],
  ["endPage", "endPageGp"],
  ["minCommission", "minCommissionGp"],
  ["minCookie", "minCookieGp"],
  ["currency", "currencyGp"],
  ["applicationReview", "applicationReviewGp"],
];

function $(id) {
  return document.getElementById(id);
}

function syncFiltersToGoaffpro() {
  FILTER_SYNC_PAIRS.forEach(([a, b]) => {
    const ela = $(a);
    const elb = $(b);
    if (ela && elb) elb.value = ela.value;
  });
}

function syncFiltersToUppromote() {
  FILTER_SYNC_PAIRS.forEach(([a, b]) => {
    const ela = $(a);
    const elb = $(b);
    if (ela && elb) ela.value = elb.value;
  });
}

function switchTab(tabId, fromUser = false) {
  if (fromUser) {
    if (tabId === "runGoaffproTab") {
      syncFiltersToGoaffpro();
    } else if (tabId === "runUppromoteTab") {
      syncFiltersToUppromote();
    }
  }
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
    alert("Không lưu được cài đặt.");
    return;
  }
  alert("Đã lưu cài đặt.");
}

function appendLogs(lines) {
  const boxes = [logBox(), logBoxGp()].filter(Boolean);
  boxes.forEach((box) => {
    lines.forEach((line) => {
      box.textContent += line + "\n";
    });
    box.scrollTop = box.scrollHeight;
  });
}

function logBox() {
  return $("logBox");
}

function logBoxGp() {
  return $("logBoxGp");
}

function setProgress(pct) {
  const v = Math.max(0, Math.min(100, pct || 0));
  const inner = $("progressInner");
  const innerGp = $("progressInnerGp");
  const tx = $("progressText");
  const txGp = $("progressTextGp");
  if (inner) inner.style.width = `${v}%`;
  if (innerGp) innerGp.style.width = `${v}%`;
  if (tx) tx.textContent = `${Math.round(v)}%`;
  if (txGp) txGp.textContent = `${Math.round(v)}%`;
}

async function pollStatus() {
  const [stRes, lgRes] = await Promise.all([
    fetch("/api/status"),
    fetch(`/api/logs?since=${state.logCursor}`),
  ]);
  const st = await stRes.json();
  const lg = await lgRes.json();

  $("statusChip").textContent = st.status || "Rảnh";
  setProgress(st.progress || 0);

  const pauseBtns = [$("pauseBtn"), $("pauseBtnGp")].filter(Boolean);
  const stopBtns = [$("stopBtn"), $("stopBtnGp")].filter(Boolean);
  const runUp = $("runBtnUppromote");
  const runGp = $("runBtnGoaffpro");
  pauseBtns.forEach((b) => {
    b.disabled = !st.running;
  });
  stopBtns.forEach((b) => {
    b.disabled = !st.running;
  });
  pauseBtns.forEach((b) => {
    b.textContent = st.paused ? "Tiếp tục" : "Tạm dừng";
  });
  if (runUp) runUp.disabled = st.running;
  if (runGp) runGp.disabled = st.running;

  if (lg.logs && lg.logs.length) appendLogs(lg.logs);
  state.logCursor = lg.total || state.logCursor;

  if (!st.running && state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
    await loadResults();
  }
}

function collectFilters(source) {
  if (source === "goaffpro") {
    return {
      start_page: $("startPageGp").value.trim(),
      end_page: $("endPageGp").value.trim(),
      min_commission: $("minCommissionGp").value.trim(),
      min_cookie: $("minCookieGp").value.trim(),
      currency: $("currencyGp").value.trim(),
      application_review: $("applicationReviewGp").value.trim(),
    };
  }
  return {
    start_page: $("startPage").value.trim(),
    end_page: $("endPage").value.trim(),
    min_commission: $("minCommission").value.trim(),
    min_cookie: $("minCookie").value.trim(),
    currency: $("currency").value.trim(),
    application_review: $("applicationReview").value.trim(),
    min_payout_rate: $("minPayoutRate").value.trim(),
    min_approval_rate: $("minApprovalRate").value.trim(),
  };
}

function minTrafficFor(source) {
  const v = source === "goaffpro" ? $("minTrafficGp")?.value : $("minTraffic")?.value;
  return Number(v || "9000");
}

async function runFilter(source) {
  const settings = {};
  settingKeys.forEach((k) => {
    settings[k] = ($(k)?.value || "").trim();
  });
  const filters = collectFilters(source);
  const minTraffic = minTrafficFor(source);

  const boxes = [logBox(), logBoxGp()].filter(Boolean);
  boxes.forEach((box) => {
    box.textContent = "";
  });
  state.logCursor = 0;
  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ settings, filters, min_traffic: minTraffic, source }),
  });
  if (!res.ok) {
    const er = await res.json().catch(() => ({}));
    alert(er.error || "Không thể bắt đầu chạy.");
    return;
  }
  if (!state.pollTimer) {
    state.pollTimer = setInterval(pollStatus, 500);
  }
  await pollStatus();
  switchTab(source === "goaffpro" ? "runGoaffproTab" : "runUppromoteTab");
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
      <a class="btn sm primary" href="/api/download/${encodeURIComponent(f.name)}">Tải xuống</a>
      <div>${f.name}</div>
      <div class="file-meta">${(f.size || 0).toLocaleString("vi-VN")} byte</div>
      <div class="file-meta">${isNaN(dt.getTime()) ? "" : dt.toLocaleString("vi-VN")}</div>
    `;
    list.appendChild(row);
  });
}

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab, true));
  });
  $("saveSettingsBtn").addEventListener("click", saveSettings);
  $("runBtnUppromote").addEventListener("click", () => runFilter("uppromote"));
  $("runBtnGoaffpro").addEventListener("click", () => runFilter("goaffpro"));
  ["pauseBtn", "pauseBtnGp"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("click", togglePause);
  });
  ["stopBtn", "stopBtnGp"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("click", stopRun);
  });
  $("refreshResultsBtn").addEventListener("click", loadResults);
}

async function init() {
  bindEvents();
  await loadSettings();
  await loadResults();
  await pollStatus();
}

init();

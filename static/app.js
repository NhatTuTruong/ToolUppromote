const state = {
  logCursor: 0,
  pollTimer: null,
};

/** Poll nhanh hơn khi đang chạy; server phải threaded=True để /api/logs không bị chặn bởi worker. */
const POLL_MS = 120;

let pollStatusBusy = false;

/** Khớp với ô nhập trong templates/index.html — không gồm AFF_LICENSE_* (chỉnh trong .env, không có field trên web). */
const settingKeys = [
  "APIFY_TOKEN",
  "UPPROMOTE_API_URL",
  "UPPROMOTE_BEARER_TOKEN",
  "UPPROMOTE_PER_PAGE",
  "GOAFFPRO_API_URL",
  "GOAFFPRO_BEARER_TOKEN",
  "GOAFFPRO_LIMIT",
  "REFERSION_API_URL",
  "REFERSION_TOKEN",
];

function clampOffersPerPageField(id) {
  const el = $(id);
  if (!el) return;
  let n = parseInt(String(el.value ?? "").trim(), 10);
  if (Number.isNaN(n)) n = 50;
  n = Math.max(10, Math.min(50, Math.floor(n / 10) * 10));
  el.value = String(n);
}

/** Không .trim() — giữ nguyên JWT/Bearer (chỉ chuẩn hóa xuống dòng Windows). */
const SECRET_SETTING_KEYS = new Set([
  "APIFY_TOKEN",
  "UPPROMOTE_BEARER_TOKEN",
  "GOAFFPRO_BEARER_TOKEN",
  "REFERSION_TOKEN",
  "AFF_LICENSE_API_TOKEN",
]);

function settingValueForPayload(key) {
  const raw = $(key)?.value;
  if (raw == null) return "";
  if (SECRET_SETTING_KEYS.has(key)) {
    return String(raw).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  }
  return String(raw).trim();
}

/** Đồng bộ khi đổi tab — không gồm minTraffic (để hai tab không ghi đè ngưỡng traffic). */
const LS_END_PAGE = "aff_filter_end_page";

const FILTER_SYNC_PAIRS_GP = [
  ["startPage", "startPageGp"],
  ["endPage", "endPageGp"],
  ["minCommission", "minCommissionGp"],
  ["minCookie", "minCookieGp"],
  ["currency", "currencyGp"],
  ["applicationReview", "applicationReviewGp"],
];

const FILTER_SYNC_PAIRS_RF = [
  ["startPage", "startPageRf"],
  ["endPage", "endPageRf"],
  ["minCommission", "minCommissionRf"],
  ["minCookie", "minCookieRf"],
  ["currency", "currencyRf"],
];

function $(id) {
  return document.getElementById(id);
}

/** Ô Token Apify / URL / Bearer: mặc định đóng (type=password che ký tự); bấm mắt để sửa; lưu hoặc load lại → đóng. Giá trị .value không đổi khi đóng/mở. */
function setSecretFieldRowOpen(row, open) {
  if (!row) return;
  const id = row.getAttribute("data-secret-for");
  const input = id ? $(id) : null;
  if (!input) return;
  row.classList.toggle("is-open", open);
  input.type = open ? "text" : "password";
  const btn = row.querySelector(".secret-eye-btn");
  if (btn) {
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.setAttribute("aria-label", open ? "Ẩn (đóng ô nhập)" : "Hiện để chỉnh sửa");
  }
  if (open) input.focus();
}

function closeAllSecretFieldRows() {
  document.querySelectorAll(".secret-field-row").forEach((row) => setSecretFieldRowOpen(row, false));
}

function bindSecretEyeButtons() {
  document.querySelectorAll(".secret-field-row").forEach((row) => {
    const btn = row.querySelector(".secret-eye-btn");
    if (!btn) return;
    btn.addEventListener("click", (e) => {
      e.preventDefault();
      const open = !row.classList.contains("is-open");
      setSecretFieldRowOpen(row, open);
    });
  });
}

function syncFiltersToGoaffpro() {
  FILTER_SYNC_PAIRS_GP.forEach(([a, b]) => {
    const ela = $(a);
    const elb = $(b);
    if (ela && elb) elb.value = ela.value;
  });
}

function syncFiltersToRefersion() {
  FILTER_SYNC_PAIRS_RF.forEach(([a, b]) => {
    const ela = $(a);
    const elb = $(b);
    if (ela && elb) elb.value = ela.value;
  });
}

function syncFiltersToUppromote() {
  FILTER_SYNC_PAIRS_GP.forEach(([a, b]) => {
    const ela = $(a);
    const elb = $(b);
    if (ela && elb) ela.value = elb.value;
  });
  FILTER_SYNC_PAIRS_RF.forEach(([a, b]) => {
    const ela = $(a);
    const elb = $(b);
    if (ela && elb) ela.value = elb.value;
  });
}

function loadPersistedEndPage() {
  const raw = localStorage.getItem(LS_END_PAGE);
  let v;
  if (raw === null) v = "1";
  else if (String(raw).trim() === "") v = "";
  else {
    const t = String(raw).trim();
    v = /^\d+$/.test(t) && parseInt(t, 10) >= 1 ? t : "1";
  }
  if ($("endPage")) $("endPage").value = v;
  if ($("endPageGp")) $("endPageGp").value = v;
  if ($("endPageRf")) $("endPageRf").value = v;
}

function mirrorEndPageOther(fromUppromote) {
  const src = fromUppromote ? $("endPage") : $("endPageGp");
  const dstA = fromUppromote ? $("endPageGp") : $("endPage");
  const dstB = $("endPageRf");
  if (src && dstA) dstA.value = src.value;
  if (src && dstB) dstB.value = src.value;
}

function persistEndPageBoth() {
  const a = ($("endPage")?.value ?? "").trim();
  const b = ($("endPageGp")?.value ?? "").trim();
  const c = ($("endPageRf")?.value ?? "").trim();
  let v = a || b || c;
  if (v !== "" && (!/^\d+$/.test(v) || parseInt(v, 10) < 1)) v = "1";
  if ($("endPage")) $("endPage").value = v;
  if ($("endPageGp")) $("endPageGp").value = v;
  if ($("endPageRf")) $("endPageRf").value = v;
  localStorage.setItem(LS_END_PAGE, v);
}

function switchTab(tabId, fromUser = false) {
  if (fromUser) {
    if (tabId === "runGoaffproTab") {
      syncFiltersToGoaffpro();
    } else if (tabId === "runRefersionTab") {
      syncFiltersToRefersion();
    } else if (tabId === "runUppromoteTab") {
      syncFiltersToUppromote();
    }
    persistEndPageBoth();
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
  closeAllSecretFieldRows();
}

async function saveSettings() {
  clampOffersPerPageField("UPPROMOTE_PER_PAGE");
  clampOffersPerPageField("GOAFFPRO_LIMIT");
  const payload = {};
  settingKeys.forEach((k) => {
    if (!$(k)) return;
    payload[k] = settingValueForPayload(k);
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
  closeAllSecretFieldRows();
  alert("Đã lưu cài đặt.");
}

/** Ghi log vào DOM rồi chờ khung vẽ (double rAF) trước khi gửi ack — khớp thứ tự với worker. */
async function appendLogs(lines) {
  const boxes = [logBox(), logBoxGp(), logBoxRf()].filter(Boolean);
  if (!lines || !lines.length) return;
  await new Promise((resolve) => {
    requestAnimationFrame(() => {
      boxes.forEach((box) => {
        lines.forEach((line) => {
          box.appendChild(document.createTextNode(`${String(line)}\n`));
        });
        box.scrollTop = box.scrollHeight;
      });
      requestAnimationFrame(() => resolve());
    });
  });
}

function logBox() {
  return $("logBox");
}

function logBoxGp() {
  return $("logBoxGp");
}

function logBoxRf() {
  return $("logBoxRf");
}

function setProgress(pct) {
  const v = Math.max(0, Math.min(100, pct || 0));
  const inner = $("progressInner");
  const innerGp = $("progressInnerGp");
  const innerRf = $("progressInnerRf");
  const tx = $("progressText");
  const txGp = $("progressTextGp");
  const txRf = $("progressTextRf");
  if (inner) inner.style.width = `${v}%`;
  if (innerGp) innerGp.style.width = `${v}%`;
  if (innerRf) innerRf.style.width = `${v}%`;
  if (tx) tx.textContent = `${Math.round(v)}%`;
  if (txGp) txGp.textContent = `${Math.round(v)}%`;
  if (txRf) txRf.textContent = `${Math.round(v)}%`;
}

async function pollStatus() {
  if (pollStatusBusy) return;
  pollStatusBusy = true;
  try {
    const [stRes, lgRes] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch(`/api/logs?since=${state.logCursor}`, { cache: "no-store" }),
    ]);
    const st = await stRes.json();
    const lg = await lgRes.json();

    $("statusChip").textContent = st.status || "Sảnh";
    setProgress(st.progress || 0);

    const pauseBtns = [$("pauseBtn"), $("pauseBtnGp"), $("pauseBtnRf")].filter(Boolean);
    const stopBtns = [$("stopBtn"), $("stopBtnGp"), $("stopBtnRf")].filter(Boolean);
    const runUp = $("runBtnUppromote");
    const runGp = $("runBtnGoaffpro");
    const runRf = $("runBtnRefersion");
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
    if (runRf) runRf.disabled = st.running;

    if (lg.logs && lg.logs.length) {
      await appendLogs(lg.logs);
    }
    if (typeof lg.total === "number") {
      state.logCursor = lg.total;
      try {
        await fetch("/api/logs/ack", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ seen_total: lg.total }),
          cache: "no-store",
        });
      } catch (_) {
        /* ignore */
      }
    }

    if (!st.running && state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      await loadResults();
      await loadLicense();
    }
  } finally {
    pollStatusBusy = false;
  }
}

function collectCheckedValues(groupSelector) {
  const root = document.querySelector(groupSelector);
  if (!root) return [];
  return Array.from(root.querySelectorAll('input[type="checkbox"]:checked')).map((c) => c.value);
}

let multiSelectDocListenersBound = false;

function bindMultiSelectDropdowns() {
  document.querySelectorAll(".multi-select").forEach((root) => {
    const btn = root.querySelector(".multi-select-btn");
    const textEl = root.querySelector(".multi-select-btn-text");
    const panel = root.querySelector(".multi-select-panel");
    if (!btn || !textEl || !panel) return;

    function updateSummary() {
      const checked = panel.querySelectorAll('input[type="checkbox"]:checked');
      const n = checked.length;
      textEl.classList.toggle("muted-hint", n === 0);
      if (n === 0) {
        textEl.textContent = "Tất cả";
        return;
      }
      if (n === 1) {
        const opt = checked[0].closest(".multi-select-option");
        const span = opt && opt.querySelector("span");
        textEl.textContent = span ? span.textContent.trim() : String(checked[0].value || "");
        return;
      }
      textEl.textContent = `Đã chọn ${n} mục`;
    }

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      const wasOpen = root.classList.contains("is-open");
      document.querySelectorAll(".multi-select.is-open").forEach((o) => {
        o.classList.remove("is-open");
        const b = o.querySelector(".multi-select-btn");
        if (b) b.setAttribute("aria-expanded", "false");
      });
      if (!wasOpen) {
        root.classList.add("is-open");
        btn.setAttribute("aria-expanded", "true");
      }
    });

    panel.addEventListener("change", () => updateSummary());
    updateSummary();
  });

  if (!multiSelectDocListenersBound) {
    multiSelectDocListenersBound = true;
    document.addEventListener("click", (e) => {
      document.querySelectorAll(".multi-select.is-open").forEach((root) => {
        if (root.contains(e.target)) return;
        root.classList.remove("is-open");
        const b = root.querySelector(".multi-select-btn");
        if (b) b.setAttribute("aria-expanded", "false");
      });
    });
    document.addEventListener("keydown", (e) => {
      if (e.key !== "Escape") return;
      document.querySelectorAll(".multi-select.is-open").forEach((root) => {
        root.classList.remove("is-open");
        const b = root.querySelector(".multi-select-btn");
        if (b) b.setAttribute("aria-expanded", "false");
      });
    });
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
  if (source === "refersion") {
    return {
      start_page: $("startPageRf").value.trim(),
      end_page: $("endPageRf").value.trim(),
      min_commission: $("minCommissionRf").value.trim(),
      min_cookie: $("minCookieRf").value.trim(),
      currency: $("currencyRf").value.trim(),
      application_review: "",
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
    categories: collectCheckedValues("#categoryUppromoteGroup"),
    payment_methods: collectCheckedValues("#paymentMethodUppromoteGroup"),
  };
}

function minTrafficFor(source) {
  const v =
    source === "goaffpro"
      ? $("minTrafficGp")?.value
      : source === "refersion"
        ? $("minTrafficRf")?.value
        : $("minTraffic")?.value;
  return Number(v || "9000");
}

async function runFilter(source) {
  clampOffersPerPageField("UPPROMOTE_PER_PAGE");
  clampOffersPerPageField("GOAFFPRO_LIMIT");
  const settings = {};
  settingKeys.forEach((k) => {
    settings[k] = settingValueForPayload(k);
  });
  const filters = collectFilters(source);
  const minTraffic = minTrafficFor(source);

  const boxes = [logBox(), logBoxGp(), logBoxRf()].filter(Boolean);
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
  persistEndPageBoth();
  if (!state.pollTimer) {
    state.pollTimer = setInterval(pollStatus, POLL_MS);
  }
  await pollStatus();
  switchTab(source === "goaffpro" ? "runGoaffproTab" : source === "refersion" ? "runRefersionTab" : "runUppromoteTab");
}

async function togglePause() {
  await fetch("/api/pause", { method: "POST" });
  await pollStatus();
}

async function stopRun() {
  await fetch("/api/stop", { method: "POST" });
  await pollStatus();
}

async function downloadResultFile(name) {
  const origin = window.location.origin || "";
  const url = `${origin}/api/download/${encodeURIComponent(name)}`;

  /** Bản .exe (pywebview): hộp thoại Lưu thành… — luôn hoạt động dù WebView chặn download. */
  const pv = window.pywebview?.api;
  if (pv && typeof pv.save_result_xlsx === "function") {
    try {
      const r = await pv.save_result_xlsx(name);
      if (r && r.ok) return;
      if (r && r.error === "cancelled") return;
      if (r && !r.ok) {
        alert(r.error || "Không lưu được file.");
        return;
      }
    } catch (e) {
      alert(String(e?.message || e || "Lỗi khi lưu file."));
      return;
    }
  }

  try {
    const head = await fetch(url, { method: "HEAD", cache: "no-store" });
    if (!head.ok) {
      const r = await fetch(url, { method: "GET", cache: "no-store" });
      const ct = (r.headers.get("content-type") || "").toLowerCase();
      if (ct.includes("application/json")) {
        const j = await r.json().catch(() => ({}));
        alert(j.error || "Không tải được file.");
        return;
      }
      alert("Không tải được file.");
      return;
    }
  } catch (_) {
    /* HEAD lỗi — vẫn thử kích hoạt tải */
  }

  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-downloads allow-same-origin");
  iframe.style.cssText =
    "position:fixed;width:0;height:0;border:none;opacity:0;pointer-events:none;left:-9999px";
  iframe.src = url;
  document.body.appendChild(iframe);
  window.setTimeout(() => {
    try {
      iframe.remove();
    } catch (_) {
      /* ignore */
    }
  }, 300000);

  window.setTimeout(() => {
    const a = document.createElement("a");
    a.href = url;
    a.setAttribute("download", name);
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, 200);
}

async function deleteResultFile(name) {
  if (!confirm(`Xóa file "${name}"?`)) return;
  const res = await fetch("/api/results/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Không xóa được file.");
    return;
  }
  await loadResults();
}

function renderLicenseStatus(lic) {
  const msg = $("licenseMessage");
  const mid = $("machineIdBox");
  if (msg) msg.textContent = lic.message || "";
  if (mid) mid.textContent = lic.machine_id || "—";
  const deBtn = $("deactivateLicenseBtn");
  if (deBtn) deBtn.disabled = !lic.licensed;
}

async function loadLicense() {
  try {
    const res = await fetch("/api/license", { cache: "no-store" });
    const lic = await res.json();
    renderLicenseStatus(lic);
    return lic;
  } catch (_) {
    const msg = $("licenseMessage");
    if (msg) msg.textContent = "Không đọc được trạng thái bản quyền.";
  }
  return null;
}

async function activateLicense() {
  const raw = ($("licenseKeyInput")?.value || "").trim();
  if (!raw) {
    alert("Nhập key.");
    return;
  }
  const res = await fetch("/api/license/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key: raw }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Kích hoạt thất bại.");
    return;
  }
  if (data.license) renderLicenseStatus(data.license);
  else await loadLicense();
  if ($("licenseKeyInput")) $("licenseKeyInput").value = "";
  alert(data.message || "Đã kích hoạt.");
}

async function deactivateLicense() {
  if (!confirm("Hủy kích hoạt trên máy này? Bạn sẽ về chế độ dùng thử (10 record Uppromote + 10 Goaffpro trọn đời trên máy, không reset) và giải phóng 1 slot máy trên key.")) {
    return;
  }
  const res = await fetch("/api/license/deactivate", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Không hủy được kích hoạt.");
    return;
  }
  if (data.license) renderLicenseStatus(data.license);
  else await loadLicense();
  alert(data.message || "Đã hủy kích hoạt.");
}

async function loadResults() {
  const res = await fetch("/api/results");
  const data = await res.json();
  const list = $("resultFileList");
  list.innerHTML = "";
  (data.files || []).forEach((f) => {
    const row = document.createElement("div");
    row.className = "file-row";
    const actions = document.createElement("div");
    actions.className = "file-actions";
    const btnDl = document.createElement("button");
    btnDl.type = "button";
    btnDl.className = "btn sm primary";
    btnDl.textContent = "Tải xuống";
    btnDl.addEventListener("click", () => downloadResultFile(f.name));
    const btnDel = document.createElement("button");
    btnDel.type = "button";
    btnDel.className = "btn sm danger";
    btnDel.textContent = "Xóa";
    btnDel.addEventListener("click", () => deleteResultFile(f.name));
    actions.appendChild(btnDl);
    actions.appendChild(btnDel);
    const nameEl = document.createElement("div");
    nameEl.textContent = f.name;
    const sizeEl = document.createElement("div");
    sizeEl.className = "file-meta";
    sizeEl.textContent = `${(f.size || 0).toLocaleString("vi-VN")} byte`;
    const dt = new Date((f.modified || 0) * 1000);
    const timeEl = document.createElement("div");
    timeEl.className = "file-meta";
    timeEl.textContent = isNaN(dt.getTime()) ? "" : dt.toLocaleString("vi-VN");
    row.appendChild(actions);
    row.appendChild(nameEl);
    row.appendChild(sizeEl);
    row.appendChild(timeEl);
    list.appendChild(row);
  });
}

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab, true));
  });
  bindMultiSelectDropdowns();
  bindSecretEyeButtons();
  $("saveSettingsBtn").addEventListener("click", saveSettings);
  $("runBtnUppromote").addEventListener("click", () => runFilter("uppromote"));
  $("runBtnGoaffpro").addEventListener("click", () => runFilter("goaffpro"));
  $("runBtnRefersion").addEventListener("click", () => runFilter("refersion"));
  ["pauseBtn", "pauseBtnGp", "pauseBtnRf"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("click", togglePause);
  });
  ["stopBtn", "stopBtnGp", "stopBtnRf"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("click", stopRun);
  });
  $("refreshResultsBtn").addEventListener("click", loadResults);
  const actLic = $("activateLicenseBtn");
  if (actLic) actLic.addEventListener("click", activateLicense);
  const deLic = $("deactivateLicenseBtn");
  if (deLic) deLic.addEventListener("click", deactivateLicense);
  const ep = $("endPage");
  const egp = $("endPageGp");
  const erf = $("endPageRf");
  if (ep) {
    ep.addEventListener("input", () => mirrorEndPageOther(true));
    ep.addEventListener("change", persistEndPageBoth);
  }
  if (egp) {
    egp.addEventListener("input", () => mirrorEndPageOther(false));
    egp.addEventListener("change", persistEndPageBoth);
  }
  if (erf) {
    erf.addEventListener("input", persistEndPageBoth);
    erf.addEventListener("change", persistEndPageBoth);
  }
}

async function init() {
  bindEvents();
  loadPersistedEndPage();
  await loadSettings();
  await loadLicense();
  await loadResults();
  await pollStatus();
}

init();

const state = {
  logCursor: 0,
  pollTimer: null,
  currentLicense: null,
  autoApply: {
    lastRunning: false,
    lastFile: "",
    lastResultSig: "",
    runToken: "",
    notifiedToken: "",
  },
};

function isAutoApplyCollabsEnabled() {
  try {
    const v = document.body?.dataset?.autoApplyCollabsEnabled;
    if (v == null || String(v).trim() === "") return true;
    return String(v).trim() === "1";
  } catch (_) {
    return true;
  }
}

const AUTO_APPLY_DEFAULTS = {
  aa_business_type: "Content Creator",
  aa_brands_worked: "Shopify DTC brands in beauty, wellness, home, and lifestyle.",
  aa_successful_partnership:
    "A successful partnership combines clear KPIs, fast communication, and consistent creative execution. I usually deliver 2-4 high-quality assets per campaign and optimize hooks/CTA based on performance.",
  aa_content_inspires:
    "Authentic product storytelling, clear problem-solution demos, before-after proof, and conversion-focused UGC with strong hooks.",
  aa_hope_gain:
    "A long-term partnership with clear performance goals, exclusive offers for my audience, and scalable monthly campaigns.",
  aa_how_found:
    "I found your brand through creator community recommendations and your product content on social media.",
  aa_city_country: "United States",
  aa_demographic:
    "Women and men aged 18-34 in US/UK/CA interested in lifestyle, beauty, home, wellness, and online shopping.",
  aa_growth_strategy:
    "I post consistently, test new hooks weekly, improve retention with tighter edits, and scale winning formats using data from saves, shares, and watch time.",
  aa_children_age: "N/A",
  aa_ugc_content: "Yes. I create UGC videos, product photography, and ad-style creatives for paid and organic use.",
  aa_content_ideas:
    "UGC review, unboxing, problem-solution demo, before-after comparison, and a creator recommendation video with clear CTA.",
  aa_followers_engagement:
    "I have a growing audience across Instagram and TikTok, and my posts typically receive consistent engagement through comments, saves, and shares. I focus on quality audience fit and conversion intent.",
  aa_why_fit:
    "My audience matches your target customer profile, and my content style is built to drive trust, clicks, and conversions while keeping the brand voice authentic.",
  aa_purchase_love:
    "I really like your product quality, practical value, and thoughtful design. It is easy to present naturally in daily-use content and gives strong social proof opportunities.",
  aa_why_join:
    "I want to join your program to build a long-term, performance-focused partnership. I can deliver authentic content consistently, communicate quickly, and optimize each campaign for better conversion.",
  aa_generic_short:
    "I would love to collaborate and create high-converting, authentic content for your brand.",
  aa_generic_long:
    "I create authentic, conversion-focused content that builds trust and helps audiences take action. I can provide consistent deliverables, fast communication, and data-informed optimization to improve campaign performance over time.",
  aa_message: "",
  aa_dob: "",
  aa_shipping_location: "United States",
  aa_identify: "Prefer not to say",
  aa_apply_mode: "only_dat",
  aa_purchase_before_choice: "Yes",
  aa_row_start: "1",
  aa_row_end: "",
};
const LS_AUTO_APPLY_HISTORY = "aff_auto_apply_history_v1";

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
  "COLLABS_API_URL",
  "COLLABS_COOKIE",
  "COLLABS_CSRF_TOKEN",
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
  "COLLABS_COOKIE",
  "COLLABS_CSRF_TOKEN",
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

function mirrorEndPageFromRefersion() {
  const src = $("endPageRf");
  const dstA = $("endPage");
  const dstB = $("endPageGp");
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

const TAB_SOURCE_MAP = {
  runUppromoteTab: "uppromote",
  runGoaffproTab: "goaffpro",
  runRefersionTab: "refersion",
  runCollabsTab: "collabs",
};

function normalizeAllowedSourcesFromLicense(lic) {
  const all = ["uppromote", "goaffpro", "refersion", "collabs"];
  if (!lic || !lic.licensed) return all;
  const incoming = Array.isArray(lic.allowed_sources) ? lic.allowed_sources : [];
  const normalized = Array.from(
    new Set(
      incoming
        .map((v) => String(v || "").trim().toLowerCase())
        .filter((s) => all.includes(s))
    )
  );
  return normalized.length ? normalized : ["uppromote", "goaffpro"];
}

function applyLicenseSourceVisibility(lic) {
  const allowed = new Set(normalizeAllowedSourcesFromLicense(lic));
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    const source = TAB_SOURCE_MAP[btn.dataset.tab || ""];
    if (!source) return;
    const visible = allowed.has(source);
    btn.style.display = visible ? "" : "none";
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const source = TAB_SOURCE_MAP[panel.id || ""];
    if (!source) return;
    panel.style.display = allowed.has(source) ? "" : "none";
  });
  document.querySelectorAll("[data-settings-source]").forEach((el) => {
    const source = String(el.getAttribute("data-settings-source") || "").trim().toLowerCase();
    if (!source) return;
    el.style.display = allowed.has(source) ? "" : "none";
  });
  const activeBtn = document.querySelector(".tab-btn.active");
  const activeTab = activeBtn ? activeBtn.dataset.tab : null;
  if (activeTab && TAB_SOURCE_MAP[activeTab] && !allowed.has(TAB_SOURCE_MAP[activeTab])) {
    const fallback = document.querySelector('.tab-btn[data-tab="settingsTab"]');
    if (fallback) switchTab("settingsTab");
  }
}

function finishLicenseLoadingState() {
  document.body.classList.remove("license-loading");
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
  const boxes = [logBox(), logBoxGp(), logBoxRf(), logBoxCb()].filter(Boolean);
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

function logBoxCb() {
  return $("logBoxCb");
}

function setProgress(pct) {
  const v = Math.max(0, Math.min(100, pct || 0));
  const inner = $("progressInner");
  const innerGp = $("progressInnerGp");
  const innerRf = $("progressInnerRf");
  const innerCb = $("progressInnerCb");
  const tx = $("progressText");
  const txGp = $("progressTextGp");
  const txRf = $("progressTextRf");
  const txCb = $("progressTextCb");
  if (inner) inner.style.width = `${v}%`;
  if (innerGp) innerGp.style.width = `${v}%`;
  if (innerRf) innerRf.style.width = `${v}%`;
  if (innerCb) innerCb.style.width = `${v}%`;
  if (tx) tx.textContent = `${Math.round(v)}%`;
  if (txGp) txGp.textContent = `${Math.round(v)}%`;
  if (txRf) txRf.textContent = `${Math.round(v)}%`;
  if (txCb) txCb.textContent = `${Math.round(v)}%`;
}

async function pollStatus() {
  if (pollStatusBusy) return;
  pollStatusBusy = true;
  try {
    const aaReq = isAutoApplyCollabsEnabled() ? fetchAutoApplyStatus().catch(() => ({})) : Promise.resolve({});
    const [stRes, lgRes, aa] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch(`/api/logs?since=${state.logCursor}`, { cache: "no-store" }),
      aaReq,
    ]);
    const st = await stRes.json();
    const lg = await lgRes.json();

    $("statusChip").textContent = st.status || "Sảnh";
    setProgress(st.progress || 0);

    const pauseBtns = [$("pauseBtn"), $("pauseBtnGp"), $("pauseBtnRf"), $("pauseBtnCb")].filter(Boolean);
    const stopBtns = [$("stopBtn"), $("stopBtnGp"), $("stopBtnRf"), $("stopBtnCb")].filter(Boolean);
    const runUp = $("runBtnUppromote");
    const runGp = $("runBtnGoaffpro");
    const runRf = $("runBtnRefersion");
    const runCb = $("runBtnCollabs");
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
    if (runCb) runCb.disabled = st.running;

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

    if (isAutoApplyCollabsEnabled()) {
      // Popup thông báo khi Auto Apply chạy nền hoàn tất / lỗi.
      const aaRunning = !!aa?.running;
      const aaFile = String(aa?.file || "");
      const aaStatus = String(aa?.status || "");
      const r = aa?.result || null;
      const err = String(aa?.error || "");
      const sig = JSON.stringify({ aaFile, aaStatus, r, err });
      state.autoApply.lastRunning = aaRunning;
      state.autoApply.lastFile = aaFile;
      const finished = !aaRunning && (aaStatus === "Done" || aaStatus === "Error" || !!r || !!err);
      const hasRunToken = !!state.autoApply.runToken;
      const shouldNotifyByToken = hasRunToken && state.autoApply.notifiedToken !== state.autoApply.runToken;
      const shouldNotifyBySig = !hasRunToken && state.autoApply.lastResultSig !== sig;
      if (finished && (shouldNotifyByToken || shouldNotifyBySig)) {
        state.autoApply.lastResultSig = sig;
        if (hasRunToken) state.autoApply.notifiedToken = state.autoApply.runToken;
        if (r && typeof r === "object") {
          appendLocalApplyHistory({
            file: aaFile,
            started_at_display: new Date().toLocaleString("vi-VN"),
            email: "",
            submitted_items: Array.isArray(r.submitted_items) ? r.submitted_items : [],
          });
          alert(
            `Auto Apply xong.\nFile: ${aaFile}\nTổng link: ${r.total || 0}\nĐã điền form: ${r.filled || 0}\nĐã submit: ${r.submitted || 0}`
          );
        } else if (err) {
          alert(`Auto Apply dừng/lỗi.\nFile: ${aaFile}\nLỗi: ${err}`);
        } else {
          alert(`Auto Apply đã dừng.\nFile: ${aaFile}`);
        }
        // refresh lại list để nút Hủy -> Auto Apply
        await loadResults();
      }
    }

    // Chỉ dừng polling khi cả pipeline và auto-apply (nếu bật) đều đã dừng.
    const aaRunningForStop = isAutoApplyCollabsEnabled() ? !!aa?.running : false;
    if (!st.running && !aaRunningForStop && state.pollTimer) {
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

function setCheckedValues(groupSelector, values) {
  const root = document.querySelector(groupSelector);
  if (!root) return;
  const set = new Set((values || []).map((v) => String(v || "").trim()).filter(Boolean));
  root.querySelectorAll('input[type="checkbox"]').forEach((c) => {
    c.checked = set.has(String(c.value || "").trim());
  });
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
        // Nếu đây là dropdown Identify trong Auto Apply, mặc định là "Prefer not to say"
        const label = String(root.getAttribute("data-multi-label") || "").toLowerCase();
        textEl.textContent = label.includes("identify") ? "Prefer not to say" : "Tất cả";
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
  if (source === "collabs") {
    return {
      start_page: $("startPageCb").value.trim(),
      end_page: $("endPageCb").value.trim(),
      min_commission: $("minCommissionCb").value.trim(),
      min_cookie: "",
      currency: "",
      application_review: "",
      categories: collectCheckedValues("#categoryCollabsGroup"),
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
        : source === "collabs"
          ? $("minTrafficCb")?.value
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

  const boxes = [logBox(), logBoxGp(), logBoxRf(), logBoxCb()].filter(Boolean);
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
  switchTab(
    source === "goaffpro"
      ? "runGoaffproTab"
      : source === "refersion"
        ? "runRefersionTab"
        : source === "collabs"
          ? "runCollabsTab"
          : "runUppromoteTab"
  );
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

async function openEdgeForAutoApply() {
  try {
    const res = await fetch("/api/edge-cdp/start", { method: "POST" });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      const detail = Array.isArray(data.logs) && data.logs.length ? `\n\nLog:\n${data.logs.join("\n")}` : "";
      alert((data.error || "Không mở được Edge CDP.") + detail);
      return;
    }
    const detail = Array.isArray(data.logs) && data.logs.length ? `\n\nLog:\n${data.logs.join("\n")}` : "";
    alert(`Edge đã sẵn sàng cho Auto Apply.\nCDP: ${data.cdp_url || "http://127.0.0.1:9222"}` + detail);
  } catch (e) {
    alert(String(e?.message || e || "Lỗi mở Edge CDP."));
  }
}

function collectAutoApplyProfile() {
  const keep = (k, v) => localStorage.setItem(k, v || "");
  const read = (k) => {
    const fromLs = localStorage.getItem(k);
    if (fromLs != null && String(fromLs).trim() !== "") return fromLs;
    return AUTO_APPLY_DEFAULTS[k] || "";
  };
  const modal = $("autoApplyModal");
  const fullNameEl = $("aa_full_name");
  const emailEl = $("aa_email");
  const phoneEl = $("aa_phone");
  const websiteEl = $("aa_website");
  const instagramEl = $("aa_instagram");
  const tiktokEl = $("aa_tiktok");
  const youtubeEl = $("aa_youtube");
  const businessTypeEl = $("aa_business_type");
  const dobEl = $("aa_dob");
  const shipEl = $("aa_shipping_location");
  const applyModeEl = $("aa_apply_mode");
  const purchaseBeforeChoiceEl = $("aa_purchase_before_choice");
  const rowStartEl = $("aa_row_start");
  const rowEndEl = $("aa_row_end");
  const brandsWorkedEl = $("aa_brands_worked");
  const successPartnerEl = $("aa_successful_partnership");
  const contentInspiresEl = $("aa_content_inspires");
  const hopeGainEl = $("aa_hope_gain");
  const howFoundEl = $("aa_how_found");
  const cityCountryEl = $("aa_city_country");
  const demographicEl = $("aa_demographic");
  const growthStrategyEl = $("aa_growth_strategy");
  const contentIdeasEl = $("aa_content_ideas");
  const followersEngagementEl = $("aa_followers_engagement");
  const whyFitEl = $("aa_why_fit");
  const purchaseLoveEl = $("aa_purchase_love");
  const whyJoinEl = $("aa_why_join");
  const genericShortEl = $("aa_generic_short");
  const genericLongEl = $("aa_generic_long");
  const messageEl = $("aa_message");
  const btnCancel = $("aa_cancel_btn");
  const btnSave = $("aa_save_btn");
  const btnConfirm = $("aa_confirm_btn");
  if (
    !modal ||
    !fullNameEl ||
    !emailEl ||
    !phoneEl ||
    !websiteEl ||
    !instagramEl ||
    !tiktokEl ||
    !youtubeEl ||
    !businessTypeEl ||
    !dobEl ||
    !shipEl ||
    !applyModeEl ||
    !purchaseBeforeChoiceEl ||
    !rowStartEl ||
    !rowEndEl ||
    !brandsWorkedEl ||
    !successPartnerEl ||
    !contentInspiresEl ||
    !hopeGainEl ||
    !howFoundEl ||
    !cityCountryEl ||
    !demographicEl ||
    !growthStrategyEl ||
    !contentIdeasEl ||
    !followersEngagementEl ||
    !whyFitEl ||
    !purchaseLoveEl ||
    !whyJoinEl ||
    !genericShortEl ||
    !genericLongEl ||
    !messageEl ||
    !btnCancel ||
    !btnSave ||
    !btnConfirm
  ) {
    alert("Thiếu popup Auto Apply trong giao diện.");
    return Promise.resolve(null);
  }

  fullNameEl.value = read("aa_full_name");
  emailEl.value = read("aa_email");
  phoneEl.value = read("aa_phone");
  websiteEl.value = read("aa_website");
  instagramEl.value = read("aa_instagram");
  tiktokEl.value = read("aa_tiktok");
  youtubeEl.value = read("aa_youtube");
  businessTypeEl.value = read("aa_business_type");
  dobEl.value = read("aa_dob");
  shipEl.value = read("aa_shipping_location") || "United States";
  applyModeEl.value = read("aa_apply_mode") || "only_dat";
  purchaseBeforeChoiceEl.value = read("aa_purchase_before_choice") || "Yes";
  rowStartEl.value = read("aa_row_start") || "1";
  rowEndEl.value = read("aa_row_end") || "";
  const identifyRaw = read("aa_identify");
  const identifyArr = String(identifyRaw || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  setCheckedValues("#aa_identify_group", identifyArr.length ? identifyArr : ["Prefer not to say"]);
  brandsWorkedEl.value = read("aa_brands_worked");
  successPartnerEl.value = read("aa_successful_partnership");
  contentInspiresEl.value = read("aa_content_inspires");
  hopeGainEl.value = read("aa_hope_gain");
  howFoundEl.value = read("aa_how_found");
  cityCountryEl.value = read("aa_city_country");
  demographicEl.value = read("aa_demographic");
  growthStrategyEl.value = read("aa_growth_strategy");
  contentIdeasEl.value = read("aa_content_ideas");
  followersEngagementEl.value = read("aa_followers_engagement");
  whyFitEl.value = read("aa_why_fit");
  purchaseLoveEl.value = read("aa_purchase_love");
  whyJoinEl.value = read("aa_why_join");
  genericShortEl.value = read("aa_generic_short");
  genericLongEl.value = read("aa_generic_long");
  messageEl.value = read("aa_message");
  modal.classList.remove("hidden");
  window.setTimeout(() => fullNameEl.focus(), 0);

  return new Promise((resolve) => {
    let done = false;
    const cleanup = () => {
      modal.classList.add("hidden");
      btnCancel.removeEventListener("click", onCancel);
      btnSave.removeEventListener("click", onSave);
      btnConfirm.removeEventListener("click", onConfirm);
    };
    const finish = (val) => {
      if (done) return;
      done = true;
      cleanup();
      resolve(val);
    };
    const onCancel = () => finish(null);

    const persistFormToLocalStorage = () => {
      const full_name = String(fullNameEl.value || "").trim();
      const email = String(emailEl.value || "").trim();
      const phone = String(phoneEl.value || "").trim();
      const website = String(websiteEl.value || "").trim();
      const instagram = String(instagramEl.value || "").trim();
      const tiktok = String(tiktokEl.value || "").trim();
      const youtube = String(youtubeEl.value || "").trim();
      const business_type = String(businessTypeEl.value || "").trim();
      const dob = String(dobEl.value || "").trim();
      const shipping_location = String(shipEl.value || "United States").trim() || "United States";
      const identify = collectCheckedValues("#aa_identify_group");
      const apply_mode = String(applyModeEl.value || "only_dat").trim() || "only_dat";
      const purchase_before_choice = String(purchaseBeforeChoiceEl.value || "Yes").trim() || "Yes";
      const row_start = String(rowStartEl.value || "").trim();
      const row_end = String(rowEndEl.value || "").trim();
      const brands_worked = String(brandsWorkedEl.value || "").trim();
      const successful_partnership = String(successPartnerEl.value || "").trim();
      const content_inspires = String(contentInspiresEl.value || "").trim();
      const hope_gain = String(hopeGainEl.value || "").trim();
      const how_found = String(howFoundEl.value || "").trim();
      const city_country = String(cityCountryEl.value || "").trim();
      const demographic = String(demographicEl.value || "").trim();
      const growth_strategy = String(growthStrategyEl.value || "").trim();
      const content_ideas = String(contentIdeasEl.value || "").trim();
      const followers_engagement = String(followersEngagementEl.value || "").trim();
      const why_fit = String(whyFitEl.value || "").trim();
      const purchase_love = String(purchaseLoveEl.value || "").trim();
      const why_join = String(whyJoinEl.value || "").trim();
      const generic_short = String(genericShortEl.value || "").trim();
      const generic_long = String(genericLongEl.value || "").trim();
      const message = String(messageEl.value || "").trim();

      keep("aa_full_name", full_name);
      keep("aa_email", email);
      keep("aa_phone", phone);
      keep("aa_website", website);
      keep("aa_instagram", instagram);
      keep("aa_tiktok", tiktok);
      keep("aa_youtube", youtube);
      keep("aa_business_type", business_type);
      keep("aa_dob", dob);
      keep("aa_shipping_location", shipping_location);
      keep("aa_identify", (identify && identify.length ? identify : ["Prefer not to say"]).join(", "));
      keep("aa_apply_mode", apply_mode);
      keep("aa_purchase_before_choice", purchase_before_choice);
      keep("aa_row_start", row_start || "1");
      keep("aa_row_end", row_end || "");
      keep("aa_brands_worked", brands_worked);
      keep("aa_successful_partnership", successful_partnership);
      keep("aa_content_inspires", content_inspires);
      keep("aa_hope_gain", hope_gain);
      keep("aa_how_found", how_found);
      keep("aa_city_country", city_country);
      keep("aa_demographic", demographic);
      keep("aa_growth_strategy", growth_strategy);
      keep("aa_content_ideas", content_ideas);
      keep("aa_followers_engagement", followers_engagement);
      keep("aa_why_fit", why_fit);
      keep("aa_purchase_love", purchase_love);
      keep("aa_why_join", why_join);
      keep("aa_generic_short", generic_short);
      keep("aa_generic_long", generic_long);
      keep("aa_message", message);
    };

    const onSave = () => {
      persistFormToLocalStorage();
      alert("Đã lưu mẫu đăng ký.");
    };
    const onConfirm = () => {
      const full_name = String(fullNameEl.value || "").trim();
      const email = String(emailEl.value || "").trim();
      const phone = String(phoneEl.value || "").trim();
      const website = String(websiteEl.value || "").trim();
      const instagram = String(instagramEl.value || "").trim();
      const tiktok = String(tiktokEl.value || "").trim();
      const youtube = String(youtubeEl.value || "").trim();
      const business_type = String(businessTypeEl.value || "").trim();
      const dob = String(dobEl.value || "").trim();
      const shipping_location = String(shipEl.value || "United States").trim() || "United States";
      const identify = collectCheckedValues("#aa_identify_group");
      const apply_mode = String(applyModeEl.value || "only_dat").trim() || "only_dat";
      const purchase_before_choice = String(purchaseBeforeChoiceEl.value || "Yes").trim() || "Yes";
      const row_start = String(rowStartEl.value || "").trim();
      const row_end = String(rowEndEl.value || "").trim();
      const brands_worked = String(brandsWorkedEl.value || "").trim();
      const successful_partnership = String(successPartnerEl.value || "").trim();
      const content_inspires = String(contentInspiresEl.value || "").trim();
      const hope_gain = String(hopeGainEl.value || "").trim();
      const how_found = String(howFoundEl.value || "").trim();
      const city_country = String(cityCountryEl.value || "").trim();
      const demographic = String(demographicEl.value || "").trim();
      const growth_strategy = String(growthStrategyEl.value || "").trim();
      const content_ideas = String(contentIdeasEl.value || "").trim();
      const followers_engagement = String(followersEngagementEl.value || "").trim();
      const why_fit = String(whyFitEl.value || "").trim();
      const purchase_love = String(purchaseLoveEl.value || "").trim();
      const why_join = String(whyJoinEl.value || "").trim();
      const generic_short = String(genericShortEl.value || "").trim();
      const generic_long = String(genericLongEl.value || "").trim();
      const message = String(messageEl.value || "").trim();
      if (!full_name && !email) {
        alert("Nhập tối thiểu Họ tên hoặc Email.");
        return;
      }
      persistFormToLocalStorage();
      finish({
        profile: {
          full_name,
          email,
          phone,
          website,
          instagram,
          tiktok,
          youtube,
          business_type,
          dob,
          identify: identify && identify.length ? identify : ["Prefer not to say"],
          shipping_location,
          brands_worked,
          successful_partnership,
          content_inspires,
          hope_gain,
          how_found,
          city_country,
          demographic,
          growth_strategy,
          content_ideas,
          followers_engagement,
          why_fit,
          purchase_love,
          why_join,
          generic_short,
          generic_long,
          message,
          purchase_before_choice,
        },
        apply_mode,
        row_start,
        row_end,
      });
    };

    btnCancel.addEventListener("click", onCancel);
    btnSave.addEventListener("click", onSave);
    btnConfirm.addEventListener("click", onConfirm);
  });
}

async function autoApplyFromResultFile(name) {
  if (!isAutoApplyCollabsEnabled()) {
    alert("Auto Apply Collabs đang tắt trên server.");
    return;
  }
  const form = await collectAutoApplyProfile();
  if (!form) return;
  const res = await fetch("/api/auto-apply/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      profile: form.profile,
      apply_mode: form.apply_mode,
      row_start: form.row_start,
      row_end: form.row_end,
      auto_submit: false,
      use_cdp: true,
      cdp_url: "http://127.0.0.1:9222",
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Không thể bắt đầu Auto Apply.");
    return;
  }
  // Bật poll để theo dõi kết thúc auto-apply (popup + đổi nút Hủy về Auto Apply).
  if (!state.pollTimer) {
    state.pollTimer = setInterval(pollStatus, POLL_MS);
  }
  state.autoApply.runToken = `${Date.now()}-${String(name || "")}`;
  state.autoApply.notifiedToken = "";
  state.autoApply.lastResultSig = "";
  // Đánh dấu trạng thái bắt đầu chạy để detect cạnh running -> done.
  state.autoApply.lastRunning = true;
  state.autoApply.lastFile = String(name || "");
  // UI sẽ tự đổi nút Auto Apply -> Hủy trong danh sách file.
  await loadResults();
  await pollStatus();
}

async function stopAutoApply() {
  if (!isAutoApplyCollabsEnabled()) {
    alert("Auto Apply Collabs đang tắt trên server.");
    return;
  }
  const res = await fetch("/api/auto-apply/stop", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Không hủy được Auto Apply.");
    return;
  }
  await loadResults();
}

async function fetchAutoApplyStatus() {
  if (!isAutoApplyCollabsEnabled()) return {};
  const res = await fetch("/api/auto-apply/status", { cache: "no-store" });
  return await res.json().catch(() => ({}));
}

function readLocalApplyHistory() {
  try {
    const raw = localStorage.getItem(LS_AUTO_APPLY_HISTORY);
    const arr = JSON.parse(raw || "[]");
    return Array.isArray(arr) ? arr : [];
  } catch (_) {
    return [];
  }
}

function appendLocalApplyHistory(entry) {
  const items = readLocalApplyHistory();
  items.unshift(entry);
  localStorage.setItem(LS_AUTO_APPLY_HISTORY, JSON.stringify(items.slice(0, 200)));
}

async function openApplyHistory(name) {
  if (!isAutoApplyCollabsEnabled()) {
    alert("Auto Apply Collabs đang tắt trên server.");
    return;
  }
  let modal = $("applyHistoryModal");
  let box = $("applyHistoryBox");
  let closeBtn = $("applyHistoryCloseBtn");
  if (!modal || !box || !closeBtn) {
    modal = document.createElement("div");
    modal.className = "modal-backdrop hidden";
    modal.id = "applyHistoryModal";
    modal.innerHTML = `
      <div class="modal-card">
        <h3>Lịch sử Apply</h3>
        <div class="log-box" id="applyHistoryBox"></div>
        <div class="actions">
          <button class="btn" type="button" id="applyHistoryCloseBtn">Đóng</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    box = $("applyHistoryBox");
    closeBtn = $("applyHistoryCloseBtn");
  }
  if (!modal || !box || !closeBtn) return;
  let items = [];
  let apiOk = false;
  try {
    const res = await fetch(`/api/auto-apply/history?name=${encodeURIComponent(name || "")}`, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      items = Array.isArray(data.items) ? data.items : [];
      apiOk = true;
    }
  } catch (_) {}
  if (!apiOk) {
    const local = readLocalApplyHistory();
    items = local.filter((it) => String((it || {}).file || "") === String(name || ""));
  }
  box.innerHTML = "";
  if (!items.length) {
    box.textContent = "Chưa có lịch sử apply cho file này.";
  } else {
    items.forEach((entry) => {
      const title = String(entry.started_at_display || entry.started_at || "").trim() || "(không rõ thời gian)";
      const wrap = document.createElement("div");
      wrap.style.marginBottom = "16px";
      wrap.style.paddingBottom = "10px";
      wrap.style.borderBottom = "1px solid #22314f";

      const head = document.createElement("div");
      head.textContent = title;
      head.style.fontSize = "18px";
      head.style.fontWeight = "700";
      head.style.marginBottom = "8px";
      wrap.appendChild(head);

      const attempted = Array.isArray(entry.attempted_items) ? entry.attempted_items : [];
      const submitted = Array.isArray(entry.submitted_items) ? entry.submitted_items : [];
      const submittedFromAttempted = attempted.filter((it) => !!it && !!it.submitted);
      const notSubmittedFromAttempted = attempted.filter((it) => !!it && !it.submitted);

      const vnErrorFromNote = (noteRaw) => {
        const note = String(noteRaw || "").trim();
        if (!note) return "Không rõ lý do";
        if (note === "timeout_open_page") return "Timeout mở trang";
        if (note.startsWith("error_open_page:")) return `Lỗi mở trang: ${note.replace(/^error_open_page:\s*/i, "")}`.trim();
        if (note === "login_or_signup_blocked") return "Chưa đăng nhập Shopify (quá 200s) hoặc bị chặn đăng nhập";
        if (note === "no_apply_cta") return "Không tìm thấy nút Apply";
        if (note === "not_in_collabs_after_apply") return "Đã bấm Apply nhưng không vào được trang Collabs";
        if (note === "cannot_open_collabs") return "Không mở được Collabs sau khi Apply";
        if (note === "brand_timeout") return "Quá thời gian xử lý brand";
        if (note === "no_fields_detected") return "Không nhận diện được ô để điền hoặc đã apply thành công";
        if (note === "not_submitted_kept_open") return "Chưa bấm được nút “Send application”";
        if (note === "submitted") return "Đã submit";
        return note; // fallback: show raw
      };

      const domainFromLink = (link) => {
        try {
          const u = new URL(String(link || ""));
          let h = String(u.host || "").toLowerCase();
          if (h.startsWith("www.")) h = h.slice(4);
          return h;
        } catch (_) {
          return "";
        }
      };

      const section = (label) => {
        const t = document.createElement("div");
        t.textContent = label;
        t.style.fontWeight = "700";
        t.style.margin = "10px 0 6px";
        t.style.color = "#cbd5e1";
        return t;
      };

      // 1) Đã submit
      wrap.appendChild(section(`Đã submit (${(submittedFromAttempted.length || submitted.length || 0)})`));
      const listSubmitted = submittedFromAttempted.length ? submittedFromAttempted : submitted;
      if (!listSubmitted.length) {
        const empty = document.createElement("div");
        empty.textContent = "Không có brand submit thành công.";
        empty.style.color = "#9aa7bd";
        wrap.appendChild(empty);
      } else {
        const ul = document.createElement("ul");
        ul.style.margin = "0";
        ul.style.paddingLeft = "18px";
        listSubmitted.forEach((it) => {
          const li = document.createElement("li");
          const brand = String(it.brand || "").trim() || "(không rõ brand)";
          const email = String(it.email || entry.email || "").trim() || "(không rõ email)";
          li.textContent = `${brand} | ${email}`;
          ul.appendChild(li);
        });
        wrap.appendChild(ul);
      }

      // 2) Chưa submit
      wrap.appendChild(section(`Chưa submit (${notSubmittedFromAttempted.length})`));
      if (!attempted.length) {
        const note = document.createElement("div");
        note.textContent = "Chưa có dữ liệu brand chưa submit (phiên cũ).";
        note.style.color = "#9aa7bd";
        wrap.appendChild(note);
      } else if (!notSubmittedFromAttempted.length) {
        const ok = document.createElement("div");
        ok.textContent = "Tất cả brand trong phiên này đã submit.";
        ok.style.color = "#9aa7bd";
        wrap.appendChild(ok);
      } else {
        const ul = document.createElement("ul");
        ul.style.margin = "0";
        ul.style.paddingLeft = "18px";
        notSubmittedFromAttempted.forEach((it) => {
          const li = document.createElement("li");
          const email = String(it.email || entry.email || "").trim() || "(không rõ email)";
          const domain = String(it.domain || "").trim() || domainFromLink(it.link) || String(it.brand || "").trim() || "(không rõ domain)";
          const errVi = vnErrorFromNote(it.note);
          li.textContent = `${domain} | ${email} | ${errVi}`;
          ul.appendChild(li);
        });
        wrap.appendChild(ul);
      }
      box.appendChild(wrap);
    });
  }
  if (!apiOk) {
    const note = document.createElement("div");
    note.style.marginTop = "8px";
    note.style.color = "#9aa7bd";
    note.textContent = "Đang dùng lịch sử local (backend history API chưa sẵn sàng).";
    box.appendChild(note);
  }
  modal.classList.remove("hidden");

  const close = () => {
    modal.classList.add("hidden");
    closeBtn.removeEventListener("click", onClose);
    modal.removeEventListener("click", onBackdrop);
    document.removeEventListener("keydown", onEsc);
  };
  const onClose = () => close();
  const onBackdrop = (e) => {
    if (e.target === modal) close();
  };
  const onEsc = (e) => {
    if (e.key === "Escape") close();
  };
  closeBtn.addEventListener("click", onClose);
  modal.addEventListener("click", onBackdrop);
  document.addEventListener("keydown", onEsc);
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
    state.currentLicense = lic;
    try {
      const enabled = lic && typeof lic.auto_apply_collabs_enabled !== "undefined" ? !!lic.auto_apply_collabs_enabled : true;
      document.body.dataset.autoApplyCollabsEnabled = enabled ? "1" : "0";
    } catch (_) {
      /* ignore */
    }
    renderLicenseStatus(lic);
    applyLicenseSourceVisibility(lic);
    finishLicenseLoadingState();
    return lic;
  } catch (_) {
    const msg = $("licenseMessage");
    if (msg) msg.textContent = "Không đọc được trạng thái bản quyền.";
    // Nếu lỗi gọi server, mở full tab để không khóa người dùng.
    const fallbackLicense = { licensed: false, allowed_sources: ["uppromote", "goaffpro", "refersion"] };
    state.currentLicense = fallbackLicense;
    applyLicenseSourceVisibility(fallbackLicense);
    finishLicenseLoadingState();
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
  const [res, aa] = await Promise.all([
    fetch("/api/results"),
    isAutoApplyCollabsEnabled() ? fetchAutoApplyStatus() : Promise.resolve({}),
  ]);
  state.autoApply.lastRunning = isAutoApplyCollabsEnabled() ? !!aa?.running : false;
  state.autoApply.lastFile = isAutoApplyCollabsEnabled() ? String(aa?.file || "") : "";
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
    const isRunning = !!aa?.running;
    const sameFile = String(aa?.file || "") === String(f.name || "");
    const btnHistory = document.createElement("button");
    btnHistory.type = "button";
    btnHistory.className = "btn sm";
    btnHistory.textContent = "Lịch sử Apply";
    btnHistory.addEventListener("click", () => openApplyHistory(f.name));
    actions.appendChild(btnDl);
    if (isAutoApplyCollabsEnabled()) {
      const btnAutoApply = document.createElement("button");
      btnAutoApply.type = "button";
      btnAutoApply.className = "btn sm";
      if (isRunning && sameFile) {
        btnAutoApply.textContent = "Hủy";
        btnAutoApply.className = "btn sm danger";
        btnAutoApply.addEventListener("click", () => stopAutoApply());
      } else {
        btnAutoApply.textContent = "Auto Apply";
        btnAutoApply.addEventListener("click", () => autoApplyFromResultFile(f.name));
      }
      btnAutoApply.disabled = isRunning && !sameFile;
      actions.appendChild(btnAutoApply);
      actions.appendChild(btnHistory);
    }
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
  $("runBtnCollabs").addEventListener("click", () => runFilter("collabs"));
  ["pauseBtn", "pauseBtnGp", "pauseBtnRf", "pauseBtnCb"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("click", togglePause);
  });
  ["stopBtn", "stopBtnGp", "stopBtnRf", "stopBtnCb"].forEach((id) => {
    const el = $(id);
    if (el) el.addEventListener("click", stopRun);
  });
  $("refreshResultsBtn").addEventListener("click", (e) => {
    try {
      e.preventDefault();
      e.stopPropagation();
    } catch (_) {}
    loadResults();
  });
  const edgeBtn = $("openEdgeCdpBtn");
  if (edgeBtn) {
    edgeBtn.addEventListener("click", (e) => {
      try {
        e.preventDefault();
        e.stopPropagation();
      } catch (_) {}
      openEdgeForAutoApply();
    });
  }
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
    erf.addEventListener("input", () => mirrorEndPageFromRefersion());
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

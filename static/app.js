const state = {
  logCursor: 0,
  pollTimer: null,
  currentLicense: null,
};

const AUTO_APPLY_DEFAULTS = {
  aa_business_type: "Content Creator",
  aa_brands_worked: "Shopify and DTC lifestyle brands",
  aa_successful_partnership:
    "A successful collaboration starts with clear goals, fast communication, and consistent content quality. I can deliver authentic content on schedule and optimize based on performance.",
  aa_content_inspires: "Educational product demos, before-after transformations, and real customer-style storytelling.",
  aa_hope_gain: "Long-term partnership, exclusive offers for my audience, and performance-based growth.",
  aa_how_found: "I discovered your brand through social media and creator community recommendations.",
  aa_city_country: "Ho Chi Minh City, Vietnam",
  aa_demographic: "Women and men aged 18-34 interested in lifestyle, home, and online shopping.",
  aa_growth_strategy: "Consistent short-form videos, SEO captions, UGC-style content, and weekly A/B tests on hooks.",
  aa_children_age: "N/A",
  aa_ugc_content: "Yes, I create UGC content.",
  aa_content_ideas: "Unboxing, product comparison, problem-solution videos, and creator picks.",
  aa_why_fit:
    "I have an audience aligned with your target customers and a strong track record of converting content.",
  aa_purchase_love: "I love the product quality, design details, and how practical it is in daily use.",
  aa_why_join:
    "I would love to join your community to create authentic content, introduce your products to my audience, and build a long-term win-win partnership.",
  aa_generic_short: "I'd love to collaborate and create engaging content for your audience.",
  aa_generic_long:
    "I focus on high-quality, authentic content that builds trust and drives conversions. I can deliver consistent posts, clear communication, and measurable performance.",
  aa_message:
    "I am excited to collaborate and create authentic, high-converting content for your brand. I can provide short-form videos, product storytelling, and consistent communication.",
  aa_dob: "",
  aa_shipping_location: "United States",
  aa_identify: "Prefer not to say",
  aa_apply_mode: "only_dat",
  aa_purchase_before_choice: "Yes",
  aa_row_start: "1",
  aa_row_end: "",
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
  "COLLABS_API_URL",
  "COLLABS_LIMIT",
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

function clampCollabsLimitField(id) {
  const el = $(id);
  if (!el) return;
  let n = parseInt(String(el.value ?? "").trim(), 10);
  if (Number.isNaN(n)) n = 48;
  n = Math.max(12, Math.min(48, Math.floor(n / 12) * 12));
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
  clampCollabsLimitField("COLLABS_LIMIT");
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
    const [stRes, lgRes] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch(`/api/logs?since=${state.logCursor}`, { cache: "no-store" }),
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
  clampCollabsLimitField("COLLABS_LIMIT");
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
      modal.removeEventListener("click", onBackdrop);
      document.removeEventListener("keydown", onEsc);
    };
    const finish = (val) => {
      if (done) return;
      done = true;
      cleanup();
      resolve(val);
    };
    const onCancel = () => finish(null);
    const onBackdrop = (e) => {
      if (e.target === modal) finish(null);
    };
    const onEsc = (e) => {
      if (e.key === "Escape") finish(null);
    };

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
    modal.addEventListener("click", onBackdrop);
    document.addEventListener("keydown", onEsc);
  });
}

async function autoApplyFromResultFile(name) {
  const form = await collectAutoApplyProfile();
  if (!form) return;
  const res = await fetch("/api/auto-apply", {
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
      login_first: true,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Auto Apply thất bại.");
    if (Array.isArray(data.logs) && data.logs.length) {
      console.log("[AUTO APPLY LOGS]\n" + data.logs.join("\n"));
    }
    return;
  }
  const r = data.result || {};
  alert(
    `Auto Apply xong.\nTổng link: ${r.total || 0}\nĐã điền form: ${r.filled || 0}\nĐã submit: ${r.submitted || 0}`
  );
  if (Array.isArray(data.logs) && data.logs.length) {
    console.log("[AUTO APPLY LOGS]\n" + data.logs.join("\n"));
  }
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
    const btnAutoApply = document.createElement("button");
    btnAutoApply.type = "button";
    btnAutoApply.className = "btn sm";
    btnAutoApply.textContent = "Auto Apply";
    btnAutoApply.addEventListener("click", () => autoApplyFromResultFile(f.name));
    actions.appendChild(btnDl);
    actions.appendChild(btnAutoApply);
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

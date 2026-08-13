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
  autoApplyRefersion: {
    lastRunning: false,
    lastFile: "",
    lastResultSig: "",
    runToken: "",
    notifiedToken: "",
    observedRunning: false, // true sau khi backend xác nhận đang chạy trong phiên hiện tại
    registrationEmail: "",
    progressModal: null,
    reopenModal: null, // ()=>void — mở lại popup log sau khi tắt
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

function isAutoApplyRefersionEnabled() {
  try {
    const v = document.body?.dataset?.autoApplyRefersionEnabled;
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
  aa_account_mode: "single",
  aa_multi_account_count: "1-2",
  aa_multi_account_emails: "",
  aa_multi_apply_flow: "replay_all_accounts",
};

const AUTO_REFERSION_DEFAULTS = {
  ar_apply_mode: "only_dat",
  ar_row_start: "1",
  ar_row_end: "",
  ar_reason: "social influencer",
  ar_affiliate_type: "Review Website",
  ar_country: "United States",
  ar_generic_answer: "",
};

const LS_AUTO_APPLY_HISTORY = "aff_auto_apply_history_v1";
const LS_AUTO_REFERSION_HISTORY = "aff_refersion_history_v1";

/** Poll nhanh hơn khi đang chạy; server phải threaded=True để /api/logs không bị chặn bởi worker. */
const POLL_MS = 120;

let pollStatusBusy = false;

/** Khớp với ô nhập trong templates/index.html — không gồm AFF_LICENSE_* (chỉnh trong .env, không có field trên web). */
const settingKeys = [
  "APIFY_TOKENS",
  "UPPROMOTE_API_URL",
  "UPPROMOTE_BEARER_TOKEN",
  "UPPROMOTE_REFRESH_TOKEN",
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
  "APIFY_TOKENS",
  "UPPROMOTE_BEARER_TOKEN",
  "UPPROMOTE_REFRESH_TOKEN",
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
const LS_END_PAGE_COLLABS = "aff_filter_end_page_collabs";

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

function syncAutoApplyAccountModeUI() {
  const sel = $("aa_account_mode");
  const wrap = $("aa_multi_count_wrap");
  const mode = sel && sel.value === "multi" ? "multi" : "single";
  if (wrap) wrap.classList.toggle("hidden", mode !== "multi");
}

const COLLABS_ACCOUNT_MAX = 10;

/** Chọn tài khoản: dải 1-5, danh sách 1,4,7, hoặc số n (chỉ tài khoản n). */
function parseCollabsAccountSelection(raw) {
  const s = String(raw || "").trim();
  if (!s) {
    return { ok: false, indices: [], error: "Nhập tài khoản (vd: 1-5 hoặc 1,4,7)." };
  }
  if (s.includes(",")) {
    const parts = s.split(",").map((p) => p.trim()).filter(Boolean);
    if (!parts.length) {
      return { ok: false, indices: [], error: "Danh sách không hợp lệ." };
    }
    const idx = [];
    const seen = new Set();
    for (const p of parts) {
      if (!/^\d+$/.test(p)) {
        return {
          ok: false,
          indices: [],
          error: `Phần "${p}" không hợp lệ. Chỉ dùng số 1–${COLLABS_ACCOUNT_MAX}, cách nhau bởi dấu phẩy.`,
        };
      }
      const n = parseInt(p, 10);
      if (n < 1 || n > COLLABS_ACCOUNT_MAX) {
        return { ok: false, indices: [], error: `Tài khoản phải từ 1 đến ${COLLABS_ACCOUNT_MAX}.` };
      }
      if (!seen.has(n)) {
        seen.add(n);
        idx.push(n);
      }
    }
    return { ok: true, indices: idx, error: "" };
  }
  if (s.includes("-")) {
    const m = s.match(/^(\d+)\s*-\s*(\d+)$/);
    if (!m) {
      return {
        ok: false,
        indices: [],
        error: "Dải không hợp lệ. Dùng đúng dạng 1-5 (hai số, một dấu gạch).",
      };
    }
    let a = parseInt(m[1], 10);
    let b = parseInt(m[2], 10);
    if (a > b) [a, b] = [b, a];
    if (a < 1 || b > COLLABS_ACCOUNT_MAX) {
      return { ok: false, indices: [], error: `Dải phải nằm trong 1–${COLLABS_ACCOUNT_MAX}.` };
    }
    const idx = [];
    for (let i = a; i <= b; i += 1) idx.push(i);
    return { ok: true, indices: idx, error: "" };
  }
  if (/^\d+$/.test(s)) {
    const n = parseInt(s, 10);
    if (!Number.isFinite(n) || n < 1 || n > COLLABS_ACCOUNT_MAX) {
      return {
        ok: false,
        indices: [],
        error: `Nhập số từ 1–${COLLABS_ACCOUNT_MAX} (chỉ tài khoản n), hoặc dải/danh sách.`,
      };
    }
    return { ok: true, indices: [n], error: "" };
  }
  return {
    ok: false,
    indices: [],
    error: "Không hiểu định dạng. Dùng 1-5 hoặc 1,4,7 hoặc số 1-10.",
  };
}

/** Parse profile theo tài khoản, mỗi dòng: 1=email|Họ tên|SĐT|Website|Instagram */
function parseCollabsAccountProfileMap(raw, selectedIndices) {
  const s = String(raw || "").trim();
  const out = {};
  if (!s) return { ok: true, map: out, error: "" };
  const allowed = new Set(Array.isArray(selectedIndices) ? selectedIndices : []);
  const lines = s.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);
  for (const line of lines) {
    const eqPos = line.indexOf("=");
    if (eqPos <= 0) {
      return {
        ok: false,
        map: {},
        error: `Dòng "${line}" không hợp lệ. Dùng dạng 1=email|Họ tên|SĐT|Website|Instagram.`,
      };
    }
    const lhs = line.slice(0, eqPos).trim();
    const rhs = line.slice(eqPos + 1).trim();
    if (!/^\d+$/.test(lhs)) {
      return { ok: false, map: {}, error: `Tài khoản "${lhs}" không hợp lệ.` };
    }
    const idx = parseInt(lhs, 10);
    if (idx < 1 || idx > COLLABS_ACCOUNT_MAX) {
      return { ok: false, map: {}, error: `Tài khoản phải từ 1 đến ${COLLABS_ACCOUNT_MAX}.` };
    }
    // TK không nằm trong "Tài khoản / trình duyệt": bỏ qua dòng, không báo lỗi.
    if (allowed.size && !allowed.has(idx)) {
      continue;
    }
    const cols = rhs.split("|");
    while (cols.length < 5) cols.push("NO");
    const asValue = (v) => {
      const t = String(v || "").trim();
      if (!t) return "";
      if (t.toUpperCase() === "NO") return "";
      return t;
    };
    const email = asValue(cols[0]);
    const full_name = asValue(cols[1]);
    const phone = asValue(cols[2]);
    const website = asValue(cols[3]);
    const instagram = asValue(cols[4]);
    if (email && !email.includes("@")) {
      return { ok: false, map: {}, error: `Email cho TK${idx} không hợp lệ.` };
    }
    out[String(idx)] = { email, full_name, phone, website, instagram };
  }
  return { ok: true, map: out, error: "" };
}

/** Ô Token Apify / URL / Bearer: mặc định đóng (type=password che ký tự); bấm mắt để sửa; lưu hoặc load lại → đóng. Giá trị .value không đổi khi đóng/mở. */
function setSecretFieldRowOpen(row, open) {
  if (!row) return;
  const id = row.getAttribute("data-secret-for");
  const input = id ? $(id) : null;
  if (!input) return;
  row.classList.toggle("is-open", open);
  if (input.tagName === "TEXTAREA") {
    input.readOnly = !open;
  } else {
    input.type = open ? "text" : "password";
  }
  const btn = row.querySelector(".secret-eye-btn[aria-expanded]");
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
    const btn = row.querySelector(".secret-eye-btn[aria-expanded]");
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
  const rawCb = localStorage.getItem(LS_END_PAGE_COLLABS);
  if ($("endPageCb")) {
    $("endPageCb").value = rawCb === null ? "" : String(rawCb);
  }
}

function persistEndPageCollabs() {
  const v = ($("endPageCb")?.value ?? "").trim();
  localStorage.setItem(LS_END_PAGE_COLLABS, v);
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
  autoCollabsTab: "collabs",
  autoRefersionTab: "refersion",
};

function normalizeAllowedSourcesFromLicense(lic) {
  const all = ["uppromote", "goaffpro", "refersion", "collabs"];
  if (!lic || !lic.licensed) return [];
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
  const licensed = !!(lic && lic.licensed);
  const allowed = new Set(normalizeAllowedSourcesFromLicense(lic));

  const setTabVisible = (tabId, visible) => {
    const show = visible ? "" : "none";
    const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    const panel = document.getElementById(tabId);
    if (btn) btn.style.display = show;
    if (panel) panel.style.display = show;
  };

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    const tabId = btn.dataset.tab || "";
    if (tabId === "settingsTab") {
      btn.style.display = "";
      return;
    }
    if (!licensed) {
      btn.style.display = "none";
      return;
    }
    const source = TAB_SOURCE_MAP[tabId];
    if (!source) {
      btn.style.display = "";
      return;
    }
    btn.style.display = allowed.has(source) ? "" : "none";
  });

  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const tabId = panel.id || "";
    if (tabId === "settingsTab") {
      panel.style.display = "";
      return;
    }
    if (!licensed) {
      panel.style.display = "none";
      return;
    }
    const source = TAB_SOURCE_MAP[tabId];
    if (!source) {
      panel.style.display = "";
      return;
    }
    panel.style.display = allowed.has(source) ? "" : "none";
  });

  document.querySelectorAll("[data-settings-source]").forEach((el) => {
    const source = String(el.getAttribute("data-settings-source") || "").trim().toLowerCase();
    if (!source) return;
    el.style.display = !licensed || allowed.has(source) ? "" : "none";
  });

  if (licensed) {
    try {
      const enabled = isAutoApplyCollabsEnabled();
      setTabVisible("autoCollabsTab", enabled && allowed.has("collabs"));
    } catch (_) {
      /* ignore */
    }
    try {
      const enabledAr = isAutoApplyRefersionEnabled();
      setTabVisible("autoRefersionTab", enabledAr && allowed.has("refersion"));
    } catch (_) {
      /* ignore */
    }
  }

  const activeBtn = document.querySelector(".tab-btn.active");
  const activeTab = activeBtn ? activeBtn.dataset.tab : null;
  const mustGoSettings =
    !licensed ||
    (activeTab &&
      TAB_SOURCE_MAP[activeTab] &&
      !allowed.has(TAB_SOURCE_MAP[activeTab])) ||
    (activeTab === "autoCollabsTab" && licensed && !isAutoApplyCollabsEnabled());
  if (mustGoSettings && activeTab !== "settingsTab") {
    switchTab("settingsTab");
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
  loadTokenStatus();
}

async function loadTokenStatus() {
  const el = $("tokenStatus");
  if (!el) return;
  try {
    const res = await fetch("/api/token-status");
    const data = await res.json();
    if (!data.has_token) {
      el.textContent = "⚠ Chưa có Bearer token";
      el.style.color = "#e74c3c";
      return;
    }
    if (data.remaining_seconds === undefined) {
      el.textContent = "Token: OK (không đọc được thời hạn)";
      el.style.color = "#888";
      return;
    }
    const mins = data.remaining_minutes;
    const color =
      mins > 5 ? "#27ae60" : mins > 1 ? "#f39c12" : "#e74c3c";
    const timeText =
      mins >= 60
        ? `${(mins / 60).toFixed(1)} giờ`
        : `${mins.toFixed(1)} phút`;
    const refreshNote = data.refresh_ok ? " | ↻ Refresh: ON" : " | ↻ Refresh: OFF";
    el.textContent = `⏱ Token Uppromote còn ${timeText}${refreshNote}`;
    el.style.color = color;
  } catch (_) {
    el.textContent = "";
  }
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
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.error || "Không lưu được cài đặt.");
    return;
  }
  closeAllSecretFieldRows();
  alert("Đã lưu cài đặt.");
  loadTokenStatus();
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
    const arReq = isAutoApplyRefersionEnabled() ? fetchAutoRefersionStatus().catch(() => ({})) : Promise.resolve({});
    const [stRes, lgRes, aa, ar] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch(`/api/logs?since=${state.logCursor}`, { cache: "no-store" }),
      aaReq,
      arReq,
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
          const parNote =
            r.parallel && r.parallel_jobs && typeof r.parallel_jobs === "object"
              ? ` (${Object.keys(r.parallel_jobs).length} slot song song)`
              : "";
          appendLocalApplyHistory({
            file: aaFile,
            started_at_display: new Date().toLocaleString("vi-VN"),
            email: "",
            submitted_items: Array.isArray(r.submitted_items) ? r.submitted_items : [],
          });
          const splitHint =
            r.sequential_multi && r.accounts && r.total_brand_runs
              ? `\nĐa tài khoản (lần lượt): ${r.accounts} tài khoản × ${r.total || 0} brand ≈ ${r.total_brand_runs} lượt chạy.`
              : r.sequential_multi && r.accounts
                ? `\nĐa tài khoản (lần lượt): ${r.accounts} phiên, mỗi phiên lặp lại cả danh sách brand.`
                : r.parallel_link_split === "sequential"
                  ? "\nChia link: theo thứ tự (khối liên tiếp)."
                  : r.parallel && r.parallel_link_split
                    ? "\nChia link: round-robin."
                    : "";
          alert(
            `Auto Apply xong.${parNote}${splitHint}\nFile: ${aaFile}\nTổng link: ${r.total || 0}\nĐã điền form: ${r.filled || 0}\nĐã submit: ${r.submitted || 0}`
          );
        } else if (err) {
          alert(`Auto Apply dừng/lỗi.\nFile: ${aaFile}\nLỗi: ${err}`);
        } else {
          alert(`Auto Apply đã dừng.\nFile: ${aaFile}`);
        }
        // refresh lại list để nút Hủy -> Auto Apply
        await Promise.all([loadResults(), loadAutoCollabsFiles()]);
      }
    }

    // Auto Refersion notification
    if (isAutoApplyRefersionEnabled()) {
      const arRunning = !!ar?.running;
      const arFile = String(ar?.file || "");
      const arResult = ar?.result || null;
      const arErr = String(ar?.error || "");
      const arSig = JSON.stringify({ arFile, arResult, arErr });
      state.autoApplyRefersion.lastRunning = arRunning;
      state.autoApplyRefersion.lastFile = arFile;
      const hasArToken = !!state.autoApplyRefersion.runToken;
      if (hasArToken && arRunning) {
        state.autoApplyRefersion.observedRunning = true;
      }
      // Chỉ thông báo khi phiên hiện tại đã thực sự chạy rồi dừng (tránh alert kết quả cũ lần 2+)
      const arFinished =
        hasArToken &&
        state.autoApplyRefersion.observedRunning &&
        !arRunning &&
        (!!arResult || !!arErr);
      const shouldArNotifyByToken = hasArToken && state.autoApplyRefersion.notifiedToken !== state.autoApplyRefersion.runToken;
      const shouldArNotifyBySig = !hasArToken && state.autoApplyRefersion.lastResultSig !== arSig;
      if (arFinished && (shouldArNotifyByToken || shouldArNotifyBySig)) {
        state.autoApplyRefersion.lastResultSig = arSig;
        if (hasArToken) state.autoApplyRefersion.notifiedToken = state.autoApplyRefersion.runToken;
        if (arResult && typeof arResult === "object") {
          // Lưu local history để hiển thị khi backend chưa kịp ghi
          appendLocalRefersionHistory({
            file: arFile,
            started_at_display: new Date().toLocaleString("vi-VN"),
            email: getRefersionRegistrationEmail(arResult),
            submitted_items: Array.isArray(arResult.submitted_items) ? arResult.submitted_items : [],
            attempted_items: Array.isArray(arResult.attempted_items) ? arResult.attempted_items : [],
            total: arResult.total || 0,
            filled: arResult.filled || 0,
            submitted: arResult.submitted || 0,
            failed: arResult.failed || 0,
            skipped: arResult.skipped || 0,
            submit_failed: arResult.submit_failed || 0,
            cancelled: !!arResult.cancelled,
          });
          const emailLine = formatRefersionResultHeader(arResult);
          const arBody = `File: ${arFile}${emailLine ? `\n${emailLine}` : ""}\n${formatRefersionSummary(arResult)}`;
          sendBrowserNotification(
            arResult.cancelled ? "Auto Refersion đã hủy" : "Auto Refersion hoàn tất",
            arBody,
            () => {
              if (state.autoApplyRefersion.reopenModal) state.autoApplyRefersion.reopenModal();
            }
          );
          alert(`${arResult.cancelled ? "Auto Refersion đã hủy." : "Auto Refersion xong."}\n${arBody}`);
        } else if (arErr) {
          appendLocalRefersionHistory({
            file: arFile,
            started_at_display: new Date().toLocaleString("vi-VN"),
            error: arErr,
            attempted_items: [],
            submitted_items: [],
          });
          sendBrowserNotification("Auto Refersion lỗi", `File: ${arFile}\nLỗi: ${arErr}`, null);
          alert(`Auto Refersion lỗi.\nFile: ${arFile}\nLỗi: ${arErr}`);
        } else {
          sendBrowserNotification("Auto Refersion đã dừng", `File: ${arFile}`, null);
          alert(`Auto Refersion đã dừng.\nFile: ${arFile}`);
        }
        state.autoApplyRefersion.observedRunning = false;
        await loadResults();
      }
    }

    // Chỉ dừng polling khi cả pipeline và auto-apply (nếu bật) đều đã dừng.
    const aaRunningForStop = isAutoApplyCollabsEnabled() ? !!aa?.running : false;
    const arRunningForStop = isAutoApplyRefersionEnabled() ? !!ar?.running : false;
    if (!st.running && !aaRunningForStop && !arRunningForStop && state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      state.autoApplyRefersion.reopenModal = null;
      state.autoApplyRefersion.runToken = "";
      state.autoApplyRefersion.notifiedToken = "";
      state.autoApplyRefersion.lastResultSig = "";
      state.autoApplyRefersion.observedRunning = false;
      state.autoApplyRefersion.registrationEmail = "";
      state.autoApplyRefersion.progressModal = null;
      state.autoApply.runToken = "";
      state.autoApply.notifiedToken = "";
      state.autoApply.lastResultSig = "";
      await Promise.all([loadResults(), loadAutoCollabsFiles()]);
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
        const emptyLabel = String(root.getAttribute("data-empty-label") || "").trim();
        if (emptyLabel) {
          textEl.textContent = emptyLabel;
        } else {
          textEl.textContent = label.includes("identify") ? "Prefer not to say" : "Tất cả";
        }
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

function updateCollabsDiscoveryModeUI() {
  const mode = $("collabsDiscoveryMode")?.value?.trim() || "in_discovery";
  const isOutside = mode === "outside_discovery";
  document.querySelectorAll(".collabs-in-discovery-only").forEach((el) => {
    el.style.display = isOutside ? "none" : "";
  });
  document.querySelectorAll(".collabs-outside-discovery-only").forEach((el) => {
    el.style.display = isOutside ? "" : "none";
  });
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
    const discoveryMode = $("collabsDiscoveryMode")?.value?.trim() || "in_discovery";
    const outTarget = $("outsideTargetResultsCb")?.value?.trim() || "30";
    return {
      discovery_mode: discoveryMode,
      start_page: $("startPageCb")?.value?.trim() || "1",
      end_page: $("endPageCb")?.value?.trim() || "",
      outside_target_results: outTarget,
      min_commission: $("minCommissionCb")?.value?.trim() || "",
      min_cookie: "",
      currency: "",
      application_review: "",
      search_query: $("searchQueryCb")?.value?.trim() || "",
      product_categories: collectCheckedValues("#productCategoryCollabsGroup"),
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
    filter_by_category: Boolean($("filterByCategoryUppromote")?.checked),
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

async function resetCollabsOutsideState() {
  const ok = window.confirm(
    "Reset trạng thái ngoài Discovery?\nThao tác sẽ xóa cursor và danh sách dedupe đã lưu."
  );
  if (!ok) return;
  const res = await fetch("/api/collabs-outside/reset", { method: "POST" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok || !body?.ok) {
    alert(body?.error || "Không reset được trạng thái ngoài Discovery.");
    return;
  }
  const removed = Array.isArray(body?.removed) && body.removed.length
    ? `\nĐã xóa: ${body.removed.join(", ")}`
    : "\nKhông có file trạng thái để xóa.";
  alert(`Đã reset trạng thái ngoài Discovery.${removed}`);
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
  await Promise.all([loadResults(), loadAutoCollabsFiles()]);
}

function closeEdgeCdpAccountPicker() {
  const modal = $("edgeCdpAccountsModal");
  if (modal) modal.classList.add("hidden");
}

function showEdgeCdpAccountPicker() {
  const modal = $("edgeCdpAccountsModal");
  if (modal) modal.classList.remove("hidden");
}

async function submitOpenEdgeCdpAccounts() {
  const indices = [];
  for (let i = 1; i <= 10; i += 1) {
    const cb = $(`edge_cdp_acc_${i}`);
    if (cb && cb.checked) indices.push(i);
  }
  if (!indices.length) {
    alert("Chọn ít nhất một tài khoản.");
    return;
  }
  try {
    const res = await fetch("/api/edge-cdp/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_indices: indices }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      const detail = Array.isArray(data.logs) && data.logs.length ? `\n\nLog:\n${data.logs.join("\n")}` : "";
      alert((data.error || "Không mở được Edge CDP.") + detail);
      return;
    }
    const opened = Array.isArray(data.opened) ? data.opened : [];
    const summary =
      opened.length > 0
        ? opened.map((o) => `Tài khoản ${o.account}: ${o.cdp_url || ""}`).join("\n")
        : `CDP: ${data.cdp_url || ""}`;
    const detail = Array.isArray(data.logs) && data.logs.length ? `\n\nLog:\n${data.logs.join("\n")}` : "";
    alert(`Edge đã sẵn sàng cho Auto Apply.\n${summary}` + detail);
    closeEdgeCdpAccountPicker();
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
  const accountModeEl = $("aa_account_mode");
  const multiAccountCountEl = $("aa_multi_account_count");
  const multiAccountEmailsEl = $("aa_multi_account_emails");
  const multiApplyFlowEl = $("aa_multi_apply_flow");
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
    !accountModeEl ||
    !multiAccountCountEl ||
    !multiAccountEmailsEl ||
    !multiApplyFlowEl ||
    !btnCancel ||
    !btnSave ||
    !btnConfirm
  ) {
    alert("Thiếu popup Auto Apply trong giao diện.");
    return Promise.resolve(null);
  }

  // Giữ lựa chọn lần trước: mặc định single nếu chưa có dữ liệu lưu.
  const savedAccountMode = String(read("aa_account_mode") || "single").trim().toLowerCase();
  accountModeEl.value = savedAccountMode === "multi" ? "multi" : "single";
  const savedCount =
    read("aa_multi_account_count").trim() ||
    read("aa_multi_browser_count").trim() ||
    "2";
  multiAccountCountEl.value = savedCount;
  multiAccountEmailsEl.value = read("aa_multi_account_emails") || "";
  multiApplyFlowEl.value = read("aa_multi_apply_flow") || "replay_all_accounts";
  syncAutoApplyAccountModeUI();
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
      keep("aa_account_mode", String(accountModeEl.value || "single"));
      keep("aa_multi_account_count", String(multiAccountCountEl.value || "2").trim() || "2");
      keep("aa_multi_account_emails", String(multiAccountEmailsEl.value || "").trim());
      keep("aa_multi_apply_flow", String(multiApplyFlowEl.value || "replay_all_accounts").trim() || "replay_all_accounts");
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
      const account_mode = String(accountModeEl.value || "single").trim() === "multi" ? "multi" : "single";
      let multi_browser_count = 2;
      let collabs_account_indices = null;
      let multi_account_spec = "";
      let collabs_account_profile_map = {};
      const multi_apply_flow = String(multiApplyFlowEl.value || "replay_all_accounts").trim() || "replay_all_accounts";
      if (account_mode === "multi") {
        const rawSpec = String(multiAccountCountEl.value || "").trim();
        const parsed = parseCollabsAccountSelection(rawSpec);
        if (!parsed.ok) {
          alert(parsed.error || "Định dạng tài khoản không hợp lệ.");
          return;
        }
        collabs_account_indices = parsed.indices;
        multi_browser_count = parsed.indices.length;
        multi_account_spec = rawSpec;
        const emailMapRaw = String(multiAccountEmailsEl.value || "").trim();
        const profileMapParsed = parseCollabsAccountProfileMap(emailMapRaw, collabs_account_indices);
        if (!profileMapParsed.ok) {
          alert(profileMapParsed.error || "Thông tin theo tài khoản không hợp lệ.");
          return;
        }
        collabs_account_profile_map = profileMapParsed.map || {};
      }
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
        account_mode,
        multi_apply_flow,
        multi_browser_count,
        collabs_account_indices,
        multi_account_spec,
        collabs_account_profile_map,
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
  const body = {
    name,
    profile: form.profile,
    apply_mode: form.apply_mode,
    row_start: form.row_start,
    row_end: form.row_end,
    auto_submit: false,
    use_cdp: true,
    cdp_url: "http://127.0.0.1:9222",
    account_mode: form.account_mode || "single",
  };
  if (form.account_mode === "multi") {
    body.multi_browser_count = form.multi_browser_count ?? 2;
    body.multi_apply_flow = form.multi_apply_flow || "replay_all_accounts";
    if (Array.isArray(form.collabs_account_indices) && form.collabs_account_indices.length >= 2) {
      body.collabs_account_indices = form.collabs_account_indices;
    }
    if (form.multi_account_spec && String(form.multi_account_spec).trim()) {
      body.multi_account_spec = String(form.multi_account_spec).trim();
    }
    if (form.collabs_account_profile_map && typeof form.collabs_account_profile_map === "object") {
      body.collabs_account_profile_map = form.collabs_account_profile_map;
    }
  }
  const res = await fetch("/api/auto-apply/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Không thể bắt đầu Auto Apply.");
    return;
  }
  // Bật poll để theo dõi kết thúc auto-apply (popup + đổi nút Hủy về Auto Apply).
  // Xóa log box trước khi bắt đầu lượt mới
  const boxes = [logBox(), logBoxCb()].filter(Boolean);
  boxes.forEach((box) => { box.textContent = ""; });
  state.logCursor = 0;
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
  await Promise.all([loadResults(), loadAutoCollabsFiles()]);
}

async function fetchAutoApplyStatus() {
  if (!isAutoApplyCollabsEnabled()) return {};
  const res = await fetch("/api/auto-apply/status", { cache: "no-store" });
  return await res.json().catch(() => ({}));
}

async function fetchAutoRefersionStatus() {
  if (!isAutoApplyRefersionEnabled()) return {};
  const res = await fetch("/api/auto-refersion/status", { cache: "no-store" });
  return await res.json().catch(() => ({}));
}

function stopAutoRefersionProgressPolling() {
  if (state.autoApplyRefersion.progressModal) {
    try {
      state.autoApplyRefersion.progressModal.stopPolling();
    } catch (_) {
      /* ignore */
    }
  }
  const oldOverlay = document.getElementById("ar_progress");
  if (oldOverlay && oldOverlay.dataset.pollTimerId) {
    clearInterval(Number(oldOverlay.dataset.pollTimerId));
    oldOverlay.dataset.pollTimerId = "";
  }
}

async function resetAutoRefersionBackend() {
  try {
    await fetch("/api/auto-refersion/reset", { method: "POST", cache: "no-store" });
  } catch (_) {
    /* ignore */
  }
}

async function stopAutoRefersion() {
  if (!isAutoApplyRefersionEnabled()) {
    alert("Auto Refersion đang tắt trên server.");
    return;
  }
  const res = await fetch("/api/auto-refersion/stop", { method: "POST" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.ok) {
    alert(data.error || "Không hủy được Auto Refersion.");
    return;
  }
  // Dọn state để nút Auto Refersion trở lại bình thường
  state.autoApplyRefersion.runToken = "";
  state.autoApplyRefersion.notifiedToken = "";
  state.autoApplyRefersion.lastResultSig = "";
  state.autoApplyRefersion.observedRunning = false;
  state.autoApplyRefersion.registrationEmail = "";
  state.autoApplyRefersion.reopenModal = null;
  stopAutoRefersionProgressPolling();
  await Promise.all([loadResults(), loadAutoRefersionFiles()]);
}

async function autoApplyRefersionFromResultFile(name) {
  if (!isAutoApplyRefersionEnabled()) {
    alert("Auto Refersion đang tắt trên server.");
    return;
  }
  // Thu thập profile từ form modal Auto Refersion
  const profile = await collectAutoRefersionProfile();
  if (!profile) return;

  stopAutoRefersionProgressPolling();
  await resetAutoRefersionBackend();

  const runToken = `${Date.now()}`;
  state.autoApplyRefersion.runToken = runToken;
  state.autoApplyRefersion.notifiedToken = "";
  state.autoApplyRefersion.lastResultSig = "";
  state.autoApplyRefersion.observedRunning = false;
  state.autoApplyRefersion.registrationEmail = String(profile.email || "").trim();
  state.autoApplyRefersion.lastFile = String(name || "");

  // Tự động mở Edge với debug port nếu chưa mở
  try {
    const browserRes = await fetch("/api/open-browser", { method: "POST" });
    browserRes.json().catch(() => ({}));
  } catch (_) { /* ignore */ }
  await new Promise(r => setTimeout(r, 2000));

  const cdpUrl = "http://127.0.0.1:9222";

  // Gọi start TRƯỚC khi mở modal polling — tránh đọc kết quả cũ từ lần chạy trước
  let totalLinks = 0;
  try {
    const res = await fetch("/api/auto-refersion/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        profile,
        auto_submit: true,
        use_cdp: true,
        cdp_url: cdpUrl,
        apply_mode: profile.apply_mode || "only_dat",
        row_start: profile.row_start || "1",
        row_end: profile.row_end || "",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      alert(`Lỗi (${res.status}): ${data.error || "Không bắt đầu được."}`);
      state.autoApplyRefersion.runToken = "";
      return;
    }
    totalLinks = data.total_links || 0;
    state.autoApplyRefersion.observedRunning = true;
  } catch (exc) {
    alert(`Lỗi kết nối: ${exc.message || exc}`);
    state.autoApplyRefersion.runToken = "";
    return;
  }

  // Tạo modal progress sau khi backend đã bắt đầu phiên mới
  const modal = createProgressModal({
    id: "ar_progress",
    title: `Auto Refersion - ${name}`,
    onStop: () => fetch("/api/auto-refersion/stop", { method: "POST" }),
    logsContainerId: "ar_logs_box",
    logsEndpoint: "/api/auto-refersion/status",
    pollIntervalMs: 1500,
  });
  state.autoApplyRefersion.reopenModal = () => modal.show(true);
  state.autoApplyRefersion.progressModal = modal;
  modal.show();
  appendLog("ar_logs_box", `Bắt đầu Auto Refersion (file: ${name})...`);
  const regEmail = String(profile.email || "").trim();
  if (regEmail) appendLog("ar_logs_box", `Email đăng ký: ${regEmail}`);
  appendLog("ar_logs_box", `Đã bắt đầu xử lý ${totalLinks} link...`);

  if (!state.pollTimer) {
    state.pollTimer = setInterval(pollStatus, POLL_MS);
  }
  await loadResults();
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

function getRefersionRegistrationEmail(source) {
  const r = source && typeof source === "object" ? source : {};
  const direct = String(r.email || r.registration_email || "").trim();
  if (direct) return direct;
  const submitted = Array.isArray(r.submitted_items) ? r.submitted_items : [];
  for (const it of submitted) {
    const em = String(it?.email || "").trim();
    if (em) return em;
  }
  const fromState = String(state.autoApplyRefersion.registrationEmail || "").trim();
  return fromState;
}

function formatRefersionResultHeader(source) {
  const email = getRefersionRegistrationEmail(source);
  return email ? `Email đăng ký: ${email}` : "";
}

function computeRefersionStats(source) {
  const r = source && typeof source === "object" ? source : {};
  const attempted = Array.isArray(r.attempted_items) ? r.attempted_items : [];
  const submittedItems = Array.isArray(r.submitted_items) ? r.submitted_items : [];
  const total = Number(r.total) || 0;
  const filled = Number(r.filled) || attempted.filter((it) => Number(it?.filled || 0) > 0).length;
  const submitted = Number(r.submitted) || submittedItems.length;
  const failed =
    Number(r.failed) ||
    attempted.filter((it) => !!it && (!!it.error || !!it.registration_error)).length;
  const skipped =
    Number(r.skipped) ||
    attempted.filter((it) => !!it && String(it.note || "") === "khong_dien_duoc_form").length;
  const submitFailed =
    Number(r.submit_failed) ||
    attempted.filter(
      (it) =>
        !!it &&
        Number(it.filled || 0) > 0 &&
        !it.submitted &&
        !it.error &&
        !it.registration_error
    ).length;
  return { total, filled, submitted, failed, skipped, submitFailed, cancelled: !!r.cancelled };
}

function formatRefersionSummary(source) {
  const s = computeRefersionStats(source);
  const parts = [
    `Tổng link: ${s.total}`,
    `Đã điền form: ${s.filled}`,
    `Submit OK: ${s.submitted}`,
  ];
  if (s.submitFailed > 0) parts.push(`Chưa submit: ${s.submitFailed}`);
  if (s.skipped > 0) parts.push(`Bỏ qua: ${s.skipped}`);
  if (s.failed > 0) parts.push(`Lỗi: ${s.failed}`);
  if (s.cancelled) parts.push("Đã hủy");
  return parts.join(" | ");
}

function refersionNoteLabel(noteRaw) {
  const note = String(noteRaw || "").trim();
  if (!note) return "";
  if (note === "submit_khong_thanh_cong") return "Đã điền form nhưng chưa submit được";
  if (note === "khong_dien_duoc_form") return "Không điền được ô nào trên form";
  if (note === "khong_auto_submit") return "Đã điền form (không bật auto submit)";
  return note;
}

function appendRefersionResultDetails(containerId, result) {
  const attempted = Array.isArray(result?.attempted_items) ? result.attempted_items : [];
  const submitted = Array.isArray(result?.submitted_items) ? result.submitted_items : [];
  const emailLine = formatRefersionResultHeader(result);
  if (emailLine) appendLog(containerId, emailLine);
  appendLog(containerId, formatRefersionSummary(result));
  if (submitted.length > 0) {
    appendLog(containerId, "");
    appendLog(containerId, `--- Submit OK (${submitted.length}) ---`);
    submitted.forEach((item, idx) => {
      appendLog(containerId, `  ${idx + 1}. ${item.brand || item.link || ""}`);
    });
  }
  const regErrors = attempted.filter((it) => !!it?.registration_error);
  if (regErrors.length > 0) {
    appendLog(containerId, "");
    appendLog(containerId, `--- Loi dang ky (${regErrors.length}) ---`);
    regErrors.forEach((item, idx) => {
      const brand = item.brand || item.link || "";
      const err = String(item.registration_error || "").slice(0, 100);
      appendLog(containerId, `  ${idx + 1}. ${brand}: ${err}`);
    });
  }
  const otherErrors = attempted.filter((it) => !!it?.error && !it?.registration_error);
  if (otherErrors.length > 0) {
    appendLog(containerId, "");
    appendLog(containerId, `--- Loi khac (${otherErrors.length}) ---`);
    otherErrors.forEach((item, idx) => {
      const brand = item.brand || item.link || "";
      appendLog(containerId, `  ${idx + 1}. ${brand}: ${String(item.error || "").slice(0, 100)}`);
    });
  }
  const notSubmitted = attempted.filter(
    (it) =>
      !!it &&
      Number(it.filled || 0) > 0 &&
      !it.submitted &&
      !it.error &&
      !it.registration_error
  );
  if (notSubmitted.length > 0) {
    appendLog(containerId, "");
    appendLog(containerId, `--- Da dien, chua submit (${notSubmitted.length}) ---`);
    notSubmitted.forEach((item, idx) => {
      const brand = item.brand || item.link || "";
      const note = refersionNoteLabel(item.note);
      appendLog(containerId, `  ${idx + 1}. ${brand}${note ? `: ${note}` : ""}`);
    });
  }
  const skipped = attempted.filter((it) => String(it?.note || "") === "khong_dien_duoc_form");
  if (skipped.length > 0) {
    appendLog(containerId, "");
    appendLog(containerId, `--- Bo qua (${skipped.length}) ---`);
    skipped.forEach((item, idx) => {
      appendLog(containerId, `  ${idx + 1}. ${item.brand || item.link || ""}`);
    });
  }
}

function readLocalRefersionHistory() {
  try {
    const raw = localStorage.getItem(LS_AUTO_REFERSION_HISTORY);
    const arr = JSON.parse(raw || "[]");
    return Array.isArray(arr) ? arr : [];
  } catch (_) {
    return [];
  }
}

function appendLocalRefersionHistory(entry) {
  const items = readLocalRefersionHistory();
  items.unshift(entry);
  localStorage.setItem(LS_AUTO_REFERSION_HISTORY, JSON.stringify(items.slice(0, 200)));
}

async function openApplyRefersionHistory(name) {
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

      // Tiếp tục xử lý các phần khác...
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

function applyRefersionTokenFromLicense(lic) {
  const token = String(lic?.refersion_token || "").trim();
  if (!token) return;
  const input = $("REFERSION_TOKEN");
  if (!input) return;
  if (String(input.value || "") === token) return;
  input.value = token;
}

async function openApplyRefersionHistory(name) {
  if (!isAutoApplyRefersionEnabled()) {
    alert("Auto Refersion đang tắt trên server.");
    return;
  }
  let modal = $("refersionHistoryModal");
  let box = $("refersionHistoryBox");
  let closeBtn = $("refersionHistoryCloseBtn");
  if (!modal || !box || !closeBtn) {
    modal = document.createElement("div");
    modal.className = "modal-backdrop hidden";
    modal.id = "refersionHistoryModal";
    modal.innerHTML = `
      <div class="modal-card" style="max-width:900px;">
        <h3>Lịch sử Apply Refersion</h3>
        <div id="refersionHistoryBox" class="log-box" style="max-height:60vh;overflow-y:auto;"></div>
        <div class="actions">
          <button class="btn" type="button" id="refersionHistoryCloseBtn">Đóng</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);
    box = $("refersionHistoryBox");
    closeBtn = $("refersionHistoryCloseBtn");
  }
  if (!modal || !box || !closeBtn) return;

  let items = [];
  let apiOk = false;
  try {
    const res = await fetch(`/api/auto-refersion/history?name=${encodeURIComponent(name || "")}`, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json().catch(() => ({}));
      items = Array.isArray(data.items) ? data.items : [];
      apiOk = true;
    }
  } catch (_) {}
  if (!apiOk) {
    const local = readLocalRefersionHistory();
    items = local.filter((it) => String((it || {}).file || "") === String(name || ""));
  }

  box.innerHTML = "";
  if (!items.length) {
    box.textContent = "Chưa có lịch sử apply Refersion cho file này.";
  } else {
    items.forEach((entry) => {
      const title = String(entry.started_at_display || entry.started_at || "").trim() || "(không rõ thời gian)";
      const regEmail = getRefersionRegistrationEmail(entry);
      const wrap = document.createElement("div");
      wrap.style.marginBottom = "20px";
      wrap.style.borderBottom = "1px solid #334155";
      wrap.style.paddingBottom = "12px";

      const head = document.createElement("div");
      head.textContent = title;
      head.style.fontSize = "16px";
      head.style.fontWeight = "700";
      head.style.marginBottom = "4px";
      head.style.color = "#60a5fa";
      wrap.appendChild(head);

      if (regEmail) {
        const emailEl = document.createElement("div");
        emailEl.textContent = `Email đăng ký: ${regEmail}`;
        emailEl.style.fontSize = "14px";
        emailEl.style.fontWeight = "600";
        emailEl.style.color = "#fbbf24";
        emailEl.style.marginBottom = "8px";
        wrap.appendChild(emailEl);
      }

      // Tổng kết
      const summary = document.createElement("div");
      summary.style.marginBottom = "8px";
      summary.style.color = "#94a3b8";
      summary.style.fontSize = "13px";
      summary.textContent = formatRefersionSummary(entry);
      wrap.appendChild(summary);

      const domainFromLink = (link) => {
        try {
          const u = new URL(String(link || ""));
          let h = String(u.host || "").toLowerCase();
          if (h.startsWith("www.")) h = h.slice(4);
          return h;
        } catch (_) {
          return String(link || "").slice(0, 60);
        }
      };

      // === ĐÃ SUBMIT THÀNH CÔNG ===
      const submitted = Array.isArray(entry.submitted_items) ? entry.submitted_items : [];
      if (submitted.length) {
        const okDiv = document.createElement("div");
        okDiv.style.marginBottom = "10px";

        const okHead = document.createElement("div");
        okHead.textContent = `✓ Thành công (${submitted.length})`;
        okHead.style.fontWeight = "700";
        okHead.style.color = "#4ade80";
        okHead.style.marginBottom = "6px";
        okDiv.appendChild(okHead);

        const okGrid = document.createElement("div");
        okGrid.style.display = "flex";
        okGrid.style.flexWrap = "wrap";
        okGrid.style.gap = "6px";
        submitted.forEach((it) => {
          const badge = document.createElement("span");
          const domain = String(it.brand || it.domain || "").trim() || domainFromLink(it.link);
          const msg = it.success_message ? ` — ${it.success_message}` : "";
          badge.textContent = domain + msg;
          badge.style.background = "rgba(6,78,59,0.2)";
          badge.style.border = "1px solid #14532d";
          badge.style.color = "#86efac";
          badge.style.borderRadius = "4px";
          badge.style.padding = "3px 8px";
          badge.style.fontSize = "12px";
          badge.style.maxWidth = "280px";
          badge.style.overflow = "hidden";
          badge.style.textOverflow = "ellipsis";
          badge.style.whiteSpace = "nowrap";
          okGrid.appendChild(badge);
        });
        okDiv.appendChild(okGrid);
        wrap.appendChild(okDiv);
      }

      // === LỖI SUBMIT ===
      const attempted = Array.isArray(entry.attempted_items) ? entry.attempted_items : [];
      const withErrors = attempted.filter((it) => !!it && !!it.registration_error);
      if (withErrors.length) {
        const errDiv = document.createElement("div");
        errDiv.style.marginBottom = "10px";

        const errHead = document.createElement("div");
        errHead.textContent = `✗ Lỗi đăng ký (${withErrors.length})`;
        errHead.style.fontWeight = "700";
        errHead.style.color = "#f87171";
        errHead.style.marginBottom = "6px";
        errDiv.appendChild(errHead);

        withErrors.forEach((it) => {
          const itemDiv = document.createElement("div");
          itemDiv.style.border = "1px solid #7f1d1d";
          itemDiv.style.borderRadius = "6px";
          itemDiv.style.padding = "8px 10px";
          itemDiv.style.marginBottom = "6px";
          itemDiv.style.background = "rgba(127,29,29,0.15)";

          const domainEl = document.createElement("div");
          domainEl.textContent = domainFromLink(it.link);
          domainEl.style.fontWeight = "600";
          domainEl.style.color = "#fca5a5";
          domainEl.style.marginBottom = "4px";
          domainEl.style.fontSize = "13px";
          itemDiv.appendChild(domainEl);

          const rawErr = String(it.registration_error || "");
          let errMsgs = [];
          if (rawErr.startsWith("Error|")) {
            errMsgs = rawErr.slice(6).split("|").map((s) => s.trim()).filter(Boolean);
          } else {
            errMsgs = [rawErr];
          }

          errMsgs.forEach((msg) => {
            const msgEl = document.createElement("div");
            msgEl.textContent = msg;
            msgEl.style.color = "#fca5a5";
            msgEl.style.fontSize = "12px";
            msgEl.style.paddingLeft = "8px";
            msgEl.style.borderLeft = "2px solid #f87171";
            msgEl.style.marginBottom = "3px";
            itemDiv.appendChild(msgEl);
          });

          errDiv.appendChild(itemDiv);
        });
        wrap.appendChild(errDiv);
      }

      // === LỖI KHÁC ===
      const withOtherErrors = attempted.filter((it) => !!it && !!it.error && !it.registration_error);
      if (withOtherErrors.length) {
        const oeDiv = document.createElement("div");
        oeDiv.style.marginBottom = "10px";

        const oeHead = document.createElement("div");
        oeHead.textContent = `✗ Lỗi khác (${withOtherErrors.length})`;
        oeHead.style.fontWeight = "700";
        oeHead.style.color = "#f87171";
        oeHead.style.marginBottom = "6px";
        oeDiv.appendChild(oeHead);

        withOtherErrors.forEach((it) => {
          const itemDiv = document.createElement("div");
          itemDiv.style.border = "1px solid #7f1d1d";
          itemDiv.style.borderRadius = "6px";
          itemDiv.style.padding = "8px 10px";
          itemDiv.style.marginBottom = "6px";
          itemDiv.style.background = "rgba(127,29,29,0.15)";

          const domainEl = document.createElement("div");
          domainEl.textContent = domainFromLink(it.link);
          domainEl.style.fontWeight = "600";
          domainEl.style.color = "#fca5a5";
          domainEl.style.marginBottom = "3px";
          domainEl.style.fontSize = "13px";
          itemDiv.appendChild(domainEl);

          const errEl = document.createElement("div");
          errEl.textContent = it.error || "Lỗi không rõ";
          errEl.style.color = "#fca5a5";
          errEl.style.fontSize = "12px";
          errEl.style.paddingLeft = "8px";
          errEl.style.borderLeft = "2px solid #f87171";
          itemDiv.appendChild(errEl);

          oeDiv.appendChild(itemDiv);
        });
        wrap.appendChild(oeDiv);
      }

      const notSubmitted = attempted.filter(
        (it) =>
          !!it &&
          Number(it.filled || 0) > 0 &&
          !it.submitted &&
          !it.error &&
          !it.registration_error
      );
      if (notSubmitted.length) {
        const nsDiv = document.createElement("div");
        nsDiv.style.marginBottom = "10px";
        const nsHead = document.createElement("div");
        nsHead.textContent = `⚠ Đã điền, chưa submit (${notSubmitted.length})`;
        nsHead.style.fontWeight = "700";
        nsHead.style.color = "#fbbf24";
        nsHead.style.marginBottom = "6px";
        nsDiv.appendChild(nsHead);
        notSubmitted.forEach((it) => {
          const row = document.createElement("div");
          row.textContent = `${domainFromLink(it.link)} — ${refersionNoteLabel(it.note) || "Chưa submit"}`;
          row.style.color = "#fcd34d";
          row.style.fontSize = "12px";
          row.style.marginBottom = "4px";
          nsDiv.appendChild(row);
        });
        wrap.appendChild(nsDiv);
      }

      const skipped = attempted.filter((it) => String(it?.note || "") === "khong_dien_duoc_form");
      if (skipped.length) {
        const skDiv = document.createElement("div");
        skDiv.style.marginBottom = "10px";
        const skHead = document.createElement("div");
        skHead.textContent = `○ Bỏ qua — không điền được form (${skipped.length})`;
        skHead.style.fontWeight = "700";
        skHead.style.color = "#94a3b8";
        skHead.style.marginBottom = "6px";
        skDiv.appendChild(skHead);
        skipped.forEach((it) => {
          const row = document.createElement("div");
          row.textContent = domainFromLink(it.link);
          row.style.color = "#94a3b8";
          row.style.fontSize = "12px";
          row.style.marginBottom = "4px";
          skDiv.appendChild(row);
        });
        wrap.appendChild(skDiv);
      }

      if (entry.error) {
        const errBanner = document.createElement("div");
        errBanner.style.color = "#f87171";
        errBanner.style.fontSize = "13px";
        errBanner.style.marginTop = "6px";
        errBanner.textContent = `Lỗi: ${entry.error}`;
        wrap.appendChild(errBanner);
      }

      box.appendChild(wrap);
    });
  }

  if (!apiOk) {
    const note = document.createElement("div");
    note.style.marginTop = "8px";
    note.style.color = "#9aa7bd";
    note.style.fontSize = "12px";
    note.textContent = "Đang dùng lịch sử local.";
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
  const onBackdrop = (e) => { if (e.target === modal) close(); };
  const onEsc = (e) => { if (e.key === "Escape") close(); };
  closeBtn.addEventListener("click", onClose);
  modal.addEventListener("click", onBackdrop);
  document.addEventListener("keydown", onEsc);
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
    applyRefersionTokenFromLicense(lic);
    applyLicenseSourceVisibility(lic);
    finishLicenseLoadingState();
    return lic;
  } catch (_) {
    const msg = $("licenseMessage");
    if (msg) msg.textContent = "Không đọc được trạng thái bản quyền.";
    // Nếu lỗi gọi server, mở full tab để không khóa người dùng.
    const fallbackLicense = { licensed: false, allowed_sources: [] };
    state.currentLicense = fallbackLicense;
    applyLicenseSourceVisibility(fallbackLicense);
    finishLicenseLoadingState();
  }
  return null;
}

async function refreshRefersionTokenFromServer() {
  const btn = $("refreshRefersionTokenBtn");
  if (btn) btn.disabled = true;
  try {
    const lic = await loadLicense();
    const token = String(lic?.refersion_token || "").trim();
    if (!token) {
      alert("Server chưa có Refersion token.");
      return;
    }
    const input = $("REFERSION_TOKEN");
    if (input) input.value = token;
  } catch (_) {
    alert("Không lấy được token mới nhất từ server.");
  } finally {
    if (btn) btn.disabled = false;
  }
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
  const [res, aa, ar] = await Promise.all([
    fetch("/api/results"),
    isAutoApplyCollabsEnabled() ? fetchAutoApplyStatus() : Promise.resolve({}),
    isAutoApplyRefersionEnabled() ? fetchAutoRefersionStatus() : Promise.resolve({}),
  ]);
  state.autoApply.lastRunning = isAutoApplyCollabsEnabled() ? !!aa?.running : false;
  state.autoApply.lastFile = isAutoApplyCollabsEnabled() ? String(aa?.file || "") : "";
  state.autoApplyRefersion.lastRunning = isAutoApplyRefersionEnabled() ? !!ar?.running : false;
  state.autoApplyRefersion.lastFile = isAutoApplyRefersionEnabled() ? String(ar?.file || "") : "";
  const data = await res.json();
  const list = $("resultFileList");
  list.innerHTML = "";
  (data.files || []).forEach((f) => {
    const isCollabs = /^collabs_/i.test(String(f.name || ""));
    const isRefersion = /^refersion_/i.test(String(f.name || ""));
    list.appendChild(buildResultLikeFileRow(f, aa, ar, isCollabs, isRefersion));
  });
}

function buildResultLikeFileRow(f, aa, ar, enableAutoApplyCollabs, enableAutoApplyRefersion) {
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

  // Nút Auto Apply cho Collabs
  if (isAutoApplyCollabsEnabled() && enableAutoApplyCollabs) {
    const isRunning = !!aa?.running;
    const sameFile = String(aa?.file || "") === String(f.name || "");
    const btnAutoApply = document.createElement("button");
    btnAutoApply.type = "button";
    btnAutoApply.className = "btn sm";
    if (isRunning && sameFile) {
      btnAutoApply.textContent = "Hủy";
      btnAutoApply.className = "btn sm danger";
      btnAutoApply.addEventListener("click", () => stopAutoApply());
    } else {
      btnAutoApply.textContent = "Auto Collabs";
      btnAutoApply.addEventListener("click", () => autoApplyFromResultFile(f.name));
    }
    btnAutoApply.disabled = isRunning && !sameFile;
    actions.appendChild(btnAutoApply);

    const btnHistory = document.createElement("button");
    btnHistory.type = "button";
    btnHistory.className = "btn sm";
    btnHistory.textContent = "Lịch sử Apply";
    btnHistory.addEventListener("click", () => openApplyHistory(f.name));
    actions.appendChild(btnHistory);
  }

  // Nút Auto Refersion cho file Refersion
  if (isAutoApplyRefersionEnabled() && enableAutoApplyRefersion) {
    const isRunning = !!ar?.running;
    const sameFile = String(ar?.file || "") === String(f.name || "");
    const btnAutoRefersion = document.createElement("button");
    btnAutoRefersion.type = "button";
    btnAutoRefersion.className = "btn sm";
    if (isRunning && sameFile) {
      btnAutoRefersion.textContent = "Hủy";
      btnAutoRefersion.className = "btn sm danger";
      btnAutoRefersion.addEventListener("click", () => stopAutoRefersion());
    } else {
      btnAutoRefersion.textContent = "Auto Refersion";
      btnAutoRefersion.addEventListener("click", () => {
        // Nếu popup đang đóng nhưng Auto Refersion còn chạy → mở lại popup log
        const existing = document.getElementById("ar_progress");
        if (existing && existing.classList.contains("hidden") && state.autoApplyRefersion.lastRunning) {
          if (state.autoApplyRefersion.reopenModal) state.autoApplyRefersion.reopenModal();
          return;
        }
        autoApplyRefersionFromResultFile(f.name);
      });
    }
    btnAutoRefersion.disabled = isRunning && !sameFile;
    actions.appendChild(btnAutoRefersion);

    // Nút Lịch sử Refersion
    const btnHist = document.createElement("button");
    btnHist.type = "button";
    btnHist.className = "btn sm";
    btnHist.textContent = "Lịch sử Apply";
    btnHist.addEventListener("click", () => openApplyRefersionHistory(f.name));
    actions.appendChild(btnHist);
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
  return row;
}

async function importAutoCollabsFile() {
  const input = $("autoCollabsFileInput");
  if (!input || !input.files || !input.files[0]) {
    alert("Chọn file .xlsx trước khi import.");
    return;
  }
  const form = new FormData();
  form.append("file", input.files[0]);
  const btn = $("importAutoCollabsBtn");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auto-collabs/import", {
      method: "POST",
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      alert(data.error || "Import file thất bại.");
      return;
    }
    input.value = "";
    syncAutoCollabsPickedFileUI();
    await loadAutoCollabsFiles();
    alert(`Import thành công: ${data.name}\nTổng link hợp lệ: ${data.total_links || 0}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function syncAutoCollabsPickedFileUI() {
  const input = $("autoCollabsFileInput");
  const nameEl = $("autoCollabsPickedName");
  if (!nameEl) return;
  const file = input && input.files && input.files[0] ? input.files[0] : null;
  if (!file) {
    nameEl.textContent = "Chưa chọn file nào";
    nameEl.classList.remove("is-picked");
    return;
  }
  nameEl.textContent = file.name || "Đã chọn 1 file";
  nameEl.classList.add("is-picked");
}

async function loadAutoCollabsFiles() {
  const [res, aa] = await Promise.all([
    fetch("/api/auto-collabs/files", { cache: "no-store" }),
    isAutoApplyCollabsEnabled() ? fetchAutoApplyStatus() : Promise.resolve({}),
  ]);
  const data = await res.json().catch(() => ({}));
  const list = $("autoCollabsFileList");
  if (!list) return;
  list.innerHTML = "";
  const files = Array.isArray(data.files) ? data.files : [];
  files.forEach((f) => list.appendChild(buildResultLikeFileRow(f, aa, true)));
}

async function downloadAutoCollabsTemplate() {
  const origin = window.location.origin || "";
  const url = `${origin}/api/auto-collabs/template?t=${Date.now()}`;
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-downloads allow-same-origin");
  iframe.style.cssText =
    "position:fixed;width:0;height:0;border:none;opacity:0;pointer-events:none;left:-9999px";
  iframe.src = url;
  document.body.appendChild(iframe);
  window.setTimeout(() => {
    try {
      iframe.remove();
    } catch (_) {}
  }, 120000);

  window.setTimeout(() => {
    const a = document.createElement("a");
    a.href = url;
    a.setAttribute("download", "auto-collabs-template.xlsx");
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, 200);
}

async function importAutoRefersionFile() {
  const input = $("autoRefersionFileInput");
  if (!input || !input.files || !input.files[0]) {
    alert("Chọn file .xlsx trước khi import.");
    return;
  }
  const form = new FormData();
  form.append("file", input.files[0]);
  const btn = $("importAutoRefersionBtn");
  if (btn) btn.disabled = true;
  try {
    const res = await fetch("/api/auto-refersion/import", {
      method: "POST",
      body: form,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      alert(data.error || "Import file thất bại.");
      return;
    }
    input.value = "";
    syncAutoRefersionPickedFileUI();
    await loadAutoRefersionFiles();
    alert(`Import thành công: ${data.name}\nTổng link hợp lệ: ${data.total_links || 0}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function syncAutoRefersionPickedFileUI() {
  const input = $("autoRefersionFileInput");
  const nameEl = $("autoRefersionPickedName");
  if (!nameEl) return;
  const file = input && input.files && input.files[0] ? input.files[0] : null;
  if (!file) {
    nameEl.textContent = "Chưa chọn file nào";
    nameEl.classList.remove("is-picked");
    return;
  }
  nameEl.textContent = file.name || "Đã chọn 1 file";
  nameEl.classList.add("is-picked");
}

const AR_FILES_PER_PAGE = 20;
let arFilesCurrentPage = 1;
let arFilesData = [];

async function loadAutoRefersionFiles() {
  const res = await fetch("/api/auto-refersion/files", { cache: "no-store" });
  const data = await res.json().catch(() => ({}));
  const list = $("autoRefersionFileList");
  if (!list) return;
  arFilesData = Array.isArray(data.files) ? data.files : [];
  arFilesCurrentPage = 1;
  renderArFilesPage(1);
}

function renderArFilesPage(page) {
  const list = $("autoRefersionFileList");
  const pager = $("autoRefersionFilePager");
  if (!list) return;

  const total = arFilesData.length;
  const totalPages = Math.max(1, Math.ceil(total / AR_FILES_PER_PAGE));
  const curPage = Math.min(Math.max(1, page), totalPages);
  arFilesCurrentPage = curPage;

  list.innerHTML = "";
  const start = (curPage - 1) * AR_FILES_PER_PAGE;
  const end = start + AR_FILES_PER_PAGE;
  const pageFiles = arFilesData.slice(start, end);

  if (!pageFiles.length && total === 0) {
    list.innerHTML = '<div style="color:#9aa7bd;padding:10px;">Chưa có file nào.</div>';
  } else {
    pageFiles.forEach((f) => list.appendChild(buildAutoRefersionFileRow(f)));
  }

  // Render pager
  if (!pager) return;
  pager.innerHTML = "";
  if (totalPages <= 1) return;

  const prevBtn = document.createElement("button");
  prevBtn.type = "button";
  prevBtn.className = "btn sm";
  prevBtn.textContent = "←";
  prevBtn.disabled = curPage <= 1;
  prevBtn.addEventListener("click", () => renderArFilesPage(curPage - 1));
  pager.appendChild(prevBtn);

  const pageInfo = document.createElement("span");
  pageInfo.textContent = `Trang ${curPage} / ${totalPages}`;
  pageInfo.style.margin = "0 10px";
  pageInfo.style.color = "#9aa7bd";
  pager.appendChild(pageInfo);

  const nextBtn = document.createElement("button");
  nextBtn.type = "button";
  nextBtn.className = "btn sm";
  nextBtn.textContent = "→";
  nextBtn.disabled = curPage >= totalPages;
  nextBtn.addEventListener("click", () => renderArFilesPage(curPage + 1));
  pager.appendChild(nextBtn);

  const totalInfo = document.createElement("span");
  totalInfo.textContent = ` (${total} file)`;
  totalInfo.style.marginLeft = "10px";
  totalInfo.style.color = "#9aa7bd";
  pager.appendChild(totalInfo);
}

function buildAutoRefersionFileRow(f) {
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
  btnAutoApply.textContent = "Auto Refersion";
  btnAutoApply.addEventListener("click", () => openAutoRefersionModal(f.name));
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
  return row;
}

async function downloadAutoRefersionTemplate() {
  const origin = window.location.origin || "";
  const url = `${origin}/api/auto-refersion/template?t=${Date.now()}`;
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-downloads allow-same-origin");
  iframe.style.cssText =
    "position:fixed;width:0;height:0;border:none;opacity:0;pointer-events:none;left:-9999px";
  iframe.src = url;
  document.body.appendChild(iframe);
  window.setTimeout(() => {
    try {
      iframe.remove();
    } catch (_) {}
  }, 120000);

  window.setTimeout(() => {
    const a = document.createElement("a");
    a.href = url;
    a.setAttribute("download", "auto-refersion-template.xlsx");
    a.rel = "noopener noreferrer";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, 200);
}

function collectAutoRefersionProfile() {
  const keep = (k, v) => localStorage.setItem(k, v || "");
  const read = (k) => {
    const fromLs = localStorage.getItem(k);
    if (fromLs != null && String(fromLs).trim() !== "") return fromLs;
    return AUTO_REFERSION_DEFAULTS[k] || "";
  };
  const modal = $("autoRefersionModal");
  const applyModeEl = $("ar_apply_mode");
  const rowStartEl = $("ar_row_start");
  const rowEndEl = $("ar_row_end");
  const firstNameEl = $("ar_first_name");
  const lastNameEl = $("ar_last_name");
  const emailEl = $("ar_email");
  const passwordEl = $("ar_password");
  const confirmPasswordEl = $("ar_confirm_password");
  const reasonEl = $("ar_reason");
  const businessNameEl = $("ar_business_name");
  const address1El = $("ar_address1");
  const address2El = $("ar_address2");
  const cityEl = $("ar_city");
  const stateEl = $("ar_state");
  const countryEl = $("ar_country");
  const zipEl = $("ar_zip");
  const postalCodeEl = $("ar_postal_code");
  const phoneEl = $("ar_phone");
  const phoneNumberEl = $("ar_phone_number");
  const instagramEl = $("ar_instagram");
  const tiktokEl = $("ar_tiktok");
  const websiteEl = $("ar_website");
  const facebookEl = $("ar_facebook");
  const socialLinksEl = $("ar_social_links");
  const affiliateTypeEl = $("ar_affiliate_type");
  const promoCodeEl = $("ar_promo_code");
  const channelUrlEl = $("ar_channel_url");
  const whyPromoteEl = $("ar_why_promote");
  const paypalEl = $("ar_paypal");
  const genericAnswerEl = $("ar_generic_answer");
  const accountModeEl = $("ar_account_mode");
  const multiEmailsEl = $("ar_multi_emails");
  const accountCountEl = $("ar_account_count");
  const btnCancel = $("ar_cancel_btn");
  const btnSave = $("ar_save_btn");
  const btnReset = $("ar_reset_btn");
  const btnConfirm = $("ar_confirm_btn");

  if (!modal) {
    alert("Thiếu popup Auto Refersion trong giao diện.");
    return Promise.resolve(null);
  }

  // Điền giá trị mặc định
  applyModeEl.value = read("ar_apply_mode") || "only_dat";
  rowStartEl.value = read("ar_row_start") || "1";
  rowEndEl.value = read("ar_row_end") || "";
  firstNameEl.value = read("ar_first_name");
  lastNameEl.value = read("ar_last_name");
  emailEl.value = read("ar_email");
  passwordEl.value = read("ar_password");
  confirmPasswordEl.value = read("ar_confirm_password");
  reasonEl.value = read("ar_reason") || "social influencer";
  businessNameEl.value = read("ar_business_name");
  address1El.value = read("ar_address1");
  address2El.value = read("ar_address2");
  cityEl.value = read("ar_city");
  stateEl.value = read("ar_state");
  countryEl.value = read("ar_country") || "United States";
  zipEl.value = read("ar_zip");
  postalCodeEl.value = read("ar_postal_code");
  phoneEl.value = read("ar_phone");
  phoneNumberEl.value = read("ar_phone_number");
  instagramEl.value = read("ar_instagram");
  tiktokEl.value = read("ar_tiktok");
  websiteEl.value = read("ar_website");
  facebookEl.value = read("ar_facebook");
  socialLinksEl.value = read("ar_social_links");
  affiliateTypeEl.value = read("ar_affiliate_type") || "Review Website";
  promoCodeEl.value = read("ar_promo_code");
  channelUrlEl.value = read("ar_channel_url");
  whyPromoteEl.value = read("ar_why_promote");
  paypalEl.value = read("ar_paypal");
  genericAnswerEl.value = read("ar_generic_answer");

  modal.classList.remove("hidden");
  window.setTimeout(() => firstNameEl.focus(), 0);

  return new Promise((resolve) => {
    let done = false;
    const cleanup = () => {
      modal.classList.add("hidden");
      btnCancel.removeEventListener("click", onCancel);
      btnSave.removeEventListener("click", onSave);
      btnReset.removeEventListener("click", onReset);
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
      keep("ar_apply_mode", applyModeEl.value);
      keep("ar_row_start", rowStartEl.value);
      keep("ar_row_end", rowEndEl.value);
      keep("ar_first_name", firstNameEl.value);
      keep("ar_last_name", lastNameEl.value);
      keep("ar_email", emailEl.value);
      keep("ar_password", passwordEl.value);
      keep("ar_confirm_password", confirmPasswordEl.value);
      keep("ar_reason", reasonEl.value);
      keep("ar_business_name", businessNameEl.value);
      keep("ar_address1", address1El.value);
      keep("ar_address2", address2El.value);
      keep("ar_city", cityEl.value);
      keep("ar_state", stateEl.value);
      keep("ar_country", countryEl.value);
      keep("ar_zip", zipEl.value);
      keep("ar_postal_code", postalCodeEl.value);
      keep("ar_phone", phoneEl.value);
      keep("ar_phone_number", phoneNumberEl.value);
      keep("ar_instagram", instagramEl.value);
      keep("ar_tiktok", tiktokEl.value);
      keep("ar_website", websiteEl.value);
      keep("ar_facebook", facebookEl.value);
      keep("ar_social_links", socialLinksEl.value);
      keep("ar_affiliate_type", affiliateTypeEl.value);
      keep("ar_promo_code", promoCodeEl.value);
      keep("ar_channel_url", channelUrlEl.value);
      keep("ar_why_promote", whyPromoteEl.value);
      keep("ar_paypal", paypalEl.value);
      keep("ar_generic_answer", genericAnswerEl.value);
    };

    const onSave = () => {
      persistFormToLocalStorage();
      alert("Đã lưu mẫu đăng ký.");
    };
    const onConfirm = () => {
      persistFormToLocalStorage();
      const email = String(emailEl.value || "").trim();
      if (!email) {
        alert("Vui lòng nhập Email.");
        return;
      }
      const password = String(passwordEl.value || "").trim();
      if (!password) {
        alert("Vui lòng nhập Password.");
        return;
      }
      const confirmPassword = String(confirmPasswordEl.value || "").trim();
      if (password !== confirmPassword) {
        alert("Password và Confirm Password không khớp.");
        return;
      }
      // Parse thông tin đa tài khoản từ textarea
      const accountMode = accountModeEl ? String(accountModeEl.value || "single").trim() : "single";
      let multi_accounts = null;
      let browser_count = 1;
      if (accountMode === "multi" && multiEmailsEl) {
        const raw = String(multiEmailsEl.value || "").trim();
        if (raw) {
          multi_accounts = {};
          raw.split("\n").forEach((line) => {
            const lineTrim = line.trim();
            if (!lineTrim) return;
            const parts = lineTrim.split("=");
            if (parts.length < 2) return;
            const numStr = parts[0].trim();
            const num = parseInt(numStr, 10);
            if (isNaN(num)) return;
            const fields = parts.slice(1).join("=").split("|").map((f) => f.trim());
            multi_accounts[num] = {
              email: fields[0] || "",
              first_name: fields[1] || "",
              last_name: fields[2] || "",
              website: fields[3] || "",
              instagram: fields[4] || "",
              paypal: fields[5] || "",
            };
          });
          browser_count = Object.keys(multi_accounts).length;
        }
      }

      const profile = {
        apply_mode: String(applyModeEl.value || "only_dat").trim(),
        row_start: String(rowStartEl.value || "1").trim() || "1",
        row_end: String(rowEndEl.value || "").trim(),
        account_count: accountCountEl ? String(accountCountEl.value || "1-2").trim() : "1-2",
        account_mode: accountMode,
        multi_accounts,
        browser_count,
        first_name: String(firstNameEl.value || "").trim(),
        last_name: String(lastNameEl.value || "").trim(),
        email,
        password,
        confirm_password: confirmPassword,
        reason: String(reasonEl.value || "").trim(),
        business_name: String(businessNameEl.value || "").trim(),
        address1: String(address1El.value || "").trim(),
        address2: String(address2El.value || "").trim(),
        city: String(cityEl.value || "").trim(),
        state: String(stateEl.value || "").trim(),
        country: String(countryEl.value || "United States").trim(),
        zip: String(zipEl.value || "").trim(),
        postal_code: String(postalCodeEl.value || "").trim(),
        phone: String(phoneEl.value || "").trim(),
        phone_number: String(phoneNumberEl.value || "").trim(),
        instagram: String(instagramEl.value || "").trim(),
        tiktok: String(tiktokEl.value || "").trim(),
        website: String(websiteEl.value || "").trim(),
        facebook: String(facebookEl.value || "").trim(),
        social_links: String(socialLinksEl.value || "").trim(),
        affiliate_type: String(affiliateTypeEl.value || "Review Website").trim(),
        promo_code: String(promoCodeEl.value || "").trim(),
        channel_url: String(channelUrlEl.value || "").trim(),
        why_promote: String(whyPromoteEl.value || "").trim(),
        paypal: String(paypalEl.value || "").trim(),
        generic_answer: String(genericAnswerEl.value || "").trim(),
      };
      finish(profile);
    };
    const onReset = async () => {
      try {
        await fetch("/api/auto-refersion/reset", { method: "POST" });
        alert("Đã reset trạng thái Auto Refersion. Có thể chạy lại được.");
      } catch (e) { alert("Lỗi reset: " + e.message); }
    };
    btnCancel.addEventListener("click", onCancel);
    btnSave.addEventListener("click", onSave);
    btnReset.addEventListener("click", onReset);
    btnConfirm.addEventListener("click", onConfirm);
  });
}

async function openAutoRefersionModal(fileName) {
  const profile = await collectAutoRefersionProfile();
  if (!profile) return;
  runAutoRefersion(profile, fileName);
}

async function runAutoRefersion(profile, fileName) {
  if (!isAutoApplyRefersionEnabled()) {
    alert("Auto Refersion đang tắt trên server.");
    return;
  }

  stopAutoRefersionProgressPolling();
  await resetAutoRefersionBackend();

  const runToken = `${Date.now()}`;
  state.autoApplyRefersion.runToken = runToken;
  state.autoApplyRefersion.notifiedToken = "";
  state.autoApplyRefersion.lastResultSig = "";
  state.autoApplyRefersion.observedRunning = false;
  state.autoApplyRefersion.registrationEmail = String(profile.email || "").trim();
  state.autoApplyRefersion.lastFile = String(fileName || "");

  // Tự động mở Edge với debug port nếu chưa mở
  try {
    const browserRes = await fetch("/api/open-browser", { method: "POST" });
    const browserData = await browserRes.json().catch(() => ({}));
    if (!browserData.ok) {
      alert("Cảnh báo: " + (browserData.error || "Không mở được Edge. Mở thủ công: msedge.exe --remote-debugging-port=9222"));
    }
  } catch (_) {
    alert("Lỗi: Không gọi được API mở browser.");
  }
  await new Promise(r => setTimeout(r, 2000));

  const cdpUrl = "http://127.0.0.1:9222";

  let totalLinks = 0;
  try {
    const res = await fetch("/api/auto-refersion/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: fileName,
        profile,
        auto_submit: true,
        use_cdp: true,
        cdp_url: cdpUrl,
        apply_mode: profile.apply_mode || "only_dat",
        row_start: profile.row_start || "1",
        row_end: profile.row_end || "",
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      const errMsg = data.error || `HTTP ${res.status}`;
      alert(`Lỗi (${res.status}): ${errMsg}`);
      state.autoApplyRefersion.runToken = "";
      return;
    }
    totalLinks = data.total_links || 0;
    state.autoApplyRefersion.observedRunning = true;
  } catch (exc) {
    alert(`Lỗi kết nối: ${exc.message || exc}`);
    state.autoApplyRefersion.runToken = "";
    return;
  }

  const modal = createProgressModal({
    id: "ar_progress",
    title: `Auto Refersion - ${fileName}`,
    onStop: () => fetch("/api/auto-refersion/stop", { method: "POST" }),
    logsContainerId: "ar_logs_box",
    logsEndpoint: "/api/auto-refersion/status",
    pollIntervalMs: 1500,
  });
  state.autoApplyRefersion.reopenModal = () => modal.show(true);
  state.autoApplyRefersion.progressModal = modal;
  modal.show();
  appendLog("ar_logs_box", `Bắt đầu Auto Refersion (file: ${fileName})...`);
  const regEmail = String(profile.email || "").trim();
  if (regEmail) appendLog("ar_logs_box", `Email đăng ký: ${regEmail}`);
  appendLog("ar_logs_box", `Đã bắt đầu xử lý ${totalLinks} link...`);

  if (!state.pollTimer) {
    state.pollTimer = setInterval(pollStatus, POLL_MS);
  }
  await loadResults();
}

function createProgressModal({ id, title, onStop, logsContainerId, logsEndpoint, pollIntervalMs = 1500 }) {
  let pollTimer = null;
  let hidden = true;
  let seenRunning = false;
  let lastLogIdx = 0;
  let completionHandled = false;

  // Tạo / reuse overlay (không xoá khi ẩn — giữ lại để mở lại được)
  let overlay = document.getElementById(id);
  if (!overlay) {
    overlay = document.createElement("div");
    overlay.className = "modal-backdrop";
    overlay.id = id;
    document.body.appendChild(overlay);
  }
  overlay.innerHTML = `
    <div class="modal-card" style="max-width:700px;max-height:80vh;overflow:hidden;display:flex;flex-direction:column;">
      <div style="display:flex;align-items:center;justify-content:space-between;padding-bottom:10px;border-bottom:1px solid #e2e8f0;">
        <h3 style="margin:0;">${title}</h3>
        <button class="btn danger" id="${id}_stop_btn" type="button">Dừng lại</button>
      </div>
      <div id="${logsContainerId}" class="log-box" style="flex:1;overflow-y:auto;margin:10px 0;padding:10px;background:#1e293b;color:#e2e8f0;border-radius:6px;font-family:monospace;font-size:12px;min-height:200px;max-height:400px;"></div>
      <div style="display:flex;justify-content:flex-end;padding-top:10px;border-top:1px solid #e2e8f0;">
        <button class="btn" id="${id}_close_btn" type="button">Đóng</button>
      </div>
    </div>
  `;
  document.getElementById(`${id}_stop_btn`).addEventListener("click", () => {
    if (onStop) onStop();
    appendLog(logsContainerId, "Đang dừng...");
  });
  document.getElementById(`${id}_close_btn`).addEventListener("click", () => {
    hide();
  });
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) hide();
  });

  function show(resume = false) {
    overlay.classList.remove("hidden");
    hidden = false;
    startPolling(resume);
  }
  function hide() {
    overlay.classList.add("hidden");
    hidden = true;
    stopPolling();
  }
  function startPolling(resume = false) {
    stopPolling();
    if (!resume) {
      seenRunning = false;
      lastLogIdx = 0;
      completionHandled = false;
      const logsBox = document.getElementById(logsContainerId);
      if (logsBox) logsBox.textContent = "";
    } else {
      seenRunning = !!state.autoApplyRefersion.observedRunning;
      lastLogIdx = 0;
      completionHandled = false;
      const logsBox = document.getElementById(logsContainerId);
      if (logsBox) logsBox.textContent = "";
    }
    pollTimer = setInterval(async () => {
      if (hidden) { stopPolling(); return; }
      try {
        const res = await fetch(logsEndpoint, { cache: "no-store" });
        const data = await res.json().catch(() => ({}));
        const logs = Array.isArray(data.logs) ? data.logs : [];
        const result = data.result;
        const running = !!data.running;
        if (running) seenRunning = true;
        const box = document.getElementById(logsContainerId);
        if (box && logs.length > lastLogIdx) {
          for (let i = lastLogIdx; i < logs.length; i++) {
            appendLogRaw(logsContainerId, logs[i]);
          }
          lastLogIdx = logs.length;
        }
        // Chỉ kết thúc khi phiên hiện tại đã từng chạy (tránh kết quả cũ lần trước)
        if (seenRunning && result && !running && !completionHandled) {
          completionHandled = true;
          stopPolling();
          appendLog(logsContainerId, "");
          appendLog(logsContainerId, result.cancelled ? "=== DA HUY ===" : "=== HOAN TAT ===");
          appendRefersionResultDetails(logsContainerId, result);
        }
      } catch (_) {}
    }, pollIntervalMs);
    overlay.dataset.pollTimerId = String(pollTimer);
  }
  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (overlay.dataset.pollTimerId) {
      clearInterval(Number(overlay.dataset.pollTimerId));
      overlay.dataset.pollTimerId = "";
    }
  }

  return { show, hide, startPolling, stopPolling };
}

function appendLogRaw(containerId, msg) {
  const box = document.getElementById(containerId);
  if (!box) return;
  const line = document.createElement("div");
  const text = String(msg || "");
  line.textContent = /^\[\d{1,2}:\d{2}:\d{2}\]/.test(text) ? text : `[${new Date().toLocaleTimeString()}] ${text}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function appendLog(containerId, msg) {
  const box = document.getElementById(containerId);
  if (!box) return;
  const line = document.createElement("div");
  line.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function bindEvents() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab, true));
  });
  const reloadBtn = $("reloadAppBtn");
  if (reloadBtn) {
    reloadBtn.addEventListener("click", (e) => {
      try {
        e.preventDefault();
        e.stopPropagation();
      } catch (_) {}
      try {
        const url = new URL(window.location.href);
        url.searchParams.set("_reload", String(Date.now()));
        window.location.replace(url.toString());
      } catch (_) {
        window.location.reload();
      }
    });
  }
  bindMultiSelectDropdowns();
  bindSecretEyeButtons();
  const aaAccMode = $("aa_account_mode");
  if (aaAccMode) aaAccMode.addEventListener("change", syncAutoApplyAccountModeUI);
  const cbMode = $("collabsDiscoveryMode");
  if (cbMode) cbMode.addEventListener("change", updateCollabsDiscoveryModeUI);
  updateCollabsDiscoveryModeUI();
  const endPageCb = $("endPageCb");
  if (endPageCb) endPageCb.addEventListener("change", persistEndPageCollabs);
  if (endPageCb) endPageCb.addEventListener("blur", persistEndPageCollabs);
  $("saveSettingsBtn").addEventListener("click", saveSettings);
  $("runBtnUppromote").addEventListener("click", () => runFilter("uppromote"));
  $("runBtnGoaffpro").addEventListener("click", () => runFilter("goaffpro"));
  $("runBtnRefersion").addEventListener("click", () => runFilter("refersion"));
  $("runBtnCollabs").addEventListener("click", () => runFilter("collabs"));

  const resetOutsideBtn = $("resetOutsideStateBtn");
  if (resetOutsideBtn) resetOutsideBtn.addEventListener("click", resetCollabsOutsideState);
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
  const importAutoCollabsBtn = $("importAutoCollabsBtn");
  if (importAutoCollabsBtn) importAutoCollabsBtn.addEventListener("click", importAutoCollabsFile);
  const refreshAutoCollabsBtn = $("refreshAutoCollabsBtn");
  if (refreshAutoCollabsBtn) refreshAutoCollabsBtn.addEventListener("click", loadAutoCollabsFiles);
  const autoCollabsFileInput = $("autoCollabsFileInput");
  if (autoCollabsFileInput) autoCollabsFileInput.addEventListener("change", syncAutoCollabsPickedFileUI);
  const downloadAutoCollabsTemplateBtn = $("downloadAutoCollabsTemplateBtn");
  if (downloadAutoCollabsTemplateBtn) {
    downloadAutoCollabsTemplateBtn.addEventListener("click", (e) => {
      try {
        e.preventDefault();
        e.stopPropagation();
      } catch (_) {}
      downloadAutoCollabsTemplate();
    });
  }
  const importAutoRefersionBtn = $("importAutoRefersionBtn");
  if (importAutoRefersionBtn) importAutoRefersionBtn.addEventListener("click", importAutoRefersionFile);
  const refreshAutoRefersionBtn = $("refreshAutoRefersionBtn");
  if (refreshAutoRefersionBtn) refreshAutoRefersionBtn.addEventListener("click", loadAutoRefersionFiles);
  const autoRefersionFileInput = $("autoRefersionFileInput");
  if (autoRefersionFileInput) autoRefersionFileInput.addEventListener("change", syncAutoRefersionPickedFileUI);
  const downloadAutoRefersionTemplateBtn = $("downloadAutoRefersionTemplateBtn");
  if (downloadAutoRefersionTemplateBtn) {
    downloadAutoRefersionTemplateBtn.addEventListener("click", (e) => {
      try {
        e.preventDefault();
        e.stopPropagation();
      } catch (_) {}
      downloadAutoRefersionTemplate();
    });
  }
  document.querySelectorAll(".open-edge-cdp-btn").forEach((edgeBtn) => {
    edgeBtn.addEventListener("click", (e) => {
      try {
        e.preventDefault();
        e.stopPropagation();
      } catch (_) {}
      showEdgeCdpAccountPicker();
    });
  });
  const edgeCdpModal = $("edgeCdpAccountsModal");
  if (edgeCdpModal) {
    edgeCdpModal.addEventListener("click", (e) => {
      if (e.target === edgeCdpModal) closeEdgeCdpAccountPicker();
    });
  }
  const edgeCdpCancel = $("edgeCdpAccountsCancelBtn");
  if (edgeCdpCancel) edgeCdpCancel.addEventListener("click", closeEdgeCdpAccountPicker);
  const edgeCdpOpen = $("edgeCdpAccountsOpenBtn");
  if (edgeCdpOpen) edgeCdpOpen.addEventListener("click", submitOpenEdgeCdpAccounts);
  const actLic = $("activateLicenseBtn");
  if (actLic) actLic.addEventListener("click", activateLicense);
  const deLic = $("deactivateLicenseBtn");
  if (deLic) deLic.addEventListener("click", deactivateLicense);
  const refreshRfTokenBtn = $("refreshRefersionTokenBtn");
  if (refreshRfTokenBtn) refreshRfTokenBtn.addEventListener("click", refreshRefersionTokenFromServer);
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
  syncAutoApplyAccountModeUI();
}

async function init() {
  bindEvents();
  loadPersistedEndPage();
  await loadSettings();
  await loadLicense();
  await loadResults();
  await loadAutoCollabsFiles();
  await loadAutoRefersionFiles();
  await pollStatus();
  requestNotificationPermission();
}

function requestNotificationPermission() {
  if (!("Notification" in window)) return;
  if (Notification.permission === "granted") return;
  if (Notification.permission === "denied") return;
  Notification.requestPermission();
}

function sendBrowserNotification(title, body, onClick) {
  if (!("Notification" in window)) return;
  if (Notification.permission !== "granted") return;
  const n = new Notification(title, {
    body,
    icon: "/static/icon.png",
    badge: "/static/icon.png",
    requireInteraction: false,
    silent: false,
  });
  n.onclick = () => {
    window.focus();
    n.close();
    if (onClick) onClick();
  };
  setTimeout(() => n.close(), 15000);
}

init();

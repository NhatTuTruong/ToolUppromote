import { spawn } from "node:child_process";

const FEED_URL = "https://marketplace.refersion.com/feed";
const HOST = "127.0.0.1";
const PORT = Number(process.env.REFERSION_EDGE_CDP_PORT || "9222");
const USER_DATA_DIR = process.env.REFERSION_EDGE_USER_DATA_DIR || "C:\\edge-cdp";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url, timeoutMs = 5000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal, cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

function edgeCandidates() {
  const pf86 = process.env["ProgramFiles(x86)"] || "C:\\Program Files (x86)";
  const pf = process.env["ProgramFiles"] || "C:\\Program Files";
  return [
    `${pf86}\\Microsoft\\Edge\\Application\\msedge.exe`,
    `${pf}\\Microsoft\\Edge\\Application\\msedge.exe`,
  ];
}

function startEdge(edgeExe) {
  const args = [
    `--remote-debugging-port=${PORT}`,
    `--user-data-dir=${USER_DATA_DIR}`,
    "--no-first-run",
    "--no-default-browser-check",
    FEED_URL,
  ];
  const cp = spawn(edgeExe, args, {
    detached: true,
    stdio: "ignore",
    windowsHide: false,
  });
  cp.unref();
}

async function ensureEdgeCdp() {
  for (let i = 0; i < 2; i += 1) {
    try {
      await fetchJson(`http://${HOST}:${PORT}/json/version`, 1500);
      return;
    } catch (_) {
      // continue
    }
    const candidates = edgeCandidates();
    for (const exe of candidates) {
      try {
        startEdge(exe);
        break;
      } catch (_) {
        // try next
      }
    }
    await sleep(1800);
  }
  // final wait window
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      await fetchJson(`http://${HOST}:${PORT}/json/version`, 1500);
      return;
    } catch (_) {
      await sleep(500);
    }
  }
  throw new Error(`Không mở được Edge CDP tại ${HOST}:${PORT}`);
}

async function openTargetWs() {
  try {
    const created = await fetchJson(`http://${HOST}:${PORT}/json/new?${encodeURIComponent(FEED_URL)}`, 6000);
    if (created && created.webSocketDebuggerUrl) return String(created.webSocketDebuggerUrl);
  } catch (_) {
    // fallback list
  }
  const list = await fetchJson(`http://${HOST}:${PORT}/json/list`, 6000);
  if (!Array.isArray(list)) throw new Error("Không đọc được danh sách target CDP.");
  const page = list.find((x) => x && x.type === "page" && x.webSocketDebuggerUrl) || list.find((x) => x && x.webSocketDebuggerUrl);
  if (!page) throw new Error("Không có target page trong CDP.");
  return String(page.webSocketDebuggerUrl);
}

async function runCdp(wsUrl) {
  return await new Promise((resolve, reject) => {
    const ws = new WebSocket(wsUrl);
    let id = 0;
    const pending = new Map();
    const timeout = setTimeout(() => {
      try { ws.close(); } catch (_) {}
      reject(new Error("Timeout chờ token từ Edge CDP."));
    }, 60000);

    function send(method, params = {}, awaitPromise = false) {
      const reqId = ++id;
      const payload = { id: reqId, method, params };
      ws.send(JSON.stringify(payload));
      return new Promise((res, rej) => {
        pending.set(reqId, { res, rej, method, awaitPromise });
      });
    }

    ws.onmessage = async (ev) => {
      try {
        const msg = JSON.parse(String(ev.data || "{}"));
        if (msg.id && pending.has(msg.id)) {
          const p = pending.get(msg.id);
          pending.delete(msg.id);
          if (msg.error) p.rej(new Error(msg.error.message || "CDP error"));
          else p.res(msg.result || {});
          return;
        }
      } catch (_) {
        // ignore
      }
    };

    ws.onerror = () => {
      clearTimeout(timeout);
      reject(new Error("WebSocket CDP lỗi kết nối."));
    };

    ws.onopen = async () => {
      try {
        await send("Page.enable");
        await send("Runtime.enable");
        await send("Network.enable");
        await send("Page.navigate", { url: FEED_URL });
        await sleep(2200);
        const evalRes = await send("Runtime.evaluate", {
          expression:
            "fetch('/feed',{credentials:'include',cache:'no-store'}).then(r=>r.headers.get('refersion-token')||r.headers.get('Refersion-Token')||'')",
          awaitPromise: true,
          returnByValue: true,
        });
        const token = String(evalRes?.result?.value || "").trim();
        clearTimeout(timeout);
        try { ws.close(); } catch (_) {}
        if (!token) return reject(new Error("Không đọc được refersion-token. Hãy login Refersion trong profile Edge CDP."));
        resolve(token);
      } catch (e) {
        clearTimeout(timeout);
        try { ws.close(); } catch (_) {}
        reject(e);
      }
    };
  });
}

async function main() {
  try {
    await ensureEdgeCdp();
    const ws = await openTargetWs();
    const token = await runCdp(ws);
    process.stdout.write(JSON.stringify({ ok: true, token }));
  } catch (e) {
    process.stdout.write(JSON.stringify({ ok: false, error: String(e?.message || e) }));
    process.exit(1);
  }
}

main();


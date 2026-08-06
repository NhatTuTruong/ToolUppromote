# -*- coding: utf-8 -*-
"""
Extract fresh Uppromote tokens from Edge browser (via CDP/Playwright),
then update .env with new tokens.

This solves the token expiry problem: instead of needing manual refresh,
the script grabs the live tokens from the user's already-logged-in browser.

Run: $env:PYTHONIOENCODING="utf-8"; python -X utf8 grab_uppromote_token.py
"""
from __future__ import annotations

import base64, json, os, re, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_cdp import ensure_edge_cdp_running

CDP_URL = "http://127.0.0.1:9222"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
UDIR = r"C:\edge-cdp"
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

def log(msg: str) -> None:
    print(msg, flush=True)

def load_env(path: str) -> dict:
    env = {}
    if not os.path.isfile(path):
        return env
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip()
    return env

def save_env(path: str, env: dict) -> None:
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue
        k = stripped.split("=", 1)[0].strip()
        if k in env:
            new_lines.append(f'{k}="{env[k]}"\n')
        else:
            new_lines.append(line)
    for k, v in env.items():
        found = any(
            l.strip().startswith(k + "=") or l.strip().startswith(k + " =")
            for l in lines
        )
        if not found:
            new_lines.append(f'{k}="{v}"\n')
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

def decode_jwt_payload(token: str) -> dict | None:
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        p = parts[1].replace("-", "+").replace("_", "/")
        padded = p + "=" * (-len(p) % 4)
        return json.loads(base64.b64decode(padded, validate=True))
    except Exception:
        return None

def jwt_exp_info(token: str) -> str:
    payload = decode_jwt_payload(token)
    if not payload:
        return "unknown payload"
    exp = payload.get("exp")
    if exp:
        now = time.time()
        if exp > now:
            remaining = int(exp - now)
            return f"con {remaining//3600}h {remaining%3600//60}m"
        else:
            return f"da het han {int(now - exp)//3600}h truoc"
    return "khong co exp"

# ------------------------------------------------------------------
# 1. Ensure Edge CDP running
# ------------------------------------------------------------------
log("[1] Khoi dong Edge CDP...")
ok = ensure_edge_cdp_running(
    port=9222, user_data_dir=UDIR, edge_exe=EDGE_EXE,
    log=log, wait_sec=15.0,
)
if not ok:
    log("ERROR: Khong mo duoc Edge CDP.")
    sys.exit(1)

# ------------------------------------------------------------------
# 2. Connect Playwright and extract tokens
# ------------------------------------------------------------------
log("\n[2] Ket noi trinh duyet de lay token...")

from playwright.sync_api import sync_playwright

tokens_found: dict[str, str] = {}

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP_URL)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()

    # Navigate to marketplace to trigger token creation
    try:
        log("    Truy cap marketplace.uppromote.com...")
        page.goto(
            "https://marketplace.uppromote.com/offers/find-offers",
            wait_until="load",
            timeout=30000,
        )
        time.sleep(5)
        log(f"    URL: {page.url}")
    except Exception as e:
        log(f"    Loi truy cap: {e}")

    # Get ALL cookies from the browser
    log("\n[3] Doc tat ca cookies...")
    all_cookies = context.cookies()
    log(f"    Tong so cookies: {len(all_cookies)}")

    for c in all_cookies:
        domain = c["domain"]
        name = c["name"]
        value = c["value"]

        # Chỉ lấy cookies của Uppromote
        if not any(x in domain for x in ["uppromote", "marketplace"]):
            continue

        # Các token quan trọng
        if name in ("marketplace_access_token", "marketplace_refresh_token"):
            tokens_found[name] = value
            log(f"    [{name}]")
            log(f"      Domain: {domain}")
            log(f"      Expires: {c.get('expires', 'session')}")
            log(f"      Token: {jwt_exp_info(value)}")
            log(f"      Value: {value[:60]}...")

        # Session tokens có thể là JWT
        elif name in ("uppromote_session", "XSRF-TOKEN"):
            if value.count(".") == 2 or value.startswith("eyJ"):
                tokens_found[name] = value
                log(f"    [{name}] (JWT): {jwt_exp_info(value)}")
                log(f"      Value: {value[:60]}...")

    # Check localStorage / sessionStorage
    log("\n[4] Doc storage cua trinh duyet...")
    try:
        stores = page.evaluate("""() => {
            const r = {};
            for (const sk of ['localStorage', 'sessionStorage']) {
                r[sk] = {};
                try {
                    const s = window[sk];
                    for (let i = 0; i < s.length; i++) {
                        const key = s.key(i);
                        try { r[sk][key] = s.getItem(key); } catch(e) {}
                    }
                } catch(e) {}
            }
            return r;
        }""")

        for stype, items in stores.items():
            for k, v in items.items():
                if not isinstance(v, str):
                    continue
                # Check for JWT
                if v.count(".") == 2 and len(v) > 50:
                    payload = decode_jwt_payload(v)
                    if payload and payload.get("aud") == "2":
                        tokens_found[f"ls_{k}"] = v
                        log(f"    [localStorage.{k}] JWT: {jwt_exp_info(v)}")
                        log(f"      sub={payload.get('sub')}, aud={payload.get('aud')}")
    except Exception as e:
        log(f"    Loi doc storage: {e}")

    # Also check app.uppromote.com
    try:
        log("\n[5] Kiem tra app.uppromote.com...")
        page.goto("https://app.uppromote.com/", wait_until="load", timeout=20000)
        time.sleep(3)
        app_cookies = context.cookies()
        for c in app_cookies:
            domain = c["domain"]
            name = c["name"]
            value = c["value"]
            if not any(x in domain for x in ["uppromote"]):
                continue
            if name in ("uppromote_session", "marketplace_access_token", "marketplace_refresh_token"):
                if name not in tokens_found or len(value) > len(tokens_found.get(name, "")):
                    tokens_found[name] = value
                    log(f"    [app.{name}]: {jwt_exp_info(value)}")
    except Exception as e:
        log(f"    Loi: {e}")

    browser.close()

# ------------------------------------------------------------------
# 3. Show results
# ------------------------------------------------------------------
log("\n[6] === KET QUA ===")
if not tokens_found:
    log("    KHONG TIM THAY TOKEN!")
    log("    Dam bao da dang nhap Uppromote trong trinh duyet Edge.")
    log("    Neu chua, mo trinh duyet Edge CDP, dang nhap tai:")
    log("    https://marketplace.uppromote.com/login")
    sys.exit(1)

for name, token in tokens_found.items():
    log(f"\n  {name}:")
    log(f"    {jwt_exp_info(token)}")
    log(f"    {token[:80]}...")

# ------------------------------------------------------------------
# 4. Update .env
# ------------------------------------------------------------------
log("\n[7] Cap nhat .env...")

env = load_env(ENV_PATH)

# Chon access_token tot nhat
access_token = tokens_found.get("marketplace_access_token", "")
refresh_token = tokens_found.get("marketplace_refresh_token", "")

if not access_token:
    log("    WARNING: Khong co marketplace_access_token!")
else:
    payload = decode_jwt_payload(access_token)
    if payload:
        exp = payload.get("exp")
        if exp and exp < time.time():
            log(f"    WARNING: Token da het han! Khong nen luu.")
        else:
            env["UPPROMOTE_BEARER_TOKEN"] = access_token
            log(f"    Da cap nhat UPPROMOTE_BEARER_TOKEN ({jwt_exp_info(access_token)})")

if refresh_token:
    env["UPPROMOTE_REFRESH_TOKEN"] = refresh_token
    log(f"    Da cap nhat UPPROMOTE_REFRESH_TOKEN")

# Also update session if found
if tokens_found.get("uppromote_session"):
    env["UPPROMOTE_SESSION"] = tokens_found["uppromote_session"]

save_env(ENV_PATH, env)
log(f"\n    Da luu vao {ENV_PATH}")

# ------------------------------------------------------------------
# 5. Verify the new token works
# ------------------------------------------------------------------
log("\n[8] Kiem tra token moi...")
import requests as _req
new_token = env.get("UPPROMOTE_BEARER_TOKEN", "")
if new_token:
    resp = _req.get(
        "https://mkp-api.uppromote.com/api/v1/marketplace-offer/find-offer/datatable/data",
        params={"page": 1, "per_page": 1, "keyword": "", "sort_by": "most_relevant",
                "tab[0]": "all-offers", "pathPage": "/offers/find-offers"},
        headers={"Authorization": f"Bearer {new_token}", "Accept": "application/json",
                 "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
        timeout=30,
    )
    log(f"    API Status: {resp.status_code}")
    if resp.ok:
        log("    ==> Token moi HOAT DONG!")
    else:
        log(f"    Response: {resp.text[:200]}")
        log("    Token co the da het han hoac can refresh.")

log("\nXong.")

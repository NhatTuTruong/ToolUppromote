"""Test Uppromote OAuth refresh token endpoint."""
import base64
import json
import os
import requests

env_path = os.path.join(os.path.dirname(__file__), ".env")
refresh_token = ""
bearer = ""
for line in open(env_path, encoding="utf-8"):
    line = line.strip()
    if line.startswith("UPPROMOTE_REFRESH_TOKEN="):
        refresh_token = line.split("=", 1)[1].strip().strip('"').strip("'")
    if line.startswith("UPPROMOTE_BEARER_TOKEN="):
        bearer = line.split("=", 1)[1].strip().strip('"').strip("'")

print(f"Refresh token: {refresh_token[:40]}...")

client_id = "2"
sub = ""
if bearer:
    parts = bearer.split(".")
    if len(parts) >= 2:
        try:
            p = parts[1].replace("-", "+").replace("_", "/")
            padded = p + "=" * (-len(p) % 4)
            decoded = base64.b64decode(padded, validate=True)
            payload = json.loads(decoded)
            client_id = str(payload.get("aud", "2"))
            sub = str(payload.get("sub", ""))
            print(f"Decoded JWT: aud={client_id}, sub={sub}")
            print(f"Full payload: {json.dumps(payload, indent=2)}")
        except Exception as e:
            print(f"JWT decode error: {e}")

ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
base = "https://mkp-api.uppromote.com/oauth/token"

def try_fmt(label, headers, data):
    print(f"\n{'='*60}\nTEST: {label}")
    try:
        resp = requests.post(base, headers=headers, data=data, timeout=30)
        print(f"Status: {resp.status_code} | Response: {resp.text[:500]}")
    except Exception as exc:
        print(f"Exception: {exc}")

# 1. Only refresh_token + client_id (no client_secret)
try_fmt(
    "PKCE: refresh_token + client_id only (no client_secret, no sub)",
    {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": ua},
    {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
)

# 2. refresh_token + client_id + scope (full)
try_fmt(
    "PKCE + scope=*",
    {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": ua},
    {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id, "scope": "*"}
)

# 3. Without grant_type
try_fmt(
    "No grant_type (already tested 400, expected)",
    {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": ua},
    {"refresh_token": refresh_token, "client_id": client_id}
)

# 4. Try client_id "marketplace-api" or similar
for cid in ["marketplace-api", "mkp-api", "uppromote", "2"]:
    try_fmt(
        f"client_id='{cid}'",
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json", "User-Agent": ua},
        {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": cid}
    )

# 5. Try from different domains (same endpoint, different referer)
for referer in [
    "https://marketplace.uppromote.com/",
    "https://mkp.uppromote.com/",
    "https://app.uppromote.com/",
]:
    try_fmt(
        f"Referer: {referer}",
        {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json",
         "User-Agent": ua, "Referer": referer, "Origin": referer},
        {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
    )

# 6. Try without Accept header
try_fmt(
    "No Accept header",
    {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": ua},
    {"grant_type": "refresh_token", "refresh_token": refresh_token, "client_id": client_id}
)

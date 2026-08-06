"""Test script to debug Uppromote fetch issue."""
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

# Load .env
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

# Test fetch
print("=== Testing Uppromote API ===")
from filter import fetch_uppromote_page, build_uppromote_headers, with_page

base_url = os.getenv("UPPROMOTE_API_URL") or ""
print(f"Base URL: {base_url[:80]}...")

# Build headers and check token
import re
def normalize_bearer(raw):
    if raw is None:
        return ""
    token = str(raw).strip().replace("\r", "")
    if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        token = token[1:-1].strip()
    token = re.sub(r"^Bearer\s+", "", token, flags=re.I)
    return token

raw_token = os.getenv("UPPROMOTE_BEARER_TOKEN", "")
print(f"Raw token from env: len={len(raw_token)}, starts_with_quote={raw_token.startswith(chr(34))}")
normalized = normalize_bearer(raw_token)
print(f"Normalized token: len={len(normalized)}")
bearer = f"Bearer {normalized}"
print(f"Full auth header: {bearer[:60]}...")

# Test page 1
import requests
request_url = with_page(base_url, 1)
print(f"\nRequest URL: {request_url}")

headers = {
    "accept": "application/json",
    "authorization": bearer,
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
}
print(f"Headers OK: auth={bearer[:60]}...")

print("\nSending request...")
res = requests.get(request_url, headers=headers, timeout=60)
print(f"Status: {res.status_code}")
print(f"Response text (first 500): {res.text[:500]}")

if res.status_code == 200:
    body = res.json()
    print(f"\nBody keys: {list(body.keys())}")
    data = body.get("data")
    print(f"data type: {type(data)}")
    if isinstance(data, dict):
        print(f"data keys: {list(data.keys())}")
        page_items = data.get("data")
        print(f"data['data'] type: {type(page_items)}, len: {len(page_items) if page_items else 0}")
else:
    print(f"Error response: {res.text[:300]}")

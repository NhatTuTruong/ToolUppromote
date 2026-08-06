"""Test if refresh token can get new bearer."""
import os
import requests

from dotenv import load_dotenv
load_dotenv(".env")

refresh = os.getenv("UPPROMOTE_REFRESH_TOKEN", "").strip()
session = os.getenv("UPPROMOTE_SESSION", "").strip()
bearer = os.getenv("UPPROMOTE_BEARER_TOKEN", "").strip()

print(f"Refresh token: {refresh[:50]}...")
print(f"Session token: {session[:50]}...")
print(f"Bearer token: {bearer[:50]}...")

# Try to get new token using refresh
print("\n=== Trying to refresh token ===")
# Try common refresh endpoints
endpoints = [
    "https://mkp-api.uppromote.com/api/v1/auth/refresh",
    "https://marketplace.uppromote.com/api/auth/refresh",
    "https://mkp-api.uppromote.com/api/v1/auth/refresh-token",
]

for ep in endpoints:
    print(f"\nTrying: {ep}")
    try:
        res = requests.post(
            ep,
            json={"refresh_token": refresh},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        print(f"  Status: {res.status_code}")
        print(f"  Response: {res.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

# Try to use session token
print("\n=== Trying session token ===")
session_endpoints = [
    "https://mkp-api.uppromote.com/api/v1/auth/me",
    "https://marketplace.uppromote.com/api/v1/auth/me",
]

headers = {"Authorization": f"Bearer {bearer}", "Accept": "application/json"}
for ep in session_endpoints:
    print(f"\nTrying: {ep}")
    try:
        res = requests.get(ep, headers=headers, timeout=10)
        print(f"  Status: {res.status_code}")
        print(f"  Response: {res.text[:200]}")
    except Exception as e:
        print(f"  Error: {e}")

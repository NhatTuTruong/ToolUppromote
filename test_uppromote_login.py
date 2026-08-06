"""Test Uppromote login with Playwright Stealth."""
import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth

BASE_DIR = Path(__file__).parent
from dotenv import load_dotenv
load_dotenv(BASE_DIR / ".env")

email = os.getenv("UPPROMOTE_EMAIL", "").strip()
from local_secret import resolve_uppromote_password
password = resolve_uppromote_password()

print(f"Email: {email[:3]}***")
print(f"Password set: {bool(password)}")

# Use stealth wrapper
with stealth.Stealth().use_sync(sync_playwright()) as p:
    print("Launching Edge with stealth...")

    browser = p.chromium.launch(
        channel="msedge",
        headless=False,  # Visible for testing
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--window-size=1920,1080",
        ],
    )

    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()

    print("Navigating to login page...")
    try:
        page.goto(
            "https://marketplace.uppromote.com/auth/login",
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        print(f"Page loaded! URL: {page.url}")
        print(f"Title: {page.title()}")
    except Exception as e:
        print(f"Navigation failed: {e}")
        browser.close()
        exit(1)

    # Wait for React to render
    print("Waiting 8s for React to render...")
    time.sleep(8)

    print(f"\nCurrent URL: {page.url}")

    # Look for email input
    print("\nLooking for email input...")
    selectors = [
        'input[type="email"]',
        'input[name="email"]',
        'input[id="email"]',
        'input[placeholder*="email" i]',
    ]

    email_input = None
    for sel in selectors:
        count = page.locator(sel).count()
        if count > 0:
            email_input = page.locator(sel).first
            print(f"Found: {sel} (count: {count})")
            break

    if not email_input:
        print("Email input NOT found!")
        screenshot_path = BASE_DIR / "debug_login.png"
        page.screenshot(path=str(screenshot_path))
        print(f"Screenshot: {screenshot_path}")

        # Check for Cloudflare
        page_text = page.inner_text("body")[:500]
        print(f"Page text: {page_text}")
        browser.close()
        exit(1)

    print("\nFilling email...")
    email_input.fill(email)
    time.sleep(0.5)

    print("Looking for password...")
    pw_selectors = ['input[type="password"]', 'input[name="password"]']
    pw_input = None
    for sel in pw_selectors:
        if page.locator(sel).count() > 0:
            pw_input = page.locator(sel).first
            print(f"Found: {sel}")
            break

    if not pw_input:
        print("Password input NOT found!")
        browser.close()
        exit(1)

    print("\nFilling password...")
    pw_input.fill(password)
    time.sleep(0.5)

    print("Looking for submit button...")
    btn_selectors = ['button[type="submit"]', 'button:has-text("Sign in")', 'button:has-text("Login")']
    submit_btn = None
    for sel in btn_selectors:
        count = page.locator(sel).count()
        if count > 0:
            submit_btn = page.locator(sel).first
            print(f"Found: {sel}")
            break

    if not submit_btn:
        print("Submit NOT found!")
        browser.close()
        exit(1)

    print("\nClicking submit...")
    submit_btn.click()

    # Wait for redirect
    try:
        page.wait_for_url(lambda url: "/offers" in url or "/dashboard" in url, timeout=60_000)
        print(f"Redirected: {page.url}")
    except Exception as e:
        print(f"No redirect: {e}, current: {page.url}")
        time.sleep(5)

    # Get cookies
    cookies = context.cookies()
    print(f"\nCookies ({len(cookies)}):")
    for c in cookies:
        name = c['name']
        val = c['value']
        if len(val) > 60:
            val = val[:60] + "..."
        print(f"  {name}: {val}")

    browser.close()
    print("\nDone!")

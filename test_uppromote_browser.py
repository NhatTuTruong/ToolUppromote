"""
Test: Dùng Playwright + Edge CDP để tự động lấy token Uppromote.
Chạy thử với trình duyệt Edge đang mở (CDP port 9222) hoặc tự mở Edge mới.
"""
import os, sys, time, json, base64

# Thêm edge_cdp.py vào path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from edge_cdp import ensure_edge_cdp_running, cdp_url_host_port, default_user_data_dir_for_port

# 1. Đảm bảo Edge CDP đang chạy
cdp_url = "http://127.0.0.1:9222"
edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
ok = ensure_edge_cdp_running(
    port=9222,
    user_data_dir=r"C:\edge-cdp",
    edge_exe=edge_exe,
    log=lambda m: print(f"[Edge] {m}"),
    wait_sec=12.0,
)
print(f"Edge CDP ready: {ok}")
if not ok:
    print("Không mở được Edge CDP. Thoát.")
    sys.exit(1)

# 2. Kết nối Playwright
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(cdp_url)
    context = browser.contexts[0] if browser.contexts else browser.new_context()
    page = context.new_page()

    print("\n=== TEST 1: Thử đăng nhập Uppromote Marketplace ===")

    # Thử trang login Uppromote
    page.goto("https://marketplace.uppromote.com/login", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    print(f"URL hiện tại: {page.url}")
    print(f"Title: {page.title()}")

    # In cookies hiện tại
    cookies = context.cookies()
    uppromote_cookies = [c for c in cookies if "uppromote" in c["domain"].lower()]
    print(f"\nUppromote cookies: {len(uppromote_cookies)}")
    for c in uppromote_cookies:
        print(f"  {c['name']} = {c['value'][:30]}...")

    # Thử localStorage / sessionStorage
    try:
        storage = page.evaluate("""() => {
            const result = {};
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                try { result[k] = localStorage.getItem(k); } catch(e) {}
            }
            return result;
        }""")
        print(f"\nLocalStorage keys: {list(storage.keys())}")
        for k, v in storage.items():
            print(f"  {k}: {str(v)[:80]}")
    except Exception as e:
        print(f"Không đọc localStorage: {e}")

    print("\n=== TEST 2: Mở trang chính Uppromote (đã login) ===")
    page.goto("https://marketplace.uppromote.com/offers/find-offers", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    print(f"URL: {page.url}")

    # Check network requests cho API calls
    print("\n=== TEST 3: Lắng nghe API calls ===")
    api_calls = []
    def handle_response(response):
        if "oauth" in response.url.lower() or "token" in response.url.lower() or "api" in response.url.lower():
            try:
                api_calls.append({
                    "url": response.url,
                    "status": response.status,
                    "headers": dict(response.headers),
                })
            except Exception:
                pass

    page.on("response", handle_response)
    page.reload(wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)

    print(f"\nAPI calls liên quan: {len(api_calls)}")
    for call in api_calls[:10]:
        print(f"  [{call['status']}] {call['url'][:100]}")
        # Check Authorization header
        auth = call['headers'].get('authorization', '')
        if auth:
            print(f"    Auth: {auth[:50]}...")

    # Đọc tokens từ localStorage / sessionStorage
    print("\n=== TEST 4: Tìm tokens trong storage ===")
    try:
        all_storage = page.evaluate("""() => {
            const result = {localStorage: {}, sessionStorage: {}};
            for (let i = 0; i < localStorage.length; i++) {
                const k = localStorage.key(i);
                try { result.localStorage[k] = localStorage.getItem(k); } catch(e) {}
            }
            for (let i = 0; i < sessionStorage.length; i++) {
                const k = sessionStorage.key(i);
                try { result.sessionStorage[k] = sessionStorage.getItem(k); } catch(e) {}
            }
            return result;
        }""")

        for storage_type, items in all_storage.items():
            for k, v in items.items():
                if any(x in k.lower() for x in ["token", "auth", "jwt", "access", "refresh", "bearer"]):
                    print(f"\n  [{storage_type}] {k}:")
                    print(f"    {str(v)[:200]}")
    except Exception as e:
        print(f"Không đọc storage: {e}")

    print("\n=== TEST 5: Check trang app.uppromote.com ===")
    page.goto("https://app.uppromote.com", wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    print(f"URL: {page.url}")
    print(f"Title: {page.title()}")

    # Lấy screenshot để xem giao diện
    try:
        page.screenshot(path="uppromote_screenshot.png", full_page=True)
        print("Đã lưu screenshot: uppromote_screenshot.png")
    except Exception as e:
        print(f"Không chụp được screenshot: {e}")

    # Check IndexedDB (nơi nhiều app lưu token)
    print("\n=== TEST 6: Check IndexedDB ===")
    try:
        dbs = page.evaluate("""async () => {
            const dbs = await indexedDB.databases();
            return dbs.map(d => d.name);
        }""")
        print(f"IndexedDB databases: {dbs}")
    except Exception as e:
        print(f"Không đọc IndexedDB: {e}")

    browser.close()

print("\nXong. Kiểm tra file uppromote_screenshot.png để xem giao diện.")

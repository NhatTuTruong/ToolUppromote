import shutil
import threading
import time
from pathlib import Path

import tkinter as tk
from tkinter import messagebox
import webview  # type: ignore

from webapp import _safe_result_file_path, app


HOST = "127.0.0.1"
PORT = 5050
URL = f"http://{HOST}:{PORT}"


class DesktopApi:
    """API gọi từ JS (window.pywebview.api) — lưu file kết quả khi WebView chặn tải tự động."""

    def save_result_xlsx(self, name: str) -> dict:
        safe = Path(str(name or "")).name
        if not safe:
            return {"ok": False, "error": "Tên file không hợp lệ."}
        full = _safe_result_file_path(safe)
        if full is None:
            return {"ok": False, "error": "Tên file không được phép."}
        if not full.is_file():
            return {"ok": False, "error": "Không tìm thấy file."}
        wins = webview.windows
        if not wins:
            return {"ok": False, "error": "Chưa có cửa sổ."}
        win = wins[0]
        try:
            result = win.create_file_dialog(
                webview.FileDialog.SAVE,
                directory="",
                save_filename=safe,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if not result:
            return {"ok": False, "error": "cancelled"}
        dest = Path(result[0])
        try:
            shutil.copy2(full, dest)
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}


def run_server():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)


def main():
    # WebView2: cho phép tải qua navigation / thẻ a (vẫn có thể bị chặn → dùng save_result_xlsx).
    webview.settings["ALLOW_DOWNLOADS"] = True

    api = DesktopApi()
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.2)

    try:
        webview.create_window(
            "Affiliate Offer Filter",
            URL,
            width=1280,
            height=820,
            js_api=api,
        )
        webview.start(gui="edgechromium")
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Launch Error",
            f"Cannot launch desktop window.\n{exc}",
        )
        root.destroy()


if __name__ == "__main__":
    main()

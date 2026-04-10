import threading
import time

import tkinter as tk
from tkinter import messagebox
import webview  # type: ignore

from webapp import app


HOST = "127.0.0.1"
PORT = 5050
URL = f"http://{HOST}:{PORT}"


def run_server():
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


def main():
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.2)

    try:
        webview.create_window("Affiliate Offer Filter", URL, width=1280, height=820)
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

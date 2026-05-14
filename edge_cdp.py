"""
Edge/Chromium CDP helpers (tách khỏi webapp để subprocess Auto Apply import nhẹ).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse


# Tài khoản Collabs k (1..10) → cổng CDP 9221+k (9222 … 9231), khớp Auto Apply đa tài khoản.
EDGE_CDP_ACCOUNT_BASE_PORT = 9221
EDGE_CDP_ACCOUNT_MAX = 10


def port_for_collabs_account(account_index: int) -> int:
    """account_index: 1 = tài khoản đầu → 9222, …, 10 → 9231."""
    i = int(account_index)
    if i < 1 or i > EDGE_CDP_ACCOUNT_MAX:
        raise ValueError(f"account_index phải từ 1 đến {EDGE_CDP_ACCOUNT_MAX}, nhận được: {account_index}")
    return EDGE_CDP_ACCOUNT_BASE_PORT + i


def cdp_url_for_collabs_account(account_index: int, host: str = "127.0.0.1") -> str:
    p = port_for_collabs_account(account_index)
    h = (host or "127.0.0.1").strip() or "127.0.0.1"
    return f"http://{h}:{p}"


def cdp_url_host_port(cdp_url: str) -> tuple[str, int]:
    raw = (cdp_url or "").strip() or "http://127.0.0.1:9222"
    u = urlparse(raw)
    host = (u.hostname or "127.0.0.1").strip() or "127.0.0.1"
    port = int(u.port or 9222)
    return host, port


def default_user_data_dir_for_port(port: int) -> str:
    """Profile Edge riêng theo cổng CDP để chạy song song nhiều account (Windows: C:\\; khác: TMP)."""
    p = int(port)
    if sys.platform.startswith("win"):
        if p == 9222:
            return r"C:\edge-cdp"
        return rf"C:\edge-cdp-{p}"
    base = os.environ.get("TMPDIR") or os.environ.get("TMP") or "/tmp"
    return str(Path(base) / f"edge-cdp-{p}")


def _is_tcp_port_open(host: str, port: int, timeout_sec: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=float(timeout_sec)):
            return True
    except OSError:
        return False


def _default_edge_paths_windows() -> list[str]:
    paths = []
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    paths.append(str(Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
    paths.append(str(Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
    return paths


def ensure_edge_cdp_running(
    port: int = 9222,
    user_data_dir: str = r"C:\edge-cdp",
    edge_exe: str | None = None,
    log: Optional[Callable[[str], None]] = None,
    wait_sec: float = 12.0,
    host: str = "127.0.0.1",
) -> bool:
    """
    - Nếu CDP port đã mở: coi như Edge đã chạy -> OK.
    - Nếu chưa: tự mở Edge với --remote-debugging-port + --user-data-dir rồi chờ port lên.
    """

    def _log(msg: str) -> None:
        if log:
            try:
                log(str(msg))
            except Exception:
                pass

    h = (host or "127.0.0.1").strip() or "127.0.0.1"
    if _is_tcp_port_open(h, port):
        _log(f"CDP đã sẵn sàng trên {h}:{port} (Edge đã mở).")
        return True

    if not sys.platform.startswith("win"):
        _log("Không phải Windows: không tự mở Edge. Hãy tự mở browser CDP trước.")
        return False

    exe = (edge_exe or "").strip()
    if not exe:
        for p in _default_edge_paths_windows():
            if Path(p).is_file():
                exe = p
                break
    if not exe:
        from shutil import which

        exe = which("msedge") or which("msedge.exe") or ""
    if not exe:
        _log("Không tìm thấy msedge.exe để mở Edge CDP.")
        return False

    args = [
        exe,
        f"--remote-debugging-port={int(port)}",
        f"--user-data-dir={user_data_dir}",
    ]

    try:
        creationflags = 0
        if sys.platform.startswith("win"):
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
    except Exception as exc:
        _log(f"Lỗi mở Edge CDP: {exc}")
        return False

    deadline = time.monotonic() + float(wait_sec)
    while time.monotonic() < deadline:
        if _is_tcp_port_open(h, port):
            _log(f"Edge CDP đã lên trên {h}:{port}.")
            return True
        time.sleep(0.25)
    _log(f"Timeout chờ Edge CDP trên {h}:{port}.")
    return False

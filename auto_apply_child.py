"""
Worker chạy trong subprocess (Windows spawn): một CDP + một profile + danh sách link.
"""

from __future__ import annotations

import auto_apply as auto_apply_core
from edge_cdp import cdp_url_host_port, default_user_data_dir_for_port, ensure_edge_cdp_running


def _default_edge_exe() -> str | None:
    return None


def run_auto_apply_in_subprocess(
    *,
    job_id: str,
    links: list,
    profile: dict,
    auto_submit: bool,
    cdp_url: str,
    login_first: bool,
    file_name: str,
    edge_user_data_dir: str,
    log_queue,
    stop_event,
    result_queue,
) -> None:
    """Blocking; gọi từ multiprocessing.Process. Kết quả gửi qua result_queue (một dict)."""

    def _log(msg: str) -> None:
        try:
            log_queue.put((job_id, str(msg)))
        except Exception:
            pass

    host, port = cdp_url_host_port(cdp_url)
    udir = (edge_user_data_dir or "").strip() or default_user_data_dir_for_port(port)
    exe = _default_edge_exe()

    try:
        _log("Đang kiểm tra/mở Edge CDP (slot song song)…")
        ok = ensure_edge_cdp_running(
            port=port,
            user_data_dir=udir,
            edge_exe=exe,
            log=_log,
            host=host,
        )
        if not ok:
            raise RuntimeError(f"Không mở / không kết nối được CDP {cdp_url} (profile: {udir}).")
        _log(f"[{job_id}] Bắt đầu Auto Apply ({len(links)} link)…")
        result = auto_apply_core.run_auto_apply(
            links=list(links),
            profile=dict(profile) if isinstance(profile, dict) else {},
            auto_submit=bool(auto_submit),
            cdp_url=str(cdp_url).strip(),
            login_first=bool(login_first),
            should_stop=lambda: stop_event.is_set(),
            log=_log,
        )
        result_queue.put({"job_id": job_id, "ok": True, "result": result})
    except Exception as exc:
        try:
            result_queue.put({"job_id": job_id, "ok": False, "error": str(exc)})
        except Exception:
            pass

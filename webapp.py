import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

import filter as core
from app import ENV_PATH, apply_settings_for_run, load_env_defaults, offer_passes_filters, row_is_dat, save_env

import license_guard
from runtime_paths import app_dir, bundle_dir


BASE_DIR = app_dir()
license_guard.set_paths(BASE_DIR)


class RunControl:
    def __init__(self):
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            return False
        self.pause_event.set()
        return True

    def wait_if_paused(self):
        while self.pause_event.is_set() and not self.stop_event.is_set():
            time.sleep(0.2)

    def should_stop(self):
        return self.stop_event.is_set()


class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.ack_lock = threading.Lock()
        self.running = False
        self.paused = False
        self.status = "Rảnh"
        self.progress = 0.0
        self.logs = []
        self.log_ack_seen = 0
        self.control = None
        self.worker = None
        self.output_file = ""
        self.output_files = []

    def add_log(self, message: str):
        with self.lock:
            self.logs.append(message)

    def log_count(self) -> int:
        with self.lock:
            return len(self.logs)

    def notify_log_displayed(self, seen_total: int) -> None:
        """Client đã vẽ xong tới mốc len(logs) == seen_total (sau poll /api/logs)."""
        if seen_total < 0:
            return
        with self.ack_lock:
            if seen_total > self.log_ack_seen:
                self.log_ack_seen = seen_total

    def wait_log_displayed(self, target_total: int, deadline_sec: float = 300.0) -> str:
        """
        Chờ client xác nhận đã hiển thị tới target_total (len logs sau add_log).
        Trả về 'ok' | 'stop' | 'timeout'.
        """
        deadline = time.monotonic() + deadline_sec
        ctrl = self.control
        while time.monotonic() < deadline:
            if ctrl and ctrl.should_stop():
                return "stop"
            with self.ack_lock:
                if self.log_ack_seen >= target_total:
                    return "ok"
            time.sleep(0.012)
        return "timeout"

    def get_logs(self, since: int):
        with self.lock:
            total = len(self.logs)
            if since < 0:
                since = 0
            return self.logs[since:], total


STATE = AppState()
_root = bundle_dir()
app = Flask(
    __name__,
    template_folder=str(_root / "templates"),
    static_folder=str(_root / "static"),
)


def _refresh_license_env_from_file() -> None:
    """
    Đồng bộ các biến license từ .env vào process hiện tại.
    Cần vì core.load_env_file() không overwrite biến đã tồn tại trong os.environ.
    """
    disk = core.parse_env_file(ENV_PATH)
    for key in (
        "AFF_LICENSE_API_BASE_URL",
        "AFF_LICENSE_SERVER_URL",
        "AFF_LICENSE_API_TOKEN",
        "AFF_LICENSE_DAILY_LIMIT",
    ):
        if key in disk:
            os.environ[key] = str(disk.get(key) or "").strip()


def fetch_offers_uppromote(filters: dict) -> list:
    base_url = (os.getenv("UPPROMOTE_API_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Thiếu UPPROMOTE_API_URL trong cài đặt")
    core.enforce_fixed_fetch_defaults()
    max_pages_cap = core.uppromote_max_pages_cap()
    start_page = int(filters.get("start_page") or 1)
    end_raw = filters.get("end_page")
    if end_raw is None:
        end_page = 1
    elif str(end_raw).strip() == "":
        end_page = None
    else:
        end_page = int(end_raw)
    if start_page < 1:
        start_page = 1
    if end_page is not None and end_page < start_page:
        end_page = start_page
    if end_page is not None and max_pages_cap is not None:
        end_page = min(end_page, max_pages_cap)
    delay_ms = int(
        os.getenv("UPPROMOTE_PAGE_DELAY_MS", str(core.DEFAULT_UPPROMOTE_PAGE_DELAY_MS))
        or str(core.DEFAULT_UPPROMOTE_PAGE_DELAY_MS)
    )

    raw_offers = []
    page = start_page
    while True:
        STATE.control.wait_if_paused()
        if STATE.control.should_stop():
            STATE.add_log("Đã dừng.")
            return []
        STATE.add_log(f"Uppromote trang {page}: đang tải...")
        body = core.fetch_uppromote_page(base_url, page)
        payload = body.get("data") or {}
        page_items = payload.get("data") or []
        if not isinstance(page_items, list):
            page_items = []
        if not page_items:
            STATE.add_log(f"Uppromote trang {page}: hết dữ liệu, dừng phân trang.")
            break
        raw_offers.extend(page_items)
        STATE.add_log(f"Uppromote trang {page}: +{len(page_items)} offer (tổng {len(raw_offers)})")
        if end_page is not None and page >= end_page:
            STATE.add_log(f"Uppromote: đã tới trang kết thúc đã chọn: {end_page}")
            break
        if max_pages_cap is not None and page >= max_pages_cap:
            STATE.add_log(f"Uppromote: đã tới giới hạn trang trong cài đặt: {max_pages_cap}")
            break
        next_page = payload.get("next_page_url")
        if not next_page:
            break
        page += 1
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

    offers = []
    detail_delay_ms = int(os.getenv("UPPROMOTE_DETAIL_DELAY_MS", "50") or "50")
    total_raw = len(raw_offers)
    for idx, raw_offer in enumerate(raw_offers, start=1):
        STATE.control.wait_if_paused()
        if STATE.control.should_stop():
            STATE.add_log("Đã dừng.")
            return []
        detail = {}
        shop_id = raw_offer.get("shop_id")
        if shop_id:
            try:
                detail = core.fetch_uppromote_offer_detail(shop_id)
            except Exception as exc:
                STATE.add_log(f"Lỗi chi tiết shop_id={shop_id}: {exc}")
        offers.append(core.map_uppromote_offer(raw_offer, detail))
        if idx % 10 == 0 or idx == total_raw:
            STATE.add_log(f"Tiến độ chi tiết offer: {idx}/{total_raw}")
        if detail_delay_ms > 0:
            time.sleep(detail_delay_ms / 1000)
    return offers


def fetch_offers_goaffpro(filters: dict) -> list:
    base_url = (os.getenv("GOAFFPRO_API_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Thiếu GOAFFPRO_API_URL trong cài đặt")
    core.enforce_fixed_fetch_defaults()
    limit = int(
        os.getenv("GOAFFPRO_LIMIT", str(core.DEFAULT_OFFERS_PER_PAGE)) or str(core.DEFAULT_OFFERS_PER_PAGE)
    )
    max_pages_cap = core.goaffpro_max_pages_cap()
    start_page = int(filters.get("start_page") or 1)
    if start_page < 1:
        start_page = 1
    end_raw = filters.get("end_page")
    if end_raw is None:
        end_page = 1
    elif str(end_raw).strip() == "":
        end_page = None
    else:
        end_page = int(end_raw)
    if end_page is not None and end_page < start_page:
        end_page = start_page
    if end_page is not None and max_pages_cap is not None:
        end_page = min(end_page, max_pages_cap)
    delay_ms = int(
        os.getenv("GOAFFPRO_PAGE_DELAY_MS", str(core.DEFAULT_GOAFFPRO_PAGE_DELAY_MS))
        or str(core.DEFAULT_GOAFFPRO_PAGE_DELAY_MS)
    )

    raw_stores = []
    page = start_page
    while True:
        STATE.control.wait_if_paused()
        if STATE.control.should_stop():
            STATE.add_log("Đã dừng.")
            return []
        offset = (page - 1) * limit
        STATE.add_log(f"Goaffpro trang {page} (offset={offset}): đang tải...")
        body = core.fetch_goaffpro_page(base_url, offset, limit)
        stores = body.get("stores") or []
        if not isinstance(stores, list):
            stores = []
        if not stores:
            STATE.add_log(f"Goaffpro trang {page}: hết dữ liệu, dừng phân trang.")
            break
        raw_stores.extend(stores)
        STATE.add_log(f"Goaffpro trang {page}: +{len(stores)} cửa hàng (tổng {len(raw_stores)})")
        try:
            total_n = int(body.get("count")) if body.get("count") is not None else None
        except Exception:
            total_n = None
        if total_n is not None and offset + len(stores) >= total_n:
            STATE.add_log("Goaffpro: đã lấy hết theo tổng từ API.")
            break
        if end_page is not None and page >= end_page:
            STATE.add_log(f"Goaffpro: đã tới trang kết thúc đã chọn: {end_page}")
            break
        if max_pages_cap is not None and page >= max_pages_cap:
            STATE.add_log(f"Goaffpro: đã tới giới hạn trang trong cài đặt: {max_pages_cap}")
            break
        if len(stores) < limit:
            break
        page += 1
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

    return [core.map_goaffpro_store(s) for s in raw_stores]


def run_pipeline(settings: dict, min_traffic: int, filters: dict, source: str = "uppromote"):
    apply_settings_for_run(settings)
    core.enforce_fixed_fetch_defaults()
    os.environ["MIN_VISITS"] = str(min_traffic)

    src = (source or "uppromote").lower()
    if src == "goaffpro":
        STATE.add_log("Đang tải offer từ Goaffpro...")
        offers = fetch_offers_goaffpro(filters)
        snapshot_path = BASE_DIR / "goaffpro-offers-last.json"
    else:
        STATE.add_log("Đang tải offer từ Uppromote...")
        offers = fetch_offers_uppromote(filters)
        snapshot_path = BASE_DIR / "uppromote-offers-last.json"

    if STATE.control.should_stop():
        STATE.add_log("Đã dừng.")
        return

    cap = license_guard.export_offer_cap(len(offers), src)
    if cap == 0:
        STATE.add_log(license_guard.zero_export_cap_log_message(src))
        return
    if cap < len(offers):
        partial = license_guard.export_cap_partial_log(len(offers), cap, src)
        if partial:
            STATE.add_log(partial)
        offers = offers[:cap]

    STATE.add_log(f"Đã tải {len(offers)} offer.")
    snapshot_path.write_text(
        core.json.dumps(
            {"fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(offers), "offers": offers},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    from_offers = core.unique_hosts([o.get("url", "") for o in offers])
    domain_file = Path(os.getenv("DOMAIN_FILE", str(BASE_DIR / "domain.txt")))
    from_file = core.read_domains_from_txt(domain_file)
    domains = sorted(set(from_offers + from_file))
    if not domains:
        raise RuntimeError("Không có tên miền: thêm URL từ offer hoặc file domain.txt.")

    STATE.add_log(f"Chạy Apify cho {len(domains)} tên miền...")
    items = []
    chunk_size = int(
        os.getenv("APIFY_MAX_DOMAINS_PER_RUN", str(core.DEFAULT_APIFY_MAX_DOMAINS_PER_RUN))
        or str(core.DEFAULT_APIFY_MAX_DOMAINS_PER_RUN)
    )
    for idx, part in enumerate(core.chunked(domains, chunk_size), start=1):
        STATE.control.wait_if_paused()
        if STATE.control.should_stop():
            STATE.add_log("Đã dừng.")
            return
        STATE.add_log(f"Apify đợt {idx}: {len(part)} tên miền")
        dataset_id = core.apify_call_actor(part)
        items.extend(core.apify_list_items(dataset_id))

    by_host = {}
    for item in items:
        site = core.apify_site_field(item)
        key = core.host_key(site)
        if key:
            by_host[key] = item

    net_prefix = "goaffpro" if src == "goaffpro" else "uppromote"
    xlsx_path = BASE_DIR / f"{net_prefix}_{int(time.time())}.xlsx"
    header = list(core.GOAFF_CSV_HEADER) if src == "goaffpro" else list(core.UPPROMOTE_CSV_HEADER_VI)

    exported_rows = []
    total_offers = len(offers)
    export_interrupted = False

    def _flush_export_workbook(note: str = "") -> bool:
        if not exported_rows:
            return False
        try:
            core.write_xlsx_highlight_status(xlsx_path, header, exported_rows, status_col=0)
        except Exception as exc:
            STATE.add_log(f"Không ghi được Excel (cần openpyxl): {exc}")
            return False
        with STATE.lock:
            STATE.output_file = str(xlsx_path)
            STATE.output_files.insert(0, xlsx_path.name)
            STATE.output_files = STATE.output_files[:100]
        extra = f" — {note}" if note else ""
        abs_path = str(xlsx_path.resolve())
        STATE.add_log(
            f"Đã ghi Excel{extra}: {len(exported_rows)} dòng → {xlsx_path.name} "
            f"(cột trạng thái ĐẠT: nền xanh lá nhạt)\n"
            f"  Đường dẫn đầy đủ: {abs_path}"
        )
        return True

    try:
        STATE.add_log(
            f"─── Xuất dữ liệu: xử lý lần lượt {total_offers} offer; "
            f"file .xlsx được lưu khi hoàn tất hoặc khi dừng / lỗi (giữ các dòng đã xử lý) ───"
        )
        _w = STATE.wait_log_displayed(STATE.log_count())
        if _w == "stop":
            STATE.add_log("Đã dừng trước khi xuất từng offer.")
            return
        if _w == "timeout":
            STATE.add_log("[Cảnh báo] Chờ hiển thị log quá lâu — tiếp tục xử lý.")
        for idx, offer in enumerate(offers, start=1):
            STATE.control.wait_if_paused()
            if STATE.control.should_stop():
                STATE.add_log("Đã nhận lệnh dừng — lưu các dòng đã xử lý ra file…")
                export_interrupted = True
                break

            brand = offer.get("brand", "")
            url = offer.get("url", "")
            key = core.host_key(url)
            item = core.lookup_apify_item(url, by_host)
            eng = core.engagement_from_item(item)
            visits = core.parse_visits_from_engagement(eng)
            min_v = float(min_traffic)
            filters_ok = offer_passes_filters(offer, filters, src)
            traffic_ok = visits >= min_v
            status = core.STATUS_TRAFFIC_OK if row_is_dat(offer, filters, src, visits, min_v) else core.STATUS_TRAFFIC_FAIL
            if src == "goaffpro":
                row = core.build_goaff_csv_row(offer, item, status)
            else:
                row = core.build_uppromote_csv_row_vi(offer, item, status)
            exported_rows.append(row)
            license_guard.record_one_exported_row(src)
            visits_show = eng.get("VisitsFormatted") if eng else ""
            if not visits_show and visits:
                visits_show = int(visits) if visits == int(visits) else round(visits, 2)
            elif not visits_show:
                visits_show = 0
            block = (
                f"┌─ Record {idx}/{total_offers} ─────────────────────\n"
                f"│  Thương hiệu : {brand}\n"
                f"│  Domain/URL  : {key or url}\n"
                f"│  Trạng thái  : {status}\n"
                f"│  Lọc offer   : {'đạt' if filters_ok else 'chưa đạt'}\n"
                f"│  Traffic      : {'đạt' if traffic_ok else 'chưa đạt'} "
                f"(~{visits_show} so với ngưỡng {min_v})\n"
                f"└────────────────────────────────────────"
            )
            STATE.add_log(block)
            with STATE.lock:
                STATE.progress = (idx / total_offers) * 100
            _w = STATE.wait_log_displayed(STATE.log_count())
            if _w == "stop":
                STATE.add_log("Đã nhận lệnh dừng — lưu các dòng đã xử lý ra file…")
                export_interrupted = True
                break
            if _w == "timeout":
                STATE.add_log("[Cảnh báo] Chờ hiển thị log quá lâu — tiếp record tiếp theo.")
    except Exception as exc:
        export_interrupted = True
        STATE.add_log(
            f"Lỗi trong vòng xuất: {exc} — đã xử lý xong {len(exported_rows)} dòng, sẽ ghi Excel phần đã có."
        )
        raise
    finally:
        if exported_rows:
            note = "dừng hoặc lỗi giữa chừng" if export_interrupted else "hoàn tất"
            _flush_export_workbook(note)


def _worker(settings: dict, min_traffic: int, filters: dict, source: str = "uppromote"):
    try:
        run_pipeline(settings, min_traffic, filters, source)
    except Exception as exc:
        STATE.add_log(f"LỖI: {exc}")
    finally:
        with STATE.lock:
            STATE.running = False
            STATE.paused = False
            STATE.status = "Rảnh"
            if STATE.progress < 100:
                STATE.progress = 100
        STATE.add_log("Hoàn tất.")


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/settings")
def api_settings():
    return jsonify(load_env_defaults())


@app.post("/api/settings")
def api_save_settings():
    payload = request.get_json(force=True) or {}
    save_env(payload)
    return jsonify({"ok": True})


@app.get("/api/license")
def api_license():
    core.load_env_file(ENV_PATH)
    _refresh_license_env_from_file()
    license_guard.set_paths(BASE_DIR)
    return _no_cache_json(license_guard.license_status_payload())


@app.post("/api/license/activate")
def api_license_activate():
    core.load_env_file(ENV_PATH)
    _refresh_license_env_from_file()
    license_guard.set_paths(BASE_DIR)
    payload = request.get_json(force=True) or {}
    key = (payload.get("key") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "Nhập key kích hoạt."}), 400
    ok, msg = license_guard.activate_key(key)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400
    return jsonify({"ok": True, "message": msg, "license": license_guard.license_status_payload()})


@app.post("/api/license/deactivate")
def api_license_deactivate():
    core.load_env_file(ENV_PATH)
    _refresh_license_env_from_file()
    license_guard.set_paths(BASE_DIR)
    ok, msg = license_guard.deactivate_on_this_machine()
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400
    return jsonify({"ok": True, "message": msg, "license": license_guard.license_status_payload()})


@app.post("/api/run")
def api_run():
    payload = request.get_json(force=True) or {}
    settings = payload.get("settings") or {}
    filters = payload.get("filters") or {}
    try:
        min_traffic = float(payload.get("min_traffic") if payload.get("min_traffic") not in (None, "") else 9000)
    except (TypeError, ValueError):
        min_traffic = 9000.0
    source = (payload.get("source") or "uppromote").strip().lower()
    if source not in ("uppromote", "goaffpro"):
        source = "uppromote"

    core.load_env_file(ENV_PATH)
    _refresh_license_env_from_file()
    license_guard.set_paths(BASE_DIR)
    ok_run, lic_err = license_guard.assert_can_start_pipeline(source)
    if not ok_run:
        return jsonify({"ok": False, "error": lic_err}), 400

    with STATE.lock:
        if STATE.running:
            return jsonify({"ok": False, "error": "Đang chạy sẵn, không thể bắt đầu thêm."}), 400
        STATE.running = True
        STATE.paused = False
        STATE.status = "Đang chạy"
        STATE.progress = 0
        STATE.logs = []
        with STATE.ack_lock:
            STATE.log_ack_seen = 0
        STATE.control = RunControl()
        STATE.worker = threading.Thread(target=_worker, args=(settings, min_traffic, filters, source), daemon=True)
        STATE.worker.start()
    return jsonify({"ok": True})


@app.post("/api/pause")
def api_pause():
    with STATE.lock:
        if not STATE.running or not STATE.control:
            return jsonify({"ok": False}), 400
        paused = STATE.control.toggle_pause()
        STATE.paused = paused
        STATE.status = "Tạm dừng" if paused else "Đang chạy"
    STATE.add_log("Đã tạm dừng." if paused else "Đã tiếp tục.")
    return jsonify({"ok": True, "paused": paused})


@app.post("/api/stop")
def api_stop():
    with STATE.lock:
        if not STATE.running or not STATE.control:
            return jsonify({"ok": False}), 400
        STATE.control.stop()
        STATE.status = "Đang dừng"
    STATE.add_log("Đang dừng...")
    return jsonify({"ok": True})


def _no_cache_json(data):
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@app.get("/api/status")
def api_status():
    with STATE.lock:
        return _no_cache_json(
            {
                "running": STATE.running,
                "paused": STATE.paused,
                "status": STATE.status,
                "progress": STATE.progress,
                "output_file": STATE.output_file,
            }
        )


@app.get("/api/logs")
def api_logs():
    since = int(request.args.get("since", "0"))
    logs, total = STATE.get_logs(since)
    return _no_cache_json({"logs": logs, "total": total})


@app.post("/api/logs/ack")
def api_logs_ack():
    """Client xác nhận đã hiển thị log tới mốc total (đồng bộ với /api/logs)."""
    payload = request.get_json(force=True) or {}
    try:
        seen = int(payload.get("seen_total", 0))
    except (TypeError, ValueError):
        seen = 0
    STATE.notify_log_displayed(seen)
    return jsonify({"ok": True})


@app.get("/api/results")
def api_results():
    files = []
    seen = set()
    globs = (
        list(BASE_DIR.glob("result-*.xlsx"))
        + list(BASE_DIR.glob("uppromote_*.xlsx"))
        + list(BASE_DIR.glob("goaffpro_*.xlsx"))
    )
    for p in sorted(globs, key=lambda x: x.stat().st_mtime, reverse=True):
        if p.name in seen:
            continue
        seen.add(p.name)
        files.append(
            {
                "name": p.name,
                "size": p.stat().st_size,
                "modified": int(p.stat().st_mtime),
            }
        )
    return jsonify({"files": files})


def _allowed_export_basename(name: str) -> bool:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext != "xlsx":
        return False
    return name.startswith("result-") or name.startswith("uppromote_") or name.startswith("goaffpro_")


def _safe_result_file_path(safe_name: str) -> Path | None:
    if not _allowed_export_basename(safe_name):
        return None
    base = BASE_DIR.resolve()
    full = (base / Path(safe_name).name).resolve()
    try:
        full.relative_to(base)
    except ValueError:
        return None
    return full


@app.get("/api/download/<path:filename>")
def api_download(filename: str):
    safe_name = Path(filename).name
    full = _safe_result_file_path(safe_name)
    if full is None:
        return jsonify({"ok": False, "error": "Invalid file"}), 400
    if not full.is_file():
        return jsonify({"ok": False, "error": "Not found"}), 404
    # str(path): PyInstaller/Windows ổn định hơn với đường dẫn UNC/unicode
    return send_file(
        str(full),
        as_attachment=True,
        download_name=safe_name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        max_age=0,
        conditional=False,
    )


@app.post("/api/results/delete")
def api_delete_result():
    payload = request.get_json(force=True) or {}
    name = (payload.get("name") or "").strip()
    safe_name = Path(name).name
    full = _safe_result_file_path(safe_name)
    if full is None:
        return jsonify({"ok": False, "error": "Invalid file"}), 400
    if not full.is_file():
        return jsonify({"ok": False, "error": "Not found"}), 404
    try:
        full.unlink()
    except OSError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
    return jsonify({"ok": True})


if __name__ == "__main__":
    # threaded=True: worker chạy pipeline không chặn request /api/logs (log theo thời gian thực)
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)

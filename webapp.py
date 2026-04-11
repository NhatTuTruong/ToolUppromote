import csv
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import filter as core
from app import apply_settings_for_run, load_env_defaults, offer_passes_filters, row_is_dat, save_env


BASE_DIR = Path(__file__).resolve().parent


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
        self.running = False
        self.paused = False
        self.status = "Rảnh"
        self.progress = 0.0
        self.logs = []
        self.control = None
        self.worker = None
        self.output_file = ""
        self.output_files = []

    def add_log(self, message: str):
        with self.lock:
            self.logs.append(message)

    def get_logs(self, since: int):
        with self.lock:
            total = len(self.logs)
            if since < 0:
                since = 0
            return self.logs[since:], total


STATE = AppState()
app = Flask(__name__, template_folder="templates", static_folder="static")


def fetch_offers_uppromote(filters: dict) -> list:
    base_url = (os.getenv("UPPROMOTE_API_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Thiếu UPPROMOTE_API_URL trong cài đặt")
    max_pages = int(os.getenv("UPPROMOTE_MAX_PAGES", "5") or "5")
    start_page = int(filters.get("start_page") or 1)
    end_page = int(filters.get("end_page") or max_pages)
    if start_page < 1:
        start_page = 1
    if end_page < start_page:
        end_page = start_page
    delay_ms = int(os.getenv("UPPROMOTE_PAGE_DELAY_MS", "250") or "250")

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
        if page >= end_page:
            STATE.add_log(f"Uppromote: đã tới trang kết thúc đã chọn: {end_page}")
            break
        if page >= max_pages:
            STATE.add_log(f"Uppromote: đã tới giới hạn trang trong cài đặt: {max_pages}")
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
    limit = int(os.getenv("GOAFFPRO_LIMIT", "50") or "50")
    max_pages = int(os.getenv("GOAFFPRO_MAX_PAGES", "100") or "100")
    start_page = int(filters.get("start_page") or 1)
    if start_page < 1:
        start_page = 1
    end_raw = filters.get("end_page")
    if end_raw is not None and str(end_raw).strip() != "":
        end_page = int(end_raw)
    else:
        end_page = max_pages
    if end_page < start_page:
        end_page = start_page
    end_page = min(end_page, max_pages)
    delay_ms = int(os.getenv("GOAFFPRO_PAGE_DELAY_MS", "250") or "250")

    raw_stores = []
    for page in range(start_page, end_page + 1):
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
        if len(stores) < limit:
            break
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

    return [core.map_goaffpro_store(s) for s in raw_stores]


def run_pipeline(settings: dict, min_traffic: int, filters: dict, source: str = "uppromote"):
    apply_settings_for_run(settings)
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
    chunk_size = int(os.getenv("APIFY_MAX_DOMAINS_PER_RUN", "50") or "50")
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
    out_path = BASE_DIR / f"{net_prefix}_{int(time.time())}.csv"
    header = list(core.GOAFF_CSV_HEADER) if src == "goaffpro" else list(core.UPPROMOTE_CSV_HEADER_VI)

    exported_rows = []
    rows = 0
    total_offers = len(offers)
    # utf-8-sig: BOM giúp Excel Windows hiển thị đúng tiếng Việt
    with out_path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for idx, offer in enumerate(offers, start=1):
            STATE.control.wait_if_paused()
            if STATE.control.should_stop():
                STATE.add_log("Đã dừng.")
                return

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
            writer.writerow(row)
            exported_rows.append(row)
            rows += 1
            visits_show = eng.get("VisitsFormatted") if eng else ""
            if not visits_show and visits:
                visits_show = int(visits) if visits == int(visits) else round(visits, 2)
            elif not visits_show:
                visits_show = 0
            STATE.add_log(
                f"Dòng {idx}/{total_offers}: {status} | {brand} | {key} | "
                f"lọc={'đạt' if filters_ok else 'chưa đạt'} | traffic={'đạt' if traffic_ok else 'chưa đạt'} | "
                f"~{visits_show} / ngưỡng {min_v}"
            )
            with STATE.lock:
                STATE.progress = (idx / total_offers) * 100

    xlsx_path = out_path.with_suffix(".xlsx")
    try:
        core.write_xlsx_highlight_status(xlsx_path, header, exported_rows, status_col=0)
        xlsx_ok = True
    except Exception as exc:
        STATE.add_log(f"Không ghi được Excel (cần openpyxl): {exc}")
        xlsx_ok = False

    with STATE.lock:
        STATE.output_file = str(out_path)
        STATE.output_files.insert(0, out_path.name)
        if xlsx_ok:
            STATE.output_files.insert(0, xlsx_path.name)
        STATE.output_files = STATE.output_files[:100]
    if xlsx_ok:
        STATE.add_log(f"Xong: {rows} dòng → {out_path.name} và {xlsx_path.name} (dòng ĐẠT: nền xanh lá nhạt trong Excel)")
    else:
        STATE.add_log(f"Xong: {rows} dòng → {out_path.name}")


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

    with STATE.lock:
        if STATE.running:
            return jsonify({"ok": False, "error": "Đang chạy sẵn, không thể bắt đầu thêm."}), 400
        STATE.running = True
        STATE.paused = False
        STATE.status = "Đang chạy"
        STATE.progress = 0
        STATE.logs = []
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


@app.get("/api/status")
def api_status():
    with STATE.lock:
        return jsonify(
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
    return jsonify({"logs": logs, "total": total})


@app.get("/api/results")
def api_results():
    files = []
    seen = set()
    globs = (
        list(BASE_DIR.glob("result-*.csv"))
        + list(BASE_DIR.glob("result-*.xlsx"))
        + list(BASE_DIR.glob("uppromote_*.csv"))
        + list(BASE_DIR.glob("uppromote_*.xlsx"))
        + list(BASE_DIR.glob("goaffpro_*.csv"))
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
    if ext not in ("csv", "xlsx"):
        return False
    return name.startswith("result-") or name.startswith("uppromote_") or name.startswith("goaffpro_")


@app.get("/api/download/<path:filename>")
def api_download(filename: str):
    safe_name = Path(filename).name
    if not _allowed_export_basename(safe_name):
        return jsonify({"ok": False, "error": "Invalid file"}), 400
    full = BASE_DIR / safe_name
    if not full.exists():
        return jsonify({"ok": False, "error": "Not found"}), 404
    return send_from_directory(BASE_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)

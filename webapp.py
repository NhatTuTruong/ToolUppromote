import csv
import os
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

import filter as core
from app import load_env_defaults, offer_passes_filters, save_env


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
        self.status = "Idle"
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


def run_pipeline(settings: dict, min_traffic: int, filters: dict):
    for k, v in settings.items():
        os.environ[k] = str(v)
    os.environ["MIN_VISITS"] = str(min_traffic)

    STATE.add_log("Fetching offers from Uppromote...")
    base_url = (os.getenv("UPPROMOTE_API_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Missing UPPROMOTE_API_URL")
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
            STATE.add_log("Stopped.")
            return
        STATE.add_log(f"Uppromote page {page}: fetching...")
        body = core.fetch_uppromote_page(base_url, page)
        payload = body.get("data") or {}
        page_items = payload.get("data") or []
        if not isinstance(page_items, list):
            page_items = []
        if not page_items:
            STATE.add_log(f"Uppromote page {page}: no records, stop pagination.")
            break
        raw_offers.extend(page_items)
        STATE.add_log(f"Uppromote page {page}: +{len(page_items)} offers (total {len(raw_offers)})")
        if page >= end_page:
            STATE.add_log(f"Uppromote reached selected end page: {end_page}")
            break
        if page >= max_pages:
            STATE.add_log(f"Uppromote reached max pages from settings: {max_pages}")
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
            STATE.add_log("Stopped.")
            return
        detail = {}
        shop_id = raw_offer.get("shop_id")
        if shop_id:
            try:
                detail = core.fetch_uppromote_offer_detail(shop_id)
            except Exception as exc:
                STATE.add_log(f"Detail failed for shop_id={shop_id}: {exc}")
        offers.append(core.map_uppromote_offer(raw_offer, detail))
        if idx % 10 == 0 or idx == total_raw:
            STATE.add_log(f"Offer detail progress: {idx}/{total_raw}")
        if detail_delay_ms > 0:
            time.sleep(detail_delay_ms / 1000)

    if STATE.control.should_stop():
        STATE.add_log("Stopped.")
        return
    STATE.add_log(f"Loaded {len(offers)} offers.")

    snapshot_path = BASE_DIR / "uppromote-offers-last.json"
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
        raise RuntimeError("No domain available from offers/domain.txt")

    STATE.add_log(f"Running Apify for {len(domains)} domains...")
    items = []
    chunk_size = int(os.getenv("APIFY_MAX_DOMAINS_PER_RUN", "50") or "50")
    for idx, part in enumerate(core.chunked(domains, chunk_size), start=1):
        STATE.control.wait_if_paused()
        if STATE.control.should_stop():
            STATE.add_log("Stopped.")
            return
        STATE.add_log(f"Apify batch {idx}: {len(part)} domains")
        dataset_id = core.apify_call_actor(part)
        items.extend(core.apify_list_items(dataset_id))

    by_host = {}
    for item in items:
        site = item.get("SiteName") or item.get("siteName")
        key = core.host_key(site)
        if key:
            by_host[key] = item

    out_path = BASE_DIR / f"result-{int(time.time())}.csv"
    header = [
        "Status",
        "Brand",
        "Website",
        "Domain",
        "Traffic Formatted",
        "Traffic Raw",
        "Pages Per Visit",
        "Bounce Rate",
        "Top Countries",
        "Top Keywords",
        "Commission",
        "Commission Type",
        "Cookie Days",
        "Currency",
        "Category",
        "Payout Rate",
        "Approval Rate",
        "Offer Score",
        "Recommend Score",
        "Application Review",
        "Payout Period",
        "Promotion Details",
        "Allowed Channels",
        "Target Locations",
        "Target Ages",
        "Target Genders",
        "Can Apply",
        "Is Applied",
        "Apply URL",
        "Offer ID",
        "Shop ID",
        "Program ID",
        "Marketplace Listing ID",
        "EPC Average Earning Per Sale",
    ]

    fh = out_path.open("w", encoding="utf-8", newline="")

    rows = 0
    total_offers = len(offers)
    with fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for idx, offer in enumerate(offers, start=1):
            STATE.control.wait_if_paused()
            if STATE.control.should_stop():
                STATE.add_log("Stopped.")
                return

            if not offer_passes_filters(offer, filters):
                STATE.add_log(f"Record {idx}/{total_offers}: SKIP by filter | {offer.get('brand', '')}")
                with STATE.lock:
                    STATE.progress = (idx / total_offers) * 100
                continue

            brand = offer.get("brand", "")
            url = offer.get("url", "")
            key = core.host_key(url)
            item = by_host.get(key, {})
            eng = item.get("Engagments") or item.get("Engagements") or {}
            visits_raw = eng.get("Visits", 0)
            try:
                visits = float(visits_raw)
            except Exception:
                visits = 0
            if visits <= min_traffic:
                STATE.add_log(
                    f"Record {idx}/{total_offers}: SKIP by min traffic | {brand} | visits={eng.get('VisitsFormatted', visits)}"
                )
                with STATE.lock:
                    STATE.progress = (idx / total_offers) * 100
                continue
            status = "GET"

            writer.writerow(
                [
                    status,
                    brand,
                    url,
                    key,
                    eng.get("VisitsFormatted", ""),
                    int(visits) if visits.is_integer() else visits,
                    eng.get("PagePerVisit", ""),
                    eng.get("BounceRate", ""),
                    core.top_countries_csv(item.get("TopCountryShares") or []),
                    core.top_keywords_csv(core.keyword_shares_from_item(item)),
                    offer.get("offer", ""),
                    offer.get("commission_type", ""),
                    offer.get("cookieDays", ""),
                    offer.get("currency", ""),
                    offer.get("category", ""),
                    offer.get("payout_rate", ""),
                    offer.get("approval_rate", ""),
                    offer.get("offer_score", ""),
                    offer.get("recommend_score", ""),
                    offer.get("application_review", ""),
                    offer.get("payments", ""),
                    core.join_list(offer.get("promotion_details")),
                    core.join_list(offer.get("target_audience_customer_channels")),
                    core.join_list(offer.get("target_audience_locations")),
                    core.join_list(offer.get("target_audience_ages")),
                    core.join_list(offer.get("target_audience_genders")),
                    offer.get("can_apply_offer", ""),
                    offer.get("is_applied_offer", ""),
                    offer.get("client_url", ""),
                    offer.get("offer_id", ""),
                    offer.get("shop_id", ""),
                    offer.get("program_id", ""),
                    offer.get("mkp_listing_id", ""),
                    offer.get("epc", ""),
                ]
            )
            rows += 1
            STATE.add_log(f"Record {idx}/{total_offers}: {status} {brand} | {key} | visits={eng.get('VisitsFormatted', visits)}")
            with STATE.lock:
                STATE.progress = (idx / total_offers) * 100

    with STATE.lock:
        STATE.output_file = str(out_path)
        STATE.output_files.insert(0, out_path.name)
        STATE.output_files = STATE.output_files[:100]
    STATE.add_log(f"Done: {rows} rows -> {out_path.name}")


def _worker(settings: dict, min_traffic: int, filters: dict):
    try:
        run_pipeline(settings, min_traffic, filters)
    except Exception as exc:
        STATE.add_log(f"ERROR: {exc}")
    finally:
        with STATE.lock:
            STATE.running = False
            STATE.paused = False
            STATE.status = "Idle"
            if STATE.progress < 100:
                STATE.progress = 100
        STATE.add_log("Process finished.")


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
    min_traffic = int(payload.get("min_traffic") or 9000)

    with STATE.lock:
        if STATE.running:
            return jsonify({"ok": False, "error": "Already running"}), 400
        STATE.running = True
        STATE.paused = False
        STATE.status = "Running"
        STATE.progress = 0
        STATE.logs = []
        STATE.control = RunControl()
        STATE.worker = threading.Thread(target=_worker, args=(settings, min_traffic, filters), daemon=True)
        STATE.worker.start()
    return jsonify({"ok": True})


@app.post("/api/pause")
def api_pause():
    with STATE.lock:
        if not STATE.running or not STATE.control:
            return jsonify({"ok": False}), 400
        paused = STATE.control.toggle_pause()
        STATE.paused = paused
        STATE.status = "Paused" if paused else "Running"
    STATE.add_log("Paused." if paused else "Resumed.")
    return jsonify({"ok": True, "paused": paused})


@app.post("/api/stop")
def api_stop():
    with STATE.lock:
        if not STATE.running or not STATE.control:
            return jsonify({"ok": False}), 400
        STATE.control.stop()
        STATE.status = "Stopping"
    STATE.add_log("Stopping...")
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
    for p in sorted(BASE_DIR.glob("result-*.csv"), key=lambda x: x.stat().st_mtime, reverse=True):
        files.append(
            {
                "name": p.name,
                "size": p.stat().st_size,
                "modified": int(p.stat().st_mtime),
            }
        )
    return jsonify({"files": files})


@app.get("/api/download/<path:filename>")
def api_download(filename: str):
    safe_name = Path(filename).name
    if not safe_name.startswith("result-") or not safe_name.endswith(".csv"):
        return jsonify({"ok": False, "error": "Invalid file"}), 400
    full = BASE_DIR / safe_name
    if not full.exists():
        return jsonify({"ok": False, "error": "Not found"}), 404
    return send_from_directory(BASE_DIR, safe_name, as_attachment=True)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)

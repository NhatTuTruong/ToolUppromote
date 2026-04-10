import csv
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

import filter as core


BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


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


def save_env(values: dict):
    lines = [f"{k}={v}" for k, v in values.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_env_defaults():
    core.load_env_file(ENV_PATH)
    return {
        "APIFY_TOKEN": os.getenv("APIFY_TOKEN", ""),
        "UPPROMOTE_API_URL": os.getenv("UPPROMOTE_API_URL", ""),
        "UPPROMOTE_BEARER_TOKEN": os.getenv("UPPROMOTE_BEARER_TOKEN", ""),
        "UPPROMOTE_MAX_PAGES": os.getenv("UPPROMOTE_MAX_PAGES", "5"),
        "UPPROMOTE_PAGE_DELAY_MS": os.getenv("UPPROMOTE_PAGE_DELAY_MS", "250"),
        "UPPROMOTE_PER_PAGE": os.getenv("UPPROMOTE_PER_PAGE", "50"),
        "APIFY_MAX_DOMAINS_PER_RUN": os.getenv("APIFY_MAX_DOMAINS_PER_RUN", "50"),
    }


def parse_number(value: str):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_percent(value) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace("%", "")
    # handle "92.34%" / "No data yet"
    try:
        return float(s)
    except ValueError:
        return None


def extract_commission_percent(value) -> float | None:
    if value is None:
        return None
    text = str(value)
    m = core.re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def offer_passes_filters(offer: dict, filters: dict) -> bool:
    min_commission = parse_number(filters.get("min_commission"))
    min_cookie = parse_number(filters.get("min_cookie"))
    currency = (filters.get("currency") or "").strip().upper()
    app_review = (filters.get("application_review") or "").strip().lower()
    min_payout_rate = parse_number(filters.get("min_payout_rate"))
    min_approval_rate = parse_number(filters.get("min_approval_rate"))

    if min_commission is not None:
        c = extract_commission_percent(offer.get("offer"))
        if c is None or c < min_commission:
            return False
    if min_cookie is not None:
        try:
            cookie_days = float(offer.get("cookieDays"))
        except Exception:
            cookie_days = None
        if cookie_days is None or cookie_days < min_cookie:
            return False
    if currency:
        offer_currency = str(offer.get("currency") or "").strip().upper()
        if offer_currency != currency:
            return False
    if app_review:
        review = str(offer.get("application_review") or "").strip().lower()
        if review != app_review:
            return False
    if min_payout_rate is not None:
        p = extract_percent(offer.get("payout_rate"))
        if p is None or p < min_payout_rate:
            return False
    if min_approval_rate is not None:
        a = extract_percent(offer.get("approval_rate"))
        if a is None or a < min_approval_rate:
            return False
    return True


def run_pipeline(settings: dict, min_traffic: int, filters: dict, log, control: RunControl):
    for k, v in settings.items():
        os.environ[k] = str(v)
    os.environ["MIN_VISITS"] = str(min_traffic)

    log("Fetching offers from Uppromote...")
    offers = core.fetch_all_uppromote_offers()
    if control.should_stop():
        log("Stopped.")
        return
    log(f"Loaded {len(offers)} offers.")

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

    log(f"Running Apify for {len(domains)} domains...")
    items = []
    chunk_size = int(os.getenv("APIFY_MAX_DOMAINS_PER_RUN", "50") or "50")
    for idx, part in enumerate(core.chunked(domains, chunk_size), start=1):
        control.wait_if_paused()
        if control.should_stop():
            log("Stopped.")
            return
        log(f"Apify batch {idx}: {len(part)} domains")
        dataset_id = core.apify_call_actor(part)
        items.extend(core.apify_list_items(dataset_id))

    by_host = {}
    for item in items:
        site = item.get("SiteName") or item.get("siteName")
        key = core.host_key(site)
        if key:
            by_host[key] = item

    out_path = BASE_DIR / "result.csv"
    header = [
        "Status", "Brand", "Website", "Domain", "Traffic Formatted", "Traffic Raw", "Pages Per Visit", "Bounce Rate",
        "Top Countries", "Top Keywords", "Commission", "Commission Type", "Cookie Days", "Currency", "Category",
        "Payout Rate", "Approval Rate", "Offer Score", "Recommend Score", "Application Review", "Payout Period",
        "Promotion Details", "Allowed Channels", "Target Locations", "Target Ages", "Target Genders", "Can Apply",
        "Is Applied", "Apply URL", "Offer ID", "Shop ID", "Program ID", "Marketplace Listing ID",
        "EPC Average Earning Per Sale",
    ]

    try:
        fh = out_path.open("w", encoding="utf-8", newline="")
    except PermissionError:
        out_path = BASE_DIR / f"result-{int(time.time())}.csv"
        fh = out_path.open("w", encoding="utf-8", newline="")

    rows = 0
    total_offers = len(offers)
    with fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for idx, offer in enumerate(offers, start=1):
            control.wait_if_paused()
            if control.should_stop():
                log("Stopped.")
                return

            if not offer_passes_filters(offer, filters):
                log(f"Record {idx}/{total_offers}: SKIP by filter | {offer.get('brand', '')}")
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
            status = "GET" if visits > min_traffic else "NO"

            writer.writerow([
                status, brand, url, key, eng.get("VisitsFormatted", ""), int(visits) if visits.is_integer() else visits,
                eng.get("PagePerVisit", ""), eng.get("BounceRate", ""), core.top_countries_csv(item.get("TopCountryShares") or []),
                core.top_keywords_csv(core.keyword_shares_from_item(item)), offer.get("offer", ""), offer.get("commission_type", ""),
                offer.get("cookieDays", ""), offer.get("currency", ""), offer.get("category", ""), offer.get("payout_rate", ""),
                offer.get("approval_rate", ""), offer.get("offer_score", ""), offer.get("recommend_score", ""),
                offer.get("application_review", ""), offer.get("payments", ""), core.join_list(offer.get("promotion_details")),
                core.join_list(offer.get("target_audience_customer_channels")), core.join_list(offer.get("target_audience_locations")),
                core.join_list(offer.get("target_audience_ages")), core.join_list(offer.get("target_audience_genders")),
                offer.get("can_apply_offer", ""), offer.get("is_applied_offer", ""), offer.get("client_url", ""),
                offer.get("offer_id", ""), offer.get("shop_id", ""), offer.get("program_id", ""), offer.get("mkp_listing_id", ""),
                offer.get("epc", ""),
            ])
            rows += 1
            log(f"Record {idx}/{total_offers}: {status} {brand} | {key} | visits={eng.get('VisitsFormatted', visits)}")

    log(f"Done: {rows} rows -> {out_path.name}")
    return out_path


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Affiliate Offer Filter1")
        self.geometry("1180x760")
        self.minsize(1080, 700)
        self.log_queue = queue.Queue()
        self.control = None
        self.worker = None
        self.is_running_var = tk.StringVar(value="Idle")
        self.progress_var = tk.DoubleVar(value=0)

        defaults = load_env_defaults()
        self.vars = {k: tk.StringVar(value=v) for k, v in defaults.items()}
        self.min_traffic_var = tk.StringVar(value=os.getenv("MIN_VISITS", "9000"))

        self.result_file_var = tk.StringVar(value="")
        self.filter_vars = {
            "min_commission": tk.StringVar(value=""),
            "min_cookie": tk.StringVar(value=""),
            "currency": tk.StringVar(value=""),
            "application_review": tk.StringVar(value=""),
            "min_payout_rate": tk.StringVar(value=""),
            "min_approval_rate": tk.StringVar(value=""),
        }

        self._build_ui_tabs()
        self.after(200, self._drain_logs)
        self._apply_style()

    def _apply_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"))
        style.configure("SubHeader.TLabel", font=("Segoe UI", 10))
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"))

    def _build_ui_tabs(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)
        nb = ttk.Notebook(frm)
        nb.pack(fill="both", expand=True)

        tab_settings = ttk.Frame(nb, padding=10)
        tab_main = ttk.Frame(nb, padding=10)
        tab_results = ttk.Frame(nb, padding=10)
        nb.add(tab_settings, text="Settings")
        nb.add(tab_main, text="Run")
        nb.add(tab_results, text="Results")

        ttk.Label(tab_settings, text="System Settings", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            tab_settings,
            text="Configure API and runtime parameters. Changes will be saved into .env",
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        settings = ttk.LabelFrame(tab_settings, text="Environment Variables", padding=10)
        settings.pack(fill="both", expand=True)
        row = 0
        for key in self.vars:
            ttk.Label(settings, text=key, width=26).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(settings, textvariable=self.vars[key], width=95, show="*" if "TOKEN" in key else "").grid(
                row=row, column=1, sticky="ew", pady=3
            )
            row += 1
        ttk.Button(settings, text="Save Settings", command=self.save_settings, style="Primary.TButton").grid(
            row=row, column=1, sticky="e", pady=8
        )
        settings.columnconfigure(1, weight=1)

        ttk.Label(tab_main, text="Run Filter", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            tab_main,
            text="Set optional conditions. Empty fields mean no restriction.",
            style="SubHeader.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        run_box = ttk.LabelFrame(tab_main, text="Run Filters", padding=10)
        run_box.pack(fill="x")
        ttk.Label(run_box, text="Min Traffic").grid(row=0, column=0, sticky="w", pady=3)
        ttk.Entry(run_box, textvariable=self.min_traffic_var, width=18).grid(row=0, column=1, sticky="w", pady=3)

        ttk.Label(run_box, text="Min Commission %").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(run_box, textvariable=self.filter_vars["min_commission"], width=18).grid(row=1, column=1, sticky="w", pady=3)

        ttk.Label(run_box, text="Min Cookie Days").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(run_box, textvariable=self.filter_vars["min_cookie"], width=18).grid(row=2, column=1, sticky="w", pady=3)

        ttk.Label(run_box, text="Currency").grid(row=0, column=2, sticky="w", padx=(20, 0), pady=3)
        ttk.Entry(run_box, textvariable=self.filter_vars["currency"], width=18).grid(row=0, column=3, sticky="w", pady=3)

        ttk.Label(run_box, text="Application Review").grid(row=1, column=2, sticky="w", padx=(20, 0), pady=3)
        review_combo = ttk.Combobox(
            run_box,
            textvariable=self.filter_vars["application_review"],
            values=["", "auto", "manual"],
            state="readonly",
            width=16,
        )
        review_combo.grid(row=1, column=3, sticky="w", pady=3)

        ttk.Label(run_box, text="Min Payout Rate %").grid(row=2, column=2, sticky="w", padx=(20, 0), pady=3)
        ttk.Entry(run_box, textvariable=self.filter_vars["min_payout_rate"], width=18).grid(row=2, column=3, sticky="w", pady=3)

        ttk.Label(run_box, text="Min Approval Rate %").grid(row=3, column=2, sticky="w", padx=(20, 0), pady=3)
        ttk.Entry(run_box, textvariable=self.filter_vars["min_approval_rate"], width=18).grid(row=3, column=3, sticky="w", pady=3)

        btn_row = ttk.Frame(tab_main)
        btn_row.pack(fill="x", pady=10)
        self.btn_run = ttk.Button(btn_row, text="Filter", command=self.start_run, style="Primary.TButton")
        self.btn_run.pack(side="left")
        self.btn_pause = ttk.Button(btn_row, text="Pause", command=self.toggle_pause, state="disabled")
        self.btn_pause.pack(side="left", padx=8)
        self.btn_stop = ttk.Button(btn_row, text="Stop", command=self.stop_run, state="disabled")
        self.btn_stop.pack(side="left")
        ttk.Label(btn_row, text="Status:", style="Status.TLabel").pack(side="left", padx=(20, 6))
        ttk.Label(btn_row, textvariable=self.is_running_var).pack(side="left")

        prog = ttk.Progressbar(tab_main, mode="determinate", variable=self.progress_var, maximum=100)
        prog.pack(fill="x", pady=(0, 10))

        log_box = ttk.LabelFrame(tab_main, text="Process Log", padding=10)
        log_box.pack(fill="both", expand=True)
        self.log_text = scrolledtext.ScrolledText(log_box, height=22, state="disabled")
        self.log_text.pack(fill="both", expand=True)

        ttk.Label(tab_results, text="Result List", style="Header.TLabel").pack(anchor="w")
        rs = ttk.LabelFrame(tab_results, text="Result List", padding=10)
        rs.pack(fill="both", expand=True)
        top_rs = ttk.Frame(rs)
        top_rs.pack(fill="x")
        ttk.Label(top_rs, textvariable=self.result_file_var).pack(side="left")
        ttk.Button(top_rs, text="Refresh", command=self.load_results, style="Primary.TButton").pack(side="right")

        cols = ("Status", "Brand", "Website", "Traffic", "Commission", "Currency", "Cookie", "Payout Rate", "Approval Rate")
        self.result_tree = ttk.Treeview(rs, columns=cols, show="headings", height=18)
        for c in cols:
            self.result_tree.heading(c, text=c)
            self.result_tree.column(c, width=120 if c != "Website" else 260, anchor="w")
        yscroll = ttk.Scrollbar(rs, orient="vertical", command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=yscroll.set)
        self.result_tree.pack(side="left", fill="both", expand=True, pady=(8, 0))
        yscroll.pack(side="right", fill="y", pady=(8, 0))

    def save_settings(self):
        payload = {k: self.vars[k].get().strip() for k in self.vars}
        payload["MIN_VISITS"] = self.min_traffic_var.get().strip()
        save_env(payload)
        messagebox.showinfo("Saved", ".env updated successfully.")

    def _log(self, msg: str):
        self.log_queue.put(msg)

    def _drain_logs(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                m = core.re.search(r"Record\s+(\d+)\/(\d+):", msg)
                if m:
                    cur = int(m.group(1))
                    total = int(m.group(2))
                    if total > 0:
                        self.progress_var.set((cur / total) * 100.0)
                self.log_text.configure(state="normal")
                self.log_text.insert("end", f"{msg}\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(200, self._drain_logs)

    def start_run(self):
        if self.worker and self.worker.is_alive():
            return
        try:
            min_traffic = int(self.min_traffic_var.get().strip())
        except ValueError:
            messagebox.showerror("Invalid input", "Min Traffic must be a number.")
            return

        settings = {k: self.vars[k].get().strip() for k in self.vars}
        filters = {k: self.filter_vars[k].get().strip() for k in self.filter_vars}
        self.control = RunControl()
        self.btn_run.configure(state="disabled")
        self.btn_pause.configure(state="normal", text="Pause")
        self.btn_stop.configure(state="normal")
        self.is_running_var.set("Running")
        self.progress_var.set(0)

        def work():
            try:
                result_path = run_pipeline(settings, min_traffic, filters, self._log, self.control)
                if result_path:
                    self.result_file_var.set(f"Output: {result_path}")
                    self.after(0, self.load_results)
            except Exception as exc:
                self._log(f"ERROR: {exc}")
            finally:
                self._log("Process finished.")
                self.after(0, lambda: self.btn_run.configure(state="normal"))
                self.after(0, lambda: self.btn_pause.configure(state="disabled", text="Pause"))
                self.after(0, lambda: self.btn_stop.configure(state="disabled"))
                self.after(0, lambda: self.is_running_var.set("Idle"))
                self.after(0, lambda: self.progress_var.set(100))

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def toggle_pause(self):
        if not self.control:
            return
        paused = self.control.toggle_pause()
        self.btn_pause.configure(text="Resume" if paused else "Pause")
        self._log("Paused." if paused else "Resumed.")
        self.is_running_var.set("Paused" if paused else "Running")

    def stop_run(self):
        if not self.control:
            return
        self.control.stop()
        self._log("Stopping...")
        self.is_running_var.set("Stopping")

    def load_results(self):
        target = self.result_file_var.get().replace("Output: ", "").strip()
        path = Path(target) if target else BASE_DIR / "result.csv"
        if not path.exists():
            return
        for row in self.result_tree.get_children():
            self.result_tree.delete(row)
        with path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for rec in reader:
                self.result_tree.insert(
                    "",
                    "end",
                    values=(
                        rec.get("Status", ""),
                        rec.get("Brand", ""),
                        rec.get("Website", ""),
                        rec.get("Traffic Formatted", ""),
                        rec.get("Commission", ""),
                        rec.get("Currency", ""),
                        rec.get("Cookie Days", ""),
                        rec.get("Payout Rate", ""),
                        rec.get("Approval Rate", ""),
                    ),
                )


if __name__ == "__main__":
    app = App()
    app.mainloop()

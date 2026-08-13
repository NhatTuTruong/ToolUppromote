import csv
import ast
import asyncio
import json
import os
import random
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import re
import string
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, unquote, urlencode, urljoin, urlparse, urlunparse

import requests

from runtime_paths import app_dir

# Khi chạy .exe (frozen), sử dụng browsers từ thư mục bundle
if getattr(sys, "frozen", False):
    bundled_browsers = os.path.join(os.path.dirname(sys.executable), "ms-playwright")
    if os.path.isdir(bundled_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.abspath(bundled_browsers)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


BASE_DIR = app_dir()
ACTOR_ID = "aqPbs3KeH9aD8b22w"
# Collabs outside discovery: fallback khi actor Similarweb mặc định không trả traffic (tắt bằng COLLABS_OUTSIDE_SIMILARWEB_FALLBACK_ACTOR="").
DEFAULT_OUTSIDE_SIMILARWEB_FALLBACK_ACTOR = "radeance~similarweb-scraper"
MIN_VISITS = int(os.getenv("MIN_VISITS", "9000") or "9000")
TOP_KEYWORDS_COUNT = int(os.getenv("TOP_KEYWORDS_COUNT", "5") or "5")

# Mặc định cố định (không cấu hình qua UI/.env cho luồng chính)
DEFAULT_APIFY_MAX_DOMAINS_PER_RUN = 50
DEFAULT_UPPROMOTE_PAGE_DELAY_MS = 250
DEFAULT_GOAFFPRO_PAGE_DELAY_MS = 250
DEFAULT_REFERSION_PAGE_DELAY_MS = 250
DEFAULT_COLLABS_PAGE_DELAY_MS = 50
DEFAULT_OFFERS_PER_PAGE = 50
MAX_OFFERS_PER_PAGE = 50
MIN_OFFERS_PER_PAGE = 10
OFFERS_PER_PAGE_STEP = 10
DEFAULT_COLLABS_LIMIT = 12
# Shopify Collabs cursor pagination có giới hạn (API báo hasNextPage); vượt bằng chia searchQuery.
COLLABS_SHARD_FETCH_THRESHOLD = int(os.getenv("COLLABS_SHARD_FETCH_THRESHOLD", "900") or "900")
COLLABS_SHARD_ALPHABET = string.ascii_lowercase + string.digits
COLLABS_SHARD_MAX_PAGES = int(os.getenv("COLLABS_SHARD_MAX_PAGES", "120") or "120")
COLLABS_SHARD_MAX_DEPTH = int(os.getenv("COLLABS_SHARD_MAX_DEPTH", "2") or "2")
COLLABS_DISCOVERY_PAGES_PER_RUN = int(os.getenv("COLLABS_DISCOVERY_PAGES_PER_RUN", "3") or "3")


def clamp_offers_per_page(raw) -> int:
    """Số offer/trang (Up) hoặc limit request (Go): bội số của 10, trong [10, 50]. Rỗng/sai → mặc định."""
    if raw is None:
        return DEFAULT_OFFERS_PER_PAGE
    s = str(raw).strip()
    if not s:
        return DEFAULT_OFFERS_PER_PAGE
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return DEFAULT_OFFERS_PER_PAGE
    n = max(MIN_OFFERS_PER_PAGE, min(MAX_OFFERS_PER_PAGE, n))
    n = (n // OFFERS_PER_PAGE_STEP) * OFFERS_PER_PAGE_STEP
    if n < MIN_OFFERS_PER_PAGE:
        n = MIN_OFFERS_PER_PAGE
    return n


def clamp_collabs_limit(raw) -> int:
    """Collabs cố định 12 brand/request (giữ hàm để tương thích call-site cũ)."""
    return DEFAULT_COLLABS_LIMIT


def enforce_fixed_fetch_defaults() -> None:
    """Apify 50 domain/lần; Uppromote & Goaffpro trễ 250ms/trang; không giới hạn số trang; offer/trang (Up & Go) theo .env/UI đã chuẩn hóa."""
    os.environ["APIFY_MAX_DOMAINS_PER_RUN"] = str(DEFAULT_APIFY_MAX_DOMAINS_PER_RUN)
    os.environ["UPPROMOTE_PAGE_DELAY_MS"] = str(DEFAULT_UPPROMOTE_PAGE_DELAY_MS)
    os.environ.pop("UPPROMOTE_MAX_PAGES", None)
    os.environ["GOAFFPRO_PAGE_DELAY_MS"] = str(DEFAULT_GOAFFPRO_PAGE_DELAY_MS)
    os.environ.pop("GOAFFPRO_MAX_PAGES", None)
    os.environ["REFERSION_PAGE_DELAY_MS"] = str(DEFAULT_REFERSION_PAGE_DELAY_MS)
    os.environ.pop("REFERSION_MAX_PAGES", None)
    os.environ["COLLABS_PAGE_DELAY_MS"] = str(DEFAULT_COLLABS_PAGE_DELAY_MS)
    os.environ.pop("COLLABS_MAX_PAGES", None)
    os.environ["UPPROMOTE_PER_PAGE"] = str(clamp_offers_per_page(os.getenv("UPPROMOTE_PER_PAGE")))
    os.environ["GOAFFPRO_LIMIT"] = str(clamp_offers_per_page(os.getenv("GOAFFPRO_LIMIT")))
    os.environ["COLLABS_LIMIT"] = str(clamp_collabs_limit(os.getenv("COLLABS_LIMIT")))


def uppromote_max_pages_cap() -> int | None:
    """None = không giới hạn trang. Chỉ dùng khi UPPROMOTE_MAX_PAGES được set thủ công (CLI / thử nghiệm)."""
    raw = (os.getenv("UPPROMOTE_MAX_PAGES") or "").strip().lower()
    if not raw or raw in ("0", "unlimited", "none", "no", "inf"):
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n > 0 else None


def goaffpro_max_pages_cap() -> int | None:
    """None = không giới hạn trang Goaffpro."""
    raw = (os.getenv("GOAFFPRO_MAX_PAGES") or "").strip().lower()
    if not raw or raw in ("0", "unlimited", "none", "no", "inf"):
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n > 0 else None


def refersion_max_pages_cap() -> int | None:
    """None = không giới hạn trang Refersion."""
    raw = (os.getenv("REFERSION_MAX_PAGES") or "").strip().lower()
    if not raw or raw in ("0", "unlimited", "none", "no", "inf"):
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n > 0 else None


def collabs_max_pages_cap() -> int | None:
    """None = không giới hạn trang Shopify Collabs."""
    raw = (os.getenv("COLLABS_MAX_PAGES") or "").strip().lower()
    if not raw or raw in ("0", "unlimited", "none", "no", "inf"):
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n > 0 else None


# Uppromote / Goaffpro / Refersion: giới hạn số brand (record API) mỗi lần lọc trước khi chạy Apify.
DEFAULT_NET_SOURCES_MAX_BRANDS_PER_RUN = 200


def net_sources_max_brands_per_run() -> int:
    """
    Số brand tối đa tải từ API mỗi lần chạy (Uppromote, Goaffpro, Refersion).
    Ghi đè bằng biến môi trường UPPROMOTE_GOAFFPRO_REFERSION_MAX_BRANDS_PER_RUN (số nguyên dương).
    """
    raw = (os.getenv("UPPROMOTE_GOAFFPRO_REFERSION_MAX_BRANDS_PER_RUN") or "").strip()
    if not raw:
        return int(DEFAULT_NET_SOURCES_MAX_BRANDS_PER_RUN)
    try:
        n = int(raw)
    except ValueError:
        return int(DEFAULT_NET_SOURCES_MAX_BRANDS_PER_RUN)
    return max(1, min(5000, n))


def _unescape_dotenv_double_quoted(inner: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(inner):
        if inner[i] == "\\" and i + 1 < len(inner):
            n = inner[i + 1]
            if n == "n":
                out.append("\n")
            elif n == "r":
                out.append("\r")
            elif n == "t":
                out.append("\t")
            elif n in ('"', "\\"):
                out.append(n)
            else:
                out.append(inner[i])
                out.append(n)
            i += 2
            continue
        out.append(inner[i])
        i += 1
    return "".join(out)


def parse_env_file(path: Path) -> dict:
    """Đọc .env → dict. utf-8-sig (bỏ BOM); giá trị trong \"…\" được unescape chuẩn dotenv."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    text = path.read_text(encoding="utf-8-sig")
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        k = key.strip()
        v = val.strip()
        if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
            v = _unescape_dotenv_double_quoted(v[1:-1])
        elif len(v) >= 2 and v[0] == "'" and v[-1] == "'":
            v = v[1:-1]
        out[k] = v
    return out


def load_env_file(path: Path):
    for k, v in parse_env_file(path).items():
        if k and k not in os.environ:
            os.environ[k] = v
    try:
        from local_secret import migrate_uppromote_password_in_env

        if migrate_uppromote_password_in_env(path):
            print("[Env] Đã mã hóa UPPROMOTE_PASSWORD (dpapi) trong .env", flush=True)
    except Exception:
        pass


load_env_file(BASE_DIR / ".env")


API_URL_ENV_KEYS = (
    "UPPROMOTE_API_URL",
    "GOAFFPRO_API_URL",
    "REFERSION_API_URL",
    "COLLABS_API_URL",
)


def is_apify_api_token(value) -> bool:
    s = str(value or "").strip()
    return bool(s) and s.lower().startswith("apify_api_")


def is_http_api_url(value) -> bool:
    s = str(value or "").strip().lower()
    return s.startswith("http://") or s.startswith("https://")


def repair_misplaced_apify_tokens(env: dict) -> tuple[dict, list[str]]:
    """Chuyển token Apify bị ghi nhầm vào các ô URL sang APIFY_TOKENS."""
    out = dict(env or {})
    notes: list[str] = []
    tokens = parse_apify_tokens_list(out.get("APIFY_TOKENS"))
    seen = set(tokens)
    for key in API_URL_ENV_KEYS:
        val = str(out.get(key) or "").strip()
        if not val or not is_apify_api_token(val):
            continue
        if val not in seen:
            tokens.append(val)
            seen.add(val)
        out.pop(key, None)
        notes.append(f"Đã chuyển token Apify khỏi {key} sang APIFY_TOKENS.")
    for legacy_key in ("APIFY_TOKEN", "APIFY_TOKEN_BACKUP", "COLLABS_OUTSIDE_APIFY_TOKEN"):
        val = str(out.get(legacy_key) or "").strip()
        if val and val not in seen:
            tokens.append(val)
            seen.add(val)
    if tokens:
        out["APIFY_TOKENS"] = "\n".join(tokens)
        for legacy_key in ("APIFY_TOKEN", "APIFY_TOKEN_BACKUP", "COLLABS_OUTSIDE_APIFY_TOKEN"):
            out.pop(legacy_key, None)
    return out, notes


def validate_api_url_env(key: str, value: str) -> str | None:
    s = str(value or "").strip()
    if not s:
        return None
    if is_apify_api_token(s):
        return (
            f"{key} đang là token Apify (bị ghi nhầm). "
            "Token Apify chỉ điền vào APIFY_TOKENS; URL API phải bắt đầu bằng https://."
        )
    if not is_http_api_url(s):
        return f"{key} không hợp lệ (cần URL bắt đầu bằng http:// hoặc https://)."
    return None


def assert_uppromote_api_url(base_url: str) -> str:
    url = str(base_url or "").strip()
    if not url:
        raise RuntimeError("Thiếu UPPROMOTE_API_URL trong .env")
    err = validate_api_url_env("UPPROMOTE_API_URL", url)
    if err:
        raise RuntimeError(err)
    return url


def host_key(raw: str) -> str:
    if not raw:
        return ""
    value = str(raw).strip().lower()
    value = re.sub(r"^https?://", "", value, flags=re.I)
    value = value.split("/")[0]
    if value.startswith("www."):
        value = value[4:]
    return value


def parse_visits_value(raw) -> float:
    """Chuyển Visits từ Apify (số, chuỗi có dấu phẩy, đôi khi dạng 1.2M) sang float."""
    if raw is None:
        return 0.0
    if isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        s = raw.replace(",", "").replace("\u00a0", " ").strip()
        if not s:
            return 0.0
        s_lower = s.lower().strip()
        for suf, mul in (("k", 1e3), ("m", 1e6), ("b", 1e9)):
            if s_lower.endswith(suf) and len(s_lower) > 1:
                try:
                    return float(s_lower[:-1].strip()) * mul
                except ValueError:
                    break
        try:
            return float(s)
        except ValueError:
            return 0.0
    return 0.0


def apify_site_field(item: dict) -> str:
    """Tên site/domain trong item Apify (nhiều actor đặt tên khác nhau)."""
    if not item:
        return ""
    # Chuẩn hoá map key lowercase để hỗ trợ actor trả key khác kiểu chữ.
    low = {str(k).strip().lower(): v for k, v in item.items()}
    return (
        item.get("SiteName")
        or item.get("siteName")
        or item.get("Domain")
        or item.get("domain")
        or item.get("Website")
        or item.get("website")
        or item.get("Url")
        or item.get("url")
        or item.get("Site")
        or item.get("site")
        or low.get("sitename")
        or low.get("domain")
        or low.get("website")
        or low.get("url")
        or low.get("site")
        or ""
    )


def engagement_from_item(item: dict) -> dict:
    """Khối engagement / hoặc Visits nằm ngang item."""
    if not item:
        return {}
    low = {str(k).strip().lower(): v for k, v in item.items()}
    eng = (
        item.get("Engagments")
        or item.get("Engagements")
        or item.get("engagement")
        or low.get("engagments")
        or low.get("engagements")
        or low.get("engagement")
    )
    if isinstance(eng, dict) and eng:
        return eng
    # Một số actor để traffic nằm ngang item với key khác casing.
    if (
        item.get("Visits") is not None
        or item.get("VisitsFormatted") is not None
        or low.get("visits") is not None
        or low.get("visitsformatted") is not None
        or low.get("estimatedmonthlyvisits") is not None
        or low.get("monthlyvisits") is not None
    ):
        return item
    return {}


def parse_visits_from_engagement(eng: dict) -> float:
    if not eng:
        return 0.0
    low = {str(k).strip().lower(): v for k, v in eng.items()} if isinstance(eng, dict) else {}
    raw = eng.get("Visits") if isinstance(eng, dict) else None
    if raw is None:
        raw = (
            (eng.get("EstimatedVisits") if isinstance(eng, dict) else None)
            or (eng.get("Traffic") if isinstance(eng, dict) else None)
            or (eng.get("MonthlyVisits") if isinstance(eng, dict) else None)
            or low.get("visits")
            or low.get("estimatedvisits")
            or low.get("traffic")
            or low.get("monthlyvisits")
            or low.get("estimatedmonthlyvisits")
        )
    return parse_visits_value(raw)


def estimated_monthly_visits_formatted(item: dict, eng: dict | None = None) -> str:
    """Chuỗi traffic theo tháng từ Apify, ưu tiên field gốc trên item."""
    src_eng = eng if isinstance(eng, dict) else {}
    item_low = {str(k).strip().lower(): v for k, v in (item or {}).items()}
    eng_low = {str(k).strip().lower(): v for k, v in src_eng.items()}
    candidates = (
        (item or {}).get("EstimatedMonthlyVisitsFormatted"),
        src_eng.get("EstimatedMonthlyVisitsFormatted"),
        (item or {}).get("EstimatedMonthlyVisits"),
        src_eng.get("EstimatedMonthlyVisits"),
        item_low.get("estimatedmonthlyvisitsformatted"),
        eng_low.get("estimatedmonthlyvisitsformatted"),
        item_low.get("estimatedmonthlyvisits"),
        eng_low.get("estimatedmonthlyvisits"),
    )
    for v in candidates:
        if v is not None and str(v).strip():
            return format_estimated_monthly_visits(v)
    return ""


def visits_formatted_from_engagement(eng: dict | None) -> str:
    if not isinstance(eng, dict) or not eng:
        return ""
    low = {str(k).strip().lower(): v for k, v in eng.items()}
    raw = eng.get("VisitsFormatted") or low.get("visitsformatted")
    if raw is not None and str(raw).strip():
        return str(raw).strip()
    visits = parse_visits_from_engagement(eng)
    if visits <= 0:
        return ""
    if float(visits).is_integer():
        return str(int(visits))
    return f"{visits:.2f}".rstrip("0").rstrip(".")


def _first_non_empty_value(*values):
    for v in values:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        return v
    return None


def format_visit_duration_cell(raw) -> str:
    """Chuẩn hoá thời gian ở lại (giây hoặc chuỗi có sẵn) để hiển thị Excel."""
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    if re.search(r"[a-zA-Z]", s) and not re.fullmatch(r"-?\d+(?:[.,]\d+)?", s):
        return s
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", s):
        parts = [int(x) for x in s.split(":")]
        if len(parts) == 2:
            sec = parts[0] * 60 + parts[1]
        else:
            sec = parts[0] * 3600 + parts[1] * 60 + parts[2]
        if sec <= 0:
            return ""
        raw = sec
        s = str(sec)
    try:
        sec_f = float(str(raw).replace(",", "."))
    except ValueError:
        return s
    if sec_f <= 0:
        return ""
    sec_i = int(round(sec_f))
    if sec_i < 60:
        return f"{sec_i}s"
    minutes, seconds = divmod(sec_i, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        if seconds:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes:
            return f"{hours}h {minutes}m"
        return f"{hours}h"
    if seconds:
        return f"{minutes}m {seconds}s"
    return f"{minutes}m"


def visit_duration_from_item(item: dict | None, eng: dict | None = None) -> str:
    """Thời gian ở lại (visit duration) từ Similarweb / Apify."""
    src_item = item if isinstance(item, dict) else {}
    src_eng = eng if isinstance(eng, dict) else engagement_from_item(src_item)
    item_low = {str(k).strip().lower(): v for k, v in src_item.items()}
    eng_low = {str(k).strip().lower(): v for k, v in (src_eng or {}).items()}
    eng_in = src_item.get("engagement") or src_item.get("Engagement") or {}
    if not isinstance(eng_in, dict):
        eng_in = {}
    eng_in_low = {str(k).strip().lower(): v for k, v in eng_in.items()}
    raw = _first_non_empty_value(
        src_eng.get("TimeOnSite"),
        src_eng.get("timeOnSite"),
        src_eng.get("VisitDuration"),
        src_eng.get("AvgVisitDuration"),
        src_eng.get("avgVisitDuration"),
        src_eng.get("AvgVisitDurationSeconds"),
        src_eng.get("avgVisitDurationSeconds"),
        src_eng.get("AverageVisitDuration"),
        src_eng.get("TimeOnSiteFormatted"),
        src_eng.get("AvgVisitDurationFormatted"),
        eng_low.get("timeonsite"),
        eng_low.get("visitduration"),
        eng_low.get("avgvisitduration"),
        eng_low.get("avgvisitdurationseconds"),
        src_item.get("TimeOnSite"),
        src_item.get("timeOnSite"),
        src_item.get("VisitDuration"),
        src_item.get("AvgVisitDuration"),
        src_item.get("avgVisitDuration"),
        src_item.get("AvgVisitDurationSeconds"),
        src_item.get("avgVisitDurationSeconds"),
        src_item.get("AverageVisitDuration"),
        src_item.get("TimeOnSiteFormatted"),
        src_item.get("AvgVisitDurationFormatted"),
        item_low.get("timeonsite"),
        item_low.get("visitduration"),
        item_low.get("avgvisitduration"),
        item_low.get("avgvisitdurationseconds"),
        eng_in.get("timeOnSite"),
        eng_in.get("TimeOnSite"),
        eng_in.get("avgVisitDuration"),
        eng_in.get("avgVisitDurationSeconds"),
        eng_in_low.get("timeonsite"),
        eng_in_low.get("avgvisitduration"),
        eng_in_low.get("avgvisitdurationseconds"),
    )
    return format_visit_duration_cell(raw)


def format_estimated_monthly_visits(raw) -> str:
    """
    Chuẩn hóa traffic theo tháng:
    {'2026-01-01': '577', '2026-02-01': '226'} -> T1(577), T2(226)
    """
    if raw is None:
        return ""
    obj = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ""
        obj = text
        if text.startswith("{") and text.endswith("}"):
            try:
                obj = json.loads(text)
            except Exception:
                try:
                    obj = ast.literal_eval(text)
                except Exception:
                    obj = text
    if isinstance(obj, dict):
        parts = []
        for k in sorted(obj.keys(), key=lambda x: str(x)):
            key_text = str(k)
            month_match = re.search(r"-(\d{2})-", key_text)
            month_label = f"T{int(month_match.group(1))}" if month_match else key_text
            v = obj.get(k)
            value_text = "" if v is None else str(v).strip()
            parts.append(f"{month_label}({value_text})")
        return ", ".join(parts)
    return str(obj).strip()


def _highlight_max_monthly_traffic(cell, raw_text: str) -> None:
    """
    Tô đỏ phần tháng có traffic lớn nhất trong chuỗi:
    T1(577), T2(226), T3(314)
    """
    text = (raw_text or "").strip()
    if not text:
        return
    matches = list(re.finditer(r"(T\d+\()([^)]+)(\))", text))
    if not matches:
        return

    parsed = []
    for m in matches:
        num_txt = (m.group(2) or "").replace(",", "").strip()
        try:
            val = float(num_txt)
        except ValueError:
            continue
        parsed.append((m.span(), val))
    if not parsed:
        return
    max_val = max(v for _, v in parsed)
    max_spans = [span for span, v in parsed if v == max_val]
    if not max_spans:
        return

    from openpyxl.styles import Font
    # Dùng cách an toàn cho mọi bản openpyxl: tô đỏ toàn bộ ô khi có max.
    # (Tránh rich text gây lỗi save trên một số môi trường.)
    if max_spans:
        cell.font = Font(color="FF0000")


def lookup_apify_item(url: str, by_host: dict) -> dict:
    """Ghép offer URL với bản ghi Apify (khớp host + quét fallback)."""
    if not by_host:
        return {}
    k = host_key(url)
    if not k:
        return {}
    if k in by_host:
        return by_host[k]
    for item in by_host.values():
        sk = host_key(apify_site_field(item))
        if sk and sk == k:
            return item
    return {}


def normalize_bearer(raw: str) -> str:
    if raw is None:
        return ""
    token = str(raw).strip().replace("\r", "")
    if (token.startswith('"') and token.endswith('"')) or (token.startswith("'") and token.endswith("'")):
        token = token[1:-1].strip()
    token = re.sub(r"^Bearer\s+", "", token, flags=re.I)
    return token


def build_uppromote_headers() -> dict:
    token = normalize_bearer(os.getenv("UPPROMOTE_BEARER_TOKEN", ""))
    if not token:
        raise RuntimeError("Thiếu UPPROMOTE_BEARER_TOKEN trong .env")
    return {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "user-agent": os.getenv(
            "UPPROMOTE_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        ),
    }


def build_goaffpro_headers() -> dict:
    token = normalize_bearer(os.getenv("GOAFFPRO_BEARER_TOKEN", ""))
    if not token:
        raise RuntimeError("Thiếu GOAFFPRO_BEARER_TOKEN trong .env")
    return {
        "accept": "application/json",
        "authorization": f"Bearer {token}",
        "user-agent": os.getenv(
            "GOAFFPRO_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        ),
    }


def build_refersion_headers() -> dict:
    token = normalize_bearer(os.getenv("REFERSION_TOKEN", ""))
    if not token:
        raise RuntimeError("Thiếu REFERSION_TOKEN trong .env")
    return {
        "accept": "application/json",
        "origin": os.getenv("REFERSION_ORIGIN", "https://marketplace.refersion.com"),
        "referer": os.getenv("REFERSION_REFERER", "https://marketplace.refersion.com/"),
        "refersion-token": token,
        "user-agent": os.getenv(
            "REFERSION_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        ),
    }


def build_collabs_headers() -> dict:
    cookie = (os.getenv("COLLABS_COOKIE") or "").strip()
    csrf = (os.getenv("COLLABS_CSRF_TOKEN") or "").strip()
    if not cookie:
        raise RuntimeError("Thiếu COLLABS_COOKIE trong .env")
    if not csrf:
        raise RuntimeError("Thiếu COLLABS_CSRF_TOKEN trong .env")
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "cookie": cookie,
        "origin": os.getenv("COLLABS_ORIGIN", "https://collabs.shopify.com"),
        "referer": os.getenv("COLLABS_REFERER", "https://collabs.shopify.com/"),
        "x-client-type": os.getenv("COLLABS_CLIENT_TYPE", "web"),
        "x-csrf-token": csrf,
        "user-agent": os.getenv(
            "COLLABS_USER_AGENT",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
        ),
    }


COLLABS_BRANDS_QUERY = (
    "query BrandsQuery($first: Int, $last: Int, $after: String, $before: String, "
    "$brandValues: [BrandValue!], $categories: [ProductCategory!], "
    "$productCategories: [CreatorProductCategory!], $saved: Boolean, $searchQuery: String) {"
    " socialAccounts { id __typename }"
    " brandsNetworkSearch("
    "   first: $first"
    "   last: $last"
    "   after: $after"
    "   before: $before"
    "   brandValues: $brandValues"
    "   categories: $categories"
    "   productCategories: $productCategories"
    "   saved: $saved"
    "   searchQuery: $searchQuery"
    " ) {"
    "   totalCount"
    "   pageInfo { hasNextPage hasPreviousPage endCursor startCursor __typename }"
    "   nodes {"
    "     id"
    "     ... on BrandInterface {"
    "       name"
    "       logoUrl"
    "       images"
    "       backgroundColor"
    "       shopifyStore { id shopifyStoreId __typename }"
    "       saved"
    "       partnershipStatus"
    "       productCategory"
    "       networkCommissionRange"
    "       partnershipState"
    "       targetCountries"
    "       previouslyPurchased"
    "       __typename"
    "     }"
    "     __typename"
    "   }"
    "   __typename"
    " }"
    "}"
)

COLLABS_BRAND_PROFILE_QUERY = (
    "query DiscoverBrandProfileQuery($shopifyStoreId: GID!) {"
    " socialAccounts { id __typename }"
    " brand(shopifyStoreId: $shopifyStoreId) {"
    "   id"
    "   ... on BrandInterface {"
    "     name"
    "     holdingPeriod"
    "     socialLinks { platform url __typename }"
    "     shopifyStore { id shopifyStoreId __typename }"
    "     __typename"
    "   }"
    "   __typename"
    " }"
    " creator { submittedApplications submittedApplicationsLimit __typename }"
    "}"
)

COLLABS_PRODUCTS_QUERY = (
    "query ProductsQuery($searchParams: ProductsSearchInput!, $first: Int, $last: Int, "
    "$after: String, $before: String, $seed: String!) {"
    " socialAccounts { id __typename }"
    " products("
    "   searchParams: $searchParams"
    "   first: $first"
    "   last: $last"
    "   after: $after"
    "   before: $before"
    "   seed: $seed"
    " ) {"
    "   nodes {"
    "     id"
    "     url"
    "     minPrice { amount currency __typename }"
    "     maxPrice { amount currency __typename }"
    "     affiliateProduct { id saved active url __typename }"
    "     shopifyStore { name shopifyStoreId __typename }"
    "     __typename"
    "   }"
    "   totalCount"
    "   pageInfo { hasNextPage hasPreviousPage endCursor startCursor __typename }"
    "   __typename"
    " }"
    "}"
)

COLLABS_CATEGORY_LABELS = {
    "CLOTHING_AND_ACCESSORIES": "Clothing and accessories",
    "WOMENS_CLOTHING": "Women's clothing and accessories",
    "MENS_CLOTHING": "Men's clothing and accessories",
    "BEAUTY": "Beauty",
    "HEALTH_AND_WELLNESS": "Health and wellness",
    "FOOD_AND_DRINK": "Food and drink",
    "HOME_GOODS_AND_DECOR": "Home goods and decor",
    "BABY_AND_TODDLER": "Baby and toddler",
    "ELECTRONICS": "Electronics",
    "SPORTS_GOODS": "Sports goods",
    "ARTS_AND_CRAFTS": "Arts and crafts",
    "TECH": "Tech",
    "PHOTOGRAPHY": "Photography",
    "PET_SUPPLIES_AND_ACCESSORIES": "Pet supplies and accessories",
    "DIY": "DIY",
    "AUTOMOTIVE": "Automotive",
    "GARDENING": "Gardening",
    "TOBACCO_AND_VAPE": "Tobacco and vape",
    "MATURE": "Mature",
    "MUSICAL_INSTRUMENTS_AND_ACCESSORIES": "Musical instruments and accessories",
}


def collabs_category_label(raw_code: str) -> str:
    code = str(raw_code or "").strip().upper()
    if not code:
        return ""
    return COLLABS_CATEGORY_LABELS.get(code, code)


def norm_collabs_product_categories(raw) -> list[str]:
    """Chuẩn hóa mã CreatorProductCategory cho GraphQL productCategories."""
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        code = str(item or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        out.append(code)
    return out


def format_collabs_holding_period(raw) -> str:
    """Chuẩn hóa holding period: số -> thêm ' day'."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    low = s.lower()
    if "day" in low:
        return s
    try:
        n = float(s.replace(",", ""))
    except ValueError:
        return s
    if abs(n - round(n)) < 1e-9:
        return f"{int(round(n))} day"
    return f"{n:g} day"


UPPROMOTE_CATEGORY_API_IDS: dict[str, int] = {
    "Art": 9,
    "Adult products": 20,
    "Automobiles & Motorcycles": 13,
    "Baby & Toddler": 30,
    "Beauty & Health": 3,
    "Books": 10,
    "Bundles": 31,
    "Business & Industrial": 32,
    "Business & Professional services": 21,
    "Cameras & Optics": 33,
    "Computers & Office": 14,
    "Education & Training": 22,
    "Electronics": 15,
    "Fashion": 1,
    "Furniture": 23,
    "Gaming": 18,
    "Garden & Outdoors": 6,
    "Gift Cards": 34,
    "Grocery & Food": 7,
    "Hardware": 35,
    "Home & Tools": 5,
    "Jewelry & Accessories": 2,
    "Luggage & Bags": 36,
    "Media": 24,
    "Mom & Kids": 11,
    "Pet supplies": 8,
    "Phone & Telecommunication": 16,
    "Product Add-Ons": 37,
    "Religion & Spirituality": 25,
    "Retail & Consumer goods": 26,
    "Software & Digital products": 17,
    "Sports & Entertainment": 4,
    "Tobacco products": 27,
    "Toys & Hobbies": 12,
    "Travel": 28,
    "Vehicles & Parts": 38,
    "Wellness & Lifestyle": 29,
    "Others": 19,
    "Uncategorized": 39,
}


def _truthy_filter_flag(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def uppromote_category_api_ids_from_filters(filters: dict | None) -> list[int]:
    if not filters or not _truthy_filter_flag(filters.get("filter_by_category")):
        return []
    names = filters.get("categories") or filters.get("category") or []
    if isinstance(names, str):
        names = [names]
    ids: list[int] = []
    seen: set[int] = set()
    for raw_name in names:
        name = str(raw_name or "").strip()
        if not name:
            continue
        cid = UPPROMOTE_CATEGORY_API_IDS.get(name)
        if cid is None or cid in seen:
            continue
        seen.add(cid)
        ids.append(cid)
    return ids


def with_page(url: str, page: int, category_ids: list[int] | None = None) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    # Always force per_page from env for consistent paging.
    query["per_page"] = os.getenv("UPPROMOTE_PER_PAGE", str(DEFAULT_OFFERS_PER_PAGE))
    for key in list(query):
        if key == "categories" or key.startswith("categories["):
            del query[key]
    if category_ids:
        for idx, cid in enumerate(category_ids):
            query[f"categories[{idx}]"] = str(int(cid))
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def offer_url_from_uppromote(offer: dict) -> str:
    website = offer.get("website")
    if isinstance(website, str) and website.strip():
        return website.strip()
    domain = offer.get("myshopify_domain")
    if isinstance(domain, str) and domain.strip():
        return f"https://{domain.strip()}"
    apply_url = offer.get("apply_url")
    if isinstance(apply_url, str) and apply_url.strip():
        return apply_url.strip()
    return ""


def fetch_uppromote_offer_detail(shop_id, _retry_after_login: bool = False) -> dict:
    base = (os.getenv("UPPROMOTE_DETAIL_BASE_URL") or "https://mkp-api.uppromote.com").strip().rstrip("/")
    url = f"{base}/api/v1/marketplace-offer/offer-detail/{shop_id}?mobile=false"
    res = requests.get(url, headers=build_uppromote_headers(), timeout=60)
    text = res.text

    # 401 → thử auto-login rồi retry một lần
    if res.status_code == 401 and not _retry_after_login:
        _uppromote_ui_log("Token hết hạn (401) — đang tự động đăng nhập lại (Edge ẩn)...")
        if _auto_login_uppromote_browser():
            _uppromote_ui_log("Đăng nhập lại thành công — token đã cập nhật, tiếp tục tải offer.")
            return fetch_uppromote_offer_detail(shop_id, _retry_after_login=True)
        raise RuntimeError("Uppromote auto-login thất bại, không lấy được token mới.")

    try:
        body = res.json()
    except Exception as exc:
        raise RuntimeError(f"Uppromote detail parse JSON lỗi (HTTP {res.status_code}): {text[:180]}") from exc
    if not res.ok:
        raise RuntimeError(f"Uppromote detail HTTP {res.status_code}: {text[:300]}")
    if body.get("status") not in (200, "200"):
        raise RuntimeError(f"Uppromote detail API lỗi: {text[:300]}")
    return body.get("data") or {}


def with_goaffpro_paging(url: str, offset: int, limit: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["limit"] = str(limit)
    query["offset"] = str(offset)
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def _portal_string(store: dict) -> str:
    raw = (
        store.get("affiliatePortal")
        or store.get("affiliate_portal")
        or store.get("AffiliatePortal")
        or ""
    )
    if raw is None:
        return ""
    if not isinstance(raw, str):
        raw = str(raw)
    return raw.strip()


def goaffpro_apply_url(store: dict) -> str:
    """Base URL https://{token}.goaffpro.com từ chuỗi affiliatePortal (mọi biến thể API)."""
    portal = _portal_string(store)
    if not portal:
        return ""
    # Đã là URL đầy đủ
    m = re.search(r"https?://([a-z0-9_-]+)\.goaffpro\.com/?", portal, re.I)
    if m:
        return f"https://{m.group(1).lower()}.goaffpro.com"
    # {goaffpro_public_token:xxx,...}.goaffpro.com
    m = re.search(r"goaffpro_public_token:\s*([^,}\s]+)", portal, re.I)
    if m:
        token = m.group(1).strip()
        if token:
            return f"https://{token}.goaffpro.com"
    # Token chỉ có chữ/số trước .goaffpro.com (một số response rút gọn)
    m = re.search(r"\b([a-z0-9_-]{2,64})\.goaffpro\.com\b", portal, re.I)
    if m:
        return f"https://{m.group(1).lower()}.goaffpro.com"
    return ""


def affiliate_portal_raw_from_offer(offer: dict) -> str:
    return (
        (offer.get("goaff_affiliate_portal") or "").strip()
        or (offer.get("affiliatePortal") or "").strip()
        or (offer.get("affiliate_portal") or "").strip()
    )


def goaff_create_account_url(offer: dict) -> str:
    """Chỉ từ affiliatePortal (API): https://sub.goaffpro.com/create-account — không dùng website."""
    portal_raw = affiliate_portal_raw_from_offer(offer)
    if not portal_raw:
        return ""
    base = goaffpro_apply_url({"affiliatePortal": portal_raw}).strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/create-account"):
        return base
    return f"{base}/create-account"


def format_goaff_commission_amount_display(offer: dict) -> str:
    """Số tiền HH kèm đơn vị: % hoặc tiền tệ ($, …) theo loại hoa hồng."""
    raw = offer.get("goaff_commission_amount")
    if raw is None or raw == "":
        return ""
    typ = (offer.get("goaff_commission_type") or "").strip().lower()
    cur = (offer.get("currency") or "").strip().upper()
    try:
        num = float(raw)
    except (TypeError, ValueError):
        return str(raw)
    if typ == "percentage" or "percent" in typ:
        return f"{num:g}%"
    if typ in ("fixed", "flat", "amount") or "fixed" in typ:
        if cur == "USD":
            return f"${num:g}"
        if cur == "EUR":
            return f"€{num:g}"
        if cur == "GBP":
            return f"£{num:g}"
        if cur == "VND":
            return f"{num:,.0f} ₫"
        if cur:
            return f"{num:g} {cur}"
        return f"${num:g}"
    if cur == "USD":
        return f"${num:g}"
    if cur:
        return f"{num:g} {cur}"
    return f"{num:g}"


def fmt_yes_no_01(val) -> str:
    if val in (1, "1", True):
        return "Có"
    if val in (0, "0", False):
        return "Không"
    return ""


def fmt_yes_no_bool_like(val) -> str:
    """Chuẩn hóa bool/0/1/"true"/"false" -> Có/Không cho cột trạng thái."""
    if val is None:
        return ""
    if isinstance(val, bool):
        return "Có" if val else "Không"
    if isinstance(val, (int, float)):
        return "Có" if int(val) != 0 else "Không"
    s = str(val).strip().lower()
    if not s:
        return ""
    if s in ("1", "true", "yes", "y", "on"):
        return "Có"
    if s in ("0", "false", "no", "n", "off"):
        return "Không"
    return str(val)


def fmt_refersion_scalar(value) -> str:
    """Giữ dữ liệu Refersion dạng chuỗi gọn cho Excel (list/dict -> text)."""
    if value is None:
        return ""
    if isinstance(value, list):
        return join_list(value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def refersion_active_from_denied(denied) -> str:
    """Hoạt động = phủ định của denied."""
    if denied is None:
        return ""
    if isinstance(denied, bool):
        return "Có" if not denied else "Không"
    if isinstance(denied, (int, float)):
        return "Có" if int(denied) == 0 else "Không"
    s = str(denied).strip().lower()
    if not s:
        return ""
    if s in ("1", "true", "yes", "y", "on"):
        return "Không"
    if s in ("0", "false", "no", "n", "off"):
        return "Có"
    return ""


def cookie_days_from_goaffpro(raw) -> str | int | float:
    if raw is None:
        return ""
    try:
        v = float(raw)
    except Exception:
        return ""
    if v > 86400 * 2:
        days = v / 86400.0
        return int(days) if days == int(days) else round(days, 2)
    return int(v) if v == int(v) else v


def commission_str_goaffpro(comm: dict | None) -> str:
    if not isinstance(comm, dict):
        return ""
    typ = (comm.get("type") or "").lower()
    amount = comm.get("amount")
    on = (comm.get("on") or "").strip()
    if typ == "percentage" and amount is not None:
        base = f"{amount}%"
        return f"{base} ({on})" if on else base
    if amount is not None:
        extra = f" {typ}" if typ else ""
        on_part = f" on {on}" if on else ""
        return f"{amount}{extra}{on_part}".strip()
    return ""


def commission_type_goaffpro(comm: dict | None) -> str:
    if not isinstance(comm, dict):
        return ""
    parts = [str(comm.get("type") or "").strip(), str(comm.get("on") or "").strip()]
    return " ".join(p for p in parts if p)


def map_goaffpro_store(store: dict) -> dict:
    website = store.get("website")
    url = website.strip() if isinstance(website, str) and website.strip() else ""
    name_raw = store.get("name")
    brand = ""
    if isinstance(name_raw, str) and name_raw.strip() and not name_raw.strip().lower().startswith("http"):
        brand = name_raw.strip()
    elif url:
        hk = host_key(url)
        brand = hk.replace(".", " ").title() if hk else url
    comm = store.get("commission") if isinstance(store.get("commission"), dict) else {}
    app_auto = store.get("isApprovedAutomatically")
    if app_auto == 1:
        application_review = "auto"
    elif app_auto == 0:
        application_review = "manual"
    else:
        application_review = ""
    return {
        "brand": brand,
        "url": url,
        "offer": commission_str_goaffpro(comm),
        "cookieDays": cookie_days_from_goaffpro(store.get("cookieDuration")),
        "client_url": goaffpro_apply_url(store) or "",
        "offer_id": store.get("id") or "",
        "shop_id": store.get("id") or "",
        "program_id": "",
        "mkp_listing_id": store.get("id") or "",
        "commission_type": commission_type_goaffpro(comm),
        "category": "",
        "epc": "",
        "payments": "",
        "currency": store.get("currency") or "",
        "payout_rate": "",
        "approval_rate": "",
        "offer_score": "",
        "recommend_score": "",
        "application_review": application_review,
        "promotion_details": [],
        "target_audience_customer_channels": [],
        "target_audience_locations": [],
        "target_audience_ages": [],
        "target_audience_genders": [],
        "can_apply_offer": None,
        "is_applied_offer": None,
        # Raw Goaff API fields (CSV / snapshot)
        "goaff_id": store.get("id", ""),
        "goaff_name": (name_raw.strip() if isinstance(name_raw, str) else "") or "",
        "goaff_logo": store.get("logo") or "",
        "goaff_affiliate_portal": _portal_string(store),
        "goaff_cookie_duration_sec": store.get("cookieDuration", ""),
        "goaff_are_registrations_open": store.get("areRegistrationsOpen", ""),
        "goaff_is_approved_automatically": store.get("isApprovedAutomatically", ""),
        "goaff_commission_type": comm.get("type", "") if comm else "",
        "goaff_commission_amount": comm.get("amount", "") if comm else "",
        "goaff_commission_on": comm.get("on", "") if comm else "",
    }


def map_refersion_offer(offer: dict) -> dict:
    category_raw = offer.get("category")
    if category_raw in (None, ""):
        category_raw = offer.get("categories")
    denied_raw = offer.get("denied")
    pending_raw = offer.get("pending")
    payments_raw = offer.get("payments")
    return {
        "brand": offer.get("brand") or "",
        "url": offer.get("url") or "",
        "offer": offer.get("offer") or "",
        "cookieDays": offer.get("cookieDays") or "",
        "client_url": offer.get("client_url") or "",
        "offer_id": offer.get("offer_id") or "",
        "shop_id": offer.get("client_id") or "",
        "program_id": offer.get("id") or "",
        "mkp_listing_id": offer.get("id") or "",
        "commission_type": offer.get("commission_type") or "",
        "category": fmt_refersion_scalar(category_raw),
        "epc": offer.get("epc") or "",
        "payments": fmt_refersion_scalar(payments_raw),
        "currency": offer.get("client_currency_symbol") or "",
        "payout_rate": "",
        "approval_rate": "",
        "offer_score": "",
        "recommend_score": "",
        "application_review": "",
        "promotion_details": [],
        "target_audience_customer_channels": [],
        "target_audience_locations": [],
        "target_audience_ages": [],
        "target_audience_genders": [],
        "can_apply_offer": offer.get("applied"),
        "is_applied_offer": offer.get("applied"),
        "refersion_id": offer.get("id") or "",
        "refersion_client_id": offer.get("client_id") or "",
        "refersion_offer_id": offer.get("offer_id") or "",
        "refersion_visible_url": offer.get("visible_url") or "",
        "refersion_payments": fmt_refersion_scalar(payments_raw),
        "refersion_category": fmt_refersion_scalar(category_raw),
        "refersion_denied": denied_raw,
        "refersion_pending": pending_raw,
    }


def _collabs_storefront_url(social_links) -> str:
    if not isinstance(social_links, list):
        return ""
    for item in social_links:
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform") or "").strip().upper()
        if platform != "STOREFRONT":
            continue
        url = str(item.get("url") or "").strip()
        if url.startswith("http://") or url.startswith("https://"):
            return url
    return ""


def _collabs_brand_url(node: dict, detail_brand: dict | None = None) -> str:
    # Ưu tiên domain storefront từ API detail, vì list query không trả website đầy đủ.
    if isinstance(detail_brand, dict):
        storefront_url = _collabs_storefront_url(detail_brand.get("socialLinks"))
        if storefront_url:
            return storefront_url
    # Fallback cũ: map sang myshopify khi chỉ có store id.
    store = node.get("shopifyStore") if isinstance(node.get("shopifyStore"), dict) else {}
    sid = str(store.get("shopifyStoreId") or "").strip()
    if sid and sid.isdigit():
        return f"https://{sid}.myshopify.com"
    return ""


def map_collabs_brand(node: dict, detail_brand: dict | None = None) -> dict:
    name = str(node.get("name") or "").strip()
    commission = node.get("networkCommissionRange")
    if commission in (None, ""):
        offer = ""
    else:
        offer = f"{commission}%"
    category_code = str(node.get("productCategory") or "").strip().upper()
    return {
        "brand": name,
        "url": _collabs_brand_url(node, detail_brand),
        "product_link": "",
        "offer": offer,
        "cookieDays": "",
        "client_url": "",
        "offer_id": node.get("id") or "",
        "shop_id": (node.get("shopifyStore") or {}).get("id") if isinstance(node.get("shopifyStore"), dict) else "",
        "program_id": "",
        "mkp_listing_id": node.get("id") or "",
        "commission_type": "network_commission_range",
        "category": collabs_category_label(category_code),
        "collabs_product_category_code": category_code,
        "epc": "",
        "payments": "",
        "currency": "",
        "payout_rate": "",
        "approval_rate": "",
        "offer_score": "",
        "recommend_score": "",
        "application_review": "",
        "promotion_details": [],
        "target_audience_customer_channels": [],
        "target_audience_locations": [],
        "target_audience_ages": [],
        "target_audience_genders": [],
        "can_apply_offer": None,
        "is_applied_offer": None,
        "collabs_partnership_status": node.get("partnershipStatus") or "",
        "collabs_partnership_state": node.get("partnershipState") or "",
        "collabs_saved": node.get("saved"),
        "collabs_previously_purchased": node.get("previouslyPurchased"),
        "collabs_target_countries": join_list(node.get("targetCountries") or []),
        "collabs_logo_url": node.get("logoUrl") or "",
        "collabs_images": join_list(node.get("images") or []),
        "collabs_shopify_store_id": ((node.get("shopifyStore") or {}).get("shopifyStoreId") if isinstance(node.get("shopifyStore"), dict) else ""),
        "collabs_holding_period": (detail_brand.get("holdingPeriod") if isinstance(detail_brand, dict) else ""),
    }


def collabs_shopify_store_gid(node: dict) -> str:
    store = node.get("shopifyStore") if isinstance(node.get("shopifyStore"), dict) else {}
    raw_id = str(store.get("id") or "").strip()
    if not raw_id:
        return ""
    if raw_id.startswith("gid://"):
        return raw_id
    return f"gid://dovetale-api/ShopifyStore/{raw_id}"


def resolve_redirected_url(storefront_url: str, timeout_sec: int = 20) -> str:
    """
    Lấy domain chính của store từ /meta.json endpoint.
    Shopify stores thường redirect storefront URL sang domain khác.
    /meta.json không bị redirect chain, trả về JSON chứa domain thật.

    Trả về URL domain chính (https://domain-thuc) hoặc chuỗi rỗng nếu fail.
    """
    raw = str(storefront_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if not parsed.netloc:
        return ""
    if not parsed.scheme:
        parsed = parsed._replace(scheme="https")
    meta_url = f"{parsed.scheme}://{parsed.netloc}/meta.json"
    try:
        res = requests.get(meta_url, timeout=timeout_sec, verify=False)
        if res.status_code == 200:
            data = res.json()
            domain = data.get("domain") or data.get("url", "").replace("https://", "").replace("http://", "").rstrip("/")
            if domain:
                return f"https://{domain}"
        return ""
    except Exception:
        return ""


def _collabs_html_has_outside_cta_phrases(low_html: str) -> bool:
    """
    CTA trên trang (low_html = HTML đã .lower()).
    Logic **HOẶC**: chỉ cần xuất hiện **một** trong các nhóm dưới → True.
    - apply now hoặc apply-now
    - chứa chuỗi con join (joining, rejoin, joint, …)
    - sign up
    - partner with us
    - get started
    - join community
    """
    if not low_html:
        return False
    return any(
        (
            ("apply now" in low_html or "apply-now" in low_html),
            ("join" in low_html),
            ("sign up" in low_html),
            ("partner with us" in low_html),
            ("get started" in low_html),
            ("join community" in low_html),
        )
    )


def _collabs_page_looks_like_signup(html: str, url: str = "") -> bool:
    text = (html or "").lower()
    u = (url or "").lower()
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html or "", flags=re.I | re.S)
    title_text = (title_match.group(1).strip().lower() if title_match else "")
    if "class=\"collabs-page__main\"" in text or "class='collabs-page__main'" in text:
        return True
    if "community" in title_text:
        return True
    signup_path_hints = (
        "/pages/collab",
        "/pages/collabs",
        "/pages/collabs-signup",
        "/pages/partnerships",
        "/pages/ambassador",
        "/pages/affiliate",
        "/pages/affiliates",
        "/pages/collaborators",
        "/pages/affiliate-program",
        "/pages/affiliate-programs",
        "/pages/ambassadors",
        "/pages/ambassador-program",
        "/pages/ambassador-programs",
        "/pages/collaboration",
        "/pages/partners",
        "/pages/partner-program",
        "/pages/partner-programs",
        "/pages/collaborations",
        "/pages/curious-community",
        "/pages/shopify-collabs",
        "/ambassadors",
        "/ambassador",
        "/community",
        "/affiliates",
        "/affiliate",
        "/affiliate-program",
        "/affiliate-programs",
        "/collab",
        "/collabs",
        "/collaborators",
        "/partnerships",
        "/partners",
        "/partner",
        "/partner-program",
        "/partner-programs",
        "/collaborations",
        "/collaboration",
        "/ambassador-program",
        "/ambassador-programs",
        "/curious-community",
        "-com",
        "ambassadors",
        "ambassador",
        "community",
        "affiliates",
        "affiliate",
        "affiliate-program",
        "affiliate-programs",
        "collab",
        "collabs",
        "collaborators",
        "partnerships",
        "partners",
        "partner",
        "partner-program",
        "partner-programs",
        "collaborations",
        "collaboration",
        "ambassador-program",
        "ambassador-programs",
        "curious-community"
    )
    if any(p in u for p in signup_path_hints):
        return True
    if _collabs_html_has_outside_cta_phrases(text):
        return True
    score = 0
    if "collab" in text:
        score += 1
    if "affiliate" in text:
        score += 1
    if "apply" in text or "application" in text:
        score += 1
    return score >= 2


def _collabs_page_has_signup_cta(html: str) -> bool:
    """
    Tiêu chí đúng cho trang đăng ký Collabs:
    page phải có element: <div class="collabs-page__cta ..."> (hoặc single-quote).
    """
    h = html or ""
    return bool(
        re.search(
            r"""<div[^>]*\bclass\s*=\s*["'][^"']*\bcollabs-page__cta\b[^"']*["'][^>]*>""",
            h,
            flags=re.I,
        )
    )


# Keywords dùng để nhận diện trang có tín hiệu affiliate (title + body text)
_AFFILIATE_TEXT_KW = (
    "affiliate", "ambassador", "partner", "referral", "influencer",
    "creator program", "collab program", "affiliate program", "partner program",
    "referral program", "affiliate registration", "join our affiliate",
    "become an affiliate", "sign up as partner", "apply to be an ambassador",
    "become an ambassador", "apply as influencer", "creator signup",
    "influencer signup", "affiliate signup", "partner signup",
    "affiliate-enroll", "ambassador-enroll", "partner-enroll",
    "affiliate-enquiry", "ambassador-enquiry", "partner-enquiry",
)

# Keywords cho form/button signup trong affiliate context
_AFFILIATE_FORM_KW = (
    "form", "input", "textarea", "select",
)

# Button text thường có trên trang affiliate signup
_AFFILIATE_BTN_KW = (
    "submit", "apply", "register", "sign up", "join", "enroll",
    "become an affiliate", "apply now", "get started",
    "join program", "sign up now", "register now",
)


def _page_has_affiliate_signals(html: str) -> bool:
    """
    Kiểm tra xem trang có tín hiệu affiliate hay không.
    Điều kiện: phải có (A) form đăng ký + (B) text chứa keyword affiliate.
    Chỉ dùng HTML đã có — không fetch thêm.
    """
    h = html or ""
    low_h = h.lower()

    # (A) Check form: tìm form + button/input
    form_tags = re.findall(r"<form[^>]*>", h, flags=re.I)
    input_in_form = bool(re.search(r"<form[^>]*>.*?<input", h, flags=re.I | re.S))
    btn_in_form = bool(re.search(r"<form[^>]*>.*?(?:submit|button)[^<]*(?:</button>|type=[\"']submit[\"'])", h, flags=re.I | re.S))
    textarea_in_form = bool(re.search(r"<form[^>]*>.*?<textarea", h, flags=re.I | re.S))
    has_form = bool(form_tags) and (input_in_form or btn_in_form or textarea_in_form)

    if not has_form:
        return False

    # (B) Check text: title hoặc body chứa keyword
    # Lấy title
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", h, flags=re.I)
    title = (title_match.group(1) or "").lower() if title_match else ""

    # Lấy visible text (strip tags)
    body_text = re.sub(r"<[^>]+>", " ", h)
    body_text = re.sub(r"\s+", " ", body_text).lower()

    # Check keyword trong title + body
    text_has_kw = any(kw in title for kw in _AFFILIATE_TEXT_KW) or any(
        kw in body_text for kw in _AFFILIATE_TEXT_KW
    )
    if not text_has_kw:
        return False

    # (C) Check button text có liên quan signup
    # Tìm text trong button/input submit
    btn_texts = re.findall(r'<button[^>]*>([^<]+)</button>', h, flags=re.I)
    btn_texts += re.findall(r'<input[^>]*type=["\']?(?:submit|button)["\']?[^>]*value=["\']([^"\']+)["\']', h, flags=re.I)
    btn_texts += re.findall(r'<a[^>]*class=["\'][^"\']*(?:btn|button|submit)[^"\']*["\'][^>]*>([^<]+)</a>', h, flags=re.I)
    all_btn_text = " ".join(btn_texts).lower()
    has_signup_btn = any(kw in all_btn_text for kw in _AFFILIATE_BTN_KW)

    return has_signup_btn


def discover_collabs_signup_url_with_redirect(
    storefront_url: str,
    timeout_sec: int = 20,
    should_stop: Callable[[], bool] | None = None,
) -> str:
    """
    Tìm link đăng ký: thử domain chính (từ /meta.json) trước,
    fallback storefront, rồi /pages/collab.
    """
    original = str(storefront_url or "").strip()
    if not original:
        return ""

    main_domain = resolve_redirected_url(original, timeout_sec=timeout_sec)
    if not main_domain:
        main_domain = original

    # Thử domain chính trước (thường là homepage thật)
    result = discover_collabs_signup_url(main_domain, timeout_sec=timeout_sec, should_stop=should_stop)
    if result and result != f"{main_domain.rstrip('/')}/pages/collab":
        return result

    # Fallback: thử storefront gốc
    if main_domain != original:
        result2 = discover_collabs_signup_url(original, timeout_sec=timeout_sec, should_stop=should_stop)
        if result2 and result2 != f"{original.rstrip('/')}/pages/collab":
            return result2

    # Fallback cuối: /pages/collab
    return f"{main_domain.rstrip('/')}/pages/collab"


COLLAB_PATTERNS_RE = [
    re.compile(r"/pages/(?:affiliate|affiliates?|affiliate-program|ambassador|ambassadors?|collab|collabs?|collaboration|collaborations?|influencer|influencers?|partner|partners?|partner-program|refprogram|referral|referral-program)[^'\"\\s]*", re.I),
    re.compile(r"/(affiliate|affiliates?|ambassador|ambassadors?|collab|collabs?|collaboration|influencer|partner|partners?)[^'\"\\s]*", re.I),
]

COMMON_COLLAB_PATHS = [
    "/pages/ambassador",
    "/pages/ambassadors",
    "/pages/affiliate",
    "/pages/affiliates",
    "/pages/affiliate-program",
    "/pages/collab",
    "/pages/collabs",
    "/pages/collaboration",
    "/pages/influencer",
    "/pages/influencers",
    "/pages/partner",
    "/pages/partners",
    "/pages/partner-program",
    "/pages/referral",
    "/pages/referral-program",
    "/pages/collaborators",
    "/pages/partnerships",
    "/pages/collaborations",
    "/pages/ambassador-program",
    "/pages/ambassador-programs",
    "/pages/curious-community",
]


def _rank_signup_url(url: str) -> int:
    low = url.lower()
    if "/pages/collaboration" in low or low.rstrip("/").endswith("/collaboration"):
        return 0
    if "collaboration" in low:
        return 1
    if "/pages/collab" in low or "/pages/collabs" in low:
        return 2
    if "/pages/affiliate" in low or "/pages/ambassador" in low or "/pages/influencer" in low or "/pages/partner" in low:
        return 3
    return 50


async def _playwright_discover(site_url: str, timeout_sec: int, should_stop: Callable[[], bool] | None) -> tuple[str, bool]:
    """
    Core Playwright logic — tìm link collabs bằng trình duyệt thật.
    Returns (url, has_cta) — url="" nếu không tìm được gì.
    """
    raw = str(site_url or "").strip()
    if not raw:
        return "", False
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if not parsed.netloc:
        return "", False
    domain = f"{parsed.scheme or 'https'}://{parsed.netloc}"

    def _halt() -> bool:
        return should_stop is not None and bool(should_stop())

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return "", False

    playwright = None
    browser = None
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            },
        )
        page = await context.new_page()
        await context.route("**/*", lambda route: route.abort() if route.request.resource_type == "image" else route.continue_())

        # 1. Load homepage, scan links
        await page.goto(domain, timeout=timeout_sec * 1000, wait_until="domcontentloaded")
        await asyncio.sleep(0.5)

        if _halt():
            return "", False

        candidates: list[str] = []
        try:
            hrefs: list[str] = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)
            """)
            for href in hrefs:
                if not href:
                    continue
                try:
                    cp = urlparse(href)
                    if cp.netloc != parsed.netloc:
                        continue
                    for pat in COLLAB_PATTERNS_RE:
                        if pat.search(cp.path or ""):
                            full = href if href.startswith("http") else f"{domain.rstrip('/')}{href}"
                            if full not in candidates:
                                candidates.append(full)
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Thử các path phổ biến
        for path in COMMON_COLLAB_PATHS:
            if _halt():
                return "", False
            url_to_try = domain.rstrip("/") + path
            try:
                resp = await page.goto(url_to_try, timeout=15000, wait_until="domcontentloaded")
                if resp and resp.status in (200, 301, 302):
                    candidates.append(url_to_try)
            except Exception:
                pass

        if not candidates:
            return "", False

        candidates.sort(key=_rank_signup_url)

        # 3. Verify bằng HTTP để check CTA (nhanh hơn browser)
        best_candidate_no_cta = ""
        best_candidate_rank = 999
        for cand in candidates[:20]:
            if _halt():
                return "", False
            try:
                res = requests.get(cand, allow_redirects=True, timeout=8)
                if not res.ok:
                    continue
                text = res.text or ""
                # Ưu tiên: trang có CTA → confirm affiliate
                if _collabs_page_has_signup_cta(text):
                    return cand, True
                # Thứ yếu: trang có tín hiệu affiliate (form + keyword) → best guess
                rank = _rank_signup_url(cand)
                if rank < best_candidate_rank and _page_has_affiliate_signals(text):
                    best_candidate_rank = rank
                    best_candidate_no_cta = cand
            except Exception:
                pass

        # 4. Verify bằng browser nếu HTTP fail hoặc chưa có CTA
        for cand in candidates[:10]:
            if _halt():
                break
            try:
                resp = await page.goto(cand, timeout=15000, wait_until="domcontentloaded")
                if resp and resp.status == 200:
                    html: str = await page.content()
                    if _collabs_page_has_signup_cta(html):
                        return cand, True
                    # Lưu best guess từ browser
                    rank = _rank_signup_url(cand)
                    if rank < best_candidate_rank and _page_has_affiliate_signals(html):
                        best_candidate_rank = rank
                        best_candidate_no_cta = cand
            except Exception:
                pass

        # Không tìm được trang có CTA → trả về candidate tốt nhất có tín hiệu affiliate
        return best_candidate_no_cta, False

    except Exception:
        pass
    finally:
        if browser:
            await browser.close()
        if playwright:
            await playwright.stop()

    return "", False


def _sync_discover_collabs(site_url: str, timeout_sec: int, should_stop: Callable[[], bool] | None) -> tuple[str, bool]:
    """Wrapper sync gọi async Playwright. Returns (url, has_cta)."""
    parsed = urlparse(site_url if "://" in site_url else f"https://{site_url}")
    if not parsed.netloc:
        return "", False

    try:
        loop = asyncio.get_running_loop()
        pass
    except RuntimeError:
        pass

    try:
        return asyncio.run(_playwright_discover(site_url, timeout_sec, should_stop))
    except Exception:
        return "", False


def discover_collabs_signup_url(
    site_url: str, timeout_sec: int = 20, should_stop: Callable[[], bool] | None = None
) -> str:
    """
    Tìm link đăng ký collabs từ domain chính bằng Playwright (trình duyệt thật).
    Không bị 429 vì trình duyệt thật được Cloudflare cho qua.

    Fallback hierarchy:
    1. Trang có CTA (confirm) → trả ngay
    2. Trang có tín hiệu affiliate (best guess, không CTA) → trả candidate đó
    3. Hoàn toàn không có candidate → /pages/collab
    """
    raw = str(site_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if not parsed.netloc:
        return ""
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"

    # Thử Playwright trước
    found_url, has_cta = _sync_discover_collabs(raw, timeout_sec, should_stop)

    if found_url:
        if has_cta:
            return found_url
        # Có candidate nhưng không confirm CTA → dùng làm best guess
        return found_url

    # Fallback cuối cùng: /pages/collab
    return f"{base}/pages/collab"


def _extract_url_from_ddg_href(href: str) -> str:
    h = str(href or "").strip()
    if not h:
        return ""
    if h.startswith("http://") or h.startswith("https://"):
        return h
    # DuckDuckGo thường bọc URL trong tham số uddg.
    if "uddg=" in h:
        try:
            q = dict(parse_qsl(urlparse(h).query, keep_blank_values=True))
            raw = unquote(str(q.get("uddg") or "").strip())
            if raw.startswith("http://") or raw.startswith("https://"):
                return raw
        except Exception:
            return ""
    return ""


def _fetch_duckduckgo_result_urls(query: str, max_results: int = 80, timeout_sec: int = 20, delay_ms: int = 350) -> list[str]:
    q = str(query or "").strip()
    if not q:
        return []
    out: list[str] = []
    seen: set[str] = set()
    offset = 0
    page_size = 30
    while len(out) < max_results:
        search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}&s={offset}"
        try:
            res = requests.get(
                search_url,
                timeout=timeout_sec,
                headers={
                    "user-agent": os.getenv(
                        "COLLABS_OUTSIDE_UA",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                    )
                },
            )
            if not res.ok:
                break
            html = res.text or ""
        except Exception:
            break

        hrefs = re.findall(r"""class=["']result__a["'][^>]*href=["']([^"']+)["']""", html, flags=re.I)
        if not hrefs:
            # Fallback parser: lấy mọi anchor có link ra ngoài.
            hrefs = re.findall(r"""<a[^>]*href=["']([^"']+)["']""", html, flags=re.I)
        added = 0
        for href in hrefs:
            final_url = _extract_url_from_ddg_href(href)
            if not final_url:
                continue
            p = urlparse(final_url)
            if not p.netloc:
                continue
            norm = f"{p.scheme or 'https'}://{p.netloc}{p.path or '/'}"
            low = norm.lower()
            if any(x in low for x in ("facebook.com", "instagram.com", "tiktok.com", "youtube.com", "x.com/", "twitter.com/")):
                continue
            if norm in seen:
                continue
            seen.add(norm)
            out.append(norm)
            added += 1
            if len(out) >= max_results:
                break
        if added == 0:
            break
        offset += page_size
        if delay_ms > 0:
            time.sleep(delay_ms / 1000.0)
    return out


def _fetch_bing_rss_result_urls(
    query: str, max_results: int = 80, timeout_sec: int = 20, should_stop: Callable[[], bool] | None = None
) -> list[str]:
    q = str(query or "").strip()
    if not q:
        return []
    if should_stop and should_stop():
        return []
    try:
        res = requests.get(
            f"https://www.bing.com/search?q={quote_plus(q)}&format=rss",
            timeout=timeout_sec,
            headers={
                "user-agent": os.getenv(
                    "COLLABS_OUTSIDE_UA",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36",
                )
            },
        )
        if not res.ok:
            return []
        xml = res.text or ""
    except Exception:
        return []

    out: list[str] = []
    seen: set[str] = set()
    links = re.findall(r"<link>(.*?)</link>", xml, flags=re.I | re.S)
    for lk in links:
        url = str(lk or "").strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        p = urlparse(url)
        if not p.netloc:
            continue
        low = (p.netloc + (p.path or "")).lower()
        if "bing.com/search" in low:
            continue
        if any(x in low for x in ("facebook.com", "instagram.com", "tiktok.com", "youtube.com", "x.com/", "twitter.com/")):
            continue
        norm = f"{p.scheme or 'https'}://{p.netloc}{p.path or '/'}"
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
        if len(out) >= max_results:
            break
    return out


def _google_cse_credentials() -> tuple[str, str]:
    """Trả về (api_key, cx) nếu đủ cấu hình Google Custom Search JSON API; ngược lại ('','')."""
    key = (os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY") or os.getenv("GOOGLE_CSE_API_KEY") or "").strip()
    cx = (os.getenv("GOOGLE_CUSTOM_SEARCH_ENGINE_ID") or os.getenv("GOOGLE_CSE_CX") or "").strip()
    return key, cx


def _outside_cursor_path() -> Path:
    return Path(os.getenv("COLLABS_OUTSIDE_CURSOR_FILE", str(BASE_DIR / ".collabs_outside_cursor.json")))


def _outside_dedup_path() -> Path:
    return Path(os.getenv("COLLABS_OUTSIDE_DEDUP_FILE", str(BASE_DIR / ".collabs_outside_seen_hosts.json")))


def _outside_cursor_key(provider: str, query: str) -> str:
    return f"{provider}::{(query or '').strip().lower()}"


def _load_outside_cursor(provider: str, query: str) -> int:
    p = _outside_cursor_path()
    if not p.exists():
        return 0
    try:
        payload = json.loads(p.read_text(encoding="utf-8-sig") or "{}")
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    cursors = payload.get("cursors") or {}
    if not isinstance(cursors, dict):
        return 0
    raw = cursors.get(_outside_cursor_key(provider, query), 0)
    try:
        n = int(raw)
    except Exception:
        return 0
    return max(0, n)


def _save_outside_cursor(provider: str, query: str, next_offset: int) -> None:
    p = _outside_cursor_path()
    data: dict = {}
    try:
        if p.exists():
            loaded = json.loads(p.read_text(encoding="utf-8-sig") or "{}")
            if isinstance(loaded, dict):
                data = loaded
    except Exception:
        data = {}
    cursors = data.get("cursors")
    if not isinstance(cursors, dict):
        cursors = {}
    cursors[_outside_cursor_key(provider, query)] = max(0, int(next_offset))
    data["cursors"] = cursors
    data["updatedAt"] = time.time()
    try:
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        return


def _fetch_google_result_urls_via_custom_search_api(
    query: str,
    max_results: int = 80,
    timeout_sec: int = 20,
    should_stop: Callable[[], bool] | None = None,
) -> list[str]:
    """
    Lấy URL organic qua Google Custom Search JSON API (hỗ trợ cú pháp Google: inurl, OR, ngoặc, …).
    Yêu cầu .env:
    - GOOGLE_CUSTOM_SEARCH_API_KEY (hoặc GOOGLE_CSE_API_KEY)
    - GOOGLE_CUSTOM_SEARCH_ENGINE_ID (hoặc GOOGLE_CSE_CX — Search engine ID)

    Mỗi request tối đa 10 kết quả; API không trả quá 100 kết quả cho một truy vấn (phân trang start 1..91).
    """
    api_key, cx = _google_cse_credentials()
    if not api_key or not cx:
        raise RuntimeError(
            "Thiếu GOOGLE_CUSTOM_SEARCH_API_KEY hoặc GOOGLE_CUSTOM_SEARCH_ENGINE_ID (cx) cho Google CSE."
        )
    q = str(query or "").strip()
    if not q:
        return []
    max_results = max(1, min(300, int(max_results)))
    # JSON API: tổng chỉ mục tối đa ~100; mỗi lần gọi num <= 10 và start + num <= 101.
    cap = min(max_results, 100)
    base = "https://www.googleapis.com/customsearch/v1"
    out: list[str] = []
    seen: set[str] = set()
    start = 1
    ua = (os.getenv("COLLABS_OUTSIDE_UA") or "").strip() or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )
    headers = {"User-Agent": ua, "Accept": "application/json"}
    while len(out) < cap and start <= 100:
        if should_stop and should_stop():
            return out
        num = min(10, cap - len(out), max(0, 101 - start))
        if num < 1:
            break
        params = {"key": api_key, "cx": cx, "q": q, "num": num, "start": start}
        try:
            res = requests.get(base, params=params, headers=headers, timeout=int(timeout_sec))
        except requests.RequestException as e:
            raise RuntimeError(f"Google Custom Search API: lỗi mạng — {e}") from e
        if not res.ok:
            snippet = (res.text or "")[:400]
            if res.status_code == 429:
                raise RuntimeError("Google Custom Search API hết quota (429). Thử lại sau hoặc kiểm tra billing.")
            raise RuntimeError(f"Google Custom Search API lỗi HTTP {res.status_code}: {snippet}")
        try:
            data = res.json() if res.text else {}
        except json.JSONDecodeError:
            raise RuntimeError("Google Custom Search API trả nội dung không phải JSON.")
        items = data.get("items") or []
        if not items:
            break
        for it in items:
            if not isinstance(it, dict):
                continue
            u = it.get("link")
            if not isinstance(u, str):
                continue
            u = u.strip()
            if not u.startswith(("http://", "https://")):
                continue
            p = urlparse(u)
            if not p.netloc:
                continue
            low = (p.netloc + (p.path or "")).lower()
            if any(
                x in low
                for x in ("facebook.com", "instagram.com", "tiktok.com", "youtube.com", "x.com/", "twitter.com/")
            ):
                continue
            norm = f"{p.scheme or 'https'}://{p.netloc}{p.path or '/'}"
            if norm in seen:
                continue
            seen.add(norm)
            out.append(norm)
            if len(out) >= cap:
                break
        start += len(items)
        if len(items) < num:
            break
        time.sleep(0.12)
    return out


def _apify_run_actor_with_token(actor_id: str, run_input: dict, wait_secs: int, tok: str) -> str:
    """Một lần POST + poll đơn giản (Google actor); tok cố định."""
    act = str(actor_id or "").strip()
    if not act:
        raise RuntimeError("Thiếu COLLABS_OUTSIDE_GOOGLE_ACTOR_ID (Apify actor id).")
    if "/" in act and "~" not in act:
        parts = [p for p in act.split("/") if p]
        if len(parts) >= 2:
            act = f"{parts[0]}~{parts[1]}"
    url = f"https://api.apify.com/v2/acts/{act}/runs?token={tok}&waitForFinish={int(wait_secs)}"
    res = requests.post(url, json=run_input, timeout=max(30, int(wait_secs) + 30))
    if not res.ok:
        body = (res.text or "")[:800]
        if _apify_http_suggests_token_failover(res.status_code, body):
            raise ApifyTokenFailover(f"HTTP {res.status_code}: {body[:300]}")
        raise RuntimeError(f"Apify run actor lỗi HTTP {res.status_code}: {res.text[:300]}")
    body = res.json() if res.text else {}
    data = (body or {}).get("data") or {}
    status = str(data.get("status") or "").upper()
    run_id = str(data.get("id") or "").strip()
    if status in {"READY", "RUNNING"} and run_id:
        deadline = time.monotonic() + max(10, int(wait_secs))
        while time.monotonic() < deadline:
            time.sleep(2.0)
            st_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={tok}"
            st = requests.get(st_url, timeout=30)
            if not st.ok:
                pb = (st.text or "")[:800]
                if _apify_http_suggests_token_failover(st.status_code, pb):
                    raise ApifyTokenFailover(f"poll HTTP {st.status_code}: {pb[:300]}")
                continue
            st_body = st.json() if st.text else {}
            st_data = (st_body or {}).get("data") or {}
            status = str(st_data.get("status") or "").upper()
            if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
                data = st_data
                break
    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify actor chưa SUCCEEDED (status={status})")
    dataset_id = str(data.get("defaultDatasetId") or "").strip()
    if not dataset_id:
        raise RuntimeError("Apify actor không trả defaultDatasetId")
    return dataset_id


def _apify_run_actor(actor_id: str, run_input: dict, wait_secs: int = 180, token: str | None = None) -> tuple[str, str]:
    """
    Run Apify actor và trả về (defaultDatasetId, token_đã_dùng).
    token=None → thử lần lượt mọi token trong APIFY_TOKENS khi lỗi quota/quyền.
    """
    if str(token or "").strip():
        t = str(token).strip()
        return _apify_run_actor_with_token(actor_id, run_input, wait_secs, t), t
    ds, used = _apify_run_with_token_failover(
        "Google actor",
        lambda tok: _apify_run_actor_with_token(actor_id, run_input, wait_secs, tok),
    )
    return ds, used


def _extract_urls_from_google_actor_items(items: list) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if not isinstance(items, list):
        return []
    for it in items:
        if not isinstance(it, dict):
            continue
        # 1) Một số actor trả thẳng link/url
        for k in ("url", "link", "resultUrl", "result_url"):
            v = it.get(k)
            if isinstance(v, str) and v.strip().startswith(("http://", "https://")):
                u = v.strip()
                if u not in seen:
                    seen.add(u)
                    out.append(u)
        # 2) google-search-scraper thường trả organicResults:[{url,...}]
        org = it.get("organicResults") or it.get("organic_results") or []
        if isinstance(org, list):
            for r in org:
                if not isinstance(r, dict):
                    continue
                u = r.get("url") or r.get("link")
                if isinstance(u, str) and u.strip().startswith(("http://", "https://")):
                    uu = u.strip()
                    if uu not in seen:
                        seen.add(uu)
                        out.append(uu)
    return out


def _fetch_google_result_urls_via_apify(
    query: str,
    max_results: int = 80,
    timeout_sec: int = 180,
    start_page: int = 1,
    end_page: int | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[str]:
    """
    Lấy URL từ Google Search theo đúng cú pháp (inurl/OR/ngoặc) bằng Apify actor.
    Yêu cầu env:
    - APIFY_TOKENS (mỗi dòng một token, failover tự động) — dùng chung với Similarweb
    - COLLABS_OUTSIDE_GOOGLE_ACTOR_ID (vd: apify/google-search-scraper)
    """
    q = str(query or "").strip()
    if not q:
        return []
    actor_id = (os.getenv("COLLABS_OUTSIDE_GOOGLE_ACTOR_ID") or "").strip()
    # Google actor hiện bị giới hạn 10 kết quả/trang (theo cập nhật Google), nên dùng maxPagesPerQuery để tăng tổng.
    cap = max(10, min(300, int(max_results)))
    per_page = 10
    if start_page < 1:
        start_page = 1
    if end_page is not None and end_page < start_page:
        end_page = start_page
    # Tối ưu chi phí theo range trang người dùng chọn:
    # - Nếu có end_page: chỉ cần số bản ghi tương ứng với số trang trong range.
    # - Actor vẫn crawl từ trang 1..maxPagesPerQuery, nhưng ta không kéo dư theo max_results toàn cục.
    if end_page is not None:
        # Cần fetch đủ tới cuối range để slice chính xác (vd trang 4-5 cần tối thiểu 50 kết quả thô).
        raw_needed_for_slice = max(10, int(end_page) * per_page)
        # Ưu tiên đúng phạm vi trang user chọn: nếu MAX_RESULTS thấp hơn mức cần thiết,
        # tự nâng lên để không bị rỗng/thiếu dữ liệu khi chọn page sâu (vd 6-8).
        cap = max(cap, raw_needed_for_slice)
        cap = min(cap, 300)
        max_pages = max(1, min(20, int(end_page)))
    else:
        max_pages = max(1, min(20, max(1, (cap + per_page - 1) // per_page)))
    # Actor hiện tại yêu cầu input.queries là string.
    run_input = {
        "queries": q,
        "maxPagesPerQuery": max_pages,
        "resultsPerPage": per_page,
        "includeUnfilteredResults": False,
        "languageCode": "en",
        "mobileResults": False,
    }
    if should_stop and should_stop():
        return []
    dataset_id, used_tok = _apify_run_actor(actor_id, run_input, wait_secs=int(timeout_sec), token=None)
    if not dataset_id:
        return []
    items = apify_list_items(dataset_id, token=used_tok)
    urls = _extract_urls_from_google_actor_items(items)
    # chuẩn hóa + giới hạn
    out: list[str] = []
    seen: set[str] = set()
    for u in urls:
        p = urlparse(u)
        if not p.netloc:
            continue
        norm = f"{p.scheme or 'https'}://{p.netloc}{p.path or '/'}"
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
        if len(out) >= cap:
            break
    # giả lập phân trang Google: 10 kết quả / trang
    if start_page > 1 or end_page is not None:
        s = (start_page - 1) * 10
        e = (int(end_page) * 10) if end_page is not None else len(out)
        out = out[s:e]
    return out


# Gán trước khi gọi discover (vd. từ webapp) để log và tìm kiếm dùng cùng một chuỗi query.
EFFECTIVE_OUTSIDE_QUERY_KEY = "_effective_outside_query"
# Thống kê nội bộ (sau discover) — target batch vs URL ứng viên vs brand sau verify.
OUTSIDE_DISCOVERY_STATS_KEY = "_outside_discovery_stats"

# Query cố định cho Outside Discovery (Google); ghép với dạng random chữ (x OR y) trong build_random_outside_collabs_google_query.
_OUTSIDE_COLLABS_GOOGLE_FIXED_QUERIES: tuple[str, ...] = (
    'inurl:pages/collabs "apply"',
    'inurl:pages/collabs "apply now"',
    'inurl:pages/collabs "apply today"',
    'inurl:pages/collabs "apply to join"',
    'inurl:pages/collabs "join"',
    'inurl:pages/collabs "join now"',
    'inurl:pages/collabs "join today"',
    'inurl:pages/collabs "join our program"',
    'inurl:pages/collabs "join our community"',
    'inurl:pages/collabs "join the program"',
    'inurl:pages/collabs "become a creator"',
    'inurl:pages/collabs "become a partner"',
    'inurl:pages/collabs "become an affiliate"',
    'inurl:pages/collabs "become an ambassador"',
    'inurl:pages/collabs "creator program"',
    'inurl:pages/collabs "affiliate program"',
    'inurl:pages/collabs "ambassador program"',
    'inurl:pages/collabs "influencer program"',
    'inurl:pages/collabs "content creator"',
    'inurl:pages/collabs "ugc creator"',
    'inurl:pages/collab "apply"',
    'inurl:pages/collab "apply now"',
    'inurl:pages/collab "apply to join"',
    'inurl:pages/collab "join"',
    'inurl:pages/collab "join now"',
    'inurl:pages/collab "join our community"',
    'inurl:pages/collab "join the program"',
    'inurl:pages/collab "become an affiliate"',
    'inurl:pages/collab "become a creator"',
    'inurl:pages/collab "creator program"',
    'inurl:pages/collab "affiliate program"',
    'inurl:pages/collab "ambassador program"',
    'inurl:pages/collab "ugc creator"',
    'inurl:pages/collab "content creator"',
    'inurl:pages "collabs" "apply"',
    'inurl:pages "collabs" "apply now"',
    'inurl:pages "collabs" "apply today"',
    'inurl:pages "collabs" "apply to join"',
    'inurl:pages "collabs" "join"',
    'inurl:pages "collabs" "join now"',
    'inurl:pages "collabs" "join today"',
    'inurl:pages "collabs" "join our program"',
    'inurl:pages "collabs" "join our community"',
    'inurl:pages "collabs" "become an affiliate"',
    'inurl:pages "collabs" "become a creator"',
    'inurl:pages "collabs" "become a partner"',
    'inurl:pages "collabs" "creator application"',
    'inurl:pages "collabs" "creator program"',
    'inurl:pages "collabs" "affiliate program"',
    'inurl:pages "collabs" "ambassador program"',
    'inurl:pages "collabs" "influencer program"',
    'inurl:pages "collabs" "ugc creator"',
    'inurl:pages "collabs" "content creator"',
    'inurl:pages "collab" "apply"',
    'inurl:pages "collab" "apply now"',
    'inurl:pages "collab" "apply to join"',
    'inurl:pages "collab" "join"',
    'inurl:pages "collab" "join now"',
    'inurl:pages "collab" "join our community"',
    'inurl:pages "collab" "join the program"',
    'inurl:pages "collab" "become an affiliate"',
    'inurl:pages "collab" "become a creator"',
    'inurl:pages "collab" "creator application"',
    'inurl:pages "collab" "creator program"',
    'inurl:pages "collab" "affiliate program"',
    'inurl:pages "collab" "ambassador program"',
    'inurl:pages "collab" "ugc creator"',
    'inurl:pages "collab" "content creator"',
    'inurl:pages "collabs" "sign up"',
    'inurl:pages "collabs" "get started"',
    'inurl:pages "collabs" "start now"',
    'inurl:pages "collabs" "start today"',
    'inurl:pages "collabs" "register"',
    'inurl:pages "collabs" "register now"',
    'inurl:pages "collab" "sign up"',
    'inurl:pages "collab" "get started"',
    'inurl:pages "collab" "start now"',
    'inurl:pages "collab" "register"',
    'inurl:pages "collab" "register now"',
    'inurl:pages/collabs "sign up"',
    'inurl:pages/collabs "get started"',
    'inurl:pages/collabs "start now"',
    'inurl:pages/collabs "register"',
    'inurl:pages/collabs "register now"',
    'inurl:pages/collab "sign up"',
    'inurl:pages/collab "get started"',
    'inurl:pages/collab "start now"',
    'inurl:pages/collab "register"',
    'inurl:pages/collab "register now"',
)


def _build_random_letter_pair_outside_collabs_query() -> str:
    """inurl:pages/collab(s) ("x" OR "y") với x≠y ngẫu nhiên."""
    x, y = random.sample(string.ascii_lowercase, 2)
    path = random.choice(("pages/collab", "pages/collabs"))
    return f'inurl:{path} ("{x}" OR "{y}")'


def build_random_outside_collabs_google_query() -> str:
    """
    Mỗi lần lọc: **một** query.

    - GROUP_QERRY=1 (mặc định hoặc trống): giữ hành vi cũ — query
      ngẫu nhiên dạng chữ (x OR y) hoặc một chuỗi cố định trong
      _OUTSIDE_COLLABS_GOOGLE_FIXED_QUERIES.
    - GROUP_QERRY=2: dùng nhóm query mới:
      ("/pages/affiliate" OR "/pages/collab") (intitle:"Collabs" OR intitle:"Community") ("x" OR "y").
    """
    group = (os.getenv("GROUP_QERRY") or "1").strip()
    if group == "2":
        x, y = random.sample(string.ascii_lowercase, 2)
        template = (
            os.getenv(
                "COLLABS_OUTSIDE_GOOGLE_GROUP2_QUERY_TEMPLATE",
                '("/pages/affiliate" OR "/pages/collab") '
                '(intitle:"Collabs" OR intitle:"Community") ("x" OR "y")',
            )
            or ""
        ).strip()
        # Hỗ trợ 2 kiểu placeholder:
        # - Mặc định theo bạn: ("x" OR "y") sẽ được thay "x"/"y" bằng chữ cái random.
        # - Hoặc template dùng {x}/{y} thì format trực tiếp.
        if "{x}" in template or "{y}" in template:
            return template.format(x=x, y=y)
        return template.replace('"x"', f'"{x}"').replace('"y"', f'"{y}"')

    # Nhóm 1: hành vi cũ.
    if random.random() < 0.5:
        return _build_random_letter_pair_outside_collabs_query()
    return random.choice(_OUTSIDE_COLLABS_GOOGLE_FIXED_QUERIES)


def resolve_outside_discovery_query_string(filters: dict | None) -> str:
    """Chuỗi query web search: ưu tiên filters.outside_query, rồi COLLABS_OUTSIDE_QUERY, rồi query ngẫu nhiên."""
    f = filters if isinstance(filters, dict) else {}
    raw = str(f.get("outside_query") or os.getenv("COLLABS_OUTSIDE_QUERY") or "").strip()
    if raw:
        return raw
    return build_random_outside_collabs_google_query()


def _outside_discovery_verify_and_build_offer(
    url: str,
    verify_timeout_sec: int,
    should_stop: Callable[[], bool] | None,
) -> dict | None:
    """Verify một URL candidate ngoài Discovery; trả dict offer hoặc None."""
    if should_stop and should_stop():
        return None
    hk = host_key(url)
    if not hk:
        return None
    try:
        res = requests.get(url, timeout=verify_timeout_sec)
        if not res.ok:
            return None
        html = res.text or ""
    except Exception:
        return None

    low_url = url.lower()
    must_path = ("/pages/collab" in low_url) or ("/pages/collabs" in low_url)
    low_html = (html or "").lower()
    has_cta_phrase = _collabs_html_has_outside_cta_phrases(low_html)
    if not must_path:
        return None
    if not has_cta_phrase:
        return None

    looks_like = _collabs_page_looks_like_signup(html, url)
    weak_signal_url = any(
        k in low_url for k in ("/pages/collab", "/pages/collabs", "affiliate", "ambassador", "partner")
    )
    if not looks_like and not weak_signal_url:
        return None

    apply_url = discover_collabs_signup_url(url, timeout_sec=verify_timeout_sec, should_stop=should_stop)
    if not apply_url:
        return None

    brand_guess = hk.split(".")[0].replace("-", " ").replace("_", " ").title()
    return {
        "brand": brand_guess,
        "url": f"https://{hk}",
        "offer": "",
        "cookieDays": "",
        "client_url": apply_url,
        "offer_id": hk,
        "shop_id": "",
        "program_id": "",
        "mkp_listing_id": hk,
        "commission_type": "",
        "category": "Outside Discovery",
        "collabs_product_category_code": "",
        "epc": "",
        "payments": "",
        "currency": "",
        "payout_rate": "",
        "approval_rate": "",
        "offer_score": "",
        "recommend_score": "",
        "application_review": "",
        "promotion_details": [],
        "target_audience_customer_channels": [],
        "target_audience_locations": [],
        "target_audience_ages": [],
        "target_audience_genders": [],
        "can_apply_offer": None,
        "is_applied_offer": None,
        "collabs_partnership_status": "",
        "collabs_partnership_state": "",
        "collabs_saved": None,
        "collabs_previously_purchased": None,
        "collabs_target_countries": "",
        "collabs_logo_url": "",
        "collabs_images": "",
        "collabs_shopify_store_id": "",
        "collabs_holding_period": "",
    }


def discover_collabs_outside_discovery_offers(
    filters: dict | None = None, should_stop: Callable[[], bool] | None = None
) -> list[dict]:
    """
    Lọc Collabs ngoài Discovery từ web search:
    - Tìm candidate URL theo query.
    - Verify trang có tín hiệu collab/apply.
    - Tìm apply URL cuối bằng discover_collabs_signup_url.
    """
    f = filters if isinstance(filters, dict) else {}
    query_text = str(f.get(EFFECTIVE_OUTSIDE_QUERY_KEY) or "").strip() or resolve_outside_discovery_query_string(f)
    # Cú pháp Google (inurl/OR/ngoặc): dùng Apify actor, Google CSE JSON API, hoặc Bing (hỗ trợ một phần).
    query_list = [query_text] if query_text else []

    # outside_target_results (UI mới) ưu tiên hơn .env; fallback về COLLABS_OUTSIDE_MAX_RESULTS.
    raw_target = f.get("outside_target_results")
    if raw_target is None or str(raw_target).strip() == "":
        raw_target = os.getenv("COLLABS_OUTSIDE_MAX_RESULTS", "80") or "80"
    try:
        max_results = int(raw_target)
    except Exception:
        max_results = int(os.getenv("COLLABS_OUTSIDE_MAX_RESULTS", "80") or "80")
    max_results = max(10, min(30, max_results))
    max_results = (max_results // 10) * 10
    if max_results < 10:
        max_results = 10
    # Pool để cursor quay vòng; cho phép >300 nếu cần.
    raw_pool = os.getenv("COLLABS_OUTSIDE_CURSOR_POOL", "300") or "300"
    try:
        cursor_pool = int(raw_pool)
    except Exception:
        cursor_pool = 300
    cursor_pool = max(max_results, min(5000, cursor_pool))
    verify_timeout_sec = int(os.getenv("COLLABS_OUTSIDE_VERIFY_TIMEOUT_SEC", "30") or "30")
    if not query_list:
        return []
    if should_stop and should_stop():
        return []
    provider = (
        "apify"
        if (os.getenv("COLLABS_OUTSIDE_GOOGLE_ACTOR_ID") or "").strip()
        else ("google_cse" if _google_cse_credentials()[0] and _google_cse_credentials()[1] else "bing")
    )
    # Google CSE có trần ~100 kết quả/query -> giới hạn pool hiệu lực để tránh batch rỗng.
    effective_pool = min(cursor_pool, 100) if provider == "google_cse" else cursor_pool
    cursor_offset = _load_outside_cursor(provider, query_text)
    # Mỗi lần chạy lấy batch kế tiếp đúng bằng outside_target_results (max_results).
    start_idx = cursor_offset % effective_pool
    if start_idx + max_results > effective_pool:
        # Chạm giới hạn pool thì quay về page đầu cho lần này.
        start_idx = 0
    end_idx = start_idx + max_results
    start_page = (start_idx // 10) + 1
    end_page = max(start_page, (end_idx + 9) // 10)
    candidates: list[str] = []
    seen_candidate: set[str] = set()
    # Thứ tự ưu tiên: Apify Google actor → Google Custom Search JSON API → Bing RSS.
    # CSE hỗ trợ cú pháp Google (inurl/OR/…) và không cần Apify; Bing chỉ fallback khi không cấu hình Google.
    cse_key, cse_cx = _google_cse_credentials()
    if provider == "apify":
        fetch_budget = max(max_results, end_page * 10)
        urls = _fetch_google_result_urls_via_apify(
            query_text,
            max_results=fetch_budget,
            timeout_sec=180,
            start_page=start_page,
            end_page=end_page,
            should_stop=should_stop,
        )
    elif provider == "google_cse" and cse_key and cse_cx:
        fetch_budget = max(max_results, min(100, end_idx))
        urls = _fetch_google_result_urls_via_custom_search_api(
            query_text,
            max_results=fetch_budget,
            timeout_sec=verify_timeout_sec,
            should_stop=should_stop,
        )
        urls = urls[start_idx:end_idx]
    elif cse_key or cse_cx:
        raise RuntimeError(
            "Collabs ngoài Discovery: thiếu một trong hai — GOOGLE_CUSTOM_SEARCH_API_KEY và "
            "GOOGLE_CUSTOM_SEARCH_ENGINE_ID (hoặc GOOGLE_CSE_API_KEY / GOOGLE_CSE_CX)."
        )
    else:
        fetch_budget = max(max_results, end_idx)
        urls = _fetch_bing_rss_result_urls(
            query_text,
            max_results=fetch_budget,
            timeout_sec=verify_timeout_sec,
            should_stop=should_stop,
        )
        urls = urls[start_idx:end_idx]
    for u in urls:
        if u in seen_candidate:
            continue
        seen_candidate.add(u)
        candidates.append(u)

    # Dedupe giữa các lần chạy (theo host). Bật bằng env:
    # - COLLABS_OUTSIDE_DEDUP_PERSIST=1
    # - (tuỳ chọn) COLLABS_OUTSIDE_DEDUP_FILE=.collabs_outside_seen_hosts.json
    dedup_enabled = str(os.getenv("COLLABS_OUTSIDE_DEDUP_PERSIST", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
        "enable",
        "enabled",
    }
    seen_hosts_persist: set[str] = set()
    dedup_path = _outside_dedup_path()
    if dedup_enabled:
        try:
            if dedup_path.exists():
                payload = json.loads(dedup_path.read_text(encoding="utf-8-sig") or "{}")
                arr = payload.get("hosts") if isinstance(payload, dict) else payload
                if isinstance(arr, list):
                    seen_hosts_persist = {host_key(x) for x in arr if host_key(x)}
        except Exception:
            seen_hosts_persist = set()

    offers: list[dict] = []
    seen_host: set[str] = set()
    added_hosts: set[str] = set()
    work_urls: list[str] = []
    stopped_early = False
    for url in candidates:
        if should_stop and should_stop():
            stopped_early = True
            break
        hk = host_key(url)
        if not hk or hk in seen_host:
            continue
        if dedup_enabled and hk in seen_hosts_persist:
            continue
        seen_host.add(hk)
        work_urls.append(url)

    nw = int(os.getenv("COLLABS_OUTSIDE_VERIFY_WORKERS", "8") or "8")
    nw = max(1, min(16, nw))

    if work_urls:
        if nw <= 1 or len(work_urls) <= 1:
            for u in work_urls:
                if should_stop and should_stop():
                    stopped_early = True
                    break
                off = _outside_discovery_verify_and_build_offer(u, verify_timeout_sec, should_stop)
                if off:
                    offers.append(off)
                    if dedup_enabled:
                        added_hosts.add(host_key(off.get("url", "") or ""))
        else:
            ex = ThreadPoolExecutor(max_workers=nw)
            try:
                futures = {
                    ex.submit(_outside_discovery_verify_and_build_offer, u, verify_timeout_sec, should_stop): i
                    for i, u in enumerate(work_urls)
                }
                pending = set(futures.keys())
                slots: list[dict | None] = [None] * len(work_urls)
                while pending:
                    done, pending = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
                    for fut in done:
                        idx = futures.pop(fut, -1)
                        if idx < 0:
                            continue
                        try:
                            slots[idx] = fut.result()
                        except Exception:
                            slots[idx] = None
                    if should_stop and should_stop():
                        stopped_early = True
                        break
                for slot in slots:
                    if not slot:
                        continue
                    offers.append(slot)
                    if dedup_enabled:
                        added_hosts.add(host_key(slot.get("url", "") or ""))
            finally:
                ex.shutdown(wait=False, cancel_futures=True)

    if dedup_enabled and added_hosts:
        try:
            merged = sorted(set(seen_hosts_persist) | set(added_hosts))
            # giữ tối đa 50k hosts để tránh file quá lớn
            merged = merged[-50000:]
            dedup_path.write_text(
                json.dumps({"updatedAt": time.time(), "hosts": merged}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
    # Chỉ cập nhật cursor khi chạy xong batch (không hủy giữa chừng) để không bỏ lỡ URL kế tiếp.
    if not stopped_early and not (should_stop and should_stop()):
        _save_outside_cursor(provider, query_text, end_idx % effective_pool)
    if isinstance(f, dict):
        f[OUTSIDE_DISCOVERY_STATS_KEY] = {
            "target_batch": max_results,
            "candidate_urls": len(candidates),
            "offers_verified": len(offers),
        }
    return offers


# Trạng thái traffic so với ngưỡng (CSV + log)
STATUS_TRAFFIC_OK = "ĐẠT"
STATUS_TRAFFIC_FAIL = "CHƯA ĐẠT"


def format_uppromote_cookie_days_cell(raw) -> str:
    """Excel: ví dụ 30 → \"30 day\"; giữ nguyên nếu đã có chữ day/days."""
    if raw is None:
        return ""
    s = str(raw).strip()
    if not s:
        return ""
    low = s.lower()
    if "day" in low:
        return s
    m = re.match(r"^(\d+(?:[.,]\d+)?)", s.replace(",", "."))
    if m:
        num = m.group(1).replace(",", ".")
        return f"{num} day"
    return f"{s} day"


def format_percent_cell(raw) -> str:
    """Excel: hiển thị tỷ lệ kèm %, ví dụ 20%. Số float trong (0,1) coi như phân số → nhân 100."""
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return ""
    if isinstance(raw, (int, float)):
        x = float(raw)
        if isinstance(raw, float) and 0 < x < 1:
            x *= 100
        if abs(x - round(x)) < 1e-6:
            return f"{int(round(x))}%"
        t = f"{x:.4f}".rstrip("0").rstrip(".")
        return f"{t}%"
    s = str(raw).strip()
    if not s:
        return ""
    if "%" in s:
        return s
    s2 = s.replace(",", ".").replace("%", "")
    try:
        x = float(s2)
        if 0 < x < 1:
            x *= 100
        if abs(x - round(x)) < 1e-6:
            return f"{int(round(x))}%"
        t = f"{x:.4f}".rstrip("0").rstrip(".")
        return f"{t}%"
    except ValueError:
        return f"{s}%"


# CSV Uppromote (tiếng Việt)
UPPROMOTE_CSV_HEADER_VI = [
    "Trạng thái",
    "Thương hiệu",
    "Website",
    "URL apply",
    "Hoa hồng",
    "Ngày cookie",
    "Danh mục",
    "Traffic (hiển thị)",
    "Traffic ước tính/tháng",
    "Trang/lượt xem",
    "Thời gian ở lại",
    "Tỷ lệ thanh toán",
    "Tỷ lệ duyệt",
    "Tỷ lệ thoát",
    "Top quốc gia",
    "Top từ khóa",
    "Tiền tệ",
    "Điểm offer",
    "Điểm gợi ý",
    "Duyệt đơn",
    "Chu kỳ thanh toán",
    "Danh sách phương thức thanh toán",
    "Chi tiết khuyến mãi",
    "Kênh được phép",
    "Đối tượng vị trí",
    "Đối tượng độ tuổi",
    "Đối tượng giới",
    "Có thể apply",
    "Đã apply",
    "Offer ID",
    "Shop ID",
    "Program ID",
    "Marketplace Listing ID",
    "EPC (TB/đơn)",
]

# CSV Goaff: chỉ cột Similarweb (Apify) + trường có trong API Goaff (không cột Uppromote rỗng)
GOAFF_CSV_HEADER = [
    "Trạng thái",
    "Thương hiệu",
    "Website",
    "Số tiền HH",
    "Ngày cookie",
    "Traffic (hiển thị)",
    "Traffic ước tính/tháng",
    "Link đăng ký",
    "Trang/lượt xem",
    "Thời gian ở lại",
    "Duyệt tự động",
    "Top từ khóa",
    "Tỷ lệ thoát",
    "Top quốc gia",
    "Tiền tệ",
    "Tên (API)",
    "Đăng ký mở",
    "Loại hoa hồng",
    "Hoa hồng trên",
    "ID cửa hàng",
]

REFERSION_CSV_HEADER = [
    "Trạng thái",
    "Thương hiệu",
    "Website",
    "URL apply",
    "Hoa hồng",
    "Ngày cookie",
    "Danh mục",
    "Hoạt động",
    "Đang tạm dừng",
    "Traffic (hiển thị)",
    "Traffic ước tính/tháng",
    "Trang/lượt xem",
    "Thời gian ở lại",
    "Tỷ lệ thoát",
    "Top quốc gia",
    "Top từ khóa",
    "Loại hoa hồng",
    "EPC",
    "Thanh toán",
    "Tiền tệ",
    "ID Refersion",
    "Client ID",
    "Offer ID",
]

COLLABS_CSV_HEADER = [
    "Trạng thái",
    "Thương hiệu",
    "Website",
    "Link Apply",
    "Link product",
    "Hoa hồng mạng lưới",
    "Thời gian giữ đơn",
    "Danh mục",
    "Đã lưu",
    "Quốc gia mục tiêu",
    "Traffic (hiển thị)",
    "Traffic ước tính/tháng",
    "Trang/lượt xem",
    "Thời gian ở lại",
    "Tỷ lệ thoát",
    "Top quốc gia",
    "Top từ khóa",
    "Link logo",
    "Offer ID",
    "ID Shopify Store",
]


def build_uppromote_csv_row_vi(offer: dict, item: dict, status: str) -> list:
    eng = engagement_from_item(item)
    estimated_monthly = estimated_monthly_visits_formatted(item, eng)
    return [
        status,
        offer.get("brand", ""),
        offer.get("url", ""),
        offer.get("client_url", ""),
        offer.get("offer", ""),
        format_uppromote_cookie_days_cell(offer.get("cookieDays", "")),
        offer.get("category", ""),
        eng.get("VisitsFormatted", ""),
        estimated_monthly,
        eng.get("PagePerVisit", ""),
        visit_duration_from_item(item, eng),
        format_percent_cell(offer.get("payout_rate", "")),
        format_percent_cell(offer.get("approval_rate", "")),
        format_percent_cell(eng.get("BounceRate", "")),
        top_countries_csv(item.get("TopCountryShares") or []),
        top_keywords_csv(keyword_shares_from_item(item)),
        offer.get("currency", ""),
        offer.get("offer_score", ""),
        offer.get("recommend_score", ""),
        offer.get("application_review", ""),
        offer.get("payments", ""),
        uppromote_payment_methods_csv(offer),
        join_list(offer.get("promotion_details")),
        join_list(offer.get("target_audience_customer_channels")),
        join_list(offer.get("target_audience_locations")),
        join_list(offer.get("target_audience_ages")),
        join_list(offer.get("target_audience_genders")),
        offer.get("can_apply_offer", ""),
        offer.get("is_applied_offer", ""),
        offer.get("offer_id", ""),
        offer.get("shop_id", ""),
        offer.get("program_id", ""),
        offer.get("mkp_listing_id", ""),
        offer.get("epc", ""),
    ]


def build_goaff_csv_row(offer: dict, item: dict, status: str) -> list:
    url = offer.get("url", "")
    eng = engagement_from_item(item)
    estimated_monthly = estimated_monthly_visits_formatted(item, eng)
    cookie_days = offer.get("cookieDays", "")
    cookie_days_text = str(cookie_days).strip() if cookie_days is not None else ""
    if cookie_days_text and cookie_days_text.replace(".", "", 1).isdigit():
        cookie_days_text = f"{cookie_days_text} day"
    return [
        status,
        offer.get("brand", ""),
        url,
        format_goaff_commission_amount_display(offer),
        cookie_days_text,
        eng.get("VisitsFormatted", ""),
        estimated_monthly,
        goaff_create_account_url(offer),
        eng.get("PagePerVisit", ""),
        visit_duration_from_item(item, eng),
        fmt_yes_no_01(offer.get("goaff_is_approved_automatically")),
        top_keywords_csv(keyword_shares_from_item(item)),
        format_percent_cell(eng.get("BounceRate", "")),
        top_countries_csv(item.get("TopCountryShares") or []),
        offer.get("currency", ""),
        offer.get("goaff_name", ""),
        fmt_yes_no_01(offer.get("goaff_are_registrations_open")),
        offer.get("goaff_commission_type", ""),
        offer.get("goaff_commission_on", ""),
        offer.get("goaff_id", ""),
    ]


def build_refersion_csv_row(offer: dict, item: dict, status: str) -> list:
    eng = engagement_from_item(item)
    estimated_monthly = estimated_monthly_visits_formatted(item, eng)
    return [
        status,
        offer.get("brand", ""),
        offer.get("url", ""),
        offer.get("client_url", ""),
        offer.get("offer", ""),
        format_uppromote_cookie_days_cell(offer.get("cookieDays", "")),
        offer.get("category", ""),
        refersion_active_from_denied(offer.get("refersion_denied")),
        fmt_yes_no_bool_like(offer.get("refersion_pending")),
        eng.get("VisitsFormatted", ""),
        estimated_monthly,
        eng.get("PagePerVisit", ""),
        visit_duration_from_item(item, eng),
        format_percent_cell(eng.get("BounceRate", "")),
        top_countries_csv(item.get("TopCountryShares") or []),
        top_keywords_csv(keyword_shares_from_item(item)),
        offer.get("commission_type", ""),
        offer.get("epc", ""),
        offer.get("payments", ""),
        offer.get("currency", ""),
        offer.get("refersion_id", ""),
        offer.get("refersion_client_id", ""),
        offer.get("refersion_offer_id", ""),
    ]


def build_collabs_csv_row(offer: dict, item: dict, status: str) -> list:
    eng = engagement_from_item(item)
    estimated_monthly = estimated_monthly_visits_formatted(item, eng)
    visits_display = visits_formatted_from_engagement(eng)
    website = str(offer.get("url", "") or "").strip()
    apply_url = str(offer.get("client_url", "") or "").strip()
    product_links = str(offer.get("product_link", "") or "").strip()
    if not apply_url and website:
        p = urlparse(website if "://" in website else f"https://{website}")
        if p.netloc:
            base = f"{p.scheme or 'https'}://{p.netloc}"
            apply_url = f"{base}/pages/collab"
    return [
        status,
        offer.get("brand", ""),
        website,
        apply_url,
        product_links,
        offer.get("offer", ""),
        format_collabs_holding_period(offer.get("collabs_holding_period", "")),
        offer.get("category", ""),
        fmt_yes_no_bool_like(offer.get("collabs_saved")),
        offer.get("collabs_target_countries", ""),
        visits_display,
        estimated_monthly,
        eng.get("PagePerVisit", ""),
        visit_duration_from_item(item, eng),
        format_percent_cell(eng.get("BounceRate", "")),
        top_countries_csv(item.get("TopCountryShares") or []),
        top_keywords_csv(keyword_shares_from_item(item)),
        offer.get("collabs_logo_url", ""),
        offer.get("offer_id", ""),
        offer.get("collabs_shopify_store_id", ""),
    ]


# Ký tự điều khiển (Apify/Similarweb đôi khi trả về) — openpyxl từ chối ghi Excel.
_ILLEGAL_EXCEL_CELL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_excel_cell(value):
    """Loại ký tự không hợp lệ với .xlsx; tránh IllegalCharacterError khi ghi ô."""
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return value
    s = str(value)
    if not s.strip() and s != "0":
        return ""
    s = _ILLEGAL_EXCEL_CELL_RE.sub("", s)
    if len(s) > 32767:
        s = s[:32767]
    return s


def write_xlsx_highlight_status(path: Path, header: list, rows: list, status_col: int = 0) -> None:
    """Ghi file Excel: dòng có trạng thái ĐẠT (hoặc GET) được tô nền xanh lá nhạt."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    wb = Workbook()
    ws = wb.active
    ws.append([sanitize_excel_cell(v) for v in header])
    header_list = [sanitize_excel_cell(v) for v in header]
    hyperlink_columns = {
        i + 1
        for i, name in enumerate(header_list)
        if str(name).strip() in {"Website", "URL apply", "Link đăng ký", "Link Apply"}
    }
    header_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    green = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
    for c in range(1, len(header_list) + 1):
        ws.cell(row=1, column=c).fill = header_fill
    ok_values = {STATUS_TRAFFIC_OK, "GET", "ĐẠT"}
    for row in rows:
        cells = []
        for v in list(row):
            if v is None or (isinstance(v, str) and not str(v).strip()):
                cells.append("N/A")
            else:
                cells.append(sanitize_excel_cell(v))
        ws.append(cells)
        r = ws.max_row
        for c in hyperlink_columns:
            if c <= len(cells):
                cell = ws.cell(row=r, column=c)
                value = str(cell.value or "").strip()
                if value.startswith("http://") or value.startswith("https://"):
                    cell.hyperlink = value
                    cell.style = "Hyperlink"
        if len(cells) > status_col and str(cells[status_col]).strip() in ok_values:
            for c in range(1, len(cells) + 1):
                ws.cell(row=r, column=c).fill = green
    wb.save(path)


def fetch_goaffpro_page(base_url: str, offset: int, limit: int) -> dict:
    request_url = with_goaffpro_paging(base_url, offset, limit)
    res = requests.get(request_url, headers=build_goaffpro_headers(), timeout=60)
    text = res.text
    try:
        body = res.json()
    except Exception as exc:
        raise RuntimeError(f"Goaffpro parse JSON lỗi (HTTP {res.status_code}): {text[:180]}") from exc
    if not res.ok:
        raise RuntimeError(f"Goaffpro HTTP {res.status_code}: {text[:300]}")
    return body if isinstance(body, dict) else {}


def with_refersion_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))


def fetch_refersion_page(base_url: str, page: int) -> dict:
    request_url = with_refersion_page(base_url, page)
    res = requests.get(request_url, headers=build_refersion_headers(), timeout=60)
    text = res.text
    try:
        body = res.json()
    except Exception as exc:
        raise RuntimeError(f"Refersion parse JSON lỗi (HTTP {res.status_code}): {text[:180]}") from exc
    if not res.ok:
        raise RuntimeError(f"Refersion HTTP {res.status_code}: {text[:300]}")
    if str(body.get("status") or "").lower() != "success":
        raise RuntimeError(f"Refersion API lỗi: {text[:300]}")
    return body if isinstance(body, dict) else {}


def fetch_collabs_page(
    base_url: str,
    first: int,
    after: str | None = None,
    product_categories: list | None = None,
    search_query: str | None = None,
) -> dict:
    payload = {
        "operationName": "BrandsQuery",
        "query": COLLABS_BRANDS_QUERY,
        "variables": {
            "first": int(first),
            "productCategories": norm_collabs_product_categories(product_categories),
            "brandValues": [],
        },
    }
    sq = str(search_query or "").strip()
    if sq:
        payload["variables"]["searchQuery"] = sq
    if after:
        payload["variables"]["after"] = str(after)
    max_retries = int(os.getenv("COLLABS_HTTP_RETRIES", "6") or "6")
    retry_base_ms = int(os.getenv("COLLABS_HTTP_RETRY_BASE_MS", "800") or "800")
    body = None
    text = ""
    res = None
    for attempt in range(max_retries + 1):
        res = requests.post(base_url, headers=build_collabs_headers(), json=payload, timeout=60)
        text = res.text
        if res.status_code == 429 or res.status_code >= 500:
            if attempt >= max_retries:
                break
            wait_ms = retry_base_ms * (2**attempt)
            time.sleep(wait_ms / 1000)
            continue
        try:
            body = res.json()
        except Exception as exc:
            if attempt >= max_retries:
                raise RuntimeError(
                    f"Collabs parse JSON lỗi (HTTP {res.status_code}): {text[:180]}"
                ) from exc
            time.sleep(retry_base_ms / 1000)
            continue
        break
    if body is None:
        raise RuntimeError(f"Collabs HTTP {res.status_code}: {text[:300]}")
    if not res.ok:
        raise RuntimeError(f"Collabs HTTP {res.status_code}: {text[:300]}")
    if body.get("errors"):
        raise RuntimeError(f"Collabs GraphQL lỗi: {json.dumps(body.get('errors'), ensure_ascii=False)[:300]}")
    return body if isinstance(body, dict) else {}


def _collabs_brands_search(body: dict) -> dict:
    data = body.get("data") if isinstance(body, dict) else {}
    search = data.get("brandsNetworkSearch") if isinstance(data, dict) else {}
    return search if isinstance(search, dict) else {}


def _collabs_shard_total_count(
    base_url: str,
    page_size: int,
    product_categories: list | None,
    search_query: str,
) -> int:
    body = fetch_collabs_page(
        base_url,
        page_size,
        product_categories=product_categories,
        search_query=search_query or None,
    )
    search = _collabs_brands_search(body)
    try:
        return int(search.get("totalCount") or 0)
    except (TypeError, ValueError):
        return 0


def _collabs_paginate_shard(
    base_url: str,
    page_size: int,
    product_categories: list | None,
    search_query: str,
    delay_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
    max_pages: int | None = None,
) -> list[dict]:
    """Lấy hết brand trong một shard searchQuery (totalCount phải <= ngưỡng shard)."""
    after = None
    out: list[dict] = []
    pages = 0
    page_cap = max_pages if max_pages is not None else COLLABS_SHARD_MAX_PAGES
    while pages < page_cap:
        if should_stop and should_stop():
            break
        body = fetch_collabs_page(
            base_url,
            page_size,
            after=after,
            product_categories=product_categories,
            search_query=search_query or None,
        )
        search = _collabs_brands_search(body)
        nodes = search.get("nodes") or []
        if not isinstance(nodes, list):
            nodes = []
        if not nodes:
            break
        pages += 1
        out.extend([n for n in nodes if isinstance(n, dict)])
        info = search.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
        if not after:
            break
        shard_delay = max(delay_ms, int(os.getenv("COLLABS_SHARD_PAGE_DELAY_MS", "50") or "50"))
        if shard_delay > 0:
            time.sleep(shard_delay / 1000)
    return out


def fetch_all_collabs_brands_nodes(
    base_url: str,
    product_categories: list | None = None,
    delay_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
    log_fn: Callable[[str], None] | None = None,
    shard_threshold: int | None = None,
    max_count: int | None = None,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    """Tải brand Discovery — chia searchQuery (a, aa, ab…) khi totalCount > ~996.

    max_count: tối đa brand *mới* (chưa có trong exclude_ids). None = không giới hạn.
    """
    threshold = shard_threshold if shard_threshold is not None else COLLABS_SHARD_FETCH_THRESHOLD
    page_size = DEFAULT_COLLABS_LIMIT
    queue: list[str] = [""]
    by_id: dict[str, dict] = {}
    exclude = exclude_ids or set()
    out: list[dict] = []
    shards_fetched = 0

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    while queue:
        if should_stop and should_stop():
            break
        prefix = queue.pop(0)
        if should_stop and should_stop():
            break
        try:
            total = _collabs_shard_total_count(base_url, page_size, product_categories, prefix)
        except Exception as exc:
            _log(f"Collabs shard {prefix!r}: lỗi đếm — {exc}")
            continue
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
        if total <= 0:
            continue
        label = prefix if prefix else "(tất cả)"
        if total > threshold:
            if len(prefix) >= COLLABS_SHARD_MAX_DEPTH:
                _log(
                    f"Collabs shard {label}: totalCount={total} vượt ngưỡng nhưng đã chạm "
                    f"max depth={COLLABS_SHARD_MAX_DEPTH}, lấy tạm shard này."
                )
            else:
                _log(f"Collabs shard {label}: totalCount={total} — chia nhỏ…")
                for ch in COLLABS_SHARD_ALPHABET:
                    queue.append(prefix + ch)
                continue
        nodes = _collabs_paginate_shard(
            base_url,
            page_size,
            product_categories,
            prefix,
            delay_ms=delay_ms,
            should_stop=should_stop,
        )
        new_n = 0
        for node in nodes:
            nid = str(node.get("id") or "").strip()
            if not nid or nid in exclude or nid in by_id:
                continue
            by_id[nid] = node
            out.append(node)
            new_n += 1
            if max_count is not None and len(out) >= max_count:
                _log(
                    f"Collabs shard {label}: đủ {max_count} brand mới — dừng shard."
                )
                return out[:max_count]
        shards_fetched += 1
        _log(
            f"Collabs shard {label}: +{new_n} brand mới "
            f"(shard {len(nodes)}, tổng mới {len(out)}/{total})"
        )

    _log(f"Collabs: hoàn tất shard — {shards_fetched} shard, {len(out)} brand mới.")
    return out


def fetch_collabs_cursor_brand_ids(
    base_url: str,
    product_categories: list | None = None,
    search_query: str | None = None,
    delay_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
) -> set[str]:
    """Thu thập toàn bộ brand id từ cursor Discovery (không searchQuery) — dùng loại trùng khi phân trang shard."""
    after = None
    out: set[str] = set()
    while True:
        if should_stop and should_stop():
            break
        body = fetch_collabs_page(
            base_url,
            DEFAULT_COLLABS_LIMIT,
            after=after,
            product_categories=product_categories,
            search_query=search_query,
        )
        search = _collabs_brands_search(body)
        nodes = search.get("nodes") or []
        if not isinstance(nodes, list) or not nodes:
            break
        for node in nodes:
            if isinstance(node, dict):
                nid = str(node.get("id") or "").strip()
                if nid:
                    out.add(nid)
        info = search.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            break
        after = info.get("endCursor")
        if not after:
            break
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
    return out


def _iter_collabs_shard_brands(
    base_url: str,
    product_categories: list | None,
    exclude_ids: set[str],
    *,
    search_query_base: str = "",
    delay_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
    max_pages_per_prefix: int | None = None,
):
    """Duyệt brand shard theo thứ tự cố định: prefix a→z→0-9, cursor từng prefix."""
    exclude = exclude_ids or set()
    seen: set[str] = set()
    page_cap = max_pages_per_prefix if max_pages_per_prefix is not None else COLLABS_SHARD_MAX_PAGES
    base_q = str(search_query_base or "").strip()
    for prefix in COLLABS_SHARD_ALPHABET:
        if should_stop and should_stop():
            return
        after = None
        pages = 0
        while pages < page_cap:
            if should_stop and should_stop():
                return
            body = fetch_collabs_page(
                base_url,
                DEFAULT_COLLABS_LIMIT,
                after=after,
                product_categories=product_categories,
                search_query=((f"{base_q} {prefix}".strip()) if base_q else (prefix or None)),
            )
            search = _collabs_brands_search(body)
            nodes = search.get("nodes") or []
            if not isinstance(nodes, list) or not nodes:
                break
            pages += 1
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                nid = str(node.get("id") or "").strip()
                if not nid or nid in exclude or nid in seen:
                    continue
                seen.add(nid)
                yield node
            info = search.get("pageInfo") or {}
            if not info.get("hasNextPage"):
                break
            after = info.get("endCursor")
            if not after:
                break
            shard_delay = max(delay_ms, int(os.getenv("COLLABS_SHARD_PAGE_DELAY_MS", "50") or "50"))
            if shard_delay > 0:
                time.sleep(shard_delay / 1000)


def fetch_collabs_brands_shard_paginated(
    base_url: str,
    product_categories: list | None,
    exclude_ids: set[str],
    max_count: int,
    search_query_base: str = "",
    skip_count: int = 0,
    delay_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> list[dict]:
    """
    Lấy brand shard theo thứ tự cố định (a→z→0-9), bỏ qua skip_count brand đầu, lấy max_count tiếp theo.
    Không random — mỗi start_page/end_page cho batch shard khác nhau.
    """
    if max_count <= 0:
        return []
    skip_count = max(0, int(skip_count or 0))

    def _log(msg: str) -> None:
        if log_fn:
            log_fn(msg)

    if skip_count:
        _log(
            f"Collabs shard: bỏ qua {skip_count} brand (phân trang cố định), "
            f"lấy tối đa {max_count} brand…"
        )
    else:
        _log(f"Collabs shard: đang lấy tối đa {max_count} brand mới…")

    skipped = 0
    out: list[dict] = []
    for node in _iter_collabs_shard_brands(
        base_url,
        product_categories,
        exclude_ids,
        search_query_base=search_query_base,
        delay_ms=delay_ms,
        should_stop=should_stop,
    ):
        if skipped < skip_count:
            skipped += 1
            continue
        out.append(node)
        if len(out) >= max_count:
            return out[:max_count]
    if skip_count and skipped < skip_count and not out:
        _log(
            f"Collabs shard: không đủ brand để bỏ qua {skip_count} "
            f"(chỉ có {skipped} brand sau khi loại trùng cursor)."
        )
    return out[:max_count]


def fetch_collabs_brands_shard_fill(
    base_url: str,
    product_categories: list | None,
    exclude_ids: set[str],
    max_count: int,
    search_query_base: str = "",
    delay_ms: int = 0,
    should_stop: Callable[[], bool] | None = None,
    log_fn: Callable[[str], None] | None = None,
    skip_count: int = 0,
) -> list[dict]:
    """Lấy brand mới qua searchQuery a-z0-9 (thứ tự cố định, có thể skip phân trang)."""
    return fetch_collabs_brands_shard_paginated(
        base_url,
        product_categories,
        exclude_ids,
        max_count=max_count,
        search_query_base=search_query_base,
        skip_count=skip_count,
        delay_ms=delay_ms,
        should_stop=should_stop,
        log_fn=log_fn,
    )


def fetch_collabs_brand_profile(base_url: str, shopify_store_gid: str) -> dict:
    gid = str(shopify_store_gid or "").strip()
    if not gid:
        return {}
    payload = {
        "operationName": "DiscoverBrandProfileQuery",
        "query": COLLABS_BRAND_PROFILE_QUERY,
        "variables": {
            "shopifyStoreId": gid,
        },
    }
    res = requests.post(base_url, headers=build_collabs_headers(), json=payload, timeout=60)
    text = res.text
    try:
        body = res.json()
    except Exception as exc:
        raise RuntimeError(f"Collabs detail parse JSON lỗi (HTTP {res.status_code}): {text[:180]}") from exc
    if not res.ok:
        raise RuntimeError(f"Collabs detail HTTP {res.status_code}: {text[:300]}")
    if body.get("errors"):
        raise RuntimeError(f"Collabs detail GraphQL lỗi: {json.dumps(body.get('errors'), ensure_ascii=False)[:300]}")
    data = body.get("data") if isinstance(body, dict) else {}
    return data if isinstance(data, dict) else {}


def _money_to_float(v) -> float:
    try:
        return float(str(v or "").strip())
    except (TypeError, ValueError):
        return 0.0


def _build_product_entry(url: str, min_amount, max_amount, currency: str = "") -> dict:
    u = str(url or "").strip()
    if not u:
        return {}
    mn = _money_to_float(min_amount)
    mx = _money_to_float(max_amount)
    avg = (mn + mx) / 2.0 if (mn or mx) else 0.0
    cur = str(currency or "").strip().upper()
    if cur in {"NONE", "NULL", "N/A", "NA"}:
        cur = ""
    if not cur:
        cur = str(os.getenv("COLLABS_DEFAULT_CURRENCY", "USD") or "USD").strip().upper()
    if cur and avg > 0:
        line = f"{avg:.2f} {cur} - {u}"
    elif avg > 0:
        line = f"{avg:.2f} - {u}"
    else:
        line = u
    return {"url": u, "avg_price": avg, "currency": cur, "line": line}


def fetch_collabs_product_links(
    base_url: str,
    shopify_store_id: str,
    *,
    brand_name: str = "",
    store_name: str = "",
    first: int = 36,
    max_pages: int = 1,
    target_count: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    delay_ms: int = 0,
) -> list[dict]:
    """
    Lấy danh sách product link theo brand/shopifyStoreId trong Discovery.
    Ưu tiên thử searchTerm theo tên brand/store để tăng độ chính xác và tốc độ.
    Ưu tiên product.url (link sản phẩm storefront), fallback affiliateProduct.url.
    """
    sid = str(shopify_store_id or "").strip()
    if not sid:
        return []
    products_seed = str(
        os.getenv("COLLABS_PRODUCTS_SEED", "6c9efb8b-2B19-4FD3-D6F4-3B6BDD54") or ""
    ).strip() or "6c9efb8b-2B19-4FD3-D6F4-3B6BDD54"

    out: list[dict] = []
    seen: set[str] = set()
    after = None
    pages = 0
    page_cap = max(1, int(max_pages or 1))
    size = max(1, int(first or 36))
    target = int(target_count) if target_count is not None else 0
    if target < 0:
        target = 0
    bn = str(brand_name or "").strip()
    sn = str(store_name or "").strip()

    def _norm_text(v: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", str(v or "").lower())

    bn_norm = _norm_text(bn)
    sn_norm = _norm_text(sn)
    candidate_terms: list[str] = []
    for t in (bn, sn):
        tt = str(t or "").strip()
        if tt and tt not in candidate_terms:
            candidate_terms.append(tt)
    # fallback query rộng nếu query theo tên chưa đủ.
    candidate_terms.append("")
    for term in candidate_terms:
        after = None
        pages = 0
        while pages < page_cap:
            if should_stop and should_stop():
                break
            payload = {
                "operationName": "ProductsQuery",
                "query": COLLABS_PRODUCTS_QUERY,
                "variables": {
                    "first": size,
                    "searchParams": {
                        "brandValues": [],
                        "categories": [],
                    },
                    "seed": products_seed,
                },
            }
            if term:
                payload["variables"]["searchParams"]["searchTerm"] = term
            if after:
                payload["variables"]["after"] = str(after)
            res = requests.post(base_url, headers=build_collabs_headers(), json=payload, timeout=60)
            text = res.text
            try:
                body = res.json()
            except Exception as exc:
                raise RuntimeError(
                    f"Collabs Products parse JSON lỗi (HTTP {res.status_code}): {text[:180]}"
                ) from exc
            if not res.ok:
                raise RuntimeError(f"Collabs Products HTTP {res.status_code}: {text[:300]}")
            gql_errors = body.get("errors") if isinstance(body, dict) else None
            if gql_errors:
                err_text = json.dumps(gql_errors, ensure_ascii=False)
                allow_partial = "UNAUTHORIZED" in err_text.upper()
                data_candidate = body.get("data") if isinstance(body, dict) else {}
                has_products_nodes = bool(
                    isinstance(data_candidate, dict)
                    and isinstance(data_candidate.get("products"), dict)
                    and isinstance((data_candidate.get("products") or {}).get("nodes"), list)
                )
                if not (allow_partial and has_products_nodes):
                    raise RuntimeError(f"Collabs Products GraphQL lỗi: {err_text[:300]}")
            data = body.get("data") if isinstance(body, dict) else {}
            products = data.get("products") if isinstance(data, dict) else {}
            nodes = products.get("nodes") if isinstance(products, dict) else []
            if not isinstance(nodes, list) or not nodes:
                break
            pages += 1
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                store = node.get("shopifyStore") if isinstance(node.get("shopifyStore"), dict) else {}
                node_sid = str(store.get("shopifyStoreId") or "").strip()
                node_store_name = str(store.get("name") or "").strip()
                if node_sid and node_sid != sid:
                    continue
                if not node_sid:
                    node_store_norm = _norm_text(node_store_name)
                    if bn_norm and bn_norm not in node_store_norm and sn_norm and sn_norm not in node_store_norm:
                        continue
                aff = node.get("affiliateProduct") if isinstance(node.get("affiliateProduct"), dict) else {}
                url = str(node.get("url") or aff.get("url") or "").strip()
                if not url or url in seen:
                    continue
                min_price = node.get("minPrice") if isinstance(node.get("minPrice"), dict) else {}
                max_price = node.get("maxPrice") if isinstance(node.get("maxPrice"), dict) else {}
                min_amount = (min_price or {}).get("amount")
                max_amount = (max_price or {}).get("amount")
                currency = (
                    (min_price or {}).get("currency")
                    or (max_price or {}).get("currency")
                    or ""
                )
                entry = _build_product_entry(url, min_amount, max_amount, currency)
                if not entry:
                    continue
                seen.add(url)
                out.append(entry)
                if target > 0 and len(out) >= target:
                    return out[:target]
            info = products.get("pageInfo") if isinstance(products, dict) else {}
            has_next = bool(info.get("hasNextPage")) if isinstance(info, dict) else False
            after = info.get("endCursor") if isinstance(info, dict) else None
            if not has_next or not after:
                break
            if delay_ms > 0:
                time.sleep(delay_ms / 1000)
        if target > 0 and len(out) >= target:
            return out[:target]
    return out[:target] if target > 0 else out


def fetch_shopify_storefront_product_links(
    site_url: str,
    *,
    max_count: int = 24,
    max_pages: int = 2,
    timeout_sec: int = 20,
    should_stop: Callable[[], bool] | None = None,
    delay_ms: int = 0,
) -> list[dict]:
    """
    Fallback lấy product link trực tiếp từ storefront Shopify qua /products.json.
    """
    raw = str(site_url or "").strip()
    if not raw:
        return []
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if not parsed.netloc:
        return []
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    out: list[dict] = []
    seen: set[str] = set()
    cap = max(1, int(max_count or 24))
    pages = max(1, int(max_pages or 1))
    for p in range(1, pages + 1):
        if should_stop and should_stop():
            break
        api_url = f"{base}/products.json?limit=250&page={p}"
        try:
            res = requests.get(api_url, timeout=timeout_sec)
            if not res.ok:
                break
            body = res.json()
        except Exception:
            break
        products = body.get("products") if isinstance(body, dict) else []
        if not isinstance(products, list) or not products:
            break
        for prod in products:
            if not isinstance(prod, dict):
                continue
            handle = str(prod.get("handle") or "").strip()
            if not handle:
                continue
            u = f"{base}/products/{handle}"
            if u in seen:
                continue
            variants = prod.get("variants") if isinstance(prod.get("variants"), list) else []
            prices: list[float] = []
            for var in variants:
                if not isinstance(var, dict):
                    continue
                prices.append(_money_to_float(var.get("price")))
            min_amount = min(prices) if prices else 0.0
            max_amount = max(prices) if prices else min_amount
            first_variant = variants[0] if variants and isinstance(variants[0], dict) else {}
            currency = str(
                first_variant.get("currency")
                or first_variant.get("currency_code")
                or prod.get("currency")
                or ""
            ).strip()
            entry = _build_product_entry(u, min_amount, max_amount, currency)
            if not entry:
                continue
            seen.add(u)
            out.append(entry)
            if len(out) >= cap:
                return out[:cap]
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
    return out[:cap]


def fetch_all_goaffpro_offers() -> list:
    base_url = (os.getenv("GOAFFPRO_API_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Thiếu GOAFFPRO_API_URL trong .env")

    enforce_fixed_fetch_defaults()
    limit = int(os.getenv("GOAFFPRO_LIMIT", str(DEFAULT_OFFERS_PER_PAGE)) or str(DEFAULT_OFFERS_PER_PAGE))
    max_pages_cap = goaffpro_max_pages_cap()
    delay_ms = int(
        os.getenv("GOAFFPRO_PAGE_DELAY_MS", str(DEFAULT_GOAFFPRO_PAGE_DELAY_MS))
        or str(DEFAULT_GOAFFPRO_PAGE_DELAY_MS)
    )

    brand_cap = net_sources_max_brands_per_run()
    all_stores = []
    page = 1
    while True:
        offset = (page - 1) * limit
        print(f"Goaffpro: tải offset={offset} (trang {page})...")
        body = fetch_goaffpro_page(base_url, offset, limit)
        page_items = body.get("stores") or []
        if not isinstance(page_items, list):
            page_items = []

        if not page_items:
            print(f"Goaffpro: không còn store — kết thúc phân trang.")
            break

        room = brand_cap - len(all_stores)
        if room <= 0:
            break
        if len(page_items) > room:
            page_items = page_items[:room]
        all_stores.extend(page_items)
        print(f"Goaffpro: +{len(page_items)} store (lũy kế {len(all_stores)})")
        if len(all_stores) >= brand_cap:
            print(f"Goaffpro: đạt giới hạn {brand_cap} brand/lần lọc.")
            break

        if max_pages_cap is not None and page >= max_pages_cap:
            print(f"Goaffpro: dừng vì GOAFFPRO_MAX_PAGES={max_pages_cap}")
            break

        total_count = body.get("count")
        try:
            total_n = int(total_count) if total_count is not None else None
        except Exception:
            total_n = None
        if total_n is not None and offset + len(page_items) >= total_n:
            break

        if len(page_items) < limit:
            break

        page += 1
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

    return [map_goaffpro_store(s) for s in all_stores]


def fetch_all_refersion_offers() -> list:
    base_url = (os.getenv("REFERSION_API_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Thiếu REFERSION_API_URL trong .env")
    enforce_fixed_fetch_defaults()
    max_pages_cap = refersion_max_pages_cap()
    delay_ms = int(
        os.getenv("REFERSION_PAGE_DELAY_MS", str(DEFAULT_REFERSION_PAGE_DELAY_MS))
        or str(DEFAULT_REFERSION_PAGE_DELAY_MS)
    )
    brand_cap = net_sources_max_brands_per_run()
    all_offers = []
    page = 1
    while True:
        print(f"Refersion: tải trang {page}...")
        body = fetch_refersion_page(base_url, page)
        payload = body.get("data") or {}
        page_items = payload.get("offers") or []
        if not isinstance(page_items, list):
            page_items = []
        if not page_items:
            print("Refersion: không còn offer — kết thúc phân trang.")
            break
        room = brand_cap - len(all_offers)
        if room <= 0:
            break
        if len(page_items) > room:
            page_items = page_items[:room]
        all_offers.extend(page_items)
        print(f"Refersion: +{len(page_items)} offer (lũy kế {len(all_offers)})")
        if len(all_offers) >= brand_cap:
            print(f"Refersion: đạt giới hạn {brand_cap} brand/lần lọc.")
            break
        if max_pages_cap is not None and page >= max_pages_cap:
            print(f"Refersion: dừng vì REFERSION_MAX_PAGES={max_pages_cap}")
            break
        total_results = payload.get("total_results")
        try:
            total_n = int(total_results) if total_results is not None else None
        except Exception:
            total_n = None
        if total_n is not None and len(all_offers) >= total_n:
            break
        if len(page_items) == 0:
            break
        page += 1
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)
    return [map_refersion_offer(o) for o in all_offers]


def map_uppromote_offer(offer: dict, detail: dict | None = None) -> dict:
    detail = detail or {}
    website = detail.get("website")
    url = website.strip() if isinstance(website, str) and website.strip() else offer_url_from_uppromote(offer)
    return {
        "brand": detail.get("name") or offer.get("name") or "",
        "url": url,
        "offer": detail.get("commission") or offer.get("commission") or "",
        "cookieDays": detail.get("cookie") or offer.get("cookie") or "",
        "client_url": detail.get("apply_url") or offer.get("apply_url") or "",
        "offer_id": offer.get("id") or "",
        "shop_id": offer.get("shop_id") or detail.get("shop_id") or "",
        "program_id": offer.get("program_id") or detail.get("program_id") or "",
        "mkp_listing_id": detail.get("mkp_listing_id") or offer.get("id") or "",
        "commission_type": detail.get("commission_type") or offer.get("commissionText") or offer.get("commission_type") or "",
        "category": detail.get("categories") or offer.get("categories") or "",
        "epc": detail.get("average_earning_per_sale") or offer.get("average_earning_per_sale") or "",
        "payments": detail.get("payout_period") or offer.get("payout_period") or "",
        "currency": detail.get("currency") or offer.get("currency") or "",
        "payout_rate": detail.get("payout_rate") or offer.get("payout_rate") or "",
        "approval_rate": detail.get("approval_rate") or offer.get("approval_rate") or "",
        "offer_score": detail.get("offer_score") or offer.get("offer_score") or "",
        "recommend_score": detail.get("recommend_score") or offer.get("recommend_score") or "",
        "application_review": detail.get("application_review") or offer.get("application_review") or "",
        "promotion_details": detail.get("promotion_details") or offer.get("promotion_details") or [],
        "target_audience_customer_channels": detail.get("target_audience_customer_channels")
        or offer.get("target_audience_customer_channels")
        or [],
        "target_audience_locations": detail.get("target_audience_locations") or offer.get("target_audience_locations") or [],
        "target_audience_ages": detail.get("target_audience_ages") or offer.get("target_audience_ages") or [],
        "target_audience_genders": detail.get("target_audience_genders") or offer.get("target_audience_genders") or [],
        "can_apply_offer": detail.get("can_apply_offer") if "can_apply_offer" in detail else offer.get("can_apply_offer"),
        "is_applied_offer": detail.get("is_applied_offer") if "is_applied_offer" in detail else offer.get("is_applied_offer"),
        "payment_support": detail.get("payment_support") or offer.get("payment_support"),
    }


def fetch_uppromote_page(
    base_url: str,
    page: int,
    category_ids: list[int] | None = None,
    _retry_after_login: bool = False,
) -> dict:
    request_url = with_page(base_url, page, category_ids=category_ids)
    res = requests.get(request_url, headers=build_uppromote_headers(), timeout=60)
    text = res.text

    # 401 → thử auto-login rồi retry một lần
    if res.status_code == 401 and not _retry_after_login:
        _uppromote_ui_log("Token hết hạn (401) — đang tự động đăng nhập lại (Edge ẩn)...")
        if _auto_login_uppromote_browser():
            _uppromote_ui_log("Đăng nhập lại thành công — token đã cập nhật, tiếp tục tải offer.")
            return fetch_uppromote_page(
                base_url, page, category_ids=category_ids, _retry_after_login=True
            )
        raise RuntimeError("Uppromote auto-login thất bại, không lấy được token mới.")

    try:
        body = res.json()
    except Exception as exc:
        raise RuntimeError(f"Uppromote parse JSON lỗi (HTTP {res.status_code}): {text[:180]}") from exc
    if not res.ok:
        raise RuntimeError(f"Uppromote HTTP {res.status_code}: {text[:300]}")
    if body.get("status") not in (200, "200"):
        raise RuntimeError(f"Uppromote API lỗi: {text[:300]}")
    
    # Debug: log cấu trúc response
    print(f"[Uppromote DEBUG] status={body.get('status')}, keys={list(body.keys())}", flush=True)
    data = body.get("data")
    if isinstance(data, dict):
        print(f"[Uppromote DEBUG] data.keys={list(data.keys())}, items={type(data.get('data'))}", flush=True)
    
    return body


def fetch_all_uppromote_offers() -> list:
    base_url = assert_uppromote_api_url(os.getenv("UPPROMOTE_API_URL") or "")

    enforce_fixed_fetch_defaults()
    max_pages_cap = uppromote_max_pages_cap()
    delay_ms = int(os.getenv("UPPROMOTE_PAGE_DELAY_MS", str(DEFAULT_UPPROMOTE_PAGE_DELAY_MS)) or str(DEFAULT_UPPROMOTE_PAGE_DELAY_MS))

    brand_cap = net_sources_max_brands_per_run()
    all_offers = []
    page = 1
    while True:
        print(f"Uppromote: tải trang {page}...")
        body = fetch_uppromote_page(base_url, page)
        payload = body.get("data") or {}
        page_items = payload.get("data") or []
        if not isinstance(page_items, list):
            page_items = []

        if not page_items:
            print(f"Uppromote: trang {page} không còn offer — kết thúc phân trang.")
            break

        room = brand_cap - len(all_offers)
        if room <= 0:
            break
        if len(page_items) > room:
            page_items = page_items[:room]
        all_offers.extend(page_items)
        print(f"Uppromote: +{len(page_items)} offer (lũy kế {len(all_offers)})")
        if len(all_offers) >= brand_cap:
            print(f"Uppromote: đạt giới hạn {brand_cap} brand/lần lọc.")
            break

        if max_pages_cap is not None and page >= max_pages_cap:
            print(f"Uppromote: dừng vì UPPROMOTE_MAX_PAGES={max_pages_cap}")
            break

        next_page = payload.get("next_page_url")
        if not next_page:
            break

        page += 1
        if delay_ms > 0:
            time.sleep(delay_ms / 1000)

    detail_delay_ms = int(os.getenv("UPPROMOTE_DETAIL_DELAY_MS", "50") or "50")
    mapped = []
    for i, offer in enumerate(all_offers, start=1):
        detail = {}
        shop_id = offer.get("shop_id")
        if shop_id:
            try:
                detail = fetch_uppromote_offer_detail(shop_id)
            except Exception as exc:
                print(f"Cảnh báo: không lấy được detail cho shop_id={shop_id}: {exc}")
            if detail_delay_ms > 0:
                time.sleep(detail_delay_ms / 1000)
        mapped_offer = map_uppromote_offer(offer, detail)
        mapped.append(mapped_offer)
        if i % 20 == 0 or i == len(all_offers):
            print(f"Uppromote detail: {i}/{len(all_offers)}")
    return mapped


def read_domains_from_txt(path: Path) -> list:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if t:
                out.append(t)
    return out


def unique_hosts(items: list) -> list:
    return sorted({host_key(x) for x in items if host_key(x)})


def top_countries_csv(countries, limit=3):
    if not isinstance(countries, list):
        return ""
    values = []
    for c in countries[:limit]:
        code = c.get("CountryCode", "")
        val = c.get("Value", 0)
        try:
            pct = round(float(val), 2)
        except Exception:
            pct = 0
        values.append(f"{code} ({pct}%)")
    return ", ".join(values)


def keyword_label(k):
    return k.get("Name") or k.get("Keyword") or k.get("keyword") or k.get("Key") or k.get("key") or ""


def keyword_volume(k):
    """Khối lượng tìm kiếm (Volume: …); không dùng Traffic/Visits — traffic nằm ở EstimatedValue."""
    candidates = [
        k.get("Volume"),
        k.get("SearchVolume"),
        k.get("MonthlyVolume"),
        k.get("EstimatedMonthlySearchVolume"),
    ]
    for raw in candidates:
        if isinstance(raw, (int, float)):
            return int(round(raw))
        if isinstance(raw, str) and raw.strip():
            v = parse_visits_value(raw)
            if v > 0:
                return int(round(v))
    return 0


def keyword_traffic_from_estimated(k):
    """Traffic hiển thị trong Top Keywords: ưu tiên EstimatedValue (Apify), rồi Traffic/EstTraffic…"""
    if not isinstance(k, dict):
        return 0
    candidates = [
        k.get("EstimatedValue"),
        k.get("estimatedValue"),
        k.get("Traffic"),
        k.get("traffic"),
        k.get("EstTraffic"),
        k.get("Visits"),
    ]
    for raw in candidates:
        if raw is None:
            continue
        if isinstance(raw, str) and not raw.strip():
            continue
        v = parse_visits_value(raw)
        if abs(v - round(v)) < 1e-9:
            return int(round(v))
        return round(v, 4)
    return 0


def keyword_cpc_number_str(k):
    """Phần số CPC (không kèm $) cho định dạng Cpc:1.07$."""
    if not isinstance(k, dict):
        return "0"
    raw = k.get("Cpc") or k.get("CPC") or k.get("cpc") or k.get("EstimatedCpc") or k.get("estimatedCpc")
    if raw is None or raw == "":
        return "0"
    if isinstance(raw, (int, float)):
        x = float(raw)
    else:
        s = str(raw).strip().rstrip("$").replace(",", "").strip()
        try:
            x = float(s)
        except ValueError:
            return "0"
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    t = f"{x:.4f}".rstrip("0").rstrip(".")
    return t or "0"


def top_keywords_csv(keywords, limit=TOP_KEYWORDS_COUNT):
    if not isinstance(keywords, list):
        return ""
    values = []
    for k in keywords[:limit]:
        if isinstance(k, str):
            s = k.strip()
            if s:
                values.append(s)
            continue
        if not isinstance(k, dict):
            continue
        label = keyword_label(k)
        if not label:
            continue
        vol = keyword_volume(k)
        traf = keyword_traffic_from_estimated(k)
        cpc = keyword_cpc_number_str(k)
        values.append(f"{label} (Volume: {vol}, Traffic: {traf}, Cpc:{cpc}$)")
    return ", ".join(values)


def join_list(value, sep="; "):
    if value is None:
        return ""
    if isinstance(value, list):
        return sep.join([str(x).strip() for x in value if str(x).strip()])
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return ""


UPPROMOTE_PAYMENT_METHOD_LABELS = {
    "paypal": "Paypal",
    "bank": "Bank transfer",
    "debit": "Debit card",
    "cheque": "Check",
    "venmo": "Venmo",
    "paytm": "PayTM",
    "upi": "UPI",
    "store_credit": "Store credit",
    "other": "Other",
}


def _normalize_payment_support(raw):
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            obj = json.loads(text)
        except Exception:
            try:
                obj = ast.literal_eval(text)
            except Exception:
                return None
        return obj if isinstance(obj, dict) else None
    return None


def _payment_support_method_on(support: dict, method_key: str) -> bool:
    if not method_key or not isinstance(support, dict):
        return False
    if method_key not in support:
        return False
    v = support[method_key]
    if v is True:
        return True
    if v is False or v is None:
        return False
    try:
        return int(v) == 1
    except (TypeError, ValueError):
        return str(v).strip() == "1"


def uppromote_payment_methods_csv(offer: dict) -> str:
    """Danh sách phương thức thanh toán bật trong payment_support, vd: Paypal, Bank transfer."""
    support = _normalize_payment_support((offer or {}).get("payment_support"))
    if not support:
        return ""
    labels: list[str] = []
    seen: set[str] = set()
    for key, label in UPPROMOTE_PAYMENT_METHOD_LABELS.items():
        if _payment_support_method_on(support, key):
            labels.append(label)
            seen.add(key)
    for key in support:
        k = str(key).strip().lower()
        if not k or k in seen:
            continue
        if _payment_support_method_on(support, k):
            labels.append(k.replace("_", " ").title())
    return ", ".join(labels)


def keyword_shares_from_item(item):
    eng = item.get("Engagments") or item.get("Engagements") or {}
    candidates = [
        item.get("TopKeywordShares"),
        item.get("TopKeywords"),
        eng.get("TopKeywordShares"),
        eng.get("TopKeywords"),
        item.get("TopOrganicKeywordShares"),
        item.get("TopOrganicKeywords"),
        eng.get("TopOrganicKeywordShares"),
        eng.get("TopOrganicKeywords"),
    ]
    for arr in candidates:
        if isinstance(arr, list) and arr:
            return arr
        if isinstance(arr, str) and arr.strip():
            return [arr.strip()]
    return []


def load_brand_average_prices() -> dict:
    path = BASE_DIR / "brand-prices.csv"
    if not path.exists():
        print("Không tìm thấy brand-prices.csv — cột avg_price và est_commission_per_sale sẽ để trống.")
        return {}
    result = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if not t or t.startswith("#"):
                continue
            parts = [x.strip() for x in t.split(",")]
            if len(parts) < 2:
                continue
            brand = parts[0].lower()
            num = parts[1].replace(",", "")
            try:
                result[brand] = float(num)
            except Exception:
                continue
    print(f"Đã load {len(result)} brand avg price từ brand-prices.csv")
    return result


def _normalize_apify_actor_id(actor_id: str) -> str:
    act = str(actor_id or "").strip()
    if "/" in act and "~" not in act:
        parts = [p for p in act.split("/") if p]
        if len(parts) >= 2:
            act = f"{parts[0]}~{parts[1]}"
    return act


class ApifyTokenFailover(Exception):
    """Token Apify hiện tại hết quota / lỗi quyền — thử token tiếp theo trong APIFY_TOKENS."""


def parse_apify_tokens_list(raw: str | None) -> list[str]:
    """Tách danh sách token Apify (mỗi dòng một token), bỏ trùng giữ thứ tự."""
    if raw is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for line in str(raw).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        tok = line.strip()
        if not tok or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    if len(out) <= 1:
        return out
    deduped: list[str] = []
    for tok in out:
        if any(other != tok and other.startswith(tok) for other in out):
            continue
        deduped.append(tok)
    return deduped


def apify_tokens_from_env() -> list[str]:
    """
    Danh sách token Apify theo thứ tự ưu tiên.
    Ưu tiên APIFY_TOKENS (nhiều dòng); tương thích .env cũ APIFY_TOKEN + APIFY_TOKEN_BACKUP.
    """
    multi = parse_apify_tokens_list(os.getenv("APIFY_TOKENS"))
    if multi:
        return multi
    out: list[str] = []
    seen: set[str] = set()
    for key in ("APIFY_TOKEN", "COLLABS_OUTSIDE_APIFY_TOKEN", "APIFY_TOKEN_BACKUP"):
        tok = (os.getenv(key) or "").strip()
        if tok and tok not in seen:
            out.append(tok)
            seen.add(tok)
    return out


def apify_primary_token() -> str:
    """Token Apify đầu tiên trong danh sách (Similarweb + Google Collabs ngoài Discovery)."""
    tokens = apify_tokens_from_env()
    return tokens[0] if tokens else ""


def apify_effective_token_candidates() -> list[str]:
    return apify_tokens_from_env()


def sync_apify_token_env(tokens: list[str] | None = None) -> None:
    """Đồng bộ biến môi trường legacy sau khi đọc/lưu APIFY_TOKENS."""
    lst = tokens if tokens is not None else apify_tokens_from_env()
    if lst:
        os.environ["APIFY_TOKENS"] = "\n".join(lst)
        os.environ["APIFY_TOKEN"] = lst[0]
        if len(lst) > 1:
            os.environ["APIFY_TOKEN_BACKUP"] = lst[1]
        else:
            os.environ.pop("APIFY_TOKEN_BACKUP", None)
    else:
        os.environ.pop("APIFY_TOKENS", None)
        os.environ.pop("APIFY_TOKEN", None)
        os.environ.pop("APIFY_TOKEN_BACKUP", None)


def _apify_tokens_missing_error(context: str = "") -> RuntimeError:
    prefix = f"Apify ({context}): " if context else "Apify: "
    return RuntimeError(
        f"{prefix}Thiếu token Apify (APIFY_TOKENS) — cần ít nhất một token (mỗi dòng một token)."
    )


def _apify_run_with_token_failover(label: str, runner):
    """Chạy runner(token) lần lượt với từng token; chỉ lỗi khi hết token."""
    candidates = apify_effective_token_candidates()
    if not candidates:
        raise _apify_tokens_missing_error(label)
    last_fail: Exception | None = None
    total = len(candidates)
    for idx, tok in enumerate(candidates):
        try:
            result = runner(tok)
            if idx > 0:
                print(f"Apify ({label}): đã chuyển sang token #{idx + 1}/{total}.")
            return result, tok
        except ApifyTokenFailover as exc:
            last_fail = exc
            if idx + 1 < total:
                print(f"Apify ({label}): token #{idx + 1}/{total} lỗi — thử token tiếp theo: {exc}")
                continue
            raise RuntimeError(
                f"Apify ({label}): tất cả {total} token đã hết quota hoặc lỗi quyền: {exc}"
            ) from exc
    if last_fail:
        raise RuntimeError(str(last_fail)) from last_fail
    raise _apify_tokens_missing_error(label)


def _apify_http_suggests_token_failover(status: int, body: str) -> bool:
    if status in (401, 402, 403, 429):
        return True
    low = (body or "")[:1200].lower()
    for hint in (
        "quota",
        "limit exceeded",
        "insufficient credit",
        "payment required",
        "unauthorized",
        "invalid token",
        "token is invalid",
        "expired",
        "usage was exceeded",
        "monthly usage",
        "exceeded your",
    ):
        if hint in low:
            return True
    return status == 400 and any(x in low for x in ("quota", "limit", "credit", "token"))


def _apify_store_actor_dataset_id_with_token(
    actor_id: str, run_input: dict, *, wait_secs: int | None, token: str
) -> str:
    """Một lần chạy actor với token cố định (POST + poll)."""
    ws = wait_secs if wait_secs is not None else int(os.getenv("APIFY_WAIT_FOR_FINISH_SECS", "240") or "240")
    http_retries = int(os.getenv("APIFY_HTTP_RETRIES", "3") or "3")
    if http_retries < 1:
        http_retries = 1
    connect_timeout_sec = float(os.getenv("APIFY_CONNECT_TIMEOUT_SECS", "20") or "20")
    if connect_timeout_sec < 3:
        connect_timeout_sec = 3.0

    def _request_with_retry(method: str, req_url: str, *, json_payload=None, read_timeout_sec: float = 60.0):
        last_exc: Exception | None = None
        for attempt in range(1, http_retries + 1):
            try:
                return requests.request(
                    method=method,
                    url=req_url,
                    json=json_payload,
                    timeout=(connect_timeout_sec, max(5.0, float(read_timeout_sec))),
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= http_retries:
                    break
                sleep_sec = min(6.0, 1.2 * attempt)
                print(f"Apify request retry {attempt}/{http_retries} sau lỗi: {exc}")
                time.sleep(sleep_sec)
        raise RuntimeError(f"Apify request thất bại sau {http_retries} lần thử: {last_exc}")

    act = _normalize_apify_actor_id(actor_id)
    if not act:
        raise RuntimeError("Thiếu actor id Apify.")
    url = f"https://api.apify.com/v2/acts/{act}/runs?token={token}&waitForFinish={int(ws)}"
    res = _request_with_retry("POST", url, json_payload=run_input, read_timeout_sec=float(ws) + 30.0)
    if not res.ok:
        body = (res.text or "")[:800]
        if _apify_http_suggests_token_failover(res.status_code, body):
            raise ApifyTokenFailover(f"HTTP {res.status_code}: {body[:300]}")
        raise RuntimeError(f"Apify call actor lỗi HTTP {res.status_code}: {res.text[:300]}")
    body = res.json()
    data = body.get("data") or {}
    run_id = data.get("id")
    if not run_id:
        raise RuntimeError("Apify không trả về run id")

    status = data.get("status")
    wait_poll_secs = int(os.getenv("APIFY_POLL_WAIT_SECS", "120") or "120")
    max_polls = int(os.getenv("APIFY_MAX_POLLS", "10") or "10")
    poll_idx = 0
    while status not in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
        poll_idx += 1
        if poll_idx > max_polls:
            raise RuntimeError(f"Apify run chưa hoàn tất sau {max_polls} lần poll (status={status})")
        poll_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}&waitForFinish={wait_poll_secs}"
        poll_res = _request_with_retry("GET", poll_url, read_timeout_sec=wait_poll_secs + 30)
        if not poll_res.ok:
            pb = (poll_res.text or "")[:800]
            if _apify_http_suggests_token_failover(poll_res.status_code, pb):
                raise ApifyTokenFailover(f"poll HTTP {poll_res.status_code}: {pb[:300]}")
            raise RuntimeError(f"Apify poll lỗi HTTP {poll_res.status_code}: {poll_res.text[:300]}")
        data = (poll_res.json() or {}).get("data") or data
        status = data.get("status")
        print(f"Apify poll {poll_idx}: status={status}")

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run không thành công (status={status})")

    dataset_id = data.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError("Apify không trả về defaultDatasetId")
    return str(dataset_id)


def _apify_store_actor_dataset_id(actor_id: str, run_input: dict, *, wait_secs: int | None = None) -> tuple[str, str]:
    """
    Chạy actor Apify Store (POST + poll), trả về (defaultDatasetId, token_đã_dùng).
    Thử lần lượt mọi token trong APIFY_TOKENS; chỉ lỗi khi tất cả token hết quota/lỗi quyền.
    """
    return _apify_run_with_token_failover(
        "Similarweb",
        lambda tok: _apify_store_actor_dataset_id_with_token(actor_id, run_input, wait_secs=wait_secs, token=tok),
    )


def apify_call_actor(domains: list) -> tuple[str, str]:
    if not domains:
        raise RuntimeError("Danh sách domain Apify rỗng")
    return _apify_store_actor_dataset_id(
        ACTOR_ID,
        {"domains": list(domains), "proxyConfiguration": {"useApifyProxy": False}},
    )


def _similarweb_monthly_text_has_positive_visits(text: str) -> bool:
    """Chuỗi dạng T1(577), T2(0) — chỉ coi là có traffic nếu có ít nhất một số trong ngoặc > 0."""
    if not text or not str(text).strip():
        return False
    for m in re.finditer(r"\(([^)]+)\)", str(text)):
        if parse_visits_value(m.group(1)) > 0:
            return True
    return False


def _similarweb_item_has_traffic(item: dict | None) -> bool:
    """
    Có dữ liệu traffic *dùng được* (số visits > 0 hoặc monthly có tháng > 0).
    Tránh coi chuỗi monthly chỉ toàn 0 / VisitsFormatted \"0\" là \"đã có traffic\" — khi đó vẫn cần fallback Radeance.
    """
    if not item:
        return False
    eng = engagement_from_item(item)
    if parse_visits_from_engagement(eng) > 0:
        return True
    em = str(estimated_monthly_visits_formatted(item, eng) or "").strip()
    if em and _similarweb_monthly_text_has_positive_visits(em):
        return True
    vf = str(visits_formatted_from_engagement(eng) or "").strip()
    if vf and parse_visits_value(vf) > 0:
        return True
    return False


def _format_visits_integer_display(v: float) -> str:
    try:
        n = int(round(float(v)))
    except Exception:
        return ""
    if n <= 0:
        return ""
    return f"{n:,}"


def _radeance_dataset_row_host_keys(raw: dict) -> set[str]:
    """Các host chuẩn hoá có thể suy ra từ một dòng dataset radeance/similarweb-scraper."""
    low = {str(k).strip().lower(): v for k, v in raw.items()}
    keys: set[str] = set()
    for cand in (
        raw.get("searchUrl"),
        raw.get("url"),
        raw.get("domain"),
        raw.get("website"),
        low.get("searchurl"),
        low.get("url"),
        low.get("domain"),
        low.get("website"),
    ):
        if isinstance(cand, str) and cand.strip():
            hk = host_key(cand.strip())
            if hk:
                keys.add(hk)
    return keys


def normalize_radeance_similarweb_item(raw: dict) -> dict:
    """
    Chuẩn hoá một dòng dataset từ radeance/similarweb-scraper về shape gần actor Similarweb cũ
    (Engagements, TopCountryShares, TopKeywordShares, EstimatedMonthlyVisits) để build_collabs_csv_row / lọc traffic hoạt động.
    """
    if not isinstance(raw, dict) or not raw:
        return {}
    low = {str(k).strip().lower(): v for k, v in raw.items()}
    domain = str(raw.get("domain") or low.get("domain") or "").strip()
    url = str(raw.get("url") or raw.get("searchUrl") or low.get("url") or low.get("searchurl") or "").strip()
    if not url and domain:
        d = domain.lstrip("/")
        url = f"https://{d}" if d else ""
    eng_in = raw.get("engagement") or raw.get("Engagement") or {}
    if not isinstance(eng_in, dict):
        eng_in = {}
    total_vis = (
        raw.get("totalVisits")
        or raw.get("TotalVisits")
        or low.get("totalvisits")
        or raw.get("Visits")
        or low.get("visits")
    )
    if total_vis is None:
        total_vis = eng_in.get("visits") or eng_in.get("Visits")
    visits_f = parse_visits_value(total_vis)
    if visits_f <= 0:
        for ak in (
            "traffic",
            "Traffic",
            "estimatedTraffic",
            "EstimatedTraffic",
            "estimatedVisits",
            "EstimatedVisits",
            "lastMonthVisits",
            "LastMonthVisits",
            "pageViews",
            "PageViews",
            "globalVisits",
            "GlobalVisits",
        ):
            v = raw.get(ak)
            if v is None:
                v = low.get(ak.lower())
            if v is None:
                continue
            pv = parse_visits_value(v)
            if pv > visits_f:
                visits_f = pv
    mv_arr = raw.get("monthlyVisits") or low.get("monthlyvisits")
    if visits_f <= 0 and isinstance(mv_arr, list) and mv_arr:
        best_mv = 0.0
        for row in mv_arr:
            if isinstance(row, dict):
                lv = row.get("visits") or row.get("Visits")
                if lv is not None:
                    best_mv = max(best_mv, parse_visits_value(lv))
        if best_mv > visits_f:
            visits_f = best_mv
    ppg = raw.get("pagesPerVisit")
    if ppg is None:
        ppg = eng_in.get("pagesPerVisit")
    br = raw.get("bounceRate")
    if br is None:
        br = eng_in.get("bounceRate")
    tos = raw.get("timeOnSite")
    if tos is None:
        tos = raw.get("avgVisitDurationSeconds")
    if tos is None:
        tos = raw.get("avgVisitDuration")
    if tos is None:
        tos = eng_in.get("timeOnSite")
    if tos is None:
        tos = eng_in.get("avgVisitDurationSeconds")
    if tos is None:
        tos = eng_in.get("avgVisitDuration")
    monthly_df = raw.get("monthlyVisitsDateFormat") or low.get("monthlyvisitsdateformat") or {}
    if isinstance(monthly_df, str) and monthly_df.strip().startswith("{"):
        try:
            monthly_df = json.loads(monthly_df)
        except Exception:
            monthly_df = {}
    if not isinstance(monthly_df, dict):
        monthly_df = {}
    if visits_f <= 0 and monthly_df:
        try:
            mx = max((parse_visits_value(v) for v in monthly_df.values()), default=0.0)
            if mx > visits_f:
                visits_f = mx
        except Exception:
            pass

    top_country_shares: list[dict] = []
    tcc_raw = raw.get("website_traffic_by_country") or raw.get("countryShare") or []
    if isinstance(tcc_raw, list):
        for row in tcc_raw[:12]:
            if not isinstance(row, dict):
                continue
            code = str(row.get("country") or row.get("CountryCode") or "").strip().upper()
            if not code:
                continue
            sh = row.get("share")
            if sh is None:
                sh = row.get("Value")
            try:
                fv = float(sh)
            except Exception:
                fv = 0.0
            if 0 <= fv <= 1.0:
                fv *= 100.0
            top_country_shares.append({"CountryCode": code, "Value": fv})

    top_kw: list[dict] = []
    tk_raw = raw.get("topKeywords") or []
    if isinstance(tk_raw, list):
        for row in tk_raw:
            if not isinstance(row, dict):
                continue
            kw = row.get("keyword") or row.get("Keyword") or row.get("Name")
            if not kw:
                continue
            vol = row.get("searchVolume") or row.get("search_volume") or row.get("Volume")
            est = row.get("estimatedValue") or row.get("estimated_value") or row.get("EstimatedValue")
            cpc = row.get("cpc") if row.get("cpc") is not None else row.get("CPC")
            try:
                vol_i = int(round(float(vol))) if vol is not None and str(vol).strip() else 0
            except Exception:
                vol_i = 0
            top_kw.append(
                {
                    "Name": str(kw),
                    "Keyword": str(kw),
                    "Volume": vol_i,
                    "EstimatedValue": est,
                    "Cpc": cpc,
                }
            )

    hk_canon = host_key(url) if url else (host_key(domain) if domain else "")
    site_field = hk_canon or (domain or "").strip() or host_key(str(raw.get("searchUrl") or ""))
    return {
        "SiteName": site_field,
        "Domain": domain,
        "Url": url or (f"https://{hk_canon}" if hk_canon else ""),
        "Engagements": {
            "Visits": visits_f,
            "VisitsFormatted": _format_visits_integer_display(visits_f),
            "PagePerVisit": ppg,
            "BounceRate": br,
            "TimeOnSite": tos,
        },
        "EstimatedMonthlyVisits": monthly_df,
        "TopCountryShares": top_country_shares,
        "TopKeywordShares": top_kw,
        "TopKeywords": top_kw,
    }


def merge_outside_similarweb_fallback_batch(part_domains: list, batch_items: list) -> tuple[list, int]:
    """
    Sau actor Similarweb mặc định: với mỗi domain trong batch, nếu không có traffic hợp lệ
    thì gọi actor fallback (radeance/similarweb-scraper), chuẩn hoá và ghi đè vào map theo host.

    Trả về (danh sách item theo thứ tự part_domains, số domain đã gọi fallback).
    """
    if not isinstance(part_domains, list) or not part_domains:
        return (batch_items if isinstance(batch_items, list) else []), 0
    batch_items = batch_items if isinstance(batch_items, list) else []

    env_fb = os.getenv("COLLABS_OUTSIDE_SIMILARWEB_FALLBACK_ACTOR")
    if env_fb is not None and not str(env_fb).strip():
        fallback_actor = ""
    else:
        fallback_actor = (str(env_fb).strip() if env_fb else DEFAULT_OUTSIDE_SIMILARWEB_FALLBACK_ACTOR)

    by_h: dict[str, dict] = {}
    for it in batch_items:
        if not isinstance(it, dict):
            continue
        k = host_key(apify_site_field(it))
        if k:
            by_h[k] = it

    need: list[str] = []
    seen_need: set[str] = set()
    for d in part_domains:
        hk = host_key(d)
        if not hk:
            continue
        it = by_h.get(hk, {})
        if _similarweb_item_has_traffic(it):
            continue
        if hk not in seen_need:
            seen_need.add(hk)
            need.append(hk)

    if not need or not fallback_actor:
        out = []
        for d in part_domains:
            hk = host_key(d)
            if not hk:
                continue
            out.append(by_h.get(hk, {}))
        return out, 0

    urls = []
    for hk in need:
        urls.append(f"https://{hk}")

    fb_wait = int(os.getenv("COLLABS_OUTSIDE_SIMILARWEB_WAIT_SECS", "360") or "360")
    run_input = {
        "urls": urls,
        "include_base_data": True,
        "include_similar_sites": False,
        "include_indepth_data": False,
        "output_mode": "individual",
    }
    try:
        ds, fb_tok = _apify_store_actor_dataset_id(fallback_actor, run_input, wait_secs=fb_wait)
        fb_items = apify_list_items(ds, token=fb_tok)
    except Exception as exc:
        print(f"Cảnh báo Similarweb fallback ({fallback_actor}): {exc}")
        out = []
        for d in part_domains:
            hk = host_key(d)
            if not hk:
                continue
            out.append(by_h.get(hk, {}))
        return out, 0

    for i, raw in enumerate(fb_items):
        if not isinstance(raw, dict):
            continue
        norm = normalize_radeance_similarweb_item(raw)
        if not norm:
            continue
        row_hosts = _radeance_dataset_row_host_keys(raw)
        matched: str | None = None
        for hk in need:
            if hk in row_hosts:
                matched = hk
                break
        if matched is None and i < len(need):
            matched = need[i]
        nk = host_key(apify_site_field(norm))
        if matched:
            by_h[matched] = norm
        if nk:
            by_h[nk] = norm

    out = []
    for d in part_domains:
        hk = host_key(d)
        if not hk:
            continue
        out.append(by_h.get(hk, {}))
    return out, len(need)


def check_apify_connection() -> str:
    """Kiểm tra kết nối Apify; thử lần lượt mọi token trong APIFY_TOKENS."""
    candidates = apify_effective_token_candidates()
    if not candidates:
        raise _apify_tokens_missing_error("connection check")
    last_err = ""
    total = len(candidates)
    for idx, tok in enumerate(candidates):
        url = f"https://api.apify.com/v2/users/me?token={tok}"
        try:
            res = requests.get(url, timeout=20)
        except requests.RequestException as exc:
            last_err = str(exc)
            continue
        if not res.ok:
            last_err = f"HTTP {res.status_code}: {res.text[:300]}"
            if _apify_http_suggests_token_failover(res.status_code, res.text or ""):
                if idx + 1 < total:
                    print(f"Apify (connection check): token #{idx + 1}/{total} lỗi — thử token tiếp theo.")
                continue
            raise RuntimeError(f"Apify connection check lỗi HTTP {res.status_code}: {res.text[:300]}")
        try:
            body = res.json()
        except Exception as exc:
            raise RuntimeError("Apify connection check trả về dữ liệu không hợp lệ.") from exc
        data = body.get("data") or {}
        username = (
            str(data.get("username") or "").strip()
            or str(data.get("email") or "").strip()
            or str(data.get("id") or "").strip()
            or "unknown-user"
        )
        if idx > 0:
            print(f"Apify (connection check): đã chuyển sang token #{idx + 1}/{total}.")
        return username
    raise RuntimeError(
        f"Apify: tất cả {total} token đã hết quota hoặc lỗi quyền (connection check): {last_err}"
    )


def _apify_check_token_quota(tok: str) -> tuple[bool, str]:
    """
    Kiểm tra xem token Apify còn quota hay không.
    Returns (ok, message). ok=False nghĩa là token hết quota / lỗi quyền.
    """
    url = f"https://api.apify.com/v2/users/me?token={tok}"
    try:
        res = requests.get(url, timeout=20)
    except requests.RequestException as exc:
        return False, f"Lỗi kết nối: {exc}"
    if not res.ok:
        body = res.text or ""
        if _apify_http_suggests_token_failover(res.status_code, body):
            return False, f"HTTP {res.status_code}: {body[:300]}"
        return False, f"HTTP {res.status_code}: {body[:300]}"
    try:
        body = res.json()
    except Exception:
        return False, "Phản hồi không hợp lệ"
    data = body.get("data") or {}
    plan = (data.get("plan") or {}).get("title", "") or ""
    # Kiểm tra thêm: nếu có thông tin về usage limits
    return True, f"OK (plan: {plan})"


def check_apify_all_tokens_quota() -> tuple[list[str], list[tuple[str, str]]]:
    """
    Kiểm tra quota của TẤT CẢ token Apify trước khi bắt đầu lọc.
    Trả về (working_tokens, failed_tokens_with_reason).
    Nếu failed_tokens chỉ toàn quota-limit thì không raise — chỉ cảnh báo.
    """
    candidates = apify_effective_token_candidates()
    if not candidates:
        raise _apify_tokens_missing_error("token quota check")
    working = []
    failed: list[tuple[str, str]] = []
    for tok in candidates:
        ok, msg = _apify_check_token_quota(tok)
        if ok:
            working.append(tok)
        else:
            failed.append((tok, msg))
    return working, failed


def apify_list_items(dataset_id: str, token: str | None = None) -> list:
    if str(token or "").strip():
        tok = str(token).strip()
    else:
        cand = apify_effective_token_candidates()
        if not cand:
            raise _apify_tokens_missing_error("list items")
        tok = cand[0]
    http_retries = int(os.getenv("APIFY_HTTP_RETRIES", "3") or "3")
    if http_retries < 1:
        http_retries = 1
    connect_timeout_sec = float(os.getenv("APIFY_CONNECT_TIMEOUT_SECS", "20") or "20")
    if connect_timeout_sec < 3:
        connect_timeout_sec = 3.0

    def _get_with_retry(req_url: str, read_timeout_sec: float):
        last_exc: Exception | None = None
        for attempt in range(1, http_retries + 1):
            try:
                return requests.get(req_url, timeout=(connect_timeout_sec, max(5.0, float(read_timeout_sec))))
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= http_retries:
                    break
                time.sleep(min(6.0, 1.2 * attempt))
        raise RuntimeError(f"Apify list items request thất bại sau {http_retries} lần thử: {last_exc}")

    items = []
    offset = 0
    limit = 1000
    while True:
        url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={tok}&offset={offset}&limit={limit}&clean=true"
        res = _get_with_retry(url, read_timeout_sec=120)
        if not res.ok:
            raise RuntimeError(f"Apify list items lỗi HTTP {res.status_code}: {res.text[:300]}")
        chunk = res.json()
        if not isinstance(chunk, list) or not chunk:
            break
        items.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit
    return items


def chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main():
    out_path = BASE_DIR / "result.csv"

    offers = fetch_all_uppromote_offers()
    print(f"Loaded {len(offers)} offers (Uppromote)")

    snapshot_path = BASE_DIR / "uppromote-offers-last.json"
    with snapshot_path.open("w", encoding="utf-8") as f:
        json.dump({"fetchedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "count": len(offers), "offers": offers}, f, ensure_ascii=False)
    print(f"Đã lưu snapshot offers -> {snapshot_path}")

    from_offers = unique_hosts([o.get("url", "") for o in offers])
    domain_file = Path(os.getenv("DOMAIN_FILE", str(BASE_DIR / "domain.txt")))
    from_file = read_domains_from_txt(domain_file)
    domains = sorted(set(from_offers + from_file))
    if not domains:
        raise RuntimeError("Không có domain: thêm url trong offers Uppromote hoặc tạo domain.txt.")
    print(f"Apify sẽ chạy trên {len(domains)} domain (từ offer + domain.txt nếu có).")

    print(f"Chạy Actor {ACTOR_ID} với {len(domains)} domain...")
    items = []
    max_domains_per_run = int(
        os.getenv("APIFY_MAX_DOMAINS_PER_RUN", str(DEFAULT_APIFY_MAX_DOMAINS_PER_RUN))
        or str(DEFAULT_APIFY_MAX_DOMAINS_PER_RUN)
    )
    for idx, part in enumerate(chunked(domains, max_domains_per_run), start=1):
        print(f"Apify batch {idx}: {len(part)} domains")
        dataset_id, apify_tok = apify_call_actor(part)
        items.extend(apify_list_items(dataset_id, token=apify_tok))

    by_host = {}
    for item in items:
        site = apify_site_field(item)
        key = host_key(site)
        if key:
            by_host[key] = item

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

    try:
        csv_handle = out_path.open("w", encoding="utf-8", newline="")
    except PermissionError:
        fallback = BASE_DIR / f"uppromote_{int(time.time())}.csv"
        print(f"Cảnh báo: {out_path.name} đang bị khóa, ghi sang {fallback.name}")
        out_path = fallback
        csv_handle = out_path.open("w", encoding="utf-8", newline="")

    with csv_handle as f:
        writer = csv.writer(f)
        writer.writerow(header)

        rows = 0
        for offer in offers:
            brand = offer.get("brand", "")
            url = offer.get("url", "")
            key = host_key(url)
            item = lookup_apify_item(url, by_host)
            eng = engagement_from_item(item)
            visits = parse_visits_from_engagement(eng)
            status = "GET" if visits >= float(MIN_VISITS) else "NO"

            commission_str = str(offer.get("offer", "") or "")

            countries = item.get("TopCountryShares") or []
            keyword_shares = keyword_shares_from_item(item)

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
                    top_countries_csv(countries),
                    top_keywords_csv(keyword_shares),
                    commission_str,
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
                    join_list(offer.get("promotion_details")),
                    join_list(offer.get("target_audience_customer_channels")),
                    join_list(offer.get("target_audience_locations")),
                    join_list(offer.get("target_audience_ages")),
                    join_list(offer.get("target_audience_genders")),
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
            visits_show = eng.get("VisitsFormatted") or (int(visits) if visits.is_integer() else visits)
            print(f"{status} {brand} | {key} | visits={visits_show}")

    print(f"Done. {rows} dòng -> {out_path} (status GET nếu traffic>{MIN_VISITS})")


# ─────────────────────────────────────────────
# AUTO LOGIN UPPROMOTE BROWSER (Playwright)
# ─────────────────────────────────────────────

UPPROMOTE_CDP_PORT = 9501
UPPROMOTE_CDP_HOST = "127.0.0.1"
UPPROMOTE_OFFERS_URL = "https://marketplace.uppromote.com/offers/find-offers"
UPPROMOTE_LOGIN_URL = "https://marketplace.uppromote.com/auth/login"
UPPROMOTE_API_TEST_URL = (
    "https://mkp-api.uppromote.com/api/v1/marketplace-offer/find-offer/datatable/data"
)

_uppromote_ui_log_fn: Callable[[str], None] | None = None


def set_uppromote_ui_log_fn(fn: Callable[[str], None] | None) -> None:
    global _uppromote_ui_log_fn
    _uppromote_ui_log_fn = fn


def _uppromote_ui_log(msg: str) -> None:
    line = msg if str(msg).startswith("Uppromote:") else f"Uppromote: {msg}"
    print(line, flush=True)
    fn = _uppromote_ui_log_fn
    if fn:
        try:
            fn(line)
        except Exception:
            pass


def _jwt_exp_unix(token: str) -> int | None:
    import base64
    import json as _json

    try:
        parts = (token or "").split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1].replace("-", "+").replace("_", "/")
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = _json.loads(base64.b64decode(payload_b64))
        exp = payload.get("exp")
        return int(exp) if exp else None
    except Exception:
        return None


def _jwt_is_fresh(token: str, buffer_sec: int = 120) -> bool:
    exp = _jwt_exp_unix(token)
    if not exp:
        return False
    return exp > time.time() + buffer_sec


def _verify_uppromote_bearer(token: str) -> bool:
    if not token:
        return False
    try:
        res = requests.get(
            UPPROMOTE_API_TEST_URL,
            params={
                "page": 1,
                "per_page": 1,
                "keyword": "",
                "sort_by": "most_relevant",
                "tab[0]": "all-offers",
                "pathPage": "/offers/find-offers",
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": os.getenv(
                    "UPPROMOTE_USER_AGENT",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                ),
            },
            timeout=30,
        )
        return res.status_code == 200
    except Exception:
        return False


def _uppromote_user_data_dir() -> str:
    return str(BASE_DIR / "edge_profiles" / "uppromote")


def _uppromote_edge_launch_extra_args() -> list[str]:
    """Flag khởi động Edge chỉ cho Uppromote (9501). Collabs không dùng hàm này."""
    mode = os.getenv("UPPROMOTE_EDGE_HIDDEN", "1").strip().lower()
    if mode in ("0", "false", "no", "off", "show", "visible"):
        return []
    if mode in ("offscreen", "2"):
        return ["--window-position=-32000,-32000", "--window-size=1280,720"]
    return ["--headless=new", "--disable-gpu"]


def _uppromote_cdp_connect_url(cdp_url: str | None = None) -> str:
    """Chuẩn hóa CDP URL — luôn dùng 127.0.0.1 (tránh localhost → ::1 ECONNREFUSED)."""
    from edge_cdp import cdp_url_host_port

    raw = (cdp_url or os.getenv("UPPROMOTE_CDP_URL") or f"http://{UPPROMOTE_CDP_HOST}:{UPPROMOTE_CDP_PORT}").strip()
    host, port = cdp_url_host_port(raw)
    if host in ("localhost", "::1"):
        host = UPPROMOTE_CDP_HOST
    if not port:
        port = UPPROMOTE_CDP_PORT
    return f"http://{host}:{port}"


def _extract_uppromote_tokens_from_cookies(cookies: list) -> tuple[str | None, str | None]:
    access = next((c["value"] for c in cookies if c.get("name") == "marketplace_access_token"), None)
    refresh = next((c["value"] for c in cookies if c.get("name") == "marketplace_refresh_token"), None)
    return access, refresh


def _write_uppromote_tokens_to_env(access: str | None, refresh: str | None) -> bool:
    if not access:
        return False
    env_path = Path(BASE_DIR) / ".env"
    env_lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    updated = False

    def _update_env(key: str, value: str) -> list:
        nonlocal updated, env_lines
        lines: list[str] = []
        found = False
        for line in env_lines:
            if line.strip().startswith(f"{key}="):
                lines.append(f'{key}="{value}"')
                found = True
                updated = True
            else:
                lines.append(line)
        if not found:
            lines.append(f'{key}="{value}"')
            updated = True
        env_lines = lines
        return lines

    _update_env("UPPROMOTE_BEARER_TOKEN", access)
    if refresh:
        _update_env("UPPROMOTE_REFRESH_TOKEN", refresh)

    if updated:
        env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")
        os.environ["UPPROMOTE_BEARER_TOKEN"] = access
        if refresh:
            os.environ["UPPROMOTE_REFRESH_TOKEN"] = refresh
    return updated


def _ensure_uppromote_edge_cdp(cdp_url: str, log: Callable[[str], None]) -> bool:
    from edge_cdp import cdp_url_host_port, ensure_edge_cdp_running

    host, port = cdp_url_host_port(cdp_url)
    if host in ("localhost", "::1"):
        host = UPPROMOTE_CDP_HOST
    udir = _uppromote_user_data_dir()
    Path(udir).mkdir(parents=True, exist_ok=True)
    extra = _uppromote_edge_launch_extra_args()
    if extra:
        log("Mở Edge Uppromote ở chế độ ẩn (headless/offscreen).")
    return ensure_edge_cdp_running(
        port=port,
        user_data_dir=udir,
        log=log,
        wait_sec=25.0,
        host=host,
        extra_args=extra,
    )


def _attach_uppromote_bearer_capture(page) -> tuple[list[str], Callable[[], None]]:
    """Bắt Bearer token từ request tới mkp-api / marketplace."""
    captured: list[str] = []

    def on_request(request) -> None:
        try:
            url = request.url or ""
            if "uppromote.com" not in url:
                return
            auth = (request.headers.get("authorization") or request.headers.get("Authorization") or "").strip()
            if not auth.lower().startswith("bearer "):
                return
            tok = auth[7:].strip()
            if tok.startswith("eyJ") and tok not in captured:
                captured.append(tok)
        except Exception:
            pass

    page.on("request", on_request)

    def detach() -> None:
        try:
            page.remove_listener("request", on_request)
        except Exception:
            pass

    return captured, detach


def _pick_best_uppromote_access(candidates: list[str], log: Callable[[str], None]) -> str | None:
    seen: set[str] = set()
    ordered: list[str] = []
    for tok in candidates:
        if tok and tok not in seen:
            seen.add(tok)
            ordered.append(tok)

    for tok in ordered:
        if _verify_uppromote_bearer(tok):
            log("Chọn token hoạt động (verify API OK).")
            return tok

    fresh = [t for t in ordered if _jwt_is_fresh(t)]
    if fresh:
        exp = _jwt_exp_unix(fresh[-1])
        log(f"Chọn token JWT còn hạn (exp={exp}).")
        return fresh[-1]

    if ordered:
        log("Dùng token cuối (chưa verify được API).")
        return ordered[-1]
    return None


def _load_offers_and_capture_token(page, log: Callable[[str], None]) -> str | None:
    captured, detach = _attach_uppromote_bearer_capture(page)
    try:
        log(f"Navigate → {UPPROMOTE_OFFERS_URL}")
        page.goto(UPPROMOTE_OFFERS_URL, wait_until="domcontentloaded", timeout=30_000)
        try:
            page.wait_for_response(
                lambda r: "mkp-api.uppromote.com" in (r.url or "") and r.status == 200,
                timeout=25_000,
            )
            log("Trang offers đã gọi API mkp-api thành công.")
        except Exception:
            log("Chờ response mkp-api timeout — thử token đã bắt / cookies.")
        time.sleep(2)
        log(f"URL hiện tại: {page.url}")
        return _pick_best_uppromote_access(captured, log)
    finally:
        detach()


def _collect_uppromote_tokens(page, context, log: Callable[[str], None]) -> tuple[str | None, str | None]:
    access = _load_offers_and_capture_token(page, log)
    cookie_access, refresh = _extract_uppromote_tokens_from_cookies(context.cookies())

    candidates: list[str] = []
    if access:
        candidates.append(access)
    if cookie_access:
        candidates.append(cookie_access)

    best = _pick_best_uppromote_access(candidates, log)
    if best and not refresh:
        _, refresh = _extract_uppromote_tokens_from_cookies(context.cookies())
    return best, refresh


def _uppromote_perform_login(page, email: str, password: str, log: Callable[[str], None]) -> bool:
    log("Chưa login, tiến hành đăng nhập...")
    if "/auth/login" not in page.url and "/login" not in page.url:
        log("Mở trang login...")
        page.goto(UPPROMOTE_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
    time.sleep(4)

    email_sel = 'input[type="email"], input[name="email"], input[id="email"], input[placeholder*="email" i]'
    pw_sel = 'input[type="password"], input[name="password"]'
    btn_sel = 'button[type="submit"], button:has-text("Sign in"), button:has-text("Login"), button:has-text("Đăng nhập")'

    log("Điền email...")
    page.locator(email_sel).first.wait_for(state="visible", timeout=20_000)
    page.locator(email_sel).first.fill(email)
    time.sleep(0.5)

    log("Điền password...")
    page.locator(pw_sel).first.wait_for(state="visible", timeout=15_000)
    page.locator(pw_sel).first.fill(password)
    time.sleep(0.5)

    log("Click đăng nhập...")
    page.locator(btn_sel).first.click(timeout=15_000)

    log("Đợi redirect sau login...")
    try:
        page.wait_for_url(
            lambda url: "/offers" in url or "/find-offers" in url or "/dashboard" in url,
            timeout=60_000,
        )
        log(f"Login thành công! URL: {page.url}")
        return True
    except Exception:
        log(f"Chưa redirect (60s), URL hiện tại: {page.url}")
        return False


def _auto_login_uppromote_browser(cdp_url: str | None = None) -> bool:
    """Mở Edge CDP (port 9501), vào find-offers, login nếu cần, lấy token → .env."""
    _uppromote_ui_log("Bắt đầu lấy token mới qua Edge (ẩn)...")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _uppromote_ui_log("Chưa cài playwright — không thể auto-login.")
        return False

    email = os.getenv("UPPROMOTE_EMAIL", "").strip()
    from local_secret import resolve_uppromote_password_with_error

    password, pwd_err = resolve_uppromote_password_with_error()
    if not email:
        _uppromote_ui_log("Thiếu UPPROMOTE_EMAIL trong .env (cạnh file .exe).")
        return False
    if not password:
        _uppromote_ui_log(pwd_err or "Thiếu UPPROMOTE_PASSWORD trong .env (cạnh file .exe).")
        return False

    def log(msg: str) -> None:
        _uppromote_ui_log(msg)

    connect_url = _uppromote_cdp_connect_url(cdp_url)
    log(f"Email: {email[:3]}*** | CDP: {connect_url}")

    if not _ensure_uppromote_edge_cdp(connect_url, log):
        log("Không mở được Edge CDP trên port 9501.")
        return False

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(connect_url, timeout=30_000)
        except Exception as exc:
            log(f"Không kết nối được CDP: {exc}")
            return False

        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()

        try:
            access, refresh = _collect_uppromote_tokens(page, context, log)
            needs_login = (
                not access
                or not _verify_uppromote_bearer(access or "")
                or "/auth/login" in page.url
                or "/login" in page.url
            )

            if needs_login:
                log("Chưa có session hợp lệ — đang đăng nhập bằng email trong .env...")
                if not _uppromote_perform_login(page, email, password, log):
                    log("Đăng nhập có thể chưa xong (Cloudflare/captcha?) — thử lấy token...")
                access, refresh = _collect_uppromote_tokens(page, context, log)
            else:
                log("Session còn hợp lệ — chỉ refresh token.")

            if access:
                log(f"Token access: {access[:40]}...")
            if refresh:
                log(f"Token refresh: {refresh[:40]}...")

            if not access:
                log("Không lấy được marketplace_access_token.")
                return False

            if not _verify_uppromote_bearer(access):
                log("Token lấy được nhưng API vẫn 401 — cần đăng nhập thủ công trên Edge (port 9501).")
                return False

            if _write_uppromote_tokens_to_env(access, refresh):
                log("Đã lưu token mới vào .env.")
                return True

            log("Không ghi được token vào .env")
            return False

        except Exception as exc:
            log(f"Lỗi: {exc}")
            return False


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Nhận SIGINT] Thoát.")
        sys.exit(0)
    except Exception as exc:
        print(exc)
        sys.exit(1)

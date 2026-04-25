import csv
import ast
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests

from runtime_paths import app_dir

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


BASE_DIR = app_dir()
ACTOR_ID = "aqPbs3KeH9aD8b22w"
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
DEFAULT_COLLABS_LIMIT = 48
MIN_COLLABS_LIMIT = 12
MAX_COLLABS_LIMIT = 48
COLLABS_LIMIT_STEP = 12


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
    """Số brand/request Collabs: bội số của 12, trong [12, 48]. Rỗng/sai → mặc định."""
    if raw is None:
        return DEFAULT_COLLABS_LIMIT
    s = str(raw).strip()
    if not s:
        return DEFAULT_COLLABS_LIMIT
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return DEFAULT_COLLABS_LIMIT
    n = max(MIN_COLLABS_LIMIT, min(MAX_COLLABS_LIMIT, n))
    n = (n // COLLABS_LIMIT_STEP) * COLLABS_LIMIT_STEP
    if n < MIN_COLLABS_LIMIT:
        n = MIN_COLLABS_LIMIT
    return n


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


load_env_file(BASE_DIR / ".env")


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
    return (
        item.get("SiteName")
        or item.get("siteName")
        or item.get("Domain")
        or item.get("domain")
        or ""
    )


def engagement_from_item(item: dict) -> dict:
    """Khối engagement / hoặc Visits nằm ngang item."""
    if not item:
        return {}
    eng = item.get("Engagments") or item.get("Engagements") or item.get("engagement")
    if isinstance(eng, dict) and eng:
        return eng
    if item.get("Visits") is not None or item.get("VisitsFormatted") is not None:
        return item
    return {}


def parse_visits_from_engagement(eng: dict) -> float:
    if not eng:
        return 0.0
    raw = eng.get("Visits")
    if raw is None:
        raw = eng.get("EstimatedVisits") or eng.get("Traffic") or eng.get("MonthlyVisits")
    return parse_visits_value(raw)


def estimated_monthly_visits_formatted(item: dict, eng: dict | None = None) -> str:
    """Chuỗi traffic theo tháng từ Apify, ưu tiên field gốc trên item."""
    src_eng = eng if isinstance(eng, dict) else {}
    candidates = (
        (item or {}).get("EstimatedMonthlyVisitsFormatted"),
        src_eng.get("EstimatedMonthlyVisitsFormatted"),
        (item or {}).get("EstimatedMonthlyVisits"),
        src_eng.get("EstimatedMonthlyVisits"),
    )
    for v in candidates:
        if v is not None and str(v).strip():
            return format_estimated_monthly_visits(v)
    return ""


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

COLLABS_CATEGORY_LABELS = {
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


def with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    # Always force per_page from env for consistent paging.
    query["per_page"] = os.getenv("UPPROMOTE_PER_PAGE", str(DEFAULT_OFFERS_PER_PAGE))
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


def fetch_uppromote_offer_detail(shop_id) -> dict:
    base = (os.getenv("UPPROMOTE_DETAIL_BASE_URL") or "https://mkp-api.uppromote.com").strip().rstrip("/")
    url = f"{base}/api/v1/marketplace-offer/offer-detail/{shop_id}?mobile=false"
    res = requests.get(url, headers=build_uppromote_headers(), timeout=60)
    text = res.text
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


def resolve_redirected_url(url: str, timeout_sec: int = 20) -> str:
    """
    Theo dõi redirect để lấy URL đích cuối (brand gốc).
    Trả về URL ban đầu nếu request lỗi/timeout.
    """
    raw = str(url or "").strip()
    if not raw:
        return ""
    if not (raw.startswith("http://") or raw.startswith("https://")):
        return raw
    try:
        res = requests.get(raw, allow_redirects=True, timeout=timeout_sec, stream=True)
        final_url = str(res.url or "").strip()
        try:
            res.close()
        except Exception:
            pass
        return final_url or raw
    except Exception:
        return raw


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
        "/ambassadors",
        "/community",
        "/affiliates",
        "/affiliate",
        "/affiliate-program",
        "/affiliate-programs",
        "/collab",
        "/collabs",
        "/collaborators",
        "/partners",
        "/partner",
        "/partner-program",
        "/partner-programs",
        "/collaborations",
        "/collaboration",
        "/ambassador-program",
        "/ambassador-programs",
        "/curious-community",
    )
    if any(p in u for p in signup_path_hints):
        return True
    if "apply now" in text or "apply-now" in text:
        return True
    score = 0
    if "collab" in text:
        score += 1
    if "affiliate" in text:
        score += 1
    if "apply" in text or "application" in text:
        score += 1
    return score >= 2


def discover_collabs_signup_url(site_url: str, timeout_sec: int = 20) -> str:
    """
    Tìm link đăng ký collabs từ domain chính.
    Ưu tiên /pages/collab; fallback quét homepage để tìm href chứa collab/affiliate.
    """
    raw = str(site_url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    if not parsed.netloc:
        return ""
    base = f"{parsed.scheme or 'https'}://{parsed.netloc}"

    def _try_get(candidate_url: str) -> tuple[str, str]:
        try:
            res = requests.get(candidate_url, allow_redirects=True, timeout=timeout_sec)
            final_url = str(res.url or candidate_url).strip()
            if not res.ok:
                return "", ""
            text = res.text or ""
            return final_url, text
        except Exception:
            return "", ""

    preferred_paths = [
        "/pages/collab",
        "/pages/collabs",
        "/pages/collabs-signup",
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
        "/ambassadors",
        "/community",
        "/affiliates",
        "/affiliate",
        "/affiliate-program",
        "/affiliate-programs",
        "/ambassadors",
        "/collab",
        "/collabs",
        "/collaborators",
        "/partners",
        "/partner",
        "/partner-program",
        "/partner-programs",
        "/partner-programs",
        "/collaborations",
        "/collaboration",
        "/ambassador-program",
        "/ambassador-programs",
        "/curious-community",
    ]
    for p in preferred_paths:
        final_url, text = _try_get(f"{base}{p}")
        if final_url and _collabs_page_looks_like_signup(text, final_url):
            return final_url

    home_url, home_html = _try_get(base)
    if not home_url:
        return ""

    # Quét toàn site (có giới hạn) để tìm page apply.
    max_scan_pages = int(os.getenv("COLLABS_SIGNUP_SCAN_MAX_PAGES", "25") or "25")
    if max_scan_pages < 1:
        max_scan_pages = 1

    def _extract_same_domain_links(page_html: str, page_url: str) -> list[str]:
        out = []
        for href in re.findall(r"""href=["']([^"'#]+)["']""", page_html or "", flags=re.I):
            h = str(href).strip()
            if not h:
                continue
            cand = urljoin(page_url, h)
            cp = urlparse(cand)
            if cp.netloc != parsed.netloc:
                continue
            path = cp.path or "/"
            # Bỏ link static/media để không tốn lượt quét.
            low_path = path.lower()
            if any(low_path.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".js", ".css", ".pdf", ".xml")):
                continue
            out.append(f"{cp.scheme or 'https'}://{cp.netloc}{path}")
        return out

    queue = [home_url]
    seen = set()
    idx = 0
    while idx < len(queue) and len(seen) < max_scan_pages:
        cur = queue[idx]
        idx += 1
        if cur in seen:
            continue
        seen.add(cur)
        final_url, text = _try_get(cur)
        if not final_url:
            continue
        if _collabs_page_looks_like_signup(text, final_url):
            return final_url

        for nxt in _extract_same_domain_links(text, final_url):
            if nxt in seen:
                continue
            low = nxt.lower()
            # Ưu tiên đường dẫn có tín hiệu collab/apply/affiliate.
            if any(k in low for k in ("collab", "affiliate", "ambassador", "apply")):
                queue.insert(idx, nxt)
            else:
                queue.append(nxt)

    return ""


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
    "Hoa hồng mạng lưới",
    "Thời gian giữ đơn",
    "Danh mục",
    "Trạng thái hợp tác",
    "Tình trạng hợp tác",
    "Đã lưu",
    "Đã mua trước đó",
    "Quốc gia mục tiêu",
    "Traffic (hiển thị)",
    "Traffic ước tính/tháng",
    "Trang/lượt xem",
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
    website = str(offer.get("url", "") or "").strip()
    apply_url = str(offer.get("client_url", "") or "").strip()
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
        offer.get("offer", ""),
        offer.get("collabs_holding_period", ""),
        offer.get("category", ""),
        offer.get("collabs_partnership_status", ""),
        offer.get("collabs_partnership_state", ""),
        fmt_yes_no_bool_like(offer.get("collabs_saved")),
        fmt_yes_no_bool_like(offer.get("collabs_previously_purchased")),
        offer.get("collabs_target_countries", ""),
        eng.get("VisitsFormatted", ""),
        estimated_monthly,
        eng.get("PagePerVisit", ""),
        format_percent_cell(eng.get("BounceRate", "")),
        top_countries_csv(item.get("TopCountryShares") or []),
        top_keywords_csv(keyword_shares_from_item(item)),
        offer.get("collabs_logo_url", ""),
        offer.get("offer_id", ""),
        offer.get("collabs_shopify_store_id", ""),
    ]


def write_xlsx_highlight_status(path: Path, header: list, rows: list, status_col: int = 0) -> None:
    """Ghi file Excel: dòng có trạng thái ĐẠT (hoặc GET) được tô nền xanh lá nhạt."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill

    wb = Workbook()
    ws = wb.active
    ws.append(list(header))
    header_list = list(header)
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
        cells = list(row)
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


def fetch_collabs_page(base_url: str, first: int, after: str | None = None) -> dict:
    payload = {
        "operationName": "BrandsQuery",
        "query": COLLABS_BRANDS_QUERY,
        "variables": {
            "first": int(first),
            "productCategories": [],
            "brandValues": [],
        },
    }
    if after:
        payload["variables"]["after"] = str(after)
    res = requests.post(base_url, headers=build_collabs_headers(), json=payload, timeout=60)
    text = res.text
    try:
        body = res.json()
    except Exception as exc:
        raise RuntimeError(f"Collabs parse JSON lỗi (HTTP {res.status_code}): {text[:180]}") from exc
    if not res.ok:
        raise RuntimeError(f"Collabs HTTP {res.status_code}: {text[:300]}")
    if body.get("errors"):
        raise RuntimeError(f"Collabs GraphQL lỗi: {json.dumps(body.get('errors'), ensure_ascii=False)[:300]}")
    return body if isinstance(body, dict) else {}


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

        all_stores.extend(page_items)
        print(f"Goaffpro: +{len(page_items)} store (lũy kế {len(all_stores)})")

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
        all_offers.extend(page_items)
        print(f"Refersion: +{len(page_items)} offer (lũy kế {len(all_offers)})")
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


def fetch_uppromote_page(base_url: str, page: int) -> dict:
    request_url = with_page(base_url, page)
    res = requests.get(request_url, headers=build_uppromote_headers(), timeout=60)
    text = res.text
    try:
        body = res.json()
    except Exception as exc:
        raise RuntimeError(f"Uppromote parse JSON lỗi (HTTP {res.status_code}): {text[:180]}") from exc
    if not res.ok:
        raise RuntimeError(f"Uppromote HTTP {res.status_code}: {text[:300]}")
    if body.get("status") not in (200, "200"):
        raise RuntimeError(f"Uppromote API lỗi: {text[:300]}")
    return body


def fetch_all_uppromote_offers() -> list:
    base_url = (os.getenv("UPPROMOTE_API_URL") or "").strip()
    if not base_url:
        raise RuntimeError("Thiếu UPPROMOTE_API_URL trong .env")

    enforce_fixed_fetch_defaults()
    max_pages_cap = uppromote_max_pages_cap()
    delay_ms = int(os.getenv("UPPROMOTE_PAGE_DELAY_MS", str(DEFAULT_UPPROMOTE_PAGE_DELAY_MS)) or str(DEFAULT_UPPROMOTE_PAGE_DELAY_MS))

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

        all_offers.extend(page_items)
        print(f"Uppromote: +{len(page_items)} offer (lũy kế {len(all_offers)})")

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


def apify_call_actor(domains: list) -> str:
    token = (os.getenv("APIFY_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Thiếu APIFY_TOKEN trong .env")
    wait_secs = int(os.getenv("APIFY_WAIT_FOR_FINISH_SECS", "240") or "240")
    url = f"https://api.apify.com/v2/acts/{ACTOR_ID}/runs?token={token}&waitForFinish={wait_secs}"
    run_input = {"domains": domains, "proxyConfiguration": {"useApifyProxy": False}}
    res = requests.post(url, json=run_input, timeout=wait_secs + 30)
    if not res.ok:
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
        poll_res = requests.get(poll_url, timeout=wait_poll_secs + 30)
        if not poll_res.ok:
            raise RuntimeError(f"Apify poll lỗi HTTP {poll_res.status_code}: {poll_res.text[:300]}")
        data = (poll_res.json() or {}).get("data") or data
        status = data.get("status")
        print(f"Apify poll {poll_idx}: status={status}")

    if status != "SUCCEEDED":
        raise RuntimeError(f"Apify run không thành công (status={status})")

    dataset_id = data.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError("Apify không trả về defaultDatasetId")
    return dataset_id


def check_apify_connection() -> str:
    """Kiểm tra kết nối/tính hợp lệ APIFY_TOKEN trước khi chạy lọc."""
    token = (os.getenv("APIFY_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("Thiếu APIFY_TOKEN trong .env")
    url = f"https://api.apify.com/v2/users/me?token={token}"
    try:
        res = requests.get(url, timeout=20)
    except requests.RequestException as exc:
        raise RuntimeError(f"Không kết nối được Apify: {exc}") from exc
    if not res.ok:
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
    return username


def apify_list_items(dataset_id: str) -> list:
    token = (os.getenv("APIFY_TOKEN") or "").strip()
    items = []
    offset = 0
    limit = 1000
    while True:
        url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}&offset={offset}&limit={limit}&clean=true"
        res = requests.get(url, timeout=120)
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
        dataset_id = apify_call_actor(part)
        items.extend(apify_list_items(dataset_id))

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


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Nhận SIGINT] Thoát.")
        sys.exit(0)
    except Exception as exc:
        print(exc)
        sys.exit(1)

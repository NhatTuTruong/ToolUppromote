import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


BASE_DIR = Path(__file__).resolve().parent
ACTOR_ID = "aqPbs3KeH9aD8b22w"
MIN_VISITS = int(os.getenv("MIN_VISITS", "9000") or "9000")
TOP_KEYWORDS_COUNT = int(os.getenv("TOP_KEYWORDS_COUNT", "5") or "5")


def load_env_file(path: Path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        k = key.strip()
        v = value.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
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


def with_page(url: str, page: int) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    # Always force per_page from env for consistent paging.
    query["per_page"] = os.getenv("UPPROMOTE_PER_PAGE", "50")
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

    max_pages = int(os.getenv("UPPROMOTE_MAX_PAGES", "5") or "5")
    delay_ms = int(os.getenv("UPPROMOTE_PAGE_DELAY_MS", "250") or "250")

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

        if page >= max_pages:
            print(f"Uppromote: dừng vì UPPROMOTE_MAX_PAGES={max_pages}")
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
    candidates = [
        k.get("Volume"),
        k.get("SearchVolume"),
        k.get("MonthlyVolume"),
        k.get("EstTraffic"),
        k.get("Traffic"),
        k.get("Visits"),
        k.get("EstimatedMonthlySearchVolume"),
    ]
    for raw in candidates:
        if isinstance(raw, (int, float)):
            return int(round(raw))
        if isinstance(raw, str) and raw.strip():
            value = raw.replace(",", "").strip()
            if value.isdigit():
                return int(value)
    return 0


def top_keywords_csv(keywords, limit=TOP_KEYWORDS_COUNT):
    if not isinstance(keywords, list):
        return ""
    values = []
    for k in keywords[:limit]:
        values.append(f"{keyword_label(k)} ({keyword_volume(k)})")
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
    ]
    for arr in candidates:
        if isinstance(arr, list) and arr:
            return arr
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
    max_domains_per_run = int(os.getenv("APIFY_MAX_DOMAINS_PER_RUN", "50") or "50")
    for idx, part in enumerate(chunked(domains, max_domains_per_run), start=1):
        print(f"Apify batch {idx}: {len(part)} domains")
        dataset_id = apify_call_actor(part)
        items.extend(apify_list_items(dataset_id))

    by_host = {}
    for item in items:
        site = item.get("SiteName") or item.get("siteName")
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
        fallback = BASE_DIR / f"result-{int(time.time())}.csv"
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
            item = by_host.get(key, {})
            eng = item.get("Engagments") or item.get("Engagements") or {}

            visits_raw = eng.get("Visits", 0)
            try:
                visits = float(visits_raw)
            except Exception:
                visits = 0
            status = "GET" if visits > MIN_VISITS else "NO"

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

"""Probe Uppromote category name -> API id mapping."""
from __future__ import annotations

import json
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from filter import (
    BASE_DIR,
    assert_uppromote_api_url,
    build_uppromote_headers,
    parse_env_file,
)


def build_url(base: str, page: int = 1, per_page: int = 3, category_ids: list[int] | None = None) -> str:
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = str(page)
    query["per_page"] = str(per_page)
    if category_ids:
        for idx, cid in enumerate(category_ids):
            query[f"categories[{idx}]"] = str(cid)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def main() -> None:
    env = parse_env_file(BASE_DIR / ".env")
    base = assert_uppromote_api_url(env.get("UPPROMOTE_API_URL", ""))
    headers = build_uppromote_headers()

    # Try marketplace JS bundles for embedded category list.
    html = requests.get("https://marketplace.uppromote.com/offers/find-offers", timeout=30).text
    scripts = re.findall(r'src="([^"]+\.js[^"]*)"', html)
    print(f"scripts on page: {len(scripts)}")
    for path in scripts:
        url = path if path.startswith("http") else f"https://marketplace.uppromote.com{path}"
        js = requests.get(url, timeout=60).text
        if "Beauty & Health" not in js and "Beauty" not in js:
            continue
        print(f"scan {url} ({len(js)} bytes)")
        # Common minified patterns
        pairs = re.findall(r'\{id:(\d+),name:"([^"]+)"\}', js)
        if not pairs:
            pairs = re.findall(r'"id":(\d+),"name":"([^"]+)"', js)
        if pairs:
            print(json.dumps(dict(pairs), ensure_ascii=False, indent=2))
            return

    # Brute-force ids 1..60 and compare first offer categories string.
    mapping: dict[str, int] = {}
    for cid in range(1, 61):
        url = build_url(base, category_ids=[cid])
        res = requests.get(url, headers=headers, timeout=60)
        if not res.ok:
            continue
        items = (res.json().get("data") or {}).get("data") or []
        if not items:
            continue
        cats = str(items[0].get("categories") or "")
        primary = cats.split(",")[0].strip() if cats else f"id-{cid}"
        if primary not in mapping:
            mapping[primary] = cid
        print(f"id={cid:2d} sample={items[0].get('name')} | {cats}")

    print("\n--- inferred mapping ---")
    print(json.dumps(mapping, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Map Uppromote UI category names to API categories[n] ids."""
from __future__ import annotations

import json
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from filter import BASE_DIR, assert_uppromote_api_url, build_uppromote_headers, parse_env_file

HTML_CATEGORIES = [
    "Art",
    "Adult products",
    "Automobiles & Motorcycles",
    "Baby & Toddler",
    "Beauty & Health",
    "Books",
    "Bundles",
    "Business & Industrial",
    "Business & Professional services",
    "Cameras & Optics",
    "Computers & Office",
    "Education & Training",
    "Electronics",
    "Fashion",
    "Furniture",
    "Gaming",
    "Garden & Outdoors",
    "Gift Cards",
    "Grocery & Food",
    "Hardware",
    "Home & Tools",
    "Jewelry & Accessories",
    "Luggage & Bags",
    "Media",
    "Mom & Kids",
    "Pet supplies",
    "Phone & Telecommunication",
    "Product Add-Ons",
    "Religion & Spirituality",
    "Retail & Consumer goods",
    "Software & Digital products",
    "Sports & Entertainment",
    "Tobacco products",
    "Toys & Hobbies",
    "Travel",
    "Vehicles & Parts",
    "Wellness & Lifestyle",
    "Others",
    "Uncategorized",
]


def build_url(base: str, category_id: int, per_page: int = 20) -> str:
    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["page"] = "1"
    query["per_page"] = str(per_page)
    query["categories[0]"] = str(category_id)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def category_hits(categories_text: str, name: str) -> bool:
    parts = [p.strip() for p in str(categories_text or "").split(",") if p.strip()]
    return name in parts


def main() -> None:
    env = parse_env_file(BASE_DIR / ".env")
    base = assert_uppromote_api_url(env.get("UPPROMOTE_API_URL", ""))
    headers = build_uppromote_headers()

    id_scores: dict[int, dict[str, int]] = {}
    for cid in range(1, 51):
        url = build_url(base, cid)
        res = requests.get(url, headers=headers, timeout=60)
        if not res.ok:
            print(f"id={cid}: HTTP {res.status_code}")
            continue
        items = (res.json().get("data") or {}).get("data") or []
        if not items:
            print(f"id={cid}: empty")
            continue
        scores: dict[str, int] = {}
        for name in HTML_CATEGORIES:
            scores[name] = sum(1 for it in items if category_hits(it.get("categories"), name))
        id_scores[cid] = scores
        best = max(scores.items(), key=lambda x: x[1])
        print(f"id={cid:2d} n={len(items):2d} best={best[0]!r} ({best[1]}/{len(items)}) sample={items[0].get('categories')}")

    mapping: dict[str, int] = {}
    for name in HTML_CATEGORIES:
        best_id = None
        best_score = 0
        for cid, scores in id_scores.items():
            score = scores.get(name, 0)
            if score > best_score:
                best_score = score
                best_id = cid
        if best_id is not None and best_score >= 10:
            mapping[name] = best_id

    print("\n--- HTML name -> API id ---")
    print(json.dumps(mapping, ensure_ascii=False, indent=2))
    missing = [n for n in HTML_CATEGORIES if n not in mapping]
    print("missing:", missing)


if __name__ == "__main__":
    main()
